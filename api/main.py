"""DHARMA COMMAND — Dashboard API.

FastAPI app with lifespan, CORS, WebSocket, and routers.

Usage:
    cd ~/dharma_swarm
    uvicorn api.main:app --port 8000 --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

# ── Singleton State ───────────────────────────────────────────────

_state: dict[str, Any] = {}


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

    # Initialize trace store
    trace_store = get_trace_store()
    await trace_store.init()

    # Initialize swarm (connects to existing daemon state)
    swarm = get_swarm()
    try:
        await swarm.init()
    except Exception as e:
        logger.warning("Swarm init partial: %s", e)

    logger.info("DHARMA COMMAND API ready on port 8000")
    yield

    logger.info("DHARMA COMMAND API shutting down")
    _state.clear()


# ── App ───────────────────────────────────────────────────────────

app = FastAPI(
    title="DHARMA COMMAND",
    description="Neo-Tokyo Swarm Dashboard API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for Next.js dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register Routers ─────────────────────────────────────────────

from api.routers.health import router as health_router
from api.routers.agents import router as agents_router
from api.routers.evolution import router as evolution_router
from api.routers.ontology import router as ontology_router
from api.routers.lineage import router as lineage_router
from api.routers.stigmergy import router as stigmergy_router
from api.routers.commands import router as commands_router
from api.routers.chat import router as chat_router
from api.routers.modules import router as modules_router
from api.routers.dashboard_new import router as dashboard_new_router

app.include_router(health_router)
app.include_router(agents_router)
app.include_router(evolution_router)
app.include_router(ontology_router)
app.include_router(lineage_router)
app.include_router(stigmergy_router)
app.include_router(commands_router)
app.include_router(chat_router)
app.include_router(modules_router)
app.include_router(dashboard_new_router)


# ── Root ──────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "name": "DHARMA COMMAND",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/api/health",
    }
