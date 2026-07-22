import json

from app import accounts as accounts_mod
from app.db import session_factory
from app.services import playback
from tests.conftest import run_sync_now

# ---------- Playback routing chain (M3 acceptance criteria) ----------

ENTITY_BOTH = {  # a track available on Spotify and YouTube
    "spotify_id": "trk1", "spotify_uri": "spotify:track:trk1",
    "youtube_video_id": "vid1",
    "links": [
        {"service_key": "spotify", "service_name": "Spotify",
         "url": "https://open.spotify.com/track/trk1", "owned": True},
        {"service_key": "youtube", "service_name": "YouTube",
         "url": "https://www.youtube.com/watch?v=vid1", "owned": False},
    ],
}


def state(**kw):
    base = {"spotify_connected": False, "spotify_premium": False,
            "apple_configured": False, "preferred": "auto"}
    return {**base, **kw}


def test_premium_spotify_wins_chain():
    r = playback.music_options(ENTITY_BOTH, state(spotify_connected=True, spotify_premium=True))
    assert r["default"]["engine"] == "spotify_sdk"


def test_free_spotify_ranks_below_youtube():
    """Accept: YouTube Premium + free Spotify → YouTube default, Spotify still an override."""
    r = playback.music_options(ENTITY_BOTH, state(spotify_connected=True, spotify_premium=False))
    assert r["default"]["engine"] == "youtube"
    engines = [o["engine"] for o in r["options"]]
    assert "spotify_embed" in engines  # 30s preview listed below YouTube
    assert engines.index("youtube") < engines.index("spotify_embed")
    # Every service's link/action is retained — dedupe never hides choice.
    assert any(o["engine"] == "deeplink" and o["service_key"] == "spotify" for o in r["options"])


def test_preferred_pin_outranks_chain():
    r = playback.music_options(ENTITY_BOTH, state(spotify_connected=True, spotify_premium=False,
                                                  preferred="spotify"))
    assert r["default"]["engine"] == "spotify_embed"  # pinned service's best engine
    r2 = playback.music_options(ENTITY_BOTH, state(spotify_connected=True, spotify_premium=True,
                                                   preferred="youtube"))
    assert r2["default"]["engine"] == "youtube"


def test_all_engines_fail_play_becomes_deeplink():
    entity = {"links": [{"service_key": "gaana", "service_name": "Gaana",
                         "url": "https://gaana.com/x", "owned": True}]}
    r = playback.music_options(entity, state())
    assert r["default"]["engine"] == "deeplink"


def test_video_titles_never_get_inapp_engines(client):
    """Accept: Netflix titles never show an in-app play button."""
    run_sync_now()
    shelf = client.get("/api/shelf").json()
    item = shelf["rails"][0]["items"][0]
    title = client.get(f"/api/titles/{item['id']}").json()
    assert all(o["engine"] == "deeplink" for o in title["play"]["options"])


# ---------- Shelf by-service view ----------

def test_shelf_service_view(client):
    run_sync_now()
    services = client.get("/api/services").json()
    netflix = next(s for s in services if s["key"] == "netflix")
    client.put(f"/api/services/{netflix['id']}/subscription", json={"subscribed": True})
    shelf = client.get("/api/shelf", params={"view": "services"}).json()
    labels = [r["label"] for r in shelf["rails"]]
    assert "Netflix" in labels
    assert labels[0] == "Netflix"  # subscribed rails first
    netflix_rail = shelf["rails"][0]
    assert all(any(b["service_key"] == "netflix" for b in i["badges"])
               for i in netflix_rail["items"])


# ---------- Connections & OAuth plumbing (mocked connectors) ----------

def test_connections_endpoint_states(client):
    conns = {c["provider"]: c for c in client.get("/api/connections").json()}
    assert conns["spotify"]["connected"] is False and conns["spotify"]["state"] == "none"
    assert conns["youtube"]["configured"] is False
    assert conns["apple_music"]["configured"] is False


def test_connect_start_requires_app_keys(client):
    r = client.get("/api/connect/youtube/start")
    assert r.status_code == 400 and "API keys" in r.json()["detail"]


