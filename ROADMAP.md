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

- **Notification agents.** MediaShelf already knows things worth telling you: a new episode of a
  show you're mid-way through has aired, a title you saved finally landed somewhere you
  subscribe to. Right now you only find out
  by opening the app. Jellyseerr's model is the one to copy — a list of agents (Discord, Telegram,
  ntfy, Gotify, Pushover, Slack, webhook, email, web push), each toggled per event type, each
  configured with your own credentials. The generic **webhook** agent is the one that matters
  most: it makes every other integration someone else's problem. Web push also gets the PWA
  notifying a phone with no third party at all.
- **Browse by category.** Genre tiles, studios and networks as first-class entry points, plus an
  "upcoming" rail — the way Jellyseerr's discover page works. MediaShelf has genre rails on the
  shelf, but no way to say "show me everything on Netflix in Crime" as a browse rather than a
  filter. TMDB already supplies studio, network and release-date data, so this is mostly UI.
- **Content-rating filter.** TMDB's `adult` flag is already excluded at source, but that only
  covers pornography — it does nothing about an 18-rated film appearing on a shelf a child
  browses, or the lucky dice landing on one. Certifications come from TMDB per country
  (`/movie/{id}/release_dates`, `/tv/{id}/content_ratings`), so a household ceiling ("nothing
  above PG-13") is a small filter over data we can already fetch. Worth doing as a global setting;
  per-profile would need user accounts, which MediaShelf deliberately doesn't have.

## Wants verifying

- **Per-season availability coverage.** TMDB's per-season watch-provider data looked good in spot
  checks, but it's likely thinner outside the big markets. If you know a show's seasons are split
  and MediaShelf doesn't show it, that's worth reporting.
- **Add-on channel noise.** Some titles list nine near-identical variants ("Paramount+ Essential",
  "Paramount+ Amazon Channel", …). Rows cap and fold them, but the underlying services could
  probably collapse further.
- **The extension's Firefox build is untested.** Built from the same source as the Chrome one and
  checked in CI, but never loaded in Firefox by anyone yet. Reports welcome on
  [its issue tracker](https://github.com/ghltshubh/mediashelf-clipper/issues).
- **Extension selectors drift.** Each service is a handful of CSS selectors against markup its
  owner can change without warning. A clip that finds nothing means that service redesigned — it
  fails quietly and never sends an empty list, but it does need someone to notice and fix it.

## Known debt

- **No schema migrations.** The database is created from the models at startup, which does nothing
  for a database that already exists — new columns never reach one. Episode tracking was built to
  need no schema change partly because of this. Fixing it properly gates anything that does.
- **The extension asks for more than it can justify.** It holds host permissions on ten streaming
  domains, plus an optional all-URLs grant for services outside the shipped list, and no threat
  model says which of those it actually needs. A server install also holds OAuth refresh tokens
  for Spotify, YouTube and Google, encrypted at rest but usable by the running process. Narrowing
  the permissions and writing down what an attacker gets is overdue.
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
- **Scraping logged-in sessions.** Reading your "My List" happens in the
  [companion extension](https://github.com/ghltshubh/mediashelf-clipper), in your browser, on a
  page you opened, when you click — never in MediaShelf. The server has no browser and none of
  your sessions, and whether to read your own account is your decision rather than a side effect
  of installing a server app. MediaShelf ships only the receiving endpoint.
- **A Request button on titles you can already watch.** It appears where a gap exists — nothing on
  your services, or nothing anywhere. Beside something you can watch right now it would argue
  against the point of the app.
- **Per-service Top 10 beyond Netflix.** Netflix publishes its weekly Top 10 as open data, which
  is what feeds "Popular right now". No other service publishes an equivalent, and the aggregators
  that hold the data license it commercially. This was checked rather than assumed: JustWatch
  quoted **from ~€1,500/month** for API access in August 2026, with affiliate revenue shared and a
  requirement that every page showing their data carry their logo and link back. That is not a
  price or a shape this project can take — MediaShelf carries no ads and no affiliate links. Their
  free widget is a non-customisable third-party embed showing *availability*, not charts, and
  MediaShelf already gets JustWatch-sourced availability free through TMDB. Scraping an aggregator
  is the kind of tooling this project deliberately excludes. Per-service views rank by TMDB
  popularity instead, which is the honest free substitute.
- **Listing the extension in the browser stores.** It installs from a
  [release zip](https://github.com/ghltshubh/mediashelf-clipper/releases/latest) and stays that
  way. A store listing is a far more exposed position than a GitHub release: a single-purpose
  extension that reads named streaming sites can be pulled on one complaint, and a takedown would
  remove the auto-updates it was added for. The zip route depends on nobody's approval. Its cost
  is real and accepted — Developer mode to install, and the in-app update notice instead of
  automatic updates. Firefox pays most: unsigned add-ons load only for the session, so it is a
  per-session install unless you run Developer Edition, Nightly or ESR with
  `xpinstall.signatures.required` off. Signing through addons.mozilla.org is not planned either.
  If that ever changes, the route worth looking at first is AMO's **unlisted** signing, which
  returns a permanently installable file without a public listing — permanence without the
  storefront exposure that ruled the rest of this out.
- **Multi-tenant hosting.** Single household, your own machine, your own keys.
