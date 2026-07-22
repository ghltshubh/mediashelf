"""Accounts API (M3): OAuth connect flows, connection status, library sync.

Both providers share the single /oauth2callback endpoint (plan); the state
token — generated server-side, single-use, short-lived — routes the callback
to the right connector and back to the page that started it.
"""

import asyncio
import logging
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import settings_store
from app.connectors.apple_music import AppleMusicConnector
from app.connectors.base import AuthExpired, NotConnected
from app.connectors.spotify import SpotifyConnector
from app.connectors.youtube import YouTubeConnector
from app.db import get_session, session_factory
from app.services import library as library_service

logger = logging.getLogger(__name__)
router = APIRouter()

spotify = SpotifyConnector()
youtube = YouTubeConnector()
apple = AppleMusicConnector()
OAUTH_CONNECTORS: dict[str, SpotifyConnector | YouTubeConnector] = {
    "spotify": spotify, "youtube": youtube,
}

DEFAULT_REDIRECT = "http://127.0.0.1:8000/oauth2callback"
_STATE_TTL = 600
_states: dict[str, tuple[str, str, float]] = {}  # state -> (provider, origin, created)


def redirect_uri(db: Session) -> str:
    return settings_store.get_setting(db, "oauth_redirect_uri") or DEFAULT_REDIRECT


@router.get("/api/connect/{provider}/start")
def connect_start(provider: str, origin: str = "settings",
                  db: Session = Depends(get_session)) -> dict:
    connector = OAUTH_CONNECTORS.get(provider)
    if connector is None:
        raise HTTPException(404, "Unknown provider")
    if not connector.configured(db):
        raise HTTPException(400, f"Add your {connector.name} API keys first")
    state = secrets.token_urlsafe(24)
    now = time.monotonic()
    for k, (_, _, created) in list(_states.items()):
        if now - created > _STATE_TTL:
            del _states[k]
    _states[state] = (provider, origin if origin in ("settings", "onboarding") else "settings", now)
    try:
        url = connector.auth_url(db, state, redirect_uri(db))
    except NotConnected as exc:
        raise HTTPException(400, f"Add your {connector.name} API keys first") from exc
    return {"url": url}


@router.get("/oauth2callback", include_in_schema=False)
def oauth2callback(state: str = "", code: str = "", error: str = "",
                   db: Session = Depends(get_session)) -> RedirectResponse:
    entry = _states.pop(state, None)
    if entry is None:
        return RedirectResponse("/settings?connect_error=Sign-in+session+expired+—+try+again")
    provider, origin, _ = entry
    back = "/onboarding" if origin == "onboarding" else "/settings"
    if error:
        return RedirectResponse(f"{back}?connect_error={error}")
    connector = OAUTH_CONNECTORS[provider]
    try:
        connector.handle_callback(db, code, redirect_uri(db))
    except Exception as exc:
        logger.warning("%s oauth callback failed: %s", provider, exc)
        return RedirectResponse(f"{back}?connect_error=Connecting+{provider}+failed")
    # First sync in the background so the library fills in right away.
    schedule_library_sync(provider)
    return RedirectResponse(f"{back}?connected={provider}")


@router.get("/api/connections")
def connections(db: Session = Depends(get_session)) -> list[dict]:
    out = []
    for connector in (spotify, youtube, apple):
        st = connector.status(db)
        st["sync"] = dict(library_service.sync_state.get(connector.key, {}))
        st["synced_at"] = settings_store.get_setting(db, f"library_synced_at_{connector.key}")
        out.append(st)
    return out


@router.delete("/api/connections/{provider}", status_code=204)
def disconnect(provider: str, db: Session = Depends(get_session)) -> None:
    if provider == "apple_music":
        apple.set_token(db, None)
        return
    connector = OAUTH_CONNECTORS.get(provider)
    if connector is None:
        raise HTTPException(404, "Unknown provider")
    connector.disconnect(db)


@router.post("/api/connections/{provider}/sync")
def trigger_library_sync(provider: str, db: Session = Depends(get_session)) -> dict:
    connector = OAUTH_CONNECTORS.get(provider)
    if connector is None:
        raise HTTPException(404, "Unknown provider")
    if not connector.connected(db):
        raise HTTPException(400, f"Connect {connector.name} first")
    schedule_library_sync(provider)
    return {"status": "started"}


@router.get("/api/library")
def get_library(db: Session = Depends(get_session)) -> dict:
    from sqlalchemy import select

    from app.models import Service, UserSub
    from app.services import playback as playback_service

    subscribed = set(db.scalars(
        select(Service.key).join(UserSub, UserSub.service_id == Service.id)
        .where(UserSub.subscribed.is_(True))))
    playback_state = playback_service.user_playback_state(db)
    return {
        "groups": library_service.rows_for_groups(db, subscribed, playback_state),
        "sync": {k: dict(v) for k, v in library_service.sync_state.items()},
        "connections": {k: c.connected(db) for k, c in OAUTH_CONNECTORS.items()},
    }


@router.get("/api/playback/spotify/token")
def spotify_playback_token(db: Session = Depends(get_session)) -> dict:
    """Fresh access token for the Web Playback SDK in the browser."""
    try:
        token = spotify.playback_token(db, redirect_uri(db))
    except NotConnected as exc:
        raise HTTPException(400, "Connect Spotify first") from exc
    except AuthExpired as exc:
        raise HTTPException(401, "Spotify authorization expired — reconnect in Settings") from exc
    return {"access_token": token}


class AppleTokenBody(BaseModel):
    token: str


@router.put("/api/connections/apple_music/token")
def set_apple_token(body: AppleTokenBody, db: Session = Depends(get_session)) -> dict:
    err = apple.set_token(db, body.token.strip())
    if err:
        raise HTTPException(400, err)
    return apple.status(db)


# ---------- background sync ----------

def _sync_in_thread(provider: str) -> None:
    with session_factory()() as db:
        library_service.sync_provider(db, provider)


def schedule_library_sync(provider: str) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        _sync_in_thread(provider)  # no loop (tests/CLI): run inline
        return
    loop.create_task(asyncio.to_thread(_sync_in_thread, provider))


def scheduled_sync_all() -> None:
    """APScheduler job: refresh all connected libraries."""
    with session_factory()() as db:
        library_service.sync_all_connected(db)
