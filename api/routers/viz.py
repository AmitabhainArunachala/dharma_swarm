"""Visualization endpoints — serves the unified data plane.

All visualization lenses (operator nervous system, temporal playback,
future cosmos/orchestra) consume from these endpoints. The VizProjector
composes data from telemetry, stigmergy, trajectories, and economics
into normalized GraphSnapshot/GraphEvent contracts.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Query

from api.models import ApiResponse

router = APIRouter(prefix="/api/viz", tags=["visualization"])

_projector = None


def _get_projector():
    """Lazy-load the VizProjector."""
    global _projector
    if _projector is None:
        from dharma_swarm.viz_projection import VizProjector
        _projector = VizProjector()
    return _projector


@router.get("/snapshot")
async def get_snapshot(
    max_nodes: int = Query(200, ge=10, le=1000),
) -> ApiResponse:
    """Current system state as a renderable graph snapshot.

    Returns nodes (agents, subsystems), edges (data flows, pheromone trails),
    and summary metrics (alive/stuck counts, revenue, trajectories).
    """
    projector = _get_projector()
    snapshot = projector.build_snapshot(max_nodes=max_nodes)
    return ApiResponse(
        status="ok",
        data=snapshot.model_dump(),
    )


@router.get("/events")
async def get_events(
    since: float = Query(0.0, description="Unix timestamp to fetch events after"),
    limit: int = Query(100, ge=1, le=1000),
) -> ApiResponse:
    """Recent events across all data sources.

    Events include: stigmergy marks, trajectory completions,
    agent status changes, economic transactions.
    """
    projector = _get_projector()
    if since <= 0:
        since = time.time() - 3600  # Default: last hour
    events = projector.recent_events(since=since, limit=limit)
    return ApiResponse(
        status="ok",
        data=[e.model_dump() for e in events],
    )


@router.get("/timeline")
async def get_timeline(
    start: float = Query(..., description="Start timestamp"),
    end: float = Query(0.0, description="End timestamp (0 = now)"),
    max_events: int = Query(200, ge=1, le=1000),
) -> ApiResponse:
    """Timeline slice for temporal playback.

    Returns events within the time range plus a bounding snapshot.
    """
    projector = _get_projector()
    if end <= 0:
        end = time.time()
    timeline = projector.build_timeline(start=start, end=end, max_events=max_events)
    return ApiResponse(
        status="ok",
        data=timeline.model_dump(),
    )


@router.get("/node/{node_id:path}")
async def get_node(node_id: str) -> ApiResponse:
    """Detail for a single node."""
    projector = _get_projector()
    node = projector.node_detail(node_id)
    if node is None:
        return ApiResponse(status="error", error=f"Node not found: {node_id}")
    return ApiResponse(
        status="ok",
        data=node.model_dump(),
    )
