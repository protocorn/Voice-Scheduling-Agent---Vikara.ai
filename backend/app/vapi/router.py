from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import json

router = APIRouter()

@router.post("/webhook")
async def vapi_webhook(request: Request):
    payload = await request.json()
    print("VAPI PAYLOAD:", payload) # For debugging
    message = payload.get("message", {})

    if message.get("type") != "tool-calls":
        return JSONResponse({"ok": True})

    results = []
    tool_calls = message.get("toolCallList", []) or []

    for tc in tool_calls:
        tool_call_id = tc.get("id")
        name = tc.get("name")
        params = tc.get("parameters", {}) or {}

        user_id = params.get("userId", "default_user")

        if name == "create_calendar_event":
            # Will update this later
            out = calendar.create_event(user_id, params)
            out = {"status": "ok", "eventId": "demo123", "htmlLink": "https://calendar.google.com/"}

            results.append({
                "toolCallId": tool_call_id,
                "name": name,
                "result": json.dumps(out)
            })

        elif name == "check_availability":
            # Will update this later
            out = {"available": True, "conflicts": []}
            results.append({
                "toolCallId": tool_call_id,
                "name": name,
                "result": json.dumps(out)
            })

        else:
            results.append({
                "toolCallId": tool_call_id,
                "name": name,
                "result": json.dumps({"error": True, "message": f"Unknown tool: {name}"})
            })

    return JSONResponse({"results": results})