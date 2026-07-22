import pytest
from fastapi.testclient import TestClient

from app import db as app_db
from app.providers import tmdb as tmdb_mod

MOVIES = [
    {"id": 101, "title": "The Long Voyage", "release_date": "2023-06-01",
     "overview": "A ship. An ocean.", "poster_path": "/voyage.jpg",
     "genre_ids": [18], "popularity": 90.0, "vote_average": 7.8},
    {"id": 102, "title": "Neon Alley", "release_date": "2024-02-10",
     "overview": "Crime in the rain.", "poster_path": "/neon.jpg",
     "genre_ids": [80, 18], "popularity": 80.0, "vote_average": 7.1},
]
TV = [
    {"id": 201, "name": "Quiet Orbit", "first_air_date": "2022-09-09",
     "overview": "Space, slowly.", "poster_path": "/orbit.jpg",
     "genre_ids": [10765], "popularity": 95.0, "vote_average": 8.4},
]

PROVIDERS = {
    (101, "movie"): {"US": {
        "link": "https://www.themoviedb.org/movie/101/watch?locale=US",
        "flatrate": [{"provider_id": 8, "provider_name": "Netflix"}],
        "rent": [{"provider_id": 2, "provider_name": "Apple TV"}],
    }},
    (102, "movie"): {"US": {
        "link": "https://www.themoviedb.org/movie/102/watch?locale=US",
        "flatrate": [{"provider_id": 9999, "provider_name": "Fancy New Service"}],
    }},
    (555, "movie"): {"US": {
        "link": "https://www.themoviedb.org/movie/555/watch?locale=US",
        "flatrate": [{"provider_id": 8, "provider_name": "Netflix"}],
        "rent": [{"provider_id": 2, "provider_name": "Apple TV"}],
    }},
    (201, "tv"): {
        "US": {
            "link": "https://www.themoviedb.org/tv/201/watch?locale=US",
            "flatrate": [{"provider_id": 8, "provider_name": "Netflix"},
                         {"provider_id": 337, "provider_name": "Disney Plus"}],
        },
        "DE": {
            "link": "https://www.themoviedb.org/tv/201/watch?locale=DE",
            "flatrate": [{"provider_id": 30, "provider_name": "WOW"}],
        },
    },
}


@pytest.fixture
def fake_tmdb(monkeypatch):
    """Patch TMDBClient network methods with fixture data."""

    async def validate_key(self):
        if self._api_key == "badkey":
            raise tmdb_mod.TMDBError("TMDB rejected the key: Invalid API key")

    async def genres(self, media_type):
        return {18: "Drama", 80: "Crime", 10765: "Sci-Fi & Fantasy"}

    async def titles_list(self, media_type, kind, page=1, region=None):
        if page > 1 or kind != "popular":
            return []
        return MOVIES if media_type == "movie" else TV

    async def popular(self, media_type, page=1, region=None):
        return await titles_list(self, media_type, "popular", page, region)

    async def watch_providers(self, media_type, tmdb_id):
        return PROVIDERS.get((tmdb_id, media_type), {})

    monkeypatch.setattr(tmdb_mod.TMDBClient, "validate_key", validate_key)
    monkeypatch.setattr(tmdb_mod.TMDBClient, "genres", genres)
    monkeypatch.setattr(tmdb_mod.TMDBClient, "titles_list", titles_list)
    monkeypatch.setattr(tmdb_mod.TMDBClient, "popular", popular)
    monkeypatch.setattr(tmdb_mod.TMDBClient, "watch_providers", watch_providers)


@pytest.fixture
def client(tmp_path, monkeypatch, fake_tmdb):
    monkeypatch.setenv("MEDIASHELF_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    app_db.reset_engine_for_tests()
    tmdb_mod.clear_cache()
    from app import api
    from app.main import create_app

    api._sync_task = None

    with TestClient(create_app()) as c:
        yield c
    app_db.reset_engine_for_tests()


def run_sync_now(api_key: str = "testkey", country: str = "US") -> None:
    """Run the catalog sync synchronously against the current test DB."""
    import asyncio

    from app.db import session_factory
    from app.services import catalog

    with session_factory()() as db:
        asyncio.run(catalog.run_sync(db, api_key, country))
