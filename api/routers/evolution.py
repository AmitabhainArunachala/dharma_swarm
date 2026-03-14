"""Evolution archive, fitness trend, lineage endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from api.models import ApiResponse, ArchiveEntryOut, FitnessOut

router = APIRouter(prefix="/api", tags=["evolution"])


def _entry_to_out(entry) -> dict:
    return ArchiveEntryOut(
        id=entry.id,
        timestamp=str(entry.timestamp),
        parent_id=entry.parent_id,
        component=entry.component,
        change_type=entry.change_type,
        description=entry.description,
        fitness=FitnessOut(
            correctness=entry.fitness.correctness,
            dharmic_alignment=entry.fitness.dharmic_alignment,
            performance=entry.fitness.performance,
            utilization=entry.fitness.utilization,
            economic_value=entry.fitness.economic_value,
            elegance=entry.fitness.elegance,
            efficiency=entry.fitness.efficiency,
            safety=entry.fitness.safety,
            weighted=entry.fitness.weighted(),
        ),
        status=entry.status,
        gates_passed=entry.gates_passed,
        gates_failed=entry.gates_failed,
        agent_id=entry.agent_id,
        model=entry.model,
    ).model_dump()


async def _get_archive():
    from dharma_swarm.archive import EvolutionArchive
    archive = EvolutionArchive()
    await archive.load()
    return archive


@router.get("/evolution/archive")
async def list_archive(status: str | None = None, limit: int = 100) -> ApiResponse:
    archive = await _get_archive()
    entries = await archive.list_entries(status=status)
    # Most recent first
    entries = sorted(entries, key=lambda e: e.timestamp, reverse=True)[:limit]
    return ApiResponse(data=[_entry_to_out(e) for e in entries])


@router.get("/evolution/archive/{entry_id}")
async def get_archive_entry(entry_id: str) -> ApiResponse:
    archive = await _get_archive()
    entry = await archive.get_entry(entry_id)
    if entry is None:
        return ApiResponse(status="error", error=f"Entry not found: {entry_id}")
    return ApiResponse(data=_entry_to_out(entry))


@router.get("/evolution/lineage/{entry_id}")
async def get_evolution_lineage(entry_id: str) -> ApiResponse:
    """Get the lineage chain for an evolution entry."""
    archive = await _get_archive()
    # lineage may or may not be async depending on version
    chain = archive.lineage(entry_id)
    if hasattr(chain, '__await__'):
        chain = await chain
    return ApiResponse(data=[_entry_to_out(e) for e in chain])


@router.get("/evolution/fitness-trend")
async def fitness_trend(component: str | None = None, limit: int = 100) -> ApiResponse:
    """Time-series fitness data for charting."""
    archive = await _get_archive()
    if component:
        entries_result = archive.entries_by_component(component)
        if hasattr(entries_result, '__await__'):
            entries_result = await entries_result
    else:
        entries_result = await archive.list_entries()

    entries = sorted(entries_result, key=lambda e: e.timestamp)[-limit:]

    trend = [
        {
            "timestamp": str(e.timestamp),
            "fitness": round(e.fitness.weighted(), 4),
            "correctness": e.fitness.correctness,
            "elegance": e.fitness.elegance,
            "component": e.component,
            "id": e.id,
        }
        for e in entries
    ]
    return ApiResponse(data=trend)


@router.get("/evolution/stats")
async def evolution_stats() -> ApiResponse:
    archive = await _get_archive()
    stats = archive.stats()
    if hasattr(stats, '__await__'):
        stats = await stats
    return ApiResponse(data=stats)


@router.get("/evolution/dag")
async def evolution_dag() -> ApiResponse:
    """Return nodes and edges for ReactFlow DAG visualization."""
    archive = await _get_archive()
    entries = await archive.list_entries()

    nodes = []
    edges = []

    for e in entries:
        nodes.append({
            "id": e.id,
            "type": "evolution",
            "data": {
                "label": e.component or e.id[:8],
                "fitness": round(e.fitness.weighted(), 3),
                "status": e.status,
                "change_type": e.change_type,
                "timestamp": str(e.timestamp),
            },
            "position": {"x": 0, "y": 0},  # Client does layout
        })

        if e.parent_id:
            edges.append({
                "id": f"{e.parent_id}-{e.id}",
                "source": e.parent_id,
                "target": e.id,
                "animated": e.status == "promoted",
            })

    return ApiResponse(data={"nodes": nodes, "edges": edges})
