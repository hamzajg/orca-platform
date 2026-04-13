"""
middleware/auth.py — API key authentication with rate limiting and audit logging.

Phase 3 upgrade over Phase 1/2:
  - Keys validated against KeyStore (DB-backed, named, revocable)
  - Per-key sliding-window rate limiting (RPM configurable per key)
  - Every auth decision written to audit_log
  - Attaches key metadata to request.state for downstream use

Usage (unchanged from caller perspective):
    @router.post("/endpoint", dependencies=[Depends(require_api_key)])

    or to get the key object:
    @router.post("/endpoint")
    async def handler(api_key: str = Depends(require_api_key)):
        ...

The dependency returns the raw key string on success so existing routes
that accept `api_key: str = Depends(require_api_key)` need no changes.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import Header, HTTPException, Request, status

from app.services import audit_log as al

logger = logging.getLogger(__name__)

# ── Public dependency ─────────────────────────────────────────────────────────

async def require_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    authorization: Optional[str] = Header(default=None),
) -> str:
    """
    FastAPI dependency.
    1. Extract key from X-API-Key or Authorization: Bearer
    2. Validate against KeyStore
    3. Check rate limit
    4. Record usage + audit event
    Returns the raw key string on success.
    """
    key_store    = request.app.state.key_store
    rate_limiter = request.app.state.rate_limiter
    client_ip    = _get_client_ip(request)
    endpoint     = str(request.url.path)

    # ── 1. Extract key ────────────────────────────────────────────────────────
    raw_key = _extract_key(x_api_key, authorization)

    if not raw_key:
        await al.audit(
            "auth_fail",
            client_ip=client_ip,
            endpoint=endpoint,
            detail="No API key supplied",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Send via 'X-API-Key' header or 'Authorization: Bearer <key>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ── 2. Validate key ───────────────────────────────────────────────────────
    key_obj = key_store.validate(raw_key)

    if key_obj is None:
        all_keys = {k.key: k for k in key_store.list_keys()}
        known_but_disabled = raw_key in all_keys and not all_keys[raw_key].enabled

        event = "auth_revoked" if known_but_disabled else "auth_fail"
        hint  = raw_key[:8] if len(raw_key) >= 8 else "***"
        name  = all_keys[raw_key].name if known_but_disabled else None

        logger.warning("Auth %s — hint: %s…  ip: %s  path: %s", event, hint, client_ip, endpoint)
        await al.audit(event, key_hint=hint, key_name=name, client_ip=client_ip, endpoint=endpoint)

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ── 3. Rate limit ─────────────────────────────────────────────────────────
    if key_obj.rate_limit_rpm > 0:
        allowed, retry_after = await rate_limiter.check(raw_key, key_obj.rate_limit_rpm)
        if not allowed:
            await al.audit(
                "rate_limit_hit",
                key_hint=key_obj.key_hint,
                key_name=key_obj.name,
                client_ip=client_ip,
                endpoint=endpoint,
                detail=f"retry_after={retry_after}s",
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded ({key_obj.rate_limit_rpm} rpm). Retry after {retry_after}s.",
                headers={"Retry-After": str(retry_after)},
            )

    # ── 4. Record usage ───────────────────────────────────────────────────────
    await key_store.record_usage(raw_key)
    await al.audit(
        "auth_ok",
        key_hint=key_obj.key_hint,
        key_name=key_obj.name,
        client_ip=client_ip,
        endpoint=endpoint,
    )

    request.state.api_key_obj  = key_obj
    request.state.api_key_hint = key_obj.key_hint

    return raw_key


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_key(x_api_key: Optional[str], authorization: Optional[str]) -> Optional[str]:
    if x_api_key:
        return x_api_key.strip()
    if authorization:
        parts = authorization.strip().split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
    return None


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"
