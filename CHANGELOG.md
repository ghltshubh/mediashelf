# Changelog

## v0.1.0 — 2026-07-22

First versioned release: the complete P1 (self-hosted web + Docker) product.

### Core
- One lit shelf across your streaming services (lit = on your services, dimmed = elsewhere),
  per-region availability, working deep links with fallback chains.
- Universal search (⌘K / `/`) over movies, TV, and music, fanned out per source.
- Home / Movies / Shows / Music / Podcasts tabs — Home is the curated landing (Music rail,
  "Because you saved…", Watchlist, Popular right now); Movies/Shows carry the full
  genre / sort / region / ownership toolbar.

### Accounts & playback
- Bring-your-own-keys connectors: Spotify (Web Playback SDK, Premium), YouTube (OAuth + iframe),
  Apple Music (MusicKit, developer token). DRM video is browse-and-link only, always.
- Continuous cross-service music queue with per-source brand badges; embed-blocked YouTube
  tracks resolve to the best match on Spotify/Apple and play there ("best match").
- YouTube likes split into YouTube Music vs videos by category; queue panel with reorder;
  playback speed; podcast resume positions.

### Library & migrations
- Library sync (likes/follows) from Spotify + YouTube; watchlist import via the local
  companion tool; playlist/likes migrations between music services with a reviewable,
  resumable, revertible job log.

### Discovery
- "More like this" + person pages (browse by actor/director), availability-enriched.
- "Because you saved X" recommendations rail, rotating its watchlist seed daily.
- Feeling-lucky dice: random pick from your services (genre / length / type / scope filters),
  with a brass die and a proper throw animation.

### Podcasts
- Subscribe by RSS URL or OPML import/export; in-app HTML5 audio; nightly refresh.

### Platform
- Installable PWA: app-shell + offline catalog caching (network-first; API never stale),
  update-available toast, offline banner.
- i18n: interface chrome in 11 languages; display locale independent of content region.
- Nightly SQLite backups with boot-time auto-restore; encrypted-at-rest secrets;
  Docker image (multi-arch publish workflow) + compose files; CI (pytest/ruff/mypy + web build).
