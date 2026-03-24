"""DHARMA COMMAND — Dashboard API.

FastAPI app with lifespan, CORS, WebSocket, and routers.

Usage:
    cd ~/dharma_swarm
    uvicorn api.main:app --port 8000 --reload
"""

from __future__ import annotations

import hmac
import logging
import os
import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)

# ── Singleton State ───────────────────────────────────────────────

_state: dict[str, Any] = {}
_OPERATOR_STATE_DIR = Path.home() / ".dharma"
_OPERATOR_PID_FILE = _OPERATOR_STATE_DIR / "operator.pid"


def _publish_operator_pid(pid: int | None = None) -> None:
    resolved_pid = pid or os.getpid()
    try:
        _OPERATOR_STATE_DIR.mkdir(parents=True, exist_ok=True)
        _OPERATOR_PID_FILE.write_text(f"{resolved_pid}\n", encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to write operator pid file: %s", exc)


def _clear_operator_pid(pid: int | None = None) -> None:
    resolved_pid = str(pid or os.getpid())
    try:
        current = _OPERATOR_PID_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return
    if current != resolved_pid:
        return
    try:
        _OPERATOR_PID_FILE.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Failed to clear operator pid file: %s", exc)


def get_swarm():
    """Get or create SwarmManager singleton."""
    if "swarm" not in _state:
        from dharma_swarm.swarm import SwarmManager
        _state["swarm"] = SwarmManager()
    return _state["swarm"]


def get_trace_store():
    """Get or create TraceStore singleton."""
    if "traces" not in _state:
        from dharma_swarm.traces import TraceStore
        _state["traces"] = TraceStore()
    return _state["traces"]


def get_monitor():
    """Get or create SystemMonitor singleton."""
    if "monitor" not in _state:
        from dharma_swarm.monitor import SystemMonitor
        _state["monitor"] = SystemMonitor(trace_store=get_trace_store())
    return _state["monitor"]


# ── Lifespan ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize subsystems on startup, cleanup on shutdown."""
    logger.info("DHARMA COMMAND API starting...")
    operator_pid = os.getpid()
    _publish_operator_pid(operator_pid)

    from dharma_swarm.ontology_runtime import get_shared_registry

    get_shared_registry()

    # Initialize trace store
    trace_store = get_trace_store()
    await trace_store.init()

    # Initialize swarm (connects to existing daemon state)
    swarm = get_swarm()
    swarm_init_task: asyncio.Task[None] | None = None
    try:
        init_timeout = float(os.getenv("DHARMA_SWARM_INIT_TIMEOUT_SECONDS", "3"))
        swarm_init_task = asyncio.create_task(swarm.init())
        _state["swarm_init_task"] = swarm_init_task
        await asyncio.wait_for(asyncio.shield(swarm_init_task), timeout=init_timeout)
        _state.pop("swarm_init_task", None)
    except TimeoutError:
        logger.warning(
            "Swarm init exceeded %.1fs; continuing API startup while warmup finishes in background",
            init_timeout,
        )
    except Exception as e:
        logger.warning("Swarm init partial: %s", e)

    logger.info("DHARMA COMMAND API ready on port 8420")
    try:
        yield
    finally:
        logger.info("DHARMA COMMAND API shutting down")
        pending_swarm_init = _state.pop("swarm_init_task", None)
        if pending_swarm_init is not None and not pending_swarm_init.done():
            pending_swarm_init.cancel()
            with suppress(asyncio.CancelledError):
                await pending_swarm_init
        _state.clear()
        _clear_operator_pid(operator_pid)


# ── Auth ──────────────────────────────────────────────────────────


def _get_api_key() -> str | None:
    """Read DASHBOARD_API_KEY from environment (per-request, supports rotation)."""
    return os.environ.get("DASHBOARD_API_KEY")


# Routes that never require authentication (method, path).
_PUBLIC_ROUTES: set[tuple[str, str]] = {
    ("GET", "/"),
    ("GET", "/api/health"),
    ("GET", "/api/verify/health"),
    ("GET", "/docs"),
    ("GET", "/openapi.json"),
    ("GET", "/redoc"),
    ("POST", "/api/verify/webhook"),
}

_AUTH_FAILURE_RESPONSE = {
    "error": "unauthorized",
    "detail": "Invalid or missing API key. Set DASHBOARD_API_KEY env var and pass as 'Bearer <key>' header.",
}


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Enforce Bearer token auth on /api/* routes.

    Skips auth entirely when DASHBOARD_API_KEY is not configured (dev mode).
    Skips auth for routes listed in _PUBLIC_ROUTES.
    Uses hmac.compare_digest for constant-time token comparison.
    """

    async def dispatch(self, request: Request, call_next):
        api_key = _get_api_key()

        # Dev mode: no key configured, everything open
        if api_key is None:
            return await call_next(request)

        path = request.url.path.rstrip("/") or "/"
        method = request.method.upper()

        # Public routes are always open
        if (method, path) in _PUBLIC_ROUTES:
            return await call_next(request)

        # Only gate /api/* routes
        needs_auth = path.startswith("/api")
        if not needs_auth:
            return await call_next(request)

        # Allow WebSocket upgrade requests with token in query params
        if request.headers.get("upgrade", "").lower() == "websocket":
            token = request.query_params.get("token", "")
            if token and hmac.compare_digest(token, api_key):
                return await call_next(request)
            return JSONResponse(status_code=401, content=_AUTH_FAILURE_RESPONSE)

        # Extract and validate Bearer token
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(status_code=401, content=_AUTH_FAILURE_RESPONSE)

        token = auth_header[7:]  # strip "Bearer "
        if not hmac.compare_digest(token, api_key):
            return JSONResponse(status_code=401, content=_AUTH_FAILURE_RESPONSE)

        return await call_next(request)


# ── App ───────────────────────────────────────────────────────────

app = FastAPI(
    title="DHARMA COMMAND",
    description="Neo-Tokyo Swarm Dashboard API",
    version="0.1.0",
    lifespan=lifespan,
)

# Auth middleware must be added BEFORE CORS so unauthenticated requests
# are rejected before CORS headers are applied.
app.add_middleware(BearerAuthMiddleware)

# CORS for Next.js dev server — explicit origins, not wildcard
_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "DASHBOARD_CORS_ORIGINS",
        "http://localhost:3000,http://localhost:3001,http://localhost:8420",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def _warn_if_no_api_key():
    if _get_api_key() is None:
        logger.warning(
            "⚠ DASHBOARD_API_KEY not set — ALL API routes are open (dev mode). "
            "Set DASHBOARD_API_KEY in environment to enable Bearer auth."
        )
    else:
        logger.info("Bearer token auth enabled for /api/* routes.")


# ── Register Routers ─────────────────────────────────────────────

from api.routers.health import router as health_router
from api.routers.agents import router as agents_router
from api.routers.evolution import router as evolution_router
from api.routers.ontology import router as ontology_router
from api.routers.lineage import router as lineage_router
from api.routers.stigmergy import router as stigmergy_router
from api.routers.commands import router as commands_router
from api.routers.chat import router as chat_router, ws_router as chat_ws_router
from api.routers.modules import router as modules_router
from api.routers.dashboard_new import router as dashboard_new_router
from api.routers.telemetry import router as telemetry_router
from api.routers.graphql_router import router as graphql_router
from api.routers.verify import router as verify_router

app.include_router(health_router)
app.include_router(agents_router)
app.include_router(evolution_router)
app.include_router(ontology_router)
app.include_router(lineage_router)
app.include_router(stigmergy_router)
app.include_router(commands_router)
app.include_router(chat_router)
app.include_router(chat_ws_router)
app.include_router(modules_router)
app.include_router(dashboard_new_router)
app.include_router(telemetry_router)
app.include_router(graphql_router)
app.include_router(verify_router)


# ── Root ──────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "name": "DHARMA COMMAND",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/api/health",
    }
