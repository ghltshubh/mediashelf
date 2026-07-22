from app.db import session_factory
from app.models import MatchCandidate


def _seed(db, n=3, base_conf=0.6):
    ids = []
    for i in range(n):
        c = MatchCandidate(
            source_payload={"title": f"Song {i}", "artists": ["A"], "duration_ms": 200000,
                            "service": "spotify"},
            candidate_payload={"title": f"Song {i} (Live)", "artists": ["A"],
                               "duration_ms": 210000, "service": "youtube_music"},
            confidence=base_conf + i * 0.15,
        )
        db.add(c)
        db.flush()
        ids.append(c.id)
    db.commit()
    return ids


def test_review_lifecycle(client):
    with session_factory()() as db:
        ids = _seed(db)

    q = client.get("/api/review").json()["pending"]
    assert len(q) == 3
    # Highest confidence first.
    assert q[0]["confidence"] >= q[-1]["confidence"]

    approved = client.post(f"/api/review/{ids[0]}/approve").json()
    assert approved["status"] == "approved"
    skipped = client.post(f"/api/review/{ids[1]}/skip").json()
    assert skipped["status"] == "skipped"
    # Idempotence guard: acting twice conflicts instead of silently rewriting.
    assert client.post(f"/api/review/{ids[0]}/approve").status_code == 409

    replaced = client.post(f"/api/review/{ids[2]}/replace", json={
        "candidate": {"title": "Song 2", "artists": ["A"], "spotify_id": "xyz"},
    }).json()
    assert replaced["status"] == "replaced" and replaced["confidence"] == 1.0

    assert client.get("/api/review").json()["pending"] == []


def test_replace_requires_title(client):
    with session_factory()() as db:
        ids = _seed(db, n=1)
    r = client.post(f"/api/review/{ids[0]}/replace", json={"candidate": {}})
    assert r.status_code == 422


def test_batch_approve_threshold(client):
    with session_factory()() as db:
        _seed(db, n=3, base_conf=0.7)  # 0.70, 0.85, 1.00
    r = client.post("/api/review/approve-batch", json={"min_confidence": 0.85}).json()
    assert r["approved"] == 2
    assert len(client.get("/api/review").json()["pending"]) == 1
