"""
routers/ollama_compat.py — Full Ollama native API compatibility layer.

Exposes every endpoint the Ollama REST API provides so any client that
points its OLLAMA_HOST (or base_url) at this gateway works transparently:

  ollama Python SDK, Open WebUI, Continue.dev, Msty, Enchanted, AnythingLLM,
  LangChain Ollama integration, Dify, and any other tool that checks /api/tags.

Endpoint map:
  GET  /                          → health check ("Ollama is running")
  GET  /api/version               → version string
  GET  /api/tags                  → list all models across cluster
  POST /api/show                  → model metadata (proxied to best node)
  POST /api/chat                  → chat inference (streaming NDJSON)
  POST /api/generate              → text generation (streaming NDJSON)
  POST /api/embed                 → embeddings (new endpoint, Ollama ≥0.3)
  POST /api/embeddings            → embeddings (legacy endpoint)
  POST /api/pull                  → pull a model (streaming NDJSON progress)
  DELETE /api/delete              → delete a model from a node
  POST /api/copy                  → copy a model on a node
  GET  /api/ps                    → list running/loaded models
  POST /api/create                → create model from Modelfile (passthrough)
  POST /api/push                  → push model to registry (passthrough)
  HEAD /api/blobs/{digest}        → check blob exists (passthrough)
  POST /api/blobs/{digest}        → upload blob (passthrough)

Strategy:
  - Inference endpoints (/api/chat, /api/generate, /api/embed) go through
    the existing round-robin router and are logged to SQLite.
  - Management endpoints (/api/pull, /api/delete, /api/copy, /api/show,
    /api/ps, /api/create, /api/push, blobs) are proxied directly to the
    best available node, or fanned out to all nodes when appropriate.
  - /api/tags aggregates models from ALL healthy nodes (deduplicates by name).
  - /api/version returns the gateway's version, not a node's.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.middleware.auth import require_api_key
from app.services.proxy import get_http_client
from app.services.logger import log_request

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ollama-compat"])

# Gateway version string returned by /api/version
_GATEWAY_VERSION = "0.7.0-gateway"


# ── helpers ───────────────────────────────────────────────────────────────────

def _registry(request: Request):
    return request.app.state.registry


async def _best_node(registry, model: Optional[str] = None):
    """Return next healthy node, raising 503 if none available."""
    node = await registry.get_next_node(model=model)
    if node is None:
        raise HTTPException(status_code=503, detail="No healthy nodes available.")
    return node


async def _passthrough_json(
    request: Request,
    path: str,
    method: str = "POST",
    node=None,
    body: Optional[dict] = None,
) -> dict:
    """Forward a JSON request to a node and return the parsed response."""
    url = f"{node.base_url}{path}"
    payload = body if body is not None else await request.json()
    resp = await get_http_client().request(method, url, json=payload, timeout=60.0)
    resp.raise_for_status()
    return resp.json()


async def _ndjson_stream(
    node_url: str,
    path: str,
    body: dict,
) -> AsyncGenerator[bytes, None]:
    """Stream raw NDJSON bytes from an Ollama node endpoint unchanged."""
    url = f"{node_url}{path}"
    async with get_http_client().stream(
        "POST", url, json=body,
        timeout=httpx.Timeout(3600.0, connect=10.0),
    ) as resp:
        resp.raise_for_status()
        async for chunk in resp.aiter_bytes():
            yield chunk


async def _safe_ndjson_stream(
    node_url: str,
    path: str,
    body: dict,
    node_id: str,
) -> AsyncGenerator[bytes, None]:
    """Like _ndjson_stream but catches upstream errors and yields them as NDJSON."""
    try:
        async for chunk in _ndjson_stream(node_url, path, body):
            yield chunk
    except httpx.HTTPStatusError as exc:
        logger.error("Upstream node %s error on %s: %s", node_id, path, exc.response.text[:200])
        yield json.dumps({"error": exc.response.text}).encode()
    except Exception as exc:
        logger.error("Unexpected error from node %s on %s: %s", node_id, path, exc)
        yield json.dumps({"error": str(exc)}).encode()


# ── Root health check ─────────────────────────────────────────────────────────
# Many clients (Open WebUI, Continue.dev) hit GET / first to verify the server.

@router.get("/", include_in_schema=False)
async def root_health():
    return Response(content="Ollama is running", media_type="text/plain")


# ── Version ───────────────────────────────────────────────────────────────────

@router.get("/api/version", summary="Ollama version", dependencies=[Depends(require_api_key)])
async def get_version():
    return {"version": _GATEWAY_VERSION}


# ── Tags (model list) ─────────────────────────────────────────────────────────
# This is the #1 endpoint that breaks clients — they call it to discover models.
# We aggregate models from ALL healthy nodes, dedup by name, and return the
# Ollama wire format that clients expect.

@router.get("/api/tags", summary="List all available models (Ollama format)", dependencies=[Depends(require_api_key)])
async def list_tags(request: Request):
    registry = _registry(request)
    nodes = [n for n in registry.get_all_nodes() if n.is_routable]

    seen: dict[str, dict] = {}   # model_name → best model entry

    for node in nodes:
        try:
            resp = await get_http_client().get(
                f"{node.base_url}/api/tags", timeout=10.0
            )
            resp.raise_for_status()
            data = resp.json()
            for model in data.get("models", []):
                name = model.get("name", "")
                if name and name not in seen:
                    seen[name] = model
        except Exception as exc:
            logger.debug("Failed to fetch tags from %s: %s", node.id, exc)

    return {"models": list(seen.values())}


# ── Model info (show) ─────────────────────────────────────────────────────────

@router.post("/api/show", summary="Show model information", dependencies=[Depends(require_api_key)])
async def show_model(request: Request):
    body = await request.json()
    model = body.get("model") or body.get("name", "")
    registry = _registry(request)
    node = await _best_node(registry, model=model)
    try:
        return await _passthrough_json(request, "/api/show", body=body, node=node)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


# ── Chat inference (native NDJSON) ────────────────────────────────────────────
# Clients that use the Ollama SDK send requests here.
# We proxy the raw NDJSON stream unchanged so all Ollama-specific fields
# (total_duration, eval_count, etc.) pass through intact.

@router.post("/api/chat", summary="Chat (Ollama native format)", dependencies=[Depends(require_api_key)])
async def api_chat(request: Request, api_key: str = Depends(require_api_key)):
    body = await request.json()
    model = body.get("model", "")
    registry = _registry(request)
    node = await _best_node(registry, model=model)

    t0 = time.monotonic()
    request_id = f"ollama-chat-{int(time.time())}"

    async def _stream_and_log():
        prompt_tokens = completion_tokens = 0
        error_text = None
        try:
            async for chunk in _ndjson_stream(node.base_url, "/api/chat", body):
                yield chunk
                try:
                    data = json.loads(chunk)
                    if data.get("done"):
                        prompt_tokens    = data.get("prompt_eval_count", 0) or 0
                        completion_tokens = data.get("eval_count", 0) or 0
                except Exception:
                    pass
        except httpx.HTTPStatusError as exc:
            error_text = exc.response.text[:500]
            logger.error("Upstream node %s error on /api/chat: %s", node.id, error_text)
            yield json.dumps({"error": exc.response.text}).encode()
        except Exception as exc:
            error_text = str(exc)[:500]
            logger.exception("Unexpected streaming error from node %s", node.id)
            yield json.dumps({"error": str(exc)}).encode()
        finally:
            await log_request(
                request_id=request_id,
                node_id=node.id,
                model=model,
                endpoint="/api/chat",
                method="POST",
                status_code=200,
                latency_ms=round((time.monotonic() - t0) * 1000, 2),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                error=error_text,
                streaming=body.get("stream", True),
                api_key_hint=api_key,
            )

    streaming = body.get("stream", True)
    if streaming:
        return StreamingResponse(
            _stream_and_log(),
            media_type="application/x-ndjson",
            headers={"X-Accel-Buffering": "no"},
        )
    else:
        chunks = []
        error_text = None
        try:
            async for chunk in _ndjson_stream(node.base_url, "/api/chat", body):
                chunks.append(chunk)
        except httpx.HTTPStatusError as exc:
            error_text = exc.response.text[:500]
            raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)
        except Exception as exc:
            error_text = str(exc)[:500]
            logger.exception("Non-streaming /api/chat failed")
            raise HTTPException(status_code=502, detail=str(exc))
        finally:
            await log_request(
                request_id=request_id,
                node_id=node.id,
                model=model,
                endpoint="/api/chat",
                method="POST",
                status_code=200 if not error_text else 502,
                latency_ms=round((time.monotonic() - t0) * 1000, 2),
                error=error_text,
                streaming=False,
                api_key_hint=api_key,
            )
        raw = b"".join(chunks)
        return Response(content=raw, media_type="application/json")


# ── Generate inference (native NDJSON) ────────────────────────────────────────

@router.post("/api/generate", summary="Generate (Ollama native format)", dependencies=[Depends(require_api_key)])
async def api_generate(request: Request, api_key: str = Depends(require_api_key)):
    body = await request.json()
    model = body.get("model", "")
    registry = _registry(request)
    node = await _best_node(registry, model=model)

    t0 = time.monotonic()
    request_id = f"ollama-gen-{int(time.time())}"

    async def _stream_and_log():
        prompt_tokens = completion_tokens = 0
        error_text = None
        try:
            async for chunk in _ndjson_stream(node.base_url, "/api/generate", body):
                yield chunk
                try:
                    data = json.loads(chunk)
                    if data.get("done"):
                        prompt_tokens     = data.get("prompt_eval_count", 0) or 0
                        completion_tokens = data.get("eval_count", 0) or 0
                except Exception:
                    pass
        except httpx.HTTPStatusError as exc:
            error_text = exc.response.text[:500]
            logger.error("Upstream node %s error on /api/generate: %s", node.id, error_text)
            yield json.dumps({"error": exc.response.text}).encode()
        except Exception as exc:
            error_text = str(exc)[:500]
            logger.exception("Unexpected streaming error from node %s", node.id)
            yield json.dumps({"error": str(exc)}).encode()
        finally:
            await log_request(
                request_id=request_id,
                node_id=node.id,
                model=model,
                endpoint="/api/generate",
                method="POST",
                status_code=200,
                latency_ms=round((time.monotonic() - t0) * 1000, 2),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                error=error_text,
                streaming=body.get("stream", True),
                api_key_hint=api_key,
            )

    streaming = body.get("stream", True)
    if streaming:
        return StreamingResponse(
            _stream_and_log(),
            media_type="application/x-ndjson",
            headers={"X-Accel-Buffering": "no"},
        )
    else:
        chunks = []
        error_text = None
        try:
            async for chunk in _ndjson_stream(node.base_url, "/api/generate", body):
                chunks.append(chunk)
        except httpx.HTTPStatusError as exc:
            error_text = exc.response.text[:500]
            raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)
        except Exception as exc:
            error_text = str(exc)[:500]
            logger.exception("Non-streaming /api/generate failed")
            raise HTTPException(status_code=502, detail=str(exc))
        finally:
            await log_request(
                request_id=request_id,
                node_id=node.id,
                model=model,
                endpoint="/api/generate",
                method="POST",
                status_code=200 if not error_text else 502,
                latency_ms=round((time.monotonic() - t0) * 1000, 2),
                error=error_text,
                streaming=False,
                api_key_hint=api_key,
            )
        raw = b"".join(chunks)
        return Response(content=raw, media_type="application/json")


# ── Embeddings (new /api/embed endpoint, Ollama ≥ 0.3) ───────────────────────

@router.post("/api/embed", summary="Embeddings (Ollama ≥0.3)", dependencies=[Depends(require_api_key)])
async def api_embed(request: Request, api_key: str = Depends(require_api_key)):
    body = await request.json()
    model = body.get("model", "")
    registry = _registry(request)
    node = await _best_node(registry, model=model)
    t0 = time.monotonic()
    try:
        resp = await get_http_client().post(
            f"{node.base_url}/api/embed", json=body, timeout=120.0
        )
        resp.raise_for_status()
        data = resp.json()
        await log_request(
            node_id=node.id, model=model, endpoint="/api/embed",
            method="POST", status_code=resp.status_code,
            latency_ms=round((time.monotonic() - t0) * 1000, 2),
            prompt_tokens=data.get("prompt_eval_count"),
            api_key_hint=api_key,
        )
        return data
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


# ── Embeddings (legacy /api/embeddings endpoint) ──────────────────────────────

@router.post("/api/embeddings", summary="Embeddings (legacy endpoint)", dependencies=[Depends(require_api_key)])
async def api_embeddings_legacy(request: Request, api_key: str = Depends(require_api_key)):
    body = await request.json()
    model = body.get("model", "")
    registry = _registry(request)
    node = await _best_node(registry, model=model)
    t0 = time.monotonic()
    try:
        # Try modern /api/embed first, fall back to /api/embeddings
        for path in ("/api/embed", "/api/embeddings"):
            try:
                resp = await get_http_client().post(
                    f"{node.base_url}{path}", json=body, timeout=120.0
                )
                if resp.status_code != 404:
                    resp.raise_for_status()
                    data = resp.json()
                    await log_request(
                        node_id=node.id, model=model, endpoint="/api/embeddings",
                        method="POST", status_code=resp.status_code,
                        latency_ms=round((time.monotonic() - t0) * 1000, 2),
                        api_key_hint=api_key,
                    )
                    return data
            except httpx.HTTPStatusError as e:
                if e.response.status_code != 404:
                    raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        raise HTTPException(status_code=404, detail="Embeddings endpoint not found on node.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── Pull (streaming NDJSON progress) ─────────────────────────────────────────
# Clients like `ollama pull` send this. We proxy to the best node.
# For multi-node pulls use the dedicated /api/models/pull endpoint instead.

@router.post("/api/pull", summary="Pull a model (Ollama native)", dependencies=[Depends(require_api_key)])
async def api_pull(request: Request):
    body = await request.json()
    model = body.get("model") or body.get("name", "")
    registry = _registry(request)
    # For pull, prefer a healthy node regardless of model presence
    node = await registry.get_next_node()
    if node is None:
        raise HTTPException(status_code=503, detail="No healthy nodes available.")

    return StreamingResponse(
        _safe_ndjson_stream(node.base_url, "/api/pull", body, node.id),
        media_type="application/x-ndjson",
        headers={"X-Accel-Buffering": "no"},
    )


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/api/delete", summary="Delete a model from a node", dependencies=[Depends(require_api_key)])
async def api_delete(request: Request):
    body = await request.json()
    model = body.get("model") or body.get("name", "")
    registry = _registry(request)
    node = await _best_node(registry, model=model)
    try:
        resp = await get_http_client().request(
            "DELETE", f"{node.base_url}/api/delete", json=body, timeout=30.0
        )
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Model '{model}' not found on node '{node.id}'.")
        resp.raise_for_status()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    await registry.trigger_immediate_check()
    return Response(status_code=200)


# ── Copy ──────────────────────────────────────────────────────────────────────

@router.post("/api/copy", summary="Copy a model on a node", dependencies=[Depends(require_api_key)])
async def api_copy(request: Request):
    body = await request.json()
    source = body.get("source", "")
    registry = _registry(request)
    node = await _best_node(registry, model=source)
    try:
        resp = await get_http_client().post(
            f"{node.base_url}/api/copy", json=body, timeout=60.0
        )
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Source model '{source}' not found on node '{node.id}'.")
        resp.raise_for_status()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    await registry.trigger_immediate_check()
    return Response(status_code=200)


# ── Running models (ps) ───────────────────────────────────────────────────────
# Returns the union of running models across ALL healthy nodes.

@router.get("/api/ps", summary="List running/loaded models across cluster", dependencies=[Depends(require_api_key)])
async def api_ps(request: Request):
    registry = _registry(request)
    nodes = [n for n in registry.get_all_nodes() if n.is_routable]

    all_running: list[dict] = []
    for node in nodes:
        try:
            resp = await get_http_client().get(
                f"{node.base_url}/api/ps", timeout=8.0
            )
            resp.raise_for_status()
            data = resp.json()
            for m in data.get("models", []):
                m["_node_id"] = node.id   # annotate with origin node
                all_running.append(m)
        except Exception as exc:
            logger.debug("Failed to fetch /api/ps from %s: %s", node.id, exc)

    return {"models": all_running}


# ── Create (Modelfile) ────────────────────────────────────────────────────────

@router.post("/api/create", summary="Create a model from a Modelfile", dependencies=[Depends(require_api_key)])
async def api_create(request: Request):
    body = await request.json()
    registry = _registry(request)
    node = await registry.get_next_node()
    if node is None:
        raise HTTPException(status_code=503, detail="No healthy nodes available.")

    stream = body.get("stream", True)
    if stream:
        return StreamingResponse(
            _safe_ndjson_stream(node.base_url, "/api/create", body, node.id),
            media_type="application/x-ndjson",
            headers={"X-Accel-Buffering": "no"},
        )
    else:
        chunks = []
        try:
            async for chunk in _ndjson_stream(node.base_url, "/api/create", body):
                chunks.append(chunk)
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        return Response(content=b"".join(chunks), media_type="application/json")


# ── Push ──────────────────────────────────────────────────────────────────────

@router.post("/api/push", summary="Push a model to a registry", dependencies=[Depends(require_api_key)])
async def api_push(request: Request):
    body = await request.json()
    model = body.get("model") or body.get("name", "")
    registry = _registry(request)
    node = await _best_node(registry, model=model)

    stream = body.get("stream", True)
    if stream:
        return StreamingResponse(
            _safe_ndjson_stream(node.base_url, "/api/push", body, node.id),
            media_type="application/x-ndjson",
            headers={"X-Accel-Buffering": "no"},
        )
    else:
        chunks = []
        try:
            async for chunk in _ndjson_stream(node.base_url, "/api/push", body):
                chunks.append(chunk)
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        return Response(content=b"".join(chunks), media_type="application/json")


# ── Blob management ───────────────────────────────────────────────────────────
# Used by `ollama create` when uploading safetensors/GGUF files.

@router.head("/api/blobs/{digest:path}", summary="Check if a blob exists", dependencies=[Depends(require_api_key)])
async def blob_check(digest: str, request: Request):
    registry = _registry(request)
    node = await registry.get_next_node()
    if node is None:
        raise HTTPException(status_code=503, detail="No healthy nodes available.")
    try:
        resp = await get_http_client().head(
            f"{node.base_url}/api/blobs/{digest}", timeout=10.0
        )
        return Response(status_code=resp.status_code)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/api/blobs/{digest:path}", summary="Upload a blob to a node", dependencies=[Depends(require_api_key)])
async def blob_upload(digest: str, request: Request):
    registry = _registry(request)
    node = await registry.get_next_node()
    if node is None:
        raise HTTPException(status_code=503, detail="No healthy nodes available.")
    try:
        raw_body = await request.body()
        resp = await get_http_client().post(
            f"{node.base_url}/api/blobs/{digest}",
            content=raw_body,
            headers={"Content-Type": "application/octet-stream"},
            timeout=httpx.Timeout(3600.0, connect=10.0),
        )
        return Response(status_code=resp.status_code)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
