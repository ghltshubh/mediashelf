import pytest

from app.providers import tmdb as tmdb_mod
from app.services import search as search_service
from tests.conftest import run_sync_now

SEARCH_MULTI = [
    {"media_type": "movie", "id": 101, "title": "The Long Voyage",
     "release_date": "2023-06-01", "poster_path": "/voyage.jpg", "popularity": 90.0},
    {"media_type": "movie", "id": 555, "title": "Voyage of Time",
     "release_date": "2016-10-07", "poster_path": "/vot.jpg", "popularity": 20.0},
    {"media_type": "tv", "id": 777, "name": "Voyagers", "first_air_date": "2020-01-01",
     "poster_path": "/voyagers.jpg", "popularity": 55.0},
    {"media_type": "person", "id": 1, "name": "Some Actor"},
]


@pytest.fixture(autouse=True)
def _search_state(monkeypatch):
    search_service.reset_state_for_tests()

    async def search_multi(self, query, page=1):
        return SEARCH_MULTI

    monkeypatch.setattr(tmdb_mod.TMDBClient, "search_multi", search_multi)
    yield
    search_service.reset_state_for_tests()


def _set_key(client):
    client.put("/api/settings", json={"tmdb_api_key": "goodkey"})


def test_video_search_merges_local_and_tmdb(client):
    _set_key(client)
    run_sync_now()
    r = client.get("/api/search", params={"q": "voyage", "scope": "video"}).json()
    assert [p["state"] for p in r["providers"]] == ["ok", "ok"]
    items = r["groups"][0]["items"]
    titles = [i["title"] for i in items]
    # tmdb_id 101 exists locally — merged into ONE row, the local one (with badges).
    assert titles.count("The Long Voyage") == 1
    voyage = next(i for i in items if i["title"] == "The Long Voyage")
    assert voyage["local"] is True and voyage["badges"]
    # Local hits rank above TMDB-only hits regardless of popularity.
    assert titles[0] == "The Long Voyage"
    # TMDB-only rows carry an import action.
    vot = next(i for i in items if i["title"] == "Voyage of Time")
    assert vot["action"]["type"] == "import" and vot["action"]["tmdb_id"] == 555


def test_video_owned_hit_deeplinks(client):
    _set_key(client)
    run_sync_now()
    services = client.get("/api/services").json()
    netflix = next(s for s in services if s["key"] == "netflix")
    client.put(f"/api/services/{netflix['id']}/subscription", json={"subscribed": True})
    r = client.get("/api/search", params={"q": "long voyage", "scope": "video"}).json()
    voyage = r["groups"][0]["items"][0]
    assert voyage["action"]["type"] == "deeplink"
    assert "netflix.com" in voyage["action"]["url"]
    assert voyage["hint"] == "↗ Netflix"


def test_search_cache_warm(client, monkeypatch):
    _set_key(client)
    calls = {"n": 0}
    orig = tmdb_mod.TMDBClient.search_multi

    async def counting(self, query, page=1):
        calls["n"] += 1
        return await orig(self, query, page)

    monkeypatch.setattr(tmdb_mod.TMDBClient, "search_multi", counting)
    client.get("/api/search", params={"q": "voyage", "scope": "video"})
    client.get("/api/search", params={"q": "Voyage", "scope": "video"})  # normalized hit
    assert calls["n"] == 1


def test_circuit_breaker_opens_and_recovers(client, monkeypatch):
    _set_key(client)

    async def broken(self, query, page=1):
        raise tmdb_mod.TMDBError("TMDB unavailable (HTTP 500)")

    monkeypatch.setattr(tmdb_mod.TMDBClient, "search_multi", broken)
    for q in ("aaa", "bbb", "ccc"):  # distinct queries dodge the cache
        r = client.get("/api/search", params={"q": q, "scope": "video"}).json()
    tmdb_state = next(p for p in r["providers"] if p["key"] == "tmdb")
    assert tmdb_state["state"] == "unavailable"
    # Breaker now open: no call attempted, local still serves.
    r = client.get("/api/search", params={"q": "ddd", "scope": "video"}).json()
    assert next(p for p in r["providers"] if p["key"] == "tmdb")["state"] == "unavailable"
    assert next(p for p in r["providers"] if p["key"] == "local")["state"] == "ok"
    # After cooldown, a half-open probe goes through again.
    search_service.breaker_for("tmdb").opened_at -= search_service.BREAKER_COOLDOWN + 1

    async def fixed(self, query, page=1):
        return SEARCH_MULTI

    monkeypatch.setattr(tmdb_mod.TMDBClient, "search_multi", fixed)
    r = client.get("/api/search", params={"q": "voyage", "scope": "video"}).json()
    assert next(p for p in r["providers"] if p["key"] == "tmdb")["state"] == "ok"


def test_music_unconfigured_without_spotify_keys(client):
    r = client.get("/api/search", params={"q": "voyage", "scope": "music"}).json()
    assert r["groups"] == []
    assert next(p for p in r["providers"] if p["key"] == "spotify")["state"] == "unconfigured"


class FakeMusicProvider:
    """Second music source proving dedupe merges services, and that adding a
    provider is a registration, not a refactor."""

    key = "fakemusic"
    scope = "music"

    def configured(self, db):
        return True

    async def search(self, db, query, country):
        return [{
            "entity": "album", "title": "Blue Train", "artists": ["John Coltrane"],
            "year": 1957, "thumb": None, "popularity": 10,
            "services": [{"service_key": "fakemusic", "service_name": "FakeMusic",
                          "url": "https://fake.example.com/blue-train"}],
        }]


