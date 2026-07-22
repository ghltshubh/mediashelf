"""Apple Music (MusicKit) wiring: developer-token endpoint + playback routing.

The MusicKit *engine* itself is browser-side and untested here; these cover the
backend contract that feeds it.
"""

from app import settings_store
from app.db import session_factory
from app.services.playback import music_options

_STATE_APPLE = {"spotify_connected": False, "spotify_premium": False,
                "apple_configured": True, "preferred": "auto"}
_STATE_NONE = {**_STATE_APPLE, "apple_configured": False}


def test_musickit_option_resolves_by_title_when_configured():
    # No apple_id (the usual case) → the option carries title/artists so the
    # engine can resolve the track in Apple's catalog at play time.
    entity = {"title": "One More Time", "artists": ["Daft Punk"], "links": []}
    routed = music_options(entity, _STATE_APPLE)
    mk = next((o for o in routed["options"] if o["engine"] == "musickit"), None)
    assert mk is not None
    assert mk["payload"]["title"] == "One More Time"
    assert mk["payload"]["artists"] == ["Daft Punk"]
    # Only in-app option here → it's the default.
    assert routed["default"]["engine"] == "musickit"


def test_musickit_uses_apple_id_when_known():
    entity = {"apple_id": "12345", "title": "T", "artists": [], "links": []}
    mk = next(o for o in music_options(entity, _STATE_APPLE)["options"]
              if o["engine"] == "musickit")
    assert mk["payload"]["apple_id"] == "12345"


def test_musickit_absent_when_not_configured():
    entity = {"title": "X", "artists": [], "links": []}
    opts = music_options(entity, _STATE_NONE)["options"]
    assert not any(o["engine"] == "musickit" for o in opts)


def test_apple_token_endpoint(client):
    # Not configured → 400.
    assert client.get("/api/playback/apple/token").status_code == 400
    with session_factory()() as db:
        settings_store.set_setting(db, "apple_developer_token", "dummy.jwt.token")
    r = client.get("/api/playback/apple/token")
    assert r.status_code == 200
    assert r.json()["developer_token"] == "dummy.jwt.token"
