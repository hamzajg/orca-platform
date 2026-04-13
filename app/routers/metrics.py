"""
routers/metrics.py — Metrics and observability endpoints (Phase 5).

All queries run against the `requests` SQLite table that has been populated
by services/logger.py since Phase 2.

Endpoints:
  GET /api/metrics                    — full metrics bundle (all views in one call)
  GET /api/metrics/overview           — top-level KPIs: counts, latency, tokens
  GET /api/metrics/by-model           — breakdown per model
  GET /api/metrics/by-node            — breakdown per worker node
  GET /api/metrics/by-key             — breakdown per API key
  GET /api/metrics/by-endpoint        — breakdown per endpoint path
  GET /api/metrics/by-hour            — hourly time-series
  GET /api/metrics/requests           — paginated raw request log
  DELETE /api/metrics/requests        — purge old request rows

All endpoints accept a `?window=` query parameter:
  1h | 6h | 24h (default) | 7d | 30d | all
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.middleware.auth import require_api_key
from app.services import metrics as svc
from app.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/metrics", tags=["metrics"])

_VALID_WINDOWS = {"1h", "6h", "24h", "7d", "30d", "all"}


def _validate_window(window: str) -> str:
    if window not in _VALID_WINDOWS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid window '{window}'. Valid: {sorted(_VALID_WINDOWS)}",
        )
    return window


# ── Full bundle ───────────────────────────────────────────────────────────────

@router.get(
    "",
    summary="Full metrics bundle — all views in one response",
    dependencies=[Depends(require_api_key)],
)
async def get_all_metrics(
    window: str = Query(default="24h"),
    request: Request = None,
):
    """
    Returns every metrics view combined into a single JSON response.
    Ideal for dashboards that need everything in one round-trip.
    """
    w = _validate_window(window)
    overview, by_model, by_node, by_key, by_endpoint, by_hour = (
        await svc.get_overview(w),
        await svc.get_by_model(w),
        await svc.get_by_node(w),
        await svc.get_by_key(w),
        await svc.get_by_endpoint(w),
        await svc.get_by_hour(w),
    )
    return {
        "overview":    overview,
        "by_model":    by_model,
        "by_node":     by_node,
        "by_key":      by_key,
        "by_endpoint": by_endpoint,
        "by_hour":     by_hour,
    }


# ── Individual views ──────────────────────────────────────────────────────────

@router.get(
    "/overview",
    summary="Top-level KPIs: request counts, latency percentiles, token throughput",
    dependencies=[Depends(require_api_key)],
)
async def get_overview(window: str = Query(default="24h")):
    return await svc.get_overview(_validate_window(window))


@router.get(
    "/by-model",
    summary="Request counts, latency, and token stats per model",
    dependencies=[Depends(require_api_key)],
)
async def get_by_model(window: str = Query(default="24h")):
    return {"window": window, "data": await svc.get_by_model(_validate_window(window))}


@router.get(
    "/by-node",
    summary="Request counts, latency, and p95 per worker node",
    dependencies=[Depends(require_api_key)],
)
async def get_by_node(window: str = Query(default="24h")):
    return {"window": window, "data": await svc.get_by_node(_validate_window(window))}


@router.get(
    "/by-key",
    summary="Request counts per API key (key hint only, no secret exposed)",
    dependencies=[Depends(require_api_key)],
)
async def get_by_key(window: str = Query(default="24h")):
    return {"window": window, "data": await svc.get_by_key(_validate_window(window))}


@router.get(
    "/by-endpoint",
    summary="Request counts per endpoint path",
    dependencies=[Depends(require_api_key)],
)
async def get_by_endpoint(window: str = Query(default="24h")):
    return {"window": window, "data": await svc.get_by_endpoint(_validate_window(window))}


@router.get(
    "/by-hour",
    summary="Hourly time-series: requests and token throughput",
    dependencies=[Depends(require_api_key)],
)
async def get_by_hour(window: str = Query(default="24h")):
    return {"window": window, "data": await svc.get_by_hour(_validate_window(window))}


# ── Request log ───────────────────────────────────────────────────────────────

@router.get(
    "/requests",
    summary="Paginated raw request log for debugging",
    dependencies=[Depends(require_api_key)],
)
async def get_request_log(
    window: str       = Query(default="1h"),
    limit: int        = Query(default=50, ge=1, le=500),
    offset: int       = Query(default=0, ge=0),
    node_id: Optional[str]  = Query(default=None),
    model: Optional[str]    = Query(default=None),
    status_gte: Optional[int] = Query(default=None, description="Min HTTP status code, e.g. 400"),
    errors_only: bool = Query(default=False),
):
    """
    Returns raw request rows, newest first.
    Filter by node_id, model, HTTP status, or errors_only=true.
    Paginate with limit/offset.
    """
    return await svc.get_request_log(
        window=_validate_window(window),
        limit=limit,
        offset=offset,
        node_id=node_id,
        model=model,
        status_gte=status_gte,
        errors_only=errors_only,
    )


# ── Housekeeping ──────────────────────────────────────────────────────────────

@router.delete(
    "/requests",
    summary="Purge request log rows older than the given window",
    dependencies=[Depends(require_api_key)],
)
async def purge_request_log(
    older_than: str = Query(
        default="30d",
        description="Delete rows older than this window. Options: 1h 6h 24h 7d 30d",
    ),
):
    """
    Removes request log rows that fall outside the retention window.
    Use this to keep the SQLite file from growing unbounded.
    Audit log and model records are NOT affected.
    """
    w = _validate_window(older_than)
    from app.services.metrics import _since_clause
    since_clause, params = _since_clause(w)

    if not since_clause:
        raise HTTPException(
            status_code=400,
            detail="Cannot purge with window='all'. Specify a concrete window like '30d'.",
        )

    # Delete rows OLDER than the window boundary
    # _since_clause gives "AND ts >= ?" — we want ts < that cutoff
    cutoff = params[0]  # the ISO timestamp
    async with get_db() as db:
        async with db.execute(
            "SELECT COUNT(*) AS n FROM requests WHERE ts < ?", [cutoff]
        ) as cur:
            count_before = (await cur.fetchone())["n"]

        await db.execute("DELETE FROM requests WHERE ts < ?", [cutoff])
        await db.commit()

    logger.info("Purged %d request rows older than %s", count_before, older_than)
    return {
        "message":      f"Purged {count_before} request row(s) older than '{older_than}'.",
        "deleted_rows": count_before,
        "cutoff_ts":    cutoff,
    }
