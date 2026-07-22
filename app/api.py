"""HTTP API routes."""

import asyncio
import logging
import re
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import db as app_db
from app import settings_store
from app.db import get_session, session_factory
from app.models import Availability, Service, UserSub
from app.providers import spotify as spotify_api
from app.providers import ytdlp_meta
from app.providers.tmdb import TMDBClient, TMDBError
from app.secrets import mask
from app.services import backups, catalog
from app.services import library as library_service
from app.services import migrate as migrate_service
from app.services import playback as playback_service
from app.services import podcasts as podcasts_service
from app.services import search as search_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict:
    return {"ok": True}


# ---------- Settings ----------

def _tracked_countries(db: Session) -> list[str]:
    home = settings_store.get_setting(db, "country") or "US"
    raw = settings_store.get_setting(db, "extra_countries") or ""
    extras = [c for c in raw.split(",") if c and c != home]
    return [home, *extras]


class SettingsUpdate(BaseModel):
    tmdb_api_key: str | None = None
    country: str | None = None
    extra_countries: list[str] | None = None
    catalog_pages: int | None = None
    onboarded: bool | None = None
    dismiss_restore_notice: bool | None = None
    omdb_api_key: str | None = None
    spotify_client_id: str | None = None
    spotify_client_secret: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
    preferred_music_service: str | None = None
    ytdlp_enabled: bool | None = None
    # Display locale (BCP-47, e.g. "fr-FR") for date/number formatting.
    # INDEPENDENT of `country`: language/formatting is presentation, region is
    # content availability. Empty string clears it → follow the browser.
    locale: str | None = None


def _settings_payload(db: Session) -> dict:
    key = settings_store.get_setting(db, "tmdb_api_key")
    spotify_id = settings_store.get_setting(db, "spotify_client_id")
    spotify_secret = settings_store.get_setting(db, "spotify_client_secret")
    return {
        "tmdb_api_key_set": bool(key),
        "tmdb_api_key_masked": mask(key),
        "country": settings_store.get_setting(db, "country"),
        "extra_countries": _tracked_countries(db)[1:],
        "onboarded": settings_store.get_setting(db, "onboarded") == "true",
        "sync": dict(catalog.sync_state),
        "synced_at": settings_store.get_setting(db, "catalog_synced_at"),
        "restore_notice": settings_store.get_setting(db, "restore_notice"),
        "omdb_configured": bool(settings_store.get_setting(db, "omdb_api_key")),
        "spotify_configured": bool(spotify_id and spotify_secret),
        "spotify_client_id": spotify_id,
        "google_configured": bool(settings_store.get_setting(db, "google_client_id")
                                  and settings_store.get_setting(db, "google_client_secret")),
        "preferred_music_service": settings_store.get_setting(db, "preferred_music_service") or "auto",
        # Empty when unset → the client falls back to the browser language.
        "locale": settings_store.get_setting(db, "locale") or "",
        "catalog_pages": int(settings_store.get_setting(db, "catalog_pages")
                             or catalog.DEFAULT_SYNC_PAGES),
        # yt-dlp: a separately-installed community plugin (M6). `detected` is
        # whether the binary is on PATH; `enabled` is the user's toggle.
        "ytdlp_detected": ytdlp_meta.detected(),
        "ytdlp_enabled": settings_store.get_setting(db, "ytdlp_enabled") == "true",
    }


@router.get("/settings")
def get_settings(db: Session = Depends(get_session)) -> dict:
    return _settings_payload(db)


