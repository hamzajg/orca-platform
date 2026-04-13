"""
services/metrics.py — Query-based metrics engine over the requests table.

All metrics are computed on demand from SQLite — no separate time-series DB
needed at this scale.  For larger deployments, replace the SQL layer with
a Prometheus push or ClickHouse queries without changing the router.

Metrics provided:

  Overview (configurable time window):
    - total_requests, error_count, error_rate
    - total_tokens (prompt + completion)
    - avg / p50 / p95 / p99 latency  (ms)
    - tokens_per_second  (completion tokens / wall-clock seconds)
    - streaming_ratio

  Breakdown by dimension:
    - by_model     — request count, avg latency, total tokens per model
    - by_node      — same, per worker node
    - by_key       — same, per api_key_hint
    - by_endpoint  — same, per endpoint path
    - by_hour      — time-series: requests + tokens bucketed per hour

  Request log:
    - Paginated raw request rows for debugging

Time window options: 1h | 6h | 24h | 7d | 30d | all
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.db import get_db

logger = logging.getLogger(__name__)

# ── Window helper ─────────────────────────────────────────────────────────────

_WINDOWS = {
    "1h":  timedelta(hours=1),
    "6h":  timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d":  timedelta(days=7),
    "30d": timedelta(days=30),
    "all": None,
}


def _since_clause(window: str) -> tuple[str, list]:
    """Return (WHERE clause fragment, params) for the given window string."""
    delta = _WINDOWS.get(window)
    if delta is None:
        return "", []
    since = (datetime.now(tz=timezone.utc) - delta).isoformat()
    return "AND ts >= ?", [since]


# ── Percentile helper (pure Python on sorted list) ───────────────────────────

def _percentile(sorted_vals: list[float], p: float) -> Optional[float]:
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p / 100
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return round(sorted_vals[lo], 2)
    frac = k - lo
    return round(sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac, 2)


# ── Public API ────────────────────────────────────────────────────────────────

async def get_overview(window: str = "24h") -> dict:
    """
    Single-row summary metrics for the given time window.
    Latency percentiles are computed in Python after fetching the raw values
    (SQLite has no native percentile function).
    """
    since_clause, params = _since_clause(window)
    base_filter = f"WHERE status_code IS NOT NULL {since_clause}"

    async with get_db() as db:
        # ── Aggregate counts ──────────────────────────────────────────────────
        async with db.execute(
            f"""
            SELECT
                COUNT(*)                                  AS total_requests,
                SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS error_count,
                SUM(CASE WHEN streaming = 1      THEN 1 ELSE 0 END) AS streaming_count,
                SUM(COALESCE(total_tokens, 0))            AS total_tokens,
                SUM(COALESCE(prompt_tokens, 0))           AS prompt_tokens,
                SUM(COALESCE(completion_tokens, 0))       AS completion_tokens,
                AVG(latency_ms)                           AS avg_latency_ms,
                MIN(latency_ms)                           AS min_latency_ms,
                MAX(latency_ms)                           AS max_latency_ms,
                MIN(ts)                                   AS oldest_ts,
                MAX(ts)                                   AS newest_ts
            FROM requests {base_filter}
            """,
            params,
        ) as cur:
            row = dict(await cur.fetchone())

        # ── Latency percentiles ───────────────────────────────────────────────
        async with db.execute(
            f"SELECT latency_ms FROM requests {base_filter} "
            f"AND latency_ms IS NOT NULL ORDER BY latency_ms",
            params,
        ) as cur:
            latencies = [r[0] for r in await cur.fetchall()]

    total  = row["total_requests"] or 0
    errors = row["error_count"] or 0
    stream = row["streaming_count"] or 0

    # Tokens/sec: completion tokens ÷ wall-clock span of the window
    tps: Optional[float] = None
    if row["oldest_ts"] and row["newest_ts"] and row["oldest_ts"] != row["newest_ts"]:
        try:
            span_s = (
                datetime.fromisoformat(row["newest_ts"])
                - datetime.fromisoformat(row["oldest_ts"])
            ).total_seconds()
            if span_s > 0:
                tps = round((row["completion_tokens"] or 0) / span_s, 2)
        except Exception:
            pass

    return {
        "window": window,
        "total_requests":     total,
        "error_count":        errors,
        "error_rate_pct":     round(errors / total * 100, 2) if total else 0.0,
        "streaming_count":    stream,
        "streaming_ratio_pct": round(stream / total * 100, 2) if total else 0.0,
        "tokens": {
            "total":      row["total_tokens"] or 0,
            "prompt":     row["prompt_tokens"] or 0,
            "completion": row["completion_tokens"] or 0,
            "per_second": tps,
        },
        "latency_ms": {
            "avg": round(row["avg_latency_ms"], 2) if row["avg_latency_ms"] else None,
            "min": round(row["min_latency_ms"], 2) if row["min_latency_ms"] else None,
            "max": round(row["max_latency_ms"], 2) if row["max_latency_ms"] else None,
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
            "p99": _percentile(latencies, 99),
        },
    }


async def get_by_model(window: str = "24h") -> list[dict]:
    """Request counts, latency, and token stats grouped by model."""
    since_clause, params = _since_clause(window)
    base_filter = f"WHERE model IS NOT NULL {since_clause}"

    async with get_db() as db:
        async with db.execute(
            f"""
            SELECT
                model,
                COUNT(*)                                              AS requests,
                SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END)  AS errors,
                AVG(latency_ms)                                       AS avg_latency_ms,
                SUM(COALESCE(total_tokens, 0))                        AS total_tokens,
                SUM(COALESCE(completion_tokens, 0))                   AS completion_tokens
            FROM requests {base_filter}
            GROUP BY model
            ORDER BY requests DESC
            """,
            params,
        ) as cur:
            rows = await cur.fetchall()

    return [
        {
            "model":              r["model"],
            "requests":           r["requests"],
            "errors":             r["errors"],
            "avg_latency_ms":     round(r["avg_latency_ms"], 2) if r["avg_latency_ms"] else None,
            "total_tokens":       r["total_tokens"],
            "completion_tokens":  r["completion_tokens"],
        }
        for r in rows
    ]


async def get_by_node(window: str = "24h") -> list[dict]:
    """Request counts and latency grouped by worker node."""
    since_clause, params = _since_clause(window)
    base_filter = f"WHERE node_id IS NOT NULL {since_clause}"

    async with get_db() as db:
        async with db.execute(
            f"""
            SELECT
                node_id,
                COUNT(*)                                              AS requests,
                SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END)  AS errors,
                AVG(latency_ms)                                       AS avg_latency_ms,
                MIN(latency_ms)                                       AS min_latency_ms,
                MAX(latency_ms)                                       AS max_latency_ms,
                SUM(COALESCE(total_tokens, 0))                        AS total_tokens
            FROM requests {base_filter}
            GROUP BY node_id
            ORDER BY requests DESC
            """,
            params,
        ) as cur:
            rows = await cur.fetchall()

        # Fetch p95 per node in Python
        async with db.execute(
            f"SELECT node_id, latency_ms FROM requests {base_filter} "
            f"AND latency_ms IS NOT NULL ORDER BY node_id, latency_ms",
            params,
        ) as cur:
            lat_rows = await cur.fetchall()

    # Group latencies by node
    node_latencies: dict[str, list[float]] = {}
    for r in lat_rows:
        node_latencies.setdefault(r["node_id"], []).append(r["latency_ms"])

    return [
        {
            "node_id":        r["node_id"],
            "requests":       r["requests"],
            "errors":         r["errors"],
            "avg_latency_ms": round(r["avg_latency_ms"], 2) if r["avg_latency_ms"] else None,
            "p95_latency_ms": _percentile(node_latencies.get(r["node_id"], []), 95),
            "min_latency_ms": round(r["min_latency_ms"], 2) if r["min_latency_ms"] else None,
            "max_latency_ms": round(r["max_latency_ms"], 2) if r["max_latency_ms"] else None,
            "total_tokens":   r["total_tokens"],
        }
        for r in rows
    ]


async def get_by_key(window: str = "24h") -> list[dict]:
    """Request counts grouped by API key hint (first 8 chars)."""
    since_clause, params = _since_clause(window)
    base_filter = f"WHERE api_key_hint IS NOT NULL {since_clause}"

    async with get_db() as db:
        async with db.execute(
            f"""
            SELECT
                api_key_hint,
                COUNT(*)                                              AS requests,
                SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END)  AS errors,
                AVG(latency_ms)                                       AS avg_latency_ms,
                SUM(COALESCE(total_tokens, 0))                        AS total_tokens
            FROM requests {base_filter}
            GROUP BY api_key_hint
            ORDER BY requests DESC
            """,
            params,
        ) as cur:
            rows = await cur.fetchall()

    return [
        {
            "key_hint":       r["api_key_hint"],
            "requests":       r["requests"],
            "errors":         r["errors"],
            "avg_latency_ms": round(r["avg_latency_ms"], 2) if r["avg_latency_ms"] else None,
            "total_tokens":   r["total_tokens"],
        }
        for r in rows
    ]


async def get_by_endpoint(window: str = "24h") -> list[dict]:
    """Request counts grouped by endpoint path."""
    since_clause, params = _since_clause(window)
    base_filter = f"WHERE endpoint IS NOT NULL {since_clause}"

    async with get_db() as db:
        async with db.execute(
            f"""
            SELECT
                endpoint,
                COUNT(*)                                              AS requests,
                SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END)  AS errors,
                AVG(latency_ms)                                       AS avg_latency_ms
            FROM requests {base_filter}
            GROUP BY endpoint
            ORDER BY requests DESC
            """,
            params,
        ) as cur:
            rows = await cur.fetchall()

    return [
        {
            "endpoint":       r["endpoint"],
            "requests":       r["requests"],
            "errors":         r["errors"],
            "avg_latency_ms": round(r["avg_latency_ms"], 2) if r["avg_latency_ms"] else None,
        }
        for r in rows
    ]


async def get_by_hour(window: str = "24h") -> list[dict]:
    """
    Hourly time-series: requests and tokens per UTC hour bucket.
    Useful for plotting throughput over time.
    """
    since_clause, params = _since_clause(window)
    base_filter = f"WHERE ts IS NOT NULL {since_clause}"

    async with get_db() as db:
        async with db.execute(
            f"""
            SELECT
                strftime('%Y-%m-%dT%H:00:00', ts)        AS hour,
                COUNT(*)                                  AS requests,
                SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS errors,
                SUM(COALESCE(total_tokens, 0))            AS total_tokens,
                AVG(latency_ms)                           AS avg_latency_ms
            FROM requests {base_filter}
            GROUP BY hour
            ORDER BY hour ASC
            """,
            params,
        ) as cur:
            rows = await cur.fetchall()

    return [
        {
            "hour":           r["hour"],
            "requests":       r["requests"],
            "errors":         r["errors"],
            "total_tokens":   r["total_tokens"],
            "avg_latency_ms": round(r["avg_latency_ms"], 2) if r["avg_latency_ms"] else None,
        }
        for r in rows
    ]


async def get_request_log(
    window: str = "1h",
    limit: int = 100,
    offset: int = 0,
    node_id: Optional[str] = None,
    model: Optional[str] = None,
    status_gte: Optional[int] = None,
    errors_only: bool = False,
) -> dict:
    """
    Paginated raw request log for debugging.
    Filters: node_id, model, minimum status code, errors_only.
    """
    since_clause, params = _since_clause(window)
    extra_clauses: list[str] = []

    if node_id:
        extra_clauses.append("AND node_id = ?")
        params.append(node_id)
    if model:
        extra_clauses.append("AND model = ?")
        params.append(model)
    if status_gte:
        extra_clauses.append("AND status_code >= ?")
        params.append(status_gte)
    if errors_only:
        extra_clauses.append("AND status_code >= 400")

    where = f"WHERE 1=1 {since_clause} {' '.join(extra_clauses)}"

    async with get_db() as db:
        # Total count for pagination
        async with db.execute(
            f"SELECT COUNT(*) AS n FROM requests {where}", params
        ) as cur:
            total = (await cur.fetchone())["n"]

        # Page of rows
        async with db.execute(
            f"""
            SELECT request_id, ts, node_id, model, endpoint,
                   status_code, latency_ms, prompt_tokens, completion_tokens,
                   total_tokens, streaming, error, api_key_hint
            FROM requests {where}
            ORDER BY ts DESC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        ) as cur:
            rows = await cur.fetchall()

    return {
        "total":  total,
        "limit":  limit,
        "offset": offset,
        "rows":   [dict(r) for r in rows],
    }
