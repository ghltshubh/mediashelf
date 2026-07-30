# Desktop build (P2)

The desktop app is the same MediaShelf: a Tauri 2 shell that spawns the FastAPI
server as a bundled sidecar on `127.0.0.1:8000` and points a webview at it. No
product logic lives in the shell, so web, Docker and desktop stay one codebase.

Status: **local spike complete on macOS (arm64).** Not signed, not notarized,
no auto-updater, no license activation — see *Not done yet* below.

## Build

```sh
bash desktop/build-sidecar.sh                      # SPA + PyInstaller server binary
cd desktop/src-tauri && npx @tauri-apps/cli build  # .app + .dmg
```

Requires the Rust toolchain (`rustup`) and the project venv. Output lands in
`desktop/src-tauri/target/release/bundle/`. The `.app` is self-contained: it was
verified launching from Finder with a stripped `PATH` (no venv, no Homebrew).

Sizes as of the first build: 45 MB sidecar, 48 MB DMG.

## Webview DRM — the finding that shaped this

The plan called for a day-one spike on whether Spotify's Web Playback SDK works
inside the platform webview. It does not on macOS. Probing the EME APIs inside
the Tauri window (`AppleWebKit/605.1.15`) returned:

| Key system | Available |
|---|---|
| Widevine (`com.widevine.alpha`) | **no** |
| FairPlay (`com.apple.fps`, `com.apple.fps.1_0`) | yes |
| ClearKey | yes |
| MSE / EME API / secure context | yes |

Spotify's SDK requires Widevine, so **Spotify playback cannot work in the macOS
desktop shell**. Rather than let the SDK fail with an opaque error, the app
detects this up front (`app/web/src/lib/drm.ts`) and takes the fallback the plan
mandates: it opens the same local app in the system browser, where playback
works, and says so in a toast. Everything else stays in the shell.

What this means per engine on macOS desktop:

- **YouTube** (iframe) — works in-shell.
- **Podcasts / HTML5 audio** — works in-shell.
- **Spotify** — hands off to the system browser.
- **Apple Music (MusicKit)** — untested; FairPlay is present, so it may work
  in-shell. Needs a developer token to verify.

Windows (WebView2/Chromium) and Linux (WebKitGTK) are unprobed. WebView2 is
likely to have Widevine; WebKitGTK likely not. Re-run the probe per platform
before promising in-shell Spotify anywhere.

## How the pieces fit

- `app/__main__.py` — the server entrypoint PyInstaller freezes. Takes
  `--data-dir` and `--exit-with-parent`.
- Data lives in the OS app-data dir (`~/Library/Application Support/in.tinkerer.mediashelf`
  on macOS), not next to the binary.
- The port is pinned to **8000** because `accounts.py` registers
  `http://127.0.0.1:8000/oauth2callback` and users whitelist that exact URI in
  their own Spotify/Google apps. A busy port is a hard error, never a silent
  reassignment.
- The shell forwards the server's stdout/stderr to its own, so a failing sidecar
  is debuggable.

### Orphaned-server trap

A one-file PyInstaller binary is *two* processes: the bootloader and the Python
it re-execs. Killing the visible child leaves the real server running, holding
port 8000 and continuing scheduled syncs. Killing on exit from the shell is
therefore not enough — the server also watches for its parent disappearing
(`_exit_with_parent`) and exits on reparenting, which covers force-quit and
crashes too. Both paths are wired; the macOS-menu quit case regressed once and
is now verified clean.

## Not done yet

- Windows and Linux bundles; per-platform DRM probe.
- CI release pipeline and the Tauri auto-updater.
- License-key activation (offline, signed — Appendix B).
- **Code signing and notarization** (Apple Developer account) — without it macOS
  warns about an unidentified developer.
- **TMDB commercial license** — Appendix B requires it before any paid
  distribution.

The last two gate *selling*, not developing.
