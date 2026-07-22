"""Migration job runner (M5).

Resumable state machine persisted in SQLite, safe to stop/restart across days:
pending → matching → review → writing → paused_quota → done
(plus paused_auth, stopped, failed, reverted).

Failure-mode guarantees (plan):
- every write is journaled (action → target id) → "Revert this job" undoes it
- duplicate job (same source, target, scope) resumes instead of forking
- write-quota budgeter: one pool, conservative per-day cap (default 150 < the
  theoretical ~190 — provider anti-spam limits risk the user's account)
- quota reset scheduling against midnight America/Los_Angeles
- same account as source and target is blocked before the job starts
- ≥0.3s sleep between writes (hard constraint)
- ambiguous matches go to the review queue and are excluded until approved
"""

import logging
import threading
import time
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app import settings_store
from app.connectors.base import AuthExpired, QuotaExhausted
from app.db import session_factory
from app.models import MatchCandidate, MigrationJob, Service
from app.services import matching
from app.services.library import CONNECTORS

logger = logging.getLogger(__name__)

LA = ZoneInfo("America/Los_Angeles")
DEFAULT_WRITE_CAP = 150
WRITE_SLEEP_S = 0.3
ACTIVE_STATUSES = ("pending", "matching", "review", "writing", "paused_quota", "paused_auth")

# Migration matrix is DERIVED from connector capabilities, never hand-listed:
# any connector that reads a library pairs with any that writes one, so every
# new connector (Apple Music, SoundCloud, Deezer, Tidal — M8) joins the matrix
# automatically on merge. Same-service transfers need a second account slot.
_MIGRATION_LABELS = {"youtube": "YouTube Music"}  # music context labeling (plan M4 rule)


def _migration_label(key: str) -> str:
    return _MIGRATION_LABELS.get(key) or CONNECTORS[key].name


def available_pairs() -> dict[tuple[str, str], str]:
    pairs: dict[tuple[str, str], str] = {}
    for a_key, a in CONNECTORS.items():
        for b_key, b in CONNECTORS.items():
            if a_key == b_key:
                continue
            ca = a.capabilities() if hasattr(a, "capabilities") else {}
            cb = b.capabilities() if hasattr(b, "capabilities") else {}
            if ca.get("user_library") and (cb.get("write_likes") or cb.get("write_follows")):
                pairs[(a_key, b_key)] = f"{_migration_label(a_key)} → {_migration_label(b_key)}"
    return pairs

_stop_flags: dict[int, threading.Event] = {}


# ---------- write-quota budgeter ----------

def _la_today() -> str:
    return datetime.now(LA).strftime("%Y%m%d")


def next_quota_reset() -> datetime:
    """YouTube quota resets at midnight America/Los_Angeles, regardless of the
    user's timezone/DST (plan failure modes)."""
    now = datetime.now(LA)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
    return tomorrow.astimezone(UTC)


def write_cap(db: Session) -> int:
    raw = settings_store.get_setting(db, "yt_write_cap")
    try:
        return max(1, min(int(raw), 190)) if raw else DEFAULT_WRITE_CAP
    except ValueError:
        return DEFAULT_WRITE_CAP


def writes_used_today(db: Session) -> int:
    raw = settings_store.get_setting(db, f"yt_writes_{_la_today()}")
    return int(raw) if raw else 0


def _record_write(db: Session) -> None:
    key = f"yt_writes_{_la_today()}"
    settings_store.set_setting(db, key, str(writes_used_today(db) + 1))


def budget_left(db: Session) -> int:
    return write_cap(db) - writes_used_today(db)


# ---------- job helpers ----------

def _service_id(db: Session, key: str) -> int | None:
    return db.scalar(select(Service.id).where(Service.key == key))


def _service_key(db: Session, service_id: int | None) -> str | None:
    if service_id is None:
        return None
    return db.scalar(select(Service.key).where(Service.id == service_id))


def _log(db: Session, job: MigrationJob, line: str) -> None:
    stamp = datetime.now(UTC).strftime("%H:%M:%S")
    job.log = [*job.log, f"{stamp} {line}"][-300:]
    flag_modified(job, "log")
    db.commit()


def _set_progress(db: Session, job: MigrationJob, **updates) -> None:
    # The runner mutates nested dicts it already handed to this attribute, so a
    # plain reassignment can compare equal and SQLAlchemy would skip the UPDATE
    # — flag_modified forces persistence every time (resumability depends on it).
    job.progress = {**job.progress, **updates}
    flag_modified(job, "progress")
    db.commit()