@router.put("/settings")
async def update_settings(body: SettingsUpdate, db: Session = Depends(get_session)) -> dict:
    country_changed = False
    if body.country is not None:
        country = body.country.strip().upper()
        if len(country) != 2 or not country.isalpha():
            raise HTTPException(422, "Country must be a 2-letter ISO code, e.g. US")
        country_changed = country != settings_store.get_setting(db, "country")
        settings_store.set_setting(db, "country", country)
    if body.extra_countries is not None:
        cleaned = []
        for c in body.extra_countries:
            c = c.strip().upper()
            if not c:
                continue
            if len(c) != 2 or not c.isalpha():
                raise HTTPException(422, f"'{c}' is not a 2-letter ISO country code")
            if c not in cleaned:
                cleaned.append(c)
        old = settings_store.get_setting(db, "extra_countries") or ""
        settings_store.set_setting(db, "extra_countries", ",".join(cleaned) or None)
        if ",".join(cleaned) != old and settings_store.get_setting(db, "tmdb_api_key"):
            schedule_sync()
    if body.catalog_pages is not None:
        if not (1 <= body.catalog_pages <= catalog.MAX_SYNC_PAGES):
            raise HTTPException(422, f"catalog_pages must be 1–{catalog.MAX_SYNC_PAGES}")
        old_pages = settings_store.get_setting(db, "catalog_pages")
        settings_store.set_setting(db, "catalog_pages", str(body.catalog_pages))
        if str(body.catalog_pages) != old_pages and settings_store.get_setting(db, "tmdb_api_key"):
            schedule_sync()
    if body.onboarded is not None:
        settings_store.set_setting(db, "onboarded", "true" if body.onboarded else "false")
    if body.ytdlp_enabled is not None:
        settings_store.set_setting(db, "ytdlp_enabled", "true" if body.ytdlp_enabled else "false")
    if body.dismiss_restore_notice:
        settings_store.set_setting(db, "restore_notice", None)
    if body.omdb_api_key is not None:
        key = body.omdb_api_key.strip()
        if key:
            from app.providers.omdb import OMDbClient, OMDbError
            try:
                await OMDbClient(key).validate_key()
            except OMDbError as exc:
                raise HTTPException(400, str(exc)) from exc
        settings_store.set_setting(db, "omdb_api_key", key or None)
    if body.tmdb_api_key is not None:
        key = body.tmdb_api_key.strip()
        if key:
            client = TMDBClient(key)
            try:
                await client.validate_key()
            except TMDBError as exc:
                raise HTTPException(400, str(exc)) from exc
        settings_store.set_setting(db, "tmdb_api_key", key or None)
        if key:
            schedule_sync()
    if country_changed and settings_store.get_setting(db, "tmdb_api_key"):
        schedule_sync()
    if body.spotify_client_id is not None or body.spotify_client_secret is not None:
        cid = (body.spotify_client_id or "").strip() or settings_store.get_setting(db, "spotify_client_id")
        secret = ((body.spotify_client_secret or "").strip()
                  or settings_store.get_setting(db, "spotify_client_secret"))
        if cid and secret:
            try:
                await spotify_api.validate_credentials(cid, secret)
            except spotify_api.SpotifyError as exc:
                raise HTTPException(400, str(exc)) from exc
        if body.spotify_client_id is not None:
            settings_store.set_setting(db, "spotify_client_id", body.spotify_client_id.strip() or None)
        if body.spotify_client_secret is not None:
            settings_store.set_setting(db, "spotify_client_secret",
                                       body.spotify_client_secret.strip() or None)
    if body.google_client_id is not None:
        settings_store.set_setting(db, "google_client_id", body.google_client_id.strip() or None)
    if body.google_client_secret is not None:
        settings_store.set_setting(db, "google_client_secret",
                                   body.google_client_secret.strip() or None)
    if body.preferred_music_service is not None:
        if body.preferred_music_service not in ("auto", "spotify", "apple_music", "youtube"):
            raise HTTPException(422, "Unknown preferred music service")
        settings_store.set_setting(db, "preferred_music_service", body.preferred_music_service)
    if body.locale is not None:
        loc = body.locale.strip()
        # Guard against junk while staying permissive about BCP-47 shapes.
        if loc and not re.fullmatch(r"[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*", loc):
            raise HTTPException(422, "Locale must be a BCP-47 tag, e.g. fr-FR")
        settings_store.set_setting(db, "locale", loc or None)
    return _settings_payload(db)


class ValidateBody(BaseModel):
    tmdb_api_key: str


@router.post("/settings/tmdb/validate")
async def validate_tmdb(body: ValidateBody) -> dict:
    """Onboarding live-validation: fires a test request, returns ✓ or the actual error."""
    try:
        await TMDBClient(body.tmdb_api_key.strip()).validate_key()
    except TMDBError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True}


# ---------- Services / subscription checklist ----------

