"""
routers/openai_compat.py — OpenAI-compatible API endpoints.

All routes live under /v1/ to be a drop-in replacement for the OpenAI SDK:

    from openai import OpenAI
    client = OpenAI(
        base_url="http://gateway-host:8000/v1",
        api_key="your-platform-key",
    )
    resp = client.chat.completions.create(
        model="llama3.2",
        messages=[{"role": "user", "content": "Hello!"}],
    )

Endpoints:
  GET  /v1/models                  — list all available models across cluster
  GET  /v1/models/{model_id}       — single model detail
  POST /v1/chat/completions        — chat (streaming + non-streaming)
  POST /v1/completions             — raw completion (streaming + non-streaming)
  POST /v1/embeddings              — embeddings
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from app.middleware.auth import require_api_key
from app.schemas.openai import (
    ChatCompletionRequest,
    CompletionRequest,
    EmbeddingRequest,
)
from app.services import proxy as proxy_svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["openai-compat"])


# ── /v1/models ────────────────────────────────────────────────────────────────

@router.get(
    "/models",
    summary="List all models available across healthy nodes",
    dependencies=[Depends(require_api_key)],
)
async def list_models(request: Request) -> dict:
    registry = request.app.state.registry
    model_index = registry.get_all_models()

    cards = []
    for name, node_ids in sorted(model_index.items()):
        cards.append(
            {
                "id": name,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "ollama",
                "available_on": node_ids,
            }
        )
    return {"object": "list", "data": cards}


@router.get(
    "/models/{model_id:path}",
    summary="Get a single model by ID",
    dependencies=[Depends(require_api_key)],
)
async def get_model(model_id: str, request: Request) -> dict:
    registry = request.app.state.registry
    model_index = registry.get_all_models()

    if model_id not in model_index:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{model_id}' not found on any healthy node.",
        )
    return {
        "id": model_id,
        "object": "model",
        "created": int(time.time()),
        "owned_by": "ollama",
        "available_on": model_index[model_id],
    }


# ── /v1/chat/completions ──────────────────────────────────────────────────────

@router.post(
    "/chat/completions",
    summary="Chat completions (OpenAI-compatible)",
    dependencies=[Depends(require_api_key)],
)
async def chat_completions(
    request: Request,
    body: ChatCompletionRequest,
    api_key: str = Depends(require_api_key),
) -> Any:
    registry = request.app.state.registry
    body_dict = body.model_dump(exclude_none=True)

    if body.stream:
        return StreamingResponse(
            proxy_svc.proxy_stream(
                registry=registry,
                endpoint="chat",
                body=body_dict,
                api_key_hint=api_key,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",    # disable nginx buffering
                "Connection": "keep-alive",
            },
        )

    try:
        result, status_code = await proxy_svc.proxy_request(
            registry=registry,
            endpoint="chat",
            body=body_dict,
            api_key_hint=api_key,
        )
        return JSONResponse(content=result, status_code=status_code)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("Chat completion failed")
        raise HTTPException(status_code=502, detail=f"Node error: {exc}")


# ── /v1/completions ───────────────────────────────────────────────────────────

@router.post(
    "/completions",
    summary="Text completions (OpenAI-compatible)",
    dependencies=[Depends(require_api_key)],
)
async def completions(
    request: Request,
    body: CompletionRequest,
    api_key: str = Depends(require_api_key),
) -> Any:
    registry = request.app.state.registry
    body_dict = body.model_dump(exclude_none=True)

    if body.stream:
        return StreamingResponse(
            proxy_svc.proxy_stream(
                registry=registry,
                endpoint="generate",
                body=body_dict,
                api_key_hint=api_key,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    try:
        result, status_code = await proxy_svc.proxy_request(
            registry=registry,
            endpoint="generate",
            body=body_dict,
            api_key_hint=api_key,
        )
        return JSONResponse(content=result, status_code=status_code)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("Completion failed")
        raise HTTPException(status_code=502, detail=f"Node error: {exc}")


# ── /v1/embeddings ────────────────────────────────────────────────────────────

@router.post(
    "/embeddings",
    summary="Embeddings (OpenAI-compatible)",
    dependencies=[Depends(require_api_key)],
)
async def embeddings(
    request: Request,
    body: EmbeddingRequest,
    api_key: str = Depends(require_api_key),
) -> Any:
    registry = request.app.state.registry
    body_dict = body.model_dump(exclude_none=True)

    try:
        result, status_code = await proxy_svc.proxy_request(
            registry=registry,
            endpoint="embed",
            body=body_dict,
            api_key_hint=api_key,
        )
        return JSONResponse(content=result, status_code=status_code)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("Embedding failed")
        raise HTTPException(status_code=502, detail=f"Node error: {exc}")
