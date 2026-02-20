"""
Token store — multi-user.

Storage backend is selected by environment variable:
  MONGO_URI set  →  MongoDB Atlas (production)
  MONGO_URI unset →  local JSON file (development)

Both backends expose the same three functions:
  save_tokens(user_id, access_token, refresh_token, expires_in)
  get_refresh_token(user_id) -> str | None
  has_tokens(user_id) -> bool
"""
import json
import os
from pathlib import Path

MONGO_URI = os.getenv("MONGO_URI")

# ── MongoDB backend ───────────────────────────────────────────────────────────
if MONGO_URI:
    from pymongo import MongoClient

    _client     = MongoClient(MONGO_URI)
    _db         = _client.get_default_database()
    _collection = _db["tokens"]

    def save_tokens(user_id: str, access_token: str, refresh_token: str, expires_in: int = None):
        _collection.update_one(
            {"_id": user_id},
            {"$set": {
                "access_token":  access_token,
                "refresh_token": refresh_token,
                "expires_in":    expires_in,
            }},
            upsert=True,
        )

    def get_refresh_token(user_id: str) -> str | None:
        doc = _collection.find_one({"_id": user_id}, {"refresh_token": 1})
        return doc.get("refresh_token") if doc else None

    def has_tokens(user_id: str) -> bool:
        return get_refresh_token(user_id) is not None

# ── File-based fallback (local dev) ──────────────────────────────────────────
else:
    _default_data_dir = Path(__file__).resolve().parent.parent / "data"
    DATA_DIR    = Path(os.getenv("TOKEN_DATA_DIR", str(_default_data_dir)))
    TOKENS_FILE = DATA_DIR / "tokens.json"

    def _ensure_data_dir():
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    def _load() -> dict:
        _ensure_data_dir()
        if not TOKENS_FILE.exists():
            return {}
        try:
            with open(TOKENS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    def _dump(data: dict):
        _ensure_data_dir()
        with open(TOKENS_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def save_tokens(user_id: str, access_token: str, refresh_token: str, expires_in: int = None):
        data = _load()
        data[user_id] = {
            "access_token":  access_token,
            "refresh_token": refresh_token,
            "expires_in":    expires_in,
        }
        _dump(data)

    def get_refresh_token(user_id: str) -> str | None:
        return _load().get(user_id, {}).get("refresh_token")

    def has_tokens(user_id: str) -> bool:
        return get_refresh_token(user_id) is not None
