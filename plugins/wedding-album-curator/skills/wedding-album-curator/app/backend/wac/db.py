"""SQLite persistence for a single project.

Each project has its own database file. Connections are short-lived; WAL mode lets
the background analysis worker write while the API reads.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import numpy as np

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS photos (
    id INTEGER PRIMARY KEY,
    rel_path TEXT NOT NULL UNIQUE,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    sha256 TEXT,
    phash TEXT,
    width INTEGER,
    height INTEGER,
    taken_at TEXT,
    taken_ts REAL,
    camera TEXT,
    format TEXT,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | ok | error | missing
    error TEXT,
    duplicate_of INTEGER,                      -- exact duplicate of photo id
    group_id INTEGER,                          -- near-duplicate / burst group
    segment_id INTEGER,                        -- timeline segment
    stage_media INTEGER NOT NULL DEFAULT 0,    -- thumbnails + hashes + metadata
    stage_quality INTEGER NOT NULL DEFAULT 0,
    stage_faces INTEGER NOT NULL DEFAULT 0,
    stage_embed INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_photos_sha ON photos(sha256);
CREATE INDEX IF NOT EXISTS idx_photos_taken ON photos(taken_ts);
CREATE INDEX IF NOT EXISTS idx_photos_group ON photos(group_id);

CREATE TABLE IF NOT EXISTS quality (
    photo_id INTEGER PRIMARY KEY REFERENCES photos(id) ON DELETE CASCADE,
    sharpness REAL, exposure REAL, brightness REAL, highlights_clipped REAL,
    shadows_clipped REAL, contrast REAL, noise REAL, colorfulness REAL,
    composition REAL, technical REAL, details TEXT
);

CREATE TABLE IF NOT EXISTS persons (
    id INTEGER PRIMARY KEY,
    name TEXT,
    role TEXT,                  -- bride | groom | NULL (explicitly set by the user only)
    importance TEXT NOT NULL DEFAULT 'other',
    hidden INTEGER NOT NULL DEFAULT 0,
    rep_face_id INTEGER,
    user_touched INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS faces (
    id INTEGER PRIMARY KEY,
    photo_id INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
    x REAL, y REAL, w REAL, h REAL,           -- normalized to the oriented image
    det_score REAL,
    size_px REAL,
    landmarks TEXT,
    embedding BLOB,
    sharpness REAL,
    frontal REAL,
    eye_blink_left REAL,
    eye_blink_right REAL,
    eyes_closed INTEGER,                       -- 1 closed, 0 open, NULL unknown
    eyes_reliable INTEGER NOT NULL DEFAULT 0,
    landmarker_found INTEGER,
    edge_cut INTEGER NOT NULL DEFAULT 0,
    person_id INTEGER REFERENCES persons(id) ON DELETE SET NULL,
    assignment TEXT NOT NULL DEFAULT 'auto',   -- auto | user | ignored
    excluded_person_ids TEXT NOT NULL DEFAULT '[]',
    match_conf REAL,
    uncertain INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_faces_photo ON faces(photo_id);
CREATE INDEX IF NOT EXISTS idx_faces_person ON faces(person_id);

CREATE TABLE IF NOT EXISTS embeddings (
    photo_id INTEGER PRIMARY KEY REFERENCES photos(id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    vector BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    photo_id INTEGER PRIMARY KEY REFERENCES photos(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    confidence REAL,
    source TEXT NOT NULL,       -- clip | vlm | timeline | user
    scores TEXT
);

CREATE TABLE IF NOT EXISTS user_state (
    photo_id INTEGER PRIMARY KEY REFERENCES photos(id) ON DELETE CASCADE,
    decision TEXT,              -- selected | rejected | NULL
    favorite INTEGER NOT NULL DEFAULT 0,
    rating INTEGER,
    reviewed INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS compare_decisions (
    id INTEGER PRIMARY KEY,
    winner_id INTEGER NOT NULL,
    loser_id INTEGER NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS selection_runs (
    id INTEGER PRIMARY KEY,
    created_at REAL NOT NULL,
    config TEXT NOT NULL,
    summary TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS selection (
    photo_id INTEGER PRIMARY KEY REFERENCES photos(id) ON DELETE CASCADE,
    run_id INTEGER NOT NULL,
    rank INTEGER NOT NULL,
    score REAL NOT NULL,
    bucket TEXT,
    reasons TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_cache (
    content_hash TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    result TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (content_hash, provider, model, prompt_version, config_hash)
);

CREATE TABLE IF NOT EXISTS usage_log (
    id INTEGER PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    photo_id INTEGER,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd REAL,
    cost_basis TEXT,            -- 'api_usage' | 'cli_reported' | 'unknown'
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    state TEXT NOT NULL,        -- queued | running | paused | done | failed | cancelled | interrupted
    stage TEXT,
    done INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL DEFAULT 0,
    message TEXT,
    error TEXT,
    params TEXT,
    started_at REAL,
    finished_at REAL
);
"""


def to_blob(vec: np.ndarray) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


class ProjectDB:
    """Thin wrapper over a project's SQLite file."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._write_lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.executescript(SCHEMA)
            con.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    def _open(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=30, isolation_level=None, check_same_thread=False)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=30000")
        return con

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        con = self._open()
        try:
            yield con
        finally:
            con.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """Serialized write transaction."""
        with self._write_lock:
            con = self._open()
            try:
                con.execute("BEGIN IMMEDIATE")
                yield con
                con.execute("COMMIT")
            except BaseException:
                con.execute("ROLLBACK")
                raise
            finally:
                con.close()

    # ----- settings -----
    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.connect() as con:
            row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set_setting(self, key: str, value: Any) -> None:
        with self.tx() as con:
            con.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value)),
            )

    def touch_user_state(self, con: sqlite3.Connection, photo_id: int, **fields: Any) -> None:
        con.execute(
            "INSERT INTO user_state(photo_id, updated_at) VALUES (?, ?) ON CONFLICT(photo_id) DO NOTHING",
            (photo_id, time.time()),
        )
        if fields:
            cols = ", ".join(f"{k}=?" for k in fields)
            con.execute(
                f"UPDATE user_state SET {cols}, updated_at=? WHERE photo_id=?",
                (*fields.values(), time.time(), photo_id),
            )
