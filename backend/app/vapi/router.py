from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import json
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from dotenv import load_dotenv

from app.calander.service import create_event
from utils.access_token import refresh_access_token
from utils.token_store import get_refresh_token, DEFAULT_USER_ID

load_dotenv()
router = APIRouter()

CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")


def _get_current_datetime_context() -> str:
    """Get current date and time formatted for AI context."""
    now = datetime.now(timezone.utc)
    formatted_date = now.strftime("%B %d, %Y")
    formatted_time = now.strftime("%I:%M %p")
    day_of_week = now.strftime("%A")
    iso_format = now.isoformat()

    return (
        f"Current date and time (UTC): {day_of_week}, {formatted_date} at {formatted_time} "
        f"(ISO format: {iso_format}). "
        f"IMPORTANT: You MUST call the get_current_time tool FIRST before creating any calendar event. "
        f"Never calculate or guess dates/times yourself. Always use the value returned by get_current_time "
        f"to compute 'tomorrow', 'next week', or any relative time the user mentions."
    )


def _get_current_time_payload(user_timezone: str = None):
    """Return structured current time, in the user's local timezone if provided."""
    utc_now = datetime.now(timezone.utc)

    if user_timezone:
        try:
            tz = ZoneInfo(user_timezone)
            now = utc_now.astimezone(tz)
            tz_label = user_timezone
        except ZoneInfoNotFoundError:
            now = utc_now
            tz_label = "UTC"
            user_timezone = None
    else:
        now = utc_now
        tz_label = "UTC"

    return {
        "currentDateTimeIso": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "time12h": now.strftime("%I:%M %p"),
        "timezone": tz_label,
        "dayOfWeek": now.strftime("%A"),
        "readable": f"{now.strftime('%A, %B %d, %Y')} at {now.strftime('%I:%M %p')} {tz_label}",
        "instruction": (
            f"Current local time is already in {tz_label}. "
            "Use 'date' and 'time' fields directly to compute relative times like 'tomorrow at the same time'. "
            "Do NOT convert or adjust — these values are already in the user's timezone. "
            "Build startIso and endIso using currentDateTimeIso as the base."
        ),
    }


def _get_access_token(user_id: str = DEFAULT_USER_ID) -> str:
    """Get access token from stored refresh token (or env fallback)."""
    refresh_token = get_refresh_token(user_id) or os.getenv("GOOGLE_REFRESH_TOKEN")
    if not refresh_token:
        raise ValueError(
            "No Google tokens found. Connect your calendar first."
        )
    access_token, _ = refresh_access_token(refresh_token, CLIENT_ID, CLIENT_SECRET)
    return access_token


@router.get("/current-time")
async def get_current_time():
    """Endpoint to get current date and time - can be referenced in Vapi system prompt."""
    now = datetime.now(timezone.utc)
    return JSONResponse({
        "currentDateTime": now.isoformat(),
        "currentDateTimeReadable": _get_current_datetime_context(),
        "timestamp": now.timestamp()
    })


@router.post("/webhook")
async def vapi_webhook(request: Request):
    payload = await request.json()
    message = payload.get("message", {})
    message_type = message.get("type")

    # Handle assistant-request: provide current date/time context
    if message_type == "assistant-request":
        current_time_context = _get_current_datetime_context()
        return JSONResponse({
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"{current_time_context}\n\n"
                        "SCHEDULING RULE: You MUST call get_current_time as your VERY FIRST tool call "
                        "whenever the user wants to schedule, reschedule, or mentions any date/time. "
                        "Do NOT attempt to create a calendar event without first calling get_current_time."
                    )
                }
            ]
        })

    # Handle tool-calls
    if message_type != "tool-calls":
        return JSONResponse({"ok": True})

    results = []
    tool_calls = message.get("toolCallList", []) or []

    for tc in tool_calls:
        tool_call_id = tc.get("id")
        function = tc.get("function", {})
        name = function.get("name", "unknown_tool")

        args = function.get("arguments", {})

        if isinstance(args, str):
            try:
                params = json.loads(args) if args else {}
            except json.JSONDecodeError as e:
                results.append({
                    "toolCallId": tool_call_id,
                    "name": name,
                    "result": json.dumps({
                        "error": True,
                        "message": f"Invalid JSON in tool arguments: {str(e)}",
                    }),
                })
                continue
        elif isinstance(args, dict):
            params = args
        else:
            params = {}

        user_id = params.get("userId", DEFAULT_USER_ID)

        if name == "get_current_time":
            user_tz = params.get("timezone")
            out = _get_current_time_payload(user_tz)
            results.append({
                "toolCallId": tool_call_id,
                "name": name,
                "result": json.dumps(out),
            })

        elif name == "create_calendar_event":
            try:
                access_token = _get_access_token(user_id)
            except ValueError as e:
                results.append({
                    "toolCallId": tool_call_id,
                    "name": name,
                    "result": json.dumps({"error": True, "message": str(e)}),
                })
                continue

            # Accept camelCase parameters from Vapi
            title = params.get("title")
            startIso = params.get("startIso")
            endIso = params.get("endIso")
            tz = params.get("timezone", "UTC")

            if not all([title, startIso, endIso]):
                missing = [f for f in ["title", "startIso", "endIso"] if not params.get(f)]
                current = _get_current_time_payload(tz or None)
                results.append({
                    "toolCallId": tool_call_id,
                    "name": name,
                    "result": json.dumps({
                        "error": True,
                        "message": (
                            f"Cannot create event. Missing fields: {missing}. "
                            "You must NOT retry create_calendar_event yet. "
                            "Step 1: use the currentTime below to compute startIso and endIso based on what the user requested. "
                            "Step 2: call create_calendar_event with title, startIso, endIso, and timezone all filled in."
                        ),
                        "currentTime": current,
                    }),
                })
                continue

            # Reject events in the past and return current time so the AI can correct
            try:
                start_dt = datetime.fromisoformat(startIso.replace("Z", "+00:00"))
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                if start_dt < now:
                    current = _get_current_time_payload(tz or None)
                    results.append({
                        "toolCallId": tool_call_id,
                        "name": name,
                        "result": json.dumps({
                            "error": True,
                            "message": "Event start time is in the past. Use the server's current time to schedule. Call get_current_time first, then create the event with future startIso and endIso.",
                            "currentTime": current,
                        }),
                    })
                    continue
            except (ValueError, TypeError):
                pass  # Invalid ISO format; let create_event fail or succeed

            try:
                out = create_event(
                    access_token,
                    title=title,
                    startIso=startIso,
                    endIso=endIso,
                    timezone=tz,
                )
                results.append({
                    "toolCallId": tool_call_id,
                    "name": name,
                    "result": json.dumps({"status": "ok", **out}),
                })
            except Exception as e:
                results.append({
                    "toolCallId": tool_call_id,
                    "name": name,
                    "result": json.dumps({"error": True, "message": str(e)}),
                })

        elif name == "check_availability":
            out = {"available": True, "conflicts": []}
            results.append({
                "toolCallId": tool_call_id,
                "name": name,
                "result": json.dumps(out),
            })

        else:
            results.append({
                "toolCallId": tool_call_id,
                "name": name,
                "result": json.dumps({"error": True, "message": f"Unknown tool: {name}"}),
            })

    # Include current time context in response for reference
    response = {
        "results": results,
        "state": {
            "currentDateTime": datetime.now().isoformat(),
            "currentDateTimeReadable": _get_current_datetime_context()
        }
    }
    return JSONResponse(response)