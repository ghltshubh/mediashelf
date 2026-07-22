def test_custom_service_lifecycle(client):
    r = client.post("/api/services", json={
        "name": "Neighborhood Cinema Club", "homepage_url": "https://cinema.example.com",
        "kind": "video",
    })
    assert r.status_code == 201
    created = r.json()
    assert created["custom"] is True
    assert created["subscribed"] is True  # user added it — it's theirs
    assert created["homepage_url"] == "https://cinema.example.com"

    # Appears in the checklist like any other service.
    services = client.get("/api/services").json()
    row = next(s for s in services if s["id"] == created["id"])
    assert row["subscribed"] is True and row["custom"] is True

    # Toggle off and on.
    client.put(f"/api/services/{created['id']}/subscription", json={"subscribed": False})
    services = client.get("/api/services").json()
    assert next(s for s in services if s["id"] == created["id"])["subscribed"] is False

    # Delete works for custom only.
    assert client.delete(f"/api/services/{created['id']}").status_code == 204
    services = client.get("/api/services").json()
    assert all(s["id"] != created["id"] for s in services)


def test_custom_service_key_collision_gets_suffix(client):
    a = client.post("/api/services", json={"name": "My TV", "homepage_url": "https://a.example.com"})
    b = client.post("/api/services", json={"name": "My TV", "homepage_url": "https://b.example.com"})
    assert a.json()["key"] != b.json()["key"]


def test_custom_service_validation(client):
    r = client.post("/api/services", json={"name": " ", "homepage_url": "https://x.example.com"})
    assert r.status_code == 422
    assert client.post("/api/services", json={"name": "X", "homepage_url": "not-a-url"}).status_code == 422
    assert client.post("/api/services", json={"name": "X", "homepage_url": "https://x.example.com",
                                              "kind": "hologram"}).status_code == 422
    # Custom services are video-only: a music marker can't surface tracks.
    music = client.post("/api/services", json={"name": "Gaana", "homepage_url": "https://gaana.com",
                                               "kind": "music"})
    assert music.status_code == 422 and "video-only" in music.json()["detail"]


def test_seeded_service_cannot_be_deleted(client):
    services = client.get("/api/services").json()
    netflix = next(s for s in services if s["key"] == "netflix")
    assert client.delete(f"/api/services/{netflix['id']}").status_code == 400
