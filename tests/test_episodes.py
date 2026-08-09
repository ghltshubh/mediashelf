"""Episode progress — manual marking (issue #2).

Tracking is manual by necessity: MediaShelf deep-links out for TV and never
sees playback. These cover the store (no duplicate rows, no schema change) and
the counting rules that make "where was I" correct.
"""

from app import settings_store
from app.db import session_factory
from app.services import progress
from tests.conftest import run_sync_now


def _set_key(key: str = "testkey") -> None:
    # Set the key directly so the endpoints' guard passes without kicking a
    # background sync (run_sync_now drives the catalog instead).
    with session_factory()() as db:
        settings_store.set_setting(db, "tmdb_api_key", key)


def _tv_id(client) -> int:
    """The show seeded by the fake TMDB fixture (tmdb_id 201)."""
    from app.models import MediaItem

    with session_factory()() as db:
        item = db.query(MediaItem).filter(MediaItem.media_type == "tv").first()
        return item.id


def _movie_id(client) -> int:
    from app.models import MediaItem

    with session_factory()() as db:
        item = db.query(MediaItem).filter(MediaItem.media_type == "movie").first()
        return item.id


# ---------- season list ----------

def test_seasons_drop_specials(client):
    run_sync_now()
    _set_key()
    r = client.get(f"/api/titles/{_tv_id(client)}/seasons")
    assert r.status_code == 200
    data = r.json()
    numbers = [s["season_number"] for s in data["seasons"]]
    # Season 0 exists in the fixture and must not be counted — specials would
    # otherwise make every show permanently unfinished.
    assert numbers == [1, 2]
    assert data["total_episodes"] == 5
    assert data["watched_episodes"] == 0
    assert data["next_up"] == {"season": 1, "episode": 1}
    assert data["complete"] is False


def test_movies_are_rejected(client):
    run_sync_now()
    _set_key()
    r = client.get(f"/api/titles/{_movie_id(client)}/seasons")
    assert r.status_code == 400


def test_unknown_title_404s(client):
    run_sync_now()
    _set_key()
    assert client.get("/api/titles/999999/seasons").status_code == 404


# ---------- marking ----------

def test_mark_and_unmark_single_episode(client):
    run_sync_now()
    _set_key()
    item_id = _tv_id(client)
    r = client.post(f"/api/titles/{item_id}/watched",
                    json={"season": 1, "episodes": [1], "watched": True})
    assert r.status_code == 200
    data = r.json()
    assert data["watched_episodes"] == 1
    assert data["next_up"] == {"season": 1, "episode": 2}

    r = client.post(f"/api/titles/{item_id}/watched",
                    json={"season": 1, "episodes": [1], "watched": False})
    assert r.json()["watched_episodes"] == 0
    assert r.json()["next_up"] == {"season": 1, "episode": 1}


def test_marking_twice_does_not_duplicate_rows(client):
    """LibraryEntry has no unique constraint, so dedupe is ours to enforce."""
    run_sync_now()
    _set_key()
    item_id = _tv_id(client)
    for _ in range(3):
        client.post(f"/api/titles/{item_id}/watched",
                    json={"season": 1, "episodes": [1, 2], "watched": True})
    from app.models import LibraryEntry

    with session_factory()() as db:
        rows = db.query(LibraryEntry).filter(
            LibraryEntry.entry_type == progress.ENTRY_TYPE).all()
        assert len(rows) == 2
    assert client.get(f"/api/titles/{item_id}/seasons").json()["watched_episodes"] == 2


def test_mark_whole_season_in_one_call(client):
    run_sync_now()
    _set_key()
    item_id = _tv_id(client)
    data = client.post(f"/api/titles/{item_id}/watched",
                       json={"season": 1, "episodes": [1, 2, 3], "watched": True}).json()
    assert data["watched_episodes"] == 3
    season1 = next(s for s in data["seasons"] if s["season_number"] == 1)
    assert season1["watched_count"] == 3
    # Next-up rolls into the following season rather than stopping.
    assert data["next_up"] == {"season": 2, "episode": 1}


def test_next_up_finds_a_gap_not_the_highest_marked(client):
    """Someone who skipped an episode is 'on' the gap, not past it."""
    run_sync_now()
    _set_key()
    item_id = _tv_id(client)
    client.post(f"/api/titles/{item_id}/watched",
                json={"season": 1, "episodes": [1, 3], "watched": True})
    assert client.get(f"/api/titles/{item_id}/seasons").json()["next_up"] == {
        "season": 1, "episode": 2}


