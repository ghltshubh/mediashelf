# Changelog

## Unreleased

- **A service with no keys yet shows "Add keys →" instead of a dead Connect button**, linking
  straight to the form that unblocks it. Onboarding's account step previously offered buttons
  that couldn't be pressed and a note pointing at the wrong settings section — and naming the
  wrong services, since Spotify needs app keys exactly like YouTube and Apple Music do.
- Deep links into a settings section (`/settings#keys`) now scroll there.

## v0.1.2 — 2026-08-09

- **Request on Seer** now also appears on titles nothing streams anywhere (it was skipped
  entirely in that case) and on titles **leaving a service you have** — watchable today, gone
  next week. Still never shown beside something you can watch right now on a service you pay for.

## v0.1.1 — 2026-08-09

- **Overseerr / Jellyseerr link.** A title on none of your ticked services shows a "Request on
  Seer" button pointing at your own instance (base URL in Settings → Plugins). Both are
  TMDB-keyed, so it lands on the exact title rather than a search page. MediaShelf only links
  out — it never sends the request or touches media.

- **Episode tracking for shows.** Season and episode lists on a title page; tick episodes or a
  whole season. A **Continue watching** rail leads the shelf with a one-tap mark for the next
  episode. Shows sort into not started / watching / caught up / seen — "caught up" being distinct
  from finished, so a running show you are up to date on steps aside until a new episode airs.
  Marking is manual: MediaShelf links out to the service and never sees playback, so nothing can
  report an episode finished on its own. A Plex/Jellyfin or Trakt connector would write into the
  same store.
- **"Want to watch"** replaces the *Watchlist* rail label, and titles can now be saved from any
  title page instead of only arriving via the companion tool's import. Your own saved rows are
  kept apart from imported ones, so an import's full-state sync never deletes them. A show you
  have started leaves the saved rail and appears only under Continue watching.
- Catalog sync at launch now only runs when the catalog is actually stale (20-hour window),
  instead of on every start.
- Attribute **JustWatch** as the source of streaming availability, per TMDB's terms.

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