def test_oauth_callback_roundtrip(client, monkeypatch):
    from app.providers import spotify as spotify_provider

    async def ok(cid, secret):
        return None

    monkeypatch.setattr(spotify_provider, "validate_credentials", ok)
    client.put("/api/settings", json={"spotify_client_id": "cid", "spotify_client_secret": "sec"})

    monkeypatch.setattr(accounts_mod.spotify.__class__, "auth_url",
                        lambda self, db, s, r: f"https://accounts.spotify.com/authorize?state={s}")
    captured = {}

    def fake_callback(self, db, code, redirect):
        captured["code"] = code
        from app import settings_store
        settings_store.set_setting(db, "spotify_oauth", json.dumps({"access_token": "tok"}))
        settings_store.set_setting(db, "spotify_profile",
                                   json.dumps({"display_name": "Shu", "product": "premium"}))

    monkeypatch.setattr(accounts_mod.spotify.__class__, "handle_callback", fake_callback)
    synced = []
    monkeypatch.setattr(accounts_mod, "schedule_library_sync", lambda p: synced.append(p))

    start = client.get("/api/connect/spotify/start").json()
    state_param = start["url"].split("state=")[1]
    r = client.get(f"/oauth2callback?state={state_param}&code=abc", follow_redirects=False)
    assert r.status_code == 307 and "connected=spotify" in r.headers["location"]
    assert captured["code"] == "abc" and synced == ["spotify"]

    conns = {c["provider"]: c for c in client.get("/api/connections").json()}
    assert conns["spotify"]["connected"] is True
    assert conns["spotify"]["premium"] is True
    # Token bundle is encrypted at rest.
    from sqlalchemy import select

    from app.models import Setting
    with session_factory()() as db:
        row = db.scalar(select(Setting).where(Setting.key == "spotify_oauth"))
        assert row.encrypted is True and "tok" not in (row.value or "")

    # Reusing the state fails (single-use).
    r2 = client.get(f"/oauth2callback?state={state_param}&code=xyz", follow_redirects=False)
    assert "connect_error" in r2.headers["location"]


def test_apple_token_validation(client):
    r = client.put("/api/connections/apple_music/token", json={"token": "not-a-jwt"})
    assert r.status_code == 400

    import base64
    import time
    exp = int(time.time()) + 20 * 86400
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    token = f"eyJhbGciOiJFUzI1NiJ9.{payload}.sig"
    r = client.put("/api/connections/apple_music/token", json={"token": token})
    assert r.status_code == 200
    st = r.json()
    assert st["configured"] is True and st["token_expiring_soon"] is False

    exp_soon = int(time.time()) + 5 * 86400
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp_soon}).encode()).decode().rstrip("=")
    r = client.put("/api/connections/apple_music/token",
                   json={"token": f"eyJhbGciOiJFUzI1NiJ9.{payload}.sig"})
    assert r.json()["token_expiring_soon"] is True  # 14-day warning window


# ---------- Library sync & search integration ----------

def _fake_spotify_library(monkeypatch):
    from app.services import library as lib

    class FakeSpotify:
        key = "spotify"
        name = "Spotify"

        def connected(self, db):
            return True

        def read_likes(self, db):
            return [{"external_id": "t1", "payload": {
                "title": "Giant Steps", "artists": ["John Coltrane"], "album": "Giant Steps",
                "isrc": "USATL0620001", "duration_ms": 285000, "thumb": None,
                "url": "https://open.spotify.com/track/t1", "uri": "spotify:track:t1"}}]

        def read_follows(self, db):
            return [{"external_id": "a1", "payload": {
                "title": "John Coltrane", "thumb": None,
                "url": "https://open.spotify.com/artist/a1", "uri": "spotify:artist:a1"}}]

    monkeypatch.setitem(lib.CONNECTORS, "spotify", FakeSpotify())


def test_library_sync_and_page(client, monkeypatch):
    _fake_spotify_library(monkeypatch)
    from app.services import library as lib
    with session_factory()() as db:
        counts = lib.sync_provider(db, "spotify")
    assert counts == {"likes": 1, "follows": 1}

    data = client.get("/api/library").json()
    keys = {g["key"] for g in data["groups"]}
    assert {"spotify_like", "spotify_follow"} <= keys

    # Re-sync replaces, never duplicates.
    with session_factory()() as db:
        counts = lib.sync_provider(db, "spotify")
    assert counts == {"likes": 1, "follows": 1}
    data = client.get("/api/library").json()
    like_group = next(g for g in data["groups"] if g["key"] == "spotify_like")
    assert like_group["count"] == 1


def test_library_search_group(client, monkeypatch):
    _fake_spotify_library(monkeypatch)
    from app.services import library as lib
    with session_factory()() as db:
        lib.sync_provider(db, "spotify")
    r = client.get("/api/search", params={"q": "giant", "scope": "library"}).json()
    assert r["groups"][0]["label"] == "YOUR LIBRARY"
    row = r["groups"][0]["items"][0]
    assert row["title"] == "Giant Steps"
    assert row["spotify_id"] == "t1"
    assert row["playback"]["options"]  # playback chain attached


def test_auth_expired_marks_reconnect(client, monkeypatch):
    from app.connectors.base import AuthExpired
    from app.services import library as lib

    class ExpiredSpotify:
        key = "spotify"
        name = "Spotify"

        def connected(self, db):
            return True

        def read_likes(self, db):
            raise AuthExpired("spotify")

        def read_follows(self, db):
            return []

    monkeypatch.setitem(lib.CONNECTORS, "spotify", ExpiredSpotify())
    with session_factory()() as db:
        lib.sync_provider(db, "spotify")
    assert lib.sync_state["spotify"]["status"] == "auth"
    assert "Reconnect" in lib.sync_state["spotify"]["detail"]
