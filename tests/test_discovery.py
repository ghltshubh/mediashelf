"""Discovery (More like this + people): recommendation/credit resolution.

Local titles resolve to their page; unknown ones carry an import action.
"""

from app import settings_store
from app.db import session_factory
from tests.conftest import run_sync_now


def _set_key(key: str = "testkey") -> None:
    # Set the key directly so the endpoints' guard passes without kicking a
    # background sync (we drive the catalog with run_sync_now instead).
    with session_factory()() as db:
        settings_store.set_setting(db, "tmdb_api_key", key)


def _movie_id(client, title: str) -> int:
    shelf = client.get("/api/shelf?filter=all").json()
    for rail in shelf["rails"]:
        for it in rail["items"]:
            if it["title"] == title:
                return it["id"]
    raise AssertionError(f"{title} not found in shelf")


def test_similar_resolves_local_and_import(client):
    _set_key()
    run_sync_now()
    vid = _movie_id(client, "The Long Voyage")
    items = client.get(f"/api/titles/{vid}/similar").json()["items"]
    by_title = {i["title"]: i for i in items}
    # Neon Alley is in the catalog → links straight to its page.
    assert by_title["Neon Alley"]["local"] is True
    assert by_title["Neon Alley"]["action"]["type"] == "title"
    # Hidden Gem isn't imported yet → import-on-click.
    assert by_title["Hidden Gem"]["local"] is False
    assert by_title["Hidden Gem"]["action"] == {
        "type": "import", "media_type": "movie", "tmdb_id": 555}


def test_similar_enriches_availability(client):
    _set_key()
    run_sync_now()
    vid = _movie_id(client, "The Long Voyage")
    items = client.get(f"/api/titles/{vid}/similar").json()["items"]
    gem = next(i for i in items if i["title"] == "Hidden Gem")
    # Not imported, but enrichment looked up its providers → shows where it streams.
    assert gem["local"] is False
    assert any(b["service_key"] == "netflix" for b in gem["badges"])


def test_similar_without_key_is_empty(client):
    run_sync_now()  # catalog exists, but no TMDB key set → no recommendations
    vid = _movie_id(client, "The Long Voyage")
    assert client.get(f"/api/titles/{vid}/similar").json()["items"] == []


def test_person_page_lists_credits_with_roles(client):
    _set_key()
    run_sync_now()
    p = client.get("/api/person/500").json()
    assert p["name"] == "Jane Doe"
    assert p["known_for"] == "Acting"
    creds = {c["title"]: c for c in p["credits"]}
    # Local acting role → resolves to the local title.
    assert creds["The Long Voyage"]["local"] is True
    assert creds["The Long Voyage"]["role"] == "Captain"
    # Non-local acting role → import action.
    assert creds["Hidden Gem"]["local"] is False
    assert creds["Hidden Gem"]["action"]["type"] == "import"
    # Directing crew credit is included, labelled with the job.
    assert creds["Quiet Orbit"]["role"] == "Director"


def test_person_requires_key(client):
    assert client.get("/api/person/500").status_code == 400


def test_home_because_rail(client):
    _set_key()
    run_sync_now()
    # No watchlist yet → empty payload, rail stays hidden.
    assert client.get("/api/home/because").json() == {"seed": None, "items": []}
    from app.models import LibraryEntry
    vid = _movie_id(client, "The Long Voyage")
    with session_factory()() as db:
        db.add(LibraryEntry(entry_type="watchlist", media_item_id=vid))
        db.commit()
    r = client.get("/api/home/because").json()
    assert r["seed"] == "The Long Voyage"
    assert any(i["title"] == "Neon Alley" for i in r["items"])


def test_cast_carries_person_id(client):
    _set_key()
    run_sync_now()
    vid = _movie_id(client, "The Long Voyage")
    t = client.get(f"/api/titles/{vid}").json()  # runs ensure_details
    ids = [c["id"] for c in t["cast"]]
    assert 500 in ids and 501 in ids
