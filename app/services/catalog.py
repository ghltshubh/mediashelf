"""Catalog sync: TMDB popular movies/TV + per-title watch-provider availability.

Runs on TMDB-key save, on boot (if a key exists), and nightly via APScheduler.
Auto-adds any provider TMDB reports for the user's country that isn't already
in the Service table (Appendix A rule).
"""

import asyncio
import logging
import re
import urllib.parse
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app import settings_store
from app.models import Availability, MediaItem, Service, UserSub
from app.providers.tmdb import IMAGE_BASE, TMDBClient, TMDBError, poster_url

logger = logging.getLogger(__name__)

DEFAULT_SYNC_PAGES = 5   # pages × 20 titles per media type; user-configurable
MAX_SYNC_PAGES = 25      # 500 titles per type — plenty for a household shelf
_PROVIDER_CONCURRENCY = 4

# Map TMDB provider names to seeded service keys where naming differs, and fold
# tier variants ("Standard with Ads", "Premium") into the parent service — one
# checklist entry per brand. Add-on channels (e.g. "Max Amazon Channel") are NOT
# folded: they're separate purchases.
_TMDB_NAME_OVERRIDES = {
    "amazon prime video": "prime_video",
    "amazon prime video with ads": "prime_video",
    "amazon video": "prime_video",
    "netflix standard with ads": "netflix",
    "netflix kids": "netflix",
    "google play movies": "youtube",
    "youtube premium": "youtube",
    "youtube free": "youtube",
    "hbo max": "max",
    "paramount+ with showtime": "paramount_plus",
    "paramount plus": "paramount_plus",
    "paramount+": "paramount_plus",
    "paramount plus premium": "paramount_plus",
    "peacock premium": "peacock",
    "peacock premium plus": "peacock",
    "hulu (no ads)": "hulu",
    "tubi tv": "tubi",
    "apple tv+": "apple_tv_plus",
    "apple tv plus": "apple_tv_plus",
    "the roku channel": "roku_channel",
    "the criterion channel": "criterion",
    "curiositystream": "curiosity_stream",
    "hotstar": "jiohotstar",
    "jiocinema": "jiohotstar",
}

# error_kind: "auth" (key rejected → fix in Settings → Keys) vs "network" (retry quietly).
sync_state: dict = {"status": "idle", "detail": None, "last_completed": None, "error_kind": None}

# Subscription-tier variants fold into the parent brand generically.
_TIER_SUFFIX_RE = re.compile(
    r"\s+(free with ads|standard with ads|basic with ads|with ads|"
    r"premium plus|premium|standard|basic|kids)$", re.IGNORECASE)

# Add-on channel storefronts ("X Amazon Channel" / "Amazon X Channel") are
# separate purchases — kept, but flagged so the UI groups them out of the main
# checklist. "The Roku Channel" is a service brand, not a storefront listing.
_CHANNEL_RE = re.compile(r"\b(amazon|apple tv|roku)\b.*\bchannel$", re.IGNORECASE)
_CHANNEL_BRAND_EXCEPTIONS = {"the roku channel", "roku channel"}


# Major video services that support watchlist import via the local companion
# tool — featured alongside Tier 1/2 connectors, above the deep-link long tail.
WATCHLIST_SERVICES = {
    "netflix", "prime_video", "disney_plus", "hulu", "max", "paramount_plus",
    "peacock", "apple_tv_plus", "crunchyroll", "tubi",
}


# OAuth connectors with a live Accounts card today (M3). Others (Deezer, Tidal,
# SoundCloud…) are catalog-capable but their connectors land in M8, so they sit
# in the long tail until then — "featured" means an action is available NOW.
CONNECTOR_KEYS = {"spotify", "youtube", "youtube_music", "apple_music"}


def service_integration(key: str, tier: int, capabilities: dict) -> tuple[bool, str, str]:
    """(featured, short-label, kind). kind ∈ connector | watchlist | basic —
    drives which setup affordance the tile links to."""
    if key in CONNECTOR_KEYS:
        return True, "library & playback", "connector"
    if key in WATCHLIST_SERVICES:
        return True, "watchlist import", "watchlist"
    return False, "browse & link", "basic"


def is_channel_name(name: str) -> bool:
    clean = name.strip().lower()
    if clean in _CHANNEL_BRAND_EXCEPTIONS:
        return False
    return bool(_CHANNEL_RE.search(clean))


def resolve_alias_key(name: str, known_keys: set[str]) -> str | None:
    """Map a TMDB provider name to an existing service key: explicit override,
    else tier-suffix-stripped base if that base is a known service."""
    low = name.lower().strip()
    if low in _TMDB_NAME_OVERRIDES:
        return _TMDB_NAME_OVERRIDES[low]
    stripped = _TIER_SUFFIX_RE.sub("", low).strip()
    if stripped != low:
        cand = _TMDB_NAME_OVERRIDES.get(stripped, _slugify(stripped))
        if cand in known_keys:
            return cand
    return None


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _service_lookup(db: Session) -> tuple[dict[int, Service], dict[str, Service]]:
    services = db.scalars(select(Service)).all()
    by_tmdb_id = {s.tmdb_provider_id: s for s in services if s.tmdb_provider_id}
    by_key = {s.key: s for s in services}
    return by_tmdb_id, by_key


