from tests.conftest import run_sync_now


def test_shelf_reports_catalog_age_and_country(client):
    run_sync_now()
    shelf = client.get("/api/shelf").json()
    assert shelf["country"] == "US"
    assert shelf["synced_at"] is not None  # data-age banner source


def test_badges_carry_last_checked_age(client):
    run_sync_now()
    shelf = client.get("/api/shelf").json()
    item = shelf["rails"][0]["items"][0]
    assert all(b["checked_at"] for b in item["badges"])


def test_sync_failure_classified_and_catalog_survives(client, monkeypatch):
    import pytest

    from app.providers import tmdb as tmdb_mod
    from app.services import catalog

    run_sync_now()

    async def broken_genres(self, media_type):
        raise tmdb_mod.TMDBError("TMDB rejected the key: Invalid API key")

    monkeypatch.setattr(tmdb_mod.TMDBClient, "genres", broken_genres)
    with pytest.raises(tmdb_mod.TMDBError):
        run_sync_now()

    assert catalog.sync_state["status"] == "error"
    assert catalog.sync_state["error_kind"] == "auth"
    # The shelf never blanks: last-synced catalog still serves.
    shelf = client.get("/api/shelf").json()
    assert shelf["stats"]["titles"] == 3
    assert shelf["synced_at"] is not None


def test_search_query_simplification():
    from app.services.catalog import search_query

    assert search_query("All Elite Wrestling: Dynamite") == "All Elite Wrestling"
    assert search_query("Ranma ½ (2024)") == "Ranma ½"
    assert search_query("M3GAN") == "M3GAN"
    # A stem too short to be useful keeps the full title.
    assert search_query("V: The Series") == "V: The Series"


def test_deep_link_falls_back_to_homepage(client):
    # A service with no template and an availability row with no TMDB link
    # falls back to the service homepage (template → tmdb link → homepage).
    from sqlalchemy import select

    from app.db import session_factory
    from app.models import Availability, MediaItem, Service
    from app.services.catalog import serialize_item

    run_sync_now()
    with session_factory()() as db:
        svc = db.scalar(select(Service).where(Service.name == "Fancy New Service"))
        svc.homepage_url = "https://fancy.example.com"
        for a in db.scalars(select(Availability).where(Availability.service_id == svc.id)):
            a.tmdb_link = None
        db.commit()
        item = db.scalar(select(MediaItem).where(MediaItem.title == "Neon Alley"))
        data = serialize_item(item, set(), "US")
    badge = next(b for b in data["badges"] if b["service_name"] == "Fancy New Service")
    assert badge["deep_link"] == "https://fancy.example.com"
