from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import json
import os
from datetime import datetime
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
    now = datetime.now()
    # Format: "February 19, 2026, 3:45 PM EST" (readable format)
    formatted_date = now.strftime("%B %d, %Y")
    formatted_time = now.strftime("%I:%M %p")
    day_of_week = now.strftime("%A")
    iso_format = now.isoformat()
    
    return (
        f"Current date and time: {day_of_week}, {formatted_date} at {formatted_time} "
        f"(ISO format: {iso_format}). "
        f"Use this information when scheduling meetings - if the user says 'tomorrow', "
        f"'next week', or 'at 5 PM', calculate based on this current time."
    )


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
    return JSONResponse({
        "currentDateTime": datetime.now().isoformat(),
        "currentDateTimeReadable": _get_current_datetime_context(),
        "timestamp": datetime.now().timestamp()
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
                    "content": current_time_context
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
        name = function.get("name")

        args = function.get("arguments", {})

        if isinstance(args, str):
            params = json.loads(args) if args else {}
        elif isinstance(args, dict):
            params = args
        else:
            params = {}

        user_id = params.get("userId", DEFAULT_USER_ID)

        if name == "create_calendar_event":
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
            timezone = params.get("timezone", "UTC")

            if not all([title, startIso, endIso]):
                results.append({
                    "toolCallId": tool_call_id,
                    "name": name,
                    "result": json.dumps({
                        "error": True,
                        "message": f"Missing required fields. Received: {list(params.keys())}. Need: title, startIso, endIso",
                    }),
                })
                continue

            try:
                out = create_event(
                    access_token,
                    title=title,
                    startIso=startIso,
                    endIso=endIso,
                    timezone=timezone,
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