@router.get("/services")
def list_services(region: str = "", db: Session = Depends(get_session)) -> list[dict]:
    rows = db.execute(
        select(Service, UserSub).outerjoin(UserSub, UserSub.service_id == Service.id)
        .order_by(Service.tier, Service.name)
    ).all()
    from app.models import LibraryEntry

    # Checklist region scope: video is shown only where it's actually available,
    # so you don't scroll every region's providers. Default = your home country;
    # "ALL" shows every region's providers. Availability from other regions still
    # works on the shelf — this only trims the tick-list.
    scope = (region or "").strip().upper() or (settings_store.get_setting(db, "country") or "US")
    region_svc_ids: set[int] = set()
    if scope != "ALL":
        region_svc_ids = set(db.scalars(
            select(Availability.service_id).where(Availability.country == scope).distinct()))

    # State so tiles can show what's already set up vs untouched.
    wl_counts: dict[int, int] = {
        sid: n for sid, n in db.execute(
            select(LibraryEntry.service_id, func.count(LibraryEntry.id))
            .where(LibraryEntry.entry_type == "watchlist")
            .group_by(LibraryEntry.service_id)).all()
        if sid is not None
    }
    connected_keys = set()
    if settings_store.get_setting(db, "spotify_oauth"):
        connected_keys.add("spotify")
    if settings_store.get_setting(db, "youtube_oauth"):
        connected_keys |= {"youtube", "youtube_music"}
    if settings_store.get_setting(db, "apple_developer_token"):
        connected_keys.add("apple_music")
    # Video "integratable" depends on TMDB reporting the provider, which only
    # populates after a sync — so we only prune dead video once the catalog has
    # synced (before that, onboarding needs the full roster).
    synced = settings_store.get_setting(db, "catalog_synced_at") is not None
    # A token can be present but expired (refresh failed) — the tile should say
    # "Reconnect", matching the Library banner and the Accounts card.
    expired_keys = set()
    if settings_store.get_setting(db, "spotify_auth_error") == "true":
        expired_keys.add("spotify")
    if settings_store.get_setting(db, "youtube_auth_error") == "true":
        expired_keys |= {"youtube", "youtube_music"}

    out = []
    for s, sub in rows:
        featured, integration, integ_kind = catalog.service_integration(
            s.key, s.tier, s.capabilities)
        # A service earns a checklist spot only if ticking it can actually surface
        # something. Otherwise keep it out (still seeded in the DB, so it
        # self-reappears once it gains a data source / connector):
        #   music → needs a real catalog/library connector (Gaana, Tidal, … don't).
        #   video → TMDB must track its availability (tmdb_provider_id) OR it's
        #           watchlist-importable / a connector / a custom browse-link marker.
        if s.kind == "music":
            if integ_kind != "connector":
                continue
        elif s.kind == "video" and synced:
            # Always keep watchlist/connector/custom. Otherwise: in "ALL" mode keep
            # anything TMDB tracks anywhere (prunes the truly-dead like DAZN); for a
            # specific region keep only what's actually available there.
            if s.custom or integ_kind in ("watchlist", "connector"):
                pass
            elif scope == "ALL":
                if s.tmdb_provider_id is None:
                    continue
            elif s.id not in region_svc_ids:
                continue
        out.append({
            "connected": s.key in connected_keys,
            "expired": s.key in expired_keys,
            "watchlist_count": wl_counts.get(s.id, 0),
            "id": s.id, "key": s.key, "name": s.name, "kind": s.kind, "tier": s.tier,
            "subscribed": bool(sub and sub.subscribed),
            "capabilities": s.capabilities,
            "signup_url": s.signup_url, "sso_note": s.sso_note,
            "homepage_url": s.homepage_url, "logo_url": s.logo_url,
            "auto_added": s.auto_added, "custom": s.custom,
            # Add-on storefronts ("X Amazon Channel") group separately in the UI.
            "is_channel": catalog.is_channel_name(s.name),
            # Deeper-integration services surface at the top of the checklist.
            "featured": featured, "integration": integration,
            "integration_kind": integ_kind,
        })
    return out


class CustomServiceBody(BaseModel):
    name: str
    homepage_url: str
    kind: str = "video"
    logo_url: str | None = None


@router.post("/services", status_code=201)
def create_custom_service(body: CustomServiceBody, db: Session = Depends(get_session)) -> dict:
    """Custom services (M1): ordinary Service rows with no availability data source."""
    name = body.name.strip()
    url = body.homepage_url.strip()
    if not name:
        raise HTTPException(422, "Give the service a name")
    if not url.startswith(("http://", "https://")):
        raise HTTPException(422, "Homepage must be a full URL (https://…)")
    # Custom services are browse-and-link markers only. That's useful for video
    # (deep-link to its site), but a marker can never surface MUSIC — that needs a
    # real catalog/library connector — so we don't let one pretend it will.
    if body.kind != "video":
        raise HTTPException(422, "Custom services are video-only. Music can't be added as a "
                                 "marker — connect Spotify, YouTube, or Apple Music instead "
                                 "(they have real catalogs/libraries).")
    key_base = "custom_" + "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_")
    key = key_base
    n = 2
    while db.scalar(select(Service).where(Service.key == key)) is not None:
        key = f"{key_base}_{n}"
        n += 1
    svc = Service(
        key=key, name=name, kind=body.kind, tier=3, custom=True,
        homepage_url=url, logo_url=(body.logo_url or None),
        capabilities={"catalog": False, "user_library": False, "write_likes": False,
                      "write_follows": False, "playback": "deeplink"},
    )
    db.add(svc)
    db.flush()
    db.add(UserSub(service_id=svc.id, subscribed=True))
    db.commit()
    return {"id": svc.id, "key": svc.key, "name": svc.name, "kind": svc.kind,
            "homepage_url": svc.homepage_url, "custom": True, "subscribed": True}


