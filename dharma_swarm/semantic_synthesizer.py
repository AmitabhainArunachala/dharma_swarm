"""Semantic synthesizer — engineering-grade file cluster generation.

Phase 3 of the Semantic Evolution Engine.  Takes a :class:`ConceptGraph`
with research annotations and generates :class:`FileClusterSpec` objects
that ground philosophical intersections in running code.

A file cluster is:
  - 3-7 files forming a self-contained semantic unit
  - One core concept file (.py with running code)
  - One grounding spec (.md with formal claims)
  - One test file
  - 0-4 satellite files

The synthesizer identifies concept intersections that lack engineering
grounding, then produces cluster specifications that a code generator
(or the Darwin Engine) can materialize into real files.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from itertools import combinations
from typing import Any, Sequence

from dharma_swarm.semantic_gravity import (
    ClusterFileSpec,
    ConceptEdge,
    ConceptGraph,
    ConceptNode,
    EdgeType,
    FileClusterSpec,
    ResearchAnnotation,
    ResearchConnectionType,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Intersection detection
# ---------------------------------------------------------------------------


class ConceptIntersection:
    """A pair or group of concepts that share formal structure or research."""

    def __init__(
        self,
        concepts: list[ConceptNode],
        shared_structures: list[str],
        shared_annotations: list[ResearchAnnotation],
        intersection_score: float,
    ) -> None:
        self.concepts = concepts
        self.shared_structures = shared_structures
        self.shared_annotations = shared_annotations
        self.score = intersection_score

    @property
    def name(self) -> str:
        names = sorted(set(c.name for c in self.concepts))
        return " × ".join(names[:3])

    @property
    def concept_ids(self) -> list[str]:
        return [c.id for c in self.concepts]


def find_intersections(
    graph: ConceptGraph,
    *,
    min_shared: int = 1,
    max_results: int = 20,
) -> list[ConceptIntersection]:
    """Find concept intersections that could generate file clusters.

    An intersection is a pair of concepts that:
    - Share at least one formal structure, OR
    - Share research annotations in the same field, OR
    - Are connected by an edge AND both have high salience

    Returns intersections sorted by score descending.
    """
    intersections: list[ConceptIntersection] = []
    nodes = graph.high_salience_nodes(threshold=0.4)

    # Strategy 1: Concepts sharing formal structures
    structure_groups: dict[str, list[ConceptNode]] = defaultdict(list)
    for node in nodes:
        for struct in node.formal_structures:
            structure_groups[struct].append(node)

    seen_pairs: set[tuple[str, str]] = set()
    for struct, group in structure_groups.items():
        if len(group) < 2:
            continue
        for a, b in combinations(group, 2):
            pair = (min(a.id, b.id), max(a.id, b.id))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            shared_structs = list(
                set(a.formal_structures) & set(b.formal_structures)
            )
            shared_anns = _shared_annotations(graph, a, b)
            score = (
                len(shared_structs) * 0.4
                + len(shared_anns) * 0.3
                + (a.salience + b.salience) * 0.15
            )
            intersections.append(ConceptIntersection(
                concepts=[a, b],
                shared_structures=shared_structs,
                shared_annotations=shared_anns,
                intersection_score=score,
            ))

    # Strategy 2: Connected high-salience concepts across different files
    for edge in graph.all_edges():
        if edge.edge_type in (EdgeType.IMPORTS, EdgeType.REFERENCES):
            src = graph.get_node(edge.source_id)
            tgt = graph.get_node(edge.target_id)
            if (
                src and tgt
                and src.source_file != tgt.source_file
                and src.salience >= 0.5
                and tgt.salience >= 0.5
            ):
                pair = (min(src.id, tgt.id), max(src.id, tgt.id))
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    shared_anns = _shared_annotations(graph, src, tgt)
                    score = (
                        edge.weight * 0.3
                        + len(shared_anns) * 0.3
                        + (src.salience + tgt.salience) * 0.2
                    )
                    intersections.append(ConceptIntersection(
                        concepts=[src, tgt],
                        shared_structures=[],
                        shared_annotations=shared_anns,
                        intersection_score=score,
                    ))

    intersections.sort(key=lambda x: x.score, reverse=True)
    return intersections[:max_results]


def _shared_annotations(
    graph: ConceptGraph,
    a: ConceptNode,
    b: ConceptNode,
) -> list[ResearchAnnotation]:
    """Find annotations that connect to the same research field."""
    a_anns = graph.annotations_for(a.id)
    b_anns = graph.annotations_for(b.id)
    a_fields = {ann.field for ann in a_anns if ann.field}
    shared = [ann for ann in b_anns if ann.field in a_fields]
    return shared


# ---------------------------------------------------------------------------
# Cluster specification generator
# ---------------------------------------------------------------------------


def _cluster_name(intersection: ConceptIntersection) -> str:
    """Generate a descriptive name for a cluster."""
    parts: list[str] = []
    if intersection.shared_structures:
        parts.append(intersection.shared_structures[0].replace("_", " ").title())
    for c in intersection.concepts[:2]:
        parts.append(c.name.replace("_", " ").title())
    return " — ".join(parts[:3])


def _cluster_description(intersection: ConceptIntersection) -> str:
    """Generate a description explaining what the cluster grounds."""
    concepts = ", ".join(c.name for c in intersection.concepts)
    structures = ", ".join(intersection.shared_structures) if intersection.shared_structures else "shared research"
    fields = ", ".join(set(a.field for a in intersection.shared_annotations if a.field))
    desc = f"Grounds the intersection of [{concepts}] via [{structures}]"
    if fields:
        desc += f" connected to research in [{fields}]"
    return desc


def _generate_cluster_files(
    intersection: ConceptIntersection,
    cluster_name: str,
) -> list[ClusterFileSpec]:
    """Generate file specifications for a cluster."""
    # Sanitize name for file paths
    slug = cluster_name.lower().replace(" — ", "_").replace(" ", "_").replace("-", "_")
    slug = "".join(c for c in slug if c.isalnum() or c == "_")[:40]

    files: list[ClusterFileSpec] = []

    # 1. Core concept file (Python)
    source_modules = list(set(
        c.source_file for c in intersection.concepts if c.source_file
    ))
    files.append(ClusterFileSpec(
        path=f"dharma_swarm/{slug}.py",
        file_type="python",
        purpose=f"Core implementation grounding {intersection.name}",
        imports_from=source_modules[:5],
        cross_references=[c.name for c in intersection.concepts],
    ))

    # 2. Grounding spec (Markdown)
    files.append(ClusterFileSpec(
        path=f"docs/clusters/{slug}_spec.md",
        file_type="markdown",
        purpose=f"Formal claims and grounding spec for {intersection.name}",
        cross_references=[c.name for c in intersection.concepts],
    ))

    # 3. Test file
    files.append(ClusterFileSpec(
        path=f"tests/test_{slug}.py",
        file_type="test",
        purpose=f"Tests validating the {intersection.name} cluster",
        imports_from=[f"dharma_swarm/{slug}.py"],
    ))

    # 4. Research bridge file (if cluster has research annotations)
    if intersection.shared_annotations:
        files.append(ClusterFileSpec(
            path=f"docs/clusters/{slug}_research.md",
            file_type="markdown",
            purpose=f"Research connections for {intersection.name}",
            cross_references=[
                a.external_source for a in intersection.shared_annotations[:5]
            ],
        ))

    return files


# ---------------------------------------------------------------------------
# SemanticSynthesizer
# ---------------------------------------------------------------------------


class SemanticSynthesizer:
    """Generates file cluster specifications from concept intersections.

    Usage::

        synthesizer = SemanticSynthesizer()
        clusters = synthesizer.synthesize(graph)
        for cluster in clusters:
            gravity.register_cluster(cluster)
    """

    def __init__(
        self,
        *,
        max_clusters: int = 10,
        min_intersection_score: float = 0.3,
    ) -> None:
        self._max_clusters = max_clusters
        self._min_score = min_intersection_score

    def synthesize(
        self,
        graph: ConceptGraph,
        *,
        max_clusters: int | None = None,
    ) -> list[FileClusterSpec]:
        """Generate cluster specifications from the concept graph.

        Returns a list of :class:`FileClusterSpec` objects ready for
        registration with :class:`SemanticGravity`.
        """
        cap = max_clusters or self._max_clusters
        intersections = find_intersections(graph, max_results=cap * 2)

        clusters: list[FileClusterSpec] = []
        used_concepts: set[str] = set()

        for intersection in intersections:
            if len(clusters) >= cap:
                break
            if intersection.score < self._min_score:
                continue

            # Avoid over-clustering the same concepts
            concept_ids = set(intersection.concept_ids)
            if concept_ids & used_concepts:
                continue

            name = _cluster_name(intersection)
            description = _cluster_description(intersection)
            files = _generate_cluster_files(intersection, name)

            cluster = FileClusterSpec(
                name=name,
                description=description,
                core_concepts=intersection.concept_ids,
                research_annotations=[
                    a.id for a in intersection.shared_annotations
                ],
                files=files,
                intersection_type=(
                    "formal_structure"
                    if intersection.shared_structures
                    else "cross_file_connection"
                ),
            )
            clusters.append(cluster)
            used_concepts.update(concept_ids)

        logger.info(
            "Synthesizer produced %d cluster specs from %d intersections",
            len(clusters),
            len(intersections),
        )
        return clusters

    def gap_analysis(self, graph: ConceptGraph) -> dict[str, Any]:
        """Identify categories and structures with no cluster coverage."""
        all_intersections = find_intersections(graph, max_results=50)

        covered_structures: set[str] = set()
        covered_categories: set[str] = set()
        for inter in all_intersections:
            covered_structures.update(inter.shared_structures)
            for c in inter.concepts:
                covered_categories.add(c.category)

        all_structures: set[str] = set()
        all_categories: set[str] = set()
        for node in graph.all_nodes():
            all_structures.update(node.formal_structures)
            if node.category:
                all_categories.add(node.category)

        return {
            "total_intersections": len(all_intersections),
            "structures_covered": sorted(covered_structures),
            "structures_uncovered": sorted(all_structures - covered_structures),
            "categories_covered": sorted(covered_categories),
            "categories_uncovered": sorted(all_categories - covered_categories),
            "top_intersections": [
                {"name": i.name, "score": round(i.score, 3)}
                for i in all_intersections[:10]
            ],
        }


__all__ = [
    "ConceptIntersection",
    "SemanticSynthesizer",
    "find_intersections",
]
