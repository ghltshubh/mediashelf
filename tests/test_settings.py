from sqlalchemy import select

from app.db import session_factory
from app.models import Setting


def test_health(client):
    assert client.get("/api/health").json() == {"ok": True}


def test_settings_roundtrip_and_secret_at_rest(client):
    r = client.get("/api/settings")
    assert r.json()["tmdb_api_key_set"] is False
    assert r.json()["country"] == "US"

    r = client.put("/api/settings", json={"tmdb_api_key": "testkey123456", "country": "de"})
    assert r.status_code == 200
    body = r.json()
    assert body["tmdb_api_key_set"] is True
    assert body["country"] == "DE"
    # Masked, never echoed raw.
    assert body["tmdb_api_key_masked"] != "testkey123456"
    assert "testkey123456" not in str(body)

    # Encrypted at rest: raw key must not appear in the settings table.
    with session_factory()() as db:
        row = db.scalar(select(Setting).where(Setting.key == "tmdb_api_key"))
        assert row is not None and row.encrypted is True
        assert "testkey123456" not in (row.value or "")


def test_invalid_country_rejected(client):
    r = client.put("/api/settings", json={"country": "USA"})
    assert r.status_code == 422


def test_locale_is_independent_of_country(client):
    # Default: unset → empty (client falls back to browser language).
    assert client.get("/api/settings").json()["locale"] == ""
    # Set a locale that does NOT match the content region — they are decoupled.
    r = client.put("/api/settings", json={"country": "FR", "locale": "en-US"})
    assert r.status_code == 200
    body = r.json()
    assert body["country"] == "FR"
    assert body["locale"] == "en-US"
    # Clearing it (empty string) reverts to the browser-default sentinel.
    assert client.put("/api/settings", json={"locale": ""}).json()["locale"] == ""


def test_invalid_locale_rejected(client):
    r = client.put("/api/settings", json={"locale": "not a locale!"})
    assert r.status_code == 422


def test_bad_tmdb_key_rejected_with_real_error(client):
    r = client.put("/api/settings", json={"tmdb_api_key": "badkey"})
    assert r.status_code == 400
    assert "Invalid API key" in r.json()["detail"]


def test_validate_endpoint_surfaces_error_text(client):
    ok = client.post("/api/settings/tmdb/validate", json={"tmdb_api_key": "goodkey"}).json()
    assert ok == {"ok": True}
    bad = client.post("/api/settings/tmdb/validate", json={"tmdb_api_key": "badkey"}).json()
    assert bad["ok"] is False
    assert "Invalid API key" in bad["error"]


# ---------- launch sync is age-gated (desktop opens and closes all day) ----------

def test_catalog_staleness_gate(client):
    """The nightly cron only exists while the process does, so a launch sync
    covers machines that were off — but it must not re-sync on every open."""
    from datetime import UTC, datetime, timedelta

    from app import settings_store
    from app.db import session_factory
    from app.main import LAUNCH_SYNC_AFTER_HOURS, _catalog_is_stale

    with session_factory()() as db:
        # Never synced → always sync.
        settings_store.set_setting(db, "catalog_synced_at", None)
        assert _catalog_is_stale(db) is True

        # Just synced → don't.
        settings_store.set_setting(db, "catalog_synced_at",
                                   datetime.now(UTC).isoformat())
        assert _catalog_is_stale(db) is False

        # Past the window → sync.
        old = datetime.now(UTC) - timedelta(hours=LAUNCH_SYNC_AFTER_HOURS + 1)
        settings_store.set_setting(db, "catalog_synced_at", old.isoformat())
        assert _catalog_is_stale(db) is True

        # Unreadable stamp → stale, never silently never-sync.
        settings_store.set_setting(db, "catalog_synced_at", "not-a-date")
        assert _catalog_is_stale(db) is True

        # Naive timestamps (older rows) must not raise.
        naive = (datetime.now() - timedelta(hours=LAUNCH_SYNC_AFTER_HOURS + 1)).isoformat()
        settings_store.set_setting(db, "catalog_synced_at", naive)
        assert _catalog_is_stale(db) is True
