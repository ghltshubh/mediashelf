import sqlite3

from app.services import backups


def test_export_produces_healthy_db(client, tmp_path):
    r = client.get("/api/backup/export")
    assert r.status_code == 200
    exported = tmp_path / "export.db"
    exported.write_bytes(r.content)
    assert backups.integrity_ok(exported)
    # It's a real MediaShelf DB — services table is populated.
    con = sqlite3.connect(exported)
    count = con.execute("SELECT COUNT(*) FROM services").fetchone()[0]
    con.close()
    assert count > 0


def test_backup_prune_keeps_seven(client):
    for _ in range(9):
        backups.create_backup()
    files = sorted(backups.backups_dir().glob("mediashelf-*.db"))
    assert len(files) <= backups.KEEP


def test_import_rejects_garbage(client, tmp_path):
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"this is not a database")
    with bad.open("rb") as f:
        r = client.post("/api/backup/import", files={"file": ("bad.db", f, "application/octet-stream")})
    assert r.status_code == 400
    assert "not a healthy" in r.json()["detail"]


def test_corruption_restore_on_boot(client):
    # Take a good backup, corrupt the live DB, then run the boot check.
    backups.create_backup()
    db_file = backups.db_path()

    import app.db as app_db

    app_db.reset_engine_for_tests()
    db_file.write_bytes(b"garbage" * 1024)
    notice = backups.check_and_restore_on_boot()
    assert notice is not None and "restored from backup" in notice
    assert backups.integrity_ok(db_file)
    # The damaged file is quarantined, not silently deleted.
    assert list(db_file.parent.glob("mediashelf.corrupt-*"))


def test_healthy_db_boots_without_notice(client):
    assert backups.check_and_restore_on_boot() is None
