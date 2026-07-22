"""YouTube connector (Tier 1): OAuth via google-auth-oauthlib, library reads.

Read-only in M3 (youtube.readonly scope): subscriptions + liked videos.
Reads are quota-cheap (1 unit/page). The user supplies their own Google Cloud
OAuth client (per-user keys, Appendix B).
"""

import json
import logging
import re
from typing import Any

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy.orm import Session

from app import settings_store
from app.connectors.base import AuthExpired, NotConnected, QuotaExhausted
from app.providers import ytdlp_meta

logger = logging.getLogger(__name__)

# Read/write from the start (M5 migrations write likes + subscriptions).
SCOPES = ["https://www.googleapis.com/auth/youtube"]

_QUOTA_REASONS = {"quotaExceeded", "rateLimitExceeded", "userRateLimitExceeded",
                  "dailyLimitExceeded"}


def _reason(err: HttpError) -> str:
    try:
        for d in (err.error_details or []):
            if d.get("reason"):
                return d["reason"]
    except Exception:
        pass
    return ""


def _translate(err: HttpError) -> Exception:
    reason = _reason(err)
    if reason in _QUOTA_REASONS:
        return QuotaExhausted("youtube", reason)
    if err.resp.status in (401, 403) and reason in ("authError", "forbidden"):
        return AuthExpired("youtube")
    return err


def _iso8601_ms(duration: str) -> int | None:
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration or "")
    if not m:
        return None
    h, mnt, s = (int(g) if g else 0 for g in m.groups())
    return (h * 3600 + mnt * 60 + s) * 1000


