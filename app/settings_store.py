"""Typed access to the Setting table, with env-var bootstrap for secrets."""

import os

from sqlalchemy.orm import Session

from app import secrets as secretbox
from app.models import Setting

SECRET_KEYS = {
    "tmdb_api_key",
    "omdb_api_key",
    "spotify_client_secret",
    "google_client_secret",
    "apple_developer_token",
    "spotify_oauth",   # OAuth token bundles are secrets too — encrypted, never printed
    "youtube_oauth",
}

DEFAULTS = {
    "country": "US",
    "onboarded": "false",
}


def get_setting(db: Session, key: str) -> str | None:
    row = db.get(Setting, key)
    if row is not None and row.value is not None:
        return secretbox.decrypt(row.value) if row.encrypted else row.value
    # Env-var bootstrap: MEDIASHELF_<KEY> or the bare key for well-known ones.
    env = os.environ.get(f"MEDIASHELF_{key.upper()}") or (
        os.environ.get("TMDB_API_KEY") if key == "tmdb_api_key" else None
    )
    if env:
        return env
    return DEFAULTS.get(key)


def set_setting(db: Session, key: str, value: str | None) -> None:
    encrypted = key in SECRET_KEYS
    stored = secretbox.encrypt(value) if (encrypted and value) else value
    row = db.get(Setting, key)
    if row is None:
        row = Setting(key=key, value=stored, encrypted=encrypted and bool(value))
        db.add(row)
    else:
        row.value = stored
        row.encrypted = encrypted and bool(value)
    db.commit()
