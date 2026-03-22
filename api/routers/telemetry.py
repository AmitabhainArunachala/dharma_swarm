"""Telemetry endpoints over the canonical company-state plane."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from fastapi import APIRouter, Query

from api.models import ApiResponse

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])

_telemetry_store = None
_telemetry_views = None
_telemetry_optimizer = None
_runtime_projector = None
_projection_lock: asyncio.Lock | None = None
_last_projection_at = 0.0


def _get_telemetry_store():
    """Lazy-load a telemetry store bound to the canonical runtime DB."""
    global _telemetry_store
    if _telemetry_store is None:
        from dharma_swarm.telemetry_plane import TelemetryPlaneStore

        db_path_raw = os.getenv("DHARMA_RUNTIME_DB", "").strip()
        db_path = Path(db_path_raw) if db_path_raw else None
        _telemetry_store = TelemetryPlaneStore(db_path)
    return _telemetry_store


def _get_telemetry_views():
    """Lazy-load telemetry read models."""
    global _telemetry_views
    if _telemetry_views is None:
        from dharma_swarm.telemetry_views import TelemetryViews

        _telemetry_views = TelemetryViews(_get_telemetry_store())
    return _telemetry_views


def _get_telemetry_optimizer():
    """Lazy-load telemetry optimization services."""
    global _telemetry_optimizer
    if _telemetry_optimizer is None:
        from dharma_swarm.telemetry_optimizer import TelemetryOptimizer

        _telemetry_optimizer = TelemetryOptimizer(_get_telemetry_store())
    return _telemetry_optimizer


def _get_runtime_projector():
    global _runtime_projector
    if _runtime_projector is None:
        from dharma_swarm.runtime_state import RuntimeStateStore
        from dharma_swarm.runtime_telemetry_projector import RuntimeTelemetryProjector

        store = _get_telemetry_store()
        _runtime_projector = RuntimeTelemetryProjector(
            runtime_state=RuntimeStateStore(store.db_path),
            telemetry=store,
        )
    return _runtime_projector


async def _project_runtime_telemetry_if_stale(*, force: bool = False):
    global _projection_lock, _last_projection_at
    ttl_seconds = float(os.getenv("DHARMA_TELEMETRY_PROJECT_TTL_SECONDS", "10"))
    now = time.monotonic()
    if not force and (now - _last_projection_at) < ttl_seconds:
        return {"status": "fresh", "projected": False}
    if _projection_lock is None:
        _projection_lock = asyncio.Lock()
    async with _projection_lock:
        now = time.monotonic()
        if not force and (now - _last_projection_at) < ttl_seconds:
            return {"status": "fresh", "projected": False}
        projector = _get_runtime_projector()
        summary = await projector.project_recent()
        _last_projection_at = time.monotonic()
        return {"status": "projected", "projected": True, "summary": summary}


def _as_dict(value):
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return value


@router.get("/overview")
async def telemetry_overview() -> ApiResponse:
    await _project_runtime_telemetry_if_stale()
    views = _get_telemetry_views()
    overview = await views.overview()
    return ApiResponse(data=_as_dict(overview))


@router.get("/routing")
async def telemetry_routing_summary() -> ApiResponse:
    await _project_runtime_telemetry_if_stale()
    views = _get_telemetry_views()
    summary = await views.routing_summary()
    return ApiResponse(data=_as_dict(summary))


@router.get("/economics")
async def telemetry_economic_summary() -> ApiResponse:
    await _project_runtime_telemetry_if_stale()
    views = _get_telemetry_views()
    summary = await views.economic_summary()
    return ApiResponse(data=_as_dict(summary))


@router.get("/agents")
async def telemetry_agents(
    status: str | None = Query(None, description="Filter by agent status"),
    limit: int = Query(50, ge=1, le=500, description="Maximum agents to return"),
) -> ApiResponse:
    await _project_runtime_telemetry_if_stale()
    store = _get_telemetry_store()
    records = await store.list_agent_identities(status=status, limit=limit)
    return ApiResponse(data=[_as_dict(item) for item in records])


@router.get("/teams")
async def telemetry_teams(
    team_id: str | None = Query(None, description="Filter by team ID"),
    agent_id: str | None = Query(None, description="Filter by agent ID"),
    active_only: bool = Query(True, description="Only return active roster entries"),
    limit: int = Query(50, ge=1, le=500, description="Maximum records to return"),
) -> ApiResponse:
    await _project_runtime_telemetry_if_stale()
    store = _get_telemetry_store()
    records = await store.list_team_roster(
        team_id=team_id,
        agent_id=agent_id,
        active_only=active_only,
        limit=limit,
    )
    return ApiResponse(data=[_as_dict(item) for item in records])


@router.get("/routes")
async def telemetry_routes(
    task_id: str | None = Query(None, description="Filter by task ID"),
    run_id: str | None = Query(None, description="Filter by run ID"),
    limit: int = Query(50, ge=1, le=500, description="Maximum records to return"),
) -> ApiResponse:
    await _project_runtime_telemetry_if_stale()
    store = _get_telemetry_store()
    records = await store.list_routing_decisions(task_id=task_id, run_id=run_id, limit=limit)
    return ApiResponse(data=[_as_dict(item) for item in records])


@router.get("/policies")
async def telemetry_policies(
    task_id: str | None = Query(None, description="Filter by task ID"),
    policy_name: str | None = Query(None, description="Filter by policy name"),
    limit: int = Query(50, ge=1, le=500, description="Maximum records to return"),
) -> ApiResponse:
    await _project_runtime_telemetry_if_stale()
    store = _get_telemetry_store()
    records = await store.list_policy_decisions(task_id=task_id, policy_name=policy_name, limit=limit)
    return ApiResponse(data=[_as_dict(item) for item in records])


@router.get("/interventions")
async def telemetry_interventions(
    task_id: str | None = Query(None, description="Filter by task ID"),
    operator_id: str | None = Query(None, description="Filter by operator ID"),
    limit: int = Query(50, ge=1, le=500, description="Maximum records to return"),
) -> ApiResponse:
    await _project_runtime_telemetry_if_stale()
    store = _get_telemetry_store()
    records = await store.list_intervention_outcomes(
        task_id=task_id,
        operator_id=operator_id,
        limit=limit,
    )
    return ApiResponse(data=[_as_dict(item) for item in records])


@router.get("/events/economic")
async def telemetry_economic_events(
    event_kind: str | None = Query(None, description="Filter by event kind"),
    session_id: str | None = Query(None, description="Filter by session ID"),
    limit: int = Query(50, ge=1, le=500, description="Maximum records to return"),
) -> ApiResponse:
    await _project_runtime_telemetry_if_stale()
    store = _get_telemetry_store()
    records = await store.list_economic_events(
        event_kind=event_kind,
        session_id=session_id,
        limit=limit,
    )
    return ApiResponse(data=[_as_dict(item) for item in records])


@router.get("/outcomes")
async def telemetry_outcomes(
    outcome_kind: str | None = Query(None, description="Filter by outcome kind"),
    session_id: str | None = Query(None, description="Filter by session ID"),
    limit: int = Query(50, ge=1, le=500, description="Maximum records to return"),
) -> ApiResponse:
    await _project_runtime_telemetry_if_stale()
    store = _get_telemetry_store()
    records = await store.list_external_outcomes(
        outcome_kind=outcome_kind,
        session_id=session_id,
        limit=limit,
    )
    return ApiResponse(data=[_as_dict(item) for item in records])


@router.get("/optimization/providers")
async def telemetry_provider_optimization(
    limit: int = Query(8, ge=1, le=100, description="Maximum provider recommendations to return"),
) -> ApiResponse:
    await _project_runtime_telemetry_if_stale()
    optimizer = _get_telemetry_optimizer()
    records = await optimizer.provider_recommendations(limit=limit)
    return ApiResponse(data=[_as_dict(item) for item in records])


@router.get("/optimization/donors")
async def telemetry_donor_targets(
    limit: int | None = Query(None, ge=1, le=100, description="Maximum donor targets to return"),
    priority: int | None = Query(None, ge=1, le=5, description="Filter donor targets by priority"),
) -> ApiResponse:
    optimizer = _get_telemetry_optimizer()
    records = optimizer.donor_targets(limit=limit, priority=priority)
    return ApiResponse(data=[_as_dict(item) for item in records])


@router.post("/project")
async def telemetry_project_runtime(force: bool = Query(True, description="Force a runtime-to-telemetry projection")) -> ApiResponse:
    result = await _project_runtime_telemetry_if_stale(force=force)
    return ApiResponse(data=result)
