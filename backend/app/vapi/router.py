from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import json
import os
import secrets
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from dotenv import load_dotenv

from app.calander.service import create_event, check_availability
from utils.access_token import refresh_access_token
from utils.token_store import get_refresh_token

load_dotenv()
router = APIRouter()

CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

# ── Session registry ──────────────────────────────────────────────────────────
# Frontend calls POST /vapi/session before starting a Vapi call.
# We return a short-lived token that the frontend passes as a variableValue.
# When assistant-request fires we resolve token → userId and store it in the
# call map. This is the primary mechanism because Vapi's Web SDK does not
# reliably forward call-level metadata to the webhook.
_session_registry: dict[str, str] = {}   # token  → userId
_call_user_map:    dict[str, str] = {}   # call_id → userId


def _get_current_time_payload(user_timezone: str = None):
    """Return structured current time, in the user's local timezone if provided."""
    utc_now = datetime.now(timezone.utc)

    if user_timezone:
        try:
            tz    = ZoneInfo(user_timezone)
            now   = utc_now.astimezone(tz)
            tz_label = user_timezone
        except ZoneInfoNotFoundError:
            now      = utc_now
            tz_label = "UTC"
    else:
        now      = utc_now
        tz_label = "UTC"

    return {
        "currentDateTimeIso": now.isoformat(),
        "date":      now.strftime("%Y-%m-%d"),
        "time":      now.strftime("%H:%M"),
        "time12h":   now.strftime("%I:%M %p"),
        "timezone":  tz_label,
        "dayOfWeek": now.strftime("%A"),
        "readable":  f"{now.strftime('%A, %B %d, %Y')} at {now.strftime('%I:%M %p')} {tz_label}",
        "instruction": (
            f"Current local time is already in {tz_label}. "
            "Use 'date' and 'time' fields directly to compute relative times like 'tomorrow at the same time'. "
            "Do NOT convert or adjust — these values are already in the user's timezone. "
            "Build startIso and endIso using currentDateTimeIso as the base."
        ),
    }


def _get_access_token(user_id: str) -> str:
    refresh_token = get_refresh_token(user_id)
    if not refresh_token:
        raise ValueError(
            "No Google Calendar connected for this session. "
            "Please connect your Google Calendar first."
        )
    access_token, _ = refresh_access_token(refresh_token, CLIENT_ID, CLIENT_SECRET)
    return access_token


def _get_call_user_id(message: dict) -> str:
    """Resolve the userId for this call.

    Resolution order:
    1. _call_user_map  — populated by assistant-request (if Vapi sends it)
    2. call.assistantOverrides.variableValues.sessionToken → _session_registry
    3. call.assistantOverrides.variableValues.userId  (direct)

    The Vapi assistant only needs a server URL on the tools, not at the
    assistant level, so assistant-request may never fire. Reading directly
    from the call object in the tool-calls payload is always reliable.
    """
    call    = message.get("call") or {}
    call_id = call.get("id")

    # 1. Fast path — already resolved by assistant-request
    if call_id and call_id in _call_user_map:
        return _call_user_map[call_id]

    var_values = (call.get("assistantOverrides") or {}).get("variableValues") or {}

    # 2. Session token (pre-registered via POST /vapi/session)
    token = var_values.get("sessionToken")
    if token and token in _session_registry:
        user_id = _session_registry.pop(token)
        if call_id:
            _call_user_map[call_id] = user_id   # cache for subsequent tool calls
        return user_id

    # 3. userId passed directly in variableValues
    user_id = var_values.get("userId")
    if user_id:
        if call_id:
            _call_user_map[call_id] = user_id
        return user_id

    raise ValueError(
        "Session not found. Please reconnect your Google Calendar and try again."
    )


@router.post("/session")
async def create_session(request: Request):
    """Frontend calls this right before vapi.start(). Returns a one-time token
    that the frontend embeds in variableValues so the webhook can resolve the
    userId without relying on Vapi forwarding call metadata."""
    body    = await request.json()
    user_id = body.get("userId")
    if not user_id:
        return JSONResponse({"error": "userId required"}, status_code=400)
    token = secrets.token_hex(16)
    _session_registry[token] = user_id
    return JSONResponse({"token": token})


@router.get("/current-time")
async def get_current_time():
    now = datetime.now(timezone.utc)
    t   = _get_current_time_payload()
    return JSONResponse({
        "currentDateTime":         now.isoformat(),
        "currentDateTimeReadable": t["readable"],
        "timestamp":               now.timestamp(),
    })


