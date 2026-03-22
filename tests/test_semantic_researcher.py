"""Tests for semantic_researcher.py — external research annotation engine."""

from __future__ import annotations

from dharma_swarm.semantic_gravity import (
    ConceptEdge,
    ConceptGraph,
    ConceptNode,
    EdgeType,
    ResearchAnnotation,
    ResearchConnectionType,
)
from dharma_swarm.semantic_researcher import (
    CATEGORY_TO_FIELDS,
    RESEARCH_CONNECTIONS,
    SemanticResearcher,
    _parse_connection_type,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graph_with_monad() -> ConceptGraph:
    """Graph with a monad concept that should match RESEARCH_CONNECTIONS."""
    g = ConceptGraph()
    n = ConceptNode(
        id="n1",
        name="self_observation_monad",
        source_file="dharma_swarm/monad.py",
        category="mathematical",
        salience=0.9,
        formal_structures=["monad"],
    )
    g.add_node(n)
    return g


def _make_graph_low_salience() -> ConceptGraph:
    g = ConceptGraph()
    n = ConceptNode(
        id="n1",
        name="minor_helper",
        source_file="utils.py",
        category="engineering",
        salience=0.1,
    )
    g.add_node(n)
    return g


def _make_diverse_graph() -> ConceptGraph:
    g = ConceptGraph()
    g.add_node(ConceptNode(
        id="n1", name="coalgebra_system", source_file="coal.py",
        category="mathematical", salience=0.8,
        formal_structures=["coalgebra"],
    ))
    g.add_node(ConceptNode(
        id="n2", name="stigmergy_store", source_file="stig.py",
        category="coordination", salience=0.7,
        formal_structures=["stigmergy"],
    ))
    g.add_node(ConceptNode(
        id="n3", name="low_salience", source_file="low.py",
        category="engineering", salience=0.2,
    ))
    g.add_node(ConceptNode(
        id="n4", name="high_no_struct", source_file="high.py",
        category="philosophical", salience=0.9,
    ))
    return g


# ---------------------------------------------------------------------------
# _parse_connection_type
# ---------------------------------------------------------------------------


class TestParseConnectionType:
    def test_validation(self):
        assert _parse_connection_type("validation") == ResearchConnectionType.VALIDATION

    def test_contradiction(self):
        assert _parse_connection_type("contradiction") == ResearchConnectionType.CONTRADICTION

    def test_orthogonal(self):
        assert _parse_connection_type("orthogonal") == ResearchConnectionType.ORTHOGONAL

    def test_engineering(self):
        assert _parse_connection_type("engineering_grounding") == ResearchConnectionType.ENGINEERING_GROUNDING

    def test_unknown_defaults_validation(self):
        assert _parse_connection_type("unknown") == ResearchConnectionType.VALIDATION

    def test_case_insensitive(self):
        assert _parse_connection_type("VALIDATION") == ResearchConnectionType.VALIDATION


# ---------------------------------------------------------------------------
# RESEARCH_CONNECTIONS constants
# ---------------------------------------------------------------------------


class TestResearchConnections:
    def test_has_monad(self):
        assert "monad" in RESEARCH_CONNECTIONS
        assert len(RESEARCH_CONNECTIONS["monad"]) >= 2

    def test_has_stigmergy(self):
        assert "stigmergy" in RESEARCH_CONNECTIONS

    def test_has_sheaf(self):
        assert "sheaf" in RESEARCH_CONNECTIONS

    def test_entries_have_required_fields(self):
        for key, connections in RESEARCH_CONNECTIONS.items():
            for conn in connections:
                assert "source" in conn, f"{key} missing source"
                assert "field" in conn, f"{key} missing field"
                assert "type" in conn, f"{key} missing type"
                assert "summary" in conn, f"{key} missing summary"


class TestCategoryToFields:
    def test_known_categories(self):
        assert "mathematical" in CATEGORY_TO_FIELDS
        assert "philosophical" in CATEGORY_TO_FIELDS
        assert "engineering" in CATEGORY_TO_FIELDS

    def test_values_are_lists(self):
        for cat, fields in CATEGORY_TO_FIELDS.items():
            assert isinstance(fields, list)
            assert len(fields) >= 1


# ---------------------------------------------------------------------------
# SemanticResearcher
# ---------------------------------------------------------------------------


class TestSemanticResearcherInit:
    def test_defaults(self):
        r = SemanticResearcher()
        assert r._salience_threshold == 0.4
        assert r._max_per_concept == 5

    def test_custom(self):
        r = SemanticResearcher(salience_threshold=0.6, max_annotations_per_concept=3)
        assert r._salience_threshold == 0.6
        assert r._max_per_concept == 3


class TestAnnotateGraph:
    def test_monad_gets_annotations(self):
        g = _make_graph_with_monad()
        r = SemanticResearcher()
        annotations = r.annotate_graph(g)
        assert len(annotations) >= 2
        # Should be monad-related
        assert all(a.concept_id == "n1" for a in annotations)

    def test_low_salience_skipped(self):
        g = _make_graph_low_salience()
        r = SemanticResearcher()
        annotations = r.annotate_graph(g)
        assert len(annotations) == 0

    def test_diverse_graph(self):
        g = _make_diverse_graph()
        r = SemanticResearcher()
        annotations = r.annotate_graph(g)
        # coalgebra and stigmergy should get formal-structure matches
        # high_no_struct should get category-level matches
        # low_salience should be skipped
        concept_ids = {a.concept_id for a in annotations}
        assert "n1" in concept_ids  # coalgebra
        assert "n2" in concept_ids  # stigmergy
        assert "n3" not in concept_ids  # low salience

    def test_custom_threshold(self):
        g = _make_diverse_graph()
        r = SemanticResearcher()
        annotations = r.annotate_graph(g, salience_threshold=0.75)
        # Only n1 (0.8) and n4 (0.9) meet 0.75 threshold
        concept_ids = {a.concept_id for a in annotations}
        assert "n2" not in concept_ids  # 0.7 < 0.75


class TestAnnotateConcept:
    def test_monad_concept(self):
        node = ConceptNode(
            id="n1", name="monad", source_file="m.py",
            category="mathematical", salience=0.9,
            formal_structures=["monad"],
        )
        r = SemanticResearcher()
        annotations = r.annotate_concept(node)
        assert len(annotations) >= 2
        assert all(isinstance(a, ResearchAnnotation) for a in annotations)
        # Should be sorted by confidence descending
        confs = [a.confidence for a in annotations]
        assert confs == sorted(confs, reverse=True)

    def test_no_matches(self):
        node = ConceptNode(
            id="n1", name="obscure", source_file="x.py",
            category="unknown_category", salience=0.9,
            formal_structures=["nonexistent_structure"],
        )
        r = SemanticResearcher()
        annotations = r.annotate_concept(node)
        # No formal match, no category match → empty
        assert len(annotations) == 0

    def test_category_fallback(self):
        """Concepts with no formal structures get category-level annotations."""
        node = ConceptNode(
            id="n1", name="abstract_concept", source_file="x.py",
            category="philosophical", salience=0.9,
        )
        r = SemanticResearcher()
        annotations = r.annotate_concept(node)
        # Should get category-level annotations
        assert len(annotations) >= 1
        assert all(
            a.metadata.get("matched_via") == "category" for a in annotations
        )

    def test_max_per_concept(self):
        node = ConceptNode(
            id="n1", name="complex", source_file="c.py",
            category="mathematical", salience=0.9,
            formal_structures=["monad", "sheaf", "coalgebra", "entropy", "fisher_metric"],
        )
        r = SemanticResearcher(max_annotations_per_concept=3)
        annotations = r.annotate_concept(node)
        assert len(annotations) <= 3


class TestResearchGaps:
    def test_concept_without_annotations(self):
        g = ConceptGraph()
        g.add_node(ConceptNode(
            id="n1", name="unmapped", source_file="u.py",
            category="philosophical", salience=0.8,
        ))
        r = SemanticResearcher()
        gaps = r.research_gaps(g)
        assert len(gaps) == 1
        assert gaps[0]["name"] == "unmapped"

    def test_annotated_concept_not_in_gaps(self):
        g = ConceptGraph()
        g.add_node(ConceptNode(
            id="n1", name="mapped", source_file="m.py",
            category="mathematical", salience=0.8,
        ))
        g.add_annotation(ResearchAnnotation(
            concept_id="n1",
            connection_type=ResearchConnectionType.VALIDATION,
            external_source="test",
            summary="test annotation",
        ))
        r = SemanticResearcher()
        gaps = r.research_gaps(g)
        assert len(gaps) == 0


class TestCoverageReport:
    def test_empty_graph(self):
        g = ConceptGraph()
        r = SemanticResearcher()
        report = r.coverage_report(g)
        assert report["total_concepts"] == 0
        assert report["annotated_concepts"] == 0
        assert report["coverage_pct"] == 0

    def test_partial_coverage(self):
        g = ConceptGraph()
        g.add_node(ConceptNode(
            id="n1", name="a", source_file="a.py", category="x", salience=0.8,
        ))
        g.add_node(ConceptNode(
            id="n2", name="b", source_file="b.py", category="y", salience=0.9,
        ))
        g.add_annotation(ResearchAnnotation(
            concept_id="n1",
            connection_type=ResearchConnectionType.VALIDATION,
            external_source="test",
            summary="x",
            field="test_field",
        ))
        r = SemanticResearcher()
        report = r.coverage_report(g)
        assert report["total_concepts"] == 2
        assert report["annotated_concepts"] == 1
        assert report["coverage_pct"] == 50.0
        assert report["total_annotations"] == 1
        assert "test_field" in report["by_field"]
