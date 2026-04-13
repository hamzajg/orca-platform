# ORCA Platform Gateway

A multi-node Ollama orchestrator with an OpenAI-compatible API surface, round-robin load balancing, health monitoring, and request logging.

## Architecture

```
Clients (OpenAI SDK / curl)
        │
        ▼  (X-API-Key or Authorization: Bearer)
┌─────────────────────────────┐
│   Gateway — root Linux      │  FastAPI · port 8000
│  ┌────────────────────────┐ │
│  │  Auth middleware        │ │
│  │  Round-robin router     │ │
│  │  OpenAI-compat /v1/*   │ │
│  │  Custom API  /api/*    │ │
│  │  Async proxy + SSE     │ │
│  │  SQLite logger          │ │
│  └────────────────────────┘ │
└──────┬────────┬─────────────┘
       │        │ httpx (LAN)
   ┌───▼──┐ ┌──▼───┐ ┌────────┐
   │Linux │ │ Win  │ │ macOS  │
   │11434 │ │11434 │ │ 11434  │
   └──────┘ └──────┘ └────────┘
```

## Quick Start

### 1. Configure nodes

Edit `nodes.yaml` with the real LAN IPs of your three worker machines:

```yaml
nodes:
  - id: worker-linux
    host: 192.168.1.101   # ← your actual IP
    port: 11434
    os: linux
```

### 2. Set your API key

```bash
# Generate a strong key
python -c "import secrets; print(secrets.token_hex(32))"

# Edit .env
API_KEYS=your-generated-key-here
```

### 3. Make sure Ollama is running on each worker

```bash
# On each worker machine
ollama serve
```

### 4. Run the gateway

**Option A — Direct (development)**
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Option B — Docker**
```bash
docker compose up -d
docker compose logs -f
```

---

## API Reference

### OpenAI-compatible (`/v1/`)

All endpoints accept `X-API-Key: <key>` or `Authorization: Bearer <key>`.

#### List models
```bash
curl http://localhost:8000/v1/models \
  -H "X-API-Key: your-key"
```

#### Chat completion
```bash
curl http://localhost:8000/v1/chat/completions \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3.2",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

#### Streaming chat
```bash
curl http://localhost:8000/v1/chat/completions \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "llama3.2", "messages": [{"role":"user","content":"Count to 5"}], "stream": true}'
```

#### Use with the OpenAI Python SDK
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://your-gateway-ip:8000/v1",
    api_key="your-key",
)

response = client.chat.completions.create(
    model="llama3.2",
    messages=[{"role": "user", "content": "What is the capital of France?"}],
)
print(response.choices[0].message.content)
```

#### Embeddings
```bash
curl http://localhost:8000/v1/embeddings \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "nomic-embed-text", "input": "Hello world"}'
```

### Custom platform API (`/api/`)

#### Gateway health (public, no key needed)
```bash
curl http://localhost:8000/api/health
```

#### List all nodes with status
```bash
curl http://localhost:8000/api/nodes \
  -H "X-API-Key: your-key"
```

#### Get a specific node
```bash
curl http://localhost:8000/api/nodes/worker-linux \
  -H "X-API-Key: your-key"
```

#### Force immediate health check
```bash
curl -X POST http://localhost:8000/api/nodes/check \
  -H "X-API-Key: your-key"
```

#### Aggregated model index
```bash
curl http://localhost:8000/api/models \
  -H "X-API-Key: your-key"
```

---

## Project Structure

