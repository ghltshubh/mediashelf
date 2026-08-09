"""Netflix's published weekly Top 10 (Tudum open data).

Netflix publishes its Top 10 for press and transparency — no login, no key:

    https://www.netflix.com/tudum/top10/data/all-weeks-countries.tsv

That file is ~31 MB of every week since 2021 for every country (~20 rows per
country-week: 10 films + 10 TV), updated weekly, with a Last-Modified header
and no ETag. The fetch sends If-Modified-Since (the dance ``podcasts.py`` does
for feeds), but Netflix's CDN ignores it — verified live, along with Range —
so the 304 is done by hand: the response is STREAMED, headers arrive before
the body, and an unchanged Last-Modified aborts the stream without reading it.
Most nights cost a connection and no bytes. When the file HAS changed, the
stream keeps only rows for the latest week in the user's tracked countries —
on a Pi that is the difference between ~20×N parsed rows and buffering 31 MB.

``_fetch`` is the one network seam, monkeypatchable per provider convention.
"""

import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from app import settings_store

logger = logging.getLogger(__name__)

DATA_URL = "https://www.netflix.com/tudum/top10/data/all-weeks-countries.tsv"
USER_AGENT = "MediaShelf/0.1 (published Top 10 reader)"

SOURCE_KEY = "netflix"
LAST_MODIFIED_SETTING = "netflix_top10_last_modified"
FETCHED_AT_SETTING = "netflix_top10_fetched_at"


async def _no_lines() -> AsyncGenerator[str, None]:
    return
    yield ""  # makes this a generator; never reached


async def _fetch(last_modified: str | None) -> tuple[int, str | None, AsyncGenerator[str, None]]:
    """Streaming conditional GET → (status, Last-Modified header, lines).
    The line generator owns the connection and closes it when exhausted or
    when the caller aborts it with ``aclose()``."""
    headers = {"User-Agent": USER_AGENT}
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=120.0),
                               follow_redirects=True)
    try:
        resp = await client.send(client.build_request("GET", DATA_URL, headers=headers),
                                 stream=True)
    except Exception:
        await client.aclose()
        raise
    if resp.status_code != 200:
        await resp.aclose()
        await client.aclose()
        return resp.status_code, resp.headers.get("last-modified"), _no_lines()

    async def lines() -> AsyncGenerator[str, None]:
        try:
            async for line in resp.aiter_lines():
                yield line
        finally:
            await resp.aclose()
            await client.aclose()

    return resp.status_code, resp.headers.get("last-modified"), lines()


async def latest_top10(db: Session, countries: list[str]) -> list[dict] | None:
    """The latest week's Top 10 for the tracked countries, as import items
    [{title, rank}] sorted by best rank. Returns None when the file has not
    changed since the last fetch (304) and [] when nothing matched — callers
    must import only a non-empty result, so a thin week never clears the rail.
    """
    prev = settings_store.get_setting(db, LAST_MODIFIED_SETTING)
    status, last_modified, lines = await _fetch(prev or None)
    if status == 304:
        return None
    if status != 200:
        raise RuntimeError(f"Netflix Top 10 fetch failed (HTTP {status})")
    if prev and last_modified == prev:
        # The CDN answered 200 to our If-Modified-Since anyway — hand-rolled
        # 304: headers are in, the 31 MB body is not. Abort before reading it.
        await lines.aclose()
        return None

    wanted = {c.upper() for c in countries}
    cols: dict[str, int] = {}
    latest_week = ""
    rows: list[tuple[str, int]] = []
    async for line in lines:
        if not line.strip():
            continue
        parts = line.split("\t")
        if not cols:
            cols = {name.strip(): i for i, name in enumerate(parts)}
            continue
        try:
            country = parts[cols["country_iso2"]].strip().upper()
            week = parts[cols["week"]].strip()
            rank = int(parts[cols["weekly_rank"]])
            title = parts[cols["show_title"]].strip()
        except (KeyError, IndexError, ValueError):
            continue  # a malformed row is their problem, not a failed rail
        if country not in wanted or not title:
            continue
        # Single pass over a file we won't buffer: keep rows only for the newest
        # week seen so far (ISO dates compare lexicographically).
        if week > latest_week:
            latest_week, rows = week, []
        if week == latest_week:
            rows.append((title, rank))

    # One title can chart in several countries, or as both film and show —
    # keep it once, at its best rank.
    best: dict[str, tuple[str, int]] = {}
    for title, rank in rows:
        if title.lower() not in best or rank < best[title.lower()][1]:
            best[title.lower()] = (title, rank)

    settings_store.set_setting(db, FETCHED_AT_SETTING, datetime.now(UTC).isoformat())
    if last_modified:
        settings_store.set_setting(db, LAST_MODIFIED_SETTING, last_modified)
    return [{"title": t, "rank": r} for t, r in sorted(best.values(), key=lambda tr: tr[1])]
