# MediaShelf

A self-hosted streaming index and router: one shelf across your streaming services, split by
what you subscribe to vs what's elsewhere, with working deep links into the owning apps.

MediaShelf never stores, serves, or plays media files. DRM services are browse-and-link only.

## What it does today

- **One lit shelf** across your services — titles you can watch on what you subscribe to are
  lit; everything else is dimmed, each with working deep links into the owning app.
- **Universal search** over movies/TV (TMDB) and music (Spotify catalog), fanned out per source.
- **Accounts & in-app playback** — connect Spotify / YouTube / Apple Music with your own keys;
  video is browse-and-link only (never DRM playback).
- **Matching engine & migrations** — move playlists/likes/follows between music services, with a
  reviewable, revertible job log.
- **Per-region availability** — the same title can stream on different services by country, and
  the shelf reflects the region you pick.
- **Media-type tabs** (All / Movies / Shows / Music) and a personal **Watchlist** rail imported
  from your streaming apps via a separate local companion tool (logged-in scraping stays out of
  the product).
- **"Popular right now"** aggregated from per-service Top 10s, **IMDb/RT/Metacritic** ratings
  (optional, via OMDb) alongside TMDB scores, service logos on every card, and studio-inferred
  **"expected on X"** hints for upcoming titles that aren't streaming yet.

**Milestones M1–M5 complete.** Next: optional `yt-dlp` metadata provider (M6), concierge &
accessibility polish (M7), more connectors (M8), and a social/feed layer (M9).

## Quick start (Docker)

```sh
docker compose -f docker/compose.yaml up --build
```

Open http://localhost:8000 — onboarding asks for your own free TMDB API key
(create one at https://www.themoviedb.org/settings/api) and your country, then lets you tick
the services you subscribe to. That's all the app needs.

Your data (SQLite DB, encrypted API keys, backups) lives in the `mediashelf-data` volume.

## Quick start (development)

```sh
# Backend
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/uvicorn app.main:app --reload            # http://localhost:8000

# Frontend (separate terminal; proxies /api to :8000)
cd app/web && npm install && npm run dev            # http://localhost:5173
```

Checks: `.venv/bin/pytest` · `.venv/bin/ruff check app tests` · `.venv/bin/mypy app`
Component demo page (dev builds): http://localhost:5173/dev/components

## Notes

- **Your own API keys.** MediaShelf never ships or embeds shared keys; setup walks you through
  creating your own. Only a TMDB key is required; connectors (Spotify/YouTube/Apple) and the
  optional OMDb ratings key are added when you want those features.
- **Secrets** are encrypted at rest (NaCl SecretBox; per-install key in the data dir) and never logged.
- **Backups**: nightly SQLite backups (keeps 7) in the data dir; Settings → About has one-click
  export/import; a corrupt DB is auto-restored from the latest good backup on boot.
- **Failure behavior**: if TMDB is unreachable or your key is revoked, the last-synced catalog
  keeps serving with a banner naming its age and the fix.
- This product uses the TMDB API but is not endorsed or certified by TMDB.
