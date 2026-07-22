"""Spotify connector (Tier 1): OAuth via spotipy, library reads, SDK token.

Uses the user's own app credentials (M2's client id/secret). Tokens live
encrypted in the Setting table via a spotipy CacheHandler.
"""

import json
import logging
from typing import Any

import spotipy
from spotipy.cache_handler import CacheHandler
from spotipy.oauth2 import SpotifyOAuth
from sqlalchemy.orm import Session

from app import settings_store
from app.connectors.base import AuthExpired, NotConnected

logger = logging.getLogger(__name__)

SCOPES = ("user-library-read user-follow-read "
          "user-library-modify user-follow-modify streaming "
          "user-read-email user-read-private "
          "user-read-playback-state user-modify-playback-state")

DEFAULT_REDIRECT = "http://127.0.0.1:8000/oauth2callback"


def _resolve_redirect(db: Session, redirect_uri: str) -> str:
    return (redirect_uri
            or settings_store.get_setting(db, "oauth_redirect_uri")
            or DEFAULT_REDIRECT)


class _SettingCache(CacheHandler):
    def __init__(self, db: Session, key: str = "spotify_oauth"):
        self.db = db
        self.key = key

    def get_cached_token(self) -> dict | None:
        raw = settings_store.get_setting(self.db, self.key)
        return json.loads(raw) if raw else None

    def save_token_to_cache(self, token_info: dict) -> None:
        settings_store.set_setting(self.db, self.key, json.dumps(token_info))


