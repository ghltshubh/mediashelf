from app.db import session_factory
from app.services.catalog import is_channel_name, resolve_alias_key
from tests.conftest import run_sync_now

KNOWN = {"prime_video", "netflix", "peacock", "apple_tv_plus", "max"}


# ---------- generic service-name folding ----------

def test_tier_variants_fold_to_parent():
    assert resolve_alias_key("Amazon Prime Video Free with Ads", KNOWN) == "prime_video"
    assert resolve_alias_key("Netflix Standard with Ads", KNOWN) == "netflix"
    assert resolve_alias_key("Peacock Premium Plus", KNOWN) == "peacock"
    assert resolve_alias_key("Netflix Kids", KNOWN) == "netflix"
    # No parent known → no fold (stays its own service).
    assert resolve_alias_key("Shahid VIP", KNOWN) is None


def test_channels_are_flagged_not_folded():
    for name in ("Amazon Arthaus Channel", "Animax Amazon Channel",
                 "Apple TV Amazon Channel", "Arthaus+ Apple TV channel",
                 "Paramount+ Roku Premium Channel"):
        assert is_channel_name(name), name
        assert resolve_alias_key(name, KNOWN) is None, name
    assert not is_channel_name("Criterion Channel")  # brand name, not a storefront
    assert not is_channel_name("The Roku Channel")   # service brand exception


def test_services_payload_flags_channels(client):
    run_sync_now()
    from app.models import Service, UserSub

    with session_factory()() as db:
        # Real channels are TMDB-tracked (carry a provider id), so they stay in
        # the checklist — only untracked video with no data source is pruned.
        svc = Service(key="animax_amazon_channel", name="Animax Amazon Channel",
                      kind="video", tier=3, auto_added=True, tmdb_provider_id=88888,
                      capabilities={})
        db.add(svc)
        db.flush()
        db.add(UserSub(service_id=svc.id, subscribed=False))
        db.commit()
    services = client.get("/api/services").json()
    row = next(s for s in services if s["name"] == "Animax Amazon Channel")
    assert row["is_channel"] is True
    assert next(s for s in services if s["key"] == "netflix")["is_channel"] is False


# ---------- watchlist import ----------

def _import(client, items, replace=True, source="netflix"):
    return client.post("/api/watchlist/import", json={
        "source": source, "replace": replace,
        "items": [{"title": t} if isinstance(t, str) else t for t in items],
    })


def test_watchlist_import_and_full_state_sync(client, monkeypatch):
    from app.providers import tmdb as tmdb_mod

    async def search_multi(self, query, page=1):
        table = {
            "the long voyage": [{"media_type": "movie", "id": 101, "title": "The Long Voyage",
                                 "release_date": "2023-06-01", "popularity": 90.0}],
            "quiet orbit": [{"media_type": "tv", "id": 201, "name": "Quiet Orbit",
                             "first_air_date": "2022-09-09", "popularity": 95.0}],
            "totally made up film": [],
        }
        return table.get(query.lower(), [])

    async def detail(self, media_type, tmdb_id):
        return {"id": tmdb_id, "title": "The Long Voyage" if tmdb_id == 101 else None,
                "name": "Quiet Orbit" if tmdb_id == 201 else None,
                "release_date": "2023-06-01", "first_air_date": "2022-09-09",
                "overview": "", "poster_path": None, "genres": [], "popularity": 1.0,
                "vote_average": 7.0}

    monkeypatch.setattr(tmdb_mod.TMDBClient, "search_multi", search_multi)
    monkeypatch.setattr(tmdb_mod.TMDBClient, "detail", detail)
    client.put("/api/settings", json={"tmdb_api_key": "goodkey"})
    run_sync_now()

    r = _import(client, ["The Long Voyage", "Quiet Orbit", "Totally Made Up Film"])
    assert r.status_code == 200
    body = r.json()
    assert body["added"] == 2 and body["unmatched"] == ["Totally Made Up Film"]

    shelf = client.get("/api/shelf", params={"filter": "all"}).json()
    wl = next(rail for rail in shelf["rails"] if rail["key"] == "watchlist")
    assert shelf["rails"][0]["key"] == "watchlist"  # leads the shelf
    assert {i["title"] for i in wl["items"]} == {"The Long Voyage", "Quiet Orbit"}

    # Full-state sync: next import without Quiet Orbit removes it.
    r = _import(client, ["The Long Voyage"]).json()
    assert r["kept"] == 1 and r["removed"] == 1
    shelf = client.get("/api/shelf", params={"filter": "all"}).json()
    wl = next(rail for rail in shelf["rails"] if rail["key"] == "watchlist")
    assert {i["title"] for i in wl["items"]} == {"The Long Voyage"}

    # Browse page for the rail works too.
    rail = client.get("/api/shelf/rail/watchlist").json()
    assert [i["title"] for i in rail["items"]] == ["The Long Voyage"]


def test_resolver_prefers_popular_article_insensitive():
    from app.api import _resolve_best

    results = [
        {"media_type": "movie", "id": 1813, "title": "The Devil's Advocate",
         "release_date": "1997-10-17", "popularity": 8.0},
        {"media_type": "movie", "id": 105483, "title": "Devil's Advocate",
         "release_date": "1995-01-01", "popularity": 1.0},
    ]
    # "Devil's Advocate" (no year) → the popular 1997 "The Devil's Advocate".
    assert _resolve_best(results, "Devil's Advocate", None)["id"] == 1813
    # With an explicit year, the year match wins over popularity.
    assert _resolve_best(results, "Devil's Advocate", 1995)["id"] == 105483
    # No title match → most popular overall.
    assert _resolve_best(results, "Totally Different", None)["id"] == 1813


