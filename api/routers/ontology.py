"""Ontology browser endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from api.models import (
    ActionDefOut,
    ApiResponse,
    LinkDefOut,
    OntologyDetailOut,
    OntologyTypeOut,
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
    from dharma_swarm.ontology import OntologyRegistry
    return OntologyRegistry.create_dharma_registry()


@router.get("/ontology/types")
async def list_types() -> ApiResponse:
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
    return ApiResponse(data=types)


@router.get("/ontology/types/{type_name}")
async def describe_type(type_name: str) -> ApiResponse:
    reg = _get_registry()
    obj_type = reg.get_type(type_name)
    if obj_type is None:
        return ApiResponse(status="error", error=f"Type not found: {type_name}")

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
    return ApiResponse(data=detail.model_dump())


@router.get("/ontology/graph")
async def ontology_graph() -> ApiResponse:
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
        nodes.append({
            "id": t.name,
            "type": category,
            "data": {
                "label": t.name,
                "description": t.description,
                "propertyCount": len(t.properties),
                "actionCount": len(t.actions),
                "linkCount": len(reg.get_all_links_involving(t.name)),
                "runtimeCount": len(reg.get_objects_by_type(t.name)),
                "shakti": t.shakti_energy.value if hasattr(t.shakti_energy, 'value') else str(t.shakti_energy),
                "telos": t.telos_alignment,
                "icon": t.icon,
                "zone": zone,
            },
            "position": {
                "x": base_x + (count_in_category % 2) * 120,
                "y": base_y + (count_in_category // 2) * 180,
            },
        })

    # Collect all unique links
    seen_edges = set()
    for t in types:
        for ld in reg.get_links_for(t.name):
            edge_key = f"{ld.source_type}-{ld.name}-{ld.target_type}"
            if edge_key not in seen_edges:
                seen_edges.add(edge_key)
                edges.append({
                    "id": edge_key,
                    "source": ld.source_type,
                    "target": ld.target_type,
                    "label": ld.name,
                    "data": {
                        "cardinality": ld.cardinality.value if hasattr(ld.cardinality, 'value') else str(ld.cardinality),
                    },
                })

    return ApiResponse(data={"nodes": nodes, "edges": edges})


@router.get("/ontology/stats")
async def ontology_stats() -> ApiResponse:
    reg = _get_registry()
    return ApiResponse(data=reg.stats())


@router.get("/ontology/objects")
async def list_objects(type_name: str | None = None) -> ApiResponse:
    reg = _get_registry()
    if type_name:
        objs = reg.get_objects_by_type(type_name)
    else:
        objs = list(reg._objects.values())
    return ApiResponse(data=[
        {
            "id": o.id,
            "type": o.type_name,
            "properties": o.properties,
            "created_by": o.created_by,
            "version": o.version,
        }
        for o in objs
    ])