@router.post("/webhook")
async def vapi_webhook(request: Request):
    payload      = await request.json()
    message      = payload.get("message", {})
    message_type = message.get("type")

    # ── assistant-request ──────────────────────────────────────────────────────
    # Fires once at the very start of each call. Resolve the userId and store
    # call_id → userId so all subsequent tool calls can look it up.
    if message_type == "assistant-request":
        call      = message.get("call") or {}
        call_id   = call.get("id")

        # Resolution order (most reliable first):
        # 1. Session token pre-registered via POST /vapi/session
        # 2. userId passed directly in assistantOverrides.variableValues
        # 3. userId in call.metadata (Web SDK doesn't set this, but kept as fallback)
        user_id = None

        var_values = (call.get("assistantOverrides") or {}).get("variableValues") or {}

        session_token = var_values.get("sessionToken")
        if session_token:
            user_id = _session_registry.pop(session_token, None)

        if not user_id:
            user_id = var_values.get("userId")

        if not user_id:
            user_id = (call.get("metadata") or {}).get("userId")

        if call_id and user_id:
            _call_user_map[call_id] = user_id

        t = _get_current_time_payload()
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

    # ── end-of-call-report ─────────────────────────────────────────────────────
    # Clean up the call → user mapping when the call finishes.
    if message_type == "end-of-call-report":
        call_id = (message.get("call") or {}).get("id")
        if call_id:
            _call_user_map.pop(call_id, None)
        return JSONResponse({"ok": True})

    # ── tool-calls ─────────────────────────────────────────────────────────────
    if message_type != "tool-calls":
        return JSONResponse({"ok": True})

    results    = []
    tool_calls = message.get("toolCallList", []) or []

    # Resolve userId for this call once, upfront.
    try:
        user_id = _get_call_user_id(message)
    except ValueError as e:
        # Return an error result for every pending tool call
        for tc in tool_calls:
            results.append({
                "toolCallId": tc.get("id"),
                "name":       (tc.get("function") or {}).get("name", "unknown"),
                "result":     json.dumps({"error": True, "message": str(e)}),
            })
        return JSONResponse({"results": results})

    # Scan for user timezone upfront so every result in this batch can use it.
    call_timezone = None
    for tc in tool_calls:
        raw = (tc.get("function") or {}).get("arguments", {})
        if isinstance(raw, str):
            try:
                raw = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                raw = {}
        if isinstance(raw, dict) and raw.get("timezone"):
            call_timezone = raw["timezone"]
            break

    server_time = _get_current_time_payload(call_timezone)

    for tc in tool_calls:
        tool_call_id = tc.get("id")
        function     = tc.get("function") or {}
        name         = function.get("name", "unknown_tool")
        args         = function.get("arguments", {})

        if isinstance(args, str):
            try:
                params = json.loads(args) if args else {}
            except json.JSONDecodeError as e:
                results.append({
                    "toolCallId": tool_call_id,
                    "name":       name,
                    "result":     json.dumps({
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

        # ── get_current_time ──────────────────────────────────────────────────
        if name == "get_current_time":
            user_tz = params.get("timezone") or call_timezone
            results.append({
                "toolCallId": tool_call_id,
                "name":       name,
                "result":     json.dumps(_get_current_time_payload(user_tz)),
            })

        # ── create_calendar_event ─────────────────────────────────────────────
        elif name == "create_calendar_event":
            try:
                access_token = _get_access_token(user_id)
            except ValueError as e:
                results.append({
                    "toolCallId": tool_call_id,
                    "name":       name,
                    "result":     json.dumps({
                        "error": True,
                        "message": str(e),
                        "serverCurrentTime": server_time,
                    }),
                })
                continue

            title    = params.get("title")
            startIso = params.get("startIso")
            endIso   = params.get("endIso")
            tz       = params.get("timezone", "UTC")

            if not all([title, startIso, endIso]):
                missing = [f for f in ["title", "startIso", "endIso"] if not params.get(f)]
                results.append({
                    "toolCallId": tool_call_id,
                    "name":       name,
                    "result":     json.dumps({
                        "error": True,
                        "message": (
                            f"Cannot create event. Missing fields: {missing}. "
                            "Use serverCurrentTime to compute startIso and endIso, then retry."
                        ),
                        "serverCurrentTime": _get_current_time_payload(tz or call_timezone),
                    }),
                })
                continue

            # Reject events in the past
            try:
                start_dt = datetime.fromisoformat(startIso.replace("Z", "+00:00"))
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
                if start_dt < datetime.now(timezone.utc):
                    results.append({
                        "toolCallId": tool_call_id,
                        "name":       name,
                        "result":     json.dumps({
                            "error": True,
                            "message": (
                                "Event start time is in the past. "
                                "Use serverCurrentTime to recompute startIso and endIso, then retry."
                            ),
                            "serverCurrentTime": _get_current_time_payload(tz or call_timezone),
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
                    "name":       name,
                    "result":     json.dumps({"status": "ok", **out}),
                })
            except Exception as e:
                results.append({
                    "toolCallId": tool_call_id,
                    "name":       name,
                    "result":     json.dumps({
                        "error": True,
                        "message": str(e),
                        "serverCurrentTime": server_time,
                    }),
                })

        # ── check_availability ────────────────────────────────────────────────
        elif name == "check_availability":
            startIso_check = params.get("startIso")
            endIso_check   = params.get("endIso")
            user_tz_check  = params.get("timezone", call_timezone or "UTC")

            if not startIso_check or not endIso_check:
                results.append({
                    "toolCallId": tool_call_id,
                    "name":       name,
                    "result":     json.dumps({
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

            out["serverCurrentTime"] = server_time
            results.append({
                "toolCallId": tool_call_id,
                "name":       name,
                "result":     json.dumps(out),
            })

        else:
            results.append({
                "toolCallId": tool_call_id,
                "name":       name,
                "result":     json.dumps({
                    "error": True,
                    "message": f"Unknown tool: {name}",
                    "serverCurrentTime": server_time,
                }),
            })

    tz_label = server_time.get("timezone", "UTC")
    return JSONResponse({
        "results": results,
        "messages": [
            {
                "role": "system",
                "content": (
                    f"[SERVER TIME] Right now it is {server_time['readable']} ({tz_label}). "
                    f"Today is {server_time['dayOfWeek']}, {server_time['date']}. "
                    "Use ONLY this value for any date/time calculations."
                ),
            }
        ],
    })
