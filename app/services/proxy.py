"""
services/proxy.py — Async reverse-proxy to Ollama worker nodes.

Two public functions:

  proxy_request()  — Non-streaming: forwards the request, waits for the full
                     response, returns it as a dict.

  proxy_stream()   — Streaming: yields raw SSE lines from Ollama directly to
                     the client using an async generator.  The caller wraps
                     this in a FastAPI StreamingResponse.

Both functions:
  - Pick the next healthy node via the registry's round-robin router
  - Translate the OpenAI-format request body into Ollama's native API format
  - Translate Ollama's response back into OpenAI format
  - Log the completed request to SQLite (fire-and-forget)

Ollama API reference: https://github.com/ollama/ollama/blob/main/docs/api.md
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, AsyncGenerator, Optional

import httpx

from app.services.node_registry import NodeRegistry
from app.services.logger import log_request

logger = logging.getLogger(__name__)

# httpx client reused across requests (connection pooling)
_http_client: Optional[httpx.AsyncClient] = None


def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0))
    return _http_client


async def close_http_client() -> None:
    global _http_client
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()


# ── Request translation: OpenAI → Ollama ──────────────────────────────────────

def _chat_to_ollama(body: dict) -> dict:
    """Translate an OpenAI chat/completions body to Ollama /api/chat format."""
    ollama: dict[str, Any] = {
        "model": body["model"],
        "messages": body.get("messages", []),
        "stream": body.get("stream", False),
    }
    options: dict[str, Any] = dict(body.get("options") or {})
    if body.get("temperature") is not None:
        options["temperature"] = body["temperature"]
    if body.get("top_p") is not None:
        options["top_p"] = body["top_p"]
    if body.get("max_tokens") is not None:
        options["num_predict"] = body["max_tokens"]
    if body.get("seed") is not None:
        options["seed"] = body["seed"]
    if body.get("stop") is not None:
        stop = body["stop"]
        options["stop"] = [stop] if isinstance(stop, str) else stop
    if options:
        ollama["options"] = options
    return ollama


def _completion_to_ollama(body: dict) -> dict:
    """Translate an OpenAI completions body to Ollama /api/generate format."""
    prompt = body["prompt"]
    if isinstance(prompt, list):
        prompt = "\n".join(prompt)
    ollama: dict[str, Any] = {
        "model": body["model"],
        "prompt": prompt,
        "stream": body.get("stream", False),
    }
    options: dict[str, Any] = dict(body.get("options") or {})
    if body.get("temperature") is not None:
        options["temperature"] = body["temperature"]
    if body.get("top_p") is not None:
        options["top_p"] = body["top_p"]
    if body.get("max_tokens") is not None:
        options["num_predict"] = body["max_tokens"]
    if body.get("seed") is not None:
        options["seed"] = body["seed"]
    if options:
        ollama["options"] = options
    return ollama


def _embedding_to_ollama(body: dict) -> dict:
    """Translate an OpenAI embeddings body to Ollama /api/embed format."""
    inp = body["input"]
    return {
        "model": body["model"],
        "input": inp if isinstance(inp, list) else [inp],
    }


# ── Response translation: Ollama → OpenAI ────────────────────────────────────

def _ollama_chat_to_openai(data: dict, request_id: str, model: str) -> dict:
    created = int(time.time())
    msg = data.get("message", {})
    usage = UsageFromOllama(data)
    return {
        "id": f"chatcmpl-{request_id}",
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": msg.get("role", "assistant"),
                    "content": msg.get("content", ""),
                },
                "finish_reason": "stop" if data.get("done") else "length",
            }
        ],
        "usage": usage,
    }


def _ollama_generate_to_openai(data: dict, request_id: str, model: str) -> dict:
    created = int(time.time())
    usage = UsageFromOllama(data)
    return {
        "id": f"cmpl-{request_id}",
        "object": "text_completion",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "text": data.get("response", ""),
                "finish_reason": "stop" if data.get("done") else "length",
            }
        ],
        "usage": usage,
    }


def _ollama_embed_to_openai(data: dict, model: str) -> dict:
    embeddings = data.get("embeddings", [])
    return {
        "object": "list",
        "data": [
            {"object": "embedding", "index": i, "embedding": emb}
            for i, emb in enumerate(embeddings)
        ],
        "model": model,
        "usage": {"prompt_tokens": data.get("prompt_eval_count", 0), "total_tokens": data.get("prompt_eval_count", 0)},
    }


def UsageFromOllama(data: dict) -> dict:
    pt = data.get("prompt_eval_count", 0) or 0
    ct = data.get("eval_count", 0) or 0
    return {
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "total_tokens": pt + ct,
    }


# ── SSE helpers ───────────────────────────────────────────────────────────────

def _chat_chunk_to_sse(data: dict, request_id: str, model: str) -> str:
    """Convert one Ollama streaming chunk to an OpenAI SSE line."""
    created = int(time.time())
    msg = data.get("message", {})
    done = data.get("done", False)
    chunk = {
        "id": f"chatcmpl-{request_id}",
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {
                    "role": "assistant",
                    "content": msg.get("content", ""),
                },
                "finish_reason": "stop" if done else None,
            }
        ],
    }
    return f"data: {json.dumps(chunk)}\n\n"


def _generate_chunk_to_sse(data: dict, request_id: str, model: str) -> str:
    """Convert one Ollama generate streaming chunk to an OpenAI SSE line."""
    created = int(time.time())
    done = data.get("done", False)
    chunk = {
        "id": f"cmpl-{request_id}",
        "object": "text_completion",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "text": data.get("response", ""),
                "finish_reason": "stop" if done else None,
            }
        ],
    }
    return f"data: {json.dumps(chunk)}\n\n"


# ── Public: non-streaming ─────────────────────────────────────────────────────

async def proxy_request(
    *,
    registry: NodeRegistry,
    endpoint: str,            # "chat" | "generate" | "embed"
    body: dict,
    api_key_hint: Optional[str] = None,
) -> tuple[dict, int]:
    """
    Forward a non-streaming request to the next healthy node.
    Returns (response_dict, http_status_code).
    Raises httpx.HTTPError on network failures.
    """
    model = body.get("model", "")
    node = await registry.get_next_node(model=model)
    if node is None:
        raise RuntimeError("No healthy nodes available.")

    request_id = str(uuid.uuid4())[:12]
    t0 = time.monotonic()

    ollama_path, ollama_body = _build_ollama_request(endpoint, body)
    url = f"{node.base_url}{ollama_path}"

    logger.debug("→ %s  node=%s  model=%s", url, node.id, model)

    try:
        resp = await get_http_client().post(url, json=ollama_body)
        latency_ms = (time.monotonic() - t0) * 1000
        resp.raise_for_status()
        data = resp.json()

        result = _translate_response(endpoint, data, request_id, model)
        usage = result.get("usage", {})

        await log_request(
            request_id=request_id,
            node_id=node.id,
            model=model,
            endpoint=f"/v1/{_endpoint_to_path(endpoint)}",
            method="POST",
            status_code=resp.status_code,
            latency_ms=round(latency_ms, 2),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            streaming=False,
            api_key_hint=api_key_hint,
        )

        return result, 200

    except httpx.HTTPStatusError as exc:
        latency_ms = (time.monotonic() - t0) * 1000
        error_text = str(exc)
        await log_request(
            request_id=request_id,
            node_id=node.id,
            model=model,
            endpoint=f"/v1/{_endpoint_to_path(endpoint)}",
            method="POST",
            status_code=exc.response.status_code,
            latency_ms=round(latency_ms, 2),
            error=error_text[:500],
            api_key_hint=api_key_hint,
        )
        raise


# ── Public: streaming ─────────────────────────────────────────────────────────

async def proxy_stream(
    *,
    registry: NodeRegistry,
    endpoint: str,
    body: dict,
    api_key_hint: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """
    Yield OpenAI-format SSE lines from Ollama's streaming response.
    The caller should wrap this in FastAPI's StreamingResponse with
    media_type="text/event-stream".
    """
    model = body.get("model", "")
    node = await registry.get_next_node(model=model)
    if node is None:
        yield "data: " + json.dumps({"error": "No healthy nodes available."}) + "\n\n"
        yield "data: [DONE]\n\n"
        return

    request_id = str(uuid.uuid4())[:12]
    t0 = time.monotonic()
    total_prompt_tokens = 0
    total_completion_tokens = 0

    ollama_path, ollama_body = _build_ollama_request(endpoint, body)
    url = f"{node.base_url}{ollama_path}"

    logger.debug("→ STREAM %s  node=%s  model=%s", url, node.id, model)

    try:
        async with get_http_client().stream("POST", url, json=ollama_body) as resp:
            resp.raise_for_status()
            async for raw_line in resp.aiter_lines():
                if not raw_line.strip():
                    continue
                try:
                    chunk_data = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue

                # Accumulate token counts from final chunk
                if chunk_data.get("done"):
                    total_prompt_tokens = chunk_data.get("prompt_eval_count", 0) or 0
                    total_completion_tokens = chunk_data.get("eval_count", 0) or 0

                # Translate and yield
                if endpoint == "chat":
                    yield _chat_chunk_to_sse(chunk_data, request_id, model)
                else:
                    yield _generate_chunk_to_sse(chunk_data, request_id, model)

        yield "data: [DONE]\n\n"

    except Exception as exc:
        logger.error("Streaming error from node %s: %s", node.id, exc)
        yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        yield "data: [DONE]\n\n"

    finally:
        latency_ms = (time.monotonic() - t0) * 1000
        await log_request(
            request_id=request_id,
            node_id=node.id,
            model=model,
            endpoint=f"/v1/{_endpoint_to_path(endpoint)}",
            method="POST",
            status_code=200,
            latency_ms=round(latency_ms, 2),
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            streaming=True,
            api_key_hint=api_key_hint,
        )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _build_ollama_request(endpoint: str, body: dict) -> tuple[str, dict]:
    if endpoint == "chat":
        return "/api/chat", _chat_to_ollama(body)
    elif endpoint == "generate":
        return "/api/generate", _completion_to_ollama(body)
    elif endpoint == "embed":
        return "/api/embed", _embedding_to_ollama(body)
    raise ValueError(f"Unknown endpoint: {endpoint!r}")


def _translate_response(endpoint: str, data: dict, request_id: str, model: str) -> dict:
    if endpoint == "chat":
        return _ollama_chat_to_openai(data, request_id, model)
    elif endpoint == "generate":
        return _ollama_generate_to_openai(data, request_id, model)
    elif endpoint == "embed":
        return _ollama_embed_to_openai(data, model)
    raise ValueError(f"Unknown endpoint: {endpoint!r}")


def _endpoint_to_path(endpoint: str) -> str:
    return {
        "chat": "chat/completions",
        "generate": "completions",
        "embed": "embeddings",
    }.get(endpoint, endpoint)
