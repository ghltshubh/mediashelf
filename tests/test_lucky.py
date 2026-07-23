"""Feeling-lucky dice: random owned pick with genre / type / time-limit scoping.

conftest fixtures: netflix carries The Long Voyage (Drama movie) and Quiet Orbit
(Sci-Fi show); the faked TMDB detail reports 115 min for movies.
"""

from tests.conftest import run_sync_now


def _subscribe(client, key: str):
    services = client.get("/api/services").json()
    svc = next(s for s in services if s["key"] == key)
    client.put(f"/api/services/{svc['id']}/subscription", json={"subscribed": True})


def test_lucky_needs_a_subscription(client):
    run_sync_now()
    assert client.get("/api/lucky").json() == {"found": False}


def test_lucky_scope_all_rolls_beyond_subscriptions(client):
    run_sync_now()
    # No subscriptions at all: default scope finds nothing, "everything" does —
    # and the pick is honestly not-owned.
    r = client.get("/api/lucky?scope=all").json()
    assert r["found"] is True
    assert r["item"]["owned"] is False


def test_lucky_picks_owned_with_filters(client):
    client.put("/api/settings", json={"tmdb_api_key": "goodkey"})
    run_sync_now()
    _subscribe(client, "netflix")

    r = client.get("/api/lucky").json()
    assert r["found"] is True
    assert r["item"]["owned"] is True
    # DRM stays browse-and-link: deep-link options only, never an in-app engine.
    assert r["item"]["play"]["options"]
    assert all(o["engine"] == "deeplink" for o in r["item"]["play"]["options"])

    assert client.get("/api/lucky?genre=Drama").json()["item"]["title"] == "The Long Voyage"
    assert client.get("/api/lucky?type=tv").json()["item"]["title"] == "Quiet Orbit"
    assert client.get("/api/lucky?genre=Nope").json() == {"found": False}


def test_lucky_time_limit_fetches_runtime_lazily(client):
    client.put("/api/settings", json={"tmdb_api_key": "goodkey"})
    run_sync_now()
    _subscribe(client, "netflix")
    # The faked detail says movies run 115 min — none fit under an hour…
    assert client.get("/api/lucky?type=movie&max_minutes=60").json()["found"] is False
    # …but fit under two hours, and the lazily-fetched runtime is persisted.
    r = client.get("/api/lucky?type=movie&max_minutes=120").json()
    assert r["found"] is True
    assert r["item"]["runtime_minutes"] == 115
