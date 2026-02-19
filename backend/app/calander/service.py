import requests

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
