# MediaShelf

A self-hosted streaming index and router: one shelf across your streaming services, split by
what you subscribe to vs what's elsewhere, with working deep links into the owning apps.

MediaShelf never stores, serves, or plays media files. DRM services are browse-and-link only.

**Status: M1 — skeleton & catalog.** Shelf, title pages, subscription checklist, custom
services, TMDB catalog sync with per-country availability, nightly DB backups.
Search (M2), accounts & in-app playback (M3), and migrations (M5) come next per `mediashelf-plan.md`.

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
  creating your own (a commercial requirement, see plan Appendix B).
- **Secrets** are encrypted at rest (NaCl SecretBox; per-install key in the data dir) and never logged.
- **Backups**: nightly SQLite backups (keeps 7) in the data dir; Settings → About has one-click
  export/import; a corrupt DB is auto-restored from the latest good backup on boot.
- **Failure behavior**: if TMDB is unreachable or your key is revoked, the last-synced catalog
  keeps serving with a banner naming its age and the fix.
- This product uses the TMDB API but is not endorsed or certified by TMDB.
