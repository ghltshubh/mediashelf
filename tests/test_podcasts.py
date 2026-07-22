"""Podcasts (M8): RSS parse/subscribe, refresh dedupe, OPML round-trip.

The single network seam ``podcasts._fetch`` is replaced with a controllable
fake, so no real HTTP happens.
"""

import pytest

from app.services import podcasts as podcasts_service

FEED = "https://example.com/feed.xml"


def _rss(title: str = "Test Cast", items: tuple[str, ...] = ()) -> bytes:
    return f"""<?xml version="1.0"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
<channel>
<title>{title}</title>
<link>https://example.com</link>
<itunes:author>Jane Host</itunes:author>
<description>A test podcast.</description>
<itunes:image href="https://example.com/art.jpg"/>
{"".join(items)}
</channel>
</rss>""".encode()


def _item(guid: str, title: str = "Ep", url: str | None = None,
          dur: str = "1:02:03", date: str = "Tue, 01 Jul 2025 10:00:00 +0000") -> str:
    url = url or f"https://cdn.example.com/{guid}.mp3"
    return (f"<item><title>{title}</title><guid>{guid}</guid>"
            f'<description>notes</description>'
            f'<enclosure url="{url}" type="audio/mpeg" length="1000"/>'
            f"<itunes:duration>{dur}</itunes:duration><pubDate>{date}</pubDate></item>")


class FakeFetcher:
    def __init__(self) -> None:
        self.feeds: dict[str, bytes] = {}
        self.not_modified: set[str] = set()

    async def __call__(self, feed_url, etag=None, last_modified=None):
        if feed_url in self.not_modified:
            return (304, b"", None, None)
        content = self.feeds.get(feed_url)
        if content is None:
            return (404, b"", None, None)
        return (200, content, None, None)


@pytest.fixture
def fetcher(monkeypatch):
    f = FakeFetcher()
    monkeypatch.setattr(podcasts_service, "_fetch", f)
    return f


def test_subscribe_parses_feed(client, fetcher):
    fetcher.feeds[FEED] = _rss(items=(_item("ep1", "First"), _item("ep2", "Second")))
    res = client.post("/api/podcasts", json={"feed_url": FEED})
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "Test Cast"
    assert data["author"] == "Jane Host"
    assert data["episode_count"] == 2
    assert {e["title"] for e in data["episodes"]} == {"First", "Second"}
    ep = data["episodes"][0]
    assert ep["audio_url"].endswith(".mp3")
    assert ep["duration_seconds"] == 3723  # 1:02:03


def test_subscribe_is_idempotent(client, fetcher):
    fetcher.feeds[FEED] = _rss(items=(_item("ep1"),))
    client.post("/api/podcasts", json={"feed_url": FEED})
    client.post("/api/podcasts", json={"feed_url": FEED})
    assert len(client.get("/api/podcasts").json()) == 1


def test_refresh_adds_only_new_episode(client, fetcher):
    fetcher.feeds[FEED] = _rss(items=(_item("ep1"),))
    client.post("/api/podcasts", json={"feed_url": FEED})
    fetcher.feeds[FEED] = _rss(items=(_item("ep1"), _item("ep2", "Second")))
    assert client.post("/api/podcasts/refresh").json()["new_episodes"] == 1
    pid = client.get("/api/podcasts").json()[0]["id"]
    assert client.get(f"/api/podcasts/{pid}").json()["episode_count"] == 2


def test_refresh_304_is_noop(client, fetcher):
    fetcher.feeds[FEED] = _rss(items=(_item("ep1"),))
    client.post("/api/podcasts", json={"feed_url": FEED})
    fetcher.not_modified.add(FEED)
    assert client.post("/api/podcasts/refresh").json()["new_episodes"] == 0


def test_opml_roundtrip(client, fetcher):
    a, b = "https://a.example/feed", "https://b.example/feed"
    fetcher.feeds[a] = _rss("Cast A", (_item("a1"),))
    fetcher.feeds[b] = _rss("Cast B", (_item("b1"),))
    opml = ('<?xml version="1.0"?><opml version="2.0"><body>'
            f'<outline type="rss" xmlUrl="{a}"/>'
            f'<outline type="rss" xmlUrl="{b}"/></body></opml>')
    res = client.post("/api/podcasts/opml/import",
                      files={"file": ("subs.opml", opml, "text/x-opml")})
    assert res.json()["subscribed"] == 2
    export = client.get("/api/podcasts/opml/export").text
    assert a in export and b in export


def test_subscribe_bad_feed_is_400(client, fetcher):
    # No feed registered → fetcher returns 404 → surfaced as a clean 400.
    res = client.post("/api/podcasts", json={"feed_url": "https://nope.example/x"})
    assert res.status_code == 400


def test_unsubscribe_removes_show(client, fetcher):
    fetcher.feeds[FEED] = _rss(items=(_item("ep1"),))
    pid = client.post("/api/podcasts", json={"feed_url": FEED}).json()["id"]
    assert client.delete(f"/api/podcasts/{pid}").status_code == 204
    assert client.get("/api/podcasts").json() == []


def test_duration_parsing():
    assert podcasts_service._parse_duration("1:02:03") == 3723
    assert podcasts_service._parse_duration("45:30") == 2730
    assert podcasts_service._parse_duration("1800") == 1800
    assert podcasts_service._parse_duration("") is None
    assert podcasts_service._parse_duration(None) is None
