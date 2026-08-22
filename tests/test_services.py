def test_dead_services_hidden_after_sync(client):
    from tests.conftest import run_sync_now
    # Before sync the full roster shows (onboarding needs it).
    assert "dazn" in {s["key"] for s in client.get("/api/services").json()}
    run_sync_now()  # populates provider ids for services TMDB reports
    keys = {s["key"] for s in client.get("/api/services").json()}
    # TMDB reported Netflix/Disney (fixtures) → kept; never reported DAZN/ESPN+ and
    # they aren't watchlist/connector/custom → pruned.
    assert "netflix" in keys and "disney_plus" in keys
    assert "dazn" not in keys and "espn_plus" not in keys


def test_service_roster_seeded(client):
    services = client.get("/api/services").json()
    keys = {s["key"] for s in services}
    # Tier 1 + a sample across tiers from Appendix A.
    for expected in ("spotify", "youtube", "apple_music", "trakt", "netflix",
                     "disney_plus", "jiohotstar"):
        assert expected in keys
    # Music with no connector (gaana/tidal) is seeded but kept out of the
    # checklist regardless of sync — ticking it can't surface any music. (Dead
    # video is pruned only post-sync; covered in test_dead_services_hidden.)
    assert "gaana" not in keys and "tidal" not in keys
    spotify = next(s for s in services if s["key"] == "spotify")
    assert spotify["tier"] == 1
    assert spotify["capabilities"]["playback"] == "sdk"
    netflix = next(s for s in services if s["key"] == "netflix")
    assert netflix["capabilities"]["playback"] == "deeplink"


def test_subscription_checklist_toggle(client):
    services = client.get("/api/services").json()
    netflix = next(s for s in services if s["key"] == "netflix")
    assert netflix["subscribed"] is False

    r = client.put(f"/api/services/{netflix['id']}/subscription", json={"subscribed": True})
    assert r.json() == {"id": netflix["id"], "subscribed": True}

    services = client.get("/api/services").json()
    assert next(s for s in services if s["key"] == "netflix")["subscribed"] is True


# ---------- Overseerr / Jellyseerr deep link ----------

def test_request_url_absent_until_configured(client):
    from tests.conftest import run_sync_now
    run_sync_now()
    shelf = client.get("/api/shelf?filter=all").json()
    item_id = shelf["rails"][0]["items"][0]["id"]
    assert client.get(f"/api/titles/{item_id}").json()["request_url"] is None


def test_request_url_is_tmdb_keyed_and_exact(client):
    """Unlike the service deep links (search-URL templates), Overseerr is TMDB
    keyed like us, so this lands on the precise title."""
    from tests.conftest import run_sync_now
    run_sync_now()
    r = client.put("/api/settings", json={"overseerr_url": "http://192.168.1.10:5055/"})
    assert r.status_code == 200
    assert r.json()["overseerr_url"] == "http://192.168.1.10:5055"  # trailing slash trimmed

    shelf = client.get("/api/shelf?filter=all").json()
    item = shelf["rails"][0]["items"][0]
    data = client.get(f"/api/titles/{item['id']}").json()
    assert data["request_url"] == (
        f"http://192.168.1.10:5055/{data['media_type']}/{data['tmdb_id']}")


def test_request_url_rejects_a_bare_host(client):
    r = client.put("/api/settings", json={"overseerr_url": "192.168.1.10:5055"})
    assert r.status_code == 422


def test_request_url_can_be_cleared(client):
    client.put("/api/settings", json={"overseerr_url": "http://seerr.local"})
    assert client.put("/api/settings", json={"overseerr_url": ""}).json()["overseerr_url"] == ""


def test_leaving_soon_is_gone(client):
    """leaving_soon never had a producer — it was removed rather than shipped
    broken. The import endpoint must reject it and titles must not carry it."""
    from tests.conftest import run_sync_now

    run_sync_now()
    r = client.post("/api/watchlist/import", json={
        "source": "netflix", "list_type": "leaving_soon",
        "items": [{"title": "x"}]})
    assert r.status_code == 422

    shelf = client.get("/api/shelf?filter=all").json()
    item_id = shelf["rails"][0]["items"][0]["id"]
    assert "leaving_soon" not in client.get(f"/api/titles/{item_id}").json()


def test_importer_url_defaults_empty_and_validates(client):
    """The companion tool runs on the machine you browse from, not the server,
    so its address can't be assumed — and an unset one shows no link at all."""
    assert client.get("/api/settings").json()["importer_url"] == ""
    assert client.put("/api/settings",
                      json={"importer_url": "127.0.0.1:8765"}).status_code == 422
    r = client.put("/api/settings", json={"importer_url": "http://127.0.0.1:8765/"})
    assert r.json()["importer_url"] == "http://127.0.0.1:8765"
    assert client.put("/api/settings", json={"importer_url": ""}).json()["importer_url"] == ""


def test_oauth_redirect_uri_is_settable_and_validated(client):
    """Unset, the app falls back to 127.0.0.1:8000 — correct on a laptop and
    silently wrong on a NAS, where the provider posts the callback to the
    user's own machine and the server never sees it."""
    s = client.get("/api/settings").json()
    assert s["oauth_redirect_uri"] == ""
    assert s["oauth_redirect_effective"] == "http://127.0.0.1:8000/oauth2callback"

    assert client.put("/api/settings",
                      json={"oauth_redirect_uri": "192.168.1.105:8010/oauth2callback"}
                      ).status_code == 422
    # Providers match the string exactly, so a missing path fails later, not now.
    assert client.put("/api/settings",
                      json={"oauth_redirect_uri": "http://192.168.1.105:8010"}
                      ).status_code == 422

    ok = client.put("/api/settings",
                    json={"oauth_redirect_uri": "http://192.168.1.105:8010/oauth2callback"})
    assert ok.status_code == 200
    assert ok.json()["oauth_redirect_effective"] == "http://192.168.1.105:8010/oauth2callback"

    cleared = client.put("/api/settings", json={"oauth_redirect_uri": ""}).json()
    assert cleared["oauth_redirect_uri"] == ""


def test_spotify_403_is_not_reported_as_an_expired_token(client, monkeypatch):
    """Spotify answers 403 when it bars the app itself from the Web API. The
    token is fine, so 'Reconnect' is the one piece of advice that cannot help."""
    import spotipy

    from app.connectors.base import ProviderRefused
    from app.connectors.spotify import SpotifyConnector

    conn = SpotifyConnector()

    def boom(*a, **kw):
        raise spotipy.SpotifyException(403, -1, "Forbidden")

    monkeypatch.setattr(SpotifyConnector, "_client",
                        lambda self, db, redirect: type("S", (), {
                            "current_user_saved_tracks": staticmethod(boom)})())
    from app.db import session_factory
    with session_factory()() as db:
        try:
            conn.read_likes(db)
        except ProviderRefused as exc:
            assert "Premium" in exc.detail
            assert "econnect" in exc.detail  # says reconnecting won't help
        else:
            raise AssertionError("a 403 should raise ProviderRefused")
