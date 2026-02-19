from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from google_auth_oauthlib.flow import Flow
import os
from utils.token_store import save_tokens, DEFAULT_USER_ID
from dotenv import load_dotenv
load_dotenv()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")

router = APIRouter()

# OAuth 2.0 scopes needed for calendar access
SCOPES = ['https://www.googleapis.com/auth/calendar']

# Client configuration (OAuth 2.0)
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
async def auth_status():
    """Check if Google Calendar is connected (has stored tokens)."""
    from utils.token_store import has_tokens
    return {"connected": has_tokens(DEFAULT_USER_ID)}


@router.get("/google")
async def google_auth():
    """Initiate Google OAuth flow"""
    flow = Flow.from_client_config(
        CLIENT_CONFIG,
        scopes=SCOPES,
        redirect_uri=GOOGLE_REDIRECT_URI
    )
    
    # Generate authorization URL
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'  # Force consent screen to get refresh token
    )
    
    # Redirect user to Google's consent screen
    return RedirectResponse(url=authorization_url)


@router.get("/callback")
async def google_callback(request: Request, code: str = None, error: str = None):
    """Handle Google OAuth callback"""
    if error:
        return HTMLResponse(
            content=f"<h1>Authorization failed</h1><p>Error: {error}</p>",
            status_code=400
        )
    
    if not code:
        raise HTTPException(status_code=400, detail="Authorization code not provided")
    
    try:
        flow = Flow.from_client_config(
            CLIENT_CONFIG,
            scopes=SCOPES,
            redirect_uri=GOOGLE_REDIRECT_URI
        )
        
        # Exchange authorization code for tokens
        flow.fetch_token(code=code)
        credentials = flow.credentials

        if not credentials.refresh_token:
            return HTMLResponse(
                content="""
                <html><body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1>Refresh token not received</h1>
                <p>Please revoke access at <a href="https://myaccount.google.com/permissions">Google Account permissions</a> and try again.</p>
                <p>Make sure to grant full access when prompted.</p>
                </body></html>
                """,
                status_code=400,
            )

        # Store tokens for single-user dev (backend/data/tokens.json)
        save_tokens(
            user_id=DEFAULT_USER_ID,
            access_token=credentials.token,
            refresh_token=credentials.refresh_token,
            expires_in=None,
        )

        return HTMLResponse(
            content="""
            <html>
                <body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h1>✅ Successfully Connected!</h1>
                    <p>Your Google Calendar has been connected.</p>
                    <p>You can now close this window.</p>
                </body>
            </html>
            """
        )
    except Exception as e:
        return HTMLResponse(
            content=f"<h1>Error</h1><p>Failed to authenticate: {str(e)}</p>",
            status_code=500
        )
