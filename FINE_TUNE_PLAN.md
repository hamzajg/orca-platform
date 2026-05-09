# Fine-Tuning Capability — Implementation Plan

## Overview

Add model fine-tuning with job scheduling to the ORCA Platform Gateway.
Training runs as a local subprocess (configurable, default Docker + unsloth),
the gateway manages job lifecycle (queue → running → completed/failed),
and the fine-tuned model is automatically imported into Ollama.

---

## 1. Database Schema (`app/db.py`)

### `fine_tune_jobs` table

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | UUID |
| `name` | TEXT | Human-readable job name |
| `base_model` | TEXT | e.g. `llama3.2` |
| `method` | TEXT | `lora`, `qlora`, `full` |
| `dataset_source` | TEXT | File path or URL |
| `dataset_format` | TEXT | `alpaca`, `sharegpt`, `messages` |
| `hyperparameters` | TEXT | JSON |
| `output_model_name` | TEXT | Name for fine-tuned model in Ollama |
| `target_node_id` | TEXT | Ollama node to import into (NULL = first) |
| `status` | TEXT | `draft` → `scheduled` → `queued` → `running` → `completed` / `failed` |
| `progress` | REAL | 0–100 |
| `log` | TEXT | Accumulated stdout/stderr |
| `error` | TEXT | Error detail |
| `schedule_at` | TEXT | ISO datetime (NULL = immediate) |
| `started_at` | TEXT | ISO datetime |
| `finished_at` | TEXT | ISO datetime |
| `created_at` | TEXT | ISO datetime |
| `created_by` | TEXT | API key hint |

### `datasets` table

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | UUID |
| `name` | TEXT | Original filename |
| `path` | TEXT | Server path |
| `size` | INTEGER | Bytes |
| `created_at` | TEXT | ISO datetime |

---

## 2. Service Layer — `app/services/fine_tuner.py`

`FineTuneManager` class:

- `create_job(data)` → insert into DB, enqueue if immediate
- `get_jobs(status=None)` → list with optional status filter
- `get_job(id)` → single job detail
- `delete_job(id)` → remove from DB (only if not running)
- `cancel_job(id)` → kill subprocess, set status = `failed`
- `run_scheduler()` → background asyncio loop (every 15s)
- `_execute_job(job)` → run training subprocess:
  1. `status` → `running`
  2. Build command from template
  3. Run subprocess, stream output into `job.log`
  4. Parse progress from training output
  5. On completion, call `_import_to_ollama()`
  6. `status` → `completed` (or `failed`)
- `_import_to_ollama(job)` → build Modelfile, call `POST /api/create` on target node

### Default training command (configurable via `FINE_TUNE_COMMAND_TEMPLATE` env var)

```bash
docker run --gpus all \
  -v {dataset_dir}:{dataset_dir} \
  -v {output_dir}:{output_dir} \
  unsloth/unsloth:latest \
  python /app/train.py \
    --base_model {base_model} \
    --dataset {dataset_path} \
    --format {dataset_format} \
    --output {output_dir}/{job_id} \
    --method {method} \
    --hyperparameters '{hyperparameters_json}'
```

---

## 3. API Router — `app/routers/fine_tune.py`

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/fine-tune/jobs` | Create a fine-tuning job |
| `GET` | `/api/fine-tune/jobs` | List jobs (?status=running) |
| `GET` | `/api/fine-tune/jobs/{id}` | Single job detail |
| `DELETE` | `/api/fine-tune/jobs/{id}` | Delete/cancel a job |
| `POST` | `/api/fine-tune/jobs/{id}/cancel` | Cancel running job |
| `GET` | `/api/fine-tune/jobs/{id}/stream` | SSE log stream |
| `POST` | `/api/fine-tune/datasets` | Upload dataset file |
| `GET` | `/api/fine-tune/datasets` | List datasets |
| `DELETE` | `/api/fine-tune/datasets/{id}` | Delete dataset |

All endpoints use `dependencies=[Depends(require_api_key)]`.

---

## 4. File Storage

```
data/
  datasets/      ← uploaded training data
  fine-tuned/    ← training artifacts (GGUF, adapters)
```

Max upload: configurable (default 2GB).

---

## 5. Frontend — `frontend/src/pages/FineTune.jsx`

- **Create Job form**: name, base model (dropdown), method (radio), dataset (upload/URL), format (select), hyperparameters (epochs, lr, batch size, r, alpha), output model name, target node, schedule (now or datetime)
- **Job list**: table with status badges, progress bars, timestamps, expandable log viewer (SSE), cancel/delete actions

## 6. Frontend API — `frontend/src/lib/api.js`

Add wrappers:
- `createFineTuneJob(data)` · `getFineTuneJobs(filter)` · `getFineTuneJob(id)`
- `deleteFineTuneJob(id)` · `cancelFineTuneJob(id)` · `uploadDataset(file)` · `getDatasets()`
- `streamFineTuneLog(id, onChunk)` — SSE stream

## 7. Registration — `app/main.py`

- Import and register `fine_tune_router`
- Start `FineTuneManager.run_scheduler()` during lifespan startup
- Cancel scheduler during lifespan shutdown

## 8. Frontend Navigation — `frontend/src/App.jsx`

Add "Fine-tune" tab in sidebar navigation.

---

## 9. Files to Create/Modify

| Action | File |
|--------|------|
| CREATE | `app/services/fine_tuner.py` |
| CREATE | `app/routers/fine_tune.py` |
| CREATE | `app/schemas/fine_tune.py` |
| CREATE | `frontend/src/pages/FineTune.jsx` |
| MODIFY | `app/db.py` |
| MODIFY | `app/main.py` |
| MODIFY | `frontend/src/App.jsx` |
| MODIFY | `frontend/src/lib/api.js` |
