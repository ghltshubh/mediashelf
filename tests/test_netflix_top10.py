"""Netflix published Top 10 → "Popular right now" with zero tooling.

The provider streams Netflix's open Tudum TSV and keeps only the latest week
for tracked countries; run_sync feeds the result through the shared import
pipeline. These tests stub the one network seam (`_fetch`) with real-shaped
TSV lines — the file format is Netflix's, so a live fetch is checked manually,
not here.
"""

from app.providers import netflix_top10
from tests.conftest import run_sync_now

HEADER = ("country_name\tcountry_iso2\tweek\tcategory\tweekly_rank\t"
          "show_title\tseason_title\tcumulative_weeks_in_top_10")

TSV_LINES = [
    HEADER,
    # An older week that must be ignored even though it comes first.
    "United States\tUS\t2026-07-26\tFilms\t1\tOld News\t\t3",
    # Latest week, US: one film, one show.
    "United States\tUS\t2026-08-02\tFilms\t1\tThe Long Voyage\t\t2",
    "United States\tUS\t2026-08-02\tTV\t2\tQuiet Orbit\tQuiet Orbit: Season 1\t5",
    # Latest week, untracked country: must be dropped.
    "France\tFR\t2026-08-02\tFilms\t1\tFilm Français\t\t1",
    # Same title charting in a second tracked country at a worse rank —
    # deduped, best rank wins.
    "Canada\tCA\t2026-08-02\tFilms\t4\tThe Long Voyage\t\t2",
    "",  # trailing blank line, as the real file has
]


async def _lines():
    for line in TSV_LINES:
        yield line


def _patch_fetch(monkeypatch, status=200, last_modified="Tue, 04 Aug 2026 12:00:00 GMT"):
    calls = []

    async def fetch(prev):
        calls.append(prev)
        return status, last_modified, _lines()

    monkeypatch.setattr(netflix_top10, "_fetch", fetch)
    return calls


def test_latest_week_for_tracked_countries_only(client, monkeypatch):
    from app.db import session_factory

    _patch_fetch(monkeypatch)
    import asyncio
    with session_factory()() as db:
        items = asyncio.run(netflix_top10.latest_top10(db, ["US", "CA"]))
    assert items == [{"title": "The Long Voyage", "rank": 1},
                     {"title": "Quiet Orbit", "rank": 2}]

    # The validator is stored so the next nightly fetch can 304.
    with session_factory()() as db:
        from app import settings_store
        assert settings_store.get_setting(db, netflix_top10.LAST_MODIFIED_SETTING) \
            == "Tue, 04 Aug 2026 12:00:00 GMT"
        assert settings_store.get_setting(db, netflix_top10.FETCHED_AT_SETTING)


def test_304_is_a_no_op(client, monkeypatch):
    from app.db import session_factory

    _patch_fetch(monkeypatch, status=304)
    import asyncio
    with session_factory()() as db:
        assert asyncio.run(netflix_top10.latest_top10(db, ["US"])) is None


def test_unchanged_last_modified_aborts_without_reading(client, monkeypatch):
    """Netflix's CDN ignores If-Modified-Since (verified live), so an unchanged
    Last-Modified on a 200 must act as the 304: abort before the 31 MB body."""
    import asyncio

    from app import settings_store
    from app.db import session_factory

    consumed = []

    async def lines():
        consumed.append(True)
        yield HEADER

    async def fetch(prev):
        return 200, "Tue, 04 Aug 2026 12:00:00 GMT", lines()

    monkeypatch.setattr(netflix_top10, "_fetch", fetch)
    with session_factory()() as db:
        settings_store.set_setting(db, netflix_top10.LAST_MODIFIED_SETTING,
                                   "Tue, 04 Aug 2026 12:00:00 GMT")
        assert asyncio.run(netflix_top10.latest_top10(db, ["US"])) is None
    assert not consumed  # the body was never read


def test_sync_fills_popular_rail_from_published_data(client, monkeypatch):
    """A stock install with only a TMDB key gets "Popular right now" after one
    sync — the whole point of moving off the deleted tooling."""
    from app.providers import tmdb as tmdb_mod

    catalog_data = {
        "the long voyage": {"media_type": "movie", "id": 101, "title": "The Long Voyage",
                            "release_date": "2023-06-01", "popularity": 90.0},
        "quiet orbit": {"media_type": "tv", "id": 201, "name": "Quiet Orbit",
                        "first_air_date": "2022-09-09", "popularity": 95.0},
    }

    async def search_multi(self, query, page=1):
        hit = catalog_data.get(query.lower())
        return [hit] if hit else []

    monkeypatch.setattr(tmdb_mod.TMDBClient, "search_multi", search_multi)
    _patch_fetch(monkeypatch)
    client.put("/api/settings", json={"tmdb_api_key": "goodkey"})
    run_sync_now()

    shelf = client.get("/api/shelf", params={"filter": "all"}).json()
    rails = {r["key"]: r for r in shelf["rails"]}
    assert "popular" in rails
    titles = [i["title"] for i in rails["popular"]["items"]]
    assert titles[0] == "The Long Voyage"  # rank 1 leads

    # Ranks landed in payloads — without them the rail order degenerates.
    from app.db import session_factory
    from app.models import LibraryEntry
    with session_factory()() as db:
        entries = db.query(LibraryEntry).filter(LibraryEntry.entry_type == "top10").all()
        assert {(e.payload["title"], e.payload["rank"]) for e in entries} \
            == {("The Long Voyage", 1), ("Quiet Orbit", 2)}


def test_empty_week_never_clears_the_rail(client, monkeypatch):
    """Tracked country absent from the dataset → [] → run_sync must skip the
    import entirely rather than full-state-sync the list down to nothing."""
    from app.db import session_factory
    from app.models import LibraryEntry, Service

    run_sync_now()
    with session_factory()() as db:
        svc = db.query(Service).filter(Service.key == "netflix").first()
        db.add(LibraryEntry(service_id=svc.id, media_item_id=None,
                            entry_type="top10", external_id="netflix:top10:held:",
                            payload={"title": "held", "rank": 1}))
        db.commit()

    async def fetch(prev):
        async def lines():
            yield HEADER
            yield "France\tFR\t2026-08-02\tFilms\t1\tFilm Français\t\t1"
        return 200, "Tue, 04 Aug 2026 12:00:00 GMT", lines()

    monkeypatch.setattr(netflix_top10, "_fetch", fetch)
    run_sync_now()  # tracked country is US → zero matching rows

    with session_factory()() as db:
        assert db.query(LibraryEntry).filter(
            LibraryEntry.entry_type == "top10").count() == 1
