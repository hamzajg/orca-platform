# ADR 0002 — In-gateway agent via Ollama-native tool calling

## Status

Accepted — implemented on `feat/agent-tools`.

## Context

The gateway already aggregates cluster state (nodes, models, metrics,
fine-tune jobs) behind `/api/*` and proxies chat to Ollama workers. An
operator asking "which node is degraded and why?" has to query several
endpoints manually. We wanted an agent surface without adding a vendor
SDK, a new datastore, or coupling to a specific model.

## Decision

`POST /api/agent/chat` runs a bounded tool-calling loop
(`app/services/agent.py`, max 5 iterations):

- The LLM is any Ollama worker reachable through `NodeRegistry`
  (round-robin, `get_next_node`), called via Ollama-native
  `/api/chat` with a `tools` array — no OpenAI translation layer.
- Tools are **read-only** gateway views (`list_nodes`, `list_models`,
  `get_metrics`, `list_fine_tune_jobs`) implemented in-process over the
  same services the REST routers use. No tool mutates cluster state.
- Tool failures return `{ok: false, error}` to the model — the loop
  never crashes the request; backend errors map to 502/503.
- History is capped at 10 prior messages; reply includes a
  `tool_trace` for observability.

## Consequences

- Zero new dependencies; works with whatever model the cluster serves.
- Read-only by design: write tools (add/remove node, trigger fine-tune)
  need a human-confirmation protocol first — deliberately deferred.
- No conversation persistence yet — each call is stateless apart from
  client-supplied `history`. If persistence is needed, add a table in
  `app/db.py` mirroring the REST audit pattern.
- The loop is intentionally simple; if multi-agent or streaming is
  needed later, the seam is `agent_svc.chat` — swap the backend, keep
  the tools.
