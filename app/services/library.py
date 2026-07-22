"""Personal library sync (M3, read-only).

Full-refresh per (service, entry_type): connectors read everything, we replace
the rows. Token expiry mid-sync is never a raw error — the provider is marked
expired and surfaces as "Reconnect <service>" (plan failure modes)."""

import logging
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import settings_store
from app.connectors.base import AuthExpired, NotConnected
from app.connectors.spotify import SpotifyConnector
from app.connectors.youtube import YouTubeConnector
from app.models import LibraryEntry, Service

logger = logging.getLogger(__name__)

CONNECTORS: dict[str, SpotifyConnector | YouTubeConnector] = {
    "spotify": SpotifyConnector(), "youtube": YouTubeConnector(),
}

sync_state: dict[str, dict] = {
    "spotify": {"status": "idle", "detail": None},
    "youtube": {"status": "idle", "detail": None},
}


def _service_id(db: Session, key: str) -> int | None:
    return db.scalar(select(Service.id).where(Service.key == key))


def _replace_entries(db: Session, service_id: int, entry_type: str, rows: list[dict]) -> int:
    db.execute(delete(LibraryEntry).where(LibraryEntry.service_id == service_id,
                                          LibraryEntry.entry_type == entry_type))
    for r in rows:
        db.add(LibraryEntry(service_id=service_id, entry_type=entry_type,
                            external_id=r["external_id"], payload=r["payload"]))
    db.commit()
    return len(rows)


def sync_provider(db: Session, provider: str) -> dict:
    """Runs a full library refresh for one provider. Sync — call in a thread."""
    connector = CONNECTORS.get(provider)
    if connector is None:
        raise ValueError(f"unknown provider {provider}")
    state = sync_state[provider]
    state.update(status="running", detail="reading library")
    service_id = _service_id(db, provider)
    if service_id is None:
        state.update(status="idle", detail=None)
        return {"likes": 0, "follows": 0}
    try:
        likes = connector.read_likes(db)
        follows = connector.read_follows(db)
        counts = {
            "likes": _replace_entries(db, service_id, "like", likes),
            "follows": _replace_entries(db, service_id, "follow", follows),
        }
        settings_store.set_setting(db, f"library_synced_at_{provider}",
                                   datetime.now(UTC).isoformat())
        state.update(status="idle", detail=None)
        logger.info("library sync %s: %s", provider, counts)
        return counts
    except AuthExpired:
        # Marked expired by the connector; UI shows "Reconnect".
        state.update(status="auth", detail=f"Reconnect {connector.name}")
        return {"likes": 0, "follows": 0}
    except NotConnected:
        state.update(status="idle", detail=None)
        return {"likes": 0, "follows": 0}
    except Exception as exc:
        logger.warning("library sync %s failed: %s", provider, exc)
        state.update(status="error", detail=str(exc))
        return {"likes": 0, "follows": 0}


def sync_all_connected(db: Session) -> None:
    for key, connector in CONNECTORS.items():
        if connector.connected(db):
            sync_provider(db, key)


def _entity_for(group_key: str) -> str:
    return {"spotify_like": "track", "spotify_follow": "artist",
            "youtube_like": "video", "youtube_follow": "channel"}.get(group_key, "track")


def to_search_row(provider: str, group_key: str, e: dict,
                  subscribed: set[str], playback_state: dict) -> dict:
    """A library entry as a palette/library row with the playback chain attached."""
    from app.services import search as search_service

    service_name = "Spotify" if provider == "spotify" else "YouTube"
    uri = e.get("uri") or ""
    row = {
        "entity": _entity_for(group_key),
        "title": e.get("title", ""),
        "artists": e.get("artists") or ([e["channel"]] if e.get("channel") else []),
        "year": None,
        "thumb": e.get("thumb"),
        "spotify_id": uri.split(":")[-1] if uri.startswith("spotify:track") else None,
        "spotify_uri": uri if uri.startswith("spotify:") else None,
        "youtube_video_id": e.get("video_id"),
        "services": [{"service_key": provider, "service_name": service_name,
                      "url": e.get("url"), "owned": provider in subscribed}],
    }
    search_service.attach_music_playback(row, playback_state)
    return row


def rows_for_groups(db: Session, subscribed: set[str], playback_state: dict,
                    query: str | None = None, per_group: int = 100) -> list[dict]:
    groups = library_groups(db, query)
    for g in groups:
        g["items"] = [to_search_row(g["provider"], g["key"], e, subscribed, playback_state)
                      for e in g["items"][:per_group]]
    return groups


def library_groups(db: Session, query: str | None = None) -> list[dict]:
    """Grouped entries for the Library page and the YOUR LIBRARY search group."""
    groups = []
    for provider, connector in CONNECTORS.items():
        service_id = _service_id(db, provider)
        if service_id is None:
            continue
        for entry_type, label in (("like", "likes"), ("follow", "follows")):
            stmt = select(LibraryEntry).where(LibraryEntry.service_id == service_id,
                                              LibraryEntry.entry_type == entry_type)
            rows = db.scalars(stmt).all()
            if query:
                qn = query.lower()
                rows = [r for r in rows
                        if qn in (r.payload.get("title") or "").lower()
                        or any(qn in a.lower() for a in r.payload.get("artists", []))
                        or qn in (r.payload.get("channel") or "").lower()][:8]
            if rows:
                groups.append({
                    "key": f"{provider}_{entry_type}",
                    "provider": provider,
                    "label": f"{connector.name} {label}",
                    "count": len(rows),
                    "items": [{"external_id": r.external_id, **r.payload} for r in rows],
                })
    return groups
