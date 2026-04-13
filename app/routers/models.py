"""
routers/models.py — Model management API (Phase 4).

Endpoints:
  GET  /api/models                        — cluster model index (moved from custom.py)
  GET  /api/models/manifest               — raw models.yaml contents
  POST /api/models/sync                   — reconcile manifest vs actual; enqueue missing pulls
  POST /api/models/pull                   — pull a model on one or all nodes
  GET  /api/models/jobs                   — list all pull jobs
  GET  /api/models/jobs/{job_id}          — single job status
  DELETE /api/models/jobs/{job_id}        — remove a finished job
  GET  /api/models/jobs/{job_id}/stream   — SSE live pull progress
  DELETE /api/models/{model}/nodes/{node_id}  — delete a model from a specific node
"""

from __future__ import annotations

import json
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.middleware.auth import require_api_key
from app.services.model_manager import JobStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/models", tags=["models"])


# ── Pydantic request models ───────────────────────────────────────────────────

class PullRequest(BaseModel):
    model: str
    node_ids: Optional[list[str]] = None   # None = all enabled nodes


# ── Model index ───────────────────────────────────────────────────────────────

@router.get(
    "",
    summary="Aggregated model index across all healthy nodes",
    dependencies=[Depends(require_api_key)],
)
async def list_models(request: Request):
    registry = request.app.state.registry
    model_index = registry.get_all_models()
    models = [
        {"name": name, "available_on": nodes}
        for name, nodes in sorted(model_index.items())
    ]
    return {"models": models, "total": len(models)}


@router.get(
    "/manifest",
    summary="Show the models.yaml manifest",
    dependencies=[Depends(require_api_key)],
)
async def get_manifest(request: Request):
    """Return the parsed contents of models.yaml."""
    from app.config import get_settings
    settings = get_settings()
    manifest = settings.load_models_config()
    return {"manifest": manifest, "total": len(manifest)}


# ── Sync ──────────────────────────────────────────────────────────────────────

@router.post(
    "/sync",
    summary="Reconcile manifest against all nodes; pull missing models",
    dependencies=[Depends(require_api_key)],
)
async def sync_manifest(request: Request):
    """
    Compares models.yaml against every enabled node.
    Enqueues pull jobs for any (model, node) pair that is missing.
    Pull jobs run in the background — poll /api/models/jobs to track progress.
    """
    manager = request.app.state.model_manager
    new_jobs = await manager.sync_manifest()

    return {
        "message": f"Sync complete. {len(new_jobs)} pull job(s) enqueued.",
        "jobs": [j.to_dict() for j in new_jobs],
    }


# ── Pull ──────────────────────────────────────────────────────────────────────

@router.post(
    "/pull",
    summary="Pull a model on one or all nodes",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_api_key)],
)
async def pull_model(body: PullRequest, request: Request):
    """
    Enqueue a pull job for the given model.
    - If node_ids is omitted, the model is pulled on ALL enabled nodes.
    - Returns immediately with job IDs; pull runs in background.
    - Stream live progress via GET /api/models/jobs/{job_id}/stream
    """
    manager = request.app.state.model_manager
    registry = request.app.state.registry

    # Validate node_ids if provided
    if body.node_ids:
        all_node_ids = {n.id for n in registry.get_all_nodes()}
        unknown = set(body.node_ids) - all_node_ids
        if unknown:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown node ID(s): {sorted(unknown)}",
            )

    jobs = await manager.pull_model(model=body.model, node_ids=body.node_ids)
    if not jobs:
        raise HTTPException(
            status_code=404,
            detail="No enabled nodes found to pull on.",
        )

    return {
        "message": f"Pull enqueued for '{body.model}' on {len(jobs)} node(s).",
        "jobs": [j.to_dict() for j in jobs],
    }


# ── Jobs ──────────────────────────────────────────────────────────────────────

@router.get(
    "/jobs",
    summary="List all pull jobs",
    dependencies=[Depends(require_api_key)],
)
async def list_jobs(
    request: Request,
    node_id: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
):
    """
    Returns all pull jobs, optionally filtered by node_id or status.
    Status values: queued | pulling | done | error
    """
    manager = request.app.state.model_manager

    job_status = None
    if status_filter:
        try:
            job_status = JobStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{status_filter}'. "
                       f"Valid values: {[s.value for s in JobStatus]}",
            )

    jobs = manager.list_jobs(node_id=node_id, status=job_status)
    return {
        "jobs": [j.to_dict() for j in jobs],
        "total": len(jobs),
    }


@router.get(
    "/jobs/{job_id}",
    summary="Get a single pull job by ID",
    dependencies=[Depends(require_api_key)],
)
async def get_job(job_id: str, request: Request):
    manager = request.app.state.model_manager
    job = manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return job.to_dict()


@router.delete(
    "/jobs/{job_id}",
    summary="Remove a finished pull job from the job list",
    dependencies=[Depends(require_api_key)],
)
async def delete_job(job_id: str, request: Request):
    manager = request.app.state.model_manager
    deleted = await manager.delete_job(job_id)
    if not deleted:
        job = manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
        raise HTTPException(
            status_code=409,
            detail=f"Job '{job_id}' is currently pulling. Wait for it to finish.",
        )
    return {"message": f"Job '{job_id}' removed."}


@router.get(
    "/jobs/{job_id}/stream",
    summary="SSE stream of live pull progress",
    dependencies=[Depends(require_api_key)],
)
async def stream_job(job_id: str, request: Request):
    """
    Server-Sent Events stream for a pull job.
    Each event is a JSON object with the job's current state.
    Stream ends with 'data: [DONE]' when the job reaches done or error.

    Example (curl):
        curl -N http://localhost:8000/api/models/jobs/{job_id}/stream \\
             -H "X-API-Key: your-key"
    """
    manager = request.app.state.model_manager
    if not manager.get_job(job_id):
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    return StreamingResponse(
        manager.subscribe(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── Delete model from node ────────────────────────────────────────────────────

@router.delete(
    "/{model}/nodes/{node_id}",
    summary="Delete a model from a specific node",
    dependencies=[Depends(require_api_key)],
)
async def delete_model_from_node(
    model: str,
    node_id: str,
    request: Request,
):
    """
    Calls DELETE /api/delete on the target Ollama node to remove the model.
    Triggers a health check refresh so the model index is updated immediately.
    """
    from app.services.proxy import get_http_client

    registry = request.app.state.registry
    node = registry.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found.")

    try:
        resp = await get_http_client().request(
            "DELETE",
            f"{node.base_url}/api/delete",
            json={"name": model},
            timeout=30.0,
        )
        if resp.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=f"Model '{model}' not found on node '{node_id}'.",
            )
        resp.raise_for_status()
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Node error: {exc}")

    # Refresh model list
    await registry.trigger_immediate_check()

    return {"message": f"Model '{model}' deleted from node '{node_id}'."}
