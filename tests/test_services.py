def test_service_roster_seeded(client):
    services = client.get("/api/services").json()
    keys = {s["key"] for s in services}
    # Tier 1 + a sample across tiers from Appendix A.
    for expected in ("spotify", "youtube", "apple_music", "trakt", "netflix",
                     "disney_plus", "jiohotstar", "gaana"):
        assert expected in keys
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
