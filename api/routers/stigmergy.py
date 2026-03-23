"""Stigmergy (pheromone marks) endpoints."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from api.models import ApiResponse, HeatmapCell, StigmergyMarkOut
from api.routers._agent_aliases import matches_agent_alias

router = APIRouter(prefix="/api", tags=["stigmergy"])
MARKS_PATH = Path.home() / ".dharma" / "stigmergy" / "marks.jsonl"


class PromoteMarkRequest(BaseModel):
    salience: float
    promoted_by: str = "operator"


def _get_store():
    from dharma_swarm.stigmergy import StigmergyStore
    return StigmergyStore(base_path=MARKS_PATH.parent)


def _load_mark_records() -> list[dict]:
    if not MARKS_PATH.exists():
        return []
    records: list[dict] = []
    with MARKS_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                records.append(payload)
    return records


def _write_mark_records(records: list[dict]) -> None:
    MARKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Atomic temp→rename to avoid data loss from concurrent writes
    tmp = MARKS_PATH.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=True) + "\n")
        fh.flush()
    tmp.rename(MARKS_PATH)


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
        semantic_type=getattr(mark, "semantic_type", "") or "",
        pillar_refs=getattr(mark, "pillar_refs", []) or [],
        confidence=float(getattr(mark, "confidence", 0.0) or 0.0),
        impact_score=float(getattr(mark, "impact_score", 0.0) or 0.0),
    ).model_dump()


@router.get("/stigmergy/marks")
async def list_marks(
    file_path: str | None = None,
    agent: str | None = None,
    limit: int = 50,
) -> ApiResponse:
    store = _get_store()
    read_limit = 10_000 if agent else limit
    marks = await store.read_marks(file_path=file_path, limit=read_limit)
    if agent:
        marks = [mark for mark in marks if matches_agent_alias(mark.agent, agent)]
    return ApiResponse(data=[_mark_to_out(m) for m in marks[:limit]])


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
    from datetime import datetime, timezone, timedelta

    store = _get_store()
    marks = await store.read_marks(limit=1000)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    grid: dict[tuple[str, int], list[float]] = defaultdict(list)
    for m in marks:
        try:
            if m.timestamp < cutoff:
                continue
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


@router.post("/stigmergy/marks/{mark_id}/promote")
async def promote_mark(mark_id: str, req: PromoteMarkRequest) -> ApiResponse:
    records = _load_mark_records()
    for record in records:
        if str(record.get("id")) != mark_id:
            continue
        record["salience"] = float(req.salience)
        record["promoted_by"] = req.promoted_by
        operator_actions = record.get("operator_actions")
        if not isinstance(operator_actions, list):
            operator_actions = []
        operator_actions.append(
            {
                "action": "promote",
                "promoted_by": req.promoted_by,
                "salience": float(req.salience),
            }
        )
        record["operator_actions"] = operator_actions
        _write_mark_records(records)
        return ApiResponse(data=record)
    return ApiResponse(status="error", error=f"Mark not found: {mark_id}")


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
