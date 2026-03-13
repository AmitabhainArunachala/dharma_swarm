"""Dimension 3 — Field Intelligence Graph.

Transforms the curated field_knowledge_base into a ConceptGraph
and produces cross-dimensional reports:

  1. overlap_report()  — what DGC already implements that exists externally
  2. gap_report()      — what the field has that DGC lacks
  3. uniqueness_report() — what DGC has that NO ONE else has
  4. competitive_position() — full strategic positioning

Cross-dimensional mapping:
  D1 = internal codebase concepts (from semantic_digester)
  D2 = PSMV knowledge corpus concepts (from psmv_deep_read)
  D3 = external field intelligence (THIS module)

All three dimensions share the same ConceptGraph infrastructure.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from dharma_swarm.field_knowledge_base import (
    ALL_FIELD_ENTRIES,
    FIELD_DOMAINS,
    RelationType,
)
from dharma_swarm.semantic_gravity import (
    ConceptEdge,
    ConceptGraph,
    ConceptNode,
    EdgeType,
    ResearchAnnotation,
    ResearchConnectionType,
)


# ---------------------------------------------------------------------------
# Relation → EdgeType / ResearchConnectionType mapping
# ---------------------------------------------------------------------------

_RELATION_TO_EDGE: dict[str, EdgeType] = {
    "validates": EdgeType.REFERENCES,
    "competes": EdgeType.ANALOGOUS_TO,
    "extends": EdgeType.EXTENDS,
    "orthogonal": EdgeType.ANALOGOUS_TO,
    "gap": EdgeType.REFERENCES,
    "unique": EdgeType.GROUNDS,
    "supersedes": EdgeType.EXTENDS,
}

_RELATION_TO_RESEARCH: dict[str, ResearchConnectionType] = {
    "validates": ResearchConnectionType.VALIDATION,
    "competes": ResearchConnectionType.ORTHOGONAL,
    "extends": ResearchConnectionType.ENGINEERING_GROUNDING,
    "orthogonal": ResearchConnectionType.ORTHOGONAL,
    "gap": ResearchConnectionType.ORTHOGONAL,
    "unique": ResearchConnectionType.VALIDATION,
    "supersedes": ResearchConnectionType.VALIDATION,
}


# ---------------------------------------------------------------------------
# Build the D3 graph
# ---------------------------------------------------------------------------


def build_field_graph() -> ConceptGraph:
    """Build a ConceptGraph from ALL_FIELD_ENTRIES.

    Each entry becomes a ConceptNode.  DGC-internal entries get
    category='dgc_internal'; external ones get their field as category.
    Edges are created between entries that share dgc_mapping tokens.
    """
    graph = ConceptGraph()
    id_by_entry: dict[str, str] = {}  # entry["id"] → node.id

    # --- Pass 1: create nodes ---
    for entry in ALL_FIELD_ENTRIES:
        is_internal = entry.get("type") == "dgc_internal"
        node = ConceptNode(
            name=entry["id"],
            definition=entry.get("summary", ""),
            source_file=entry.get("url", ""),
            category="dgc_internal" if is_internal else entry.get("field", ""),
            salience=entry.get("confidence", 0.5),
            metadata={
                "d3_entry_id": entry["id"],
                "d3_source": entry.get("source", ""),
                "d3_field": entry.get("field", ""),
                "d3_type": entry.get("type", ""),
                "d3_year": entry.get("year", 0),
                "d3_relation": entry.get("relation", ""),
                "d3_dgc_mapping": entry.get("dgc_mapping", []),
                "d3_relevance": entry.get("relevance_to_dgc", ""),
                "dimension": 3,
            },
        )
        nid = graph.add_node(node)
        id_by_entry[entry["id"]] = nid

    # --- Pass 2: create edges via shared dgc_mapping tokens ---
    mapping_index: dict[str, list[str]] = defaultdict(list)  # token → [entry_id]
    for entry in ALL_FIELD_ENTRIES:
        for token in entry.get("dgc_mapping", []):
            mapping_index[token].append(entry["id"])

    seen_edges: set[tuple[str, str]] = set()
    for token, entry_ids in mapping_index.items():
        for i, eid_a in enumerate(entry_ids):
            for eid_b in entry_ids[i + 1:]:
                pair = (min(eid_a, eid_b), max(eid_a, eid_b))
                if pair in seen_edges:
                    continue
                seen_edges.add(pair)
                nid_a = id_by_entry.get(eid_a)
                nid_b = id_by_entry.get(eid_b)
                if nid_a and nid_b:
                    graph.add_edge(ConceptEdge(
                        source_id=nid_a,
                        target_id=nid_b,
                        edge_type=EdgeType.REFERENCES,
                        weight=0.8,
                        evidence=f"shared dgc_mapping token: {token}",
                    ))

    # --- Pass 3: add research annotations for external → DGC links ---
    for entry in ALL_FIELD_ENTRIES:
        if entry.get("type") == "dgc_internal":
            continue
        nid = id_by_entry.get(entry["id"])
        if not nid:
            continue
        relation = entry.get("relation", "orthogonal")
        conn_type = _RELATION_TO_RESEARCH.get(
            relation, ResearchConnectionType.ORTHOGONAL
        )
        graph.add_annotation(ResearchAnnotation(
            concept_id=nid,
            connection_type=conn_type,
            external_source=entry.get("source", ""),
            citation=entry.get("url", ""),
            summary=entry.get("relevance_to_dgc", ""),
            confidence=entry.get("confidence", 0.5),
            field=entry.get("field", ""),
            year=entry.get("year", 2026),
        ))

    return graph


# ---------------------------------------------------------------------------
# Cross-dimensional bridge
# ---------------------------------------------------------------------------


def cross_dimensional_edges(
    d3_graph: ConceptGraph,
    d1_graph: ConceptGraph | None = None,
    d2_graph: ConceptGraph | None = None,
) -> list[ConceptEdge]:
    """Create cross-dimensional edges by matching dgc_mapping tokens
    against concept names in D1/D2 graphs.

    Returns the list of new edges (also added to d3_graph).
    """
    new_edges: list[ConceptEdge] = []

    for node in d3_graph.all_nodes():
        mapping_tokens = node.metadata.get("d3_dgc_mapping", [])
        if not mapping_tokens:
            continue

        for token in mapping_tokens:
            # Try D1
            if d1_graph:
                matches = d1_graph.find_by_name(token)
                for m in matches:
                    edge = ConceptEdge(
                        source_id=node.id,
                        target_id=m.id,
                        edge_type=EdgeType.REFERENCES,
                        weight=0.7,
                        evidence=f"D3→D1 cross-dim: {token}",
                        metadata={"cross_dimensional": "D3→D1"},
                    )
                    d3_graph.add_edge(edge)
                    new_edges.append(edge)
            # Try D2
            if d2_graph:
                matches = d2_graph.find_by_name(token)
                for m in matches:
                    edge = ConceptEdge(
                        source_id=node.id,
                        target_id=m.id,
                        edge_type=EdgeType.ANALOGOUS_TO,
                        weight=0.6,
                        evidence=f"D3→D2 cross-dim: {token}",
                        metadata={"cross_dimensional": "D3→D2"},
                    )
                    d3_graph.add_edge(edge)
                    new_edges.append(edge)

    return new_edges


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def _entries_by_relation(relation: str) -> list[dict[str, Any]]:
    return [e for e in ALL_FIELD_ENTRIES if e.get("relation") == relation]


def overlap_report() -> dict[str, Any]:
    """What DGC already implements that also exists externally.

    Overlap = entries with relation 'validates' or 'supersedes'.
    These are external concepts/tools that DGC has equivalent or
    better versions of.
    """
    validates = _entries_by_relation("validates")
    supersedes = _entries_by_relation("supersedes")
    overlapping = validates + supersedes
    return {
        "title": "D3 OVERLAP: DGC capabilities validated by or superseding external work",
        "count": len(overlapping),
        "validated_by_external": [
            {"id": e["id"], "source": e["source"], "dgc_mapping": e.get("dgc_mapping", []),
             "relevance": e.get("relevance_to_dgc", "")}
            for e in validates
        ],
        "dgc_supersedes": [
            {"id": e["id"], "source": e["source"], "dgc_mapping": e.get("dgc_mapping", []),
             "relevance": e.get("relevance_to_dgc", "")}
            for e in supersedes
        ],
    }


def gap_report() -> dict[str, Any]:
    """Capabilities the field has that DGC currently lacks.

    These are integration opportunities and upgrade targets.
    """
    gaps = _entries_by_relation("gap")
    extends = _entries_by_relation("extends")
    return {
        "title": "D3 GAPS: Capabilities DGC lacks or could integrate",
        "hard_gaps": [
            {"id": e["id"], "source": e["source"], "field": e.get("field", ""),
             "relevance": e.get("relevance_to_dgc", "")}
            for e in gaps
        ],
        "integration_opportunities": [
            {"id": e["id"], "source": e["source"], "field": e.get("field", ""),
             "relevance": e.get("relevance_to_dgc", "")}
            for e in extends
        ],
        "hard_gap_count": len(gaps),
        "integration_count": len(extends),
        "total": len(gaps) + len(extends),
    }


def uniqueness_report() -> dict[str, Any]:
    """What DGC has that NO ONE else in the field has.

    These are the defensible moats and genuine innovations.
    """
    unique = _entries_by_relation("unique")
    return {
        "title": "D3 UNIQUENESS: DGC capabilities with no external equivalent",
        "count": len(unique),
        "moats": [
            {"id": e["id"], "source": e["source"],
             "summary": e.get("summary", ""),
             "relevance": e.get("relevance_to_dgc", "")}
            for e in unique
        ],
    }


def competitive_position() -> dict[str, Any]:
    """Full strategic positioning of DGC relative to the field.

    Synthesizes overlap, gaps, uniqueness, and competition into
    a single strategic picture.
    """
    competitors = _entries_by_relation("competes")
    unique = _entries_by_relation("unique")
    gaps = _entries_by_relation("gap")
    validates = _entries_by_relation("validates")
    supersedes = _entries_by_relation("supersedes")
    extends = _entries_by_relation("extends")
    orthogonal = _entries_by_relation("orthogonal")

    total = len(ALL_FIELD_ENTRIES)
    internal = [e for e in ALL_FIELD_ENTRIES if e.get("type") == "dgc_internal"]
    external = total - len(internal)

    # Competitive threats
    threats = []
    for c in competitors:
        threats.append({
            "id": c["id"],
            "source": c["source"],
            "threat_level": "HIGH" if c.get("confidence", 0) >= 0.9 else "MEDIUM",
            "dgc_advantage": c.get("relevance_to_dgc", ""),
        })

    # Domain coverage
    domain_coverage = {}
    for domain_name, entries in FIELD_DOMAINS.items():
        domain_unique = [e for e in entries if e.get("relation") == "unique"]
        domain_gaps = [e for e in entries if e.get("relation") == "gap"]
        domain_validates = [e for e in entries if e.get("relation") in ("validates", "supersedes")]
        domain_coverage[domain_name] = {
            "total": len(entries),
            "unique": len(domain_unique),
            "gaps": len(domain_gaps),
            "validated": len(domain_validates),
            "strength": "STRONG" if len(domain_unique) > 0 or len(domain_validates) > len(domain_gaps)
                       else "NEEDS_WORK" if len(domain_gaps) > 0
                       else "NEUTRAL",
        }

    return {
        "title": "D3 COMPETITIVE POSITION: DGC in the AI Field",
        "summary": {
            "total_field_entries": total,
            "external_entries": external,
            "dgc_internal_entries": len(internal),
            "relation_breakdown": {
                "validates": len(validates),
                "supersedes": len(supersedes),
                "competes": len(competitors),
                "extends": len(extends),
                "orthogonal": len(orthogonal),
                "gap": len(gaps),
                "unique": len(unique),
            },
        },
        "competitive_threats": threats,
        "domain_coverage": domain_coverage,
        "strategic_assessment": {
            "moat_count": len(unique),
            "gap_count": len(gaps),
            "validated_count": len(validates) + len(supersedes),
            "threat_count": len(competitors),
            "overall": (
                "DOMINANT" if len(unique) >= 5 and len(gaps) <= 3
                else "STRONG" if len(unique) >= 3
                else "DEVELOPING"
            ),
        },
    }


# ---------------------------------------------------------------------------
# Full D3 scan
# ---------------------------------------------------------------------------


def full_field_scan(
    d1_graph: ConceptGraph | None = None,
    d2_graph: ConceptGraph | None = None,
) -> dict[str, Any]:
    """Run the complete D3 field intelligence scan.

    Returns:
      - The D3 ConceptGraph
      - Cross-dimensional edge count
      - All four reports
    """
    d3 = build_field_graph()
    cross_edges = cross_dimensional_edges(d3, d1_graph, d2_graph)

    return {
        "d3_graph": d3,
        "graph_stats": {
            "nodes": d3.node_count,
            "edges": d3.edge_count,
            "annotations": d3.annotation_count,
            "cross_dimensional_edges": len(cross_edges),
            "components": len(d3.connected_components()),
            "density": round(d3.density(), 6),
        },
        "overlap": overlap_report(),
        "gaps": gap_report(),
        "uniqueness": uniqueness_report(),
        "competitive_position": competitive_position(),
    }


__all__ = [
    "build_field_graph",
    "cross_dimensional_edges",
    "overlap_report",
    "gap_report",
    "uniqueness_report",
    "competitive_position",
    "full_field_scan",
]
