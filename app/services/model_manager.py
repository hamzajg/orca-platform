"""
services/model_manager.py — Model manifest sync and pull orchestration.

Responsibilities:
  - Load models.yaml manifest at startup
  - Compare manifest against each node's actual model list
  - Issue pull requests to nodes for missing models (respects priority order)
  - Track every pull as a PullJob with live status + progress
  - Persist final model inventory to the `models` SQLite table
  - Expose job state for the SSE progress stream endpoint

Pull flow per node:
  POST /api/pull  →  Ollama streams NDJSON progress lines
  Each line: {"status": "...", "digest": "...", "total": N, "completed": N}
  Final line: {"status": "success"}

Job lifecycle:  queued → pulling → done | error
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import AsyncGenerator, Optional

import httpx

from app.db import get_db
from app.services.proxy import get_http_client

logger = logging.getLogger(__name__)


# ── Domain ────────────────────────────────────────────────────────────────────

class JobStatus(str, Enum):
    QUEUED  = "queued"
    PULLING = "pulling"
    DONE    = "done"
    ERROR   = "error"


@dataclass
class PullJob:
    job_id:    str
    node_id:   str
    node_url:  str
    model:     str
    status:    JobStatus = JobStatus.QUEUED
    progress_pct: float  = 0.0          # 0–100
    bytes_total:  int    = 0
    bytes_done:   int    = 0
    current_layer: str   = ""
    error:     Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    log: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "job_id":        self.job_id,
            "node_id":       self.node_id,
            "model":         self.model,
            "status":        self.status.value,
            "progress_pct":  round(self.progress_pct, 1),
            "bytes_total":   self.bytes_total,
            "bytes_done":    self.bytes_done,
            "current_layer": self.current_layer,
            "error":         self.error,
            "started_at":    self.started_at.isoformat() if self.started_at else None,
            "finished_at":   self.finished_at.isoformat() if self.finished_at else None,
        }


# ── Manager ───────────────────────────────────────────────────────────────────

class ModelManager:
    """
    One instance lives on app.state.model_manager.
    All public methods are async-safe.
    """

    def __init__(self) -> None:
        # job_id → PullJob  (kept in memory; survives as long as the process runs)
        self._jobs: dict[str, PullJob] = {}
        self._lock = asyncio.Lock()
        # SSE subscribers: job_id → list of asyncio.Queue
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    # ── Startup ───────────────────────────────────────────────────────────────

    async def startup(self, registry) -> None:
        """Persist model inventory from registry's first health check."""
        self._registry = registry
        await self._sync_models_table()
        logger.info("ModelManager ready.")

    async def _sync_models_table(self) -> None:
        """Write each node's current model list into the `models` table."""
        nodes = self._registry.get_all_nodes()
        now = datetime.now(tz=timezone.utc).isoformat()
        async with get_db() as db:
            for node in nodes:
                for model_name in node.available_models:
                    tag = "latest"
                    if ":" in model_name:
                        model_name, tag = model_name.rsplit(":", 1)
                    await db.execute(
                        """
                        INSERT INTO models (node_id, model_name, tag, updated_at)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(node_id, model_name, tag)
                        DO UPDATE SET updated_at = excluded.updated_at
                        """,
                        (node.id, model_name, tag, now),
                    )
            await db.commit()

    # ── Manifest sync ─────────────────────────────────────────────────────────

    async def sync_manifest(self) -> list[PullJob]:
        """
        Compare models.yaml manifest against each node's actual model list.
        Enqueue pull jobs for every (model, node) pair that's missing.
        Returns the list of newly created jobs (may be empty if everything is
        already present).
        """
        from app.config import get_settings
        settings = get_settings()
        manifest = settings.load_models_config()
        all_nodes = self._registry.get_all_nodes()
        node_map = {n.id: n for n in all_nodes}

        new_jobs: list[PullJob] = []

        # Sort by priority ascending so lower numbers pull first
        for entry in sorted(manifest, key=lambda e: e.get("priority", 99)):
            model_name: str = entry["name"]
            target_nodes_cfg = entry.get("target_nodes", "all")

            # Resolve target node list
            if target_nodes_cfg == "all" or target_nodes_cfg == ["all"]:
                targets = list(node_map.values())
            else:
                targets = [
                    node_map[nid]
                    for nid in target_nodes_cfg
                    if nid in node_map
                ]

            for node in targets:
                if not node.enabled:
                    continue
                # Normalise: Ollama returns names like "llama3.2:latest"
                has_model = any(
                    m == model_name or m.startswith(model_name + ":")
                    for m in node.available_models
                )
                if has_model:
                    logger.debug(
                        "Manifest sync: %s already on %s — skip", model_name, node.id
                    )
                    continue

                job = await self._enqueue_pull(node.id, node.base_url, model_name)
                new_jobs.append(job)
                logger.info(
                    "Manifest sync: queued pull of '%s' on %s (job %s)",
                    model_name, node.id, job.job_id,
                )

        return new_jobs

    # ── On-demand pull ────────────────────────────────────────────────────────

    async def pull_model(
        self,
        model: str,
        node_ids: Optional[list[str]] = None,
    ) -> list[PullJob]:
        """
        Enqueue pull jobs for `model` on the specified nodes.
        If node_ids is None, pull on ALL enabled nodes.
        Returns the created jobs immediately (pull runs in background).
        """
        all_nodes = self._registry.get_all_nodes()
        if node_ids:
            targets = [n for n in all_nodes if n.id in node_ids and n.enabled]
        else:
            targets = [n for n in all_nodes if n.enabled]

        jobs: list[PullJob] = []
        for node in targets:
            job = await self._enqueue_pull(node.id, node.base_url, model)
            jobs.append(job)
        return jobs

    # ── Job management ────────────────────────────────────────────────────────

    def get_job(self, job_id: str) -> Optional[PullJob]:
        return self._jobs.get(job_id)

    def list_jobs(
        self,
        node_id: Optional[str] = None,
        status: Optional[JobStatus] = None,
    ) -> list[PullJob]:
        jobs = list(self._jobs.values())
        if node_id:
            jobs = [j for j in jobs if j.node_id == node_id]
        if status:
            jobs = [j for j in jobs if j.status == status]
        return sorted(jobs, key=lambda j: j.started_at or datetime.min, reverse=True)

    async def delete_job(self, job_id: str) -> bool:
        async with self._lock:
            if job_id not in self._jobs:
                return False
            job = self._jobs[job_id]
            if job.status == JobStatus.PULLING:
                return False  # can't delete active job
            del self._jobs[job_id]
            return True

    # ── SSE progress stream ───────────────────────────────────────────────────

    async def subscribe(self, job_id: str) -> AsyncGenerator[str, None]:
        """
        Yield SSE-formatted strings for a pull job.
        Yields current state immediately, then streams updates until done/error.
        """
        job = self._jobs.get(job_id)
        if not job:
            yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
            return

        # If already finished, just return final state
        if job.status in (JobStatus.DONE, JobStatus.ERROR):
            yield f"data: {json.dumps(job.to_dict())}\n\n"
            yield "data: [DONE]\n\n"
            return

        # Subscribe to live updates
        q: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._subscribers.setdefault(job_id, []).append(q)

        try:
            # Send current snapshot immediately
            yield f"data: {json.dumps(job.to_dict())}\n\n"

            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    # Heartbeat to keep connection alive
                    yield ": heartbeat\n\n"
                    continue

                yield f"data: {json.dumps(event)}\n\n"
                if event.get("status") in ("done", "error"):
                    break
        finally:
            async with self._lock:
                subs = self._subscribers.get(job_id, [])
                if q in subs:
                    subs.remove(q)

        yield "data: [DONE]\n\n"

    # ── Internal: pull execution ──────────────────────────────────────────────

    async def _enqueue_pull(
        self, node_id: str, node_url: str, model: str
    ) -> PullJob:
        job = PullJob(
            job_id=str(uuid.uuid4())[:12],
            node_id=node_id,
            node_url=node_url,
            model=model,
        )
        async with self._lock:
            self._jobs[job.job_id] = job

        # Fire and forget — pull runs in background
        asyncio.create_task(
            self._run_pull(job), name=f"pull-{job.job_id}"
        )
        return job

    async def _run_pull(self, job: PullJob) -> None:
        job.status = JobStatus.PULLING
        job.started_at = datetime.now(tz=timezone.utc)
        await self._notify(job)

        url = f"{job.node_url}/api/pull"
        payload = {"name": job.model, "stream": True}

        try:
            async with get_http_client().stream(
                "POST", url, json=payload,
                timeout=httpx.Timeout(3600.0, connect=10.0)   # pulls can take a long time
            ) as resp:
                resp.raise_for_status()
                async for raw_line in resp.aiter_lines():
                    if not raw_line.strip():
                        continue
                    try:
                        data = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue
                    await self._handle_pull_chunk(job, data)

            # Verify success
            if job.status != JobStatus.ERROR:
                job.status = JobStatus.DONE
                job.progress_pct = 100.0
                job.finished_at = datetime.now(tz=timezone.utc)
                await self._persist_model(job)
                # Refresh node's model list after successful pull
                await self._registry.trigger_immediate_check()
                logger.info("Pull complete: %s on %s", job.model, job.node_id)

        except Exception as exc:
            job.status = JobStatus.ERROR
            job.error = str(exc)[:500]
            job.finished_at = datetime.now(tz=timezone.utc)
            logger.error(
                "Pull failed: %s on %s — %s", job.model, job.node_id, exc
            )

        await self._notify(job)

    async def _handle_pull_chunk(self, job: PullJob, data: dict) -> None:
        """Parse one Ollama pull progress line and update job state."""
        status_str = data.get("status", "")
        job.current_layer = status_str

        total     = data.get("total", 0) or 0
        completed = data.get("completed", 0) or 0

        if total > 0:
            # Update running totals (Ollama reports per-layer)
            job.bytes_total = max(job.bytes_total, total)
            job.bytes_done  = completed
            job.progress_pct = min((completed / total) * 100, 99.9)
        elif status_str == "success":
            job.status = JobStatus.DONE
            job.progress_pct = 100.0

        if "error" in data:
            job.status = JobStatus.ERROR
            job.error = data["error"]

        job.log.append(status_str[:120] if status_str else "")
        await self._notify(job)

    async def _notify(self, job: PullJob) -> None:
        """Push job snapshot to all SSE subscribers."""
        snapshot = job.to_dict()
        async with self._lock:
            for q in self._subscribers.get(job.job_id, []):
                try:
                    q.put_nowait(snapshot)
                except asyncio.QueueFull:
                    pass

    async def _persist_model(self, job: PullJob) -> None:
        """Write a completed pull to the models table."""
        model_name = job.model
        tag = "latest"
        if ":" in model_name:
            model_name, tag = model_name.rsplit(":", 1)
        now = datetime.now(tz=timezone.utc).isoformat()
        try:
            async with get_db() as db:
                await db.execute(
                    """
                    INSERT INTO models (node_id, model_name, tag, pulled_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(node_id, model_name, tag)
                    DO UPDATE SET pulled_at = excluded.pulled_at,
                                  updated_at = excluded.updated_at
                    """,
                    (job.node_id, model_name, tag, now, now),
                )
                await db.commit()
        except Exception as exc:
            logger.warning("Failed to persist model record: %s", exc)