def job_json(db: Session, job: MigrationJob) -> dict:
    p = job.progress
    return {
        "id": job.id,
        "source": _service_key(db, job.source_service_id),
        "target": _service_key(db, job.target_service_id),
        "status": job.status,
        "scope": job.scope,
        "counts": p.get("counts", {}),
        "total": p.get("total", 0),
        "resume_at": p.get("resume_at"),
        "journal_size": len(p.get("journal", [])),
        "log": job.log[-20:],
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


def create_or_resume(db: Session, source: str, target: str, scope: dict) -> tuple[MigrationJob, bool]:
    """Duplicate-job protection: an identical active job resumes, never forks."""
    if source == target:
        raise ValueError("Same-service transfers need a second Google account slot "
                         "— multi-account support hasn't landed yet")
    if (source, target) not in available_pairs():
        raise ValueError("That direction isn't supported yet — the matrix grows "
                         "automatically as connectors land (M8)")
    src, tgt = CONNECTORS[source], CONNECTORS[target]
    if not src.connected(db):
        raise ValueError(f"Connect {src.name} first")
    if not tgt.connected(db):
        raise ValueError(f"Connect {tgt.name} first")
    sid, tid = src.account_id(db), tgt.account_id(db)
    if sid and tid and sid == tid:
        raise ValueError("Source and target are the same account — nothing to migrate")

    source_id, target_id = _service_id(db, source), _service_id(db, target)
    existing = db.scalar(select(MigrationJob).where(
        MigrationJob.source_service_id == source_id,
        MigrationJob.target_service_id == target_id,
        MigrationJob.status.in_(ACTIVE_STATUSES)))
    if existing is not None and existing.scope == scope:
        return existing, False

    job = MigrationJob(source_service_id=source_id, target_service_id=target_id,
                       status="pending", scope=scope,
                       progress={"counts": {"added": 0, "already": 0, "failed": 0,
                                            "skipped": 0, "queued": 0},
                                 "resolved": {}, "journal": [], "total": 0})
    db.add(job)
    db.commit()
    return job, True


# ---------- the runner (sync; called via asyncio.to_thread) ----------

def run_job(job_id: int) -> None:
    stop = _stop_flags.setdefault(job_id, threading.Event())
    stop.clear()
    with session_factory()() as db:
        job = db.get(MigrationJob, job_id)
        if job is None or job.status in ("done", "stopped", "reverted", "failed"):
            return
        try:
            _run_phases(db, job, stop)
        except AuthExpired as exc:
            job.status = "paused_auth"
            _log(db, job, f"Reconnect {exc.provider} to continue — progress saved.")
        except QuotaExhausted:
            _pause_quota(db, job)
        except Exception as exc:
            logger.exception("migration job %s failed", job_id)
            job.status = "failed"
            _log(db, job, f"Failed: {exc}")
        db.commit()


def _pause_quota(db: Session, job: MigrationJob) -> None:
    job.status = "paused_quota"
    resume_at = next_quota_reset()
    _set_progress(db, job, resume_at=resume_at.isoformat())
    counts = job.progress["counts"]
    done_n = counts["added"] + counts["already"]
    _log(db, job, f"Daily YouTube limit reached. Saved at {done_n}/{job.progress.get('total', '?')}; "
                  "resumes tomorrow.")


def _run_phases(db: Session, job: MigrationJob, stop: threading.Event) -> None:
    source_key, target_key = _service_key(db, job.source_service_id), _service_key(db, job.target_service_id)
    assert source_key is not None and target_key is not None
    source, target = CONNECTORS[source_key], CONNECTORS[target_key]

    # ---- matching phase ----
    job.status = "matching"
    db.commit()
    items: list[tuple[str, dict]] = []   # (kind, payload)
    if job.scope.get("likes"):
        items += [("like", e["payload"] | {"external_id": e["external_id"]})
                  for e in source.read_likes(db)]
    if job.scope.get("follows"):
        items += [("follow", e["payload"] | {"external_id": e["external_id"]})
                  for e in source.read_follows(db)]
    _set_progress(db, job, total=len(items))
    _log(db, job, f"Read {len(items)} items from {source.name}.")

    resolved: dict = dict(job.progress.get("resolved", {}))
    counts = dict(job.progress["counts"])
    for kind, payload in items:
        if stop.is_set():
            job.status = "stopped"
            _log(db, job, "Stopped.")
            return
        sid = f"{kind}:{payload['external_id']}"
        if sid in resolved:
            continue
        title = payload.get("title", "")
        artists = payload.get("artists") or ([payload["channel"]] if payload.get("channel") else [])
        if kind == "like":
            candidates = target.search_track(db, title, artists)
        else:
            candidates = (target.search_channel(db, title) if hasattr(target, "search_channel")
                          else target.search_artist(db, title))
        refs = [matching.TrackRef(title=c["title"], artists=c.get("artists", []),
                                  duration_ms=c.get("duration_ms"), isrc=c.get("isrc"),
                                  external_id=c["external_id"], payload=c)
                for c in candidates]
        src_ref = matching.TrackRef(title=title, artists=artists,
                                    duration_ms=payload.get("duration_ms"),
                                    isrc=payload.get("isrc"))
        result = matching.best_match(src_ref, refs)
        if result.status == "matched" and result.candidate is not None:
            resolved[sid] = {"state": "matched", "kind": kind,
                             "target_id": result.candidate.external_id,
                             "confidence": result.confidence}
        elif result.status == "review" and result.candidate is not None:
            cand = MatchCandidate(job_id=job.id, confidence=result.confidence,
                                  source_payload={**payload, "kind": kind,
                                                  "service": source.key},
                                  candidate_payload=result.candidate.payload)
            db.add(cand)
            db.flush()
            resolved[sid] = {"state": "review", "kind": kind, "candidate_id": cand.id}
            counts["queued"] += 1
        else:
            resolved[sid] = {"state": "none", "kind": kind}
            counts["failed"] += 1
        _set_progress(db, job, resolved=resolved, counts=counts)

    # ---- review gate: approved/replaced flow in; pending block writing ----
    for _sid, r in resolved.items():
        if r["state"] != "review":
            continue
        reviewed = db.get(MatchCandidate, r.get("candidate_id"))
        if reviewed is None:
            r["state"] = "none"
            continue
        if reviewed.status in ("approved", "replaced"):
            target_id = reviewed.candidate_payload.get("external_id") \
                or reviewed.candidate_payload.get("spotify_id")
            if target_id:
                r.update(state="matched", target_id=target_id, confidence=reviewed.confidence)
                counts["queued"] = max(0, counts["queued"] - 1)
            else:
                r["state"] = "none"
                counts["failed"] += 1
        elif reviewed.status == "skipped":
            r["state"] = "skipped"
            counts["skipped"] += 1
            counts["queued"] = max(0, counts["queued"] - 1)
    _set_progress(db, job, resolved=resolved, counts=counts)

    pending = db.scalar(select(MatchCandidate).where(MatchCandidate.job_id == job.id,
                                                     MatchCandidate.status == "pending"))
    if pending is not None:
        job.status = "review"
        _log(db, job, f"{counts['queued']} ambiguous matches need review — nothing is "
                      "written until you approve them.")
        return

    # ---- writing phase ----
    job.status = "writing"
    db.commit()
    journal = list(job.progress.get("journal", []))
    written = {(j["kind"], j["target_id"]) for j in journal}
    target_is_youtube = target.key == "youtube"
    for _sid, r in resolved.items():
        if stop.is_set():
            job.status = "stopped"
            _log(db, job, "Stopped — journal kept, revert available.")
            return
        if r["state"] != "matched" or (r["kind"], r["target_id"]) in written:
            continue
        if target_is_youtube and budget_left(db) <= 0:
            _pause_quota(db, job)
            return
        outcome = (target.add_like(db, r["target_id"]) if r["kind"] == "like"
                   else target.follow(db, r["target_id"]))
        if target_is_youtube:
            _record_write(db)
        counts[outcome if outcome == "already" else "added"] += 1
        if outcome == "added":
            journal.append({"kind": r["kind"], "target_id": r["target_id"],
                            "at": datetime.now(UTC).isoformat()})
        written.add((r["kind"], r["target_id"]))
        _set_progress(db, job, counts=counts, journal=journal)
        time.sleep(WRITE_SLEEP_S)

    job.status = "done"
    _log(db, job, f"Done — added {counts['added']} · already there {counts['already']} · "
                  f"failed {counts['failed']} · skipped {counts['skipped']}.")


def revert_job(job_id: int) -> None:
    """Undo: unlike/unsubscribe exactly what this job's journal wrote."""
    with session_factory()() as db:
        job = db.get(MigrationJob, job_id)
        if job is None:
            return
        target_key = _service_key(db, job.target_service_id)
        assert target_key is not None
        target = CONNECTORS[target_key]
        journal = list(job.progress.get("journal", []))
        undone = 0
        try:
            while journal:
                entry = journal[-1]
                if entry["kind"] == "like":
                    target.remove_like(db, entry["target_id"])
                else:
                    target.unfollow(db, entry["target_id"])
                undone += 1
                journal.pop()
                _set_progress(db, job, journal=journal)
                time.sleep(WRITE_SLEEP_S)
            job.status = "reverted"
            _log(db, job, f"Reverted {undone} writes.")
        except QuotaExhausted:
            _pause_quota(db, job)
            _log(db, job, f"Revert paused by quota after {undone} undos — resumes tomorrow.")
        except Exception as exc:
            _log(db, job, f"Revert stopped after {undone} undos: {exc}")
        db.commit()


def request_stop(job_id: int) -> None:
    _stop_flags.setdefault(job_id, threading.Event()).set()


def due_resumes(db: Session) -> list[int]:
    """Jobs whose quota window has reset — auto-resume next launch (plan §4.6)."""
    now = datetime.now(UTC)
    out = []
    for job in db.scalars(select(MigrationJob).where(MigrationJob.status == "paused_quota")):
        resume_at = job.progress.get("resume_at")
        if resume_at and datetime.fromisoformat(resume_at) <= now:
            out.append(job.id)
    return out
