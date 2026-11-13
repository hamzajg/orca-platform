# AGENTS.md — orca-platform

Guidance for AI agents (and humans) working in this repository.

## Project

ORCA Platform Gateway: a multi-node Ollama orchestrator exposing an
OpenAI-compatible API (`/v1/*`) plus a custom management API (`/api/*`),
with round-robin load balancing, health monitoring, request logging, and a
fine-tuning job runner. Backend is FastAPI + SQLite; `frontend/` is a React +
Vite admin UI.
Stack: Python 3.13 (FastAPI, httpx, aiosqlite, pydantic), React 18 + Vite +
Tailwind for the UI.

## Commands

Verified 2026-11-13 against CI (`.github/workflows/ci.yml`) and local runs.

| Task | Command |
|---|---|
| Install deps (backend) | `pip install -r requirements-dev.txt` |
| Install deps (frontend) | `cd frontend && npm ci` |
| Test (backend) | `pytest` (14 tests, `pytest.ini` sets `asyncio_mode=auto`, `testpaths=tests`) |
| Build (frontend) | `cd frontend && npm run build` |
| Run (backend) | `uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| Run (frontend dev) | `cd frontend && npm run dev` |
| Run (all, docker) | `docker compose up -d` |

Requires: `.env` (copy `.env.example`; set `API_KEYS`), `nodes.yaml` with
real worker IPs, and Ollama running on each worker. `DATABASE_PATH` defaults
to `data/platform.db` (SQLite, auto-created).

## Architecture

- `app/main.py` — FastAPI entrypoint, lifespan wiring, router registration.
- `app/config.py` — settings from env (`pydantic-settings`) + `nodes.yaml` /
  `models.yaml` loaders.
- `app/db.py` — SQLite schema + async connection manager (aiosqlite).
- `app/middleware/` — `auth.py` (API-key dependency), `request_id.py`.
- `app/routers/` — `openai_compat.py` (`/v1/*`), `custom.py` (`/api/nodes`,
  `/api/models`, `/api/health`), `fine_tune.py`, `metrics.py`, `admin.py`,
  `models.py`, `ollama_compat.py`.
- `app/services/` — `node_registry`/discovery (node pool, health loop,
  round-robin), `proxy` (httpx + SSE relay to workers), `logger` /
  `audit_log` (SQLite request log), `key_store`, `metrics`, `fine_tuner`
  (background subprocess jobs).
- `frontend/` — React admin UI (Vite build; served separately or via
  `app/static` in docker).

### API contract (frontend ↔ backend ↔ workers)

Clients authenticate with `X-API-Key` or `Authorization: Bearer` against
`API_KEYS` / the key store. The gateway proxies to Ollama workers
(`http://<node>:11434`) using the same OpenAI wire format, so the contract is
the OpenAI API plus the custom endpoints below (full detail in README and
`app/routers/`):

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/v1/models` | key | Aggregated model list |
| POST | `/v1/chat/completions` | key | Chat (supports `stream: true` SSE) |
| POST | `/v1/embeddings` | key | Embeddings |
| GET | `/api/health` | none | Gateway health |
| GET/POST | `/api/nodes`, `/api/nodes/check` | key | Node pool status / force check |
| GET | `/api/models` | key | Model index |
| * | `/api/fine-tune/jobs*` | key | Fine-tune job CRUD + run/cancel |
| * | `/api/auth/keys*`, `/api/auth/audit` | key | Key management, rate limits, audit |

## Conventions

- Routers stay thin: validate via `app/schemas/` pydantic models, delegate to
  `app/services/`. Don't put proxy/DB logic in route handlers.
- Wire format for `/v1/*` must stay OpenAI-compatible — the OpenAI SDK is a
  supported client. Breaking the schema breaks clients.
- KISS/SOLID/DRY: simplest change matching existing patterns; no new
  frameworks. Python 3.13, pinned deps in `requirements.txt`.

## Landmines

- `API_KEYS` defaults to `change-me-key-1` — never ship that to a real deploy.
- Fine-tune jobs run as **background subprocesses** (`app/services/fine_tuner.py`);
  see `FINE_TUNE_PLAN.md` before touching that path.
- Health-check timing is env-tunable (`HEALTH_CHECK_*`); nodes flap to
  `degraded` after `HEALTH_CHECK_FAILURES` consecutive misses — don't "fix"
  that by removing the threshold.
- `pytest.ini` sets `pythonpath=.` — tests import `app` from repo root.

## Agent rules

- Branch from `main`; name branches `feat/*`, `fix/*`, `chore/*`, `docs/*`.
- Docs-only changes still go through a PR; never commit to `main` directly.
- Verify before claiming: run `pytest` and/or `cd frontend && npm run build`
  and report the real result. If you can't run it, say so.
- Keep changes minimal and consistent with surrounding code. No drive-by
  refactors.
- Update AGENTS.md / docs/ARCHITECTURE.md when your change alters commands,
  structure, or API contracts.
