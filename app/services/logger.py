"""
services/logger.py — Async request logger.

Writes one row to the `requests` table for every proxied inference call.
The write is fire-and-forget (asyncio.create_task) so it never adds latency
to the response path.

Usage:
    from app.services.logger import log_request

    await log_request(
        request_id="uuid",
        node_id="worker-linux",
        model="llama3.2",
        endpoint="/v1/chat/completions",
        method="POST",
        status_code=200,
        latency_ms=312.5,
        prompt_tokens=45,
        completion_tokens=120,
        streaming=True,
        api_key_hint="abcd1234",
    )
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.db import get_db

logger = logging.getLogger(__name__)


async def log_request(
    *,
    request_id: Optional[str] = None,
    node_id: Optional[str] = None,
    model: Optional[str] = None,
    endpoint: Optional[str] = None,
    method: Optional[str] = None,
    status_code: Optional[int] = None,
    latency_ms: Optional[float] = None,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    total_tokens: Optional[int] = None,
    streaming: bool = False,
    error: Optional[str] = None,
    api_key_hint: Optional[str] = None,
) -> None:
    """
    Fire-and-forget async write to the requests table.
    Errors are caught and logged — never propagated to the caller.
    """
    async def _write() -> None:
        try:
            async with get_db() as db:
                await db.execute(
                    """
                    INSERT INTO requests (
                        request_id, ts, node_id, model, endpoint, method,
                        status_code, latency_ms,
                        prompt_tokens, completion_tokens, total_tokens,
                        streaming, error, api_key_hint
                    ) VALUES (
                        :request_id, :ts, :node_id, :model, :endpoint, :method,
                        :status_code, :latency_ms,
                        :prompt_tokens, :completion_tokens, :total_tokens,
                        :streaming, :error, :api_key_hint
                    )
                    """,
                    {
                        "request_id": request_id or str(uuid.uuid4()),
                        "ts": datetime.now(tz=timezone.utc).isoformat(),
                        "node_id": node_id,
                        "model": model,
                        "endpoint": endpoint,
                        "method": method,
                        "status_code": status_code,
                        "latency_ms": latency_ms,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": (
                            total_tokens
                            or (
                                (prompt_tokens or 0) + (completion_tokens or 0)
                                if prompt_tokens or completion_tokens
                                else None
                            )
                        ),
                        "streaming": int(streaming),
                        "error": error,
                        "api_key_hint": api_key_hint[:8] if api_key_hint else None,
                    },
                )
                await db.commit()
        except Exception as exc:
            logger.warning("Failed to log request to DB: %s", exc)

    asyncio.create_task(_write())