@router.delete("/services/{service_id}", status_code=204)
def delete_custom_service(service_id: int, db: Session = Depends(get_session)) -> None:
    svc = db.get(Service, service_id)
    if svc is None:
        raise HTTPException(404, "Unknown service")
    if not svc.custom:
        raise HTTPException(400, "Only custom services can be removed")
    for sub in db.scalars(select(UserSub).where(UserSub.service_id == service_id)):
        db.delete(sub)
    for avail in db.scalars(select(Availability).where(Availability.service_id == service_id)):
        db.delete(avail)
    db.delete(svc)
    db.commit()


class SubscriptionBody(BaseModel):
    subscribed: bool


@router.put("/services/{service_id}/subscription")
def set_subscription(service_id: int, body: SubscriptionBody,
                     db: Session = Depends(get_session)) -> dict:
    svc = db.get(Service, service_id)
    if svc is None:
        raise HTTPException(404, "Unknown service")
    sub = db.scalar(select(UserSub).where(UserSub.service_id == service_id))
    if sub is None:
        sub = UserSub(service_id=service_id)
        db.add(sub)
    sub.subscribed = body.subscribed
    db.commit()
    return {"id": service_id, "subscribed": sub.subscribed}


# ---------- Catalog ----------

def _region_or_home(db: Session, region: str) -> tuple[str, list[str] | None]:
    """Returns (country_label, all_countries). "ALL" aggregates every tracked
    region; otherwise a single tracked region (falling back to home)."""
    tracked = _tracked_countries(db)
    r = region.strip().upper()
    if r == "ALL" and len(tracked) > 1:
        return "ALL", tracked
    return (r if r in tracked else tracked[0]), None


def _valid_filter(filter: str) -> str:
    if filter in ("all", "mine", "elsewhere") or filter.startswith("svc:"):
        return filter
    return "all"


def _valid_sort(sort: str) -> str:
    return sort if sort in ("popularity", "title", "year") else "popularity"


@router.get("/shelf")
def shelf(view: str = "categories", region: str = "", filter: str = "all",
          type: str = "", sort: str = "popularity", genre: str = "",
          db: Session = Depends(get_session)) -> dict:
    country, all_countries = _region_or_home(db, region)
    data = catalog.build_shelf(db, country,
                               view=view if view in ("categories", "services") else "categories",
                               flt=_valid_filter(filter),
                               media_type=type if type in ("movie", "tv") else None,
                               all_countries=all_countries, sort=_valid_sort(sort),
                               genre=genre or None)
    data["regions"] = _tracked_countries(db)
    return data


@router.get("/regions")
async def available_regions(db: Session = Depends(get_session)) -> list[dict]:
    """Selectable regions with country names, from TMDB (cached upstream)."""
    api_key = settings_store.get_setting(db, "tmdb_api_key")
    if not api_key:
        return []
    try:
        regions = await TMDBClient(api_key).watch_provider_regions()
    except TMDBError:
        return []
    out = [{"code": r["iso_3166_1"], "name": r.get("english_name") or r["iso_3166_1"]}
           for r in regions if len(r.get("iso_3166_1", "")) == 2]
    out.sort(key=lambda r: r["name"])
    return out


@router.get("/shelf/rail/{rail_key}")
def shelf_rail(rail_key: str, region: str = "", filter: str = "all", type: str = "",
               sort: str = "popularity", db: Session = Depends(get_session)) -> dict:
    country, all_countries = _region_or_home(db, region)
    data = catalog.build_rail(db, country, rail_key, flt=_valid_filter(filter),
                              media_type=type if type in ("movie", "tv") else None,
                              all_countries=all_countries, sort=_valid_sort(sort))
    if data is None:
        raise HTTPException(404, "Unknown rail")
    data["country"] = country
    data["regions"] = _tracked_countries(db)
    return data


@router.get("/titles/{item_id}")
async def title(item_id: int, region: str = "", db: Session = Depends(get_session)) -> dict:
    country, all_countries = _region_or_home(db, region)
    api_key = settings_store.get_setting(db, "tmdb_api_key")
    await catalog.ensure_trailer(db, item_id, api_key)
    await catalog.ensure_ratings(db, item_id, api_key,
                                 settings_store.get_setting(db, "omdb_api_key"))
    await catalog.ensure_expected_service(db, item_id, api_key)
    await catalog.ensure_details(db, item_id, api_key)
    data = catalog.build_title(db, item_id, country, all_countries=all_countries)
    if data is None:
        raise HTTPException(404, "Title not found")
    tracked = _tracked_countries(db)
    data["regions"] = tracked
    data["world"] = await catalog.world_availability(
        api_key, data["media_type"], data["tmdb_id"], exclude=tracked)
    return data


