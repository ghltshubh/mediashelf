"""Service roster seed (plan Appendix A).

Tier 3 services are data, not code: name, deep-link URL template, signup URL,
SSO note, capability flags. The TMDB sync auto-adds any provider TMDB reports
for the user's country that isn't listed here.

Deep-link templates use {query} (URL-encoded title). Search-page links are the
honest M1 baseline; a licensed availability provider can later supply per-title
deep links behind the same interface.
"""

import urllib.parse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Service, UserSub

CAP_NONE = {"catalog": False, "user_library": False, "write_likes": False,
            "write_follows": False, "playback": "deeplink"}


def caps(playback: str = "deeplink", **kw) -> dict:
    c = dict(CAP_NONE)
    c["playback"] = playback
    c.update(kw)
    return c


# (key, name, kind, tier, deep_link_template, signup_url, sso_note, capabilities)
SERVICES: list[tuple] = [
    # ---- Tier 1 — full connectors (connector code lands M3+) ----
    ("spotify", "Spotify", "music", 1, "https://open.spotify.com/search/{query}",
     "https://www.spotify.com/signup", "Google, Facebook, Apple",
     caps("sdk", catalog=True, user_library=True, write_likes=True, write_follows=True)),
    ("youtube", "YouTube", "video", 1, "https://www.youtube.com/results?search_query={query}",
     "https://www.youtube.com", "Google",
     caps("embed", catalog=True, user_library=True, write_likes=True, write_follows=True)),
    ("youtube_music", "YouTube Music", "music", 1, "https://music.youtube.com/search?q={query}",
     "https://music.youtube.com", "Google",
     caps("embed", catalog=True, user_library=True, write_likes=True, write_follows=True)),
    ("apple_music", "Apple Music", "music", 1, "https://music.apple.com/search?term={query}",
     "https://music.apple.com/subscribe", "Apple",
     caps("sdk", catalog=True, user_library=True, write_likes=True, write_follows=True)),
    # ---- Tier 2 — partial connectors (M8) ----
    ("trakt", "Trakt.tv", "meta", 2, "https://trakt.tv/search?query={query}",
     "https://trakt.tv/auth/join", "Google, Apple",
     caps("none", user_library=True, write_likes=True)),
    ("soundcloud", "SoundCloud", "music", 2, "https://soundcloud.com/search?q={query}",
     "https://soundcloud.com/signup", "Google, Facebook, Apple",
     caps("embed", catalog=True, user_library=True, write_likes=True, write_follows=True)),
    ("deezer", "Deezer", "music", 2, "https://www.deezer.com/search/{query}",
     "https://www.deezer.com/register", "Google, Facebook, Apple",
     caps("embed", catalog=True, user_library=True, write_likes=True)),
    ("lastfm", "Last.fm", "meta", 2, "https://www.last.fm/search?q={query}",
     "https://www.last.fm/join", None, caps("none", user_library=True)),
    ("listenbrainz", "ListenBrainz", "meta", 2, "https://listenbrainz.org/search/?search_term={query}",
     "https://listenbrainz.org/login/", None, caps("none", user_library=True)),
    ("tidal", "Tidal", "music", 2, "https://listen.tidal.com/search?q={query}",
     "https://tidal.com/signup", "Apple",
     caps("deeplink", catalog=True, user_library=True)),
    ("podcasts", "Podcasts (RSS)", "podcast", 2, None, None, None,
     caps("embed", catalog=True, user_library=True, write_follows=True)),
    # ---- Tier 3 — video, global ----
    ("netflix", "Netflix", "video", 3, "https://www.netflix.com/search?q={query}",
     "https://www.netflix.com/signup", "None (email)", caps()),
    ("prime_video", "Prime Video", "video", 3,
     "https://www.primevideo.com/search/?phrase={query}",
     "https://www.primevideo.com", "Amazon", caps()),
    ("disney_plus", "Disney+", "video", 3, "https://www.disneyplus.com/search?q={query}",
     "https://www.disneyplus.com/sign-up", "None (email)", caps()),
    ("hulu", "Hulu", "video", 3, "https://www.hulu.com/search?q={query}",
     "https://signup.hulu.com", "None (email)", caps()),
    ("max", "Max", "video", 3, "https://play.max.com/search?q={query}",
     "https://www.max.com", "Google, Apple", caps()),
    ("paramount_plus", "Paramount+", "video", 3, "https://www.paramountplus.com/search/?q={query}",
     "https://www.paramountplus.com/account/signup/", "Apple", caps()),
    ("peacock", "Peacock", "video", 3, "https://www.peacocktv.com/watch/search?q={query}",
     "https://www.peacocktv.com/plans/all-monthly", "Google, Apple", caps()),
    ("apple_tv_plus", "Apple TV+", "video", 3, "https://tv.apple.com/search?term={query}",
     "https://tv.apple.com", "Apple", caps()),
    ("crunchyroll", "Crunchyroll", "video", 3, "https://www.crunchyroll.com/search?q={query}",
     "https://www.crunchyroll.com/register", "Google, Apple, Facebook", caps()),
    ("mubi", "MUBI", "video", 3, "https://mubi.com/en/search/films?query={query}",
     "https://mubi.com/register", "Google, Apple", caps()),
    ("tubi", "Tubi", "video", 3, "https://tubitv.com/search/{query}",
     "https://tubitv.com/signup", "Google, Facebook, Apple", caps()),
    ("pluto_tv", "Pluto TV", "video", 3, "https://pluto.tv/search?query={query}",
     "https://pluto.tv", "No account needed", caps()),
    ("plex", "Plex", "video", 3, "https://watch.plex.tv/search?q={query}",
     "https://www.plex.tv/sign-up/", "Google, Apple, Facebook", caps()),
    ("roku_channel", "The Roku Channel", "video", 3,
     "https://therokuchannel.roku.com/search/{query}",
     "https://my.roku.com/signup", "None (email)", caps()),
    ("shudder", "Shudder", "video", 3, "https://www.shudder.com/search/{query}",
     "https://www.shudder.com", "None (email)", caps()),
    ("criterion", "Criterion Channel", "video", 3,
     "https://www.criterionchannel.com/search?q={query}",
     "https://www.criterionchannel.com/checkout/subscribe", "None (email)", caps()),
    ("curiosity_stream", "Curiosity Stream", "video", 3,
     "https://curiositystream.com/search?keyword={query}",
     "https://curiositystream.com/plans", "None (email)", caps()),
    ("discovery_plus", "Discovery+", "video", 3, "https://www.discoveryplus.com/search?q={query}",
     "https://www.discoveryplus.com", "None (email)", caps()),
    ("espn_plus", "ESPN+", "video", 3, "https://www.espn.com/search/_/q/{query}",
     "https://plus.espn.com", "None (email)", caps()),
    ("dazn", "DAZN", "video", 3, "https://www.dazn.com/en-US/search/{query}",
     "https://www.dazn.com", "None (email)", caps()),
    ("youtube_tv", "YouTube TV", "video", 3, "https://tv.youtube.com/search/{query}",
     "https://tv.youtube.com/welcome/", "Google", caps()),
    # ---- Tier 3 — video, regional examples ----
    ("jiohotstar", "JioHotstar", "video", 3, "https://www.hotstar.com/in/explore?search_query={query}",
     "https://www.hotstar.com/in/subscribe", "None (phone)", caps()),
    ("zee5", "ZEE5", "video", 3, "https://www.zee5.com/search?q={query}",
     "https://www.zee5.com/myaccount/subscription", "Google, Facebook", caps()),
    ("sonyliv", "SonyLIV", "video", 3, "https://www.sonyliv.com/search?searchTerm={query}",
     "https://www.sonyliv.com/subscription", "Google", caps()),
    ("aha", "Aha", "video", 3, "https://www.aha.video/search?q={query}",
     "https://www.aha.video/subscribe", "None (phone)", caps()),
    ("sun_nxt", "Sun NXT", "video", 3, "https://www.sunnxt.com/search?q={query}",
     "https://www.sunnxt.com/subscribe", "None (phone)", caps()),
    ("hoichoi", "Hoichoi", "video", 3, "https://www.hoichoi.tv/search?q={query}",
     "https://www.hoichoi.tv/subscribe", "None (email)", caps()),
    ("bbc_iplayer", "BBC iPlayer", "video", 3, "https://www.bbc.co.uk/iplayer/search?q={query}",
     "https://account.bbc.com/register", "None (email)", caps()),
    ("itvx", "ITVX", "video", 3, "https://www.itv.com/search?q={query}",
     "https://www.itv.com/watch", "None (email)", caps()),
    ("channel4", "Channel 4", "video", 3, "https://www.channel4.com/search?q={query}",
     "https://www.channel4.com/registration", "None (email)", caps()),
    ("stan", "Stan", "video", 3, "https://www.stan.com.au/search?q={query}",
     "https://www.stan.com.au/signup", "None (email)", caps()),
    ("binge", "Binge", "video", 3, "https://binge.com.au/search?q={query}",
     "https://binge.com.au/offers", "None (email)", caps()),
    ("crave", "Crave", "video", 3, "https://www.crave.ca/en/search?q={query}",
     "https://www.crave.ca/en/subscribe", "None (email)", caps()),
    ("viki", "Viki", "video", 3, "https://www.viki.com/search?q={query}",
     "https://www.viki.com/pass", "Google, Facebook, Apple", caps()),
    ("iqiyi", "iQIYI", "video", 3, "https://www.iq.com/search?query={query}",
     "https://www.iq.com/vip", "Google, Facebook", caps()),
    ("viu", "Viu", "video", 3, "https://www.viu.com/ott/search?keyword={query}",
     "https://www.viu.com", "Google, Facebook", caps()),
    # ---- Tier 3 — music ----
    ("amazon_music", "Amazon Music", "music", 3, "https://music.amazon.com/search/{query}",
     "https://music.amazon.com", "Amazon", caps()),
    ("gaana", "Gaana", "music", 3, "https://gaana.com/search/{query}",
     "https://gaana.com/gaanaplus", "Google, Facebook", caps()),
    ("jiosaavn", "JioSaavn", "music", 3, "https://www.jiosaavn.com/search/{query}",
     "https://www.jiosaavn.com/pro", "None (phone)", caps()),
    ("wynk", "Wynk Music", "music", 3, "https://wynk.in/music/search/{query}",
     "https://wynk.in/music", "None (phone)", caps()),
    ("pandora", "Pandora", "music", 3, "https://www.pandora.com/search/{query}/all",
     "https://www.pandora.com/account/register", "None (email)", caps()),
    ("iheartradio", "iHeartRadio", "music", 3, "https://www.iheart.com/search/?q={query}",
     "https://www.iheart.com/signup/", "Google, Facebook, Apple", caps()),
    ("audiomack", "Audiomack", "music", 3, "https://audiomack.com/search?q={query}",
     "https://audiomack.com/join", "Google, Apple", caps()),
    ("boomplay", "Boomplay", "music", 3, "https://www.boomplay.com/search/default/{query}",
     "https://www.boomplay.com", "Google, Facebook", caps()),
    ("anghami", "Anghami", "music", 3, "https://play.anghami.com/search/{query}",
     "https://www.anghami.com/plus", "Google, Facebook, Apple", caps()),
]