def _tmdb_logo(provider: dict) -> str | None:
    path = provider.get("logo_path")
    return f"{IMAGE_BASE}/w92{path}" if path else None


def _resolve_service(db: Session, provider: dict,
                     by_tmdb_id: dict[int, Service], by_key: dict[str, Service]) -> Service:
    pid = provider.get("provider_id")
    name = provider.get("provider_name", "Unknown")
    logo = _tmdb_logo(provider)
    # Only adopt a logo when the provider name IS this service (its slug == key),
    # never via an alias — else "Google Play Movies" (→ youtube) would give
    # YouTube the Google Play logo.
    if pid in by_tmdb_id:
        cached = by_tmdb_id[pid]
        if logo and not cached.logo_url and _slugify(name) == cached.key:
            cached.logo_url = logo
        return cached
    key = resolve_alias_key(name, set(by_key)) or _slugify(name)
    svc = by_key.get(key)
    if svc is None:
        svc = Service(
            key=key, name=name, kind="video", tier=3, auto_added=True,
            tmdb_provider_id=pid, logo_url=logo,  # brand-new service: name == key
            capabilities={"catalog": False, "user_library": False, "write_likes": False,
                          "write_follows": False, "playback": "deeplink"},
        )
        db.add(svc)
        db.flush()
        db.add(UserSub(service_id=svc.id, subscribed=False))
        by_key[key] = svc
    elif logo and not svc.logo_url and _slugify(name) == svc.key:
        svc.logo_url = logo
    if svc.tmdb_provider_id is None:
        svc.tmdb_provider_id = pid
    if pid is not None:
        by_tmdb_id[pid] = svc
    return svc


def _upsert_media_item(db: Session, media_type: str, r: dict, genre_map: dict[int, str]) -> MediaItem:
    item = db.scalar(select(MediaItem).where(
        MediaItem.media_type == media_type, MediaItem.tmdb_id == r["id"]))
    title = r.get("title") or r.get("name") or "Untitled"
    date = r.get("release_date") or r.get("first_air_date") or ""
    year = int(date[:4]) if len(date) >= 4 and date[:4].isdigit() else None
    fields = dict(
        title=title, year=year, overview=r.get("overview"),
        poster_path=r.get("poster_path"), backdrop_path=r.get("backdrop_path"),
        genres=[genre_map[g] for g in r.get("genre_ids", []) if g in genre_map],
        popularity=r.get("popularity", 0.0), rating=r.get("vote_average"),
    )
    if item is None:
        item = MediaItem(media_type=media_type, tmdb_id=r["id"], **fields)
        db.add(item)
        db.flush()
    else:
        for k, v in fields.items():
            setattr(item, k, v)
    return item


def _upsert_availability(db: Session, item: MediaItem, country: str,
                         country_data: dict, by_tmdb_id: dict, by_key: dict) -> None:
    existing = {(a.service_id, a.offer_type): a for a in db.scalars(
        select(Availability).where(Availability.media_item_id == item.id,
                                   Availability.country == country))}
    seen: set[tuple[int, str]] = set()
    link = country_data.get("link")
    for offer_type, tmdb_field in [("flatrate", "flatrate"), ("free", "free"),
                                   ("ads", "ads"), ("rent", "rent"), ("buy", "buy")]:
        for provider in country_data.get(tmdb_field, []) or []:
            svc = _resolve_service(db, provider, by_tmdb_id, by_key)
            sig = (svc.id, offer_type)
            if sig in seen:
                continue
            seen.add(sig)
            row = existing.get(sig)
            if row is None:
                db.add(Availability(media_item_id=item.id, service_id=svc.id,
                                    country=country, offer_type=offer_type, tmdb_link=link))
            else:
                row.tmdb_link = link
    # Remove offers TMDB no longer reports (availability refresh, not append-only).
    for sig, row in existing.items():
        if sig not in seen:
            db.delete(row)


