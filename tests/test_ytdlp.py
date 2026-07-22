"""M6 — yt-dlp metadata provider: detection, zero-quota routing, graceful
degrade, settings round-trip, and the metadata-only guard."""

import asyncio
import json
import pathlib

import pytest

from app import settings_store
from app.providers import ytdlp_meta
from app.services import search as search_service

# yt-dlp --dump-json output: one JSON object per line (flat playlist entries).
MUSIC_JSON = "\n".join([
    json.dumps({"id": "vid1", "title": "Song One", "uploader": "Artist A - Topic",
                "duration": 200, "thumbnail": "http://t/1.jpg"}),
    json.dumps({"id": "vid2", "title": "Song Two", "channel": "Artist B",
                "duration": 180.5, "thumbnails": [{"url": "http://t/2.jpg"}]}),
])
CHANNEL_JSON = "\n".join([
    json.dumps({"id": "v1", "title": "Clip", "channel": "Great Channel",
                "channel_id": "UC123", "channel_url": "https://youtube.com/@great"}),
    json.dumps({"id": "v2", "title": "Clip 2", "channel": "Great Channel",
                "channel_id": "UC123"}),  # same channel → deduped
])


class _FakeProc:
    def __init__(self, stdout: str, returncode: int = 0):
        self.stdout = stdout
        self.returncode = returncode


def _installed(monkeypatch, stdout: str):
    """Pretend yt-dlp is installed and returns `stdout`."""
    monkeypatch.setattr(ytdlp_meta, "detected", lambda: True)
    monkeypatch.setattr(ytdlp_meta.subprocess, "run",
                        lambda *a, **k: _FakeProc(stdout))


# ---- module: detection + parsing --------------------------------------------

def test_detected_false_when_binary_absent(monkeypatch):
    monkeypatch.setattr(ytdlp_meta.shutil, "which", lambda _b: None)
    assert ytdlp_meta.detected() is False


def test_search_music_raises_when_not_installed(monkeypatch):
    monkeypatch.setattr(ytdlp_meta, "detected", lambda: False)
    with pytest.raises(ytdlp_meta.YtDlpError):
        ytdlp_meta.search_music("anything")


def test_search_music_parses_rows(monkeypatch):
    _installed(monkeypatch, MUSIC_JSON)
    rows = ytdlp_meta.search_music("song")
    assert [r["external_id"] for r in rows] == ["vid1", "vid2"]
    assert rows[0]["artists"] == ["Artist A"]        # " - Topic" stripped
    assert rows[0]["duration_ms"] == 200_000
    assert rows[1]["duration_ms"] == 180_500
    assert rows[0]["service"] == "youtube_music"
    assert rows[0]["url"].endswith("vid1")
    assert rows[0]["thumb"] == "http://t/1.jpg"


def test_search_channel_dedupes_by_channel(monkeypatch):
    _installed(monkeypatch, CHANNEL_JSON)
    chans = ytdlp_meta.search_channel("great")
    assert len(chans) == 1
    assert chans[0]["external_id"] == "UC123"
    assert chans[0]["service"] == "youtube"


def test_search_channel_raises_without_channel_ids(monkeypatch):
    _installed(monkeypatch, json.dumps({"id": "v", "title": "no channel here"}))
    with pytest.raises(ytdlp_meta.YtDlpError):
        ytdlp_meta.search_channel("x")


def test_run_raises_on_nonzero_and_empty(monkeypatch):
    monkeypatch.setattr(ytdlp_meta, "detected", lambda: True)
    monkeypatch.setattr(ytdlp_meta.subprocess, "run",
                        lambda *a, **k: _FakeProc("", returncode=1))
    with pytest.raises(ytdlp_meta.YtDlpError):
        ytdlp_meta.search_music("x")


# ---- search provider: configured gate + zero-quota + degrade ----------------

def _db(client):
    from app.db import session_factory
    return session_factory()()


def test_provider_configured_follows_toggle(client, monkeypatch):
    prov = search_service.YouTubeSearchProvider()
    monkeypatch.setattr(ytdlp_meta, "detected", lambda: True)
    with _db(client) as db:
        assert prov.configured(db) is False            # toggle off
        settings_store.set_setting(db, "ytdlp_enabled", "true")
        assert prov.configured(db) is True             # on + detected
        monkeypatch.setattr(ytdlp_meta, "detected", lambda: False)
        assert prov.configured(db) is False            # on but not installed


