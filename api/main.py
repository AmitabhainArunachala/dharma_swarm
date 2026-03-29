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

from dharma_swarm.api_keys import DASHBOARD_API_KEY_ENV

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


def _log_auth_mode() -> None:
    if _get_api_key() is None:
        logger.warning(
            f"⚠ {DASHBOARD_API_KEY_ENV} not set — ALL API routes are open (dev mode). "
            f"Set {DASHBOARD_API_KEY_ENV} in environment to enable Bearer auth."
        )
    else:
        logger.info("Bearer token auth enabled for /api/* routes.")


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

    _log_auth_mode()
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
    return os.environ.get(DASHBOARD_API_KEY_ENV)


# Routes that never require authentication (method, path).
_PUBLIC_ROUTES: set[tuple[str, str]] = {
    ("GET", "/"),
    ("GET", "/health"),
    ("GET", "/api/health"),
    ("GET", "/api/verify/health"),
    ("GET", "/docs"),
    ("GET", "/openapi.json"),
    ("GET", "/redoc"),
    ("POST", "/api/verify/webhook"),
}

_AUTH_FAILURE_RESPONSE = {
    "error": "unauthorized",
    "detail": f"Invalid or missing API key. Set {DASHBOARD_API_KEY_ENV} env var and pass as 'Bearer <key>' header.",
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


# ── Register Routers ─────────────────────────────────────────────

def _register_routers(api_app: FastAPI) -> None:
    from api.routers.health import router as health_router
    from api.routers.agents import router as agents_router
    from api.routers.evolution import router as evolution_router
    from api.routers.ontology import router as ontology_router
    from api.routers.lineage import router as lineage_router
    from api.routers.stigmergy import router as stigmergy_router
    from api.routers.commands import router as commands_router
    from api.routers.modules import router as modules_router
    from api.routers.dashboard_new import router as dashboard_new_router
    from api.routers.telemetry import router as telemetry_router
    from api.routers.graphql_router import router as graphql_router
    from api.routers.verify import router as verify_router

    api_app.include_router(health_router)
    api_app.include_router(agents_router)
    api_app.include_router(evolution_router)
    api_app.include_router(ontology_router)
    api_app.include_router(lineage_router)
    api_app.include_router(stigmergy_router)
    api_app.include_router(commands_router)
    api_app.include_router(modules_router)
    api_app.include_router(dashboard_new_router)
    api_app.include_router(telemetry_router)
    api_app.include_router(graphql_router)
    api_app.include_router(verify_router)

    from api.routers.chat import router as chat_router, ws_router as chat_ws_router

    api_app.include_router(chat_router)
    api_app.include_router(chat_ws_router)


_register_routers(app)


# ── Root ──────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "name": "DHARMA COMMAND",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/api/health",
    }


# ── Process Supervision Health ────────────────────────────────────

@app.get("/health")
async def daemon_health():
    """Process supervision health — daemon PID, uptime, and last tick timestamp."""
    import json
    import time

    state_dir = Path.home() / ".dharma"
    pid_file = state_dir / "daemon.pid"
    health_file = state_dir / "stigmergy" / "dgc_health.json"

    daemon_pid: int | None = None
    pid_started_at: float | None = None
    try:
        daemon_pid = int(pid_file.read_text(encoding="utf-8").strip())
        pid_started_at = pid_file.stat().st_mtime
    except (OSError, ValueError):
        pass

    dgc_health: dict = {}
    try:
        dgc_health = json.loads(health_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass

    uptime_seconds: float | None = None
    if pid_started_at is not None:
        uptime_seconds = round(time.time() - pid_started_at, 1)

    return {
        "daemon_pid": daemon_pid,
        "uptime_seconds": uptime_seconds,
        "dgc_health_status": dgc_health.get("source", "unknown"),
        "last_tick": dgc_health.get("timestamp"),
        "agent_count": dgc_health.get("agent_count"),
        "task_count": dgc_health.get("task_count"),
    }
