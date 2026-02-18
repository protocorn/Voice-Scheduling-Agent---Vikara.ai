from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
import os
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
        
        # Store credentials (in production, store securely in database)
        # For now, we'll return success message
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