def test_complete_when_every_episode_marked(client):
    run_sync_now()
    _set_key()
    item_id = _tv_id(client)
    client.post(f"/api/titles/{item_id}/watched",
                json={"season": 1, "episodes": [1, 2, 3], "watched": True})
    data = client.post(f"/api/titles/{item_id}/watched",
                       json={"season": 2, "episodes": [1, 2], "watched": True}).json()
    assert data["complete"] is True
    assert data["next_up"] is None


def test_empty_episode_list_is_rejected(client):
    run_sync_now()
    _set_key()
    r = client.post(f"/api/titles/{_tv_id(client)}/watched",
                    json={"season": 1, "episodes": [], "watched": True})
    assert r.status_code == 422


# ---------- episode list ----------

def test_episode_list_carries_watched_flags(client):
    run_sync_now()
    _set_key()
    item_id = _tv_id(client)
    client.post(f"/api/titles/{item_id}/watched",
                json={"season": 1, "episodes": [2], "watched": True})
    episodes = client.get(f"/api/titles/{item_id}/seasons/1").json()["episodes"]
    assert [e["episode_number"] for e in episodes] == [1, 2, 3]
    assert [e["watched"] for e in episodes] == [False, True, False]


# ---------- clearing ----------

def test_clear_forgets_everything(client):
    run_sync_now()
    _set_key()
    item_id = _tv_id(client)
    client.post(f"/api/titles/{item_id}/watched",
                json={"season": 1, "episodes": [1, 2, 3], "watched": True})
    data = client.delete(f"/api/titles/{item_id}/watched").json()
    assert data["removed"] == 3
    assert data["watched_episodes"] == 0
    assert data["next_up"] == {"season": 1, "episode": 1}


# ---------- show state (the JustWatch buckets) ----------

def test_state_starts_not_started(client):
    run_sync_now()
    _set_key()
    data = client.get(f"/api/titles/{_tv_id(client)}/seasons").json()
    assert data["state"] == "not_started"
    # Fixture: 5 episodes listed, but only up to S2E1 has aired.
    assert data["aired_episodes"] == 4
    assert data["unwatched_aired"] == 4


def test_state_watching_while_aired_episodes_remain(client):
    run_sync_now()
    _set_key()
    data = client.post(f"/api/titles/{_tv_id(client)}/watched",
                       json={"season": 1, "episodes": [1], "watched": True}).json()
    assert data["state"] == "watching"
    assert data["unwatched_aired"] == 3


def test_state_caught_up_when_everything_aired_is_watched(client):
    """Watched all four that exist; S2E2 hasn't aired, so this is caught up,
    not finished — a running show can never be 'seen'."""
    run_sync_now()
    _set_key()
    item_id = _tv_id(client)
    client.post(f"/api/titles/{item_id}/watched",
                json={"season": 1, "episodes": [1, 2, 3], "watched": True})
    data = client.post(f"/api/titles/{item_id}/watched",
                       json={"season": 2, "episodes": [1], "watched": True}).json()
    assert data["state"] == "caught_up"
    assert data["unwatched_aired"] == 0
    assert data["complete"] is False
    assert data["next_air_date"] == "2026-09-01"


def test_unaired_episodes_never_count_as_waiting(client):
    """Marking an unaired episode must not push unwatched_aired negative."""
    run_sync_now()
    _set_key()
    item_id = _tv_id(client)
    client.post(f"/api/titles/{item_id}/watched",
                json={"season": 1, "episodes": [1, 2, 3], "watched": True})
    data = client.post(f"/api/titles/{item_id}/watched",
                       json={"season": 2, "episodes": [1, 2], "watched": True}).json()
    assert data["unwatched_aired"] == 0
    assert data["complete"] is True
    # Show is still running, so complete ≠ seen.
    assert data["state"] == "caught_up"


def test_ended_show_becomes_seen(client):
    run_sync_now()
    _set_key()
    item_id = _tv_id(client)
    from app.models import MediaItem

    client.get(f"/api/titles/{item_id}/seasons")  # cache first, or the fetch overwrites
    with session_factory()() as db:
        item = db.get(MediaItem, item_id)
        item.extra = {**item.extra, "show_status": "Ended", "last_aired": None}
        db.commit()
    client.post(f"/api/titles/{item_id}/watched",
                json={"season": 1, "episodes": [1, 2, 3], "watched": True})
    data = client.post(f"/api/titles/{item_id}/watched",
                       json={"season": 2, "episodes": [1, 2], "watched": True}).json()
    assert data["state"] == "seen"


