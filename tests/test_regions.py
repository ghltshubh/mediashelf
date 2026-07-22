import asyncio

from app.db import session_factory
from app.services import catalog


def _sync(countries):
    with session_factory()() as db:
        asyncio.run(catalog.run_sync(db, "testkey", countries[0], countries[1:]))


def test_multi_region_sync_and_switch(client):
    client.put("/api/settings", json={"extra_countries": ["de"]})
    assert client.get("/api/settings").json()["extra_countries"] == ["DE"]
    _sync(["US", "DE"])

    us = client.get("/api/shelf").json()
    assert us["regions"] == ["US", "DE"]
    orbit_us = next(i for r in us["rails"] for i in r["items"] if i["title"] == "Quiet Orbit")
    assert {b["service_key"] for b in orbit_us["badges"]} == {"netflix", "disney_plus"}

    de = client.get("/api/shelf", params={"region": "DE"}).json()
    orbit_de = next(i for r in de["rails"] for i in r["items"] if i["title"] == "Quiet Orbit")
    # Different region, different catalog: WOW (auto-added German provider) only.
    assert {b["service_name"] for b in orbit_de["badges"]} == {"WOW"}

    # Title page region switch too.
    t = client.get(f"/api/titles/{orbit_us['id']}", params={"region": "DE"}).json()
    assert t["country"] == "DE"
    assert {b["service_name"] for b in t["badges"]} == {"WOW"}

    # Untracked region falls back to home, never errors.
    fr = client.get("/api/shelf", params={"region": "FR"}).json()
    assert fr["country"] == "US"


def test_all_regions_aggregate(client):
    client.put("/api/settings", json={"extra_countries": ["DE"]})
    _sync(["US", "DE"])
    services = client.get("/api/services").json()
    netflix = next(s for s in services if s["key"] == "netflix")
    client.put(f"/api/services/{netflix['id']}/subscription", json={"subscribed": True})

    shelf = client.get("/api/shelf", params={"region": "ALL"}).json()
    assert shelf["country"] == "ALL"
    orbit = next(i for r in shelf["rails"] for i in r["items"] if i["title"] == "Quiet Orbit")
    names = {b["service_name"] for b in orbit["badges"]}
    # Home badges plain, other regions tagged; owned = owned anywhere.
    assert "Netflix" in names and "WOW · DE" in names
    assert orbit["owned"] is True

    t = client.get(f"/api/titles/{orbit['id']}", params={"region": "ALL"}).json()
    assert {b["service_name"] for b in t["badges"]} >= {"Netflix", "WOW · DE"}


def test_region_validation_and_prune(client):
    r = client.put("/api/settings", json={"extra_countries": ["EUR"]})
    assert r.status_code == 422

    client.put("/api/settings", json={"extra_countries": ["DE"]})
    _sync(["US", "DE"])
    de = client.get("/api/shelf", params={"region": "DE"}).json()
    assert any(i["badges"] for r_ in de["rails"] for i in r_["items"])

    # Stop tracking DE → next sync prunes its rows.
    client.put("/api/settings", json={"extra_countries": []})
    _sync(["US"])
    de = client.get("/api/shelf", params={"region": "DE"}).json()
    assert de["country"] == "US"  # DE no longer tracked; falls back home
    from sqlalchemy import select

    from app.models import Availability
    with session_factory()() as db:
        assert db.scalar(select(Availability).where(Availability.country == "DE")) is None
