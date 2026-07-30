#!/usr/bin/env bash
# Build the FastAPI server as a single-file binary for the Tauri desktop shell.
#
#   bash desktop/build-sidecar.sh
#
# Output: desktop/src-tauri/binaries/mediashelf-server-<target-triple>
# Tauri's externalBin resolves that triple suffix at bundle time.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"
PY="${PY:-$ROOT/.venv/bin/python}"
OUT="$ROOT/desktop/src-tauri/binaries"

# Tauri looks for the binary named with the Rust host triple.
TRIPLE="$(rustc -vV | awk '/^host:/ {print $2}')"
[ -n "$TRIPLE" ] || { echo "could not determine rust target triple (is rustc installed?)"; exit 1; }

echo "==> building SPA"
(cd app/web && npm run build)

echo "==> installing build deps"
"$PY" -m pip install -q --upgrade pyinstaller

mkdir -p "$OUT"

echo "==> PyInstaller -> mediashelf-server-$TRIPLE"
"$PY" -m PyInstaller \
  --clean --noconfirm --onefile \
  --name "mediashelf-server-$TRIPLE" \
  --distpath "$OUT" \
  --workpath "$ROOT/desktop/.build" \
  --specpath "$ROOT/desktop/.build" \
  --add-data "$ROOT/app/web/dist:web/dist" \
  --collect-submodules uvicorn \
  --collect-submodules apscheduler \
  --hidden-import uvicorn.loops.auto \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import uvicorn.protocols.websockets.auto \
  --hidden-import uvicorn.lifespan.on \
  --hidden-import app.main \
  --exclude-module yt_dlp \
  --exclude-module pytest \
  --exclude-module PyInstaller \
  "$ROOT/app/__main__.py"

echo "==> built: $OUT/mediashelf-server-$TRIPLE"
"$OUT/mediashelf-server-$TRIPLE" --help >/dev/null && echo "==> smoke: --help OK"
