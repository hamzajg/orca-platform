"""
main.py — ORCA Platform Gateway entrypoint.

Startup sequence:
  1. Ensure data/ directory and SQLite schema exist
  2. Load NodeRegistry from nodes.yaml → persist to DB
  3. Fire first health check immediately (don't wait for the first interval)
  4. Start background health-check loop
  5. Start ModelManager — sync model inventory
  6. Metrics router active — queries requests table on demand

Shutdown sequence:
  1. Cancel health-check loop
  2. Close shared httpx client
  3. aiosqlite connections close themselves via context managers

Run with:
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import init_db
from app.middleware.request_id import RequestIDMiddleware
from app.routers.admin import router as admin_router
from app.routers.ollama_compat import router as ollama_router
from app.routers.metrics import router as metrics_router
from app.routers.models import router as models_router
from app.routers.custom import router as custom_router
from app.routers.openai_compat import router as openai_router
from app.services.key_store import KeyStore
from app.services.model_manager import ModelManager
from app.services.node_registry import NodeRegistry
from app.services.proxy import close_http_client
from app.services.rate_limiter import RateLimiter

# ── Logging ───────────────────────────────────────────────────────────────────

settings = get_settings()

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    logger.info("━━━ ORCA Platform Gateway starting ━━━")

    # 1. Database
    await init_db()

    # 2. Auth — KeyStore + RateLimiter
    key_store = KeyStore()
    app.state.key_store = key_store
    app.state.rate_limiter = RateLimiter()
    await key_store.startup(bootstrap_keys=settings.api_key_set)

    # 3. Node registry
    registry = NodeRegistry()
    app.state.registry = registry
    await registry.startup()

    # 4. First health check immediately (don't wait for first interval)
    logger.info("Running initial health check on all nodes…")
    await registry.trigger_immediate_check()

    # 5. Model manager — sync model inventory from registry
    model_manager = ModelManager()
    app.state.model_manager = model_manager
    await model_manager.startup(registry)

    healthy = registry.get_healthy_count()
    total   = len(registry.get_all_nodes())
    logger.info("━━━ Gateway ready — %d/%d nodes healthy ━━━", healthy, total)

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("Shutting down gateway…")
    await registry.shutdown()
    await close_http_client()
    logger.info("Gateway stopped.")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="ORCA Platform Gateway",
    description=(
        "Multi-node Ollama orchestrator with OpenAI-compatible API and "
        "custom cluster management endpoints."
    ),
    version="0.7.1",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Permissive defaults for local/trusted-network use.
# Tighten allow_origins when you expose this externally.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request ID (must be added before routers) ────────────────────────────────
app.add_middleware(RequestIDMiddleware)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(ollama_router)   # /api/version, /api/tags, /api/chat, /api/generate …
app.include_router(openai_router)   # /v1/*
app.include_router(admin_router)    # /api/auth/*
app.include_router(models_router)   # /api/models/*
app.include_router(metrics_router)  # /api/metrics/*
app.include_router(custom_router)   # /api/*


# ── Static files ─────────────────────────────────────────────────────────────
from pathlib import Path as _Path

# React SPA build output (npm run build → app/static/react/)
_react_dir = _Path(__file__).parent / "static" / "react"
# Legacy HTML dashboard (kept for fallback)
_static_dir = _Path(__file__).parent / "static"

if _react_dir.exists():
    # Serve the built React app at /ui/
    app.mount("/ui/assets", StaticFiles(directory=str(_react_dir / "assets")), name="react-assets")

    @app.get("/ui", include_in_schema=False)
    @app.get("/ui/{path:path}", include_in_schema=False)
    async def react_spa(path: str = ""):
        index = _react_dir / "index.html"
        return FileResponse(str(index))

    # Redirect root to React UI
    @app.get("/dashboard", include_in_schema=False)
    async def dashboard_redirect():
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/ui")

elif _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

    @app.get("/dashboard", include_in_schema=False)
    async def dashboard():
        return FileResponse(str(_static_dir / "dashboard.html"))


# ── Global exception handler ──────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error.", "type": type(exc).__name__},
    )


# ── Root redirect ─────────────────────────────────────────────────────────────

@app.get("/api/info", include_in_schema=False)
async def gateway_info():
    """Gateway metadata endpoint — does not conflict with Ollama's GET / health check."""
    return {
        "name": "ORAC Platform Gateway",
        "version": "0.7.0",
        "docs": "/docs",
        "health": "/api/health",
        "ui": "/ui",
        "dashboard_legacy": "/dashboard",
    }
