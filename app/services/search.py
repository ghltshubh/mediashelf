"""Universal search (M2): fan-out, dedupe, rank, cache, circuit breaker.

Adding a provider is a registration, not a refactor: implement SearchProvider
and append an instance to PROVIDERS. Scopes render as independent UI sections,
so one slow/failing provider never blocks the others (plan failure modes: the
palette shows a per-provider "unavailable" chip instead).

Dedupe collapses display, never options: a music entity found on several
services keeps every service's link in its `services` list.
"""

import asyncio
import logging
import re
import time
import urllib.parse
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import settings_store
from app.models import Availability, MediaItem, Service
from app.providers import spotify as spotify_api
from app.providers import ytdlp_meta
from app.providers.tmdb import TMDBClient, poster_url
from app.services import catalog
from app.services import playback as playback_service

logger = logging.getLogger(__name__)

CACHE_TTL = 24 * 3600
_CACHE_MAX = 500
_cache: dict[tuple, tuple[float, Any]] = {}

BREAKER_THRESHOLD = 3
BREAKER_COOLDOWN = 120.0


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


class CircuitBreaker:
    """Open after N consecutive failures; half-open retry after a cooldown."""

    def __init__(self) -> None:
        self.failures = 0
        self.opened_at: float | None = None

    def allow(self) -> bool:
        if self.opened_at is None:
            return True
        if time.monotonic() - self.opened_at >= BREAKER_COOLDOWN:
            return True  # half-open probe
        return False

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= BREAKER_THRESHOLD:
            self.opened_at = time.monotonic()


class SearchProvider(Protocol):
    key: str
    scope: str  # "video" | "music"

    def configured(self, db: Session) -> bool: ...
    async def search(self, db: Session, query: str, country: str) -> list[dict]: ...


class LocalCatalogProvider:
    """Synced MediaItems — instant, availability-badged, ranked first per plan."""

    key = "local"
    scope = "video"
    cacheable = False  # DB is the source of truth; caching would hide fresh imports

    def configured(self, db: Session) -> bool:
        return True

    async def search(self, db: Session, query: str, country: str) -> list[dict]:
        items = db.scalars(
            select(MediaItem)
            .where(MediaItem.media_type.in_(["movie", "tv"]),
                   MediaItem.title.ilike(f"%{query}%"))
            .options(selectinload(MediaItem.availabilities).selectinload(Availability.service))
            .order_by(MediaItem.popularity.desc())
            .limit(20)
        ).all()
        subs = catalog.subscribed_service_ids(db)
        raw = settings_store.get_setting(db, "extra_countries") or ""
        extra = [c for c in raw.split(",") if c and c != country]
        out = []
        for it in items:
            s = catalog.serialize_item(it, subs, country)
            # Search is global across tracked regions: append other regions'
            # badges, tagged with the region code.
            for c in extra:
                for b in catalog.serialize_item(it, subs, c)["badges"]:
                    b["service_name"] = f"{b['service_name']} · {c}"
                    s["badges"].append(b)
            s["owned"] = any(b["owned"] for b in s["badges"])
            s["local"] = True
            s["popularity"] = it.popularity
            out.append(s)
        return out


class TMDBSearchProvider:
    key = "tmdb"
    scope = "video"

    ENRICH_TOP = 8  # watch-provider lookups per query (6h-cached upstream)

    def configured(self, db: Session) -> bool:
        return bool(settings_store.get_setting(db, "tmdb_api_key"))

    async def search(self, db: Session, query: str, country: str) -> list[dict]:
        api_key = settings_store.get_setting(db, "tmdb_api_key")
        assert api_key
        client = TMDBClient(api_key)
        results = await client.search_multi(query)
        out = []
        for r in results:
            if r.get("media_type") not in ("movie", "tv"):
                continue
            date = r.get("release_date") or r.get("first_air_date") or ""
            out.append({
                "local": False,
                "media_type": r["media_type"],
                "tmdb_id": r["id"],
                "id": None,
                "title": r.get("title") or r.get("name") or "Untitled",
                "year": int(date[:4]) if date[:4].isdigit() else None,
                "poster": poster_url(r.get("poster_path"), "w92"),
                "rating": r.get("vote_average") or None,
                "genres": [],
                "popularity": r.get("popularity", 0.0),
                "owned": False,
                "badges": [],
                "unlock_service": None,
            })
        # Un-imported results get availability too: raw provider maps travel with
        # the cached rows; badges are computed fresh per request in _merge_video.
        top = out[: self.ENRICH_TOP]
        provs = await asyncio.gather(
            *(client.watch_providers(r["media_type"], r["tmdb_id"]) for r in top),
            return_exceptions=True,
        )
        for r, p in zip(top, provs, strict=True):
            r["_providers"] = p if isinstance(p, dict) else {}
        return out


