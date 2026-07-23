"""Cross-service playback resolution.

Given a track's metadata (from, say, a YouTube like that can't be embedded),
find the best-matching song across the user's *playable* services (Spotify
Premium, Apple Music) and return a concrete play option for it. This lets a
song play via a sanctioned player on whichever service actually has it — no
YouTube stream extraction, all within each service's own SDK/API.

YouTube metadata is noisy — "Snow Patrol - Chasing Cars (Official Video)" by
channel "SnowPatrolVEVO", or "No Roof Access" by "Kyle Lux - Topic" — so we
clean it and try a few source interpretations ("Artist - Title" split, cleaned
title + channel, title alone), scoring every candidate with the matching
engine and keeping the single best hit.
"""

import logging
import re

from sqlalchemy.orm import Session

from app import settings_store
from app.providers import spotify as spotify_api
from app.services import matching
from app.services import playback as playback_service

logger = logging.getLogger(__name__)

MIN_CONFIDENCE = 0.6  # below the auto-migrate bar (0.85) but safe for "play this"
GOOD_ENOUGH = matching.AUTO_THRESHOLD  # stop trying variants once we're here

# YouTube-channel noise: auto-generated "X - Topic" channels and VEVO handles.
_TOPIC = re.compile(r"\s*-\s*topic\s*$", re.IGNORECASE)
_VEVO = re.compile(r"\s*vevo\s*$", re.IGNORECASE)
# Upload decorations that poison catalog search queries (kept out of scoring —
# the matching engine does its own normalization).
_DECOR = re.compile(
    r"\s*[\(\[][^)\]]*(official|video|audio|lyric|visuali[sz]er|hq|hd|4k|m/?v)[^)\]]*[\)\]]",
    re.IGNORECASE,
)


def _clean_channel(name: str) -> str:
    n = _TOPIC.sub("", name.strip())
    n = _VEVO.sub("", n)
    return n.strip()


def _clean_title(title: str) -> str:
    t = _DECOR.sub(" ", title)
    return re.sub(r"\s{2,}", " ", t).strip() or title.strip()


def _attempts(title: str, artists: list[str],
              duration_ms: int | None) -> list[tuple[matching.TrackRef, str]]:
    """Source interpretations to try, each paired with its catalog query."""
    t = _clean_title(title)
    chans = [c for c in (_clean_channel(a) for a in artists or []) if c]
    out: list[tuple[matching.TrackRef, str]] = []
    # "Artist - Title" uploads: the artist lives in the title, the channel is
    # often an unrelated uploader.
    if " - " in t:
        left, right = (p.strip() for p in t.split(" - ", 1))
        if left and right and len(left) <= 48:
            out.append((matching.TrackRef(title=right, artists=[left],
                                          duration_ms=duration_ms), f"{right} {left}"))
    if chans:
        out.append((matching.TrackRef(title=t, artists=chans, duration_ms=duration_ms),
                    f"{t} {' '.join(chans)}"))
    out.append((matching.TrackRef(title=t, artists=chans, duration_ms=duration_ms), t))
    # Dedupe by query, order preserved.
    seen: set[str] = set()
    deduped: list[tuple[matching.TrackRef, str]] = []
    for ref, q in out:
        if q.lower() not in seen:
            seen.add(q.lower())
            deduped.append((ref, q))
    return deduped


async def _apple_candidates(token: str, query: str, storefront: str) -> list[matching.TrackRef]:
    """Apple Music catalog search — needs only the developer token (no user token)."""
    from app.providers import apple

    songs = await apple.search_songs(token, query, storefront, limit=5)
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
    Tries cleaned source interpretations against each service's catalog and
    returns the single highest-confidence match above the threshold."""
    title = (title or "").strip()
    if not title:
        return None
    attempts = _attempts(title, artists or [], duration_ms)
    country = settings_store.get_setting(db, "country") or "US"
    state = playback_service.user_playback_state(db)

    best_conf = 0.0
    best_opt: dict | None = None

    # Spotify — in-app playback requires Premium.
    if state["spotify_connected"] and state["spotify_premium"]:
        cid = settings_store.get_setting(db, "spotify_client_id")
        secret = settings_store.get_setting(db, "spotify_client_secret")
        if cid and secret:
            for source, query in attempts:
                try:
                    res = await spotify_api.search_catalog(cid, secret, query, country)
                except Exception as exc:
                    logger.debug("spotify resolve search failed: %s", exc)
                    break
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
                if best_conf >= GOOD_ENOUGH:
                    break

    # Apple Music — catalog search needs only the developer token.
    token = settings_store.get_setting(db, "apple_developer_token")
    if token and best_conf < GOOD_ENOUGH:
        for source, query in attempts:
            try:
                cands = await _apple_candidates(token, query, (country or "us").lower())
            except Exception as exc:
                logger.debug("apple resolve search failed: %s", exc)
                break
            m = matching.best_match(source, cands)
            if m.candidate and m.confidence >= MIN_CONFIDENCE and m.confidence > best_conf:
                best_conf, best_opt = m.confidence, {
                    "engine": "musickit", "service_key": "apple_music", "label": "Apple Music",
                    "kind": "full", "payload": {"apple_id": m.candidate.external_id}}
            if best_conf >= GOOD_ENOUGH:
                break

    return best_opt
