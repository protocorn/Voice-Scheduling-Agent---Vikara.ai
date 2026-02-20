from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import json
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from dotenv import load_dotenv

from app.calander.service import create_event, check_availability
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

    # Handle assistant-request: inject live server time at the start of every call
    if message_type == "assistant-request":
        t = _get_current_time_payload()  # UTC until we know user's timezone
        return JSONResponse({
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"[SERVER TIME] The current UTC time is {t['readable']}. "
                        f"Today is {t['dayOfWeek']}, {t['date']}. "
                        "This will be updated to the user's local timezone once you collect their location. "
                        "Never use your own internal sense of time — always rely on [SERVER TIME] values."
                    ),
                }
            ]
        })

    # Handle tool-calls
    if message_type != "tool-calls":
        return JSONResponse({"ok": True})

    results = []
    tool_calls = message.get("toolCallList", []) or []

    # Scan all tool calls upfront to find the user's timezone if any tool carries it.
    # This lets us inject accurate local time into every result in this batch.
    call_timezone = None
    for tc in tool_calls:
        raw_args = tc.get("function", {}).get("arguments", {})
        if isinstance(raw_args, str):
            try:
                raw_args = json.loads(raw_args) if raw_args else {}
            except json.JSONDecodeError:
                raw_args = {}
        if isinstance(raw_args, dict) and raw_args.get("timezone"):
            call_timezone = raw_args["timezone"]
            break

    # Current time stamped once for the whole request, in the user's timezone when known.
    server_time = _get_current_time_payload(call_timezone)

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
                        "serverCurrentTime": server_time,
                    }),
                })
                continue
        elif isinstance(args, dict):
            params = args
        else:
            params = {}

        user_id = params.get("userId", DEFAULT_USER_ID)

        if name == "get_current_time":
            user_tz = params.get("timezone") or call_timezone
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
                    "result": json.dumps({
                        "error": True,
                        "message": str(e),
                        "serverCurrentTime": server_time,
                    }),
                })
                continue

            title = params.get("title")
            startIso = params.get("startIso")
            endIso = params.get("endIso")
            tz = params.get("timezone", "UTC")

            if not all([title, startIso, endIso]):
                missing = [f for f in ["title", "startIso", "endIso"] if not params.get(f)]
                current = _get_current_time_payload(tz or call_timezone)
                results.append({
                    "toolCallId": tool_call_id,
                    "name": name,
                    "result": json.dumps({
                        "error": True,
                        "message": (
                            f"Cannot create event. Missing fields: {missing}. "
                            "Use serverCurrentTime below to compute the correct startIso and endIso, "
                            "then retry create_calendar_event with all fields filled in."
                        ),
                        "serverCurrentTime": current,
                    }),
                })
                continue

            # Reject events in the past
            try:
                start_dt = datetime.fromisoformat(startIso.replace("Z", "+00:00"))
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
                now_utc = datetime.now(timezone.utc)
                if start_dt < now_utc:
                    current = _get_current_time_payload(tz or call_timezone)
                    results.append({
                        "toolCallId": tool_call_id,
                        "name": name,
                        "result": json.dumps({
                            "error": True,
                            "message": (
                                "Event start time is in the past. "
                                "Use serverCurrentTime below — it shows the real current time in the user's timezone. "
                                "Recompute startIso and endIso from it, then retry."
                            ),
                            "serverCurrentTime": current,
                        }),
                    })
                    continue
            except (ValueError, TypeError):
                pass

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
                    "result": json.dumps({
                        "error": True,
                        "message": str(e),
                        "serverCurrentTime": server_time,
                    }),
                })

        elif name == "check_availability":
            startIso_check = params.get("startIso")
            endIso_check = params.get("endIso")
            user_tz_check = params.get("timezone", call_timezone or "UTC")

            if not startIso_check or not endIso_check:
                results.append({
                    "toolCallId": tool_call_id,
                    "name": name,
                    "result": json.dumps({
                        "error": True,
                        "message": "Missing startIso and endIso. Compute them from serverCurrentTime first.",
                        "serverCurrentTime": server_time,
                    }),
                })
                continue

            try:
                access_token = _get_access_token(user_id)
                out = check_availability(access_token, startIso_check, endIso_check, user_tz_check)
            except Exception as e:
                out = {"error": True, "message": str(e)}

            # Always attach server time so the AI has a verified reference alongside availability
            out["serverCurrentTime"] = server_time
            results.append({
                "toolCallId": tool_call_id,
                "name": name,
                "result": json.dumps(out),
            })

        else:
            results.append({
                "toolCallId": tool_call_id,
                "name": name,
                "result": json.dumps({
                    "error": True,
                    "message": f"Unknown tool: {name}",
                    "serverCurrentTime": server_time,
                }),
            })

    # Inject current time as a system message so the AI sees it in context
    # regardless of which tool it called or whether it called get_current_time at all.
    tz_label = server_time.get("timezone", "UTC")
    time_injection = (
        f"[SERVER TIME] Right now it is {server_time['readable']} ({tz_label}). "
        f"Today is {server_time['dayOfWeek']}, {server_time['date']}. "
        "Use ONLY this value for any date/time calculations. Do not use your own internal sense of time."
    )

    response = {
        "results": results,
        "messages": [
            {
                "role": "system",
                "content": time_injection,
            }
        ],
    }
    return JSONResponse(response)