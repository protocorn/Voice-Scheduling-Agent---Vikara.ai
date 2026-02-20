import requests
from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo


def check_availability(access_token: str, startIso: str, endIso: str, user_timezone: str = "UTC", calendar_id: str = "primary") -> dict:
    """Query Google Calendar Freebusy API and return any conflicting events."""
    url = "https://www.googleapis.com/calendar/v3/freeBusy"
    body = {
        "timeMin": startIso,
        "timeMax": endIso,
        "items": [{"id": calendar_id}],
    }
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json=body,
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()

    busy_slots = data.get("calendars", {}).get(calendar_id, {}).get("busy", [])

    if not busy_slots:
        return {"available": True, "conflicts": []}

    try:
        tz = ZoneInfo(user_timezone)
    except Exception:
        tz = dt_timezone.utc

    conflicts = []
    for slot in busy_slots:
        start_utc = datetime.fromisoformat(slot["start"].replace("Z", "+00:00"))
        end_utc = datetime.fromisoformat(slot["end"].replace("Z", "+00:00"))
        start_local = start_utc.astimezone(tz)
        end_local = end_utc.astimezone(tz)
        conflicts.append({
            "start": start_local.strftime("%I:%M %p"),
            "end": end_local.strftime("%I:%M %p"),
            "date": start_local.strftime("%A, %B %d, %Y"),
            "startIso": start_local.isoformat(),
            "endIso": end_local.isoformat(),
        })

    return {
        "available": False,
        "conflicts": conflicts,
        "message": (
            f"There is already a meeting scheduled during that time: "
            + ", ".join(f"{c['date']} from {c['start']} to {c['end']}" for c in conflicts)
            + f" ({user_timezone}). Ask the user if they want to pick a different time."
        ),
    }


def create_event(access_token: str, title: str, startIso: str, endIso: str, timezone: str, calendar_id: str = "primary"):
    url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
    body = {
        "summary": title,
        "start": {"dateTime": startIso, "timeZone": timezone},
        "end": {"dateTime": endIso, "timeZone": timezone},
    }

    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json=body,
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    return {
        "eventId": data.get("id"),
        "htmlLink": data.get("htmlLink"),
        "status": data.get("status"),
    }
