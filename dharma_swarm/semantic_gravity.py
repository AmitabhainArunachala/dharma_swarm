"""Semantic gravity — concept graph, file clusters, and lattice tightening.

The gravitational core of the Semantic Evolution Engine.  Dense clusters
of interconnected concepts attract related ideas, form bridges, and
tighten the semantic lattice over successive iterations.

Data structures:
  ConceptNode     — a named idea extracted from a source file
  ConceptEdge     — a typed relationship between two concepts
  ConceptGraph    — the full lattice of concepts and relationships
  FileCluster     — a self-contained group of semantically linked files
  HardeningReport — multi-angle quality verdict for a cluster
  SemanticGravity — measures cluster coherence and drives lattice tightening

The gravity metaphor: concept count × cross-reference count × hardening
score = gravitational mass.  Dense clusters become attractors that pull
the lattice inward.  Weak clusters decay like stigmergic marks.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from statistics import mean, stdev
from typing import Any, Mapping, Sequence

from pydantic import BaseModel, Field

from dharma_swarm.models import GateResult, _new_id, _utc_now

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EdgeType(str, Enum):
    """Typed relationship between two concepts."""

    DEPENDS_ON = "depends_on"
    IMPLEMENTS = "implements"
    EXTENDS = "extends"
    CONTRADICTS = "contradicts"
    ANALOGOUS_TO = "analogous_to"
    IMPORTS = "imports"
    REFERENCES = "references"
    GROUNDS = "grounds"  # philosophical concept grounded in engineering
    IS_A = "is_a"
    ENABLES = "enables"


class HardeningAngle(str, Enum):
    """The six angles of semantic hardening."""

    MATHEMATICAL = "mathematical"
    COMPUTATIONAL = "computational"
    ENGINEERING = "engineering"
    CONTEXT_ENGINEERING = "context_engineering"
    SWARM_DYNAMICS = "swarm_dynamics"
    BEHAVIORAL_HEALTH = "behavioral_health"


class ResearchConnectionType(str, Enum):
    """How an internal concept connects to external research."""

    VALIDATION = "validation"
    CONTRADICTION = "contradiction"
    ORTHOGONAL = "orthogonal"
    ENGINEERING_GROUNDING = "engineering_grounding"


# ---------------------------------------------------------------------------
# Core data models
# ---------------------------------------------------------------------------


class ConceptNode(BaseModel):
    """A named idea extracted from a source file."""

    id: str = Field(default_factory=_new_id)
    name: str
    definition: str = ""
    source_file: str = ""
    source_line: int = 0
    category: str = ""  # "mathematical", "philosophical", "engineering", "measurement"
    claims: list[str] = Field(default_factory=list)
    formal_structures: list[str] = Field(default_factory=list)
    salience: float = 0.5
    semantic_density: float = 0.0
    behavioral_entropy: float = 0.0
    behavioral_complexity: float = 0.0
    recognition_type: str = "NONE"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)


class ConceptEdge(BaseModel):
    """A typed relationship between two concept nodes."""

    id: str = Field(default_factory=_new_id)
    source_id: str
    target_id: str
    edge_type: EdgeType
    weight: float = 1.0
    evidence: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchAnnotation(BaseModel):
    """Links an internal concept to external research."""

    id: str = Field(default_factory=_new_id)
    concept_id: str
    connection_type: ResearchConnectionType
    external_source: str = ""
    citation: str = ""
    summary: str = ""
    confidence: float = 0.5
    field: str = ""  # "multi-agent systems", "category theory", "mech-interp", etc.
    year: int = 2026
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)


class AngleVerdict(BaseModel):
    """Result of one hardening angle check."""

    angle: HardeningAngle
    result: GateResult
    score: float = 0.0
    details: str = ""
    gaps: list[str] = Field(default_factory=list)


class HardeningReport(BaseModel):
    """Multi-angle quality verdict for a file cluster."""

    id: str = Field(default_factory=_new_id)
    cluster_id: str
    verdicts: list[AngleVerdict] = Field(default_factory=list)
    overall_score: float = 0.0
    semantic_density: float = 0.0
    passed: bool = False
    iteration: int = 0
    gaps_identified: list[str] = Field(default_factory=list)
    suggested_refinements: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=_utc_now)

    @property
    def pass_count(self) -> int:
        return sum(1 for v in self.verdicts if v.result == GateResult.PASS)

    @property
    def fail_count(self) -> int:
        return sum(1 for v in self.verdicts if v.result == GateResult.FAIL)

    @property
    def warn_count(self) -> int:
        return sum(1 for v in self.verdicts if v.result == GateResult.WARN)


class FileClusterSpec(BaseModel):
    """Specification for a group of semantically linked files."""

    id: str = Field(default_factory=_new_id)
    name: str
    description: str = ""
    core_concepts: list[str] = Field(default_factory=list)  # concept node IDs
    research_annotations: list[str] = Field(default_factory=list)  # annotation IDs
    files: list[ClusterFileSpec] = Field(default_factory=list)
    intersection_type: str = ""  # what conceptual gap or intersection this addresses
    gravitational_mass: float = 0.0
    hardening_score: float = 0.0
    iteration: int = 0
    created_at: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClusterFileSpec(BaseModel):
    """Specification for a single file within a cluster."""

    path: str
    file_type: str = "python"  # "python", "markdown", "test", "spec"
    purpose: str = ""
    imports_from: list[str] = Field(default_factory=list)
    cross_references: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# ConceptGraph
# ---------------------------------------------------------------------------


class ConceptGraph:
    """The full lattice of concepts and their relationships.

    Nodes are :class:`ConceptNode` instances, edges are :class:`ConceptEdge`.
    Supports efficient lookup by name, source file, category, and neighbor
    traversal.  Serializable to/from JSON for persistence.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, ConceptNode] = {}
        self._edges: dict[str, ConceptEdge] = {}
        self._annotations: dict[str, ResearchAnnotation] = {}
        # Indices
        self._by_name: dict[str, list[str]] = defaultdict(list)
        self._by_file: dict[str, list[str]] = defaultdict(list)
        self._by_category: dict[str, list[str]] = defaultdict(list)
        self._outgoing: dict[str, list[str]] = defaultdict(list)
        self._incoming: dict[str, list[str]] = defaultdict(list)
        self._annotations_by_concept: dict[str, list[str]] = defaultdict(list)

    # -- nodes ---------------------------------------------------------------

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return len(self._edges)

    @property
    def annotation_count(self) -> int:
        return len(self._annotations)

    def add_node(self, node: ConceptNode) -> str:
        """Add a concept node and update indices.  Returns the node id."""
        self._nodes[node.id] = node
        self._by_name[node.name.lower()].append(node.id)
        if node.source_file:
            self._by_file[node.source_file].append(node.id)
        if node.category:
            self._by_category[node.category].append(node.id)
        return node.id

    def get_node(self, node_id: str) -> ConceptNode | None:
        return self._nodes.get(node_id)

    def find_by_name(self, name: str) -> list[ConceptNode]:
        """Case-insensitive name lookup."""
        ids = self._by_name.get(name.lower(), [])
        return [self._nodes[nid] for nid in ids if nid in self._nodes]

    def find_by_file(self, source_file: str) -> list[ConceptNode]:
        ids = self._by_file.get(source_file, [])
        return [self._nodes[nid] for nid in ids if nid in self._nodes]

    def find_by_category(self, category: str) -> list[ConceptNode]:
        ids = self._by_category.get(category, [])
        return [self._nodes[nid] for nid in ids if nid in self._nodes]

    def all_nodes(self) -> list[ConceptNode]:
        return list(self._nodes.values())

    def high_salience_nodes(self, threshold: float = 0.7) -> list[ConceptNode]:
        """Return nodes with salience >= threshold, sorted descending."""
        nodes = [n for n in self._nodes.values() if n.salience >= threshold]
        nodes.sort(key=lambda n: n.salience, reverse=True)
        return nodes

    # -- edges ---------------------------------------------------------------

    def add_edge(self, edge: ConceptEdge) -> str:
        """Add a concept edge and update adjacency indices."""
        self._edges[edge.id] = edge
        self._outgoing[edge.source_id].append(edge.id)
        self._incoming[edge.target_id].append(edge.id)
        return edge.id

    def get_edge(self, edge_id: str) -> ConceptEdge | None:
        return self._edges.get(edge_id)

    def neighbors(self, node_id: str) -> list[ConceptNode]:
        """Return all nodes directly connected to node_id (both directions)."""
        neighbor_ids: set[str] = set()
        for eid in self._outgoing.get(node_id, []):
            edge = self._edges.get(eid)
            if edge:
                neighbor_ids.add(edge.target_id)
        for eid in self._incoming.get(node_id, []):
            edge = self._edges.get(eid)
            if edge:
                neighbor_ids.add(edge.source_id)
        return [self._nodes[nid] for nid in neighbor_ids if nid in self._nodes]

    def edges_from(self, node_id: str) -> list[ConceptEdge]:
        return [
            self._edges[eid]
            for eid in self._outgoing.get(node_id, [])
            if eid in self._edges
        ]

    def edges_to(self, node_id: str) -> list[ConceptEdge]:
        return [
            self._edges[eid]
            for eid in self._incoming.get(node_id, [])
            if eid in self._edges
        ]

    def all_edges(self) -> list[ConceptEdge]:
        return list(self._edges.values())

    # -- annotations ---------------------------------------------------------

    def add_annotation(self, annotation: ResearchAnnotation) -> str:
        self._annotations[annotation.id] = annotation
        self._annotations_by_concept[annotation.concept_id].append(annotation.id)
        return annotation.id

    def get_annotation(self, annotation_id: str) -> ResearchAnnotation | None:
        return self._annotations.get(annotation_id)

    def annotations_for(self, concept_id: str) -> list[ResearchAnnotation]:
        ids = self._annotations_by_concept.get(concept_id, [])
        return [self._annotations[aid] for aid in ids if aid in self._annotations]

    def all_annotations(self) -> list[ResearchAnnotation]:
        return list(self._annotations.values())

    # -- graph metrics -------------------------------------------------------

    def degree(self, node_id: str) -> int:
        return len(self._outgoing.get(node_id, [])) + len(
            self._incoming.get(node_id, [])
        )

    def density(self) -> float:
        """Graph density: edges / max_possible_edges."""
        n = len(self._nodes)
        if n < 2:
            return 0.0
        return len(self._edges) / (n * (n - 1))

    def connected_components(self) -> list[set[str]]:
        """Return connected components as sets of node IDs (undirected)."""
        visited: set[str] = set()
        components: list[set[str]] = []
        adjacency: dict[str, set[str]] = defaultdict(set)
        for edge in self._edges.values():
            adjacency[edge.source_id].add(edge.target_id)
            adjacency[edge.target_id].add(edge.source_id)
        for nid in self._nodes:
            if nid in visited:
                continue
            component: set[str] = set()
            stack = [nid]
            while stack:
                current = stack.pop()
                if current in visited:
                    continue
                visited.add(current)
                component.add(current)
                stack.extend(adjacency.get(current, set()) - visited)
            components.append(component)
        return components

    def shared_concepts(
        self, file_a: str, file_b: str
    ) -> list[tuple[ConceptNode, ConceptNode, ConceptEdge]]:
        """Return concept pairs connected across two files."""
        nodes_a = {n.id for n in self.find_by_file(file_a)}
        nodes_b = {n.id for n in self.find_by_file(file_b)}
        result: list[tuple[ConceptNode, ConceptNode, ConceptEdge]] = []
        for edge in self._edges.values():
            if edge.source_id in nodes_a and edge.target_id in nodes_b:
                src = self._nodes.get(edge.source_id)
                tgt = self._nodes.get(edge.target_id)
                if src and tgt:
                    result.append((src, tgt, edge))
            elif edge.source_id in nodes_b and edge.target_id in nodes_a:
                src = self._nodes.get(edge.source_id)
                tgt = self._nodes.get(edge.target_id)
                if src and tgt:
                    result.append((src, tgt, edge))
        return result

    # -- serialization -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [n.model_dump(mode="json") for n in self._nodes.values()],
            "edges": [e.model_dump(mode="json") for e in self._edges.values()],
            "annotations": [
                a.model_dump(mode="json") for a in self._annotations.values()
            ],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ConceptGraph:
        graph = cls()
        for raw in data.get("nodes", []):
            graph.add_node(ConceptNode.model_validate(raw))
        for raw in data.get("edges", []):
            graph.add_edge(ConceptEdge.model_validate(raw))
        for raw in data.get("annotations", []):
            graph.add_annotation(ResearchAnnotation.model_validate(raw))
        return graph

    async def save(self, path: Path) -> None:
        """Persist the graph to a JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        import aiofiles

        async with aiofiles.open(path, "w") as f:
            await f.write(json.dumps(self.to_dict(), indent=2, default=str))

    @classmethod
    async def load(cls, path: Path) -> ConceptGraph:
        """Load a graph from a JSON file."""
        if not path.exists():
            return cls()
        import aiofiles

        async with aiofiles.open(path, "r") as f:
            data = json.loads(await f.read())
        return cls.from_dict(data)


# ---------------------------------------------------------------------------
# SemanticGravity
# ---------------------------------------------------------------------------


class GravitySnapshot(BaseModel):
    """State of the semantic lattice at one point in time."""

    timestamp: datetime = Field(default_factory=_utc_now)
    total_nodes: int = 0
    total_edges: int = 0
    total_annotations: int = 0
    total_clusters: int = 0
    mean_density: float = 0.0
    mean_hardening_score: float = 0.0
    component_count: int = 0
    largest_component_size: int = 0
    h1_obstruction_count: int = 0
    convergence_score: float = 0.0


class SemanticGravity:
    """Measures cluster coherence and drives lattice tightening.

    Gravity mechanics:
    - Density = concept_count × cross_ref_count × hardening_score
    - Dense clusters attract related concepts
    - Weak clusters decay
    - Convergence when H¹ obstructions stabilize and mean hardening > threshold
    """

    def __init__(
        self,
        graph: ConceptGraph,
        *,
        decay_threshold: float = 0.2,
        bridge_threshold: int = 3,
        convergence_window: int = 10,
        convergence_variance: float = 0.01,
    ) -> None:
        self._graph = graph
        self._decay_threshold = decay_threshold
        self._bridge_threshold = bridge_threshold
        self._convergence_window = convergence_window
        self._convergence_variance = convergence_variance
        self._snapshots: list[GravitySnapshot] = []
        self._clusters: dict[str, FileClusterSpec] = {}
        self._hardening_reports: dict[str, list[HardeningReport]] = defaultdict(list)

    @property
    def graph(self) -> ConceptGraph:
        return self._graph

    @property
    def cluster_count(self) -> int:
        return len(self._clusters)

    def register_cluster(self, cluster: FileClusterSpec) -> None:
        self._clusters[cluster.id] = cluster

    def record_hardening(self, report: HardeningReport) -> None:
        self._hardening_reports[report.cluster_id].append(report)
        cluster = self._clusters.get(report.cluster_id)
        if cluster is not None:
            cluster.hardening_score = report.overall_score
            cluster.iteration = report.iteration

    def get_cluster(self, cluster_id: str) -> FileClusterSpec | None:
        return self._clusters.get(cluster_id)

    def all_clusters(self) -> list[FileClusterSpec]:
        return list(self._clusters.values())

    def hardening_history(self, cluster_id: str) -> list[HardeningReport]:
        return list(self._hardening_reports.get(cluster_id, []))

    # -- gravity metrics -----------------------------------------------------

    def gravitational_mass(self, cluster: FileClusterSpec) -> float:
        """Compute gravitational mass for a cluster.

        mass = concept_count × cross_ref_count × (hardening_score + 0.1)
        The 0.1 floor prevents zero-mass clusters before hardening.
        """
        concept_count = len(cluster.core_concepts)
        cross_refs = sum(
            len(f.cross_references) + len(f.imports_from) for f in cluster.files
        )
        hardening = max(cluster.hardening_score, 0.0) + 0.1
        mass = concept_count * max(cross_refs, 1) * hardening
        cluster.gravitational_mass = mass
        return mass

    def should_decay(self, cluster: FileClusterSpec) -> bool:
        """Return True if the cluster should decay (mass below threshold)."""
        mass = self.gravitational_mass(cluster)
        return mass < self._decay_threshold

    def bridge_candidates(self) -> list[tuple[FileClusterSpec, FileClusterSpec, int]]:
        """Find cluster pairs that share enough concepts to form a bridge.

        Returns (cluster_a, cluster_b, shared_count) sorted by shared_count
        descending.
        """
        clusters = list(self._clusters.values())
        bridges: list[tuple[FileClusterSpec, FileClusterSpec, int]] = []
        for i, a in enumerate(clusters):
            a_concepts = set(a.core_concepts)
            for b in clusters[i + 1 :]:
                b_concepts = set(b.core_concepts)
                shared = len(a_concepts & b_concepts)
                if shared >= self._bridge_threshold:
                    bridges.append((a, b, shared))
        bridges.sort(key=lambda t: t[2], reverse=True)
        return bridges

    # -- lattice snapshot ----------------------------------------------------

    def snapshot(self, *, h1_count: int = 0) -> GravitySnapshot:
        """Capture the current state of the semantic lattice."""
        components = self._graph.connected_components()
        largest = max((len(c) for c in components), default=0)
        clusters = list(self._clusters.values())
        hardening_scores = [c.hardening_score for c in clusters if c.hardening_score > 0]

        snap = GravitySnapshot(
            total_nodes=self._graph.node_count,
            total_edges=self._graph.edge_count,
            total_annotations=self._graph.annotation_count,
            total_clusters=len(clusters),
            mean_density=self._graph.density(),
            mean_hardening_score=mean(hardening_scores) if hardening_scores else 0.0,
            component_count=len(components),
            largest_component_size=largest,
            h1_obstruction_count=h1_count,
            convergence_score=self._convergence_score(),
        )
        self._snapshots.append(snap)
        return snap

    def _convergence_score(self) -> float:
        """Compute convergence from recent snapshot variance.

        Returns 1.0 when fully converged (variance ≈ 0), 0.0 when divergent.
        """
        if len(self._snapshots) < self._convergence_window:
            return 0.0
        recent = self._snapshots[-self._convergence_window :]
        densities = [s.mean_density for s in recent]
        if len(densities) < 2:
            return 0.0
        var = stdev(densities) ** 2
        return max(0.0, 1.0 - (var / max(self._convergence_variance, 1e-12)))

    def is_converged(self) -> bool:
        """True when lattice has reached a semantic fixed point."""
        if len(self._snapshots) < self._convergence_window:
            return False
        score = self._convergence_score()
        return score > 0.95

    def convergence_trend(self) -> list[float]:
        """Return the convergence score over all snapshots."""
        if len(self._snapshots) < 2:
            return []
        scores: list[float] = []
        for i in range(1, len(self._snapshots)):
            window = self._snapshots[max(0, i - self._convergence_window) : i + 1]
            if len(window) < 2:
                scores.append(0.0)
                continue
            densities = [s.mean_density for s in window]
            var = stdev(densities) ** 2 if len(densities) > 1 else 0.0
            scores.append(max(0.0, 1.0 - (var / max(self._convergence_variance, 1e-12))))
        return scores

    # -- persistence ---------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "graph": self._graph.to_dict(),
            "clusters": [c.model_dump(mode="json") for c in self._clusters.values()],
            "snapshots": [s.model_dump(mode="json") for s in self._snapshots],
            "hardening_reports": {
                cid: [r.model_dump(mode="json") for r in reports]
                for cid, reports in self._hardening_reports.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SemanticGravity:
        graph = ConceptGraph.from_dict(data.get("graph", {}))
        gravity = cls(graph)
        for raw in data.get("clusters", []):
            cluster = FileClusterSpec.model_validate(raw)
            gravity.register_cluster(cluster)
        for raw in data.get("snapshots", []):
            gravity._snapshots.append(GravitySnapshot.model_validate(raw))
        for cid, reports_raw in data.get("hardening_reports", {}).items():
            for raw in reports_raw:
                report = HardeningReport.model_validate(raw)
                gravity._hardening_reports[cid].append(report)
        return gravity

    async def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        import aiofiles

        async with aiofiles.open(path, "w") as f:
            await f.write(json.dumps(self.to_dict(), indent=2, default=str))

    @classmethod
    async def load(cls, path: Path) -> SemanticGravity:
        if not path.exists():
            return cls(ConceptGraph())
        import aiofiles

        async with aiofiles.open(path, "r") as f:
            data = json.loads(await f.read())
        return cls.from_dict(data)


__all__ = [
    "AngleVerdict",
    "ClusterFileSpec",
    "ConceptEdge",
    "ConceptGraph",
    "ConceptNode",
    "EdgeType",
    "FileClusterSpec",
    "GravitySnapshot",
    "HardeningAngle",
    "HardeningReport",
    "ResearchAnnotation",
    "ResearchConnectionType",
    "SemanticGravity",
]