class SpotifyConnector:
    key = "spotify"
    name = "Spotify"

    def __init__(self, slot: str = "primary") -> None:
        # The "secondary" slot is a second account used ONLY for account-to-account
        # migration: it reads/writes a parallel set of settings keys (…_2) and never
        # touches shelf/library/playback (those use the primary singleton).
        self.slot = slot
        self._suffix = "" if slot == "primary" else "_2"

    def _k(self, base: str) -> str:
        return base + self._suffix

    def capabilities(self) -> dict:
        return {"catalog": True, "user_library": True, "write_likes": True,
                "write_follows": True, "playback": "sdk"}

    def _oauth(self, db: Session, redirect_uri: str = "") -> SpotifyOAuth:
        cid = settings_store.get_setting(db, "spotify_client_id")
        secret = settings_store.get_setting(db, "spotify_client_secret")
        if not (cid and secret):
            raise NotConnected("spotify")
        return SpotifyOAuth(client_id=cid, client_secret=secret,
                            redirect_uri=_resolve_redirect(db, redirect_uri),
                            scope=SCOPES, cache_handler=_SettingCache(db, self._k("spotify_oauth")),
                            open_browser=False)

    def configured(self, db: Session) -> bool:
        # App credentials are shared across both accounts (same Spotify app).
        return bool(settings_store.get_setting(db, "spotify_client_id")
                    and settings_store.get_setting(db, "spotify_client_secret"))

    def connected(self, db: Session) -> bool:
        return settings_store.get_setting(db, self._k("spotify_oauth")) is not None

    def auth_url(self, db: Session, state: str, redirect_uri: str) -> str:
        return self._oauth(db, redirect_uri).get_authorize_url(state=state)

    def handle_callback(self, db: Session, code: str, redirect_uri: str) -> None:
        oauth = self._oauth(db, redirect_uri)
        oauth.get_access_token(code, as_dict=False, check_cache=False)  # cache handler persists
        settings_store.set_setting(db, self._k("spotify_auth_error"), None)
        me = spotipy.Spotify(auth=self._access_token(db, redirect_uri)).me()
        settings_store.set_setting(db, self._k("spotify_profile"), json.dumps({
            "display_name": me.get("display_name"),
            "id": me.get("id"),
            "product": me.get("product"),  # "premium" | "free" | ...
        }))

    def disconnect(self, db: Session) -> None:
        for k in ("spotify_oauth", "spotify_profile", "spotify_auth_error"):
            settings_store.set_setting(db, self._k(k), None)

    def _access_token(self, db: Session, redirect_uri: str) -> str:
        oauth = self._oauth(db, redirect_uri)
        cache = _SettingCache(db, self._k("spotify_oauth"))
        token_info = cache.get_cached_token()
        if not token_info:
            raise NotConnected("spotify")
        try:
            token_info = oauth.validate_token(token_info)  # refreshes if expired
        except Exception as exc:
            settings_store.set_setting(db, self._k("spotify_auth_error"), "true")
            raise AuthExpired("spotify") from exc
        if not token_info:
            settings_store.set_setting(db, self._k("spotify_auth_error"), "true")
            raise AuthExpired("spotify")
        return token_info["access_token"]

    def playback_token(self, db: Session, redirect_uri: str) -> str:
        """Fresh access token for the Web Playback SDK (browser side)."""
        return self._access_token(db, redirect_uri)

    def _client(self, db: Session, redirect_uri: str) -> spotipy.Spotify:
        return spotipy.Spotify(auth=self._access_token(db, redirect_uri))

    def status(self, db: Session) -> dict:
        profile = settings_store.get_setting(db, self._k("spotify_profile"))
        p = json.loads(profile) if profile else {}
        expired = settings_store.get_setting(db, self._k("spotify_auth_error")) == "true"
        return {
            "provider": "spotify",
            "name": "Spotify",
            "configured": self.configured(db),
            "connected": self.connected(db),
            "state": "expired" if expired else ("ok" if self.connected(db) else "none"),
            "profile": p.get("display_name") or p.get("id"),
            "premium": p.get("product") == "premium",
            "adds": "play full tracks in-app · sync liked songs & followed artists",
            "requires": "your Spotify API keys (already set)" if self.configured(db)
                        else "your own free Spotify app keys — Settings → Keys",
        }

    def read_likes(self, db: Session, redirect_uri: str = "") -> list[dict[str, Any]]:
        sp = self._client(db, redirect_uri)
        out: list[dict] = []
        results = sp.current_user_saved_tracks(limit=50)
        while results:
            for row in results["items"]:
                t = row["track"]
                if not t:
                    continue
                out.append({
                    "external_id": t["id"],
                    "payload": {
                        "title": t["name"],
                        "artists": [a["name"] for a in t.get("artists", [])],
                        "album": (t.get("album") or {}).get("name"),
                        "isrc": (t.get("external_ids") or {}).get("isrc"),
                        "duration_ms": t.get("duration_ms"),
                        "thumb": ((t.get("album") or {}).get("images") or [{}])[-1].get("url"),
                        "url": (t.get("external_urls") or {}).get("spotify"),
                        "uri": t.get("uri"),
                    },
                })
            results = sp.next(results) if results.get("next") else None
        return out

    # ---------- M5: matching + writes ----------

    def account_id(self, db: Session) -> str | None:
        profile = settings_store.get_setting(db, self._k("spotify_profile"))
        return json.loads(profile).get("id") if profile else None

    def search_track(self, db: Session, title: str, artists: list[str]) -> list[dict]:
        sp = self._client(db, "")
        q = f"track:{title}"
        if artists:
            q += f" artist:{artists[0]}"
        results = sp.search(q=q, type="track", limit=5)
        out = []
        for t in (results.get("tracks") or {}).get("items", []):
            out.append({
                "title": t["name"],
                "artists": [a["name"] for a in t.get("artists", [])],
                "duration_ms": t.get("duration_ms"),
                "isrc": (t.get("external_ids") or {}).get("isrc"),
                "external_id": t["id"],
                "url": (t.get("external_urls") or {}).get("spotify"),
                "service": "spotify",
            })
        return out

    def search_artist(self, db: Session, name: str) -> list[dict]:
        sp = self._client(db, "")
        results = sp.search(q=name, type="artist", limit=5)
        return [{
            "title": a["name"], "artists": [], "external_id": a["id"],
            "url": (a.get("external_urls") or {}).get("spotify"), "service": "spotify",
        } for a in (results.get("artists") or {}).get("items", [])]

    def add_like(self, db: Session, track_id: str) -> str:
        """→ 'added' | 'already'."""
        sp = self._client(db, "")
        if sp.current_user_saved_tracks_contains([track_id])[0]:
            return "already"
        sp.current_user_saved_tracks_add([track_id])
        return "added"

    def remove_like(self, db: Session, track_id: str) -> None:
        self._client(db, "").current_user_saved_tracks_delete([track_id])

    def follow(self, db: Session, artist_id: str) -> str:
        sp = self._client(db, "")
        if sp.current_user_following_artists([artist_id])[0]:
            return "already"
        sp.user_follow_artists([artist_id])
        return "added"

    def unfollow(self, db: Session, artist_id: str) -> None:
        self._client(db, "").user_unfollow_artists([artist_id])

    def read_follows(self, db: Session, redirect_uri: str = "") -> list[dict[str, Any]]:
        sp = self._client(db, redirect_uri)
        out: list[dict] = []
        results = sp.current_user_followed_artists(limit=50)
        while results:
            artists = results["artists"]
            for a in artists["items"]:
                out.append({
                    "external_id": a["id"],
                    "payload": {
                        "title": a["name"],
                        "thumb": (a.get("images") or [{}])[-1].get("url"),
                        "url": (a.get("external_urls") or {}).get("spotify"),
                        "uri": a.get("uri"),
                    },
                })
            results = sp.next(artists) if artists.get("next") else None
        return out
