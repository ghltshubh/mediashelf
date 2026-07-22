"""Podcast subscriptions (M8).

Subscribe by RSS feed URL or bulk-import an OPML file; episodes stream in-app
through a plain HTML5 <audio> element. Podcast RSS is an open standard, so there
is nothing to authenticate — this works for every user with zero setup, no
account, no API key.

Network fetch is isolated in ``_fetch`` (async ``httpx``, following the provider
convention) so tests can monkeypatch a single seam. Parsing uses ``feedparser``;
OPML uses stdlib ``xml.etree`` — no extra dependency.
"""

import logging
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

import feedparser
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Podcast, PodcastEpisode, utcnow

logger = logging.getLogger(__name__)

USER_AGENT = "MediaShelf/0.1 (podcast subscriber)"


# ---------- network seam ----------

async def _fetch(
    feed_url: str, etag: str | None = None, last_modified: str | None = None
) -> tuple[int, bytes, str | None, str | None]:
    """GET the feed with a conditional-GET when validators are known.
    Returns (status_code, content, etag, last_modified)."""
    headers = {"User-Agent": USER_AGENT}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
        resp = await client.get(feed_url, headers=headers)
    return (resp.status_code, resp.content,
            resp.headers.get("etag"), resp.headers.get("last-modified"))


# ---------- parsing ----------