class YouTubeConnector:
    key = "youtube"
    name = "YouTube"

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
                "write_follows": True, "playback": "embed"}

    def _client_config(self, db: Session) -> dict:
        cid = settings_store.get_setting(db, "google_client_id")
        secret = settings_store.get_setting(db, "google_client_secret")
        if not (cid and secret):
            raise NotConnected("youtube")
        return {"web": {
            "client_id": cid,
            "client_secret": secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }}

    def configured(self, db: Session) -> bool:
        return bool(settings_store.get_setting(db, "google_client_id")
                    and settings_store.get_setting(db, "google_client_secret"))

    def connected(self, db: Session) -> bool:
        return settings_store.get_setting(db, self._k("youtube_oauth")) is not None

    def auth_url(self, db: Session, state: str, redirect_uri: str) -> str:
        flow = Flow.from_client_config(self._client_config(db), scopes=SCOPES,
                                       redirect_uri=redirect_uri)
        url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            # select_account per plan; consent guarantees a refresh token
            prompt="consent select_account",
            state=state,
        )
        # google-auth-oauthlib enables PKCE by default: authorization_url()
        # generates a code_verifier that the token exchange must echo back. The
        # callback builds a fresh Flow, so persist the verifier for it — else
        # Google rejects the exchange with "invalid_grant: Missing code verifier".
        if flow.code_verifier:
            settings_store.set_setting(db, self._k("youtube_oauth_verifier"), flow.code_verifier)
        return url

    def handle_callback(self, db: Session, code: str, redirect_uri: str) -> None:
        flow = Flow.from_client_config(self._client_config(db), scopes=SCOPES,
                                       redirect_uri=redirect_uri)
        verifier = settings_store.get_setting(db, self._k("youtube_oauth_verifier"))
        if verifier:
            flow.code_verifier = verifier
        flow.fetch_token(code=code)
        settings_store.set_setting(db, self._k("youtube_oauth_verifier"), None)  # one-time use
        creds = flow.credentials
        settings_store.set_setting(db, self._k("youtube_oauth"), creds.to_json())
        settings_store.set_setting(db, self._k("youtube_auth_error"), None)
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        chans = yt.channels().list(part="snippet", mine=True).execute()
        items = chans.get("items", [])
        if items:
            settings_store.set_setting(db, self._k("youtube_profile"), json.dumps({
                "title": items[0]["snippet"]["title"],
                "id": items[0]["id"],
            }))

    def disconnect(self, db: Session) -> None:
        for k in ("youtube_oauth", "youtube_profile", "youtube_auth_error",
                  "youtube_oauth_verifier"):
            settings_store.set_setting(db, self._k(k), None)

    def _creds(self, db: Session) -> Credentials:
        raw = settings_store.get_setting(db, self._k("youtube_oauth"))
        if not raw:
            raise NotConnected("youtube")
        creds = Credentials.from_authorized_user_info(json.loads(raw), scopes=SCOPES)
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                settings_store.set_setting(db, self._k("youtube_oauth"), creds.to_json())
            except RefreshError as exc:
                settings_store.set_setting(db, self._k("youtube_auth_error"), "true")
                raise AuthExpired("youtube") from exc
        return creds

    def _yt(self, db: Session):
        return build("youtube", "v3", credentials=self._creds(db), cache_discovery=False)

    def status(self, db: Session) -> dict:
        profile = settings_store.get_setting(db, self._k("youtube_profile"))
        p = json.loads(profile) if profile else {}
        expired = settings_store.get_setting(db, self._k("youtube_auth_error")) == "true"
        return {
            "provider": "youtube",
            "name": "YouTube",
            "configured": self.configured(db),
            "connected": self.connected(db),
            "state": "expired" if expired else ("ok" if self.connected(db) else "none"),
            "profile": p.get("title"),
            "premium": False,
            "adds": "sync your subscriptions & liked videos",
            "requires": "your own Google Cloud OAuth client — free, ~5 min, guided below",
        }

    # ---------- M5: matching + writes ----------

    def account_id(self, db: Session) -> str | None:
        profile = settings_store.get_setting(db, self._k("youtube_profile"))
        return json.loads(profile).get("id") if profile else None

    def search_track(self, db: Session, title: str, artists: list[str]) -> list[dict]:
        """search.list costs 100 units — the expensive read. When the yt-dlp
        toggle is on (M6) this runs at zero quota; yt-dlp errors degrade silently
        to the official API. Music category, small page, durations batched."""
        q = f"{artists[0]} {title}" if artists else title
        if ytdlp_meta.active(db):
            try:
                return ytdlp_meta.search_music(q)
            except ytdlp_meta.YtDlpError:
                pass  # degrade to the official API below
        yt = self._yt(db)
        try:
            resp = yt.search().list(part="snippet", q=q, type="video",
                                    videoCategoryId="10", maxResults=5).execute()
            ids = [i["id"]["videoId"] for i in resp.get("items", [])]
            durations: dict[str, int | None] = {}
            if ids:
                vids = yt.videos().list(part="contentDetails", id=",".join(ids)).execute()
                for v in vids.get("items", []):
                    durations[v["id"]] = _iso8601_ms(v["contentDetails"].get("duration", ""))
        except HttpError as err:
            raise _translate(err) from err
        out = []
        for item in resp.get("items", []):
            vid = item["id"]["videoId"]
            channel = item["snippet"].get("channelTitle", "")
            out.append({
                "title": item["snippet"]["title"],
                "artists": [channel.removesuffix(" - Topic").strip()] if channel else [],
                "duration_ms": durations.get(vid),
                "external_id": vid,
                "url": f"https://music.youtube.com/watch?v={vid}",
                "thumb": (item["snippet"].get("thumbnails", {}).get("default") or {}).get("url"),
                "service": "youtube_music",
            })
        return out

    def search_channel(self, db: Session, name: str) -> list[dict]:
        if ytdlp_meta.active(db):
            try:
                return ytdlp_meta.search_channel(name)
            except ytdlp_meta.YtDlpError:
                pass  # degrade to the official API below
        yt = self._yt(db)
        try:
            resp = yt.search().list(part="snippet", q=name, type="channel",
                                    maxResults=5).execute()
        except HttpError as err:
            raise _translate(err) from err
        return [{
            "title": i["snippet"]["title"], "artists": [],
            "external_id": i["id"]["channelId"],
            "url": f"https://www.youtube.com/channel/{i['id']['channelId']}",
            "service": "youtube",
        } for i in resp.get("items", [])]

    def add_like(self, db: Session, video_id: str) -> str:
        """videos.rate — 50 quota units. → 'added' | 'already'."""
        yt = self._yt(db)
        try:
            rating = yt.videos().getRating(id=video_id).execute()
            items = rating.get("items", [])
            if items and items[0].get("rating") == "like":
                return "already"
            yt.videos().rate(id=video_id, rating="like").execute()
        except HttpError as err:
            raise _translate(err) from err
        return "added"

    def remove_like(self, db: Session, video_id: str) -> None:
        try:
            self._yt(db).videos().rate(id=video_id, rating="none").execute()
        except HttpError as err:
            raise _translate(err) from err

    def follow(self, db: Session, channel_id: str) -> str:
        """subscriptions.insert — 50 units. subscriptionDuplicate = success."""
        yt = self._yt(db)
        try:
            yt.subscriptions().insert(part="snippet", body={
                "snippet": {"resourceId": {"kind": "youtube#channel",
                                           "channelId": channel_id}},
            }).execute()
        except HttpError as err:
            if _reason(err) == "subscriptionDuplicate":
                return "already"
            raise _translate(err) from err
        return "added"

    def unfollow(self, db: Session, channel_id: str) -> None:
        yt = self._yt(db)
        try:
            resp = yt.subscriptions().list(part="id", forChannelId=channel_id,
                                           mine=True).execute()
            for item in resp.get("items", []):
                yt.subscriptions().delete(id=item["id"]).execute()
        except HttpError as err:
            raise _translate(err) from err

    def read_follows(self, db: Session) -> list[dict[str, Any]]:
        yt = self._yt(db)
        out: list[dict] = []
        req = yt.subscriptions().list(part="snippet", mine=True, maxResults=50)
        while req is not None:
            resp = req.execute()
            for item in resp.get("items", []):
                sn = item["snippet"]
                channel_id = sn["resourceId"]["channelId"]
                out.append({
                    "external_id": channel_id,
                    "payload": {
                        "title": sn["title"],
                        "thumb": (sn.get("thumbnails", {}).get("default") or {}).get("url"),
                        "url": f"https://www.youtube.com/channel/{channel_id}",
                    },
                })
            req = yt.subscriptions().list_next(req, resp)
        return out

    def read_likes(self, db: Session) -> list[dict[str, Any]]:
        yt = self._yt(db)
        chans = yt.channels().list(part="contentDetails", mine=True).execute()
        items = chans.get("items", [])
        if not items:
            return []
        likes_playlist = items[0]["contentDetails"]["relatedPlaylists"].get("likes")
        if not likes_playlist:
            return []
        out: list[dict] = []
        req = yt.playlistItems().list(part="snippet", playlistId=likes_playlist, maxResults=50)
        while req is not None:
            resp = req.execute()
            for item in resp.get("items", []):
                sn = item["snippet"]
                video_id = sn["resourceId"]["videoId"]
                out.append({
                    "external_id": video_id,
                    "payload": {
                        "title": sn["title"],
                        "channel": sn.get("videoOwnerChannelTitle"),
                        "thumb": (sn.get("thumbnails", {}).get("default") or {}).get("url"),
                        "url": f"https://www.youtube.com/watch?v={video_id}",
                        "video_id": video_id,
                    },
                })
            req = yt.playlistItems().list_next(req, resp)
        return out
