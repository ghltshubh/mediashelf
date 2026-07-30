"""Server entrypoint for the desktop build (P2).

The Tauri shell spawns this as a sidecar binary and points its webview at the
port below. Kept dependency-light and importable as `python -m app` so the same
path works from source and from the PyInstaller bundle.

Loopback only, never 0.0.0.0: the desktop build is a local app, not a LAN
server. Self-hosters who *want* LAN access run the Docker image instead.
"""

import argparse
import os
import sys
import threading
import time

# The default MUST stay 8000. accounts.py pins the OAuth redirect to
# http://127.0.0.1:8000/oauth2callback, and that exact URI is registered in the
# user's own Spotify/Google apps — a different port silently breaks every
# connector, so a busy port is a hard error rather than a silent reassignment.
DEFAULT_PORT = 8000


def _exit_with_parent() -> None:
    """Exit when whoever launched us goes away.

    The desktop shell kills its sidecar on quit, but a PyInstaller one-file
    binary is really two processes (bootloader + the Python it re-execs), so
    killing the visible child can orphan the server — it would keep holding
    port 8000 and running scheduled syncs after the app is gone. Watching for
    reparenting covers every exit path, including a force-quit or a crash.
    """
    original = os.getppid()

    def watch() -> None:
        while True:
            time.sleep(2)
            # Reparented (usually to launchd/init) means the parent is gone.
            if os.getppid() != original:
                os._exit(0)

    threading.Thread(target=watch, daemon=True).start()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mediashelf-server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--data-dir", default=None,
                        help="where the SQLite db, keys and backups live")
    parser.add_argument("--exit-with-parent", action="store_true",
                        help="shut down when the launching process exits (desktop shell)")
    args = parser.parse_args(argv)

    if args.exit_with_parent:
        _exit_with_parent()

    # Must be set before app.db is imported: data_dir() reads the env var and
    # the engine is cached per process.
    if args.data_dir:
        os.environ["MEDIASHELF_DATA_DIR"] = args.data_dir

    import uvicorn

    from app.main import create_app

    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
