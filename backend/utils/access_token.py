import requests

def refresh_access_token(refresh_token: str, client_id: str, client_secret: str):
    """Exchange refresh token for access token. Raises on error."""
    if not refresh_token or not client_id or not client_secret:
        raise ValueError("refresh_token, client_id, and client_secret are required")

    r = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )

    if not r.ok:
        err_msg = r.text
        try:
            err_body = r.json()
            err_msg = err_body.get("error_description", err_msg)
        except Exception:
            pass
        raise requests.exceptions.HTTPError(
            f"Token refresh failed ({r.status_code}): {err_msg}"
        )

    data = r.json()
    return data["access_token"], data.get("expires_in")