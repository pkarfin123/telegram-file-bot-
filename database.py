"""SQLite layer: safe initialisation, versioned migrations, all queries.

Methods are synchronous (SQLite is fast) and thread-safe via a lock.
Async handlers call them through `arun(...)` so the event loop never blocks.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

log = logging.getLogger(__name__)

DISPLAY_ID_OFFSET = 1000  # submission row 24 is shown as #1024


def display_id(submission_id: int) -> int:
    return DISPLAY_ID_OFFSET + int(submission_id)


def real_id(shown: int) -> int:
    return int(shown) - DISPLAY_ID_OFFSET


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


async def arun(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run a blocking DB call in a worker thread."""
    return await asyncio.to_thread(func, *args, **kwargs)


DEFAULT_SETTINGS = {
    "notify_on_submit": "1",
    "accept_xlsx": "1",
    "accept_sheets": "1",
    "submissions_open": "1",
}

# ---------------------------------------------------------------- migrations
MIGRATION_1 = """
CREATE TABLE admins (
    telegram_id INTEGER PRIMARY KEY,
    added_at    TEXT NOT NULL
);

CREATE TABLE approved_users (
    telegram_id INTEGER PRIMARY KEY,
    username    TEXT,
    full_name   TEXT,
    approved_by INTEGER NOT NULL,
    approved_at TEXT NOT NULL
);

CREATE TABLE access_requests (
    telegram_id  INTEGER PRIMARY KEY,
    username     TEXT,
    full_name    TEXT,
    requested_at TEXT NOT NULL
);

CREATE TABLE buyers (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    username      TEXT,
    chat_id       INTEGER NOT NULL UNIQUE,
    registered_at TEXT NOT NULL,
    is_active     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE buyer_invites (
    code         TEXT PRIMARY KEY,
    buyer_name   TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    used_at      TEXT,
    used_chat_id INTEGER
);

CREATE TABLE submissions (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    submitter_id       INTEGER NOT NULL,
    submitter_username TEXT,
    submitter_name     TEXT,
    source_type        TEXT NOT NULL CHECK (source_type IN ('telegram_file','google_sheet')),
    status             TEXT NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending','delivered','rejected')),
    created_at         TEXT NOT NULL,
    delivered_at       TEXT,
    delivered_buyer_id INTEGER
);

CREATE TABLE files (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id    INTEGER NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    original_name    TEXT NOT NULL,
    stored_path      TEXT NOT NULL,
    telegram_file_id TEXT,
    size_bytes       INTEGER NOT NULL DEFAULT 0,
    sha256           TEXT NOT NULL,
    sheet_url        TEXT,
    sheets_count     INTEGER,
    rows_count       INTEGER,
    created_at       TEXT NOT NULL
);
CREATE INDEX idx_files_sha ON files(sha256);
CREATE INDEX idx_files_sub ON files(submission_id);

CREATE TABLE deliveries (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id       INTEGER NOT NULL REFERENCES submissions(id),
    file_id             INTEGER NOT NULL REFERENCES files(id),
    buyer_id            INTEGER NOT NULL REFERENCES buyers(id),
    submitter_id        INTEGER NOT NULL,
    status              TEXT NOT NULL CHECK (status IN ('success','failed')),
    error               TEXT,
    telegram_message_id INTEGER,
    created_at          TEXT NOT NULL
);
CREATE INDEX idx_deliv_sub ON deliveries(submission_id);
CREATE INDEX idx_deliv_buyer ON deliveries(buyer_id);

CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Add future migrations at the end as (version, sql). Never edit old ones.
MIGRATIONS: list[tuple[int, str]] = [(1, MIGRATION_1)]


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            self.path, check_same_thread=False, isolation_level=None, timeout=30
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA synchronous=NORMAL")

    # ------------------------------------------------------------ plumbing
    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            else:
                self._conn.execute("COMMIT")

    def _one(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def _all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------ init
    def init(self, admin_id: int) -> None:
        """Create/upgrade schema safely. Existing data is never dropped."""
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
            )
            row = self._conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
            current = row["v"] or 0
        for version, sql in MIGRATIONS:
            if version <= current:
                continue
            log.info("Applying migration %s", version)
            with self._tx() as c:
                for stmt in _split_sql(sql):
                    c.execute(stmt)
                c.execute("INSERT INTO schema_version(version) VALUES (?)", (version,))
        with self._tx() as c:
            c.execute(
                "INSERT OR IGNORE INTO admins(telegram_id, added_at) VALUES (?,?)",
                (admin_id, utcnow()),
            )
            for k, v in DEFAULT_SETTINGS.items():
                c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES (?,?)", (k, v))

    def backup(self, backup_dir: Path, keep: int = 14) -> Path:
        """Consistent online backup using SQLite's backup API."""
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        target = backup_dir / f"bot_{stamp}.db"
        with self._lock:
            dest = sqlite3.connect(target)
            try:
                self._conn.backup(dest)
            finally:
                dest.close()
        old = sorted(backup_dir.glob("bot_*.db"))
        for f in old[:-keep]:
            try:
                f.unlink()
            except OSError:
                log.warning("Could not delete old backup %s", f)
        return target

    # ------------------------------------------------------------ settings
    def get_setting(self, key: str) -> str:
        row = self._one("SELECT value FROM settings WHERE key=?", (key,))
        return row["value"] if row else DEFAULT_SETTINGS.get(key, "")

    def set_setting(self, key: str, value: str) -> None:
        with self._tx() as c:
            c.execute(
                "INSERT INTO settings(key,value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def toggle_setting(self, key: str) -> str:
        new = "0" if self.get_setting(key) == "1" else "1"
        self.set_setting(key, new)
        return new

    # ------------------------------------------------------------ admins
    def is_admin(self, telegram_id: int) -> bool:
        return self._one("SELECT 1 FROM admins WHERE telegram_id=?", (telegram_id,)) is not None

    # ------------------------------------------------------------ approved users
    def approve_user(self, telegram_id: int, username: Optional[str],
                     full_name: Optional[str], approved_by: int) -> None:
        with self._tx() as c:
            c.execute(
                "INSERT INTO approved_users(telegram_id,username,full_name,approved_by,approved_at) "
                "VALUES (?,?,?,?,?) ON CONFLICT(telegram_id) DO UPDATE SET "
                "username=COALESCE(excluded.username, username), "
                "full_name=COALESCE(excluded.full_name, full_name)",
                (telegram_id, username, full_name, approved_by, utcnow()),
            )
            c.execute("DELETE FROM access_requests WHERE telegram_id=?", (telegram_id,))

    def remove_user(self, telegram_id: int) -> bool:
        with self._tx() as c:
            cur = c.execute("DELETE FROM approved_users WHERE telegram_id=?", (telegram_id,))
            return cur.rowcount > 0

    def is_approved(self, telegram_id: int) -> bool:
        return self._one(
            "SELECT 1 FROM approved_users WHERE telegram_id=?", (telegram_id,)
        ) is not None

    def list_approved(self) -> list[sqlite3.Row]:
        return self._all("SELECT * FROM approved_users ORDER BY approved_at DESC")

    def touch_user_profile(self, telegram_id: int, username: Optional[str],
                           full_name: Optional[str]) -> None:
        with self._tx() as c:
            c.execute(
                "UPDATE approved_users SET username=?, full_name=? WHERE telegram_id=?",
                (username, full_name, telegram_id),
            )

    # ------------------------------------------------------------ access requests
    def add_access_request(self, telegram_id: int, username: Optional[str],
                           full_name: Optional[str]) -> bool:
        """Returns True if this is a NEW request."""
        with self._tx() as c:
            cur = c.execute(
                "INSERT OR IGNORE INTO access_requests(telegram_id,username,full_name,requested_at) "
                "VALUES (?,?,?,?)",
                (telegram_id, username, full_name, utcnow()),
            )
            return cur.rowcount > 0

    def list_access_requests(self) -> list[sqlite3.Row]:
        return self._all("SELECT * FROM access_requests ORDER BY requested_at")

    def get_access_request(self, telegram_id: int) -> Optional[sqlite3.Row]:
        return self._one("SELECT * FROM access_requests WHERE telegram_id=?", (telegram_id,))

    def delete_access_request(self, telegram_id: int) -> None:
        with self._tx() as c:
            c.execute("DELETE FROM access_requests WHERE telegram_id=?", (telegram_id,))

    # ------------------------------------------------------------ buyers
    def create_buyer_invite(self, buyer_name: str) -> str:
        code = secrets.token_urlsafe(9).replace("-", "x").replace("_", "y")
        with self._tx() as c:
            c.execute(
                "INSERT INTO buyer_invites(code,buyer_name,created_at) VALUES (?,?,?)",
                (code, buyer_name, utcnow()),
            )
        return code

    def consume_invite(self, code: str, chat_id: int,
                       username: Optional[str]) -> Optional[sqlite3.Row]:
        """Register the buyer using the verified chat_id. One-time use."""
        with self._tx() as c:
            inv = c.execute(
                "SELECT * FROM buyer_invites WHERE code=? AND used_at IS NULL", (code,)
            ).fetchone()
            if inv is None:
                return None
            c.execute(
                "INSERT INTO buyers(name,username,chat_id,registered_at,is_active) "
                "VALUES (?,?,?,?,1) ON CONFLICT(chat_id) DO UPDATE SET "
                "name=excluded.name, username=excluded.username, is_active=1",
                (inv["buyer_name"], username, chat_id, utcnow()),
            )
            c.execute(
                "UPDATE buyer_invites SET used_at=?, used_chat_id=? WHERE code=?",
                (utcnow(), chat_id, code),
            )
            return c.execute("SELECT * FROM buyers WHERE chat_id=?", (chat_id,)).fetchone()

    def list_buyers(self, active_only: bool = True) -> list[sqlite3.Row]:
        sql = "SELECT * FROM buyers"
        if active_only:
            sql += " WHERE is_active=1"
        return self._all(sql + " ORDER BY name COLLATE NOCASE")

    def get_buyer(self, buyer_id: int) -> Optional[sqlite3.Row]:
        return self._one("SELECT * FROM buyers WHERE id=?", (buyer_id,))

    def get_buyer_by_chat(self, chat_id: int) -> Optional[sqlite3.Row]:
        return self._one("SELECT * FROM buyers WHERE chat_id=? AND is_active=1", (chat_id,))

    def find_buyer(self, query: str) -> Optional[sqlite3.Row]:
        """Find by numeric buyer id, chat id, or @username."""
        q = query.strip()
        if q.lstrip("-").isdigit():
            n = int(q)
            return self._one(
                "SELECT * FROM buyers WHERE (id=? OR chat_id=?) AND is_active=1", (n, n)
            )
        return self._one(
            "SELECT * FROM buyers WHERE lower(username)=lower(?) AND is_active=1",
            (q.lstrip("@"),),
        )

    def remove_buyer(self, buyer_id: int) -> bool:
        """Soft-delete: delivery history keeps pointing at the buyer row."""
        with self._tx() as c:
            cur = c.execute("UPDATE buyers SET is_active=0 WHERE id=? AND is_active=1", (buyer_id,))
            return cur.rowcount > 0

    def buyer_delivery_history(self, buyer_id: int, limit: int = 20) -> list[sqlite3.Row]:
        return self._all(
            "SELECT d.*, f.original_name FROM deliveries d "
            "JOIN files f ON f.id=d.file_id WHERE d.buyer_id=? "
            "ORDER BY d.id DESC LIMIT ?",
            (buyer_id, limit),
        )

    # ------------------------------------------------------------ submissions
    def create_submission(self, *, submitter_id: int, username: Optional[str],
                          full_name: Optional[str], source_type: str,
                          original_name: str, stored_path: str,
                          telegram_file_id: Optional[str], size_bytes: int,
                          sha256: str, sheet_url: Optional[str] = None,
                          sheets_count: Optional[int] = None,
                          rows_count: Optional[int] = None) -> int:
        now = utcnow()
        with self._tx() as c:
            cur = c.execute(
                "INSERT INTO submissions(submitter_id,submitter_username,submitter_name,"
                "source_type,status,created_at) VALUES (?,?,?,?, 'pending', ?)",
                (submitter_id, username, full_name, source_type, now),
            )
            sub_id = cur.lastrowid
            c.execute(
                "INSERT INTO files(submission_id,original_name,stored_path,telegram_file_id,"
                "size_bytes,sha256,sheet_url,sheets_count,rows_count,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (sub_id, original_name, stored_path, telegram_file_id, size_bytes,
                 sha256, sheet_url, sheets_count, rows_count, now),
            )
            return int(sub_id)

    _SUB_SELECT = (
        "SELECT s.*, f.id AS file_id, f.original_name, f.stored_path, f.telegram_file_id, "
        "f.size_bytes, f.sha256, f.sheet_url, f.sheets_count, f.rows_count "
        "FROM submissions s JOIN files f ON f.submission_id=s.id "
    )

    def get_submission(self, submission_id: int) -> Optional[sqlite3.Row]:
        return self._one(self._SUB_SELECT + "WHERE s.id=?", (submission_id,))

    def list_submissions(self, status: Optional[str] = None, limit: int = 8,
                         offset: int = 0) -> list[sqlite3.Row]:
        if status:
            return self._all(
                self._SUB_SELECT + "WHERE s.status=? ORDER BY s.id DESC LIMIT ? OFFSET ?",
                (status, limit, offset),
            )
        return self._all(
            self._SUB_SELECT + "ORDER BY s.id DESC LIMIT ? OFFSET ?", (limit, offset)
        )

    def count_submissions(self, status: Optional[str] = None) -> int:
        if status:
            row = self._one("SELECT COUNT(*) AS n FROM submissions WHERE status=?", (status,))
        else:
            row = self._one("SELECT COUNT(*) AS n FROM submissions")
        return int(row["n"])

    def find_duplicate_by_hash(self, sha256: str) -> Optional[sqlite3.Row]:
        return self._one(
            self._SUB_SELECT + "WHERE f.sha256=? ORDER BY s.id LIMIT 1", (sha256,)
        )

    def reject_submission(self, submission_id: int) -> None:
        with self._tx() as c:
            c.execute(
                "UPDATE submissions SET status='rejected' WHERE id=? AND status='pending'",
                (submission_id,),
            )

    # ------------------------------------------------------------ deliveries
    def has_successful_delivery(self, file_id: int, buyer_id: Optional[int] = None) -> bool:
        if buyer_id is None:
            row = self._one(
                "SELECT 1 FROM deliveries WHERE file_id=? AND status='success' LIMIT 1",
                (file_id,),
            )
        else:
            row = self._one(
                "SELECT 1 FROM deliveries WHERE file_id=? AND buyer_id=? AND status='success' LIMIT 1",
                (file_id, buyer_id),
            )
        return row is not None

    def deliveries_for_submission(self, submission_id: int) -> list[sqlite3.Row]:
        return self._all(
            "SELECT d.*, b.name AS buyer_name, b.username AS buyer_username "
            "FROM deliveries d JOIN buyers b ON b.id=d.buyer_id "
            "WHERE d.submission_id=? AND d.status='success' ORDER BY d.id",
            (submission_id,),
        )

    def record_delivery(self, *, submission_id: int, file_id: int, buyer_id: int,
                        submitter_id: int, success: bool, error: Optional[str] = None,
                        telegram_message_id: Optional[int] = None) -> int:
        """Call with success=True ONLY after Telegram confirmed the send."""
        now = utcnow()
        with self._tx() as c:
            cur = c.execute(
                "INSERT INTO deliveries(submission_id,file_id,buyer_id,submitter_id,status,"
                "error,telegram_message_id,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (submission_id, file_id, buyer_id, submitter_id,
                 "success" if success else "failed",
                 (error or None) and error[:500], telegram_message_id, now),
            )
            if success:
                c.execute(
                    "UPDATE submissions SET status='delivered', delivered_at=?, "
                    "delivered_buyer_id=? WHERE id=?",
                    (now, buyer_id, submission_id),
                )
            return int(cur.lastrowid)

    def list_deliveries(self, limit: int = 8, offset: int = 0) -> list[sqlite3.Row]:
        return self._all(
            "SELECT d.*, b.name AS buyer_name, b.username AS buyer_username, "
            "f.original_name FROM deliveries d "
            "JOIN buyers b ON b.id=d.buyer_id JOIN files f ON f.id=d.file_id "
            "ORDER BY d.id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )

    def count_deliveries(self) -> int:
        return int(self._one("SELECT COUNT(*) AS n FROM deliveries")["n"])

    # ------------------------------------------------------------ stats
    def stats(self) -> dict[str, int]:
        def n(sql: str) -> int:
            return int(self._one(sql)["n"])
        return {
            "approved_users": n("SELECT COUNT(*) AS n FROM approved_users"),
            "buyers": n("SELECT COUNT(*) AS n FROM buyers WHERE is_active=1"),
            "submissions": n("SELECT COUNT(*) AS n FROM submissions"),
            "pending": n("SELECT COUNT(*) AS n FROM submissions WHERE status='pending'"),
            "delivered": n("SELECT COUNT(*) AS n FROM submissions WHERE status='delivered'"),
            "rejected": n("SELECT COUNT(*) AS n FROM submissions WHERE status='rejected'"),
            "deliveries_ok": n("SELECT COUNT(*) AS n FROM deliveries WHERE status='success'"),
            "deliveries_failed": n("SELECT COUNT(*) AS n FROM deliveries WHERE status='failed'"),
        }


def _split_sql(script: str) -> list[str]:
    """Split a migration script into single statements."""
    return [s.strip() for s in script.split(";") if s.strip()]
