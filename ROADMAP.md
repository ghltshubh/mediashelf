# Roadmap

What's likely next, what's deliberately not, and the debt behind both. No dates — this is a
nights-and-weekends project. Anything with an issue number is where the discussion lives.

## Next

- **Plex / Jellyfin / Emby library read** ([#1](https://github.com/ghltshubh/mediashelf/issues/1)) —
  your own library as another source of "where can I watch this", with *Play on Plex* as a deep
  link out. MediaShelf would read the library and link to it; it would never serve a file. Plex
  stores TMDB/IMDb GUIDs and MediaShelf keys on TMDB ids, so titles match on id rather than by
  name. All three should sit behind one interface.
- **Trakt** — the only route to *automatic* watched state. MediaShelf deep-links out for TV and
  never sees playback, so marking is manual by necessity; Trakt is where media centres scrobble
  to, and reading it would fill episode progress in for people who don't self-host a server.
- **Overseerr one-click** — today the *Request on Seer* button is a link, so you press Request in
  Overseerr. Its API takes a TMDB id and a season list, so MediaShelf could request directly and
  offer "just the seasons you're missing" — which Overseerr can't know. Costs storing a Seerr API
  key, so it's only worth it if people want it.
- **Seerr discoverability** — without a configured URL the button doesn't exist anywhere, so
  there's nothing to find unless you already know to look. A pointer in the empty state would fix
  that, at the cost of advertising the integration to people who never asked for it.

## Wants verifying

- **Per-season availability coverage.** TMDB's per-season watch-provider data looked good in spot
  checks, but it's likely thinner outside the big markets. If you know a show's seasons are split
  and MediaShelf doesn't show it, that's worth reporting.
- **Add-on channel noise.** Some titles list nine near-identical variants ("Paramount+ Essential",
  "Paramount+ Amazon Channel", …). Rows cap and fold them, but the underlying services could
  probably collapse further.

## Known debt

- **No schema migrations.** The database is created from the models at startup, which does nothing
  for a database that already exists — new columns never reach one. Episode tracking was built to
  need no schema change partly because of this. Fixing it properly gates anything that does.
- **Desktop (P2) is a spike, not a product.** macOS only, unsigned, no auto-updater. Windows and
  Linux need their own DRM probe: Spotify's SDK needs Widevine, which macOS WKWebView lacks, so
  that surface hands off to the system browser there. Signing and a TMDB commercial licence gate
  selling it, not building it.

## Not planned

- **Storing, serving, or playing media files.** MediaShelf indexes and routes streaming services.
  It is not a media server, and reading a Plex library above does not change that — it links to
  your server, it never becomes one.
- **Downloading or proxying DRM streams**, or any playback path through yt-dlp. yt-dlp is
  metadata-only, wrapped in one module that exposes nothing else.
- **Scraping logged-in sessions.** Watchlist import runs as a separate local companion tool, out
  of the product on purpose.
- **A Request button on titles you can already watch.** It appears where a gap exists — nothing on
  your services, nothing anywhere, or a title leaving a service you have. Beside something you can
  watch right now it would argue against the point of the app.
- **Multi-tenant hosting.** Single household, your own machine, your own keys.
