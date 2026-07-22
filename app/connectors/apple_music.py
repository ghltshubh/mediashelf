"""Apple Music connector: MusicKit JS does auth + playback client-side; the
backend stores the user-supplied developer token and tracks its expiry
(MusicKit developer tokens live ≤6 months — warn 14 days ahead, plan failure
modes). Library read/write lands with the M5 migration work."""

import base64
import json
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app import settings_store

logger = logging.getLogger(__name__)


def _decode_jwt_exp(token: str) -> datetime | None:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        if "exp" in data:
            return datetime.fromtimestamp(data["exp"], tz=UTC)
    except Exception:
        return None
    return None


class AppleMusicConnector:
    key = "apple_music"
    name = "Apple Music"

    def capabilities(self) -> dict:
        return {"catalog": True, "user_library": True, "write_likes": True,
                "write_follows": False, "playback": "sdk"}

    def configured(self, db: Session) -> bool:
        return settings_store.get_setting(db, "apple_developer_token") is not None

    def connected(self, db: Session) -> bool:
        # User consent happens in the browser via MusicKit JS; the backend only
        # knows whether a developer token is present.
        return self.configured(db)

    def set_token(self, db: Session, token: str | None) -> str | None:
        """Store/clear the developer token. Returns a validation error, or None."""
        if not token:
            settings_store.set_setting(db, "apple_developer_token", None)
            return None
        exp = _decode_jwt_exp(token)
        if exp is None:
            return "That doesn't look like a MusicKit developer token (JWT with an expiry)"
        if exp < datetime.now(UTC):
            return f"That token expired on {exp.date().isoformat()} — generate a fresh one"
        settings_store.set_setting(db, "apple_developer_token", token)
        return None

    def status(self, db: Session) -> dict:
        token = settings_store.get_setting(db, "apple_developer_token")
        exp = _decode_jwt_exp(token) if token else None
        expiring = bool(exp and exp - datetime.now(UTC) < timedelta(days=14))
        return {
            "provider": "apple_music",
            "name": "Apple Music",
            "configured": bool(token),
            "connected": bool(token),
            "state": "ok" if token else "none",
            "profile": None,
            "premium": bool(token),
            "token_expires": exp.isoformat() if exp else None,
            "token_expiring_soon": expiring,
            "adds": "play full tracks in-app (subscribers) via MusicKit",
            "requires": "your own Apple developer token (paid Apple Developer account)",
        }