@router.post("/sync")
async def trigger_sync(db: Session = Depends(get_session)) -> dict:
    if not settings_store.get_setting(db, "tmdb_api_key"):
        raise HTTPException(400, "Add your TMDB key first")
    schedule_sync()
    return {"status": "started"}


# ---------- Universal search (M2) ----------

@router.get("/search")
async def search(q: str = "", scope: str = "video",
                 db: Session = Depends(get_session)) -> dict:
    """One scope per call — the palette fans out per scope so sections render
    progressively and a slow provider never blocks the rest."""
    if scope not in ("video", "music", "library"):
        raise HTTPException(422, "scope must be video, music or library")
    q = q.strip()
    if len(q) < 2:
        return {"scope": scope, "groups": [], "providers": []}
    country = settings_store.get_setting(db, "country") or "US"
    subscribed = set(db.scalars(
        select(Service.key).join(UserSub, UserSub.service_id == Service.id)
        .where(UserSub.subscribed.is_(True))
    ))
    playback_state = playback_service.user_playback_state(db)
    if scope == "library":
        items = _library_search_items(db, q, subscribed, playback_state)
        groups = [{"key": "library", "label": "YOUR LIBRARY", "items": items}] if items else []
        return {"scope": "library", "groups": groups, "providers": [{"key": "library", "state": "ok"}]}
    return await search_service.run_search(db, scope, q, country, subscribed, playback_state)


def _library_search_items(db: Session, q: str, subscribed: set[str],
                          playback_state: dict) -> list[dict]:
    """Synced likes/follows as palette rows — pinned first when they hit (§4.3)."""
    groups = library_service.rows_for_groups(db, subscribed, playback_state,
                                             query=q, per_group=5)
    return [item for g in groups for item in g["items"]][:10]


class ImportBody(BaseModel):
    media_type: str
    tmdb_id: int


@router.post("/titles/import")
async def import_title(body: ImportBody, db: Session = Depends(get_session)) -> dict:
    """Pull a search hit into the catalog (detail + availability) and return it."""
    if body.media_type not in ("movie", "tv"):
        raise HTTPException(422, "media_type must be movie or tv")
    api_key = settings_store.get_setting(db, "tmdb_api_key")
    if not api_key:
        raise HTTPException(400, "Add your TMDB key first")
    countries = _tracked_countries(db)
    try:
        item = await catalog.import_title(db, api_key, body.media_type, body.tmdb_id, countries)
    except TMDBError as exc:
        raise HTTPException(502, str(exc)) from exc
    data = catalog.build_title(db, item.id, countries[0])
    assert data is not None
    return data


# ---------- Watchlist import (decided in plan; product ships importer only) ----------

LIST_TYPES = ("watchlist", "top10", "leaving_soon")

_ARTICLE_RE = re.compile(r"^(the|a|an)\s+", re.IGNORECASE)


def _norm_title(t: str) -> str:
    t = _ARTICLE_RE.sub("", t.lower().strip())
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def _resolve_best(results: list[dict], title: str, year: int | None) -> dict | None:
    """Pick the best TMDB hit for a scraped title. Article-insensitive
    ("Devil's Advocate" == "The Devil's Advocate"); among title matches, prefer
    a year match then popularity; else fall back to the most popular result."""
    qn = _norm_title(title)
    matches: list[tuple[bool, float, dict]] = []
    for r in results:
        name = r.get("title") or r.get("name") or ""
        date = r.get("release_date") or r.get("first_air_date") or ""
        r_year = int(date[:4]) if date[:4].isdigit() else None
        if _norm_title(name) == qn:
            matches.append((year is not None and r_year == year,
                            r.get("popularity", 0.0), r))
    if matches:
        matches.sort(key=lambda mrec: (not mrec[0], -mrec[1]))
        return matches[0][2]
    return results[0] if results else None


async def _resolve_for_service(client: TMDBClient, results: list[dict], title: str,
                               year: int | None, source_key: str, country: str,
                               known_keys: set[str]) -> dict | None:
    """Service-aware resolution: a title from your Netflix list should match the
    TMDB entry that's actually ON Netflix. Disambiguates same-name films
    ("Ludo" 2020 Bollywood on Netflix vs a 2021 documentary) by checking each
    candidate's availability on the source service; falls back to _resolve_best."""
    qn = _norm_title(title)
    matches = [r for r in results
               if _norm_title(r.get("title") or r.get("name") or "") == qn]
    pool = matches or results
    if len(pool) <= 1:
        return pool[0] if pool else None
    from app.services.catalog import _slugify, resolve_alias_key

    for cand in sorted(pool, key=lambda r: -(r.get("popularity") or 0.0))[:6]:
        try:
            regions = await client.watch_providers(cand["media_type"], cand["id"])
        except Exception:
            continue
        data = regions.get(country) or {}
        keys: set[str] = set()
        for field in ("flatrate", "free", "ads", "rent", "buy"):
            for p in data.get(field, []) or []:
                name = p.get("provider_name", "")
                keys.add(resolve_alias_key(name, known_keys) or _slugify(name))
        if source_key in keys:
            return cand
    return _resolve_best(results, title, year)