async def run_sync(db: Session, api_key: str, country: str,
                   extra_countries: list[str] | None = None,
                   pages: int = DEFAULT_SYNC_PAGES) -> dict:
    """Full catalog sync. One watch-providers call returns EVERY region, so
    tracking extra regions costs zero additional TMDB requests."""
    client = TMDBClient(api_key)
    countries = [country] + [c for c in (extra_countries or []) if c != country]
    sync_state.update(status="running", detail="fetching catalog", error_kind=None)
    try:
        genre_maps = {
            "movie": await client.genres("movie"),
            "tv": await client.genres("tv"),
        }
        pages = max(1, min(pages, MAX_SYNC_PAGES))
        items: list[MediaItem] = []
        seen: set[tuple[str, int | None]] = set()
        # Popular skews to new releases (paid subscriptions); top-rated brings the
        # back-catalog that free/ad-supported services actually carry.
        for media_type in ("movie", "tv"):
            for kind in ("popular", "top_rated"):
                for page in range(1, pages + 1):
                    for r in await client.titles_list(media_type, kind, page=page, region=country):
                        if (media_type, r["id"]) in seen:
                            continue
                        seen.add((media_type, r["id"]))
                        items.append(_upsert_media_item(db, media_type, r, genre_maps[media_type]))
        # Availability refresh covers the WHOLE catalog, including titles that
        # were imported via search and are no longer in the popular pages.
        for it in db.scalars(select(MediaItem).where(MediaItem.media_type.in_(["movie", "tv"]))):
            if (it.media_type, it.tmdb_id) not in seen:
                seen.add((it.media_type, it.tmdb_id))
                items.append(it)
        db.commit()

        sync_state["detail"] = (
            f"refreshing availability for {len(items)} titles · {', '.join(countries)}")
        by_tmdb_id, by_key = _service_lookup(db)
        sem = asyncio.Semaphore(_PROVIDER_CONCURRENCY)

        async def fetch(it: MediaItem) -> tuple[MediaItem, dict]:
            async with sem:
                if it.tmdb_id is None:
                    return it, {}
                try:
                    return it, await client.watch_providers(it.media_type, it.tmdb_id)
                except Exception as exc:  # keep the sync going; log without secrets
                    logger.warning("watch_providers failed for %s/%s: %s",
                                   it.media_type, it.tmdb_id, exc)
                    return it, {}

        results = await asyncio.gather(*(fetch(it) for it in items))
        # Write in chunks: commit every N titles (releasing the write-lock so
        # interactive requests get a turn) and yield the event loop between
        # chunks, instead of one long lock-held transaction that stalls reads.
        for i, (item, regions) in enumerate(results):
            for c in countries:
                country_data = regions.get(c)
                if country_data:
                    _upsert_availability(db, item, c, country_data, by_tmdb_id, by_key)
            if (i + 1) % 100 == 0:
                db.commit()
                await asyncio.sleep(0)
        # Prune regions no longer tracked.
        db.execute(sa_delete(Availability).where(Availability.country.notin_(countries)))
        db.commit()

        # Predict a likely streaming home for UPCOMING titles that came back with
        # no availability, so their "not streaming yet" cards can hint where they
        # will land. Bounded — upcoming, unstreamed titles are a small minority.
        cur_year = datetime.now(UTC).year

        def _no_stream(it: MediaItem) -> bool:
            return not any(a.country == country and a.offer_type in ("flatrate", "free", "ads")
                           for a in it.availabilities)

        upcoming = [it for it in items
                    if it.tmdb_id is not None and not it.extra.get("expected_checked")
                    and (it.year or 9999) >= cur_year and _no_stream(it)][:400]

        async def infer_one(it: MediaItem) -> None:
            if it.tmdb_id is None:
                return
            async with sem:
                try:
                    detail = await client.detail(it.media_type, it.tmdb_id)
                except Exception as exc:
                    logger.debug("detail fetch failed for %s: %s", it.id, exc)
                    return
                it.extra = {**it.extra, "expected_checked": True,
                            "expected_service": _expected_from_detail(detail, it.media_type, by_key)}

        if upcoming:
            sync_state["detail"] = f"inferring likely home for {len(upcoming)} upcoming titles"
            await asyncio.gather(*(infer_one(it) for it in upcoming))
            db.commit()

        now = datetime.now(UTC).isoformat()
        settings_store.set_setting(db, "catalog_synced_at", now)
        sync_state.update(status="idle", detail=None, last_completed=now, error_kind=None)
        return {"titles": len(items)}
    except Exception as exc:
        db.rollback()
        kind = "auth" if isinstance(exc, TMDBError) and "rejected the key" in str(exc) else "network"
        sync_state.update(status="error", detail=str(exc), error_kind=kind)
        raise


async def import_title(db: Session, api_key: str, media_type: str, tmdb_id: int,
                       countries: str | list[str]) -> MediaItem:
    """Import a single title found via search (M2): detail + availability for
    every tracked region, on demand."""
    if isinstance(countries, str):
        countries = [countries]
    client = TMDBClient(api_key)
    detail = await client.detail(media_type, tmdb_id)
    genre_names = [g["name"] for g in detail.get("genres", [])]
    r = {
        "id": tmdb_id,
        "title": detail.get("title") or detail.get("name"),
        "release_date": detail.get("release_date") or detail.get("first_air_date") or "",
        "overview": detail.get("overview"),
        "poster_path": detail.get("poster_path"),
        "backdrop_path": detail.get("backdrop_path"),
        "genre_ids": [],
        "popularity": detail.get("popularity", 0.0),
        "vote_average": detail.get("vote_average"),
    }
    item = _upsert_media_item(db, media_type, r, {})
    item.genres = genre_names
    runtime = detail.get("runtime") or (detail.get("episode_run_time") or [None])[0]
    item.runtime_minutes = runtime
    regions = await client.watch_providers(media_type, tmdb_id)
    by_tmdb_id, by_key = _service_lookup(db)
    for c in countries:
        country_data = regions.get(c)
        if country_data:
            _upsert_availability(db, item, c, country_data, by_tmdb_id, by_key)
    db.commit()
    return item


