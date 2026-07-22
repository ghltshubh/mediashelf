from tests.conftest import run_sync_now


def _sync_and_title(client):
    run_sync_now()
    shelf = client.get("/api/shelf").json()
    item = shelf["rails"][0]["items"][0]
    return item["id"]


def test_tmdb_rating_on_cards_and_title(client):
    """TMDB score is free and always present — no OMDb needed."""
    run_sync_now()
    shelf = client.get("/api/shelf").json()
    item = next(i for r in shelf["rails"] for i in r["items"] if i["title"] == "Quiet Orbit")
    assert item["rating"] == 8.4  # from fixture vote_average
    title = client.get(f"/api/titles/{item['id']}").json()
    assert title["rating"] == 8.4
    assert title["ratings"] == {}  # OMDb off → no imdb/rt/metacritic


def test_omdb_enriches_ratings(client, monkeypatch):
    from app.providers import omdb as omdb_mod
    from app.providers import tmdb as tmdb_mod

    async def validate_key(self):
        if self._api_key == "bad":
            raise omdb_mod.OMDbError("OMDb rejected the key")

    async def external_ids(self, media_type, tmdb_id):
        return {"imdb_id": "tt0111161"}

    async def ratings(self, imdb_id):
        return {"imdb": 8.4, "imdb_votes": "1,200,000", "rt": "91%", "metacritic": "82"}

    monkeypatch.setattr(omdb_mod.OMDbClient, "validate_key", validate_key)
    monkeypatch.setattr(omdb_mod.OMDbClient, "ratings", ratings)
    monkeypatch.setattr(tmdb_mod.TMDBClient, "external_ids", external_ids)
    client.put("/api/settings", json={"tmdb_api_key": "goodkey"})  # needed for external_ids

    # Bad key rejected with real error.
    r = client.put("/api/settings", json={"omdb_api_key": "bad"})
    assert r.status_code == 400 and "rejected" in r.json()["detail"]

    r = client.put("/api/settings", json={"omdb_api_key": "goodkey"})
    assert r.status_code == 200 and r.json()["omdb_configured"] is True

    item_id = _sync_and_title(client)
    title = client.get(f"/api/titles/{item_id}").json()
    assert title["ratings"] == {"imdb": 8.4, "imdb_votes": "1,200,000",
                                "rt": "91%", "metacritic": "82"}

    # Cached: a second view doesn't re-fetch (mark ratings_checked).
    calls = {"n": 0}
    orig = ratings

    async def counting(self, imdb_id):
        calls["n"] += 1
        return await orig(self, imdb_id)

    monkeypatch.setattr(omdb_mod.OMDbClient, "ratings", counting)
    client.get(f"/api/titles/{item_id}")
    assert calls["n"] == 0


def test_omdb_secret_encrypted_at_rest(client, monkeypatch):
    from sqlalchemy import select

    from app.db import session_factory
    from app.models import Setting
    from app.providers import omdb as omdb_mod

    async def ok(self):
        return None

    monkeypatch.setattr(omdb_mod.OMDbClient, "validate_key", ok)
    client.put("/api/settings", json={"omdb_api_key": "secretkey123456"})
    with session_factory()() as db:
        row = db.scalar(select(Setting).where(Setting.key == "omdb_api_key"))
        assert row.encrypted is True and "secretkey123456" not in (row.value or "")
