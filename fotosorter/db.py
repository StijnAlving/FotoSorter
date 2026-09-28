"""SQLite-backed state for resumable sorting sessions.

Every source file discovered under RAW/ gets one row in `files`, moving
through a small status machine as the pipeline processes it:

    new -> (low_quality_done | pending_group | error)
    pending_group -> (needs_location | done via group of 1)
    pending_group -> pending_review (group of 2+, joins a `groups` row)
    pending_review -> needs_location | done  (once the user saves the group)
    needs_location -> done (once a location rule is added and resolved)

Because every transition is persisted immediately, quitting the app at any
point and relaunching just resumes from whatever rows aren't `done` yet.
"""
import sqlite3
from contextlib import closing
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    content_hash TEXT,
    date_taken TEXT,
    date_is_estimated INTEGER DEFAULT 0,
    width INTEGER,
    height INTEGER,
    camera_make TEXT,
    camera_model TEXT,
    gps_lat REAL,
    gps_lon REAL,
    phash TEXT,
    sharpness REAL,
    quality_flag TEXT,
    quality_reasons TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    group_id INTEGER,
    year INTEGER,
    country TEXT,
    kept INTEGER,
    error TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (group_id) REFERENCES groups(id)
);
CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL DEFAULT 'pending_review',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
CREATE INDEX IF NOT EXISTS idx_files_group ON files(group_id);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    with closing(conn.cursor()) as cur:
        cur.executescript(SCHEMA)
    conn.commit()
    return conn


def known_paths(conn: sqlite3.Connection) -> set[str]:
    return {row["path"] for row in conn.execute("SELECT path FROM files")}


def insert_new_file(conn: sqlite3.Connection, path: str, content_hash: str) -> int:
    cur = conn.execute(
        "INSERT INTO files (path, content_hash, status) VALUES (?, ?, 'new')",
        (path, content_hash),
    )
    conn.commit()
    return cur.lastrowid


def get_by_status(conn: sqlite3.Connection, status: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM files WHERE status = ? ORDER BY date_taken", (status,)
    ).fetchall()


def update_file(conn: sqlite3.Connection, file_id: int, **fields) -> None:
    cols = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE files SET {cols} WHERE id = ?", (*fields.values(), file_id))
    conn.commit()


def create_group(conn: sqlite3.Connection, file_ids: list[int]) -> int:
    cur = conn.execute("INSERT INTO groups (status) VALUES ('pending_review')")
    group_id = cur.lastrowid
    conn.executemany(
        "UPDATE files SET group_id = ?, status = 'pending_review' WHERE id = ?",
        [(group_id, fid) for fid in file_ids],
    )
    conn.commit()
    return group_id


def get_pending_review_groups(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute(
        "SELECT id FROM groups WHERE status = 'pending_review' ORDER BY id"
    ).fetchall()
    return [row["id"] for row in rows]


def get_group_members(conn: sqlite3.Connection, group_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM files WHERE group_id = ? ORDER BY date_taken", (group_id,)
    ).fetchall()


def mark_group_resolved(conn: sqlite3.Connection, group_id: int) -> None:
    conn.execute("UPDATE groups SET status = 'resolved' WHERE id = ?", (group_id,))
    conn.commit()


def get_needs_location(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM files WHERE status = 'needs_location' ORDER BY date_taken"
    ).fetchall()


def counts_by_status(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        "SELECT status, COUNT(*) as n FROM files GROUP BY status"
    ).fetchall()
    return {row["status"]: row["n"] for row in rows}
