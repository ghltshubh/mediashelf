"""TMDB API client.

Rate-limit courtesy per hard constraints: exponential backoff on 429/5xx and a
per-provider in-memory TTL cache on GETs. Accepts either a v3 API key or a v4
read access token (auto-detected).
"""

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p"

_CACHE_TTL = 6 * 3600
_cache: dict[str, tuple[float, Any]] = {}


class TMDBError(Exception):
    """Raised with a human-readable message safe to surface in the UI."""


def _cache_get(key: str) -> Any | None:
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < _CACHE_TTL:
        return hit[1]
    _cache.pop(key, None)
    return None


def clear_cache() -> None:
    _cache.clear()


class TMDBClient:
    def __init__(self, api_key: str):
        self._is_v4 = api_key.startswith("ey")  # v4 read tokens are JWTs
        self._api_key = api_key

    def _request_args(self, params: dict) -> tuple[dict, dict]:
        headers = {"Accept": "application/json"}
        if self._is_v4:
            headers["Authorization"] = f"Bearer {self._api_key}"
        else:
            params = {**params, "api_key": self._api_key}
        return headers, params

    async def _get(self, path: str, *, use_cache: bool = True, **params: Any) -> dict:
        cache_key = f"{path}?{sorted(params.items())!r}"
        if use_cache and (hit := _cache_get(cache_key)) is not None:
            return hit
        headers, full_params = self._request_args(params)
        delay = 1.0
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as client:
            for attempt in range(4):
                try:
                    resp = await client.get(path, params=full_params, headers=headers)
                except httpx.HTTPError as exc:
                    if attempt == 3:
                        raise TMDBError(f"Could not reach TMDB: {exc.__class__.__name__}") from exc
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                if resp.status_code == 200:
                    data = resp.json()
                    if use_cache:
                        _cache[cache_key] = (time.monotonic(), data)
                    return data
                if resp.status_code == 401:
                    msg = resp.json().get("status_message", "Invalid API key")
                    raise TMDBError(f"TMDB rejected the key: {msg}")
                if resp.status_code == 404:
                    raise TMDBError("TMDB: not found")
                if resp.status_code == 429 or resp.status_code >= 500:
                    if attempt == 3:
                        raise TMDBError(f"TMDB unavailable (HTTP {resp.status_code})")
                    retry_after = float(resp.headers.get("Retry-After", delay))
                    await asyncio.sleep(max(retry_after, delay))
                    delay *= 2
                    continue
                raise TMDBError(f"TMDB error (HTTP {resp.status_code})")
        raise TMDBError("TMDB request failed")  # unreachable

    async def validate_key(self) -> None:
        """Fires a real request; raises TMDBError with the actual error text."""
        await self._get("/configuration", use_cache=False)

    async def genres(self, media_type: str) -> dict[int, str]:
        data = await self._get(f"/genre/{media_type}/list")
        return {g["id"]: g["name"] for g in data.get("genres", [])}

    async def popular(self, media_type: str, page: int = 1, region: str | None = None) -> list[dict]:
        return await self.titles_list(media_type, "popular", page=page, region=region)

    async def top_rated(self, media_type: str, page: int = 1, region: str | None = None) -> list[dict]:
        return await self.titles_list(media_type, "top_rated", page=page, region=region)

    async def titles_list(self, media_type: str, kind: str, page: int = 1,
                          region: str | None = None) -> list[dict]:
        params: dict[str, Any] = {"page": page}
        if region:
            params["region"] = region
        data = await self._get(f"/{media_type}/{kind}", **params)
        return data.get("results", [])

    async def detail(self, media_type: str, tmdb_id: int) -> dict:
        return await self._get(f"/{media_type}/{tmdb_id}")

    async def watch_provider_regions(self) -> list[dict]:
        """All regions TMDB reports availability for: [{iso_3166_1, english_name}]."""
        data = await self._get("/watch/providers/regions")
        return data.get("results", [])

    async def external_ids(self, media_type: str, tmdb_id: int) -> dict:
        """→ {imdb_id, ...}. Movie detail also carries imdb_id, but TV needs this."""
        return await self._get(f"/{media_type}/{tmdb_id}/external_ids")

    async def videos(self, media_type: str, tmdb_id: int) -> list[dict]:
        data = await self._get(f"/{media_type}/{tmdb_id}/videos")
        return data.get("results", [])

    async def search_multi(self, query: str, page: int = 1) -> list[dict]:
        data = await self._get("/search/multi", query=query, include_adult="false", page=page)
        return data.get("results", [])

    async def watch_providers(self, media_type: str, tmdb_id: int) -> dict:
        """Returns {country: {link, flatrate: [...], rent: [...], buy: [...], ads/free}}."""
        data = await self._get(f"/{media_type}/{tmdb_id}/watch/providers")
        return data.get("results", {})


def poster_url(path: str | None, size: str = "w342") -> str | None:
    return f"{IMAGE_BASE}/{size}{path}" if path else None