# ---------- Read side (shelf / title page) ----------

def search_query(title: str) -> str:
    """Simplify a title for service search boxes: strict search engines choke on
    subtitles and parentheticals ("All Elite Wrestling: Dynamite" → Tubi lists
    "AEW: Dynamite"). The stem matches far more often than the full string."""
    q = re.sub(r"\s*\([^)]*\)", "", title).strip()
    if ":" in q:
        stem = q.split(":", 1)[0].strip()
        if len(stem) >= 3:
            q = stem
    return q or title


def _deep_link(service: Service, title: str, tmdb_link: str | None) -> str | None:
    """Fallback chain per plan failure modes: template → TMDB watch page → homepage."""
    if service.deep_link_template:
        return service.deep_link_template.replace("{query}", urllib.parse.quote(search_query(title)))
    return tmdb_link or service.homepage_url


def _badge(avail: Availability, item: MediaItem, subscribed_ids: set[int]) -> dict:
    svc = avail.service
    return {
        "service_key": svc.key,
        "service_name": svc.name,
        "logo": svc.logo_url,
        "offer_type": avail.offer_type,
        "owned": svc.id in subscribed_ids and avail.offer_type in ("flatrate", "free", "ads"),
        "deep_link": _deep_link(svc, item.title, avail.tmdb_link),
        "price": avail.price,
        "signup_url": svc.signup_url,
        "sso_note": svc.sso_note,
        "country": avail.country,
        # Availability rows show last-checked age on hover (plan failure modes).
        "checked_at": avail.updated_at.isoformat() if avail.updated_at else None,
    }


def serialize_item(item: MediaItem, subscribed_ids: set[int], country: str) -> dict:
    badges = [_badge(a, item, subscribed_ids)
              for a in item.availabilities if a.country == country]
    # Owned first, then streaming before rent/buy.
    order = {"flatrate": 0, "free": 1, "ads": 2, "rent": 3, "buy": 4}
    badges.sort(key=lambda b: (not b["owned"], order.get(b["offer_type"], 9)))
    owned = any(b["owned"] for b in badges)
    unlock = next((b for b in badges if not b["owned"] and b["offer_type"] == "flatrate"), None)
    return {
        "id": item.id,
        "media_type": item.media_type,
        "tmdb_id": item.tmdb_id,
        "title": item.title,
        "year": item.year,
        "poster": poster_url(item.poster_path),
        "backdrop": poster_url(item.backdrop_path, "w780"),
        "rating": item.rating,
        "genres": item.genres,
        "owned": owned,
        "unlock_service": unlock["service_name"] if unlock else None,
        "badges": badges,
        # Studio-inferred "expected on X" hint — only when nothing streams (the
        # "not streaming yet" card); a prediction, so the UI dims/labels it.
        "expected_service": item.extra.get("expected_service") if not badges else None,
    }


def serialize_item_multi(item: MediaItem, subs: set[int], countries: list[str]) -> dict:
    """"All regions" serialization: home badges plain, other regions tagged
    with their code; owned means owned anywhere you track."""
    base = serialize_item(item, subs, countries[0])
    for c in countries[1:]:
        for b in serialize_item(item, subs, c)["badges"]:
            b["service_name"] = f"{b['service_name']} · {c}"
            base["badges"].append(b)
    base["owned"] = any(b["owned"] for b in base["badges"])
    unlock = next((b for b in base["badges"]
                   if not b["owned"] and b["offer_type"] == "flatrate"), None)
    base["unlock_service"] = unlock["service_name"] if unlock else None
    return base


def _serialize_pool(items: Sequence[MediaItem], subs: set[int], country: str,
                    all_countries: list[str] | None) -> list[dict]:
    if all_countries and len(all_countries) > 1:
        return [serialize_item_multi(i, subs, all_countries) for i in items]
    return [serialize_item(i, subs, country) for i in items]


def subscribed_service_ids(db: Session) -> set[int]:
    return set(db.scalars(select(UserSub.service_id).where(UserSub.subscribed.is_(True))))


_CHANNEL_SUFFIXES = (" amazon channel", " roku premium channel", " apple tv channel")