def merge_duplicate_services(db: Session) -> None:
    """Fold auto-added duplicates (e.g. TMDB's "Tubi TV" vs seeded "Tubi") into
    their seeded service once a name override exists: availability moves over,
    the duplicate row goes away, subscriptions on the seeded row start matching."""
    from app.models import Availability
    from app.services.catalog import resolve_alias_key

    by_key = {s.key: s for s in db.scalars(select(Service)).all()}
    for svc in list(by_key.values()):
        if not svc.auto_added:
            continue
        target_key = resolve_alias_key(svc.name, set(by_key) - {svc.key})
        target = by_key.get(target_key) if target_key else None
        if target is None or target.id == svc.id:
            continue
        for avail in db.scalars(select(Availability).where(Availability.service_id == svc.id)):
            dup = db.scalar(select(Availability).where(
                Availability.media_item_id == avail.media_item_id,
                Availability.service_id == target.id,
                Availability.country == avail.country,
                Availability.offer_type == avail.offer_type))
            if dup is None:
                avail.service_id = target.id
            else:
                db.delete(avail)
        if target.tmdb_provider_id is None:
            target.tmdb_provider_id = svc.tmdb_provider_id
        for sub in db.scalars(select(UserSub).where(UserSub.service_id == svc.id)):
            db.delete(sub)
        db.delete(svc)
        del by_key[svc.key]
    db.commit()


def seed_services(db: Session) -> None:
    """Insert-if-absent; never clobbers user edits or auto-added providers."""
    existing = {s.key for s in db.scalars(select(Service)).all()}
    for key, name, kind, tier, template, signup, sso, capabilities in SERVICES:
        if key in existing:
            continue
        # Homepage = final deep-link fallback (plan: failure modes / template rot).
        base = template or signup
        homepage = None
        if base:
            parts = urllib.parse.urlsplit(base)
            homepage = f"{parts.scheme}://{parts.netloc}"
        svc = Service(
            key=key, name=name, kind=kind, tier=tier,
            deep_link_template=template, homepage_url=homepage,
            signup_url=signup, sso_note=sso,
            capabilities=capabilities,
        )
        db.add(svc)
        db.flush()
        db.add(UserSub(service_id=svc.id, subscribed=False))
    db.commit()