```
orca-platform/
├── app/
│   ├── main.py                  # FastAPI entrypoint, lifespan
│   ├── config.py                # Settings (env + YAML loaders)
│   ├── db.py                    # SQLite schema, async connection manager
│   ├── middleware/
│   │   └── auth.py              # API key validation dependency
│   ├── routers/
│   │   ├── openai_compat.py     # /v1/models, /v1/chat/completions, etc.
│   │   └── custom.py            # /api/nodes, /api/models, /api/health
│   ├── schemas/
│   │   ├── openai.py            # Pydantic models — OpenAI wire format
│   │   └── custom.py            # Pydantic models — custom endpoints
│   └── services/
│       ├── node_registry.py     # Node pool, health loop, round-robin
│       ├── proxy.py             # httpx proxy + SSE stream relay
│       └── logger.py            # Fire-and-forget SQLite request logger
├── nodes.yaml                   # Worker node definitions
├── models.yaml                  # Model manifest (used in Phase 4 sync)
├── .env                         # Environment config
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `API_KEYS` | `change-me-key-1` | Comma-separated list of valid API keys |
| `GATEWAY_HOST` | `0.0.0.0` | Bind address |
| `GATEWAY_PORT` | `8000` | Listen port |
| `LOG_LEVEL` | `info` | `debug` / `info` / `warning` |
| `HEALTH_CHECK_INTERVAL` | `15` | Seconds between node health checks |
| `HEALTH_CHECK_FAILURES` | `2` | Consecutive failures before marking degraded |
| `HEALTH_CHECK_TIMEOUT` | `5` | Per-request timeout for health checks |
| `DATABASE_PATH` | `data/platform.db` | SQLite file path |
| `NODES_CONFIG` | `nodes.yaml` | Path to nodes config |
| `MODELS_CONFIG` | `models.yaml` | Path to models manifest |

## Phase 3 — Auth & Rate Limiting

### Key management endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/auth/keys` | List all keys (no secret values) |
| POST | `/api/auth/keys` | Create new key (secret returned once) |
| DELETE | `/api/auth/keys/{name}` | Permanently delete a key |
| POST | `/api/auth/keys/{name}/revoke` | Disable a key |
| POST | `/api/auth/keys/{name}/enable` | Re-enable a key |
| PATCH | `/api/auth/keys/{name}/rate-limit` | Set RPM limit |
| POST | `/api/auth/keys/{name}/reset-limit` | Clear sliding window |
| GET | `/api/auth/audit` | View audit log |

### Create a named key with a rate limit
```bash
curl -X POST http://localhost:8000/api/auth/keys \
  -H "X-API-Key: your-bootstrap-key" \
  -H "Content-Type: application/json" \
  -d '{"name": "prod-app", "rate_limit_rpm": 120}'
# → returns the full key value ONCE — save it immediately
```

### Revoke a key
```bash
curl -X POST http://localhost:8000/api/auth/keys/prod-app/revoke \
  -H "X-API-Key: your-bootstrap-key"
```

### View audit log
```bash
curl "http://localhost:8000/api/auth/audit?limit=20&event_type=auth_fail" \
  -H "X-API-Key: your-bootstrap-key"
```

### Audit event types
| Event | Meaning |
|---|---|
| `auth_ok` | Successful authentication |
| `auth_fail` | Unknown or missing key |
| `auth_revoked` | Key found but disabled |
| `rate_limit_hit` | Request rejected by rate limiter |
| `key_created` | New key created |
| `key_revoked` | Key disabled |
| `key_deleted` | Key permanently removed |
| `key_enabled` | Disabled key re-enabled |
| `rate_limit_changed` | RPM limit updated |

### Request tracing
Every response now carries `X-Request-ID`. Supply your own to correlate
your client logs with gateway logs:
```bash
curl http://localhost:8000/v1/chat/completions \
  -H "X-API-Key: your-key" \
  -H "X-Request-ID: my-trace-123" \
  ...
# Response will echo: X-Request-ID: my-trace-123
```

## Phase 4 — Model Manager

### Model management endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/models` | Cluster model index |
| GET | `/api/models/manifest` | Show models.yaml contents |
| POST | `/api/models/sync` | Reconcile manifest vs nodes; enqueue pulls |
| POST | `/api/models/pull` | Pull a model on one or all nodes |
| GET | `/api/models/jobs` | List all pull jobs |
| GET | `/api/models/jobs/{id}` | Single job status |
| DELETE | `/api/models/jobs/{id}` | Remove finished job |
| GET | `/api/models/jobs/{id}/stream` | SSE live pull progress |
| DELETE | `/api/models/{model}/nodes/{node_id}` | Remove model from node |

### Pull a model on all nodes
```bash
curl -X POST http://localhost:8000/api/models/pull \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "llama3.2"}'
# → returns job IDs immediately; pull runs in background
```

### Pull on a specific node only
```bash
curl -X POST http://localhost:8000/api/models/pull \
  -H "X-API-Key: your-key" \
  -d '{"model": "codellama", "node_ids": ["worker-linux"]}'
```

### Stream live pull progress
```bash
curl -N http://localhost:8000/api/models/jobs/{job_id}/stream \
  -H "X-API-Key: your-key"
# → SSE stream:
# data: {"job_id":"abc123","status":"pulling","progress_pct":34.2,...}
# data: {"job_id":"abc123","status":"done","progress_pct":100.0,...}
# data: [DONE]
```

### Sync entire manifest
```bash
curl -X POST http://localhost:8000/api/models/sync \
  -H "X-API-Key: your-key"
# → compares models.yaml against all nodes, pulls anything missing
```

### Delete a model from a node
```bash
curl -X DELETE http://localhost:8000/api/models/mistral/nodes/worker-macos \
  -H "X-API-Key: your-key"
```

## Phase 5 — Metrics & Observability

### Metrics endpoints

