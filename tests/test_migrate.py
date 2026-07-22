"""M5 acceptance: quota exhaustion mid-job → paused_quota, restartable with no
duplicates; review-queue items excluded until approved; journaled revert;
duplicate-job resume; same-account block; budgeter cap."""

import pytest

from app.connectors.base import QuotaExhausted
from app.db import session_factory
from app.models import MatchCandidate, MigrationJob
from app.services import migrate
from app.services.library import CONNECTORS


class FakeSpotify:
    key = "spotify"
    name = "Spotify"

    def __init__(self, likes):
        self._likes = likes

    def capabilities(self):
        return {"user_library": True, "write_likes": True, "write_follows": True}

    def connected(self, db):
        return True

    def account_id(self, db):
        return "spotify-user-1"

    def read_likes(self, db):
        return self._likes

    def read_follows(self, db):
        return []


class FakeYouTube:
    key = "youtube"
    name = "YouTube"

    def __init__(self, catalog, quota_after=None):
        self.catalog = catalog          # query title → list of candidates
        self.quota_after = quota_after  # writes allowed before quota blows
        self.writes: list[str] = []
        self.removed: list[str] = []

    def capabilities(self):
        return {"user_library": True, "write_likes": True, "write_follows": True}

    def connected(self, db):
        return True

    def account_id(self, db):
        return "yt-channel-1"

    def search_track(self, db, title, artists):
        return self.catalog.get(title, [])

    def search_channel(self, db, name):
        return []

    def add_like(self, db, video_id):
        if self.quota_after is not None and len(self.writes) >= self.quota_after:
            raise QuotaExhausted("youtube", "quotaExceeded")
        if video_id in self.writes:
            return "already"
        self.writes.append(video_id)
        return "added"

    def remove_like(self, db, video_id):
        self.removed.append(video_id)
        if video_id in self.writes:
            self.writes.remove(video_id)

    def follow(self, db, channel_id):
        return "added"

    def unfollow(self, db, channel_id):
        pass


def like(i, title, artists, dur, isrc=None):
    return {"external_id": f"sp{i}",
            "payload": {"title": title, "artists": artists, "duration_ms": dur, "isrc": isrc}}


def cand(vid, title, artists, dur, isrc=None):
    return {"title": title, "artists": artists, "duration_ms": dur, "isrc": isrc,
            "external_id": vid, "service": "youtube_music"}


@pytest.fixture
def fake_pair(monkeypatch):
    likes = [
        like(1, "Clean Match", ["Artist A"], 200000),
        like(2, "Ambiguous Song", ["Artist B"], 200000),
        like(3, "No Hit", ["Artist C"], 200000),
        like(4, "Second Clean", ["Artist D"], 180000),
    ]
    yt = FakeYouTube({
        "Clean Match": [cand("v1", "Clean Match", ["Artist A"], 201000)],
        "Ambiguous Song": [cand("v2", "Ambiguous Song (Live)", ["Artist B"], 201000)],
        "No Hit": [],
        "Second Clean": [cand("v4", "Second Clean", ["Artist D"], 181000)],
    })
    sp = FakeSpotify(likes)
    monkeypatch.setitem(CONNECTORS, "spotify", sp)
    monkeypatch.setitem(CONNECTORS, "youtube", yt)
    monkeypatch.setattr(migrate, "WRITE_SLEEP_S", 0)
    return sp, yt


def _make_and_run(db, scope=None):
    job, created = migrate.create_or_resume(db, "spotify", "youtube",
                                            scope or {"likes": True, "follows": False})
    db.commit()
    migrate.run_job(job.id)
    db.expire_all()
    return db.get(MigrationJob, job.id)


def test_full_run_with_review_gate(client, fake_pair):
    sp, yt = fake_pair
    with session_factory()() as db:
        job = _make_and_run(db)
        # Ambiguous item queued → job waits at review, nothing ambiguous written.
        assert job.status == "review"
        assert job.progress["counts"]["queued"] == 1
        assert job.progress["counts"]["failed"] == 1  # "No Hit"
        assert yt.writes == []  # review gate blocks ALL writing until resolved

        pending = db.scalars(select_pending(db, job.id)).all()
        assert len(pending) == 1
        pending[0].status = "approved"
        db.commit()

        migrate.run_job(job.id)
        db.expire_all()
        job = db.get(MigrationJob, job.id)
        assert job.status == "done"
        assert sorted(yt.writes) == ["v1", "v2", "v4"]
        assert job.progress["counts"]["added"] == 3
        assert len(job.progress["journal"]) == 3


