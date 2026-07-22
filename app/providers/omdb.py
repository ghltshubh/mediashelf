"""OMDb API client (optional ratings provider).

Legitimate source for IMDb / Rotten Tomatoes / Metacritic scores — OMDb licenses
and aggregates them, keyed by IMDb id. Free tier: 1,000 calls/day with the
user's own key (bring-your-own-key, off by default) — same pattern as the
availability provider. We never scrape imdb.com.
"""

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://www.omdbapi.com/"


class OMDbError(Exception):
    """Human-readable, safe to surface in the UI."""


class OMDbClient:
    def __init__(self, api_key: str):
        self._api_key = api_key

    async def _get(self, **params) -> dict:
        delay = 1.0
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=10) as client:
            for attempt in range(3):
                try:
                    resp = await client.get("", params={"apikey": self._api_key, **params})
                except httpx.HTTPError as exc:
                    if attempt == 2:
                        raise OMDbError(f"Could not reach OMDb: {exc.__class__.__name__}") from exc
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                if resp.status_code == 401:
                    raise OMDbError("OMDb rejected the key")
                if resp.status_code == 429 or resp.status_code >= 500:
                    if attempt == 2:
                        raise OMDbError(f"OMDb unavailable (HTTP {resp.status_code})")
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                data = resp.json()
                if data.get("Response") == "False":
                    raise OMDbError(data.get("Error", "OMDb error"))
                return data
        raise OMDbError("OMDb request failed")  # unreachable

    async def validate_key(self) -> None:
        """Fires a real request; raises OMDbError with the actual error text."""
        try:
            await self._get(i="tt0111161")  # Shawshank — always present
        except OMDbError as exc:
            if "movie not found" in str(exc).lower():
                return  # key works, lookup issue only
            raise

    async def ratings(self, imdb_id: str) -> dict:
        """→ {imdb, imdb_votes, rt, metacritic} (missing keys omitted)."""
        data = await self._get(i=imdb_id, tomatoes="false")
        out: dict = {}
        rating = data.get("imdbRating")
        if rating and rating != "N/A":
            try:
                out["imdb"] = float(rating)
            except ValueError:
                pass
        votes = data.get("imdbVotes")
        if votes and votes != "N/A":
            out["imdb_votes"] = votes
        for r in data.get("Ratings", []):
            src, val = r.get("Source"), r.get("Value", "")
            if src == "Rotten Tomatoes":
                out["rt"] = val  # "87%"
            elif src == "Metacritic":
                out["metacritic"] = val.split("/")[0]  # "74/100" → "74"
        return out