class WatchlistItem(BaseModel):
    title: str
    year: int | None = None
    rank: int | None = None          # top10 ordering
    note: str | None = None          # e.g. "leaves Jul 31"


class WatchlistImportBody(BaseModel):
    source: str                      # service key, e.g. "netflix"
    items: list[WatchlistItem]
    replace: bool = True             # full-state sync: adds AND removals
    list_type: str = "watchlist"     # watchlist | top10 | leaving_soon


@router.post("/watchlist/import")
async def import_watchlist(body: WatchlistImportBody,
                           db: Session = Depends(get_session)) -> dict:
    from app.models import LibraryEntry

    if body.list_type not in LIST_TYPES:
        raise HTTPException(422, f"list_type must be one of {LIST_TYPES}")
    api_key = settings_store.get_setting(db, "tmdb_api_key")
    if not api_key:
        raise HTTPException(400, "Add your TMDB key first")
    svc = db.scalar(select(Service).where(Service.key == body.source.strip().lower()))
    if svc is None:
        raise HTTPException(404, f"Unknown service '{body.source}'")
    countries = _tracked_countries(db)
    client = TMDBClient(api_key)
    lt = body.list_type
    known_keys = set(db.scalars(select(Service.key)))

    added, kept, unmatched = 0, 0, []
    seen_external: set[str] = set()
    for idx, item in enumerate(body.items[:500]):
        title = item.title.strip()
        if not title:
            continue
        external_id = f"{body.source}:{lt}:{title.lower()}"
        if external_id in seen_external:
            continue
        seen_external.add(external_id)
        rank = item.rank if item.rank is not None else (idx + 1 if lt == "top10" else None)
        payload = {"title": title, "year": item.year, "rank": rank, "note": item.note}
        existing = db.scalar(select(LibraryEntry).where(
            LibraryEntry.service_id == svc.id,
            LibraryEntry.entry_type == lt,
            LibraryEntry.external_id == external_id))
        if existing is not None:
            existing.payload = payload  # refresh rank/note even when title unchanged
            kept += 1
            continue
        # Resolve against TMDB: prefer the match that's on the source service,
        # else article-insensitive popularity-best.
        try:
            results = [r for r in await client.search_multi(title)
                       if r.get("media_type") in ("movie", "tv")]
        except TMDBError:
            results = []
        best = await _resolve_for_service(client, results, title, item.year,
                                          svc.key, countries[0], known_keys)
        if best is None:
            unmatched.append(title)
            continue
        media = await catalog.import_title(db, api_key, best["media_type"], best["id"], countries)
        db.add(LibraryEntry(service_id=svc.id, media_item_id=media.id,
                            entry_type=lt, external_id=external_id, payload=payload))
        db.commit()
        added += 1

    removed = 0
    if body.replace:
        for entry in db.scalars(select(LibraryEntry).where(
                LibraryEntry.service_id == svc.id,
                LibraryEntry.entry_type == lt)):
            if entry.external_id not in seen_external:
                db.delete(entry)
                removed += 1
        db.commit()
    return {"source": body.source, "added": added, "kept": kept,
            "removed": removed, "unmatched": unmatched}


# ---------- Migrations (M5) ----------

class MigrationBody(BaseModel):
    source: str
    target: str
    likes: bool = True
    follows: bool = False
    source_slot: str = "primary"
    target_slot: str = "primary"


def _start_job_task(job_id: int) -> None:
    loop = asyncio.get_running_loop()
    loop.create_task(asyncio.to_thread(migrate_service.run_job, job_id))


@router.get("/migrations")
def list_migrations(db: Session = Depends(get_session)) -> dict:
    from app.models import MigrationJob

    jobs = db.scalars(select(MigrationJob).order_by(MigrationJob.id.desc()).limit(20)).all()
    return {
        "jobs": [migrate_service.job_json(db, j) for j in jobs],
        "pairs": migrate_service.migration_pairs(db),
        "budget": {"cap": migrate_service.write_cap(db),
                   "used_today": migrate_service.writes_used_today(db)},
    }