def _channel_parent_key(label: str) -> str | None:
    low = label.lower()
    for suffix in _CHANNEL_SUFFIXES:
        if low.endswith(suffix):
            base = low[: -len(suffix)].strip()
            return _TMDB_NAME_OVERRIDES.get(base, _slugify(base))
    return None


def _service_rails(serialized: list[dict]) -> list[dict]:
    """By-service shelf view: one rail per service — what's on Netflix, Prime, …
    Subscribed services first, then the rest by catalog size."""
    by_service: dict[str, dict] = {}
    for s in serialized:
        for b in s["badges"]:
            if b["offer_type"] not in ("flatrate", "free", "ads"):
                continue
            rail = by_service.setdefault(b["service_key"], {
                "key": f"svc_{b['service_key']}",
                "label": b["service_name"],
                "owned": b["owned"],
                "items": [],
                "_seen": set(),
            })
            if s["id"] not in rail["_seen"]:
                rail["_seen"].add(s["id"])
                rail["items"].append(s)

    # Fold "<X> Amazon/Roku/Apple TV Channel" rails into their parent service's
    # rail — same content, one shelf row. The checklist keeps them separate
    # (a channel is its own purchase); this is display reconciliation only.
    for svc_key in list(by_service):
        rail = by_service[svc_key]
        parent_key = _channel_parent_key(rail["label"])
        if not parent_key or parent_key == svc_key:
            continue
        parent = by_service.get(parent_key)
        if parent is None:
            continue
        for item in rail["items"]:
            if item["id"] not in parent["_seen"]:
                parent["_seen"].add(item["id"])
                parent["items"].append(item)
        parent["owned"] = parent["owned"] or rail["owned"]
        del by_service[svc_key]
    rails = sorted(by_service.values(), key=lambda r: (not r["owned"], -len(r["items"])))
    for r in rails:
        del r["_seen"]
        r["total"] = len(r["items"])
    shown, overflow = rails[:15], rails[15:]
    # Nothing silently vanishes from this view: titles only on smaller services
    # land in "Other services"; titles nowhere land in the explicit tail rail.
    shown_ids = {i["id"] for r in shown for i in r["items"]}
    other = [i for r in overflow for i in r["items"] if i["id"] not in shown_ids]
    other = list({i["id"]: i for i in other}.values())
    if other:
        shown.append({"key": "svc_other", "label": "Other services", "owned": False,
                      "items": other, "total": len(other)})
    not_streaming = [s for s in serialized
                     if not any(b["offer_type"] in ("flatrate", "free", "ads")
                                for b in s["badges"])]
    if not_streaming:
        shown.append({"key": "svc_none", "label": "Not streaming anywhere", "owned": False,
                      "items": not_streaming, "total": len(not_streaming)})
    return shown


def _imported_list_rails(db: Session, by_id: dict[int, dict]) -> list[dict]:
    """Rails built from imported lists (companion tool): unified Watchlist, then
    per-service Top 10 (rank-ordered) and Leaving-soon. `by_id` is the already
    filtered/serialized pool so these respect region, media-type and filter."""
    from app.models import LibraryEntry, Service

    rows = db.execute(
        select(LibraryEntry, Service.name, Service.key, Service.logo_url)
        .join(Service, Service.id == LibraryEntry.service_id)
        .where(LibraryEntry.entry_type.in_(["watchlist", "top10", "leaving_soon"]),
               LibraryEntry.media_item_id.isnot(None))
    ).all()

    # Watchlist is unified across services, so each card carries its source
    # list ("on your Tubi list") — the availability badge shows where it streams,
    # which can differ from the list you added it to.
    watchlist_map: dict[int, dict] = {}
    # Top 10s across all services fold into ONE "Popular right now" rail: a title
    # trending on more services ranks higher, ties broken by best rank.
    popular: dict[int, dict] = {}     # item_id -> {item, services:set, best:int}
    leaving: dict[str, dict] = {}
    for entry, svc_name, svc_key, svc_logo in rows:
        item = by_id.get(entry.media_item_id)
        if item is None:
            continue
        if entry.entry_type == "watchlist":
            wl = watchlist_map.get(item["id"])
            if wl is None:
                watchlist_map[item["id"]] = {**item, "list_source": svc_name,
                                             "list_source_logo": svc_logo}
            elif svc_name not in wl["list_source"]:
                wl["list_source"] += f", {svc_name}"
                wl["list_source_logo"] = None  # multiple sources → name, not one logo
        elif entry.entry_type == "top10":
            rank = (entry.payload or {}).get("rank") or 99
            agg = popular.setdefault(item["id"], {"item": item, "services": set(), "best": 99})
            agg["services"].add(svc_name)
            agg["best"] = min(agg["best"], rank)
        elif entry.entry_type == "leaving_soon":
            g = leaving.setdefault(svc_key, {"name": svc_name, "items": []})
            g["items"].append(item)

    rails: list[dict] = []
    if watchlist_map:
        rails.append({"key": "watchlist", "label": "Watchlist",
                      "items": list(watchlist_map.values())})
    if popular:
        ranked = sorted(popular.values(), key=lambda a: (-len(a["services"]), a["best"]))
        # No per-rail cap here — the shelf's general 40-item rail cap applies, with
        # a "see all N" into the full browse grid for the remainder.
        rails.append({"key": "popular", "label": "Popular right now",
                      "items": [a["item"] for a in ranked]})
    for svc_key, g in sorted(leaving.items(), key=lambda kv: -len(kv[1]["items"])):
        rails.append({"key": f"leaving_{svc_key}", "label": f"Leaving {g['name']} soon",
                      "items": g["items"]})
    return rails


