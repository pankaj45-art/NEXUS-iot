"""SQLite persistence layer for NEXUS IoT.

One connection per request/thread (check_same_thread=False is not needed
because ThreadingHTTPServer creates a new connection in each handler call).
WAL mode gives concurrent readers while the server writes.
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Iterator

from . import config
from .security import json_dumps

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'free',           -- free | pro | admin
    disabled INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    last_login_at REAL
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan TEXT NOT NULL DEFAULT 'free',           -- free | pro
    status TEXT NOT NULL DEFAULT 'inactive',    -- active | cancelled | expired | past_due | inactive
    provider TEXT NOT NULL DEFAULT 'manual',    -- manual | stripe | none
    provider_customer_id TEXT DEFAULT '',
    provider_subscription_id TEXT DEFAULT '',
    started_at REAL,
    expires_at REAL,
    cancelled_at REAL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    csrf TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token_hash);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    difficulty TEXT NOT NULL,
    board TEXT NOT NULL,
    comms TEXT NOT NULL,
    summary TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    is_free INTEGER NOT NULL DEFAULT 0,
    free_rank INTEGER,
    status TEXT NOT NULL DEFAULT 'draft',       -- draft | published | archived
    quality_status TEXT NOT NULL DEFAULT 'Draft',
    version INTEGER NOT NULL DEFAULT 1,
    content_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    published_at REAL,
    author TEXT NOT NULL DEFAULT 'NEXUS Engineering'
);
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status, is_free);
CREATE INDEX IF NOT EXISTS idx_projects_category ON projects(category);

CREATE TABLE IF NOT EXISTS usage_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    cost INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    meta_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_usage_user_day ON usage_events(user_id, created_at);

CREATE TABLE IF NOT EXISTS tool_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tool TEXT NOT NULL,
    input_json TEXT NOT NULL,
    output_json TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'offline',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tool_runs_user ON tool_runs(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS workspaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    project_slug TEXT NOT NULL DEFAULT '',
    state_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_workspaces_user ON workspaces(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS workspace_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,             -- milestone | version | decision | test | note | code
    payload_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ws_events ON workspace_events(workspace_id, created_at DESC);

CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    token_prefix TEXT NOT NULL,
    created_at REAL NOT NULL,
    last_seen_at REAL
);
CREATE INDEX IF NOT EXISTS idx_devices_user ON devices(user_id);

CREATE TABLE IF NOT EXISTS telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    ts REAL NOT NULL,
    key TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'real',    -- real | simulated
    meta_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_telemetry_device_ts ON telemetry(device_id, ts DESC);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER,
    action TEXT NOT NULL,
    target TEXT NOT NULL DEFAULT '',
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    ip TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at DESC);

CREATE TABLE IF NOT EXISTS debug_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_key TEXT NOT NULL,
    symptom TEXT NOT NULL,
    fix TEXT NOT NULL,
    outcome TEXT NOT NULL DEFAULT 'unverified',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_debug_attempts ON debug_attempts(user_id, session_key);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value_json TEXT NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (user_id, key)
);

CREATE TABLE IF NOT EXISTS login_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip TEXT NOT NULL,
    email TEXT NOT NULL,
    ts REAL NOT NULL,
    success INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_login_attempts ON login_attempts(ip, ts);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=20, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        from .migrations import migrate
        migrate(conn)
        for key, value in config.DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings(key, value_json, updated_at) VALUES (?,?,?)",
                (key, json_dumps(value), time.time()),
            )
    finally:
        conn.close()


def get_setting(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    row = conn.execute("SELECT value_json FROM settings WHERE key=?", (key,)).fetchone()
    if not row:
        return default if default is not None else config.DEFAULT_SETTINGS.get(key)
    return json.loads(row["value_json"])


def set_setting(conn: sqlite3.Connection, key: str, value: Any) -> Any:
    conn.execute(
        "INSERT INTO settings(key, value_json, updated_at) VALUES (?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
        (key, json_dumps(value), time.time()),
    )
    return value


def audit(conn: sqlite3.Connection, actor_id: int | None, action: str,
          target: str = "", detail: Any = None, ip: str = "") -> None:
    conn.execute(
        "INSERT INTO audit_logs(actor_id, action, target, detail_json, created_at, ip) "
        "VALUES (?,?,?,?,?,?)",
        (actor_id, action, target, json_dumps(detail or {}), time.time(), ip[:64]),
    )


def count_usage(conn: sqlite3.Connection, user_id: int, kind: str, window_seconds: float) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(cost),0) AS n FROM usage_events "
        "WHERE user_id=? AND kind=? AND created_at > ?",
        (user_id, kind, time.time() - window_seconds),
    ).fetchone()
    return int(row["n"])


def count_usage_all(conn: sqlite3.Connection, user_id: int, kind: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(cost),0) AS n FROM usage_events WHERE user_id=? AND kind=?",
        (user_id, kind),
    ).fetchone()
    return int(row["n"])


def record_usage(conn: sqlite3.Connection, user_id: int, kind: str,
                 cost: int = 1, meta: Any = None) -> None:
    conn.execute(
        "INSERT INTO usage_events(user_id, kind, cost, created_at, meta_json) VALUES (?,?,?,?,?)",
        (user_id, kind, cost, time.time(), json_dumps(meta or {})),
    )


USER_SETTING_DEFAULTS = {
    "units": "metric",                 # metric | imperial
    "default_board": "esp32",         # used to prefill Pro tool forms
    "notifications": True,            # in-app alert preference
    "theme": "dark",                  # dark | light (dark is the shipped theme)
    "auto_save_notes": False,
}


def get_user_settings(conn: sqlite3.Connection, user_id: int) -> dict:
    out = dict(USER_SETTING_DEFAULTS)
    for r in conn.execute("SELECT key, value_json FROM user_settings WHERE user_id=?", (user_id,)):
        try:
            out[r["key"]] = json.loads(r["value_json"])
        except ValueError:
            continue
    return out


def set_user_settings(conn: sqlite3.Connection, user_id: int, values: dict) -> dict:
    now = time.time()
    for key, value in values.items():
        if key not in USER_SETTING_DEFAULTS:
            continue
        conn.execute(
            "INSERT INTO user_settings(user_id, key, value_json, updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(user_id, key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
            (user_id, key, json_dumps(value), now))
    return get_user_settings(conn, user_id)
