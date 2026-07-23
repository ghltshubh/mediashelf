# MediaShelf — Installation & Setup

MediaShelf is a self-hosted streaming index and router: one shelf across your streaming
services, split by what you subscribe to vs what's elsewhere, with working deep links into the
owning apps. It never stores, serves, or plays media files — DRM video is browse-and-link only;
music plays through official SDKs/embeds.

This guide takes you from zero to a running instance with your services connected.

- [1. What you need](#1-what-you-need)
- [2. Install & run](#2-install--run)
- [3. First run](#3-first-run)
- [4. Where your data lives](#4-where-your-data-lives)
- [5. Getting your API keys](#5-getting-your-api-keys)
- [6. Connecting accounts (OAuth)](#6-connecting-accounts-oauth)
- [7. Optional: yt-dlp plugin](#7-optional-yt-dlp-plugin-zero-quota-youtube-search)
- [8. Running on a remote host / custom domain](#8-running-on-a-remote-host--custom-domain)
- [9. Updating](#9-updating)
- [10. Troubleshooting](#10-troubleshooting)

---

## 1. What you need

- **Docker** (recommended) — [Docker Desktop](https://www.docker.com/products/docker-desktop/) on
  macOS/Windows, or Docker Engine + Compose on Linux. That's the only prerequisite for the standard
  install.
- **A free TMDB API key** — the *only* required key. Everything else is optional and unlocks a
  specific feature (see §5).
- Your **own API keys** for any optional service. MediaShelf ships **no shared keys** — you create
  your own, so you're never rate-limited by other users and nothing is billed to anyone but you.

Only TMDB is needed to browse the shelf. Add the rest whenever you want that feature.

---

## 2. Install & run

### Option A — Prebuilt image (fastest, recommended)

No source checkout, no build — pull the published image:

```sh
curl -O https://raw.githubusercontent.com/ghltshubh/mediashelf/main/docker/compose.prod.yaml
docker compose -f compose.prod.yaml up -d
```

Or in one line without a compose file:

```sh
docker run -d -p 8000:8000 -v mediashelf-data:/data --restart unless-stopped \
  ghcr.io/ghltshubh/mediashelf:latest
```

Open **http://localhost:8000**. Multi-arch images (amd64 + arm64) are published to GHCR on each
release. Pin a version by using a tag (`:1.2.3`) instead of `:latest`.

### Option B — Build from source (Docker)

```sh
git clone https://github.com/ghltshubh/mediashelf.git
cd mediashelf
docker compose -f docker/compose.yaml up --build -d
```

Open **http://localhost:8000**. Your data (SQLite DB, encrypted keys, nightly backups) lives in the
`mediashelf-data` Docker volume and survives restarts and updates.

To stop: `docker compose -f docker/compose.yaml down` (add `-v` to also delete the data volume).

### Option B — From source (for development)

```sh
# Backend (Python 3.12)
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/uvicorn app.main:app --reload            # http://localhost:8000

# Frontend (separate terminal; proxies /api to :8000)
cd app/web && npm install && npm run dev            # http://localhost:5173
```

Checks: `.venv/bin/pytest` · `.venv/bin/ruff check app tests` · `.venv/bin/mypy app`

> The dev server (`:5173`) is for frontend work. The single-port app (`:8000`) is what you install
> and what the service-worker/PWA and OAuth redirects target.

---

## 3. First run

On first open, onboarding asks for two things:

1. **Your TMDB API key** (see §5) — required to load the catalog.
2. **Your country** — the home region that drives availability (what streams where).

Then you tick the services you subscribe to. That's all MediaShelf needs to light up your shelf.

You can also bootstrap the TMDB key without onboarding by setting `TMDB_API_KEY` in the environment
(uncomment it in `docker/compose.yaml`).

---

## 4. Where your data lives

- **Docker:** the `mediashelf-data` named volume, mounted at `/data` in the container.
- **From source:** a `./data` directory (override with the `MEDIASHELF_DATA_DIR` env var).

It contains the SQLite database (`mediashelf.db`), your **encrypted** API keys/tokens (NaCl
SecretBox; the per-install key never leaves the data dir), and nightly backups (keeps 7). Settings →
About has one-click export/import, and a corrupt DB is auto-restored from the latest good backup on
boot. **Back up this directory** to preserve everything.

---

## 5. Getting your API keys

Enter all keys in **Settings → Keys**. Only **TMDB** is required.

| Provider | Unlocks | Required? |
|---|---|---|
| **TMDB** | the whole catalog + availability | ✅ Yes |
| **OMDb** | IMDb / Rotten Tomatoes / Metacritic ratings | Optional |
| **Spotify** | music search, in-app playback (Premium), migration | Optional |
| **Google / YouTube** | subscriptions + likes sync, YouTube Music, migration | Optional |
| **Apple Music** | Apple Music in the playback chain | Optional |

### TMDB (required) — ~2 minutes

1. Create a free account at [themoviedb.org](https://www.themoviedb.org/).
2. Go to **Settings → API** ([direct link](https://www.themoviedb.org/settings/api)) → **Request an
   API key** → choose *Developer* → accept the terms, fill the short form (any personal use
   description is fine).
3. Copy the **API Key (v3 auth)** — a 32-character string. (The v4 read access token also works.)
4. Paste it into MediaShelf onboarding or **Settings → Keys → TMDB**.

### OMDb (optional) — real IMDb/RT/Metacritic scores

1. Go to [omdbapi.com/apikey.aspx](https://www.omdbapi.com/apikey.aspx) → select **FREE (1,000
   daily)** → enter your email → submit.
2. **Click the activation link** in the email OMDb sends (the key doesn't work until activated).
3. Paste the key into **Settings → Keys → OMDb**. Without it, cards still show TMDB's own score.

### Spotify (optional) — music search, playback, migration

1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and log in.
2. **Create app** → give it any name/description.
3. In the app settings, add this **Redirect URI** exactly (Save):
   ```
   http://127.0.0.1:8000/oauth2callback
   ```
4. Copy the **Client ID** and **Client Secret**.
5. Paste both into **Settings → Keys → Spotify**, then connect the account (see §6).

> In-app *full-track* playback requires **Spotify Premium**. Free accounts get 30-second official
> previews.

### Google / YouTube (optional) — YouTube + YouTube Music

This is the most involved one. It's a standard "bring your own OAuth app" flow.

1. Open the [Google Cloud Console](https://console.cloud.google.com) → **create a project** (any
   name).
2. **APIs & Services → Library** → search **"YouTube Data API v3"** → **Enable**.
3. **APIs & Services → Credentials → Create credentials → OAuth client ID.** If prompted "What data
   will you be accessing?", choose **User data** (you're reading *your own* account — this creates
   an OAuth client, not an API key).
4. Configure the **OAuth consent screen**:
   - **User type: External.**
   - Fill the app name + your email.
   - **Scopes:** you can skip adding scopes here — MediaShelf requests what it needs at sign-in.
   - **Test users:** click **+ Add users** and add **the exact Google account you'll sign in with.**
     ⚠️ This step is mandatory — without it, sign-in is blocked (see Troubleshooting).
   - **Publishing status** must be **Testing** (not "In production", which would require Google
     verification you don't need).
5. Back in **Credentials → OAuth client ID → Application type: Web application.** Under **Authorized
   redirect URIs**, add exactly:
   ```
   http://127.0.0.1:8000/oauth2callback
   ```
   (Leave *Authorized JavaScript origins* blank — that field rejects paths. The redirect URI is the
   one that matters.)
6. Copy the **Client ID** and **Client Secret** → paste into **Settings → Keys → YouTube / Google**.
7. Connect the account (§6).

> **One connection covers both** YouTube and YouTube Music — there's no separate YT Music login.
> Note: *YouTube Music search* is powered by the optional **yt-dlp** plugin (§7), because the
> YouTube Data API charges 100 quota units per search. The account connection powers library sync
> and playback; yt-dlp powers zero-quota music search.

### Apple Music (optional)

Requires a paid Apple Developer account. Generate a **MusicKit developer token** (a JWT) and paste
it into **Settings → Keys → Apple Music**.

---

## 6. Connecting accounts (OAuth)

After saving a provider's keys in **Settings → Keys**, go to **Settings → Accounts** and click
**Connect** on that service's card. You'll be sent to the provider's consent screen; approve it, and
you're redirected back and shown as connected.

- The OAuth **redirect URI** is always `http://127.0.0.1:8000/oauth2callback` (for the default
  localhost install). It must be registered in the provider's app settings *exactly* (see §5), and
  it must match the address you access MediaShelf on. For a non-localhost host, see §8.
- Connecting syncs your **library** (likes/subscriptions → the Library tab) and enables **in-app
  playback** and **migrations**.
- If a token later expires, the account card shows **Reconnect** — click it to refresh.

---

## 7. Optional: yt-dlp plugin (zero-quota YouTube search)

`yt-dlp` gives YouTube/YouTube-Music **search** without spending YouTube API quota. It's a separate
community tool that MediaShelf detects on your PATH — it's never bundled.

**Install it so it's always on PATH:**

- macOS (Homebrew): `brew install yt-dlp`
- Any OS (pipx): `pipx install yt-dlp`
- Any OS (pip): `pip install yt-dlp` *(only detected if its bin dir is on PATH)*
- **Docker:** yt-dlp is not in the published image by default. When building from source, opt in
  with `docker compose -f docker/compose.yaml build --build-arg INCLUDE_YTDLP=1`.

Then enable it in **Settings → Plugins** (toggle on). The page shows a green "✓ detected" when the
binary is found. If it says "not detected," the binary isn't on the PATH the server process sees.

---

## 8. Running on a remote host / custom domain

The default setup assumes `http://127.0.0.1:8000`. To run MediaShelf on a server, NAS, or behind a
domain:

1. **Serve over HTTPS.** OAuth providers (and browser features like the PWA and Spotify SDK) expect
   a secure origin for anything but `localhost`. Put MediaShelf behind a reverse proxy (Caddy, nginx,
   Traefik) that terminates TLS and forwards to the container's port 8000.
2. **Set the OAuth redirect URI to your host.** Register `https://your-domain/oauth2callback` in each
   provider's app settings, and point MediaShelf at it by setting the `oauth_redirect_uri` value
   (Settings store) to the same URL. It must match on both sides exactly.
3. **Keep it private.** MediaShelf is single-user/household scale with no auth layer of its own —
   don't expose it to the open internet. Use a LAN, a VPN, or Tailscale.

---

## 9. Updating

**Docker:**
```sh
git pull
docker compose -f docker/compose.yaml up --build -d
```
Your data volume is untouched. (A published prebuilt image is planned — see the roadmap — which will
make this a simple `docker compose pull && up -d`.)

**From source:** `git pull`, reinstall deps if they changed (`.venv/bin/pip install -e ".[dev]"`),
rebuild the frontend (`cd app/web && npm install && npm run build`), and restart uvicorn.

After updating, one browser reload may show the previous version briefly while the service worker
swaps to the new build — reload once more.

---

## 10. Troubleshooting

**"Access blocked: … has not completed the Google verification process" (Error 403).**
Your Google account isn't an approved tester. On the OAuth consent screen (Google Auth Platform →
**Audience**), confirm **Publishing status = Testing** and add the **exact** email you sign in with
under **Test users**. You do *not* need Google verification for personal use.

**"Invalid Origin: URIs must not contain a path" when saving the Google client.**
You pasted the redirect into **Authorized JavaScript origins**. The `.../oauth2callback` value goes
in **Authorized redirect URIs**; leave JavaScript origins blank.

**Connecting fails after consent / "Missing code verifier".**
Fixed in current versions — update to the latest build.

**YouTube Music search shows nothing / provider "unconfigured".**
The `yt-dlp` binary isn't installed or isn't on PATH (see §7). Library sync and playback still work;
only *search* needs yt-dlp. After installing, restart so the server sees it on PATH.

**"TMDB rejected the key."** Re-check the key in Settings → Keys. The last-synced catalog keeps
serving with a banner naming its age until the key is fixed.

**The shelf is empty.** Add your TMDB key, then trigger a sync (Settings → Keys → Sync now). The
catalog refreshes nightly on its own.

**A liked YouTube video shows under "YouTube videos" not "YouTube Music".** MediaShelf splits your
YouTube likes by YouTube's own category (Music = category 10); non-music likes live in the Library
tab under "YouTube videos". Re-sync to re-classify.

---

This product uses the TMDB API but is not endorsed or certified by TMDB.
