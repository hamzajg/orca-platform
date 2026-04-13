"""
node_registry.py — Node pool, health-check background task, and round-robin router.

Responsibilities:
  - Load node definitions from nodes.yaml at startup
  - Persist node list to SQLite (upsert on each start)
  - Run a background asyncio task that pings each node's Ollama API every
    HEALTH_CHECK_INTERVAL seconds
  - Track consecutive failures; mark nodes degraded/offline after threshold
  - Expose get_next_node() which returns the next healthy node in round-robin
    order (skipping degraded/offline nodes)
  - Expose get_all_nodes() for the /api/nodes status endpoint
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import httpx

from app.config import get_settings
from app.db import get_db

logger = logging.getLogger(__name__)


# ── Domain types ──────────────────────────────────────────────────────────────

class NodeStatus(str, Enum):
    UNKNOWN   = "unknown"
    HEALTHY   = "healthy"
    DEGRADED  = "degraded"
    OFFLINE   = "offline"


@dataclass
class Node:
    id: str
    label: str
    host: str
    port: int
    os: str
    enabled: bool = True
    tags: list[str] = field(default_factory=list)

    # Runtime state (not persisted between restarts, refreshed by health loop)
    status: NodeStatus = NodeStatus.UNKNOWN
    failure_count: int = 0
    last_seen: Optional[datetime] = None
    ollama_version: Optional[str] = None
    available_models: list[str] = field(default_factory=list)

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def is_routable(self) -> bool:
        return self.enabled and self.status == NodeStatus.HEALTHY

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "host": self.host,
            "port": self.port,
            "os": self.os,
            "enabled": self.enabled,
            "tags": self.tags,
            "status": self.status.value,
            "failure_count": self.failure_count,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "ollama_version": self.ollama_version,
            "available_models": self.available_models,
            "base_url": self.base_url,
        }


# ── Registry ──────────────────────────────────────────────────────────────────

class NodeRegistry:
    """
    Singleton-style registry that owns all node state.
    Instantiated once in main.py and stored on app.state.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}
        self._rr_index: int = 0          # round-robin cursor
        self._lock = asyncio.Lock()      # guards _rr_index and status mutations
        self._health_task: Optional[asyncio.Task] = None

    # ── Startup / shutdown ────────────────────────────────────────────────────

    async def startup(self) -> None:
        """Load nodes from YAML, persist to DB, start health-check loop."""
        await self._load_nodes()
        await self._persist_nodes()
        self._health_task = asyncio.create_task(
            self._health_loop(), name="health-check-loop"
        )
        logger.info(
            "NodeRegistry started with %d node(s): %s",
            len(self._nodes),
            list(self._nodes.keys()),
        )

    async def shutdown(self) -> None:
        """Cancel the background health-check task gracefully."""
        if self._health_task and not self._health_task.done():
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
        logger.info("NodeRegistry shut down.")

    # ── Node loading ──────────────────────────────────────────────────────────

    async def _load_nodes(self) -> None:
        settings = get_settings()
        raw_nodes = settings.load_nodes_config()
        for raw in raw_nodes:
            node = Node(
                id=raw["id"],
                label=raw.get("label", raw["id"]),
                host=raw["host"],
                port=raw.get("port", 11434),
                os=raw.get("os", "linux"),
                enabled=raw.get("enabled", True),
                tags=raw.get("tags", []),
            )
            self._nodes[node.id] = node

    async def _persist_nodes(self) -> None:
        """Upsert all nodes into the SQLite nodes table."""
        async with get_db() as db:
            for node in self._nodes.values():
                await db.execute(
                    """
                    INSERT INTO nodes
                        (id, label, host, port, os, enabled, tags, status)
                    VALUES
                        (:id, :label, :host, :port, :os, :enabled, :tags, :status)
                    ON CONFLICT(id) DO UPDATE SET
                        label   = excluded.label,
                        host    = excluded.host,
                        port    = excluded.port,
                        os      = excluded.os,
                        enabled = excluded.enabled,
                        tags    = excluded.tags
                    """,
                    {
                        "id": node.id,
                        "label": node.label,
                        "host": node.host,
                        "port": node.port,
                        "os": node.os,
                        "enabled": int(node.enabled),
                        "tags": json.dumps(node.tags),
                        "status": node.status.value,
                    },
                )
            await db.commit()

    # ── Health loop ───────────────────────────────────────────────────────────

    async def _health_loop(self) -> None:
        settings = get_settings()
        while True:
            await asyncio.sleep(settings.health_check_interval)
            await self._check_all_nodes()

    async def _check_all_nodes(self) -> None:
        tasks = [self._check_node(node) for node in self._nodes.values()]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_node(self, node: Node) -> None:
        settings = get_settings()
        try:
            async with httpx.AsyncClient(timeout=settings.health_check_timeout) as client:
                # GET /api/tags returns the list of local models — ideal health probe
                resp = await client.get(f"{node.base_url}/api/tags")
                resp.raise_for_status()
                data = resp.json()

            # ── Success ───────────────────────────────────────────────────────
            async with self._lock:
                node.failure_count = 0
                node.status = NodeStatus.HEALTHY
                node.last_seen = datetime.now(tz=timezone.utc)
                # Extract model names from Ollama's response
                node.available_models = [
                    m["name"] for m in data.get("models", [])
                ]
                # Grab version from a separate lightweight endpoint (best-effort)
                try:
                    vresp = await client.get(f"{node.base_url}/api/version")
                    node.ollama_version = vresp.json().get("version")
                except Exception:
                    pass

            await self._update_node_db(node)
            logger.debug("Node %s healthy — %d model(s)", node.id, len(node.available_models))

        except Exception as exc:
            async with self._lock:
                node.failure_count += 1
                if node.failure_count >= settings.health_check_failures:
                    prev = node.status
                    node.status = NodeStatus.DEGRADED if node.failure_count < 5 else NodeStatus.OFFLINE
                    if prev != node.status:
                        logger.warning(
                            "Node %s → %s (failures: %d) — %s",
                            node.id, node.status.value, node.failure_count, exc,
                        )
            await self._update_node_db(node)

    async def _update_node_db(self, node: Node) -> None:
        async with get_db() as db:
            await db.execute(
                """
                UPDATE nodes SET
                    status         = :status,
                    failure_count  = :failure_count,
                    last_seen      = :last_seen,
                    ollama_version = :ollama_version
                WHERE id = :id
                """,
                {
                    "id": node.id,
                    "status": node.status.value,
                    "failure_count": node.failure_count,
                    "last_seen": node.last_seen.isoformat() if node.last_seen else None,
                    "ollama_version": node.ollama_version,
                },
            )
            await db.commit()

    # ── Routing ───────────────────────────────────────────────────────────────

    async def get_next_node(self, model: Optional[str] = None) -> Optional[Node]:
        """
        Return the next healthy node using round-robin.
        If `model` is specified, prefer nodes that already have that model loaded.
        Falls back to any healthy node if no model-match is found.
        """
        async with self._lock:
            routable = [n for n in self._nodes.values() if n.is_routable]
            if not routable:
                return None

            # Prefer nodes that already have the requested model
            if model:
                preferred = [n for n in routable if model in n.available_models]
                if preferred:
                    routable = preferred

            # Advance round-robin cursor (wrap within current routable set)
            self._rr_index = self._rr_index % len(routable)
            node = routable[self._rr_index]
            self._rr_index = (self._rr_index + 1) % len(routable)
            return node

    # ── Accessors ─────────────────────────────────────────────────────────────

    def get_all_nodes(self) -> list[Node]:
        return list(self._nodes.values())

    def get_node(self, node_id: str) -> Optional[Node]:
        return self._nodes.get(node_id)

    def get_healthy_count(self) -> int:
        return sum(1 for n in self._nodes.values() if n.status == NodeStatus.HEALTHY)

    def get_all_models(self) -> dict[str, list[str]]:
        """Return {model_name: [node_ids]} for all models across healthy nodes."""
        index: dict[str, list[str]] = {}
        for node in self._nodes.values():
            if node.is_routable:
                for model in node.available_models:
                    index.setdefault(model, []).append(node.id)
        return index

    async def trigger_immediate_check(self) -> None:
        """Force a health check right now (used after a pull completes)."""
        await self._check_all_nodes()
