import urllib.parse

from tests.conftest import run_sync_now


def _subscribe(client, key: str, subscribed: bool = True):
    services = client.get("/api/services").json()
    svc = next(s for s in services if s["key"] == key)
    client.put(f"/api/services/{svc['id']}/subscription", json={"subscribed": subscribed})


def test_shelf_after_sync(client):
    run_sync_now()
    shelf = client.get("/api/shelf").json()
    assert shelf["stats"]["titles"] == 3
    rails = {r["key"]: r for r in shelf["rails"]}
    assert [i["title"] for i in rails["movies"]["items"]] == ["The Long Voyage", "Neon Alley"]
    assert [i["title"] for i in rails["shows"]["items"]] == ["Quiet Orbit"]
    # Genre rails appear.
    assert any(k.startswith("genre_") for k in rails)


def test_badges_reflect_checklist(client):
    run_sync_now()
    shelf = client.get("/api/shelf").json()
    voyage = shelf["rails"][0]["items"][0]
    assert voyage["owned"] is False
    assert voyage["unlock_service"] == "Netflix"

    _subscribe(client, "netflix")
    shelf = client.get("/api/shelf").json()
    voyage = shelf["rails"][0]["items"][0]
    assert voyage["owned"] is True
    netflix_badge = next(b for b in voyage["badges"] if b["service_key"] == "netflix")
    assert netflix_badge["owned"] is True
    # Rent-only offers never count as owned.
    rent = next(b for b in voyage["badges"] if b["offer_type"] == "rent")
    assert rent["owned"] is False


def test_deep_links_use_service_template(client):
    run_sync_now()
    shelf = client.get("/api/shelf").json()
    voyage = shelf["rails"][0]["items"][0]
    netflix_badge = next(b for b in voyage["badges"] if b["service_key"] == "netflix")
    q = urllib.parse.quote("The Long Voyage")
    assert netflix_badge["deep_link"] == f"https://www.netflix.com/search?q={q}"


def test_unknown_provider_auto_added_with_tmdb_link_fallback(client):
    run_sync_now()
    services = client.get("/api/services").json()
    fancy = next(s for s in services if s["name"] == "Fancy New Service")
    assert fancy["auto_added"] is True
    shelf = client.get("/api/shelf").json()
    neon = next(i for r in shelf["rails"] for i in r["items"] if i["title"] == "Neon Alley")
    badge = next(b for b in neon["badges"] if b["service_name"] == "Fancy New Service")
    # No template → falls back to TMDB's watch page.
    assert badge["deep_link"].startswith("https://www.themoviedb.org/movie/102/watch")


def test_title_page_groups(client):
    run_sync_now()
    _subscribe(client, "netflix")
    shelf = client.get("/api/shelf").json()
    orbit = next(i for r in shelf["rails"] for i in r["items"] if i["title"] == "Quiet Orbit")
    title = client.get(f"/api/titles/{orbit['id']}").json()
    assert title["overview"] == "Space, slowly."
    on = {b["service_key"] for b in title["on_your_services"]}
    elsewhere = {b["service_key"] for b in title["elsewhere"]}
    assert "netflix" in on
    assert "disney_plus" in elsewhere


def test_media_type_tabs_scope_shelf_and_rails(client):
    run_sync_now()
    movies = client.get("/api/shelf", params={"type": "movie"}).json()
    assert all(i["media_type"] == "movie" for r in movies["rails"] for i in r["items"])
    assert all(r["key"] != "shows" for r in movies["rails"])
    shows = client.get("/api/shelf", params={"type": "tv"}).json()
    assert all(i["media_type"] == "tv" for r in shows["rails"] for i in r["items"])
    # Genre rails are type-scoped too — Drama exists for movies in fixtures.
    drama = client.get("/api/shelf/rail/genre_drama", params={"type": "movie"}).json()
    assert drama["items"] and all(i["media_type"] == "movie" for i in drama["items"])


def test_sync_requires_key(client):
    r = client.post("/api/sync")
    assert r.status_code == 400
    assert "TMDB key" in r.json()["detail"]


def test_tags_and_cast_on_title(client):
    client.put("/api/settings", json={"tmdb_api_key": "goodkey"})  # enrichers need the key
    run_sync_now()
    shelf = client.get("/api/shelf").json()
    mid = next(i["id"] for r in shelf["rails"] if r["key"] == "movies" for i in r["items"])
    t = client.get(f"/api/titles/{mid}").json()
    assert "adventure" in t["keywords"] and "ocean" in t["keywords"]
    assert t["cast"][0] == {"name": "Jane Doe", "character": "Captain",
                            "profile": "https://image.tmdb.org/t/p/w185/jane.jpg"}
    assert t["cast"][1]["profile"] is None  # missing photo → None, no crash


def test_genre_filter_scopes_shelf(client):
    run_sync_now()
    shelf = client.get("/api/shelf").json()
    assert shelf["all_genres"] and all(isinstance(g, str) for g in shelf["all_genres"])
    genre = "Drama"  # The Long Voyage carries genre 18 → Drama (conftest)
    assert genre in shelf["all_genres"]
    filtered = client.get(f"/api/shelf?genre={genre}").json()
    catalog_rails = [r for r in filtered["rails"]
                     if r["key"] in ("movies", "shows") or r["key"].startswith("genre_")]
    assert catalog_rails
    for r in catalog_rails:
        assert all(genre in i["genres"] for i in r["items"])
    # Unknown genre → no catalog rails at all.
    empty = client.get("/api/shelf?genre=Nonexistent").json()
    assert not any(r["key"] in ("movies", "shows") for r in empty["rails"])


def test_sort_reorders_catalog_rails(client):
    run_sync_now()

    def movie_titles(sort: str) -> list[str]:
        shelf = client.get(f"/api/shelf?sort={sort}").json()
        rails = {r["key"]: r for r in shelf["rails"]}
        return [i["title"] for i in rails["movies"]["items"]]

    # Default: TMDB popularity-desc (Long Voyage 90 > Neon Alley 80).
    assert movie_titles("popularity") == ["The Long Voyage", "Neon Alley"]
    # A→Z: case-insensitive title order ("neon" < "the long").
    assert movie_titles("title") == ["Neon Alley", "The Long Voyage"]
    # Newest first: Neon Alley (2024) before The Long Voyage (2023).
    assert movie_titles("year") == ["Neon Alley", "The Long Voyage"]
    # Unknown sort falls back to popularity.
    assert movie_titles("bogus") == ["The Long Voyage", "Neon Alley"]
    # The "see all" browse rail respects sort too.
    r = client.get("/api/shelf/rail/movies?sort=title").json()
    assert [i["title"] for i in r["items"]] == ["Neon Alley", "The Long Voyage"]