def _apply_filter(serialized: list[dict], flt: str) -> list[dict]:
    """Ownership filter, applied BEFORE rails are capped — so 'On my services'
    means every owned title, not owned ∩ top-40-by-popularity."""
    if flt == "mine":
        return [s for s in serialized if s["owned"]]
    if flt == "elsewhere":
        return [s for s in serialized if not s["owned"]]
    if flt.startswith("svc:"):
        key = flt.removeprefix("svc:")
        return [s for s in serialized
                if any(b["owned"] and b["service_key"] == key for b in s["badges"])]
    return serialized


def _category_rails(pool: list[dict]) -> list[dict]:
    rails = [
        {"key": "movies", "label": "Movies",
         "items": [s for s in pool if s["media_type"] == "movie"]},
        {"key": "shows", "label": "Shows",
         "items": [s for s in pool if s["media_type"] == "tv"]},
    ]
    # Per-genre rails for the most common genres.
    genre_counts: dict[str, int] = {}
    for s in pool:
        for g in s["genres"]:
            genre_counts[g] = genre_counts.get(g, 0) + 1
    top_genres = sorted(genre_counts, key=lambda g: genre_counts[g], reverse=True)[:4]
    for g in top_genres:
        rails.append({"key": f"genre_{_slugify(g)}", "label": g,
                      "items": [s for s in pool if g in s["genres"]]})
    return rails


def _sort_clause(sort: str) -> list:
    """order_by terms for the user-chosen sort. Default popularity-desc; A→Z is
    case-insensitive; newest-first leaves NULL years last (SQLite sorts them last
    under DESC) and breaks ties by popularity."""
    if sort == "title":
        return [func.lower(MediaItem.title).asc()]
    if sort == "year":
        return [MediaItem.year.desc(), MediaItem.popularity.desc()]
    return [MediaItem.popularity.desc()]


def build_shelf(db: Session, country: str, view: str = "categories",
                flt: str = "all", media_type: str | None = None,
                all_countries: list[str] | None = None,
                sort: str = "popularity") -> dict:
    items = db.scalars(
        select(MediaItem)
        .where(MediaItem.media_type.in_(["movie", "tv"]))
        .options(selectinload(MediaItem.availabilities).selectinload(Availability.service))
        .order_by(*_sort_clause(sort))
    ).all()
    subs = subscribed_service_ids(db)
    serialized = _serialize_pool(items, subs, country, all_countries)
    # Media-type tabs (Movies/Shows) scope everything below; "All" leaves it unified.
    if media_type in ("movie", "tv"):
        serialized = [s for s in serialized if s["media_type"] == media_type]

    # Imported-list rails (Watchlist, Top 10, Leaving soon) are personal, not
    # catalog rails: they lead BOTH views. Under "All"/"On my services" they
    # respect the ownership filter (so "On my services" shows only what you can
    # actually watch — all gold, no gray). Exception: "Popular right now" is a
    # discovery rail, so under "Not on my services" it shows the FULL aggregated
    # trending list (Watchlist/Leaving stay hidden there — they're personal).
    if flt in ("all", "mine"):
        list_rails = _imported_list_rails(db, {s["id"]: s for s in _apply_filter(serialized, flt)})
    elif flt == "elsewhere":
        list_rails = [r for r in _imported_list_rails(db, {s["id"]: s for s in serialized})
                      if r["key"] == "popular"]
    else:
        list_rails = []

    if view == "services":
        # Rails are built from everything; the filter then selects RAILS —
        # your services vs the rest — never items inside another service's rail.
        rails = _service_rails(serialized)
        if flt == "mine":
            rails = [r for r in rails if r.get("owned")]
        elif flt == "elsewhere":
            rails = [r for r in rails if not r.get("owned")]
        elif flt.startswith("svc:"):
            rails = [r for r in rails if r["key"] == f"svc_{flt.removeprefix('svc:')}"]
    else:
        pool = _apply_filter(serialized, flt)
        rails = _category_rails(pool)
    rails = list_rails + rails

    service_count = len({b["service_key"] for s in serialized for b in s["badges"]})
    # Rails cap their length for the horizontal scroll; total counts let the UI
    # offer "see all N" into the full-grid browse page — filter-aware, so the
    # number always matches what clicking it opens.
    for r in rails:
        r["total"] = len(r["items"])
        r["items"] = r["items"][:40]
        r.pop("_seen", None)
    # Chips offer only subscribed services that actually appear on this shelf —
    # music services (Spotify, YouTube Music) hold no movie/TV availability and
    # would always filter to nothing.
    chip_services: dict[str, str] = {}
    for s in serialized:
        for b in s["badges"]:
            if b["owned"]:
                existing = chip_services.get(b["service_key"])
                # Prefer the untagged (home-region) name over "Name · CC".
                if existing is None or ("·" in existing and "·" not in b["service_name"]):
                    chip_services[b["service_key"]] = b["service_name"]
    subscribed_services = sorted(
        ({"key": k, "name": v} for k, v in chip_services.items()),
        key=lambda x: x["name"])
    return {
        "stats": {"titles": len(serialized), "services": service_count,
                  "subscribed": len(subs)},
        "rails": [r for r in rails if r["items"]],
        "subscribed_services": subscribed_services,
        "filter": flt,
        "sync": dict(sync_state),
        "country": country,
        # Stale-catalog banner data: the shelf never blanks, it just shows its age.
        "synced_at": settings_store.get_setting(db, "catalog_synced_at"),
    }


