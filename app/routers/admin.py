"""
routers/admin.py — Key management and audit log endpoints.

All routes require authentication.  In a real deployment you'd want a
separate admin-only key with a different privilege level; for now any
valid key can manage keys.  This is easy to harden in Phase 5.

Endpoints:
  GET    /api/auth/keys               — list all keys (no secret values)
  POST   /api/auth/keys               — create a new key (returns full secret once)
  DELETE /api/auth/keys/{name}        — permanently delete a key
  POST   /api/auth/keys/{name}/revoke — disable a key
  POST   /api/auth/keys/{name}/enable — re-enable a key
  PATCH  /api/auth/keys/{name}/rate-limit  — update RPM limit
  POST   /api/auth/keys/{name}/reset-limit — reset rate-limit window
  GET    /api/auth/audit              — recent audit log events
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.middleware.auth import require_api_key
from app.services import audit_log as al

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["admin"])


# ── Pydantic request/response models ─────────────────────────────────────────

class CreateKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_\-]+$")
    rate_limit_rpm: int = Field(default=0, ge=0, description="0 = unlimited")


class UpdateRateLimitRequest(BaseModel):
    rate_limit_rpm: int = Field(..., ge=0)


class KeyResponse(BaseModel):
    name: str
    key_hint: str
    key: Optional[str] = None     # only populated on creation
    enabled: bool
    rate_limit_rpm: int
    created_at: str
    last_used: Optional[str]
    request_count: int


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get(
    "/keys",
    summary="List all API keys (no secret values)",
    dependencies=[Depends(require_api_key)],
)
async def list_keys(request: Request) -> dict:
    keys = request.app.state.key_store.list_keys()
    return {
        "keys": [k.to_dict(reveal_key=False) for k in keys],
        "total": len(keys),
    }


@router.post(
    "/keys",
    summary="Create a new API key",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key)],
)
async def create_key(
    body: CreateKeyRequest,
    request: Request,
    api_key: str = Depends(require_api_key),
) -> dict:
    key_store = request.app.state.key_store
    try:
        new_key = await key_store.create_key(
            name=body.name,
            rate_limit_rpm=body.rate_limit_rpm,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    await al.audit(
        "key_created",
        key_hint=new_key.key_hint,
        key_name=new_key.name,
        client_ip=_ip(request),
        detail=f"rpm={body.rate_limit_rpm}",
    )

    result = new_key.to_dict(reveal_key=True)
    result["_note"] = "Store this key now — it will not be shown again."
    return result


@router.delete(
    "/keys/{name}",
    summary="Permanently delete an API key",
    dependencies=[Depends(require_api_key)],
)
async def delete_key(
    name: str,
    request: Request,
    api_key: str = Depends(require_api_key),
) -> dict:
    key_store = request.app.state.key_store
    deleted = await key_store.delete_key(name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Key '{name}' not found.")

    await al.audit("key_deleted", key_name=name, client_ip=_ip(request))
    return {"message": f"Key '{name}' deleted."}


@router.post(
    "/keys/{name}/revoke",
    summary="Revoke (disable) an API key",
    dependencies=[Depends(require_api_key)],
)
async def revoke_key(
    name: str,
    request: Request,
    api_key: str = Depends(require_api_key),
) -> dict:
    key_store = request.app.state.key_store
    ok = await key_store.revoke_key(name)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Key '{name}' not found.")

    await al.audit("key_revoked", key_name=name, client_ip=_ip(request))
    return {"message": f"Key '{name}' revoked. It will be rejected on next use."}


@router.post(
    "/keys/{name}/enable",
    summary="Re-enable a revoked API key",
    dependencies=[Depends(require_api_key)],
)
async def enable_key(
    name: str,
    request: Request,
    api_key: str = Depends(require_api_key),
) -> dict:
    key_store = request.app.state.key_store
    ok = await key_store.enable_key(name)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Key '{name}' not found.")

    await al.audit("key_enabled", key_name=name, client_ip=_ip(request))
    return {"message": f"Key '{name}' is now active."}


@router.patch(
    "/keys/{name}/rate-limit",
    summary="Update the rate limit for a key",
    dependencies=[Depends(require_api_key)],
)
async def update_rate_limit(
    name: str,
    body: UpdateRateLimitRequest,
    request: Request,
    api_key: str = Depends(require_api_key),
) -> dict:
    key_store = request.app.state.key_store
    ok = await key_store.update_rate_limit(name, body.rate_limit_rpm)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Key '{name}' not found.")

    await al.audit(
        "rate_limit_changed",
        key_name=name,
        client_ip=_ip(request),
        detail=f"new_rpm={body.rate_limit_rpm}",
    )
    label = f"{body.rate_limit_rpm} rpm" if body.rate_limit_rpm > 0 else "unlimited"
    return {"message": f"Key '{name}' rate limit set to {label}."}


@router.post(
    "/keys/{name}/reset-limit",
    summary="Reset the sliding-window rate limit counter for a key",
    dependencies=[Depends(require_api_key)],
)
async def reset_rate_limit(
    name: str,
    request: Request,
    api_key: str = Depends(require_api_key),
) -> dict:
    key_store    = request.app.state.key_store
    rate_limiter = request.app.state.rate_limiter

    key_obj = next((k for k in key_store.list_keys() if k.name == name), None)
    if not key_obj:
        raise HTTPException(status_code=404, detail=f"Key '{name}' not found.")

    rate_limiter.reset(key_obj.key)
    return {"message": f"Rate-limit window for '{name}' cleared."}


@router.get(
    "/audit",
    summary="View recent audit log events",
    dependencies=[Depends(require_api_key)],
)
async def get_audit_log(
    limit: int = Query(default=50, ge=1, le=500),
    event_type: Optional[str] = Query(default=None),
    key_hint: Optional[str] = Query(default=None),
) -> dict:
    events = await al.get_recent_events(
        limit=limit,
        event_type=event_type,
        key_hint=key_hint,
    )
    return {"events": events, "total": len(events)}


# ── Helper ────────────────────────────────────────────────────────────────────

def _ip(request: Request) -> str:
    fwd = request.headers.get("X-Forwarded-For")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
