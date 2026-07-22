"""SQLite safety (plan: failure modes, M1).

Nightly copy-on-write backups (keep 7) into the data volume, one-click
export/import, and corruption-on-boot restore from the latest good backup.
Uses sqlite3's online backup API so copies are consistent while the app runs.
"""

import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.db import data_dir

logger = logging.getLogger(__name__)

KEEP = 7


def db_path() -> Path:
    return data_dir() / "mediashelf.db"


def backups_dir() -> Path:
    d = data_dir() / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def integrity_ok(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = con.execute("PRAGMA integrity_check").fetchone()
        finally:
            con.close()
        return bool(row) and row[0] == "ok"
    except sqlite3.Error:
        return False


def create_backup(dest: Path | None = None) -> Path:
    """Consistent online copy of the live DB; prunes to the newest KEEP."""
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target = dest or backups_dir() / f"mediashelf-{stamp}.db"
    src = sqlite3.connect(db_path())
    try:
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    if dest is None:
        prune()
    return target


def prune(keep: int = KEEP) -> None:
    backups = sorted(backups_dir().glob("mediashelf-*.db"))
    for old in backups[:-keep]:
        old.unlink(missing_ok=True)


def latest_good_backup() -> Path | None:
    for candidate in sorted(backups_dir().glob("mediashelf-*.db"), reverse=True):
        if integrity_ok(candidate):
            return candidate
    return None


def check_and_restore_on_boot() -> str | None:
    """Returns a human-readable notice if a restore (or reset) happened, else None."""
    path = db_path()
    if not path.exists() or integrity_ok(path):
        return None
    quarantine = path.with_suffix(f".corrupt-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}")
    path.rename(quarantine)
    backup = latest_good_backup()
    if backup is None:
        logger.error("database corrupt, no usable backup — starting fresh (kept %s)", quarantine.name)
        return (
            "The database was corrupted and no backup was available, so MediaShelf started fresh. "
            f"The damaged file was kept as {quarantine.name}."
        )
    import shutil

    shutil.copyfile(backup, path)
    logger.warning("database corrupt — restored %s (kept %s)", backup.name, quarantine.name)
    return (
        f"The database was corrupted on startup and was restored from backup {backup.name}. "
        f"The damaged file was kept as {quarantine.name}."
    )
