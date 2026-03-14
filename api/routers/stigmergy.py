"""Stigmergy (pheromone marks) endpoints."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter

from api.models import ApiResponse, HeatmapCell, StigmergyMarkOut

router = APIRouter(prefix="/api", tags=["stigmergy"])


def _get_store():
    from dharma_swarm.stigmergy import StigmergyStore
    return StigmergyStore()


def _mark_to_out(mark) -> dict:
    return StigmergyMarkOut(
        id=mark.id,
        timestamp=str(mark.timestamp),
        agent=mark.agent,
        file_path=mark.file_path,
        action=mark.action,
        observation=mark.observation,
        salience=mark.salience,
        connections=mark.connections,
    ).model_dump()


@router.get("/stigmergy/marks")
async def list_marks(file_path: str | None = None, limit: int = 50) -> ApiResponse:
    store = _get_store()
    marks = await store.read_marks(file_path=file_path, limit=limit)
    return ApiResponse(data=[_mark_to_out(m) for m in marks])


@router.get("/stigmergy/hot-paths")
async def hot_paths(window_hours: float = 24, min_marks: int = 3) -> ApiResponse:
    store = _get_store()
    paths = await store.hot_paths(window_hours=window_hours, min_marks=min_marks)
    return ApiResponse(data=[{"path": p, "count": c} for p, c in paths])


@router.get("/stigmergy/high-salience")
async def high_salience(threshold: float = 0.7, limit: int = 20) -> ApiResponse:
    store = _get_store()
    marks = await store.high_salience(threshold=threshold, limit=limit)
    return ApiResponse(data=[_mark_to_out(m) for m in marks])


@router.get("/stigmergy/heatmap")
async def heatmap_data(window_hours: float = 168) -> ApiResponse:
    """Heatmap data: file_path × hour_of_day × count + avg_salience."""
    store = _get_store()
    marks = await store.read_marks(limit=1000)

    grid: dict[tuple[str, int], list[float]] = defaultdict(list)
    for m in marks:
        try:
            hour = m.timestamp.hour
        except Exception:
            hour = 0
        key = (m.file_path, hour)
        grid[key].append(m.salience)

    cells = [
        HeatmapCell(
            file_path=fp,
            hour=h,
            count=len(saliences),
            avg_salience=round(sum(saliences) / len(saliences), 3),
        ).model_dump()
        for (fp, h), saliences in grid.items()
    ]
    return ApiResponse(data=cells)


@router.get("/stigmergy/density")
async def density() -> ApiResponse:
    store = _get_store()
    return ApiResponse(data={"density": store.density()})


@router.get("/stigmergy/graph")
async def stigmergy_graph() -> ApiResponse:
    """Force-directed graph data: nodes=files, edges=connections, size=salience."""
    store = _get_store()
    marks = await store.read_marks(limit=500)

    nodes_map: dict[str, dict] = {}
    edges = []

    for m in marks:
        if m.file_path not in nodes_map:
            nodes_map[m.file_path] = {
                "id": m.file_path,
                "label": m.file_path.split("/")[-1],
                "salience": m.salience,
                "count": 1,
            }
        else:
            nodes_map[m.file_path]["count"] += 1
            nodes_map[m.file_path]["salience"] = max(
                nodes_map[m.file_path]["salience"], m.salience
            )

        for conn in m.connections:
            if conn not in nodes_map:
                nodes_map[conn] = {
                    "id": conn,
                    "label": conn.split("/")[-1],
                    "salience": 0.3,
                    "count": 0,
                }
            edges.append({
                "source": m.file_path,
                "target": conn,
                "agent": m.agent,
            })

    return ApiResponse(data={
        "nodes": list(nodes_map.values()),
        "edges": edges,
    })
