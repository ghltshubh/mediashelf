"""Imported lists (Want to watch / Top 10): the shared import pipeline.

One loop turns {source, list_type, items} into resolved LibraryEntry rows.
It lives in services/ because it has two callers — the /api/watchlist/import
endpoint (paste, upload, or an external tool) and the nightly Netflix Top 10
fetch inside catalog.run_sync — and a sync job must not import from the HTTP
layer.

`replace=True` is a full-state sync scoped to (service, list_type): entries
absent from the payload are removed. Callers are responsible for not passing
an empty item list with replace on unless clearing is what they mean — the
API endpoint enforces that with its allow_empty flag.
"""

import logging

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LibraryEntry, Service
from app.providers.tmdb import TMDBClient, TMDBError
from app.services.resolve_titles import resolve_for_service

logger = logging.getLogger(__name__)

LIST_TYPES = ("watchlist", "top10")

MAX_IMPORT_ITEMS = 500


class ImportItem(BaseModel):
    title: str
    year: int | None = None
    rank: int | None = None          # top10 ordering


class UnknownServiceError(ValueError):
    """The source key names no service in this install's catalog."""


async def import_list(db: Session, api_key: str, *, source: str,
                      items: list[ImportItem], countries: list[str],
                      list_type: str = "watchlist", replace: bool = True) -> dict:
    from app.services import catalog  # circular: catalog.run_sync calls back here

    svc = db.scalar(select(Service).where(Service.key == source.strip().lower()))
    if svc is None:
        raise UnknownServiceError(f"Unknown service '{source}'")
    client = TMDBClient(api_key)
    known_keys = set(db.scalars(select(Service.key)))

    added, kept, unmatched = 0, 0, []
    truncated = max(len(items) - MAX_IMPORT_ITEMS, 0)
    seen_external: set[str] = set()
    for idx, item in enumerate(items[:MAX_IMPORT_ITEMS]):
        title = item.title.strip()
        if not title:
            continue
        # Year is part of the key: without it "Dune" 1984 and 2021 collapse into
        # one row, and a paste of both silently becomes one.
        external_id = f"{source}:{list_type}:{title.lower()}:{item.year or ''}"
        if external_id in seen_external:
            continue
        seen_external.add(external_id)
        rank = item.rank if item.rank is not None else (idx + 1 if list_type == "top10" else None)
        payload = {"title": title, "year": item.year, "rank": rank}
        existing = db.scalar(select(LibraryEntry).where(
            LibraryEntry.service_id == svc.id,
            LibraryEntry.entry_type == list_type,
            LibraryEntry.external_id == external_id))
        if existing is not None:
            existing.payload = payload  # refresh rank even when title unchanged
            kept += 1
            continue
        # Resolve against TMDB: prefer the match that's on the source service,
        # else article-insensitive popularity-best.
        try:
            results = [r for r in await client.search_multi(title)
                       if r.get("media_type") in ("movie", "tv")]
        except TMDBError:
            results = []
        best = await resolve_for_service(client, results, title, item.year,
                                         svc.key, countries[0], known_keys)
        if best is None:
            unmatched.append(title)
            continue
        media = await catalog.import_title(db, api_key, best["media_type"], best["id"], countries)
        db.add(LibraryEntry(service_id=svc.id, media_item_id=media.id,
                            entry_type=list_type, external_id=external_id, payload=payload))
        db.commit()
        added += 1

    removed = 0
    if replace:
        for entry in db.scalars(select(LibraryEntry).where(
                LibraryEntry.service_id == svc.id,
                LibraryEntry.entry_type == list_type)):
            if entry.external_id not in seen_external:
                db.delete(entry)
                removed += 1
        db.commit()
    return {"source": source, "added": added, "kept": kept,
            "removed": removed, "unmatched": unmatched, "truncated": truncated}