@router.post("/migrations")
async def start_migration(body: MigrationBody, db: Session = Depends(get_session)) -> dict:
    if not (body.likes or body.follows):
        raise HTTPException(422, "Pick at least one thing to copy")
    try:
        job, created = migrate_service.create_or_resume(
            db, body.source, body.target,
            {"likes": body.likes, "follows": body.follows,
             "source_slot": body.source_slot, "target_slot": body.target_slot})
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    _start_job_task(job.id)
    return {**migrate_service.job_json(db, job), "resumed_existing": not created}


@router.post("/migrations/{job_id}/resume")
async def resume_migration(job_id: int, db: Session = Depends(get_session)) -> dict:
    from app.models import MigrationJob

    job = db.get(MigrationJob, job_id)
    if job is None:
        raise HTTPException(404, "No such job")
    if job.status not in ("review", "paused_quota", "paused_auth", "matching",
                          "writing", "pending", "stopped"):
        raise HTTPException(409, f"Job is {job.status}")
    _start_job_task(job.id)
    return migrate_service.job_json(db, job)


@router.post("/migrations/{job_id}/stop")
def stop_migration(job_id: int, db: Session = Depends(get_session)) -> dict:
    migrate_service.request_stop(job_id)
    return {"status": "stopping"}


@router.post("/migrations/{job_id}/revert")
async def revert_migration(job_id: int, db: Session = Depends(get_session)) -> dict:
    from app.models import MigrationJob

    job = db.get(MigrationJob, job_id)
    if job is None:
        raise HTTPException(404, "No such job")
    if job.status in migrate_service.ACTIVE_STATUSES and job.status != "paused_quota":
        raise HTTPException(409, "Stop the job before reverting")
    if not job.progress.get("journal"):
        raise HTTPException(400, "Nothing to revert — this job wrote nothing")
    loop = asyncio.get_running_loop()
    loop.create_task(asyncio.to_thread(migrate_service.revert_job, job_id))
    return {"status": "reverting"}


# ---------- Match review queue (M4) ----------

def _candidate_json(c) -> dict:
    return {"id": c.id, "job_id": c.job_id, "source": c.source_payload,
            "candidate": c.candidate_payload, "confidence": c.confidence,
            "status": c.status}


@router.get("/review")
def review_queue(db: Session = Depends(get_session)) -> dict:
    from app.models import MatchCandidate

    rows = db.scalars(select(MatchCandidate)
                      .where(MatchCandidate.status == "pending")
                      .order_by(MatchCandidate.confidence.desc())).all()
    return {"pending": [_candidate_json(c) for c in rows]}


def _get_pending(db: Session, candidate_id: int):
    from app.models import MatchCandidate

    row = db.get(MatchCandidate, candidate_id)
    if row is None:
        raise HTTPException(404, "No such review item")
    if row.status != "pending":
        raise HTTPException(409, f"Already {row.status}")
    return row


@router.post("/review/{candidate_id}/approve")
def review_approve(candidate_id: int, db: Session = Depends(get_session)) -> dict:
    row = _get_pending(db, candidate_id)
    row.status = "approved"
    db.commit()
    return _candidate_json(row)


@router.post("/review/{candidate_id}/skip")
def review_skip(candidate_id: int, db: Session = Depends(get_session)) -> dict:
    row = _get_pending(db, candidate_id)
    row.status = "skipped"
    db.commit()
    return _candidate_json(row)


class ReplaceBody(BaseModel):
    candidate: dict


@router.post("/review/{candidate_id}/replace")
def review_replace(candidate_id: int, body: ReplaceBody,
                   db: Session = Depends(get_session)) -> dict:
    """"Pick another": the user chose a different target via inline search."""
    if not body.candidate.get("title"):
        raise HTTPException(422, "Replacement needs at least a title")
    row = _get_pending(db, candidate_id)
    row.candidate_payload = body.candidate
    row.confidence = 1.0  # human-chosen
    row.status = "replaced"
    db.commit()
    return _candidate_json(row)


class BatchBody(BaseModel):
    min_confidence: float = 0.9


@router.post("/review/approve-batch")
def review_approve_batch(body: BatchBody, db: Session = Depends(get_session)) -> dict:
    from app.models import MatchCandidate

    rows = db.scalars(select(MatchCandidate)
                      .where(MatchCandidate.status == "pending",
                             MatchCandidate.confidence >= body.min_confidence)).all()
    for r in rows:
        r.status = "approved"
    db.commit()
    return {"approved": len(rows)}


# ---------- Backups (SQLite safety, plan failure modes) ----------