def build_rail(db: Session, country: str, rail_key: str, flt: str = "all",
               media_type: str | None = None,
               all_countries: list[str] | None = None,
               sort: str = "popularity") -> dict | None:
    """Full, uncapped contents of one shelf rail — the "see all" browse page."""
    items = db.scalars(
        select(MediaItem)
        .where(MediaItem.media_type.in_(["movie", "tv"]))
        .options(selectinload(MediaItem.availabilities).selectinload(Availability.service))
        .order_by(*_sort_clause(sort))
    ).all()
    subs = subscribed_service_ids(db)
    serialized = _serialize_pool(items, subs, country, all_countries)
    if media_type in ("movie", "tv"):
        serialized = [s for s in serialized if s["media_type"] == media_type]

    if rail_key.startswith("svc_"):
        # Reuse the exact rail construction (channel folds, other, none) so
        # "see all" always matches what the shelf showed. Service rails are
        # whole-service views; the ownership filter selects rails, not items.
        rails = _service_rails(serialized)
        rail = next((r for r in rails if r["key"] == rail_key), None)
        if rail is None:
            return None
        rail.pop("_seen", None)
        return {"key": rail_key, "label": rail["label"], "items": rail["items"]}

    pool = _apply_filter(serialized, flt)
    if rail_key in ("watchlist", "popular") or rail_key.startswith("leaving_"):
        # "Popular right now" is a discovery rail: under "Not on my services" it
        # uses the full trending list (matching the shelf), not the not-owned slice.
        lookup = serialized if (rail_key == "popular" and flt == "elsewhere") else pool
        rail = next((r for r in _imported_list_rails(db, {s["id"]: s for s in lookup})
                     if r["key"] == rail_key), None)
        return rail  # None → 404 in the endpoint
    if rail_key == "movies":
        return {"key": rail_key, "label": "Movies",
                "items": [s for s in pool if s["media_type"] == "movie"]}
    if rail_key == "shows":
        return {"key": rail_key, "label": "Shows",
                "items": [s for s in pool if s["media_type"] == "tv"]}
    if rail_key.startswith("genre_"):
        slug = rail_key.removeprefix("genre_")
        label = next((g for s in serialized for g in s["genres"] if _slugify(g) == slug), None)
        if label is None:
            return None
        return {"key": rail_key, "label": label,
                "items": [s for s in pool if label in s["genres"]]}
    return None


async def world_availability(api_key: str | None, media_type: str, tmdb_id: int | None,
                             exclude: list[str]) -> list[dict]:
    """"In other regions": streaming regions beyond the tracked ones (geography
    axis — deliberately NOT named "elsewhere", which is the ownership axis in
    §4.2/§4.4). Display-only information (plan boundary: no circumvention
    guidance). Reuses the TMDB response already cached by the sync."""
    if not api_key or tmdb_id is None:
        return []
    try:
        regions = await TMDBClient(api_key).watch_providers(media_type, tmdb_id)
    except Exception:
        return []
    out = []
    for country in sorted(regions):
        if country in exclude or len(country) != 2:
            continue
        names: list[str] = []
        for field in ("flatrate", "free", "ads"):
            for p in regions[country].get(field, []) or []:
                if p.get("provider_name") and p["provider_name"] not in names:
                    names.append(p["provider_name"])
        if names:
            out.append({"country": country, "services": names[:4],
                        "more": max(0, len(names) - 4)})
    return out[:40]