def test_service_aware_resolution(client, monkeypatch):
    """A 'Ludo' from the Netflix list matches the one ON Netflix, not a
    same-named obscure title that streams elsewhere."""
    import asyncio

    from app.api import _resolve_for_service
    from app.providers import tmdb as tmdb_mod

    results = [
        {"media_type": "movie", "id": 700, "title": "Ludo",
         "release_date": "2021-01-01", "popularity": 12.0},   # obscure, on Tubi
        {"media_type": "movie", "id": 701, "title": "Ludo",
         "release_date": "2020-11-12", "popularity": 9.0},     # Bollywood, on Netflix
    ]

    async def watch_providers(self, media_type, tmdb_id):
        if tmdb_id == 701:
            return {"US": {"flatrate": [{"provider_name": "Netflix"}]}}
        return {"US": {"flatrate": [{"provider_name": "Tubi"}]}}

    monkeypatch.setattr(tmdb_mod.TMDBClient, "watch_providers", watch_providers)
    client_tmdb = tmdb_mod.TMDBClient("k")
    known = {"netflix", "tubi"}
    # From Netflix list → the Netflix one (701), despite lower popularity.
    got = asyncio.run(_resolve_for_service(client_tmdb, results, "Ludo", None, "netflix", "US", known))
    assert got["id"] == 701
    # From Tubi list → the Tubi one (700).
    got = asyncio.run(_resolve_for_service(client_tmdb, results, "Ludo", None, "tubi", "US", known))
    assert got["id"] == 700


def test_watchlist_import_requires_known_service(client):
    client.put("/api/settings", json={"tmdb_api_key": "goodkey"})
    r = _import(client, ["X"], source="nonexistent_service")
    assert r.status_code == 404


def test_top10_and_leaving_rails(client, monkeypatch):
    from app.providers import tmdb as tmdb_mod

    catalog_data = {
        "the long voyage": {"media_type": "movie", "id": 101, "title": "The Long Voyage",
                            "release_date": "2023-06-01", "popularity": 90.0},
        "quiet orbit": {"media_type": "tv", "id": 201, "name": "Quiet Orbit",
                        "first_air_date": "2022-09-09", "popularity": 95.0},
        "neon alley": {"media_type": "movie", "id": 102, "title": "Neon Alley",
                       "release_date": "2024-02-10", "popularity": 80.0},
    }

    async def search_multi(self, query, page=1):
        hit = catalog_data.get(query.lower())
        return [hit] if hit else []

    names = {101: "The Long Voyage", 201: "Quiet Orbit", 102: "Neon Alley"}

    async def detail(self, media_type, tmdb_id):
        return {"id": tmdb_id, "title": names[tmdb_id], "name": names[tmdb_id],
                "release_date": "2023-01-01", "overview": "", "poster_path": None,
                "genres": [], "popularity": 1.0, "vote_average": 7.0}

    monkeypatch.setattr(tmdb_mod.TMDBClient, "search_multi", search_multi)
    monkeypatch.setattr(tmdb_mod.TMDBClient, "detail", detail)
    client.put("/api/settings", json={"tmdb_api_key": "goodkey"})
    run_sync_now()

    # Top 10 on Netflix (Long Voyage #1) and Tubi (Neon Alley #1, Long Voyage #2).
    client.post("/api/watchlist/import", json={
        "source": "netflix", "list_type": "top10",
        "items": [{"title": "The Long Voyage", "rank": 1}, {"title": "Neon Alley", "rank": 2}],
    })
    client.post("/api/watchlist/import", json={
        "source": "tubi", "list_type": "top10",
        "items": [{"title": "Neon Alley", "rank": 1}, {"title": "The Long Voyage", "rank": 2}],
    })
    # Leaving soon stays per-service.
    client.post("/api/watchlist/import", json={
        "source": "tubi", "list_type": "leaving_soon",
        "items": [{"title": "Quiet Orbit", "note": "leaves Jul 31"}],
    })

    shelf = client.get("/api/shelf", params={"filter": "all"}).json()
    rails = {r["key"]: r for r in shelf["rails"]}
    # One aggregated "Popular right now" rail — no per-service top10 rails.
    assert "popular" in rails
    assert not any(k.startswith("top10_") for k in rails)
    assert rails["popular"]["label"] == "Popular right now"
    # Both titles trend on 2 services → both appear, deduped; Long Voyage best
    # rank 1 (Netflix) beats Neon Alley best rank 1 (Tubi) — tie, so order by
    # service count (equal) then best rank (equal) then insertion.
    pop_titles = {i["title"] for i in rails["popular"]["items"]}
    assert pop_titles == {"The Long Voyage", "Neon Alley"}
    assert len(rails["popular"]["items"]) == 2  # deduped across services
    assert "leaving_tubi" in rails and rails["leaving_tubi"]["label"] == "Leaving Tubi soon"

    # "see all" browse pages resolve for these rails.
    assert client.get("/api/shelf/rail/popular").status_code == 200
    assert client.get("/api/shelf/rail/leaving_tubi").json()["label"] == "Leaving Tubi soon"