class FakeSpotifyLike:
    key = "spotify"
    scope = "music"

    def configured(self, db):
        return True

    async def search(self, db, query, country):
        return [{
            "entity": "album", "title": "Blue Train", "artists": ["John Coltrane"],
            "year": 1957, "thumb": None, "popularity": 80,
            "services": [{"service_key": "spotify", "service_name": "Spotify",
                          "url": "https://open.spotify.com/album/xyz"}],
        }]


def test_music_dedupe_keeps_every_services_link(client, monkeypatch):
    monkeypatch.setattr(search_service, "PROVIDERS", [FakeSpotifyLike(), FakeMusicProvider()])
    services = client.get("/api/services").json()
    spotify = next(s for s in services if s["key"] == "spotify")
    client.put(f"/api/services/{spotify['id']}/subscription", json={"subscribed": True})

    r = client.get("/api/search", params={"q": "blue train", "scope": "music"}).json()
    items = r["groups"][0]["items"]
    assert len(items) == 1  # dedupe collapses display…
    row = items[0]
    keys = {s["service_key"]: s for s in row["services"]}
    assert set(keys) == {"spotify", "fakemusic"}  # …never options
    assert keys["spotify"]["url"] and keys["fakemusic"]["url"]
    assert keys["spotify"]["owned"] is True and keys["fakemusic"]["owned"] is False
    # Smart default routes to the owned service.
    assert row["action"]["url"] == "https://open.spotify.com/album/xyz"
    assert row["hint"] == "↗ Spotify"


def test_unimported_results_carry_badges(client):
    """TMDB-only hits show availability before import, with fresh owned flags."""
    _set_key(client)
    r = client.get("/api/search", params={"q": "voyage of time", "scope": "video"}).json()
    vot = next(i for i in r["groups"][0]["items"] if i["title"] == "Voyage of Time")
    assert vot["local"] is False
    names = {(b["service_key"], b["offer_type"]) for b in vot["badges"]}
    assert ("netflix", "flatrate") in names
    assert vot["owned"] is False
    assert vot["unlock_service"] == "Netflix"

    # Toggling the checklist re-lights cached results immediately (no re-fetch).
    services = client.get("/api/services").json()
    netflix = next(s for s in services if s["key"] == "netflix")
    client.put(f"/api/services/{netflix['id']}/subscription", json={"subscribed": True})
    r = client.get("/api/search", params={"q": "voyage of time", "scope": "video"}).json()
    vot = next(i for i in r["groups"][0]["items"] if i["title"] == "Voyage of Time")
    assert vot["owned"] is True
    nb = next(b for b in vot["badges"] if b["service_key"] == "netflix")
    assert nb["owned"] is True and "netflix.com" in nb["deep_link"]


def test_imported_title_appears_in_search_immediately(client, monkeypatch):
    """Regression: the 24h cache must not hide fresh imports (local is uncached)."""
    _set_key(client)

    async def detail(self, media_type, tmdb_id):
        return {"id": 555, "title": "Voyage of Time", "release_date": "2016-10-07",
                "overview": "", "poster_path": None, "runtime": 90, "genres": [],
                "popularity": 20.0, "vote_average": 6.9}

    monkeypatch.setattr(tmdb_mod.TMDBClient, "detail", detail)
    # Warm the cache BEFORE importing.
    r = client.get("/api/search", params={"q": "voyage of time", "scope": "video"}).json()
    top = r["groups"][0]["items"][0]
    assert top["local"] is False
    client.post("/api/titles/import", json={"media_type": "movie", "tmdb_id": 555})
    r = client.get("/api/search", params={"q": "voyage of time", "scope": "video"}).json()
    top = r["groups"][0]["items"][0]
    assert top["local"] is True and top["title"] == "Voyage of Time"


def test_import_title_from_search(client, monkeypatch):
    _set_key(client)

    async def detail(self, media_type, tmdb_id):
        assert (media_type, tmdb_id) == ("movie", 555)
        return {"id": 555, "title": "Voyage of Time", "release_date": "2016-10-07",
                "overview": "The universe.", "poster_path": "/vot.jpg", "runtime": 90,
                "genres": [{"id": 99, "name": "Documentary"}], "popularity": 20.0,
                "vote_average": 6.9}

    monkeypatch.setattr(tmdb_mod.TMDBClient, "detail", detail)
    r = client.post("/api/titles/import", json={"media_type": "movie", "tmdb_id": 555})
    assert r.status_code == 200
    t = r.json()
    assert t["title"] == "Voyage of Time"
    assert t["genres"] == ["Documentary"]
    assert t["runtime_minutes"] == 90
    # Idempotent: importing again returns the same row.
    again = client.post("/api/titles/import", json={"media_type": "movie", "tmdb_id": 555}).json()
    assert again["id"] == t["id"]


def test_spotify_settings_roundtrip(client, monkeypatch):
    from sqlalchemy import select

    from app.db import session_factory
    from app.models import Setting
    from app.providers import spotify as spotify_mod

    async def ok_validate(cid, secret):
        if secret == "badsecret":
            raise spotify_mod.SpotifyError("Spotify rejected the credentials: Invalid client secret")

    monkeypatch.setattr(spotify_mod, "validate_credentials", ok_validate)

    r = client.put("/api/settings", json={"spotify_client_id": "cid123",
                                          "spotify_client_secret": "badsecret"})
    assert r.status_code == 400 and "Invalid client secret" in r.json()["detail"]

    r = client.put("/api/settings", json={"spotify_client_id": "cid123",
                                          "spotify_client_secret": "goodsecret456"})
    assert r.status_code == 200
    body = r.json()
    assert body["spotify_configured"] is True
    assert "goodsecret456" not in str(body)  # secret never echoed
    with session_factory()() as db:
        row = db.scalar(select(Setting).where(Setting.key == "spotify_client_secret"))
        assert row.encrypted is True and "goodsecret456" not in (row.value or "")
