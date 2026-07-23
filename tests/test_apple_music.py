"""Apple Music (MusicKit) wiring: developer-token endpoint + playback routing.

The MusicKit *engine* itself is browser-side and untested here; these cover the
backend contract that feeds it.
"""

import json

from app import settings_store
from app.db import session_factory
from app.providers import spotify as spotify_api
from app.services.playback import music_options

_STATE_APPLE = {"spotify_connected": False, "spotify_premium": False,
                "apple_configured": True, "preferred": "auto"}
_STATE_NONE = {**_STATE_APPLE, "apple_configured": False}


def test_resolve_option_when_title_and_service_available():
    # No apple_id / spotify_id (the usual case) → a cross-service "resolve" option
    # carries the metadata so the player finds the best match at play time.
    entity = {"title": "One More Time", "artists": ["Daft Punk"], "links": []}
    routed = music_options(entity, _STATE_APPLE)
    opt = next((o for o in routed["options"] if o["engine"] == "resolve"), None)
    assert opt is not None
    assert opt["payload"]["title"] == "One More Time"
    assert opt["payload"]["artists"] == ["Daft Punk"]
    # No native in-app option → resolve is the default (proactive).
    assert routed["default"]["engine"] == "resolve"


def test_musickit_uses_apple_id_when_known():
    entity = {"apple_id": "12345", "title": "T", "artists": [], "links": []}
    mk = next(o for o in music_options(entity, _STATE_APPLE)["options"]
              if o["engine"] == "musickit")
    assert mk["payload"]["apple_id"] == "12345"


def test_musickit_absent_when_not_configured():
    entity = {"title": "X", "artists": [], "links": []}
    opts = music_options(entity, _STATE_NONE)["options"]
    assert not any(o["engine"] == "musickit" for o in opts)


async def test_resolve_prefers_best_spotify_match(client, monkeypatch):
    # Spotify Premium connected + a catalog hit → resolve returns a spotify_sdk
    # option for the best-matching track.
    with session_factory()() as db:
        settings_store.set_setting(db, "spotify_client_id", "cid")
        settings_store.set_setting(db, "spotify_client_secret", "sec")
        settings_store.set_setting(db, "spotify_oauth", json.dumps({"access_token": "x"}))
        settings_store.set_setting(db, "spotify_profile", json.dumps({"product": "premium"}))

    async def fake_search(cid, secret, query, country):
        return {"tracks": [
            {"title": "One More Time", "artists": ["Daft Punk"], "duration_ms": 320357,
             "spotify_uri": "spotify:track:abc", "isrc": None},
            {"title": "Something Else", "artists": ["Nobody"], "duration_ms": 100000,
             "spotify_uri": "spotify:track:zzz", "isrc": None},
        ]}
    monkeypatch.setattr(spotify_api, "search_catalog", fake_search)

    from app.services import resolve
    with session_factory()() as db:
        opt = await resolve.resolve_playback(db, "One More Time", ["Daft Punk"], 320357)
    assert opt is not None
    assert opt["engine"] == "spotify_sdk"
    assert opt["payload"]["spotify_uri"] == "spotify:track:abc"


def test_apple_token_endpoint(client):
    # Not configured → 400.
    assert client.get("/api/playback/apple/token").status_code == 400
    with session_factory()() as db:
        settings_store.set_setting(db, "apple_developer_token", "dummy.jwt.token")
    r = client.get("/api/playback/apple/token")
    assert r.status_code == 200
    assert r.json()["developer_token"] == "dummy.jwt.token"
