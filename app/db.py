"""
db.py — SQLite database initialisation and connection management.

Three tables:
  - nodes     : persists node definitions and current status
  - requests  : one row per proxied inference request (logged async)
  - models    : model inventory per node, updated after pulls / health checks

All queries use aiosqlite for fully async I/O, keeping the event loop free
during disk writes (important on the gateway's hot path).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite

from app.config import get_settings

logger = logging.getLogger(__name__)

# ── DDL ───────────────────────────────────────────────────────────────────────

_CREATE_NODES = """
CREATE TABLE IF NOT EXISTS nodes (
    id           TEXT PRIMARY KEY,
    label        TEXT NOT NULL,
    host         TEXT NOT NULL,
    port         INTEGER NOT NULL,
    os           TEXT NOT NULL,
    enabled      INTEGER NOT NULL DEFAULT 1,   -- 0/1 boolean
    tags         TEXT,                          -- JSON array stored as text
    status       TEXT NOT NULL DEFAULT 'unknown',
                                               -- unknown | healthy | degraded | offline
    failure_count INTEGER NOT NULL DEFAULT 0,
    last_seen    TEXT,                          -- ISO-8601 timestamp
    ollama_version TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_REQUESTS = """
CREATE TABLE IF NOT EXISTS requests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id   TEXT NOT NULL,                -- UUID generated per request
    ts           TEXT NOT NULL DEFAULT (datetime('now')),
    node_id      TEXT,
    model        TEXT,
    endpoint     TEXT,                         -- e.g. /v1/chat/completions
    method       TEXT,
    status_code  INTEGER,
    latency_ms   REAL,
    prompt_tokens   INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    streaming    INTEGER NOT NULL DEFAULT 0,   -- 0/1 boolean
    error        TEXT,                         -- error message if status >= 400
    api_key_hint TEXT                          -- first 8 chars of key, for tracing
);
"""

_CREATE_MODELS = """
CREATE TABLE IF NOT EXISTS models (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id      TEXT NOT NULL,
    model_name   TEXT NOT NULL,
    tag          TEXT NOT NULL DEFAULT 'latest',
    size_bytes   INTEGER,
    digest       TEXT,
    pulled_at    TEXT,
    updated_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(node_id, model_name, tag)
);
"""

_CREATE_FINE_TUNE_JOBS = """
CREATE TABLE IF NOT EXISTS fine_tune_jobs (
    id           TEXT PRIMARY KEY,
    name         TEXT,
    base_model   TEXT,
    method       TEXT,
    dataset_source TEXT,
    dataset_format TEXT,
    hyperparameters TEXT,
    output_model_name TEXT,
    target_node_id TEXT,
    status       TEXT,
    progress     REAL DEFAULT 0,
    log          TEXT,
    error        TEXT,
    schedule_at  TEXT,
    started_at   TEXT,
    finished_at  TEXT,
    created_at   TEXT DEFAULT (datetime('now')),
    created_by   TEXT
);
"""

_CREATE_DATASETS = """
CREATE TABLE IF NOT EXISTS datasets (
    id           TEXT PRIMARY KEY,
    name         TEXT,
    path         TEXT,
    size         INTEGER,
    created_at   TEXT DEFAULT (datetime('now'))
);
"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_requests_ts       ON requests(ts);",
    "CREATE INDEX IF NOT EXISTS idx_requests_node_id  ON requests(node_id);",
    "CREATE INDEX IF NOT EXISTS idx_requests_model    ON requests(model);",
    "CREATE INDEX IF NOT EXISTS idx_models_node_id    ON models(node_id);",
    "CREATE INDEX IF NOT EXISTS idx_fine_tune_status  ON fine_tune_jobs(status);",
]

# audit_log DDL is imported from services.audit_log to keep it co-located
# with the event constants.  We call it here to ensure consistent init order.

# ── Public API ────────────────────────────────────────────────────────────────

async def init_db() -> None:
    """Create the database file, directory, and all tables if they don't exist."""
    settings = get_settings()
    db_path = Path(settings.database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL;")   # concurrent reads + writes
        await db.execute("PRAGMA foreign_keys=ON;")
        await db.execute(_CREATE_NODES)
        await db.execute(_CREATE_REQUESTS)
        await db.execute(_CREATE_MODELS)
        await db.execute(_CREATE_FINE_TUNE_JOBS)
        await db.execute(_CREATE_DATASETS)
        for idx in _INDEXES:
            await db.execute(idx)

        # Phase 3: audit_log table (imported here to avoid circular imports)
        from app.services.audit_log import CREATE_AUDIT_TABLE, CREATE_AUDIT_INDEX
        await db.execute(CREATE_AUDIT_TABLE)
        for idx in CREATE_AUDIT_INDEX:
            await db.execute(idx)

        await db.commit()

    logger.info("Database ready: %s", db_path.resolve())


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """
    Async context manager that yields an aiosqlite connection.
    Row factory is set so rows behave like dicts.

    Usage:
        async with get_db() as db:
            await db.execute(...)
    """
    settings = get_settings()
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA foreign_keys=ON;")
        yield db