class SpotifyCatalogProvider:
    key = "spotify"
    scope = "music"
    service_key = "spotify"
    service_name = "Spotify"

    def configured(self, db: Session) -> bool:
        return bool(settings_store.get_setting(db, "spotify_client_id")
                    and settings_store.get_setting(db, "spotify_client_secret"))

    async def search(self, db: Session, query: str, country: str) -> list[dict]:
        cid = settings_store.get_setting(db, "spotify_client_id")
        secret = settings_store.get_setting(db, "spotify_client_secret")
        assert cid and secret
        data = await spotify_api.search_catalog(cid, secret, query, country)
        out = []
        for item in data["tracks"] + data["albums"] + data["artists"]:
            out.append({**item, "services": [
                {"service_key": self.service_key, "service_name": self.service_name,
                 "url": item.pop("url", None)}
            ]})
        return out


class YouTubeSearchProvider:
    """YouTube joins the music fan-out only behind the yt-dlp toggle — the
    official `search.list` costs 100 quota units/call (M6). When on, reads go
    through yt-dlp at zero quota; if yt-dlp errors mid-search, fall back to the
    official API but only when the user actually connected YouTube, else stay
    silent. Rows carry `youtube_video_id`, which `attach_music_playback` already
    turns into in-app playback."""

    key = "youtube"
    scope = "music"
    service_key = "youtube_music"
    service_name = "YouTube Music"

    def __init__(self) -> None:
        from app.connectors.youtube import YouTubeConnector
        self._connector = YouTubeConnector()

    def configured(self, db: Session) -> bool:
        return ytdlp_meta.active(db)

    async def search(self, db: Session, query: str, country: str) -> list[dict]:
        try:
            rows = await asyncio.to_thread(ytdlp_meta.search_music, query)
        except ytdlp_meta.YtDlpError:
            if not self._connector.connected(db):
                return []
            rows = await asyncio.to_thread(self._connector.search_track, db, query, [])
        return [self._to_music_row(r) for r in rows]

    @staticmethod
    def _to_music_row(r: dict) -> dict:
        return {
            "entity": "track",
            "title": r.get("title") or "",
            "artists": r.get("artists") or [],
            "year": None,
            "thumb": r.get("thumb"),
            "duration_ms": r.get("duration_ms"),
            "youtube_video_id": r.get("external_id"),
            "popularity": None,
            "services": [{"service_key": "youtube_music",
                          "service_name": "YouTube Music", "url": r.get("url")}],
        }


# Registration point: append here — nothing else changes.
PROVIDERS: list[Any] = [LocalCatalogProvider(), TMDBSearchProvider(),
                        SpotifyCatalogProvider(), YouTubeSearchProvider()]
_breakers: dict[str, CircuitBreaker] = {}


def breaker_for(key: str) -> CircuitBreaker:
    return _breakers.setdefault(key, CircuitBreaker())


def reset_state_for_tests() -> None:
    _breakers.clear()
    _cache.clear()


async def _run_provider(provider: Any, db: Session, query: str, country: str) -> tuple[str, list[dict]]:
    """Returns (state, results); state ∈ ok|unavailable|unconfigured."""
    if not provider.configured(db):
        return "unconfigured", []
    cacheable = getattr(provider, "cacheable", True)
    cache_key = (provider.key, _norm(query), country)
    if cacheable:
        hit = _cache.get(cache_key)
        if hit and time.monotonic() - hit[0] < CACHE_TTL:
            return "ok", hit[1]
    breaker = breaker_for(provider.key)
    if not breaker.allow():
        return "unavailable", []
    try:
        results = await provider.search(db, query, country)
    except Exception as exc:
        logger.warning("search provider %s failed: %s", provider.key, exc)
        breaker.record_failure()
        return "unavailable", []
    breaker.record_success()
    if cacheable:
        if len(_cache) >= _CACHE_MAX:
            oldest = min(_cache, key=lambda k: _cache[k][0])
            del _cache[oldest]
        _cache[cache_key] = (time.monotonic(), results)
    return "ok", results


