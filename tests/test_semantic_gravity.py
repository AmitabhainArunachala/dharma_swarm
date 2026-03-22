"""Tests for semantic_gravity.py — concept graph, file clusters, and lattice tightening."""

from __future__ import annotations

import pytest

from dharma_swarm.models import GateResult
from dharma_swarm.semantic_gravity import (
    AngleVerdict,
    ClusterFileSpec,
    ConceptEdge,
    ConceptGraph,
    ConceptNode,
    EdgeType,
    FileClusterSpec,
    GravitySnapshot,
    HardeningAngle,
    HardeningReport,
    ResearchAnnotation,
    ResearchConnectionType,
    SemanticGravity,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_edge_types(self):
        assert EdgeType.DEPENDS_ON.value == "depends_on"
        assert EdgeType.GROUNDS.value == "grounds"
        assert len(EdgeType) >= 10

    def test_hardening_angles(self):
        assert len(HardeningAngle) == 6
        assert HardeningAngle.MATHEMATICAL.value == "mathematical"
        assert HardeningAngle.BEHAVIORAL_HEALTH.value == "behavioral_health"

    def test_research_connection_types(self):
        assert ResearchConnectionType.VALIDATION.value == "validation"
        assert len(ResearchConnectionType) >= 4


# ---------------------------------------------------------------------------
# ConceptNode
# ---------------------------------------------------------------------------


class TestConceptNode:
    def test_construction(self):
        n = ConceptNode(name="autopoiesis")
        assert n.name == "autopoiesis"
        assert n.id != ""
        assert n.salience == 0.5
        assert n.recognition_type == "NONE"

    def test_all_fields(self):
        n = ConceptNode(
            name="R_V",
            definition="Value matrix participation ratio contraction",
            source_file="bridge.py",
            source_line=42,
            category="measurement",
            claims=["R_V < 1.0 indicates contraction"],
            formal_structures=["PR_late / PR_early"],
            salience=0.9,
            behavioral_entropy=0.6,
        )
        assert n.category == "measurement"
        assert n.salience == 0.9
        assert len(n.claims) == 1


# ---------------------------------------------------------------------------
# ConceptEdge
# ---------------------------------------------------------------------------


class TestConceptEdge:
    def test_construction(self):
        e = ConceptEdge(
            source_id="a", target_id="b", edge_type=EdgeType.DEPENDS_ON
        )
        assert e.source_id == "a"
        assert e.target_id == "b"
        assert e.weight == 1.0


# ---------------------------------------------------------------------------
# ResearchAnnotation
# ---------------------------------------------------------------------------


class TestResearchAnnotation:
    def test_construction(self):
        a = ResearchAnnotation(
            concept_id="c1",
            connection_type=ResearchConnectionType.VALIDATION,
            external_source="Friston 2010",
        )
        assert a.concept_id == "c1"
        assert a.confidence == 0.5


# ---------------------------------------------------------------------------
# AngleVerdict / HardeningReport
# ---------------------------------------------------------------------------


class TestAngleVerdict:
    def test_construction(self):
        v = AngleVerdict(
            angle=HardeningAngle.MATHEMATICAL,
            result=GateResult.PASS,
            score=0.85,
        )
        assert v.angle == HardeningAngle.MATHEMATICAL
        assert v.score == 0.85


class TestHardeningReport:
    def test_defaults(self):
        r = HardeningReport(cluster_id="c1")
        assert r.passed is False
        assert r.overall_score == 0.0

    def test_pass_count(self):
        r = HardeningReport(
            cluster_id="c1",
            verdicts=[
                AngleVerdict(
                    angle=HardeningAngle.MATHEMATICAL,
                    result=GateResult.PASS,
                    score=0.9,
                ),
                AngleVerdict(
                    angle=HardeningAngle.COMPUTATIONAL,
                    result=GateResult.FAIL,
                    score=0.2,
                ),
                AngleVerdict(
                    angle=HardeningAngle.ENGINEERING,
                    result=GateResult.WARN,
                    score=0.5,
                ),
            ],
        )
        assert r.pass_count == 1
        assert r.fail_count == 1
        assert r.warn_count == 1


# ---------------------------------------------------------------------------
# FileClusterSpec / ClusterFileSpec
# ---------------------------------------------------------------------------


class TestFileClusterSpec:
    def test_construction(self):
        c = FileClusterSpec(name="test_cluster")
        assert c.name == "test_cluster"
        assert c.gravitational_mass == 0.0

    def test_with_files(self):
        c = FileClusterSpec(
            name="core",
            core_concepts=["c1", "c2"],
            files=[
                ClusterFileSpec(path="dharma_swarm/foo.py", purpose="main module"),
                ClusterFileSpec(path="tests/test_foo.py", file_type="test"),
            ],
        )
        assert len(c.files) == 2
        assert c.files[1].file_type == "test"


# ---------------------------------------------------------------------------
# ConceptGraph
# ---------------------------------------------------------------------------


class TestConceptGraph:
    def _make_graph(self):
        g = ConceptGraph()
        n1 = ConceptNode(id="n1", name="autopoiesis", source_file="varela.py", category="philosophical")
        n2 = ConceptNode(id="n2", name="strange_loop", source_file="hofstadter.py", category="mathematical")
        n3 = ConceptNode(id="n3", name="free_energy", source_file="friston.py", category="mathematical")
        g.add_node(n1)
        g.add_node(n2)
        g.add_node(n3)
        g.add_edge(ConceptEdge(id="e1", source_id="n1", target_id="n2", edge_type=EdgeType.ANALOGOUS_TO))
        g.add_edge(ConceptEdge(id="e2", source_id="n2", target_id="n3", edge_type=EdgeType.ENABLES))
        return g

    def test_node_count(self):
        g = self._make_graph()
        assert g.node_count == 3

    def test_edge_count(self):
        g = self._make_graph()
        assert g.edge_count == 2

    def test_get_node(self):
        g = self._make_graph()
        n = g.get_node("n1")
        assert n is not None
        assert n.name == "autopoiesis"

    def test_get_node_missing(self):
        g = self._make_graph()
        assert g.get_node("nonexistent") is None

    def test_find_by_name(self):
        g = self._make_graph()
        results = g.find_by_name("autopoiesis")
        assert len(results) == 1
        assert results[0].id == "n1"

    def test_find_by_name_case_insensitive(self):
        g = self._make_graph()
        results = g.find_by_name("AUTOPOIESIS")
        assert len(results) == 1

    def test_find_by_file(self):
        g = self._make_graph()
        results = g.find_by_file("friston.py")
        assert len(results) == 1
        assert results[0].name == "free_energy"

    def test_find_by_category(self):
        g = self._make_graph()
        results = g.find_by_category("mathematical")
        assert len(results) == 2

    def test_all_nodes(self):
        g = self._make_graph()
        assert len(g.all_nodes()) == 3

    def test_high_salience_nodes(self):
        g = ConceptGraph()
        g.add_node(ConceptNode(id="a", name="high", salience=0.9))
        g.add_node(ConceptNode(id="b", name="low", salience=0.3))
        g.add_node(ConceptNode(id="c", name="mid", salience=0.7))
        high = g.high_salience_nodes(threshold=0.7)
        assert len(high) == 2
        assert high[0].salience >= high[1].salience

    def test_neighbors(self):
        g = self._make_graph()
        neighbors = g.neighbors("n2")
        ids = {n.id for n in neighbors}
        assert "n1" in ids  # incoming
        assert "n3" in ids  # outgoing

    def test_edges_from(self):
        g = self._make_graph()
        edges = g.edges_from("n1")
        assert len(edges) == 1
        assert edges[0].target_id == "n2"

    def test_edges_to(self):
        g = self._make_graph()
        edges = g.edges_to("n2")
        assert len(edges) == 1
        assert edges[0].source_id == "n1"

    def test_degree(self):
        g = self._make_graph()
        assert g.degree("n2") == 2  # 1 incoming + 1 outgoing
        assert g.degree("n1") == 1  # 1 outgoing
        assert g.degree("n3") == 1  # 1 incoming

    def test_density(self):
        g = self._make_graph()
        # 3 nodes, 2 edges, max = 3*2 = 6
        assert abs(g.density() - 2 / 6) < 0.01

    def test_density_single_node(self):
        g = ConceptGraph()
        g.add_node(ConceptNode(id="a", name="solo"))
        assert g.density() == 0.0

    def test_connected_components(self):
        g = self._make_graph()
        components = g.connected_components()
        assert len(components) == 1
        assert len(components[0]) == 3

    def test_connected_components_disconnected(self):
        g = ConceptGraph()
        g.add_node(ConceptNode(id="a", name="alpha"))
        g.add_node(ConceptNode(id="b", name="beta"))
        # No edges — 2 isolated components
        components = g.connected_components()
        assert len(components) == 2

    def test_shared_concepts(self):
        g = self._make_graph()
        # n1 is in varela.py, n2 in hofstadter.py, edge e1 connects them
        shared = g.shared_concepts("varela.py", "hofstadter.py")
        assert len(shared) == 1
        assert shared[0][2].id == "e1"

    def test_shared_concepts_none(self):
        g = self._make_graph()
        shared = g.shared_concepts("varela.py", "nonexistent.py")
        assert shared == []

    # -- annotations --

    def test_add_and_get_annotation(self):
        g = ConceptGraph()
        g.add_node(ConceptNode(id="c1", name="concept"))
        ann = ResearchAnnotation(
            id="a1",
            concept_id="c1",
            connection_type=ResearchConnectionType.VALIDATION,
        )
        g.add_annotation(ann)
        assert g.annotation_count == 1
        assert g.get_annotation("a1") is not None

    def test_annotations_for_concept(self):
        g = ConceptGraph()
        g.add_node(ConceptNode(id="c1", name="concept"))
        g.add_annotation(
            ResearchAnnotation(
                concept_id="c1",
                connection_type=ResearchConnectionType.VALIDATION,
            )
        )
        g.add_annotation(
            ResearchAnnotation(
                concept_id="c1",
                connection_type=ResearchConnectionType.CONTRADICTION,
            )
        )
        assert len(g.annotations_for("c1")) == 2

    # -- serialization --

    def test_to_dict_and_from_dict(self):
        g = self._make_graph()
        g.add_annotation(
            ResearchAnnotation(
                id="a1",
                concept_id="n1",
                connection_type=ResearchConnectionType.VALIDATION,
            )
        )
        d = g.to_dict()
        assert len(d["nodes"]) == 3
        assert len(d["edges"]) == 2
        assert len(d["annotations"]) == 1

        g2 = ConceptGraph.from_dict(d)
        assert g2.node_count == 3
        assert g2.edge_count == 2
        assert g2.annotation_count == 1

    def test_from_dict_empty(self):
        g = ConceptGraph.from_dict({})
        assert g.node_count == 0


# ---------------------------------------------------------------------------
# SemanticGravity
# ---------------------------------------------------------------------------


class TestSemanticGravity:
    def _make_gravity(self):
        g = ConceptGraph()
        g.add_node(ConceptNode(id="n1", name="alpha", source_file="a.py"))
        g.add_node(ConceptNode(id="n2", name="beta", source_file="b.py"))
        g.add_edge(ConceptEdge(source_id="n1", target_id="n2", edge_type=EdgeType.DEPENDS_ON))
        return SemanticGravity(g)

    def test_cluster_count(self):
        sg = self._make_gravity()
        assert sg.cluster_count == 0

    def test_register_cluster(self):
        sg = self._make_gravity()
        c = FileClusterSpec(id="c1", name="test")
        sg.register_cluster(c)
        assert sg.cluster_count == 1
        assert sg.get_cluster("c1") is not None

    def test_all_clusters(self):
        sg = self._make_gravity()
        sg.register_cluster(FileClusterSpec(id="c1", name="a"))
        sg.register_cluster(FileClusterSpec(id="c2", name="b"))
        assert len(sg.all_clusters()) == 2

    def test_gravitational_mass(self):
        sg = self._make_gravity()
        c = FileClusterSpec(
            id="c1",
            name="test",
            core_concepts=["n1", "n2"],
            files=[
                ClusterFileSpec(
                    path="a.py",
                    cross_references=["beta"],
                    imports_from=["b.py"],
                )
            ],
            hardening_score=0.8,
        )
        mass = sg.gravitational_mass(c)
        # 2 concepts * max(2, 1) * (0.8 + 0.1) = 2 * 2 * 0.9 = 3.6
        assert abs(mass - 3.6) < 0.01

    def test_gravitational_mass_no_hardening(self):
        sg = self._make_gravity()
        c = FileClusterSpec(
            id="c1",
            name="test",
            core_concepts=["n1"],
            files=[ClusterFileSpec(path="a.py")],
        )
        mass = sg.gravitational_mass(c)
        # 1 concept * max(0, 1) * (0.0 + 0.1) = 1 * 1 * 0.1 = 0.1
        assert abs(mass - 0.1) < 0.01

    def test_should_decay(self):
        sg = self._make_gravity()
        c = FileClusterSpec(id="c1", name="weak", core_concepts=["n1"])
        # Mass = 1 * 1 * 0.1 = 0.1 < 0.2 threshold
        assert sg.should_decay(c) is True

    def test_should_not_decay(self):
        sg = self._make_gravity()
        c = FileClusterSpec(
            id="c1",
            name="strong",
            core_concepts=["n1", "n2"],
            files=[ClusterFileSpec(path="a.py", cross_references=["x", "y"])],
            hardening_score=0.5,
        )
        assert sg.should_decay(c) is False

    def test_bridge_candidates(self):
        sg = self._make_gravity()
        c1 = FileClusterSpec(
            id="c1", name="a", core_concepts=["n1", "n2", "n3", "n4"]
        )
        c2 = FileClusterSpec(
            id="c2", name="b", core_concepts=["n2", "n3", "n4", "n5"]
        )
        sg.register_cluster(c1)
        sg.register_cluster(c2)
        bridges = sg.bridge_candidates()
        assert len(bridges) == 1
        assert bridges[0][2] == 3  # 3 shared concepts

    def test_bridge_candidates_below_threshold(self):
        sg = self._make_gravity()
        c1 = FileClusterSpec(id="c1", name="a", core_concepts=["n1", "n2"])
        c2 = FileClusterSpec(id="c2", name="b", core_concepts=["n2", "n3"])
        sg.register_cluster(c1)
        sg.register_cluster(c2)
        # Only 1 shared < threshold of 3
        assert sg.bridge_candidates() == []

    def test_record_hardening(self):
        sg = self._make_gravity()
        c = FileClusterSpec(id="c1", name="test")
        sg.register_cluster(c)
        report = HardeningReport(
            cluster_id="c1", overall_score=0.75, iteration=1
        )
        sg.record_hardening(report)
        assert c.hardening_score == 0.75
        assert c.iteration == 1
        assert len(sg.hardening_history("c1")) == 1

    def test_snapshot(self):
        sg = self._make_gravity()
        snap = sg.snapshot()
        assert isinstance(snap, GravitySnapshot)
        assert snap.total_nodes == 2
        assert snap.total_edges == 1
        assert snap.component_count == 1

    def test_convergence_not_enough_snapshots(self):
        sg = self._make_gravity()
        assert sg.is_converged() is False
        assert sg.convergence_trend() == []

    def test_convergence_with_snapshots(self):
        sg = SemanticGravity(ConceptGraph(), convergence_window=3)
        # Take 5 snapshots (all identical density → should converge)
        for _ in range(5):
            sg.snapshot()
        # With empty graph, density is always 0 → variance = 0 → converged
        assert sg.is_converged() is True

    def test_convergence_trend(self):
        sg = SemanticGravity(ConceptGraph(), convergence_window=3)
        for _ in range(5):
            sg.snapshot()
        trend = sg.convergence_trend()
        assert len(trend) == 4  # n-1 entries

    # -- serialization --

    def test_to_dict_and_from_dict(self):
        sg = self._make_gravity()
        sg.register_cluster(FileClusterSpec(id="c1", name="test"))
        sg.snapshot()
        d = sg.to_dict()
        assert "graph" in d
        assert "clusters" in d
        assert "snapshots" in d

        sg2 = SemanticGravity.from_dict(d)
        assert sg2.graph.node_count == 2
        assert sg2.cluster_count == 1

    def test_from_dict_empty(self):
        sg = SemanticGravity.from_dict({})
        assert sg.graph.node_count == 0
        assert sg.cluster_count == 0
