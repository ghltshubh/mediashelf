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