def _badges_from_providers(providers_map: dict, title: str, countries: list[str],
                           subscribed_keys: set[str],
                           services_by_key: dict[str, Service]) -> list[dict]:
    """Display badges for an un-imported TMDB hit, straight from its raw
    watch-providers map — same data an import would store."""
    from app.services.catalog import _TMDB_NAME_OVERRIDES, _slugify

    badges: list[dict] = []
    home = countries[0] if countries else "US"
    for c in countries:
        data = providers_map.get(c) or {}
        seen: set[tuple[str, str]] = set()
        for offer_type in ("flatrate", "free", "ads", "rent", "buy"):
            for p in data.get(offer_type, []) or []:
                name = p.get("provider_name") or "Unknown"
                key = _TMDB_NAME_OVERRIDES.get(name.lower(), _slugify(name))
                if (key, offer_type) in seen:
                    continue
                seen.add((key, offer_type))
                svc = services_by_key.get(key)
                display = svc.name if svc else name
                link: str | None = data.get("link")
                if svc and svc.deep_link_template:
                    link = svc.deep_link_template.replace(
                        "{query}", urllib.parse.quote(catalog.search_query(title)))
                badges.append({
                    "service_key": key,
                    "service_name": display if c == home else f"{display} · {c}",
                    "logo": svc.logo_url if svc else None,
                    "offer_type": offer_type,
                    "owned": key in subscribed_keys and offer_type in ("flatrate", "free", "ads"),
                    "deep_link": link,
                    "price": None,
                    "signup_url": svc.signup_url if svc else None,
                    "sso_note": svc.sso_note if svc else None,
                    "country": c,
                    "checked_at": None,
                })
    order = {"flatrate": 0, "free": 1, "ads": 2, "rent": 3, "buy": 4}
    badges.sort(key=lambda b: (not b["owned"], b["country"] != home,
                               order.get(b["offer_type"], 9)))
    return badges


def _merge_video(query: str, per_provider: dict[str, list[dict]],
                 countries: list[str] | None = None,
                 subscribed_keys: set[str] | None = None,
                 services_by_key: dict[str, Service] | None = None) -> list[dict]:
    """Merge local + TMDB by tmdb_id — local wins (it has availability)."""
    by_tmdb: dict[int, dict] = {}
    merged: list[dict] = []
    for item in per_provider.get("local", []):
        merged.append(item)
        if item.get("tmdb_id"):
            by_tmdb[item["tmdb_id"]] = item
    for cached in per_provider.get("tmdb", []):
        if cached["tmdb_id"] in by_tmdb:
            continue
        # Never mutate cached rows: copy, and recompute badges fresh each
        # request so checklist/region changes reflect immediately.
        providers_map = cached.get("_providers")
        item = {k: v for k, v in cached.items() if k != "_providers"}
        if providers_map and countries:
            item["badges"] = _badges_from_providers(
                providers_map, item["title"], countries,
                subscribed_keys or set(), services_by_key or {})
            item["owned"] = any(b["owned"] for b in item["badges"])
            unlock = next((b for b in item["badges"]
                           if not b["owned"] and b["offer_type"] == "flatrate"), None)
            item["unlock_service"] = unlock["service_name"] if unlock else None
        merged.append(item)
    qn = _norm(query)
    # Rank per plan: local-library hits > exact title matches > popularity.
    merged.sort(key=lambda i: (
        not i.get("local"),
        _norm(i["title"]) != qn,
        -(i.get("popularity") or 0.0),
    ))
    for i in merged:
        i.pop("popularity", None)
        if i.get("local"):
            owned_badge = next((b for b in i["badges"] if b["owned"] and b["deep_link"]), None)
            if owned_badge:
                i["action"] = {"type": "deeplink", "url": owned_badge["deep_link"]}
                i["hint"] = f"↗ {owned_badge['service_name']}"
            else:
                i["action"] = {"type": "title", "title_id": i["id"]}
                i["hint"] = "→ details"
        else:
            i["action"] = {"type": "import", "media_type": i["media_type"], "tmdb_id": i["tmdb_id"]}
            i["hint"] = "→ details"
    return merged[:20]


