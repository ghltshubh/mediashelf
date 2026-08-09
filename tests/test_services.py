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


def test_leaving_soon_surfaces_on_the_title(client):
    """Watchable today, gone next week — the one case where a request makes
    sense even though a service you pay for still carries it."""
    from app.db import session_factory
    from app.models import LibraryEntry, Service
    from tests.conftest import run_sync_now

    run_sync_now()
    client.put("/api/settings", json={"overseerr_url": "http://seerr.local"})
    shelf = client.get("/api/shelf?filter=all").json()
    item_id = shelf["rails"][0]["items"][0]["id"]
    assert client.get(f"/api/titles/{item_id}").json()["leaving_soon"] is None

    with session_factory()() as db:
        svc = db.query(Service).filter(Service.key == "netflix").first()
        db.add(LibraryEntry(service_id=svc.id, media_item_id=item_id,
                            entry_type="leaving_soon", external_id="netflix:leaving:x",
                            payload={"title": "x", "note": "leaves Aug 31"}))
        db.commit()

    data = client.get(f"/api/titles/{item_id}").json()
    assert data["leaving_soon"] == {"service_name": "Netflix", "note": "leaves Aug 31"}
