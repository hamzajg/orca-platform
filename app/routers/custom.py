"""
routers/custom.py — Custom platform API endpoints.

Phase 1 endpoints:
  GET  /api/health          — Gateway liveness probe
  GET  /api/nodes           — All nodes with status, models, metadata
  GET  /api/nodes/{node_id} — Single node detail
  GET  /api/models          — Aggregated model index across healthy nodes
  POST /api/nodes/check     — Force an immediate health check on all nodes

Phase 4: /api/models/* in routers/models.py
Phase 5: /api/metrics/* in routers/metrics.py
"""

from __future__ import annotations

import platform
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.middleware.auth import require_api_key

router = APIRouter(prefix="/api", tags=["platform"])

_START_TIME = time.monotonic()


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/health", summary="Gateway liveness probe")
async def health(request: Request):
    """
    Public endpoint — no auth required.
    Returns gateway uptime, Python version, node summary, and a
    1-hour request/error snapshot from the metrics layer.
    """
    from app.services.metrics import get_overview
    registry = request.app.state.registry
    nodes = registry.get_all_nodes()

    status_counts: dict[str, int] = {}
    for node in nodes:
        status_counts[node.status.value] = status_counts.get(node.status.value, 0) + 1

    # Best-effort metrics snapshot — never fails the health check
    metrics_snapshot: dict = {}
    try:
        ov = await get_overview("1h")
        metrics_snapshot = {
            "requests_1h":  ov["total_requests"],
            "errors_1h":    ov["error_count"],
            "avg_latency_ms": ov["latency_ms"]["avg"],
            "p95_latency_ms": ov["latency_ms"]["p95"],
            "tokens_1h":    ov["tokens"]["total"],
        }
    except Exception:
        pass

    return {
        "status": "ok",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "uptime_seconds": round(time.monotonic() - _START_TIME, 1),
        "gateway": {
            "python_version": platform.python_version(),
            "platform": platform.system(),
            "version": "0.5.0",
        },
        "nodes": {
            "total": len(nodes),
            **status_counts,
        },
        "metrics": metrics_snapshot,
    }


# ── Nodes ─────────────────────────────────────────────────────────────────────

@router.get(
    "/nodes",
    summary="List all nodes with status",
    dependencies=[Depends(require_api_key)],
)
async def list_nodes(request: Request):
    """Return all registered nodes and their current health state."""
    registry = request.app.state.registry
    nodes = registry.get_all_nodes()
    return {
        "nodes": [n.to_dict() for n in nodes],
        "total": len(nodes),
        "healthy": registry.get_healthy_count(),
    }


@router.get(
    "/nodes/{node_id}",
    summary="Get a single node by ID",
    dependencies=[Depends(require_api_key)],
)
async def get_node(node_id: str, request: Request):
    """Return detail for a single node."""
    registry = request.app.state.registry
    node = registry.get_node(node_id)
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node '{node_id}' not found.",
        )
    return node.to_dict()


@router.post(
    "/nodes/check",
    summary="Force an immediate health check on all nodes",
    dependencies=[Depends(require_api_key)],
)
async def force_health_check(request: Request):
    """Trigger health checks right now without waiting for the next interval."""
    registry = request.app.state.registry
    await registry.trigger_immediate_check()
    nodes = registry.get_all_nodes()
    return {
        "message": "Health check complete.",
        "nodes": [{"id": n.id, "status": n.status.value} for n in nodes],
    }