# ---------- Continue watching rail ----------

def _rail_keys(client) -> list[str]:
    return [r["key"] for r in client.get("/api/shelf?filter=all").json()["rails"]]


def test_continue_watching_rail_absent_until_something_is_marked(client):
    run_sync_now()
    _set_key()
    assert "continue_watching" not in _rail_keys(client)


def test_continue_watching_rail_appears_and_carries_next_up(client):
    run_sync_now()
    _set_key()
    item_id = _tv_id(client)
    client.get(f"/api/titles/{item_id}/seasons")  # caches season data
    client.post(f"/api/titles/{item_id}/watched",
                json={"season": 1, "episodes": [1], "watched": True})
    shelf = client.get("/api/shelf?filter=all").json()
    rail = next(r for r in shelf["rails"] if r["key"] == "continue_watching")
    assert rail["label"] == "Continue watching"
    assert [i["id"] for i in rail["items"]] == [item_id]
    assert rail["items"][0]["next_up"] == {"season": 1, "episode": 2}
    assert rail["items"][0]["unwatched_aired"] == 3


def test_caught_up_show_leaves_the_rail(client):
    """The rail is for shows with something waiting — being up to date on a
    running show is not 'continue watching'."""
    run_sync_now()
    _set_key()
    item_id = _tv_id(client)
    client.get(f"/api/titles/{item_id}/seasons")
    client.post(f"/api/titles/{item_id}/watched",
                json={"season": 1, "episodes": [1, 2, 3], "watched": True})
    assert "continue_watching" in _rail_keys(client)
    client.post(f"/api/titles/{item_id}/watched",
                json={"season": 2, "episodes": [1], "watched": True})
    assert "continue_watching" not in _rail_keys(client)


# ---------- isolation from existing library data ----------

def test_progress_rows_do_not_leak_into_the_watchlist(client):
    """The new entry_type must be invisible to every existing reader."""
    run_sync_now()
    _set_key()
    item_id = _tv_id(client)
    before = client.get("/api/settings").json().get("watchlist_count")
    client.post(f"/api/titles/{item_id}/watched",
                json={"season": 1, "episodes": [1, 2, 3], "watched": True})
    assert client.get("/api/settings").json().get("watchlist_count") == before


def test_started_show_leaves_the_watchlist_rail(client):
    """Same title in Continue watching and Watchlist at once is the confusing
    case — "want to watch" and "part way through" are one list, not two."""
    run_sync_now()
    _set_key()
    item_id = _tv_id(client)
    from app.db import session_factory as sf
    from app.models import LibraryEntry, Service

    with sf()() as db:
        svc = db.query(Service).filter(Service.key == "netflix").first()
        db.add(LibraryEntry(service_id=svc.id, media_item_id=item_id,
                            entry_type="watchlist", external_id="netflix:watchlist:x",
                            payload={"title": "x"}))
        db.commit()

    def rail_ids(key):
        rails = client.get("/api/shelf?filter=all").json()["rails"]
        rail = next((r for r in rails if r["key"] == key), None)
        return [i["id"] for i in rail["items"]] if rail else []

    assert item_id in rail_ids("watchlist")          # saved, not started
    client.get(f"/api/titles/{item_id}/seasons")
    client.post(f"/api/titles/{item_id}/watched",
                json={"season": 1, "episodes": [1], "watched": True})
    assert item_id in rail_ids("continue_watching")  # moved…
    assert item_id not in rail_ids("watchlist")      # …and only there


# ---------- manual watchlist (yours, not the importer's) ----------

def test_manual_watchlist_add_remove(client):
    run_sync_now()
    _set_key()
    item_id = _tv_id(client)
    assert client.get(f"/api/titles/{item_id}").json()["in_watchlist"] is False
    assert client.post(f"/api/titles/{item_id}/watchlist").json()["in_watchlist"] is True
    assert client.get(f"/api/titles/{item_id}").json()["in_watchlist"] is True

    # Idempotent: pressing it twice must not create a second row.
    client.post(f"/api/titles/{item_id}/watchlist")
    from app.models import LibraryEntry
    from app.services.catalog import WATCHLIST_MANUAL

    with session_factory()() as db:
        rows = db.query(LibraryEntry).filter(
            LibraryEntry.entry_type == WATCHLIST_MANUAL).all()
        assert len(rows) == 1

    assert client.delete(f"/api/titles/{item_id}/watchlist").json()["in_watchlist"] is False


