"""Database: persistence, buyers, submissions, settings, backup."""
from database import Database, display_id


def _make_submission(db, sha="h1", submitter=222, name="a.xlsx"):
    return db.create_submission(
        submitter_id=submitter, username="sub", full_name="Sub User",
        source_type="telegram_file", original_name=name, stored_path="/tmp/x.xlsx",
        telegram_file_id="fid", size_bytes=100, sha256=sha, sheets_count=1, rows_count=3,
    )


def test_admin_is_seeded(db, admin_id):
    assert db.is_admin(admin_id) is True
    assert db.is_admin(999) is False


def test_init_is_idempotent(db, admin_id):
    db.init(admin_id)
    db.init(admin_id)
    assert db._one("SELECT COUNT(*) AS n FROM schema_version")["n"] == 1


def test_data_survives_restart(tmp_path, admin_id):
    path = tmp_path / "persist.db"
    d1 = Database(path)
    d1.init(admin_id)
    d1.approve_user(222, "sub", "Sub", admin_id)
    sid = _make_submission(d1)
    d1.close()

    d2 = Database(path)
    d2.init(admin_id)
    assert d2.is_approved(222)
    assert d2.get_submission(sid)["original_name"] == "a.xlsx"
    d2.close()


def test_approve_and_remove_user(db, admin_id):
    assert db.is_approved(222) is False
    db.approve_user(222, "sub", "Sub", admin_id)
    assert db.is_approved(222) is True
    assert db.remove_user(222) is True
    assert db.is_approved(222) is False
    assert db.remove_user(222) is False


def test_access_request_cleared_on_approve(db, admin_id):
    assert db.add_access_request(222, "sub", "Sub") is True
    assert db.add_access_request(222, "sub", "Sub") is False
    db.approve_user(222, "sub", "Sub", admin_id)
    assert db.get_access_request(222) is None


def test_buyer_registration_with_invite(db):
    code = db.create_buyer_invite("Karim")
    buyer = db.consume_invite(code, 5551, "karim_u")
    assert buyer["chat_id"] == 5551
    assert buyer["name"] == "Karim"
    assert db.get_buyer_by_chat(5551) is not None
    assert db.find_buyer("@karim_u")["id"] == buyer["id"]
    assert db.find_buyer("5551")["id"] == buyer["id"]


def test_invite_is_single_use_and_invalid_codes_fail(db):
    code = db.create_buyer_invite("Karim")
    assert db.consume_invite(code, 5551, "k") is not None
    assert db.consume_invite(code, 6662, "other") is None
    assert db.consume_invite("doesnotexist", 7773, "x") is None
    assert len(db.list_buyers()) == 1


def test_remove_buyer_is_soft_delete(db):
    code = db.create_buyer_invite("Karim")
    buyer = db.consume_invite(code, 5551, "k")
    assert db.remove_buyer(buyer["id"]) is True
    assert db.list_buyers() == []
    assert db.get_buyer(buyer["id"]) is not None  # history stays linked


def test_submission_creation_and_display_id(db):
    sid = _make_submission(db)
    row = db.get_submission(sid)
    assert row["status"] == "pending"
    assert row["submitter_id"] == 222
    assert row["sha256"] == "h1"
    assert display_id(sid) == 1000 + sid
    assert db.count_submissions("pending") == 1
    assert len(db.list_user_submissions(222)) == 1


def test_duplicate_hash_detection(db):
    sid = _make_submission(db, sha="same")
    dup = db.find_duplicate_by_hash("same")
    assert dup is not None and dup["id"] == sid
    assert db.find_duplicate_by_hash("different") is None


def test_reject_submission(db):
    sid = _make_submission(db)
    db.reject_submission(sid)
    assert db.get_submission(sid)["status"] == "rejected"
    assert db.count_submissions("pending") == 0


def test_settings_toggle(db):
    assert db.get_setting("submissions_open") == "1"
    assert db.toggle_setting("submissions_open") == "0"
    assert db.get_setting("submissions_open") == "0"
    assert db.toggle_setting("submissions_open") == "1"


def test_stats(db, admin_id):
    db.approve_user(222, "sub", "Sub", admin_id)
    _make_submission(db)
    s = db.stats()
    assert s["approved_users"] == 1
    assert s["submissions"] == 1
    assert s["pending"] == 1


def test_backup_creates_file_and_keeps_limit(db, tmp_path):
    bdir = tmp_path / "backups"
    for _ in range(3):
        db.backup(bdir, keep=2)
    files = list(bdir.glob("bot_*.db"))
    assert 1 <= len(files) <= 2
    assert all(f.stat().st_size > 0 for f in files)
