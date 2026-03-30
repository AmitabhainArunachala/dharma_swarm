"""
GraphQL Router for Palantir-Style Ontology Interface
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from dharma_swarm.ontology_agents import (
    agent_display_name,
    agent_slug,
    canonical_model_key,
)
from dharma_swarm.runtime_paths import resolve_runtime_paths

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graphql", tags=["graphql"])


# Models
class GraphQLSurfaceContract(BaseModel):
    enabled: bool
    mounted: bool
    mode: str
    reason: str
    feature_flag: str
    feature_enabled: bool
    dependency_ready: bool
    query_fields: List[str]
    rest_routes: List[str]


class OntologyObject(BaseModel):
    id: str
    type: str
    properties: dict
    created_at: datetime
    updated_at: datetime


class StigmergyMark(BaseModel):
    id: str
    agent: str
    file_path: str
    action: str
    observation: str
    semantic_type: str
    salience: float
    confidence: float
    impact_score: float
    pillar_refs: List[str]
    linked_objects: List[str]
    timestamp: datetime


class AgentIdentity(BaseModel):
    id: str
    name: str
    display_name: str = ""
    agent_slug: str = ""
    runtime_agent_id: str = ""
    kaizenops_id: str
    roles: List[str]
    provider: str = ""
    model: str = ""
    model_key: str = ""
    status: str = "unknown"
    telos_alignment: float
    witness_quality: float
    shakti_energy: float
    tasks_completed: int
    avg_quality: float
    created_at: datetime
    updated_at: datetime


class GraphNode(BaseModel):
    id: str
    type: str
    label: str
    properties: dict


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str
    properties: dict


class ConnectionGraph(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]


GINKO_AGENTS_DIR: Path | None = None
STIGMERGY_MARKS_PATH: Path | None = None
GRAPH_ROOT_ALIASES = {
    "ecosystem-synthesizer": "glm5-researcher",
    "ecosystem_synthesizer": "glm5-researcher",
    "agent_identity_ecosystem_synthesizer": "glm5-researcher",
}


def _runtime_state_root() -> Path:
    return resolve_runtime_paths().state_root


def _ginko_agents_dir() -> Path:
    if GINKO_AGENTS_DIR is not None:
        return GINKO_AGENTS_DIR
    return _runtime_state_root() / "ginko" / "agents"


def _stigmergy_marks_path() -> Path:
    if STIGMERGY_MARKS_PATH is not None:
        return STIGMERGY_MARKS_PATH
    return _runtime_state_root() / "stigmergy" / "marks.jsonl"


def _path_tail(path: str, parts: int = 2) -> str:
    trimmed = [segment for segment in path.split("/") if segment]
    if not trimmed:
        return path
    return "/".join(trimmed[-parts:])


def _load_marks(agent: str, limit: int = 20) -> list[dict]:
    marks_path = _stigmergy_marks_path()
    if not marks_path.exists():
        return []

    marks: list[dict] = []
    with marks_path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                data = json.loads(line.strip())
            except Exception:
                continue
            if data.get("agent") != agent:
                continue
            marks.append(data)

    marks.sort(key=lambda item: float(item.get("salience", 0.0)), reverse=True)
    return marks[:limit]


def _graph_from_stigmergy(agent_id: str, limit: int = 20) -> ConnectionGraph:
    marks = _load_marks(agent_id, limit=limit)
    identity_path = _ginko_agents_dir() / agent_id / "identity.json"

    agent_label = agent_id
    agent_props: dict = {}
    if identity_path.exists():
        try:
            identity = json.loads(identity_path.read_text(encoding="utf-8"))
            agent_label = identity.get("name") or agent_id
            agent_props = {
                "role": identity.get("role", ""),
                "model": identity.get("model", ""),
                "status": identity.get("status", ""),
                "last_active": identity.get("last_active", ""),
            }
        except Exception:
            logger.debug("Failed to load agent identity from %s", identity_path, exc_info=True)

    nodes: dict[str, GraphNode] = {
        agent_id: GraphNode(
            id=agent_id,
            type="agent",
            label=agent_label,
            properties=agent_props,
        )
    }
    edges: list[GraphEdge] = []

    for index, mark in enumerate(marks):
        raw_mark_id = str(mark.get("id") or f"{agent_id}-{index}")
        mark_node_id = f"mark:{raw_mark_id}"
        file_path = str(mark.get("file_path", "")).strip()
        file_node_id = f"file:{file_path}" if file_path else ""

        nodes[mark_node_id] = GraphNode(
            id=mark_node_id,
            type="mark",
            label=_path_tail(file_path, parts=2) or str(mark.get("action", "mark")),
            properties={
                "action": mark.get("action", ""),
                "semantic_type": mark.get("semantic_type", ""),
                "salience": mark.get("salience", 0.0),
                "confidence": mark.get("confidence", 0.0),
                "observation": mark.get("observation", ""),
            },
        )
        edges.append(
            GraphEdge(
                id=f"edge:{mark_node_id}:agent",
                source=mark_node_id,
                target=agent_id,
                type="left_by",
                properties={},
            )
        )

        if file_node_id:
            nodes[file_node_id] = GraphNode(
                id=file_node_id,
                type="file",
                label=_path_tail(file_path, parts=2),
                properties={"path": file_path},
            )
            edges.append(
                GraphEdge(
                    id=f"edge:{mark_node_id}:file",
                    source=mark_node_id,
                    target=file_node_id,
                    type="touches",
                    properties={},
                )
            )

        for pillar in mark.get("pillar_refs", []) or []:
            pillar_id = f"pillar:{pillar}"
            nodes[pillar_id] = GraphNode(
                id=pillar_id,
                type="pillar",
                label=str(pillar),
                properties={},
            )
            edges.append(
                GraphEdge(
                    id=f"edge:{mark_node_id}:{pillar_id}",
                    source=mark_node_id,
                    target=pillar_id,
                    type="references",
                    properties={},
                )
            )

    return ConnectionGraph(nodes=list(nodes.values()), edges=edges)


def _resolve_graph_root(root_id: str) -> str:
    return GRAPH_ROOT_ALIASES.get(root_id, root_id)


def _graph_label(properties: dict, fallback_id: str) -> str:
    return str(
        properties.get("name")
        or properties.get("display_name")
        or properties.get("title")
        or fallback_id
    )


# Endpoints
@router.get("", response_model=GraphQLSurfaceContract)
@router.get("/", response_model=GraphQLSurfaceContract, include_in_schema=False)
async def get_graphql_surface_contract():
    """Report the truthful state of the public GraphQL surface."""
    from api.graphql.schema import graphql_surface_contract

    return GraphQLSurfaceContract(**graphql_surface_contract())


@router.get("/agent/{agent_id}", response_model=AgentIdentity)
async def get_agent_identity(agent_id: str):
    """Get agent identity by ID."""
    from dharma_swarm.ontology_agents import find_agent_identity
    from dharma_swarm.ontology_runtime import get_shared_registry

    registry = get_shared_registry()
    ontology_obj = find_agent_identity(registry, agent_id=agent_id, name=agent_id)
    if ontology_obj is not None:
        props = ontology_obj.properties
        obj_type = registry.get_type("AgentIdentity")
        return AgentIdentity(
            id=ontology_obj.id,
            name=str(props.get("name") or agent_id),
            display_name=str(
                props.get("display_name")
                or agent_display_name(str(props.get("name") or agent_id))
            ),
            agent_slug=str(props.get("agent_slug") or agent_slug(str(props.get("name") or agent_id))),
            runtime_agent_id=str(props.get("agent_id") or ontology_obj.id),
            kaizenops_id=str(props.get("kaizenops_id") or props.get("agent_id") or ontology_obj.id),
            roles=[str(props.get("role") or "general")],
            provider=str(props.get("provider") or ""),
            model=str(props.get("model") or ""),
            model_key=str(
                props.get("model_key")
                or canonical_model_key(
                    str(props.get("provider") or ""),
                    str(props.get("model") or ""),
                )
            ),
            status=str(props.get("status") or "unknown"),
            telos_alignment=float(obj_type.telos_alignment if obj_type else 0.0),
            witness_quality=float(props.get("swabhaav_capacity") or 0.0),
            shakti_energy=0.0,
            tasks_completed=int(props.get("tasks_completed") or 0),
            avg_quality=float(props.get("fitness_average") or 0.0),
            created_at=ontology_obj.created_at,
            updated_at=ontology_obj.updated_at,
        )

    identity_path = _ginko_agents_dir() / agent_id / "identity.json"

    if not identity_path.exists():
        raise HTTPException(status_code=404, detail="Agent not found")

    with identity_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    provider = str(data.get("provider", "") or "")
    model = str(data.get("model", "") or "")
    runtime_agent_id = str(data.get("agent_id") or data.get("id") or agent_id)

    return AgentIdentity(
        id=data.get("id", agent_id),
        name=data.get("name", agent_id),
        display_name=data.get("display_name", agent_display_name(str(data.get("name", agent_id)))),
        agent_slug=data.get("agent_slug", agent_slug(str(data.get("name", agent_id)))),
        runtime_agent_id=runtime_agent_id,
        kaizenops_id=str(data.get("kaizenops_id") or runtime_agent_id),
        roles=data.get("roles") or [str(data.get("role") or "general")],
        provider=provider,
        model=model,
        model_key=str(data.get("model_key") or canonical_model_key(provider, model)),
        status=data.get("status", "unknown"),
        telos_alignment=data.get("telos_alignment", 0.0),
        witness_quality=data.get("witness_quality", 0.0),
        shakti_energy=data.get("shakti_energy", 0.0),
        tasks_completed=data.get("tasks_completed", 0),
        avg_quality=data.get("avg_quality", 0.0),
        created_at=datetime.fromisoformat(data.get("created_at", datetime.now().isoformat())),
        updated_at=datetime.fromisoformat(data.get("updated_at", datetime.now().isoformat())),
    )


@router.get("/stigmergy_marks", response_model=List[StigmergyMark])
async def get_stigmergy_marks(
    agent: Optional[str] = None,
    semantic_type: Optional[str] = None,
    min_salience: Optional[float] = None,
    limit: int = 50
):
    """Get stigmergy marks with optional filters."""
    if not STIGMERGY_MARKS_PATH.exists():
        return []

    marks = []
    with STIGMERGY_MARKS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                
                # Apply filters
                if agent and data.get("agent") != agent:
                    continue
                if semantic_type and data.get("semantic_type") != semantic_type:
                    continue
                if min_salience and data.get("salience", 0) < min_salience:
                    continue
                
                marks.append(StigmergyMark(
                    id=data.get("id", ""),
                    agent=data.get("agent", ""),
                    file_path=data.get("file_path", ""),
                    action=data.get("action", ""),
                    observation=data.get("observation", ""),
                    semantic_type=data.get("semantic_type", "task_receipt"),
                    salience=data.get("salience", 0.0),
                    confidence=data.get("confidence", 0.0),
                    impact_score=data.get("impact_score", 0.0),
                    pillar_refs=data.get("pillar_refs", []),
                    linked_objects=data.get("linked_objects", []),
                    timestamp=datetime.fromisoformat(data.get("timestamp", datetime.now().isoformat())),
                ))
                
                if len(marks) >= limit:
                    break
            except Exception:
                continue
    
    return marks


@router.get("/connection_graph/{root_id}", response_model=ConnectionGraph)
async def get_connection_graph(root_id: str, depth: int = 3):
    """Get connection graph from root object."""
    from dharma_swarm.ontology_query import OntologyGraph
    from dharma_swarm.ontology_runtime import get_shared_registry

    resolved_root = _resolve_graph_root(root_id)
    registry = get_shared_registry()
    graph = OntologyGraph(registry)
    result = graph.traverse(resolved_root, depth=min(depth, 5))

    if result["root"] is not None:
        nodes = []
        for obj in result["nodes"]:
            nodes.append(GraphNode(
                id=obj.id,
                type=obj.type_name,
                label=_graph_label(obj.properties, obj.id),
                properties=obj.properties,
            ))
        edges = [
            GraphEdge(
                id=link.id,
                source=link.source_id,
                target=link.target_id,
                type=link.link_name,
                properties=link.metadata,
            )
            for link in result["edges"]
        ]
        return ConnectionGraph(nodes=nodes, edges=edges)

    # Fall back to a real graph synthesized from stigmergy if no ontology root exists yet.
    return _graph_from_stigmergy(resolved_root, limit=max(6, min(depth * 8, 24)))


@router.get("/search", response_model=List[OntologyObject])
async def search_objects(
    query: str,
    types: Optional[List[str]] = None,
    limit: int = 50
):
    """Search ontology objects via FTS5 full-text search."""
    from dharma_swarm.ontology_runtime import get_shared_registry, _SHARED_HUB

    # Prefer FTS5 through OntologyHub when available.
    get_shared_registry()  # ensure hub is initialised
    hub = _SHARED_HUB

    results: list[OntologyObject] = []
    if hub is not None:
        if types:
            for type_name in types:
                for obj in hub.search_text(query, type_name=type_name, limit=limit):
                    results.append(OntologyObject(
                        id=obj.id,
                        type=obj.type_name,
                        properties=obj.properties,
                        created_at=obj.created_at,
                        updated_at=obj.updated_at,
                    ))
        else:
            for obj in hub.search_text(query, limit=limit):
                results.append(OntologyObject(
                    id=obj.id,
                    type=obj.type_name,
                    properties=obj.properties,
                    created_at=obj.created_at,
                    updated_at=obj.updated_at,
                ))
    else:
        # Fallback: in-memory substring search via registry.
        registry = get_shared_registry()
        query_lower = query.lower()
        for obj in list(registry._objects.values())[:limit * 5]:
            if types and obj.type_name not in types:
                continue
            if query_lower in obj.type_name.lower() or any(
                isinstance(v, str) and query_lower in v.lower()
                for v in obj.properties.values()
            ):
                results.append(OntologyObject(
                    id=obj.id,
                    type=obj.type_name,
                    properties=obj.properties,
                    created_at=obj.created_at,
                    updated_at=obj.updated_at,
                ))
            if len(results) >= limit:
                break

    return results[:limit]
