"""
middleware/request_id.py — Injects a unique X-Request-ID on every request.

If the client sends an X-Request-ID header we echo it back unchanged,
so clients can correlate their own traces.  Otherwise we generate a
short UUID and attach it.

The request ID is stored on request.state.request_id so any downstream
handler or logger can read it without parsing headers again.

Usage (added in main.py as Starlette middleware):
    from app.middleware.request_id import RequestIDMiddleware
    app.add_middleware(RequestIDMiddleware)
"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # Honour client-supplied ID; fall back to a fresh one
        request_id = (
            request.headers.get("X-Request-ID")
            or str(uuid.uuid4())
        )
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