def select_pending(db, job_id):
    from sqlalchemy import select

    return select(MatchCandidate).where(MatchCandidate.job_id == job_id,
                                        MatchCandidate.status == "pending")


def test_quota_pause_and_resume_no_duplicates(client, fake_pair, monkeypatch):
    sp, yt = fake_pair
    yt.catalog["Ambiguous Song"] = [cand("v2", "Ambiguous Song", ["Artist B"], 200500)]
    yt.quota_after = 2  # quota blows on the third write
    with session_factory()() as db:
        job = _make_and_run(db)
        assert job.status == "paused_quota"
        assert job.progress["resume_at"] is not None
        assert len(yt.writes) == 2

        # Next day: quota resets, job resumes — already-written items are NOT rewritten.
        yt.quota_after = None
        migrate.run_job(job.id)
        db.expire_all()
        job = db.get(MigrationJob, job.id)
        assert job.status == "done"
        assert len(yt.writes) == 3           # zero duplicates
        assert job.progress["counts"]["added"] == 3


def test_budgeter_caps_writes(client, fake_pair):
    sp, yt = fake_pair
    yt.catalog["Ambiguous Song"] = [cand("v2", "Ambiguous Song", ["Artist B"], 200500)]
    with session_factory()() as db:
        from app import settings_store

        settings_store.set_setting(db, "yt_write_cap", "2")
        job = _make_and_run(db)
        assert job.status == "paused_quota"
        assert len(yt.writes) == 2
        assert migrate.budget_left(db) == 0


def test_revert_undoes_journal(client, fake_pair):
    sp, yt = fake_pair
    yt.catalog["Ambiguous Song"] = [cand("v2", "Ambiguous Song", ["Artist B"], 200500)]
    with session_factory()() as db:
        job = _make_and_run(db)
        assert job.status == "done" and len(yt.writes) == 3
        migrate.revert_job(job.id)
        db.expire_all()
        job = db.get(MigrationJob, job.id)
        assert job.status == "reverted"
        assert yt.writes == [] and len(yt.removed) == 3
        assert job.progress["journal"] == []


def test_duplicate_job_resumes_not_forks(client, fake_pair):
    with session_factory()() as db:
        job1, created1 = migrate.create_or_resume(db, "spotify", "youtube",
                                                  {"likes": True, "follows": False})
        job2, created2 = migrate.create_or_resume(db, "spotify", "youtube",
                                                  {"likes": True, "follows": False})
        assert created1 is True and created2 is False
        assert job1.id == job2.id


def test_same_account_blocked(client, fake_pair, monkeypatch):
    sp, yt = fake_pair
    monkeypatch.setattr(FakeYouTube, "account_id", lambda self, db: "spotify-user-1")
    with session_factory()() as db:
        with pytest.raises(ValueError, match="same account"):
            migrate.create_or_resume(db, "spotify", "youtube", {"likes": True, "follows": False})


def test_unsupported_direction_blocked(client, fake_pair):
    with session_factory()() as db:
        with pytest.raises(ValueError, match="second Google account"):
            migrate.create_or_resume(db, "youtube", "youtube", {"likes": True, "follows": False})


def test_migrations_api(client, fake_pair):
    r = client.get("/api/migrations").json()
    assert {"cap", "used_today"} <= set(r["budget"])
    assert any(p["label"] == "Spotify → YouTube Music" for p in r["pairs"])

    r = client.post("/api/migrations", json={"source": "spotify", "target": "youtube",
                                             "likes": True, "follows": False})
    assert r.status_code == 200
    job_id = r.json()["id"]
    # Poll until the background thread settles into the review gate.
    import time as _t

    for _ in range(50):
        jobs = client.get("/api/migrations").json()["jobs"]
        j = next(x for x in jobs if x["id"] == job_id)
        if j["status"] in ("review", "done", "paused_quota", "failed"):
            break
        _t.sleep(0.1)
    assert j["status"] == "review"
    assert j["counts"]["queued"] == 1