def _parse_duration(raw: object) -> int | None:
    """iTunes duration is 'HH:MM:SS', 'MM:SS', or a bare seconds count."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if ":" in text:
        try:
            nums = [int(p) for p in text.split(":")]
        except ValueError:
            return None
        secs = 0
        for n in nums:
            secs = secs * 60 + n
        return secs
    try:
        return int(float(text))
    except ValueError:
        return None


def _entry_datetime(entry: dict) -> datetime | None:
    st = entry.get("published_parsed") or entry.get("updated_parsed")
    if not st:
        return None
    try:
        return datetime(st[0], st[1], st[2], st[3], st[4], st[5], tzinfo=UTC)
    except (ValueError, TypeError, IndexError):
        return None


def _entry_audio(entry: dict) -> str | None:
    for enc in entry.get("enclosures") or []:
        href = enc.get("href")
        typ = enc.get("type") or ""
        if href and (typ.startswith("audio") or not typ):
            return href
    for link in entry.get("links") or []:
        if link.get("rel") == "enclosure" and link.get("href"):
            return link["href"]
    return None


def _image_href(obj: dict) -> str | None:
    img = obj.get("image")
    if isinstance(img, dict):
        return img.get("href")
    return None


def _parse(content: bytes) -> dict:
    parsed = feedparser.parse(content)
    feed = parsed.feed
    episodes = []
    for e in parsed.entries:
        audio = _entry_audio(e)
        if not audio:
            continue  # no enclosure → nothing to play
        episodes.append({
            "guid": e.get("id") or e.get("guid") or audio,
            "title": e.get("title") or "",
            "description": e.get("summary"),
            "audio_url": audio,
            "duration_seconds": _parse_duration(e.get("itunes_duration")),
            "published_at": _entry_datetime(e),
            "image_url": _image_href(e),
        })
    return {
        "title": feed.get("title") or "",
        "author": feed.get("author"),
        "description": feed.get("subtitle") or feed.get("summary"),
        "image_url": _image_href(feed),
        "website": feed.get("link"),
        "episodes": episodes,
    }


# ---------- subscription operations ----------

def _upsert_episodes(db: Session, podcast: Podcast, episodes: list[dict]) -> int:
    existing = {ep.guid for ep in podcast.episodes}
    added = 0
    for ep in episodes:
        if ep["guid"] in existing:
            continue
        db.add(PodcastEpisode(podcast_id=podcast.id, **ep))
        existing.add(ep["guid"])
        added += 1
    return added


async def subscribe(db: Session, feed_url: str) -> Podcast:
    """Subscribe to a feed (idempotent — an existing subscription is refreshed)."""
    feed_url = feed_url.strip()
    if not feed_url:
        raise ValueError("Feed URL is required")
    existing = db.scalar(select(Podcast).where(Podcast.feed_url == feed_url))
    if existing:
        await refresh(db, existing)
        return existing
    status, content, etag, last_modified = await _fetch(feed_url)
    if status >= 400 or not content:
        raise ValueError(f"Could not fetch feed (HTTP {status})")
    meta = _parse(content)
    podcast = Podcast(
        feed_url=feed_url,
        title=meta["title"] or feed_url,
        author=meta["author"],
        description=meta["description"],
        image_url=meta["image_url"],
        website=meta["website"],
        etag=etag,
        last_modified=last_modified,
        last_fetched_at=utcnow(),
    )
    db.add(podcast)
    db.flush()
    _upsert_episodes(db, podcast, meta["episodes"])
    db.commit()
    db.refresh(podcast)
    return podcast


async def refresh(db: Session, podcast: Podcast) -> int:
    """Re-fetch a feed; insert only episodes not already stored. Returns the
    number of new episodes. A 304 (conditional GET) is a no-op."""
    status, content, etag, last_modified = await _fetch(
        podcast.feed_url, etag=podcast.etag, last_modified=podcast.last_modified)
    podcast.last_fetched_at = utcnow()
    if status == 304 or status >= 400 or not content:
        db.commit()
        return 0
    meta = _parse(content)
    if meta["title"]:
        podcast.title = meta["title"]
    podcast.author = meta["author"] or podcast.author
    podcast.description = meta["description"] or podcast.description
    podcast.image_url = meta["image_url"] or podcast.image_url
    podcast.website = meta["website"] or podcast.website
    podcast.etag = etag
    podcast.last_modified = last_modified
    added = _upsert_episodes(db, podcast, meta["episodes"])
    db.commit()
    return added


async def refresh_all(db: Session) -> int:
    """Nightly job entry point: refresh every subscription, isolating failures."""
    total = 0
    for podcast in db.scalars(select(Podcast)).all():
        try:
            total += await refresh(db, podcast)
        except Exception:
            logger.exception("podcast refresh failed for %s", podcast.feed_url)
    return total


def unsubscribe(db: Session, podcast_id: int) -> bool:
    podcast = db.get(Podcast, podcast_id)
    if not podcast:
        return False
    db.delete(podcast)  # cascade removes its episodes
    db.commit()
    return True


# ---------- OPML ----------

async def import_opml(db: Session, xml_bytes: bytes) -> list[Podcast]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError("That file is not valid OPML") from exc
    urls = [
        (o.get("xmlUrl") or o.get("xmlurl") or "").strip()
        for o in root.iter("outline")
    ]
    subscribed: list[Podcast] = []
    for url in urls:
        if not url:
            continue
        try:
            subscribed.append(await subscribe(db, url))
        except Exception:
            logger.warning("OPML import: could not subscribe to %s", url)
    return subscribed


def export_opml(db: Session) -> str:
    opml = ET.Element("opml", version="2.0")
    head = ET.SubElement(opml, "head")
    ET.SubElement(head, "title").text = "MediaShelf podcasts"
    body = ET.SubElement(opml, "body")
    for podcast in db.scalars(select(Podcast).order_by(Podcast.title)).all():
        attrs = {"type": "rss", "text": podcast.title,
                 "title": podcast.title, "xmlUrl": podcast.feed_url}
        if podcast.website:
            attrs["htmlUrl"] = podcast.website
        ET.SubElement(body, "outline", attrs)
    return ET.tostring(opml, encoding="unicode", xml_declaration=True)


# ---------- serialization ----------

_EPOCH = datetime.min.replace(tzinfo=UTC)


def episode_dict(ep: PodcastEpisode) -> dict:
    return {
        "id": ep.id,
        "guid": ep.guid,
        "title": ep.title,
        "description": ep.description,
        "audio_url": ep.audio_url,
        "duration_seconds": ep.duration_seconds,
        "published_at": ep.published_at.isoformat() if ep.published_at else None,
        "image_url": ep.image_url,
    }


def podcast_dict(podcast: Podcast, with_episodes: bool = False) -> dict:
    eps = sorted(podcast.episodes, key=lambda e: e.published_at or _EPOCH, reverse=True)
    data = {
        "id": podcast.id,
        "feed_url": podcast.feed_url,
        "title": podcast.title,
        "author": podcast.author,
        "description": podcast.description,
        "image_url": podcast.image_url,
        "website": podcast.website,
        "episode_count": len(eps),
        "last_fetched_at": podcast.last_fetched_at.isoformat() if podcast.last_fetched_at else None,
        "latest_episode": episode_dict(eps[0]) if eps else None,
    }
    if with_episodes:
        data["episodes"] = [episode_dict(e) for e in eps]
    return data


def list_podcasts(db: Session) -> list[dict]:
    rows = db.scalars(select(Podcast).order_by(Podcast.title)).all()
    return [podcast_dict(p) for p in rows]