@router.get("/backup/export")
def export_backup() -> FileResponse:
    """One-click DB export: a fresh consistent copy, not the live file."""
    tmp = Path(tempfile.mkdtemp()) / "mediashelf-export.db"
    backups.create_backup(dest=tmp)
    return FileResponse(tmp, filename="mediashelf-export.db",
                        media_type="application/octet-stream")


@router.post("/backup/import")
async def import_backup(file: UploadFile) -> dict:
    """Replace the DB with an uploaded export. Integrity-checked first; the
    current DB is backed up before it is replaced."""
    tmp = Path(tempfile.mkdtemp()) / "upload.db"
    with tmp.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    if not backups.integrity_ok(tmp):
        raise HTTPException(400, "That file is not a healthy MediaShelf database")
    backups.create_backup()
    app_db.reset_engine_for_tests()  # dispose connections before swapping the file
    shutil.copyfile(tmp, backups.db_path())
    app_db.reset_engine_for_tests()
    return {"status": "imported"}


# ---------- Podcasts (M8): RSS/OPML, no accounts or keys ----------

class PodcastSubscribeBody(BaseModel):
    feed_url: str


@router.get("/podcasts")
def list_podcasts(db: Session = Depends(get_session)) -> list[dict]:
    return podcasts_service.list_podcasts(db)


@router.get("/podcasts/{podcast_id}")
def get_podcast(podcast_id: int, db: Session = Depends(get_session)) -> dict:
    from app.models import Podcast

    podcast = db.get(Podcast, podcast_id)
    if not podcast:
        raise HTTPException(404, "Podcast not found")
    return podcasts_service.podcast_dict(podcast, with_episodes=True)


@router.post("/podcasts", status_code=201)
async def subscribe_podcast(body: PodcastSubscribeBody,
                            db: Session = Depends(get_session)) -> dict:
    try:
        podcast = await podcasts_service.subscribe(db, body.feed_url)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return podcasts_service.podcast_dict(podcast, with_episodes=True)


@router.delete("/podcasts/{podcast_id}", status_code=204)
def unsubscribe_podcast(podcast_id: int, db: Session = Depends(get_session)) -> None:
    if not podcasts_service.unsubscribe(db, podcast_id):
        raise HTTPException(404, "Podcast not found")


@router.post("/podcasts/refresh")
async def refresh_podcasts(db: Session = Depends(get_session)) -> dict:
    added = await podcasts_service.refresh_all(db)
    return {"new_episodes": added}


@router.get("/podcasts/opml/export")
def export_podcasts_opml(db: Session = Depends(get_session)) -> Response:
    xml = podcasts_service.export_opml(db)
    return Response(content=xml, media_type="text/x-opml",
                    headers={"Content-Disposition": "attachment; filename=mediashelf-podcasts.opml"})


@router.post("/podcasts/opml/import")
async def import_podcasts_opml(file: UploadFile,
                               db: Session = Depends(get_session)) -> dict:
    raw = await file.read()
    try:
        subscribed = await podcasts_service.import_opml(db, raw)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"subscribed": len(subscribed)}


async def _podcast_refresh_job() -> None:
    with session_factory()() as db:
        try:
            added = await podcasts_service.refresh_all(db)
            logger.info("podcast refresh done: %s new episodes", added)
        except Exception:
            logger.exception("podcast refresh job failed")


# ---------- Sync scheduling ----------

_sync_task: asyncio.Task | None = None
_retry_task: asyncio.Task | None = None
_retry_delay = 0


async def _sync_job() -> None:
    global _retry_delay, _retry_task
    with session_factory()() as db:
        api_key = settings_store.get_setting(db, "tmdb_api_key")
        countries = _tracked_countries(db)
        if not api_key:
            return
        pages = int(settings_store.get_setting(db, "catalog_pages") or catalog.DEFAULT_SYNC_PAGES)
        try:
            summary = await catalog.run_sync(db, api_key, countries[0], countries[1:], pages=pages)
            logger.info("catalog sync done: %s", summary)
            _retry_delay = 0
        except Exception as exc:
            logger.error("catalog sync failed: %s", exc)
            # Retry with backoff (15m → 30m → 1h → 2h → 4h cap); the shelf keeps
            # serving the last-synced catalog in the meantime.
            _retry_delay = min(_retry_delay * 2, 14400) if _retry_delay else 900
            if _retry_task is None or _retry_task.done():
                _retry_task = asyncio.get_running_loop().create_task(_retry_after(_retry_delay))


async def _retry_after(delay: float) -> None:
    await asyncio.sleep(delay)
    schedule_sync()


def schedule_sync() -> None:
    """Kick a sync in the background; no-op if one is already running."""
    global _sync_task
    if _sync_task and not _sync_task.done():
        return
    _sync_task = asyncio.get_running_loop().create_task(_sync_job())