def _merge_music(query: str, per_provider: dict[str, list[dict]],
                 subscribed_keys: set[str], playback_state: dict | None = None) -> list[dict]:
    """Dedupe to one row per entity; every service's link is retained."""
    rows: dict[tuple, dict] = {}
    order: list[tuple] = []
    for _, results in per_provider.items():
        for item in results:
            key = (item["entity"], _norm(item["title"]),
                   _norm(item["artists"][0]) if item["artists"] else "")
            if key in rows:
                row = rows[key]
                have = {s["service_key"] for s in row["services"]}
                row["services"].extend(s for s in item["services"] if s["service_key"] not in have)
                # Carry over playback identifiers a later provider supplies (e.g.
                # YouTube's video id) so in-app playback lights up on the merged row.
                for f in ("spotify_id", "spotify_uri", "apple_id", "youtube_video_id"):
                    if not row.get(f) and item.get(f):
                        row[f] = item[f]
            else:
                rows[key] = {k: v for k, v in item.items()}
                order.append(key)
    qn = _norm(query)
    out = [rows[k] for k in order]
    out.sort(key=lambda i: (_norm(i["title"]) != qn, -(i.get("popularity") or 0)))
    for i in out:
        i.pop("popularity", None)
        for s in i["services"]:
            s["owned"] = s["service_key"] in subscribed_keys
        attach_music_playback(i, playback_state)
    return out


def attach_music_playback(row: dict, playback_state: dict | None) -> None:
    """M3: Enter's smart default is the playback chain; deep-link is its tail."""
    entity = {
        "spotify_id": row.get("spotify_id"),
        "spotify_uri": row.get("spotify_uri"),
        "apple_id": row.get("apple_id"),
        "youtube_video_id": row.get("youtube_video_id"),
        # Whether the YouTube video allows embedding (in-app play). Unknown for
        # search hits → default True (try, fall back on error).
        "embeddable": row.get("embeddable", True),
        # Title/artists let the MusicKit engine resolve a track in Apple's catalog
        # when we don't already hold its apple_id (which is the usual case).
        "title": row.get("title"),
        "artists": row.get("artists") or [],
        "links": row.get("services", []),
    }
    routed = playback_service.music_options(entity, playback_state or {
        "spotify_connected": False, "spotify_premium": False,
        "apple_configured": False, "preferred": "auto",
    })
    row["playback"] = routed
    default = routed["default"]
    if default is None:
        row["action"] = None
        row["hint"] = ""
    elif default["engine"] == "deeplink":
        row["action"] = {"type": "deeplink", "url": default["payload"]["url"]}
        row["hint"] = f"↗ {default['label']}"
    else:
        row["action"] = {"type": "play"}
        row["hint"] = f"▶ {default['label']}"


async def run_search(db: Session, scope: str, query: str, country: str,
                     subscribed_keys: set[str], playback_state: dict | None = None) -> dict:
    providers = [p for p in PROVIDERS if p.scope == scope]
    results = await asyncio.gather(*(_run_provider(p, db, query, country) for p in providers))
    per_provider = {p.key: r for p, (_, r) in zip(providers, results, strict=True)}
    statuses = [{"key": p.key, "state": s} for p, (s, _) in zip(providers, results, strict=True)]

    groups = []
    if scope == "video":
        raw = settings_store.get_setting(db, "extra_countries") or ""
        countries = [country] + [c for c in raw.split(",") if c and c != country]
        services_by_key = {s.key: s for s in db.scalars(select(Service))}
        items = _merge_video(query, per_provider, countries, subscribed_keys, services_by_key)
        if items:
            groups.append({"key": "movies_tv", "label": "MOVIES & SHOWS", "items": items})
    else:
        merged = _merge_music(query, per_provider, subscribed_keys, playback_state)
        music = [i for i in merged if i["entity"] in ("track", "album")][:12]
        artists = [i for i in merged if i["entity"] == "artist"][:6]
        if music:
            groups.append({"key": "music", "label": "MUSIC", "items": music})
        if artists:
            groups.append({"key": "artists", "label": "ARTISTS & CHANNELS", "items": artists})
    return {"scope": scope, "groups": groups, "providers": statuses}
