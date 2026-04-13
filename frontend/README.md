# ORCA Platform — React Frontend

A production-grade React + Tailwind CSS dashboard for the Ollama Platform Gateway.

## Stack

- **React 18** — component model, hooks
- **Vite 5** — build tool with HMR in dev
- **Tailwind CSS 3** — utility-first styling with custom design tokens
- **JetBrains Mono** — monospace UI font
- **DM Sans** — body font
- **Lucide React** — icon set

## Design system

Dark industrial theme built around a custom Tailwind config:

| Token | Value | Use |
|---|---|---|
| `bg-0..5` | `#07090b` → `#263340` | Background layers |
| `amber` | `#f0a030` | Primary accent, active states |
| `jade` | `#2fd87c` | Success, healthy nodes |
| `teal` | `#22d3c8` | Data values, throughput |
| `crimson` | `#f05c5c` | Errors, danger |
| `sky` | `#45a0e8` | Info, p50 latency |

## Development

```bash
cd frontend

# Install dependencies
npm install

# Start dev server (proxies /api and /v1 to localhost:8000)
npm run dev
# → http://localhost:5173/ui/
```

The `server.proxy` in `vite.config.js` forwards all `/api/*` and `/v1/*`
requests to the FastAPI gateway — no CORS issues, no separate config needed.

## Production build

```bash
cd frontend
npm run build
# → builds to ../app/static/react/
```

After building, the FastAPI gateway serves the React SPA at:
```
http://your-gateway:8000/ui/
```

The gateway handles all `/ui/*` routes as SPA fallback (returns `index.html`),
so React Router would work if added later.

## Project structure

```
frontend/
├── index.html
├── vite.config.js
├── tailwind.config.js
├── postcss.config.js
├── package.json
└── src/
    ├── main.jsx              # Entry point
    ├── App.jsx               # Shell: topbar, tabs, auth, toast
    ├── index.css             # Tailwind base + global styles
    ├── lib/
    │   ├── api.js            # API client + SSE streaming helper
    │   └── utils.js          # Formatting helpers
    ├── components/
    │   ├── ui.jsx            # Design system primitives
    │   └── NodeCard.jsx      # Reusable node status card
    └── pages/
        ├── Overview.jsx      # KPIs, node cards, charts
        ├── Nodes.jsx         # Full node grid + health check
        ├── Models.jsx        # Pull jobs, manifest sync, inventory
        ├── Metrics.jsx       # Latency percentiles, breakdowns
        ├── Keys.jsx          # API key management
        ├── RequestLog.jsx    # Paginated request log
        ├── Playground.jsx    # Streaming chat + live perf stats
        └── Benchmark.jsx     # Multi-model benchmark runner
```

## Pages

| Tab | Features |
|---|---|
| **Overview** | KPI cards (requests, error rate, p95, tokens), node health grid, model/node bar charts, hourly throughput chart |
| **Nodes** | Node cards with status, OS, version, last-seen, model chips, force health-check |
| **Models** | Pull form, node selector, manifest sync, live job progress bars with byte counters, model inventory |
| **Metrics** | p50/p95/p99 latency cards, by-model / by-node / by-key tables, hourly bar chart, configurable time window |
| **Keys** | Create with RPM limit, copy-once reveal, revoke / enable / delete per key |
| **Request Log** | Paginated table, filters: window, model, node, errors-only, pagination |
| **Playground** | Model selector, system prompt, parameter controls, streaming toggle, chat history, live TTFT / latency / tok/s stats |
| **Benchmark** | Multi-model runner, configurable runs+concurrency+temperature, live log, results table with p50/p95/tok/s, latency distribution bars, per-run detail drill-down |
