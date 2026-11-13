# ADR 0001 — Initial architecture

Date: 2026-11-13 (baseline recorded retroactively)
Status: accepted (describes what is built)

## Context

The platform orchestrates multiple Ollama workers across a LAN and must
serve both OpenAI-SDK clients and its own management UI.

## Decisions

1. **OpenAI-compatible `/v1/*` surface.** Clients use the stock OpenAI SDK
   with a custom `base_url`. Rationale: zero client work, ecosystem
   compatibility. Cost: wire format is constrained by the OpenAI schema.
2. **Custom `/api/*` for management.** Nodes, keys, rate limits, audit,
   fine-tune jobs are platform concepts with no OpenAI equivalent.
3. **Round-robin over a health-checked node pool.** `nodes.yaml` declares
   workers; a background loop marks nodes healthy/degraded. Rationale:
   KISS — no consistent-hashing or ML-based routing at this scale.
4. **SQLite for all gateway state.** Request log, audit, keys, rate-limit
   windows, job records in one file via aiosqlite. Rationale: zero ops,
   single-node gateway.
5. **Proxy + SSE relay, never local inference.** Workers run Ollama; the
   gateway forwards bytes. Keeps the gateway stateless-ish and lets
   heterogeneous OS workers participate.
6. **Fine-tune jobs as subprocesses.** Isolates long-running training from
   the async request path; job state tracked in SQLite.
7. **React + Vite + Tailwind admin UI.** Separate build, served statically;
   talks to `/api/*` only.

## Consequences

- Scaling beyond one gateway requires rethinking SQLite and in-process
  round-robin.
- API-key auth is a gateway concern; worker endpoints are trusted on the
  LAN (documented in README security notes).
