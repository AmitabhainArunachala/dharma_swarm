"""Lineage (provenance + impact) endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from api.models import ApiResponse, ImpactOut, LineageEdgeOut, ProvenanceOut

router = APIRouter(prefix="/api", tags=["lineage"])


def _get_lineage():
    from dharma_swarm.lineage import LineageGraph
    return LineageGraph()


def _edge_to_out(edge) -> dict:
    return LineageEdgeOut(
        edge_id=edge.edge_id,
        task_id=edge.task_id,
        input_artifacts=edge.input_artifacts,
        output_artifacts=edge.output_artifacts,
        agent=edge.agent,
        operation=edge.operation,
        timestamp=str(edge.timestamp),
    ).model_dump()


@router.get("/lineage/{artifact_id}/provenance")
async def get_provenance(artifact_id: str, max_depth: int = 50) -> ApiResponse:
    lg = _get_lineage()
    chain = lg.provenance(artifact_id, max_depth=max_depth)
    return ApiResponse(data=ProvenanceOut(
        artifact_id=chain.artifact_id,
        chain=[LineageEdgeOut(
            edge_id=e.edge_id,
            task_id=e.task_id,
            input_artifacts=e.input_artifacts,
            output_artifacts=e.output_artifacts,
            agent=e.agent,
            operation=e.operation,
            timestamp=str(e.timestamp),
        ) for e in chain.chain],
        root_sources=chain.root_sources,
        depth=chain.depth,
    ).model_dump())


@router.get("/lineage/{artifact_id}/impact")
async def get_impact(artifact_id: str, max_depth: int = 50) -> ApiResponse:
    lg = _get_lineage()
    impact = lg.impact(artifact_id, max_depth=max_depth)
    return ApiResponse(data=ImpactOut(
        root_artifact=impact.root_artifact,
        affected_artifacts=impact.affected_artifacts,
        affected_tasks=impact.affected_tasks,
        depth=impact.depth,
        total_descendants=impact.total_descendants,
    ).model_dump())


@router.get("/lineage/{artifact_id}/ancestors")
async def get_ancestors(artifact_id: str, max_depth: int = 50) -> ApiResponse:
    lg = _get_lineage()
    edges = lg.ancestors(artifact_id, max_depth=max_depth)
    return ApiResponse(data=[_edge_to_out(e) for e in edges])


@router.get("/lineage/{artifact_id}/descendants")
async def get_descendants(artifact_id: str, max_depth: int = 50) -> ApiResponse:
    lg = _get_lineage()
    edges = lg.descendants(artifact_id, max_depth=max_depth)
    return ApiResponse(data=[_edge_to_out(e) for e in edges])


@router.get("/lineage/{artifact_id}/dag")
async def lineage_dag(artifact_id: str, max_depth: int = 20) -> ApiResponse:
    """Return nodes and edges for ReactFlow visualization of provenance + impact."""
    lg = _get_lineage()

    ancestors = lg.ancestors(artifact_id, max_depth=max_depth)
    descendants = lg.descendants(artifact_id, max_depth=max_depth)

    nodes = {}
    edges = []

    # Root artifact
    nodes[artifact_id] = {
        "id": artifact_id,
        "type": "artifact",
        "data": {"label": artifact_id, "isRoot": True},
        "position": {"x": 0, "y": 0},
    }

    for edge in ancestors:
        for inp in edge.input_artifacts:
            if inp not in nodes:
                nodes[inp] = {
                    "id": inp,
                    "type": "artifact",
                    "data": {"label": inp, "isRoot": False},
                    "position": {"x": 0, "y": 0},
                }
        for out in edge.output_artifacts:
            if out not in nodes:
                nodes[out] = {
                    "id": out,
                    "type": "artifact",
                    "data": {"label": out, "isRoot": False},
                    "position": {"x": 0, "y": 0},
                }
        for inp in edge.input_artifacts:
            for out in edge.output_artifacts:
                edges.append({
                    "id": f"{inp}-{out}",
                    "source": inp,
                    "target": out,
                    "label": edge.operation,
                    "animated": True,
                })

    for edge in descendants:
        for inp in edge.input_artifacts:
            if inp not in nodes:
                nodes[inp] = {
                    "id": inp,
                    "type": "artifact",
                    "data": {"label": inp, "isRoot": False},
                    "position": {"x": 0, "y": 0},
                }
        for out in edge.output_artifacts:
            if out not in nodes:
                nodes[out] = {
                    "id": out,
                    "type": "artifact",
                    "data": {"label": out, "isRoot": False},
                    "position": {"x": 0, "y": 0},
                }
        for inp in edge.input_artifacts:
            for out in edge.output_artifacts:
                edges.append({
                    "id": f"{inp}-{out}",
                    "source": inp,
                    "target": out,
                    "label": edge.operation,
                })

    return ApiResponse(data={"nodes": list(nodes.values()), "edges": edges})


@router.get("/lineage/stats")
async def lineage_stats() -> ApiResponse:
    lg = _get_lineage()
    return ApiResponse(data=lg.stats())
