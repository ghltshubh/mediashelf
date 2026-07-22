"""yt-dlp metadata provider (M6) — the ONLY place yt-dlp is invoked.

yt-dlp is an optional, separately-installed community plugin. It is never
bundled and never a runtime dependency; the app detects its presence and lights
up zero-quota YouTube reads when the user enables the toggle.

METADATA ONLY — hard contract (plan §Constraints):
  * Allowed: `--dump-json` / `--flat-playlist` / `--skip-download` extraction of
    PUBLIC channel / playlist / video metadata to save API quota.
  * Forbidden anywhere: downloading media, extracting stream URLs, format
    selection, or any playback path through yt-dlp.
Every invocation below passes `--skip-download` and never `-f` / a format —
grep this file for `--skip-download` (present) and `download`/`format` (absent)
to verify the boundary.
"""

import json
import logging
import shutil
import subprocess

from sqlalchemy.orm import Session

from app import settings_store

logger = logging.getLogger(__name__)

_BINARY = "yt-dlp"
_TIMEOUT = 20  # seconds; a metadata search is fast, so a hang means trouble.
# Metadata-only flags. Intentionally no `-f`/format/download flag ever.
_META_FLAGS = ["--dump-json", "--flat-playlist", "--skip-download",
               "--no-warnings", "--quiet", "--ignore-errors"]


class YtDlpError(Exception):
    """yt-dlp missing, timed out, exited non-zero, or returned nothing usable.
    Callers catch this and fall back to the official API."""


def detected() -> bool:
    """True when the yt-dlp binary is on PATH (the community plugin is installed)."""
    return shutil.which(_BINARY) is not None


def active(db: Session) -> bool:
    """The user enabled the toggle AND the binary is installed."""
    return settings_store.get_setting(db, "ytdlp_enabled") == "true" and detected()


def _run(target: str) -> list[dict]:
    """Run yt-dlp in metadata-only mode and parse its JSON-lines output."""
    if not detected():
        raise YtDlpError("yt-dlp not installed")
    try:
        proc = subprocess.run(
            [_BINARY, target, *_META_FLAGS],
            capture_output=True, text=True, timeout=_TIMEOUT, check=False,
        )
    except FileNotFoundError as exc:  # removed between detect() and run
        raise YtDlpError("yt-dlp not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise YtDlpError("yt-dlp timed out") from exc
    if proc.returncode != 0 and not proc.stdout.strip():
        raise YtDlpError(f"yt-dlp exited {proc.returncode}")
    entries: list[dict] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if not entries:
        raise YtDlpError("yt-dlp returned no metadata")
    return entries


def _thumb(entry: dict) -> str | None:
    if entry.get("thumbnail"):
        return entry["thumbnail"]
    thumbs = entry.get("thumbnails") or []
    return thumbs[-1]["url"] if thumbs else None


def search_music(query: str, limit: int = 5) -> list[dict]:
    """Zero-quota YouTube music search. Returns the same row shape the YouTube
    connector's official-API `search_track` produces, so callers are drop-in."""
    entries = _run(f"ytsearch{limit}:{query}")
    out: list[dict] = []
    for e in entries:
        vid = e.get("id")
        if not vid:
            continue
        channel = (e.get("uploader") or e.get("channel") or "").removesuffix(" - Topic").strip()
        dur = e.get("duration")
        out.append({
            "title": e.get("title") or "",
            "artists": [channel] if channel else [],
            "duration_ms": int(dur * 1000) if isinstance(dur, int | float) else None,
            "external_id": vid,
            "url": f"https://music.youtube.com/watch?v={vid}",
            "thumb": _thumb(e),
            "service": "youtube_music",
        })
    if not out:
        raise YtDlpError("no video results")
    return out


def search_channel(query: str, limit: int = 5) -> list[dict]:
    """Zero-quota channel lookup, derived from the distinct channels behind a
    video search (yt-dlp's `ytsearch` returns videos, not channels). Falls back
    via YtDlpError when channel identity isn't present in the flat metadata."""
    entries = _run(f"ytsearch{max(limit * 3, 10)}:{query}")
    seen: set[str] = set()
    out: list[dict] = []
    for e in entries:
        cid = e.get("channel_id") or e.get("uploader_id")
        name = e.get("channel") or e.get("uploader")
        if not cid or not name or cid in seen:
            continue
        seen.add(cid)
        out.append({
            "title": name,
            "artists": [],
            "external_id": cid,
            "url": e.get("channel_url") or e.get("uploader_url")
            or f"https://www.youtube.com/channel/{cid}",
            "service": "youtube",
        })
        if len(out) >= limit:
            break
    if not out:
        raise YtDlpError("no channel results")
    return out
