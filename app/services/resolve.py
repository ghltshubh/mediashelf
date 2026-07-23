"""Cross-service playback resolution.

Given a track's metadata (from, say, a YouTube like that can't be embedded),
find the best-matching song across the user's *playable* services (Spotify
Premium, Apple Music) and return a concrete play option for it. This lets a
song play via a sanctioned player on whichever service actually has it — no
YouTube stream extraction, all within each service's own SDK/API.
"""

import logging

import httpx
from sqlalchemy.orm import Session

from app import settings_store
from app.providers import spotify as spotify_api
from app.services import matching
from app.services import playback as playback_service

logger = logging.getLogger(__name__)

APPLE_API = "https://api.music.apple.com"
MIN_CONFIDENCE = 0.6  # below the auto-migrate bar (0.85) but safe for "play this"


async def _apple_candidates(token: str, query: str, storefront: str) -> list[matching.TrackRef]:
    """Apple Music catalog search — needs only the developer token (no user token)."""
    async with httpx.AsyncClient(base_url=APPLE_API, timeout=10) as client:
        resp = await client.get(
            f"/v1/catalog/{storefront}/search",
            params={"term": query, "types": "songs", "limit": 5},
            headers={"Authorization": f"Bearer {token}"},
        )
    if resp.status_code != 200:
        return []
    songs = ((resp.json().get("results") or {}).get("songs") or {}).get("data", [])
    out = []
    for s in songs:
        a = s.get("attributes") or {}
        out.append(matching.TrackRef(
            title=a.get("name", ""),
            artists=[a["artistName"]] if a.get("artistName") else [],
            duration_ms=a.get("durationInMillis"),
            external_id=s.get("id"),
        ))
    return out


async def resolve_playback(db: Session, title: str, artists: list[str],
                           duration_ms: int | None = None) -> dict | None:
    """Best in-app-playable option for a track across connected services, or None.
    Scores each service's top hits against the source metadata and returns the
    single highest-confidence match above the threshold."""
    title = (title or "").strip()
    if not title:
        return None
    source = matching.TrackRef(title=title, artists=artists or [], duration_ms=duration_ms)
    query = f"{title} {' '.join(artists or [])}".strip()
    country = settings_store.get_setting(db, "country") or "US"
    state = playback_service.user_playback_state(db)

    best_conf = 0.0
    best_opt: dict | None = None

    # Spotify — in-app playback requires Premium.
    if state["spotify_connected"] and state["spotify_premium"]:
        cid = settings_store.get_setting(db, "spotify_client_id")
        secret = settings_store.get_setting(db, "spotify_client_secret")
        if cid and secret:
            try:
                res = await spotify_api.search_catalog(cid, secret, query, country)
                cands = [matching.TrackRef(
                    title=t["title"], artists=t.get("artists") or [],
                    duration_ms=t.get("duration_ms"), isrc=t.get("isrc"),
                    external_id=t.get("spotify_uri"),
                ) for t in res.get("tracks", []) if t.get("spotify_uri")]
                m = matching.best_match(source, cands)
                if m.candidate and m.confidence >= MIN_CONFIDENCE and m.confidence > best_conf:
                    best_conf, best_opt = m.confidence, {
                        "engine": "spotify_sdk", "service_key": "spotify", "label": "Spotify",
                        "kind": "full", "payload": {"spotify_uri": m.candidate.external_id}}
            except Exception as exc:
                logger.debug("spotify resolve failed: %s", exc)

    # Apple Music — catalog search needs only the developer token.
    token = settings_store.get_setting(db, "apple_developer_token")
    if token:
        try:
            cands = await _apple_candidates(token, query, (country or "us").lower())
            m = matching.best_match(source, cands)
            if m.candidate and m.confidence >= MIN_CONFIDENCE and m.confidence > best_conf:
                best_conf, best_opt = m.confidence, {
                    "engine": "musickit", "service_key": "apple_music", "label": "Apple Music",
                    "kind": "full", "payload": {"apple_id": m.candidate.external_id}}
        except Exception as exc:
            logger.debug("apple resolve failed: %s", exc)

    return best_opt
