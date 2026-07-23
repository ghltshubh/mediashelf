"""Apple Music catalog reads.

Catalog search needs only the MusicKit developer token (Settings → Keys) — no
user sign-in. Shared by universal search and cross-service playback resolution.
"""

import httpx

API_BASE = "https://api.music.apple.com"


async def search_songs(token: str, term: str, storefront: str = "us",
                       limit: int = 8) -> list[dict]:
    """Raw Apple catalog song objects for a search term ([] on any failure)."""
    async with httpx.AsyncClient(base_url=API_BASE, timeout=10) as client:
        resp = await client.get(
            f"/v1/catalog/{storefront}/search",
            params={"term": term, "types": "songs", "limit": limit},
            headers={"Authorization": f"Bearer {token}"},
        )
    if resp.status_code != 200:
        return []
    return ((resp.json().get("results") or {}).get("songs") or {}).get("data", [])
