"""Ontology browser endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from api.routers._agent_aliases import alias_candidates, matches_agent_alias
from api.models import (
    ActionDefOut,
    LinkDefOut,
    OntologyDetailOut,
    OntologyDetailResponse,
    OntologyGraphEdgeDataOut,
    OntologyGraphEdgeOut,
    OntologyGraphNodeDataOut,
    OntologyGraphNodeOut,
    OntologyGraphOut,
    OntologyGraphResponse,
    OntologyObjectListResponse,
    OntologyObjectOut,
    OntologyObjectResponse,
    OntologyStatsOut,
    OntologyStatsResponse,
    OntologyTypeOut,
    OntologyTypeListResponse,
    PropertyOut,
)

router = APIRouter(prefix="/api", tags=["ontology"])

_TYPE_CATEGORIES: dict[str, tuple[str, str]] = {
    "ResearchThread": ("concept", "strategy lattice"),
    "Experiment": ("concept", "research ops"),
    "Paper": ("artifact", "publication"),
    "AgentIdentity": ("agent", "operator mesh"),
    "KnowledgeArtifact": ("artifact", "knowledge vault"),
    "TypedTask": ("task", "execution rail"),
    "EvolutionEntry": ("artifact", "evolution archive"),
    "WitnessLog": ("gate", "witness field"),
}

_CATEGORY_LAYOUT: dict[str, tuple[int, int]] = {
    "concept": (80, 80),
    "task": (420, 160),
    "agent": (760, 60),
    "artifact": (1080, 120),
    "gate": (1420, 200),
}


def _get_registry():
    from dharma_swarm.ontology_runtime import get_shared_registry

    return get_shared_registry()


def _resolve_type_name(reg, requested_type: str | None) -> str | None:
    if not requested_type:
        return None

    candidates = [
        requested_type,
        requested_type.strip(),
        requested_type.replace("-", "_"),
        requested_type.replace("_", " "),
    ]
    titleized = candidates[-1].title().replace(" ", "")
    if titleized not in candidates:
        candidates.append(titleized)

    requested_lower = requested_type.lower()
    for obj_type in reg.get_types():
        if obj_type.name in candidates:
            return obj_type.name
        if obj_type.name.lower() == requested_lower:
            return obj_type.name
    return None


def _find_identity_object(reg, lookup: str):
    for obj in reg.get_objects_by_type("AgentIdentity"):
        props = obj.properties
        values = (
            obj.id,
            str(props.get("name") or ""),
            str(props.get("agent_id") or ""),
            str(props.get("agent_slug") or ""),
            str(props.get("display_name") or ""),
        )
        if any(matches_agent_alias(value, lookup) for value in values if value):
            return obj
    return None


def _serialize_object(reg, obj) -> dict:
    payload = {
        "id": obj.id,
        "type": obj.type_name,
        "properties": obj.properties,
        "created_by": obj.created_by,
        "created_at": str(obj.created_at),
        "updated_at": str(obj.updated_at),
        "version": obj.version,
    }

    if obj.type_name == "AgentIdentity":
        props = obj.properties
        type_def = reg.get_type(obj.type_name)
        role = str(props.get("role") or "").strip()
        roles = [role] if role else []
        payload.update(
            {
                "name": str(props.get("name") or ""),
                "display_name": str(props.get("display_name") or props.get("name") or ""),
                "agent_slug": str(props.get("agent_slug") or ""),
                "runtime_agent_id": str(props.get("agent_id") or obj.id),
                "kaizenops_id": str(props.get("kaizenops_id") or props.get("agent_id") or obj.id),
                "roles": roles,
                "status": str(props.get("status") or "unknown"),
                "telos_alignment": float(getattr(type_def, "telos_alignment", 0.0) or 0.0),
                "witness_quality": float(getattr(type_def, "witness_quality", 0.0) or 0.0),
                "shakti_energy": 1.0,
                "tasks_completed": int(props.get("tasks_completed", 0) or 0),
                "avg_quality": float(props.get("fitness_average", 0.0) or 0.0),
                "last_active": str(
                    props.get("last_active")
                    or props.get("last_heartbeat")
                    or obj.updated_at
                ),
            }
        )

    return payload


@router.get("/ontology/types", response_model=OntologyTypeListResponse)
async def list_types() -> OntologyTypeListResponse:
    reg = _get_registry()
    types = [
        OntologyTypeOut(
            name=t.name,
            description=t.description,
            telos_alignment=t.telos_alignment,
            shakti=t.shakti_energy.value if hasattr(t.shakti_energy, 'value') else str(t.shakti_energy),
            property_count=len(t.properties),
            link_count=len(t.links),
            action_count=len(t.actions),
            icon=t.icon,
        ).model_dump()
        for t in reg.get_types()
    ]
    return OntologyTypeListResponse(data=[OntologyTypeOut(**item) for item in types])


@router.get("/ontology/types/{type_name}", response_model=OntologyDetailResponse)
async def describe_type(type_name: str) -> OntologyDetailResponse:
    reg = _get_registry()
    obj_type = reg.get_type(type_name)
    if obj_type is None:
        return OntologyDetailResponse(status="error", error=f"Type not found: {type_name}")

    detail = OntologyDetailOut(
        name=obj_type.name,
        description=obj_type.description,
        properties=[
            PropertyOut(
                name=p.name,
                property_type=p.property_type.value if hasattr(p.property_type, 'value') else str(p.property_type),
                required=p.required,
                description=p.description,
                searchable=p.searchable,
            )
            for p in obj_type.properties.values()
        ],
        links=[
            LinkDefOut(
                name=ld.name,
                source_type=ld.source_type,
                target_type=ld.target_type,
                cardinality=ld.cardinality.value if hasattr(ld.cardinality, 'value') else str(ld.cardinality),
                description=ld.description,
            )
            for ld in reg.get_all_links_involving(type_name)
        ],
        actions=[
            ActionDefOut(
                name=ad.name,
                description=ad.description,
                requires_approval=ad.requires_approval,
                telos_gates=ad.telos_gates,
                is_deterministic=ad.is_deterministic,
            )
            for ad in reg.get_actions_for(type_name)
        ],
        security_level=obj_type.security.classification.value if hasattr(obj_type.security.classification, 'value') else str(obj_type.security.classification),
        telos_alignment=obj_type.telos_alignment,
        shakti=obj_type.shakti_energy.value if hasattr(obj_type.shakti_energy, 'value') else str(obj_type.shakti_energy),
    )
    return OntologyDetailResponse(data=detail)


@router.get("/ontology/graph", response_model=OntologyGraphResponse)
async def ontology_graph() -> OntologyGraphResponse:
    """Return nodes and edges for ReactFlow graph visualization."""
    reg = _get_registry()
    nodes = []
    edges = []
    category_counts: dict[str, int] = {}

    types = reg.get_types()
    for t in types:
        category, zone = _TYPE_CATEGORIES.get(t.name, ("concept", "semantic mesh"))
        count_in_category = category_counts.get(category, 0)
        category_counts[category] = count_in_category + 1
        base_x, base_y = _CATEGORY_LAYOUT.get(category, (0, 0))
        nodes.append(
            OntologyGraphNodeOut(
                id=t.name,
                type=category,
                data=OntologyGraphNodeDataOut(
                    label=t.name,
                    description=t.description,
                    propertyCount=len(t.properties),
                actionCount=len(t.actions),
                linkCount=len(reg.get_all_links_involving(t.name)),
                runtimeCount=len(reg.get_objects_by_type(t.name)),
                shakti=t.shakti_energy.value if hasattr(t.shakti_energy, 'value') else str(t.shakti_energy),
                telos=t.telos_alignment,
                icon=t.icon,
                zone=zone,
                ),
                position={
                    "x": base_x + (count_in_category % 2) * 120,
                    "y": base_y + (count_in_category // 2) * 180,
                },
            )
        )

    # Collect all unique links
    seen_edges = set()
    for t in types:
        for ld in reg.get_links_for(t.name):
            edge_key = f"{ld.source_type}-{ld.name}-{ld.target_type}"
            if edge_key not in seen_edges:
                seen_edges.add(edge_key)
                edges.append(
                    OntologyGraphEdgeOut(
                        id=edge_key,
                        source=ld.source_type,
                        target=ld.target_type,
                        label=ld.name,
                        data=OntologyGraphEdgeDataOut(
                            cardinality=ld.cardinality.value if hasattr(ld.cardinality, 'value') else str(ld.cardinality),
                        ),
                    )
                )

    return OntologyGraphResponse(data=OntologyGraphOut(nodes=nodes, edges=edges))


@router.get("/ontology/stats", response_model=OntologyStatsResponse)
async def ontology_stats() -> OntologyStatsResponse:
    reg = _get_registry()
    return OntologyStatsResponse(data=OntologyStatsOut(**reg.stats()))


@router.get("/ontology/objects", response_model=OntologyObjectListResponse)
async def list_objects(
    type_name: str | None = None,
    type: str | None = None,
) -> OntologyObjectListResponse:
    reg = _get_registry()
    requested_type = type_name or type
    resolved_type = _resolve_type_name(reg, requested_type)
    if requested_type and resolved_type is None:
        objs = []
    elif resolved_type:
        objs = reg.get_objects_by_type(resolved_type)
    else:
        objs = list(reg._objects.values())
    return OntologyObjectListResponse(
        data=[OntologyObjectOut(**_serialize_object(reg, o)) for o in objs]
    )


@router.get("/ontology/objects/{obj_id}", response_model=OntologyObjectResponse)
async def get_object(obj_id: str) -> OntologyObjectResponse:
    reg = _get_registry()
    obj = reg.get_object(obj_id)
    if obj is None:
        for candidate in alias_candidates(obj_id):
            obj = _find_identity_object(reg, candidate)
            if obj is not None:
                break
    if obj is None:
        return OntologyObjectResponse(status="error", error=f"Object not found: {obj_id}")

    payload = _serialize_object(reg, obj)
    payload["context"] = reg.object_context_for_llm(obj.id)
    return OntologyObjectResponse(data=OntologyObjectOut(**payload))
