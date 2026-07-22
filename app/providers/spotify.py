"""Spotify catalog search via client-credentials (M2).

App-key only — no user OAuth (that's the M3 connector). The user supplies their
own Spotify app credentials per Appendix B. Tokens are cached until expiry;
errors surface Spotify's actual message.
"""

import asyncio
import base64
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"

_token_cache: dict[str, tuple[float, str]] = {}


class SpotifyError(Exception):
    """Human-readable, safe to surface in the UI."""


def clear_token_cache() -> None:
    _token_cache.clear()


async def _get_token(client_id: str, client_secret: str) -> str:
    cached = _token_cache.get(client_id)
    if cached and time.monotonic() < cached[0]:
        return cached[1]
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(
                TOKEN_URL,
                data={"grant_type": "client_credentials"},
                headers={"Authorization": f"Basic {basic}"},
            )
        except httpx.HTTPError as exc:
            raise SpotifyError(f"Could not reach Spotify: {exc.__class__.__name__}") from exc
    if resp.status_code != 200:
        try:
            body = resp.json()
            detail = body.get("error_description") or body.get("error") or f"HTTP {resp.status_code}"
        except ValueError:
            detail = f"HTTP {resp.status_code}"
        raise SpotifyError(f"Spotify rejected the credentials: {detail}")
    data = resp.json()
    token = data["access_token"]
    _token_cache[client_id] = (time.monotonic() + data.get("expires_in", 3600) - 60, token)
    return token


async def validate_credentials(client_id: str, client_secret: str) -> None:
    """Fires a real token request; raises SpotifyError with the actual error text."""
    _token_cache.pop(client_id, None)
    await _get_token(client_id, client_secret)


async def search_catalog(client_id: str, client_secret: str, query: str,
                         country: str) -> dict[str, list[dict[str, Any]]]:
    """Returns {tracks: [...], albums: [...], artists: [...]} in our neutral shape."""
    token = await _get_token(client_id, client_secret)
    params: dict[str, str | int] = {"q": query, "type": "track,album,artist",
                                    "limit": 8, "market": country}
    delay = 1.0
    async with httpx.AsyncClient(base_url=API_BASE, timeout=10) as client:
        for attempt in range(3):
            resp = await client.get("/search", params=params,
                                    headers={"Authorization": f"Bearer {token}"})
            if resp.status_code == 200:
                break
            if resp.status_code == 401:  # token expired mid-flight — refresh once
                _token_cache.pop(client_id, None)
                token = await _get_token(client_id, client_secret)
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt == 2:
                    raise SpotifyError(f"Spotify search unavailable (HTTP {resp.status_code})")
                retry_after = float(resp.headers.get("Retry-After", delay))
                await asyncio.sleep(max(retry_after, delay))
                delay *= 2
                continue
            raise SpotifyError(f"Spotify search failed (HTTP {resp.status_code})")
        else:
            raise SpotifyError("Spotify search failed")
    data = resp.json()

    def thumb(images: list) -> str | None:
        return images[-1]["url"] if images else None  # smallest image last

    tracks = [{
        "entity": "track",
        "spotify_id": t.get("id"),
        "spotify_uri": t.get("uri"),
        "title": t["name"],
        "artists": [a["name"] for a in t.get("artists", [])],
        "year": int(t["album"]["release_date"][:4])
        if t.get("album", {}).get("release_date", "")[:4].isdigit() else None,
        "thumb": thumb(t.get("album", {}).get("images", [])),
        "duration_ms": t.get("duration_ms"),
        "isrc": (t.get("external_ids") or {}).get("isrc"),
        "popularity": t.get("popularity", 0),
        "url": t.get("external_urls", {}).get("spotify"),
    } for t in data.get("tracks", {}).get("items", []) if t]
    albums = [{
        "entity": "album",
        "spotify_id": a.get("id"),
        "spotify_uri": a.get("uri"),
        "title": a["name"],
        "artists": [ar["name"] for ar in a.get("artists", [])],
        "year": int(a["release_date"][:4])
        if a.get("release_date", "")[:4].isdigit() else None,
        "thumb": thumb(a.get("images", [])),
        "popularity": 0,
        "url": a.get("external_urls", {}).get("spotify"),
    } for a in data.get("albums", {}).get("items", []) if a]
    artists = [{
        "entity": "artist",
        "spotify_id": a.get("id"),
        "spotify_uri": a.get("uri"),
        "title": a["name"],
        "artists": [],
        "year": None,
        "thumb": thumb(a.get("images", [])),
        "popularity": a.get("popularity", 0),
        "url": a.get("external_urls", {}).get("spotify"),
    } for a in data.get("artists", {}).get("items", []) if a]
    return {"tracks": tracks, "albums": albums, "artists": artists}
