"""
services/audit_log.py — Security-focused audit event logger.

Writes structured events to the `audit_log` SQLite table.
Events are always written synchronously on security-relevant actions
(auth failures, key creation/deletion, rate limit hits) so they're
never lost even if the process crashes immediately after.

For high-frequency per-request logging use services/logger.py instead.

Event types:
  auth_ok          — successful authentication
  auth_fail        — unknown or missing key
  auth_revoked     — key found but disabled
  rate_limit_hit   — request rejected by rate limiter
  key_created      — new API key created
  key_revoked      — key disabled
  key_deleted      — key permanently removed
  key_enabled      — disabled key re-enabled
  rate_limit_changed — RPM limit updated
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from app.db import get_db

logger = logging.getLogger(__name__)

# ── DDL (called from db.init_db) ──────────────────────────────────────────────

CREATE_AUDIT_TABLE = """
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL DEFAULT (datetime('now')),
    event_type  TEXT NOT NULL,
    key_hint    TEXT,
    key_name    TEXT,
    client_ip   TEXT,
    endpoint    TEXT,
    detail      TEXT
);
"""

CREATE_AUDIT_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_audit_ts         ON audit_log(ts);",
    "CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_log(event_type);",
    "CREATE INDEX IF NOT EXISTS idx_audit_key_hint   ON audit_log(key_hint);",
)


# ── Public API ────────────────────────────────────────────────────────────────

async def audit(
    event_type: str,
    *,
    key_hint: Optional[str] = None,
    key_name: Optional[str] = None,
    client_ip: Optional[str] = None,
    endpoint: Optional[str] = None,
    detail: Optional[str] = None,
) -> None:
    """
    Write one audit event.  Fire-and-forget via asyncio.create_task.
    Uses a separate task so it never blocks the request path.
    """
    asyncio.create_task(
        _write(
            event_type=event_type,
            key_hint=key_hint,
            key_name=key_name,
            client_ip=client_ip,
            endpoint=endpoint,
            detail=detail,
        )
    )


async def _write(
    event_type: str,
    key_hint: Optional[str],
    key_name: Optional[str],
    client_ip: Optional[str],
    endpoint: Optional[str],
    detail: Optional[str],
) -> None:
    try:
        async with get_db() as db:
            await db.execute(
                """
                INSERT INTO audit_log
                    (ts, event_type, key_hint, key_name, client_ip, endpoint, detail)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(tz=timezone.utc).isoformat(),
                    event_type,
                    key_hint,
                    key_name,
                    client_ip,
                    endpoint,
                    detail,
                ),
            )
            await db.commit()
    except Exception as exc:
        logger.warning("Failed to write audit event '%s': %s", event_type, exc)


async def get_recent_events(
    limit: int = 100,
    event_type: Optional[str] = None,
    key_hint: Optional[str] = None,
) -> list[dict]:
    """Fetch recent audit events (for the /api/auth/audit endpoint)."""
    clauses = []
    params: list = []
    if event_type:
        clauses.append("event_type = ?")
        params.append(event_type)
    if key_hint:
        clauses.append("key_hint = ?")
        params.append(key_hint)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)

    async with get_db() as db:
        async with db.execute(
            f"SELECT * FROM audit_log {where} ORDER BY ts DESC LIMIT ?",
            params,
        ) as cur:
            rows = await cur.fetchall()
    return [dict(row) for row in rows]
