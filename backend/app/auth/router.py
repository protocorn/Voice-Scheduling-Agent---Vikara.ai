from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from google_auth_oauthlib.flow import Flow
import os
from utils.token_store import save_tokens, has_tokens
from dotenv import load_dotenv
load_dotenv()

GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI  = os.getenv("GOOGLE_REDIRECT_URI")

router = APIRouter()

SCOPES = ['https://www.googleapis.com/auth/calendar']

CLIENT_CONFIG = {
    "web": {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [GOOGLE_REDIRECT_URI]
    }
}


@router.get("/status")
async def auth_status(userId: str):
    """Check if this user has connected their Google Calendar."""
    return {"connected": has_tokens(userId)}


@router.get("/google")
async def google_auth(userId: str):
    """Start Google OAuth. The userId is carried through the round-trip via
    the OAuth `state` parameter so we know whose tokens to save on callback."""
    flow = Flow.from_client_config(
        CLIENT_CONFIG,
        scopes=SCOPES,
        redirect_uri=GOOGLE_REDIRECT_URI
    )

    authorization_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent',
        state=userId,
    )

    return RedirectResponse(url=authorization_url)


@router.get("/callback")
async def google_callback(
    request: Request,
    code: str = None,
    error: str = None,
    state: str = None,
):
    """Handle Google OAuth callback. `state` is the userId set in /google."""
    if error:
        return HTMLResponse(
            content=f"<h1>Authorization failed</h1><p>Error: {error}</p>",
            status_code=400
        )

    if not code:
        raise HTTPException(status_code=400, detail="Authorization code not provided")

    if not state:
        raise HTTPException(status_code=400, detail="Missing userId in OAuth state")

    user_id = state

    try:
        flow = Flow.from_client_config(
            CLIENT_CONFIG,
            scopes=SCOPES,
            redirect_uri=GOOGLE_REDIRECT_URI
        )

        flow.fetch_token(code=code)
        credentials = flow.credentials

        if not credentials.refresh_token:
            return HTMLResponse(
                content="""
                <html><body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1>Refresh token not received</h1>
                <p>Please revoke access at
                <a href="https://myaccount.google.com/permissions">Google Account permissions</a>
                and try again.</p>
                </body></html>
                """,
                status_code=400,
            )

        save_tokens(
            user_id=user_id,
            access_token=credentials.token,
            refresh_token=credentials.refresh_token,
            expires_in=None,
        )

        return RedirectResponse(url="/voice.html?connected=1")

    except Exception as e:
        return HTMLResponse(
            content=f"<h1>Error</h1><p>Failed to authenticate: {str(e)}</p>",
            status_code=500
        )
