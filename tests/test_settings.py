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