async def ensure_trailer(db: Session, item_id: int, api_key: str | None) -> None:
    """Lazily fetch the trailer's YouTube key on first title-page visit (M3)."""
    item = db.get(MediaItem, item_id)
    if item is None or item.extra.get("videos_checked") or not api_key or item.tmdb_id is None:
        return
    try:
        videos = await TMDBClient(api_key).videos(item.media_type, item.tmdb_id)
    except Exception as exc:
        logger.debug("trailer fetch failed for %s: %s", item_id, exc)
        return
    trailer = next(
        (v for v in videos if v.get("site") == "YouTube" and v.get("type") == "Trailer"),
        next((v for v in videos if v.get("site") == "YouTube"), None),
    )
    item.extra = {**item.extra, "videos_checked": True,
                  "trailer_youtube_id": trailer.get("key") if trailer else None}
    db.commit()


async def ensure_ratings(db: Session, item_id: int, tmdb_key: str | None,
                         omdb_key: str | None) -> None:
    """Lazily enrich a title with IMDb/RT/Metacritic on first view, via OMDb
    (optional). No-op without an OMDb key — TMDB's own score always shows."""
    item = db.get(MediaItem, item_id)
    if item is None or not omdb_key or item.tmdb_id is None:
        return
    if item.extra.get("ratings_checked"):
        return
    from app.providers.omdb import OMDbClient, OMDbError

    imdb_id = item.extra.get("imdb_id")
    if not imdb_id and tmdb_key:
        try:
            ext = await TMDBClient(tmdb_key).external_ids(item.media_type, item.tmdb_id)
            imdb_id = ext.get("imdb_id")
        except Exception as exc:
            logger.debug("external_ids failed for %s: %s", item_id, exc)
    ratings: dict = {}
    if imdb_id:
        try:
            ratings = await OMDbClient(omdb_key).ratings(imdb_id)
        except OMDbError as exc:
            logger.debug("OMDb ratings failed for %s: %s", imdb_id, exc)
            return  # transient — don't mark checked, retry next view
    item.extra = {**item.extra, "ratings_checked": True, "imdb_id": imdb_id, "ratings": ratings}
    db.commit()


def _expected_from_detail(detail: dict, media_type: str,
                          by_key: dict[str, Service]) -> dict | None:
    """Turn an inferred (key, name) into the card-ready dict, pulling the real
    service's display name + logo when we carry it. A prediction, not data."""
    from app.services.studio_home import infer_expected

    hit = infer_expected(detail, media_type)
    if hit is None:
        return None
    key, name = hit
    svc = by_key.get(key)
    return {"service_key": key,
            "service_name": svc.name if svc else name,
            "logo": svc.logo_url if svc else None}


async def ensure_expected_service(db: Session, item_id: int, api_key: str | None) -> None:
    """Lazily predict where an UPCOMING, not-yet-streaming title will likely land,
    from its studio/network (see ``studio_home``). Cached in ``extra`` like the
    other enrichers. A heuristic — never a confirmed availability badge."""
    item = db.get(MediaItem, item_id)
    if item is None or not api_key or item.tmdb_id is None:
        return
    if item.extra.get("expected_checked"):
        return
    # Only upcoming titles get a prediction — an old title with no availability
    # isn't "coming", it's just unlicensed. And skip anything already streaming.
    upcoming = item.year is None or item.year >= datetime.now(UTC).year
    streaming = any(a.offer_type in ("flatrate", "free", "ads") for a in item.availabilities)
    if not upcoming or streaming:
        item.extra = {**item.extra, "expected_checked": True, "expected_service": None}
        db.commit()
        return
    try:
        detail = await TMDBClient(api_key).detail(item.media_type, item.tmdb_id)
    except Exception as exc:
        logger.debug("detail fetch failed for %s: %s", item_id, exc)
        return  # transient — don't mark checked, retry next view
    _, by_key = _service_lookup(db)
    item.extra = {**item.extra, "expected_checked": True,
                  "expected_service": _expected_from_detail(detail, item.media_type, by_key)}
    db.commit()


def build_title(db: Session, item_id: int, country: str,
                all_countries: list[str] | None = None) -> dict | None:
    from app.services import playback as playback_service

    item = db.get(MediaItem, item_id, options=[
        selectinload(MediaItem.availabilities).selectinload(Availability.service)])
    if item is None:
        return None
    subs = subscribed_service_ids(db)
    if all_countries and len(all_countries) > 1:
        data = serialize_item_multi(item, subs, all_countries)
    else:
        data = serialize_item(item, subs, country)
    data["overview"] = item.overview
    data["runtime_minutes"] = item.runtime_minutes
    data["country"] = country
    data["on_your_services"] = [b for b in data["badges"] if b["owned"]]
    data["elsewhere"] = [b for b in data["badges"] if not b["owned"]]
    # Movies/TV play = deep links only; DRM never gets an in-app engine.
    data["play"] = playback_service.video_options(data["badges"])
    data["trailer_youtube_id"] = item.extra.get("trailer_youtube_id")
    data["ratings"] = item.extra.get("ratings") or {}  # imdb/rt/metacritic (OMDb)
    return data
