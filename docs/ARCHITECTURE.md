# Architecture — orca-platform

Current-state map. Descriptive, not aspirational; see `docs/adr/` for why.

## System shape

```
OpenAI SDK / curl / React UI
        │  X-API-Key or Bearer
        ▼
FastAPI gateway (app/main.py, :8000)
  ├─ middleware/auth.py      API-key check (env API_KEYS + SQLite key store)
  ├─ middleware/request_id   request correlation
  ├─ routers/openai_compat   /v1/models, /v1/chat/completions, /v1/embeddings
  ├─ routers/custom          /api/nodes, /api/models, /api/health
  ├─ routers/fine_tune       /api/fine-tune/jobs* (background subprocesses)
  ├─ routers/admin, metrics, models, ollama_compat
  └─ services/
       ├─ discovery / node pool   nodes.yaml → registry, health loop, round-robin
       ├─ proxy                   httpx async forward + SSE relay to workers
       ├─ logger / audit_log      fire-and-forget SQLite (aiosqlite)
       ├─ key_store               named keys, rate limits (sliding window)
       └─ fine_tuner              spawns fine-tuning subprocesses per job
        │  httpx, LAN
        ▼
Ollama workers :11434 (linux / windows / macOS nodes from nodes.yaml)
```

## Data stores

- **SQLite** (`DATABASE_PATH`, default `data/platform.db`): request log,
  audit log, named API keys, rate-limit windows, fine-tune job records.
  Schema created in `app/db.py` at startup.
- **YAML config**: `nodes.yaml` (worker pool), `models.yaml` (model
  manifest, Phase 4 sync).
- **No other persistence.** Workers hold model weights; the gateway holds
  only metadata.

## Request flow (chat completion)

1. `middleware/auth.py` validates key → attaches key context.
2. `routers/openai_compat.py` parses body into `app/schemas/openai.py`
   models (OpenAI wire format preserved).
3. Service picks a healthy node (round-robin over registry; degraded nodes
   skipped).
4. `services/proxy` forwards via httpx; for `stream: true` it relays SSE
   chunks back without buffering.
5. `services/logger` writes the request record asynchronously
   (fire-and-forget — logging must never block or fail the request).

## Frontend (`frontend/`)

React 18 + Vite + Tailwind admin UI. Calls the same `/api/*` endpoints with
a user-supplied key. Built output can be served via `app/static` in the
Docker image; in dev it runs on the Vite dev server.

## Key decisions (see docs/adr/)

- OpenAI-compatible surface rather than a bespoke API — any OpenAI SDK
  client works unchanged.
- SQLite for all gateway state — single-file, zero infra, sufficient at
  this scale.
- Proxy-and-relay (no inference in-process) — workers own the models.