def test_provider_search_uses_ytdlp_with_zero_api(client, monkeypatch):
    """Happy path: results come from yt-dlp; the official API is never touched."""
    api_calls: list = []
    monkeypatch.setattr("app.connectors.youtube.YouTubeConnector.search_track",
                        lambda self, db, title, artists: api_calls.append(1) or [])
    monkeypatch.setattr(ytdlp_meta, "search_music", lambda q, limit=5: [{
        "title": "Song One", "artists": ["Artist A"], "duration_ms": 200_000,
        "external_id": "vid1", "url": "https://music.youtube.com/watch?v=vid1",
        "thumb": "t", "service": "youtube_music"}])
    prov = search_service.YouTubeSearchProvider()
    with _db(client) as db:
        rows = asyncio.run(prov.search(db, "song one", "US"))
    assert api_calls == []                              # zero search.list calls
    assert rows[0]["entity"] == "track"
    assert rows[0]["youtube_video_id"] == "vid1"
    assert rows[0]["services"][0]["service_key"] == "youtube_music"


def test_provider_degrades_to_api_when_connected(client, monkeypatch):
    def boom(q, limit=5):
        raise ytdlp_meta.YtDlpError("killed mid-search")
    monkeypatch.setattr(ytdlp_meta, "search_music", boom)
    monkeypatch.setattr("app.connectors.youtube.YouTubeConnector.connected",
                        lambda self, db: True)
    monkeypatch.setattr("app.connectors.youtube.YouTubeConnector.search_track",
                        lambda self, db, title, artists: [{
                            "title": "API Song", "artists": ["X"], "duration_ms": 1000,
                            "external_id": "apivid", "url": "u", "thumb": None,
                            "service": "youtube_music"}])
    prov = search_service.YouTubeSearchProvider()
    with _db(client) as db:
        rows = asyncio.run(prov.search(db, "q", "US"))
    assert rows[0]["youtube_video_id"] == "apivid"     # fell back, no error raised


def test_provider_silent_when_ytdlp_fails_and_not_connected(client, monkeypatch):
    monkeypatch.setattr(ytdlp_meta, "search_music",
                        lambda q, limit=5: (_ for _ in ()).throw(ytdlp_meta.YtDlpError("x")))
    monkeypatch.setattr("app.connectors.youtube.YouTubeConnector.connected",
                        lambda self, db: False)
    prov = search_service.YouTubeSearchProvider()
    with _db(client) as db:
        rows = asyncio.run(prov.search(db, "q", "US"))
    assert rows == []


def test_merge_carries_youtube_video_id_into_matched_row():
    """A YouTube result that dedupes into a Spotify row must contribute both its
    service link AND its video id, so in-app YouTube playback stays available."""
    spotify_row = {"entity": "track", "title": "Levels", "artists": ["Avicii"],
                   "spotify_id": "sp1",
                   "services": [{"service_key": "spotify", "service_name": "Spotify", "url": "u1"}]}
    youtube_row = {"entity": "track", "title": "Levels", "artists": ["Avicii"],
                   "youtube_video_id": "ytid",
                   "services": [{"service_key": "youtube_music",
                                 "service_name": "YouTube Music", "url": "u2"}]}
    merged = search_service._merge_music(
        "levels", {"spotify": [spotify_row], "youtube": [youtube_row]}, set())
    assert len(merged) == 1
    row = merged[0]
    assert {s["service_key"] for s in row["services"]} == {"spotify", "youtube_music"}
    assert row["youtube_video_id"] == "ytid"


# ---- settings round-trip ----------------------------------------------------

def test_settings_expose_and_persist_ytdlp(client, monkeypatch):
    monkeypatch.setattr(ytdlp_meta, "detected", lambda: True)
    r = client.get("/api/settings").json()
    assert r["ytdlp_detected"] is True and r["ytdlp_enabled"] is False
    client.put("/api/settings", json={"ytdlp_enabled": True})
    assert client.get("/api/settings").json()["ytdlp_enabled"] is True


# ---- metadata-only guard ----------------------------------------------------

def test_ytdlp_invocation_is_metadata_only():
    """The only flags yt-dlp is ever invoked with are metadata-only: skip
    download, no format selection, no download flag."""
    flags = ytdlp_meta._META_FLAGS
    assert "--skip-download" in flags
    assert not any(f == "-f" or f.startswith("--format") or f == "--audio-format"
                   for f in flags)
    src = pathlib.Path(__file__).resolve().parents[1] / "app/providers/ytdlp_meta.py"
    text = src.read_text()
    # No yt-dlp-python download call, and the subprocess only spreads _META_FLAGS.
    assert "download=True" not in text
    assert "*_META_FLAGS]" in text
