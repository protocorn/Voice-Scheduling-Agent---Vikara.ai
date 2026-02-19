"""
Simple token store for development (single user).
Stores Google OAuth tokens in a JSON file.
"""
import json
import os
from pathlib import Path

# Store in backend/data/tokens.json
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TOKENS_FILE = DATA_DIR / "tokens.json"

DEFAULT_USER_ID = "default_user"


def _ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_tokens() -> dict:
    """Load tokens from file."""
    _ensure_data_dir()
    if not TOKENS_FILE.exists():
        return {}
    try:
        with open(TOKENS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_tokens(data: dict):
    """Save tokens to file."""
    _ensure_data_dir()
    with open(TOKENS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def save_tokens(
    user_id: str,
    access_token: str,
    refresh_token: str,
    expires_in: int = None,
):
    """Save OAuth tokens for a user."""
    data = _load_tokens()
    data[user_id] = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": expires_in,
    }
    _save_tokens(data)


def get_refresh_token(user_id: str = DEFAULT_USER_ID) -> str | None:
    """Get refresh token for user. Returns None if not found."""
    data = _load_tokens()
    user_data = data.get(user_id)
    if not user_data:
        return None
    return user_data.get("refresh_token")


def has_tokens(user_id: str = DEFAULT_USER_ID) -> bool:
    """Check if we have stored tokens for the user."""
    return get_refresh_token(user_id) is not None
