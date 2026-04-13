"""
services/key_store.py — Named API key management with metadata.

Each key has:
  - A human-readable name  (e.g. "laptop-dev", "prod-app")
  - An optional rate limit  (requests per minute, 0 = unlimited)
  - enabled flag            (revoke without deleting)
  - created_at / last_used  timestamps
  - request_count           lifetime counter

Keys are stored in the `api_keys` SQLite table and cached in memory at
startup.  The in-memory cache is the hot path; the DB is the source of truth
across restarts.

Bootstrap keys from .env (API_KEYS) are auto-imported on first startup with
the name "bootstrap-N" and no rate limit.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from app.db import get_db

logger = logging.getLogger(__name__)


# ── Domain ────────────────────────────────────────────────────────────────────

@dataclass
class ApiKey:
    key: str                          # the actual secret
    name: str                         # human label
    enabled: bool = True
    rate_limit_rpm: int = 0           # requests/min; 0 = unlimited
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    last_used: Optional[datetime] = None
    request_count: int = 0

    @property
    def key_hint(self) -> str:
        """First 8 chars — safe for logging."""
        return self.key[:8] if len(self.key) >= 8 else self.key

    @property
    def key_hash(self) -> str:
        """SHA-256 of the key — stored in DB instead of the plaintext."""
        return hashlib.sha256(self.key.encode()).hexdigest()

    def to_dict(self, reveal_key: bool = False) -> dict:
        return {
            "name": self.name,
            "key_hint": self.key_hint,
            "key": self.key if reveal_key else None,
            "enabled": self.enabled,
            "rate_limit_rpm": self.rate_limit_rpm,
            "created_at": self.created_at.isoformat(),
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "request_count": self.request_count,
        }


# ── Store ─────────────────────────────────────────────────────────────────────

class KeyStore:
    """
    In-memory key registry backed by SQLite.
    Instantiated once; stored on app.state.key_store.
    """

    def __init__(self) -> None:
        # key → ApiKey (hot lookup path)
        self._keys: dict[str, ApiKey] = {}
        self._lock = asyncio.Lock()

    # ── Startup ───────────────────────────────────────────────────────────────

    async def startup(self, bootstrap_keys: frozenset[str]) -> None:
        """Load keys from DB, then import any bootstrap keys not yet seen."""
        await self._ensure_table()
        await self._load_from_db()
        await self._import_bootstrap_keys(bootstrap_keys)
        logger.info("KeyStore ready — %d key(s) loaded.", len(self._keys))

    async def _ensure_table(self) -> None:
        async with get_db() as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    key_hash      TEXT PRIMARY KEY,
                    key_hint      TEXT NOT NULL,
                    name          TEXT NOT NULL UNIQUE,
                    key_value     TEXT NOT NULL,
                    enabled       INTEGER NOT NULL DEFAULT 1,
                    rate_limit_rpm INTEGER NOT NULL DEFAULT 0,
                    created_at    TEXT NOT NULL,
                    last_used     TEXT,
                    request_count INTEGER NOT NULL DEFAULT 0
                )
            """)
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_api_keys_name ON api_keys(name);"
            )
            await db.commit()

    async def _load_from_db(self) -> None:
        async with get_db() as db:
            async with db.execute("SELECT * FROM api_keys") as cur:
                rows = await cur.fetchall()
        for row in rows:
            key_obj = ApiKey(
                key=row["key_value"],
                name=row["name"],
                enabled=bool(row["enabled"]),
                rate_limit_rpm=row["rate_limit_rpm"],
                created_at=datetime.fromisoformat(row["created_at"]),
                last_used=datetime.fromisoformat(row["last_used"]) if row["last_used"] else None,
                request_count=row["request_count"],
            )
            self._keys[key_obj.key] = key_obj

    async def _import_bootstrap_keys(self, bootstrap_keys: frozenset[str]) -> None:
        """
        Keys from .env (API_KEYS) that aren't in the DB yet are auto-created
        with name 'bootstrap-N' so they appear in the key list immediately.
        """
        existing_keys = set(self._keys.keys())
        new_keys = bootstrap_keys - existing_keys
        for i, raw_key in enumerate(sorted(new_keys)):
            name = f"bootstrap-{i+1}"
            # Make name unique if bootstrap-1 etc. already exist
            counter = i + 1
            while any(k.name == name for k in self._keys.values()):
                counter += 1
                name = f"bootstrap-{counter}"
            key_obj = ApiKey(key=raw_key, name=name)
            await self._persist_key(key_obj)
            self._keys[raw_key] = key_obj
            logger.info("Imported bootstrap key as '%s'", name)

    # ── CRUD ──────────────────────────────────────────────────────────────────

    async def create_key(
        self,
        name: str,
        rate_limit_rpm: int = 0,
        key_value: Optional[str] = None,
    ) -> ApiKey:
        """Generate (or accept) a new API key and persist it."""
        async with self._lock:
            if any(k.name == name for k in self._keys.values()):
                raise ValueError(f"A key with name '{name}' already exists.")
            raw = key_value or secrets.token_hex(32)
            if raw in self._keys:
                raise ValueError("Key value collision — try again.")
            key_obj = ApiKey(key=raw, name=name, rate_limit_rpm=rate_limit_rpm)
            await self._persist_key(key_obj)
            self._keys[raw] = key_obj
            logger.info("Created API key '%s' (hint: %s…)", name, key_obj.key_hint)
            return key_obj

    async def revoke_key(self, name: str) -> bool:
        """Disable a key by name. Returns True if found."""
        async with self._lock:
            key_obj = self._find_by_name(name)
            if not key_obj:
                return False
            key_obj.enabled = False
            await self._update_field(key_obj.key_hash, "enabled", 0)
            logger.info("Revoked API key '%s'", name)
            return True

    async def enable_key(self, name: str) -> bool:
        """Re-enable a previously revoked key."""
        async with self._lock:
            key_obj = self._find_by_name(name)
            if not key_obj:
                return False
            key_obj.enabled = True
            await self._update_field(key_obj.key_hash, "enabled", 1)
            logger.info("Enabled API key '%s'", name)
            return True

    async def delete_key(self, name: str) -> bool:
        """Permanently delete a key. Returns True if found."""
        async with self._lock:
            key_obj = self._find_by_name(name)
            if not key_obj:
                return False
            del self._keys[key_obj.key]
            async with get_db() as db:
                await db.execute(
                    "DELETE FROM api_keys WHERE key_hash = ?", (key_obj.key_hash,)
                )
                await db.commit()
            logger.info("Deleted API key '%s'", name)
            return True

    async def update_rate_limit(self, name: str, rpm: int) -> bool:
        async with self._lock:
            key_obj = self._find_by_name(name)
            if not key_obj:
                return False
            key_obj.rate_limit_rpm = rpm
            await self._update_field(key_obj.key_hash, "rate_limit_rpm", rpm)
            return True

    # ── Validation (hot path — no lock needed, dict lookup is atomic) ─────────

    def validate(self, raw_key: str) -> Optional[ApiKey]:
        """
        Returns the ApiKey if the key is known and enabled, else None.
        Called on every authenticated request — must be fast.
        """
        key_obj = self._keys.get(raw_key)
        if key_obj and key_obj.enabled:
            return key_obj
        return None

    async def record_usage(self, raw_key: str) -> None:
        """
        Bump last_used and request_count.  Fire-and-forget from the auth layer.
        """
        key_obj = self._keys.get(raw_key)
        if not key_obj:
            return
        now = datetime.now(tz=timezone.utc)
        key_obj.last_used = now
        key_obj.request_count += 1
        # Async DB write — don't await at call site
        asyncio.create_task(self._flush_usage(key_obj.key_hash, now, key_obj.request_count))

    async def _flush_usage(self, key_hash: str, last_used: datetime, count: int) -> None:
        try:
            async with get_db() as db:
                await db.execute(
                    "UPDATE api_keys SET last_used = ?, request_count = ? WHERE key_hash = ?",
                    (last_used.isoformat(), count, key_hash),
                )
                await db.commit()
        except Exception as exc:
            logger.debug("Failed to flush key usage: %s", exc)

    # ── Listing ───────────────────────────────────────────────────────────────

    def list_keys(self) -> list[ApiKey]:
        return sorted(self._keys.values(), key=lambda k: k.created_at)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _find_by_name(self, name: str) -> Optional[ApiKey]:
        return next((k for k in self._keys.values() if k.name == name), None)

    async def _persist_key(self, key_obj: ApiKey) -> None:
        async with get_db() as db:
            await db.execute(
                """
                INSERT INTO api_keys
                    (key_hash, key_hint, name, key_value, enabled, rate_limit_rpm, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(key_hash) DO NOTHING
                """,
                (
                    key_obj.key_hash,
                    key_obj.key_hint,
                    key_obj.name,
                    key_obj.key,
                    int(key_obj.enabled),
                    key_obj.rate_limit_rpm,
                    key_obj.created_at.isoformat(),
                ),
            )
            await db.commit()

    async def _update_field(self, key_hash: str, field: str, value) -> None:
        async with get_db() as db:
            await db.execute(
                f"UPDATE api_keys SET {field} = ? WHERE key_hash = ?",
                (value, key_hash),
            )
            await db.commit()