def test_manual_watchlist_shows_in_the_rail(client):
    run_sync_now()
    _set_key()
    item_id = _tv_id(client)
    client.post(f"/api/titles/{item_id}/watchlist")
    rails = client.get("/api/shelf?filter=all").json()["rails"]
    rail = next(r for r in rails if r["key"] == "watchlist")
    assert rail["label"] == "Want to watch"
    assert item_id in [i["id"] for i in rail["items"]]


def test_importer_full_sync_cannot_delete_your_own_entries(client):
    """The importer's `replace` pass deletes rows the source list dropped. It
    must not be able to reach something you saved by hand."""
    run_sync_now()
    _set_key()
    item_id = _tv_id(client)
    client.post(f"/api/titles/{item_id}/watchlist")
    r = client.post("/api/watchlist/import",
                    json={"source": "netflix", "items": [], "replace": True,
                          "list_type": "watchlist", "allow_empty": True})
    assert r.status_code == 200
    assert client.get(f"/api/titles/{item_id}").json()["in_watchlist"] is True


# ---------- per-season availability (issue #2's actual ask) ----------

def test_season_availability_reports_the_split(client):
    run_sync_now()
    _set_key()
    data = client.get(f"/api/titles/{_tv_id(client)}/seasons/availability").json()
    assert data["split"] is True
    assert data["any_data"] is True
    groups = data["groups"]
    assert [(g["from"], g["to"]) for g in groups] == [(1, 1), (2, 2)]
    assert [o["service_name"] for o in groups[0]["offers"]] == ["Netflix"]
    # TMDB says "Disney Plus"; it folds onto the seeded service, as elsewhere.
    assert [o["service_name"] for o in groups[1]["offers"]] == ["Disney+"]


def test_consecutive_identical_seasons_fold_into_one_row():
    """Four rows saying Prime Video is noise; "Seasons 1–4" is the point."""
    from app.services.catalog import group_seasons_by_offers

    prime = [{"service_key": "prime_video", "service_name": "Prime Video"}]
    netflix = [{"service_key": "netflix", "service_name": "Netflix"}]
    groups = group_seasons_by_offers([
        {"season_number": 1, "offers": prime},
        {"season_number": 2, "offers": prime},
        {"season_number": 3, "offers": prime},
        {"season_number": 4, "offers": prime},
        {"season_number": 5, "offers": netflix},
    ])
    assert [(g["from"], g["to"]) for g in groups] == [(1, 4), (5, 5)]


def test_non_consecutive_seasons_do_not_fold():
    """S1 and S3 on Prime with S2 elsewhere must not become "seasons 1-3"."""
    from app.services.catalog import group_seasons_by_offers

    prime = [{"service_key": "prime_video", "service_name": "Prime Video"}]
    netflix = [{"service_key": "netflix", "service_name": "Netflix"}]
    groups = group_seasons_by_offers([
        {"season_number": 1, "offers": prime},
        {"season_number": 2, "offers": netflix},
        {"season_number": 3, "offers": prime},
    ])
    assert [(g["from"], g["to"]) for g in groups] == [(1, 1), (2, 2), (3, 3)]


def test_movies_have_no_season_availability(client):
    run_sync_now()
    _set_key()
    assert client.get(
        f"/api/titles/{_movie_id(client)}/seasons/availability").status_code == 400


def test_purchase_only_differences_are_not_a_split(client, monkeypatch):
    """Every season streams on Netflix; only buy options differ. That is not a
    split, and showing the block would just repeat the title-level rows."""
    from app.providers import tmdb as tmdb_mod

    async def providers(self, tv_id, season_number):
        base = {"flatrate": [{"provider_id": 8, "provider_name": "Netflix"}]}
        if season_number == 2:
            base = {**base, "buy": [{"provider_id": 2, "provider_name": "Apple TV"}]}
        return {"US": base}

    monkeypatch.setattr(tmdb_mod.TMDBClient, "season_watch_providers", providers)
    run_sync_now()
    _set_key()
    data = client.get(f"/api/titles/{_tv_id(client)}/seasons/availability").json()
    assert data["any_data"] is True
    assert data["split"] is False
    assert [(g["from"], g["to"]) for g in data["groups"]] == [(1, 2)]