All accept `?window=1h|6h|24h|7d|30d|all` (default: `24h`).

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/metrics` | Full bundle — all views in one call |
| GET | `/api/metrics/overview` | KPIs: request count, error rate, latency p50/p95/p99, token throughput |
| GET | `/api/metrics/by-model` | Stats per model |
| GET | `/api/metrics/by-node` | Stats per worker node |
| GET | `/api/metrics/by-key` | Stats per API key (hint only) |
| GET | `/api/metrics/by-endpoint` | Stats per endpoint path |
| GET | `/api/metrics/by-hour` | Hourly time-series for charting |
| GET | `/api/metrics/requests` | Paginated raw request log |
| DELETE | `/api/metrics/requests` | Purge old request rows |

### Usage examples

```bash
# Full bundle — last 24h
curl http://localhost:8000/api/metrics \
  -H "X-API-Key: your-key"

# KPIs for the last hour
curl "http://localhost:8000/api/metrics/overview?window=1h" \
  -H "X-API-Key: your-key"
# → {
#     "total_requests": 142,
#     "error_rate_pct": 1.4,
#     "latency_ms": { "p50": 312.4, "p95": 891.2, "p99": 1204.5 },
#     "tokens": { "total": 84210, "per_second": 23.4 }
#   }

# Last 7 days breakdown by model
curl "http://localhost:8000/api/metrics/by-model?window=7d" \
  -H "X-API-Key: your-key"

# Node comparison — who's fastest?
curl "http://localhost:8000/api/metrics/by-node?window=7d" \
  -H "X-API-Key: your-key"

# Per-key usage (who's using the most tokens?)
curl "http://localhost:8000/api/metrics/by-key?window=30d" \
  -H "X-API-Key: your-key"

# Hourly time-series for the last 24h (pipe into a chart)
curl "http://localhost:8000/api/metrics/by-hour?window=24h" \
  -H "X-API-Key: your-key"

# Last 50 errors only
curl "http://localhost:8000/api/metrics/requests?errors_only=true&limit=50" \
  -H "X-API-Key: your-key"

# Purge rows older than 30 days
curl -X DELETE "http://localhost:8000/api/metrics/requests?older_than=30d" \
  -H "X-API-Key: your-key"
```

### Health endpoint now includes metrics snapshot

`GET /api/health` (public, no auth) now returns a live 1-hour snapshot:
```json
{
  "status": "ok",
  "nodes": { "total": 3, "healthy": 3 },
  "metrics": {
    "requests_1h": 87,
    "errors_1h": 0,
    "avg_latency_ms": 345.2,
    "p95_latency_ms": 812.4,
    "tokens_1h": 51200
  }
}
```

## Phase 6 — Frontend Dashboard

The dashboard is a single-page app served directly by the gateway at `/dashboard`.
No separate build step, no Node.js, no dependencies — just open it in a browser.

### Access

```
http://your-gateway-ip:8000/dashboard
```

### Features

| Tab | What you see |
|---|---|
| **Overview** | KPI cards (requests, error rate, p95 latency, tokens), node health cards, model/node bar charts, hourly throughput chart |
| **Nodes** | Detailed node cards with OS, Ollama version, last-seen time, pulled model chips, force health-check button |
| **Models** | Pull model form, manifest sync button, live pull-job progress bars, full model inventory table |
| **Metrics** | Latency p50/p95/p99 cards, breakdown tables by model / node / key, hourly bar chart — all with configurable time window |
| **Keys** | Create named keys with RPM limits, revoke/enable/delete, copy-once key display |
| **Request Log** | Paginated raw request log with filters: model, node, errors-only, time window |

### Authentication

Paste your API key into the top-right field and click **CONNECT**. The key is
stored in `sessionStorage` for the browser session only.

## Complete file structure

```
ollama-platform/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── db.py
│   ├── middleware/
│   │   ├── auth.py
│   │   └── request_id.py
│   ├── routers/
│   │   ├── openai_compat.py   /v1/*
│   │   ├── admin.py           /api/auth/*
│   │   ├── custom.py          /api/health, /api/nodes
│   │   ├── models.py          /api/models/*
│   │   └── metrics.py         /api/metrics/*
│   ├── schemas/
│   │   ├── openai.py
│   │   └── custom.py
│   ├── services/
│   │   ├── node_registry.py
│   │   ├── proxy.py
│   │   ├── model_manager.py
│   │   ├── key_store.py
│   │   ├── rate_limiter.py
│   │   ├── metrics.py
│   │   ├── logger.py
│   │   └── audit_log.py
│   └── static/
│       └── dashboard.html     ← the full dashboard
├── nodes.yaml
├── models.yaml
├── .env
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```
