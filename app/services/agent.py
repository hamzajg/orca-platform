"""
services/agent.py — in-gateway agent: Ollama tool-calling loop whose
tools are the gateway's own management reads.

The agent asks an Ollama worker (chosen round-robin via NodeRegistry)
for the next move; the worker may call tools, which run in-process
against the same services the REST routers use. Read-only by design —
no tool mutates cluster state.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable, Optional

import httpx

from app.services import metrics as metrics_svc
from app.services.fine_tuner import fine_tuner

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 5
DEFAULT_MODEL = "llama3.2"

# ── Tool implementations (all read-only) ──────────────────────────────────────


def _tool_list_nodes(registry) -> dict:
    return {
        "nodes": [
            {
                "id": n.id,
                "label": n.label,
                "status": n.status.value,
                "enabled": n.enabled,
                "host": n.host,
                "port": n.port,
                "available_models": n.available_models,
            }
            for n in registry.get_all_nodes()
        ]
    }


def _tool_list_models(registry) -> dict:
    return {"models": registry.get_all_models()}


async def _tool_metrics(window: str = "24h") -> dict:
    return await metrics_svc.get_overview(window=window)


async def _tool_fine_tune_jobs(status: Optional[str] = None) -> dict:
    jobs = await fine_tuner.get_jobs(status=status)
    return {
        "jobs": [
            {k: v for k, v in j.items() if k in (
                "id", "name", "base_model", "status", "created_at",
                "finished_at", "error",
            )}
            for j in jobs
        ]
    }


def build_tools(registry) -> list[dict]:
    """OpenAI/Ollama function specs for the agent's read-only toolset."""
    return [
        {
            "type": "function",
            "function": {
                "name": "list_nodes",
                "description": "List all Ollama worker nodes with status, host and available models.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_models",
                "description": "List models available across healthy nodes, grouped by node.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_metrics",
                "description": "Gateway request metrics overview for a time window.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "window": {
                            "type": "string",
                            "enum": ["1h", "24h", "7d", "30d"],
                            "description": "Time window (default 24h)",
                        }
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_fine_tune_jobs",
                "description": "List fine-tuning jobs, optionally filtered by status.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "enum": ["queued", "running", "completed", "failed", "cancelled"],
                        }
                    },
                },
            },
        },
    ]


async def execute_tool(registry, name: str, arguments: dict) -> dict:
    """Dispatch a tool call; returns a JSON-safe result or error dict."""
    try:
        if name == "list_nodes":
            return {"ok": True, "result": _tool_list_nodes(registry)}
        if name == "list_models":
            return {"ok": True, "result": _tool_list_models(registry)}
        if name == "get_metrics":
            window = (arguments or {}).get("window", "24h")
            return {"ok": True, "result": await _tool_metrics(window)}
        if name == "list_fine_tune_jobs":
            status = (arguments or {}).get("status")
            return {"ok": True, "result": await _tool_fine_tune_jobs(status)}
        return {"ok": False, "error": f"Unknown tool: {name}"}
    except Exception as exc:
        logger.warning("agent tool %s failed: %s", name, exc)
        return {"ok": False, "error": f"{name} failed: {exc}"}


SYSTEM_PROMPT = (
    "You are the ORCA gateway assistant. You can inspect the Ollama "
    "cluster through tools: worker nodes, available models, request "
    "metrics, and fine-tuning jobs. You are read-only — you cannot "
    "change cluster state. Answer concisely; use tools when the answer "
    "needs live data."
)

# ── Ollama chat call (injectable for tests) ───────────────────────────────────

ChatFn = Callable[[Any, str, list[dict], list[dict]], Awaitable[dict]]


async def _default_chat(registry, model: str, messages: list[dict], tools: list[dict]) -> dict:
    """POST /api/chat to the next healthy node; returns the `message` dict."""
    node = await registry.get_next_node(model=model)
    if node is None:
        raise RuntimeError("No healthy Ollama node available")
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "tools": tools,
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(f"{node.base_url}/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json().get("message", {})


async def chat(
    registry,
    user_message: str,
    history: Optional[list[dict]] = None,
    model: str = DEFAULT_MODEL,
    chat_fn: Optional[ChatFn] = None,
) -> dict:
    """Run one agent turn. Returns {reply, tool_trace, model}."""
    call = chat_fn or _default_chat
    tools_spec = build_tools(registry)
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in (history or [])[-10:]:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_message})

    trace: list[dict] = []
    for _ in range(MAX_ITERATIONS):
        message = await call(registry, model, messages, tools_spec)
        tool_calls = message.get("tool_calls") or []

        if not tool_calls:
            return {
                "reply": message.get("content") or "",
                "tool_trace": trace,
                "model": model,
            }

        messages.append({
            "role": "assistant",
            "content": message.get("content") or "",
            "tool_calls": tool_calls,
        })
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            result = await execute_tool(registry, name, args)
            trace.append({"tool": name, "arguments": args, "result": result})
            messages.append({
                "role": "tool",
                "content": json.dumps(result),
            })

    return {
        "reply": "Tool budget exhausted — here's what I found so far.",
        "tool_trace": trace,
        "model": model,
    }
