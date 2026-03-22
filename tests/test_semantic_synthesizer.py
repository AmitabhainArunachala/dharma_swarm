"""Tests for semantic_synthesizer.py — file cluster generation from concept intersections."""

from __future__ import annotations

from dharma_swarm.semantic_gravity import (
    ConceptEdge,
    ConceptGraph,
    ConceptNode,
    EdgeType,
    ResearchAnnotation,
    ResearchConnectionType,
)
from dharma_swarm.semantic_synthesizer import (
    ConceptIntersection,
    SemanticSynthesizer,
    _cluster_description,
    _cluster_name,
    _generate_cluster_files,
    _shared_annotations,
    find_intersections,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_intersection_graph() -> ConceptGraph:
    """Graph with overlapping formal structures for intersection detection."""
    g = ConceptGraph()
    # Two concepts sharing "monad" formal structure
    n1 = ConceptNode(
        id="n1", name="self_observation", source_file="obs.py",
        category="mathematical", salience=0.8,
        formal_structures=["monad", "fixed_point"],
    )
    n2 = ConceptNode(
        id="n2", name="cascading_effect", source_file="casc.py",
        category="mathematical", salience=0.7,
        formal_structures=["monad", "coalgebra"],
    )
    # A concept with no shared structures
    n3 = ConceptNode(
        id="n3", name="dashboard_widget", source_file="dash.py",
        category="engineering", salience=0.5,
    )
    g.add_node(n1)
    g.add_node(n2)
    g.add_node(n3)
    return g


def _make_connected_graph() -> ConceptGraph:
    """Graph with connected high-salience concepts across different files."""
    g = ConceptGraph()
    n1 = ConceptNode(
        id="n1", name="sheaf_topology", source_file="sheaf.py",
        category="mathematical", salience=0.8,
    )
    n2 = ConceptNode(
        id="n2", name="agent_consensus", source_file="consensus.py",
        category="coordination", salience=0.7,
    )
    g.add_node(n1)
    g.add_node(n2)
    g.add_edge(ConceptEdge(
        id="e1", source_id="n1", target_id="n2",
        edge_type=EdgeType.REFERENCES, weight=0.9,
    ))
    return g


# ---------------------------------------------------------------------------
# ConceptIntersection
# ---------------------------------------------------------------------------


class TestConceptIntersection:
    def test_name(self):
        n1 = ConceptNode(id="a", name="alpha", source_file="a.py", category="x", salience=0.5)
        n2 = ConceptNode(id="b", name="beta", source_file="b.py", category="y", salience=0.5)
        ci = ConceptIntersection(
            concepts=[n1, n2],
            shared_structures=["monad"],
            shared_annotations=[],
            intersection_score=0.5,
        )
        assert "alpha" in ci.name
        assert "beta" in ci.name

    def test_concept_ids(self):
        n1 = ConceptNode(id="a", name="x", source_file="f.py", category="c", salience=0.5)
        ci = ConceptIntersection(
            concepts=[n1],
            shared_structures=[],
            shared_annotations=[],
            intersection_score=0.3,
        )
        assert ci.concept_ids == ["a"]

    def test_score(self):
        ci = ConceptIntersection(
            concepts=[],
            shared_structures=[],
            shared_annotations=[],
            intersection_score=0.75,
        )
        assert ci.score == 0.75


# ---------------------------------------------------------------------------
# find_intersections
# ---------------------------------------------------------------------------


class TestFindIntersections:
    def test_shared_formal_structure(self):
        g = _make_intersection_graph()
        intersections = find_intersections(g)
        # n1 and n2 share "monad" → should produce intersection
        assert len(intersections) >= 1
        concept_ids = {c.id for i in intersections for c in i.concepts}
        assert "n1" in concept_ids
        assert "n2" in concept_ids

    def test_connected_concepts(self):
        g = _make_connected_graph()
        intersections = find_intersections(g)
        assert len(intersections) >= 1

    def test_max_results(self):
        g = _make_intersection_graph()
        intersections = find_intersections(g, max_results=1)
        assert len(intersections) <= 1

    def test_sorted_by_score(self):
        g = _make_intersection_graph()
        intersections = find_intersections(g)
        if len(intersections) >= 2:
            scores = [i.score for i in intersections]
            assert scores == sorted(scores, reverse=True)

    def test_empty_graph(self):
        g = ConceptGraph()
        intersections = find_intersections(g)
        assert intersections == []


# ---------------------------------------------------------------------------
# _shared_annotations
# ---------------------------------------------------------------------------


class TestSharedAnnotations:
    def test_shared_field(self):
        g = ConceptGraph()
        n1 = ConceptNode(id="n1", name="a", source_file="a.py", category="x", salience=0.5)
        n2 = ConceptNode(id="n2", name="b", source_file="b.py", category="y", salience=0.5)
        g.add_node(n1)
        g.add_node(n2)
        g.add_annotation(ResearchAnnotation(
            concept_id="n1",
            connection_type=ResearchConnectionType.VALIDATION,
            external_source="paper1",
            summary="x",
            field="topology",
        ))
        g.add_annotation(ResearchAnnotation(
            concept_id="n2",
            connection_type=ResearchConnectionType.ORTHOGONAL,
            external_source="paper2",
            summary="y",
            field="topology",
        ))
        shared = _shared_annotations(g, n1, n2)
        assert len(shared) == 1  # paper2 shares field "topology" with n1

    def test_no_shared(self):
        g = ConceptGraph()
        n1 = ConceptNode(id="n1", name="a", source_file="a.py", category="x", salience=0.5)
        n2 = ConceptNode(id="n2", name="b", source_file="b.py", category="y", salience=0.5)
        g.add_node(n1)
        g.add_node(n2)
        g.add_annotation(ResearchAnnotation(
            concept_id="n1",
            connection_type=ResearchConnectionType.VALIDATION,
            external_source="p1", summary="x", field="algebra",
        ))
        g.add_annotation(ResearchAnnotation(
            concept_id="n2",
            connection_type=ResearchConnectionType.VALIDATION,
            external_source="p2", summary="y", field="topology",
        ))
        shared = _shared_annotations(g, n1, n2)
        assert len(shared) == 0


# ---------------------------------------------------------------------------
# _cluster_name / _cluster_description / _generate_cluster_files
# ---------------------------------------------------------------------------


class TestClusterHelpers:
    def _make_intersection(self):
        n1 = ConceptNode(id="a", name="monad_obs", source_file="m.py", category="math", salience=0.8)
        n2 = ConceptNode(id="b", name="fixed_point", source_file="f.py", category="math", salience=0.7)
        return ConceptIntersection(
            concepts=[n1, n2],
            shared_structures=["monad"],
            shared_annotations=[],
            intersection_score=0.6,
        )

    def test_cluster_name(self):
        ci = self._make_intersection()
        name = _cluster_name(ci)
        assert "Monad" in name

    def test_cluster_description(self):
        ci = self._make_intersection()
        desc = _cluster_description(ci)
        assert "monad_obs" in desc
        assert "fixed_point" in desc

    def test_generate_files(self):
        ci = self._make_intersection()
        name = _cluster_name(ci)
        files = _generate_cluster_files(ci, name)
        assert len(files) >= 3  # .py, _spec.md, test_.py
        types = {f.file_type for f in files}
        assert "python" in types
        assert "markdown" in types
        assert "test" in types

    def test_generate_files_with_annotations(self):
        n1 = ConceptNode(id="a", name="x", source_file="x.py", category="c", salience=0.8)
        ann = ResearchAnnotation(
            concept_id="a",
            connection_type=ResearchConnectionType.VALIDATION,
            external_source="paper1",
            summary="test",
        )
        ci = ConceptIntersection(
            concepts=[n1],
            shared_structures=[],
            shared_annotations=[ann],
            intersection_score=0.5,
        )
        files = _generate_cluster_files(ci, "test cluster")
        # With annotations, should include research file
        assert len(files) == 4


# ---------------------------------------------------------------------------
# SemanticSynthesizer
# ---------------------------------------------------------------------------


class TestSemanticSynthesizer:
    def test_defaults(self):
        s = SemanticSynthesizer()
        assert s._max_clusters == 10
        assert s._min_score == 0.3

    def test_synthesize_produces_clusters(self):
        g = _make_intersection_graph()
        s = SemanticSynthesizer()
        clusters = s.synthesize(g)
        assert len(clusters) >= 1

    def test_synthesize_respects_max(self):
        g = _make_intersection_graph()
        s = SemanticSynthesizer(max_clusters=1)
        clusters = s.synthesize(g)
        assert len(clusters) <= 1

    def test_synthesize_empty_graph(self):
        g = ConceptGraph()
        s = SemanticSynthesizer()
        clusters = s.synthesize(g)
        assert clusters == []

    def test_gap_analysis(self):
        g = _make_intersection_graph()
        s = SemanticSynthesizer()
        gaps = s.gap_analysis(g)
        assert "total_intersections" in gaps
        assert "structures_covered" in gaps
        assert "structures_uncovered" in gaps
        assert "top_intersections" in gaps

    def test_gap_analysis_empty_graph(self):
        g = ConceptGraph()
        s = SemanticSynthesizer()
        gaps = s.gap_analysis(g)
        assert gaps["total_intersections"] == 0
