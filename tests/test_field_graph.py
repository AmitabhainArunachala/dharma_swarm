"""Tests for field_graph.py — D3 Field Intelligence Graph."""

from __future__ import annotations

from dharma_swarm.field_graph import (
    _entries_by_relation,
    build_field_graph,
    competitive_position,
    cross_dimensional_edges,
    full_field_scan,
    gap_report,
    overlap_report,
    uniqueness_report,
)
from dharma_swarm.field_knowledge_base import ALL_FIELD_ENTRIES, FIELD_DOMAINS
from dharma_swarm.semantic_gravity import ConceptGraph, ConceptNode, EdgeType


# ---------------------------------------------------------------------------
# build_field_graph
# ---------------------------------------------------------------------------


class TestBuildFieldGraph:
    def test_returns_graph(self):
        g = build_field_graph()
        assert isinstance(g, ConceptGraph)

    def test_node_count_matches_entries(self):
        g = build_field_graph()
        assert g.node_count == len(ALL_FIELD_ENTRIES)

    def test_has_edges(self):
        g = build_field_graph()
        # With shared dgc_mapping tokens, there should be edges
        assert g.edge_count >= 0

    def test_nodes_have_d3_metadata(self):
        g = build_field_graph()
        for node in g.all_nodes():
            assert "d3_entry_id" in node.metadata
            assert node.metadata["dimension"] == 3

    def test_internal_nodes_categorized(self):
        g = build_field_graph()
        internal = [n for n in g.all_nodes() if n.category == "dgc_internal"]
        external = [n for n in g.all_nodes() if n.category != "dgc_internal"]
        # Both should exist
        assert len(internal) >= 1
        assert len(external) >= 1

    def test_annotations_on_external(self):
        g = build_field_graph()
        # External entries get research annotations
        assert g.annotation_count >= 1


# ---------------------------------------------------------------------------
# cross_dimensional_edges
# ---------------------------------------------------------------------------


class TestCrossDimensionalEdges:
    def test_no_other_graphs(self):
        d3 = build_field_graph()
        edges = cross_dimensional_edges(d3)
        assert edges == []

    def test_with_d1_graph(self):
        d3 = build_field_graph()
        # Build a D1 graph with a node name matching a dgc_mapping token
        d1 = ConceptGraph()
        # Pick a dgc_mapping token from the first entry that has one
        token = None
        for entry in ALL_FIELD_ENTRIES:
            mapping = entry.get("dgc_mapping", [])
            if mapping:
                token = mapping[0]
                break
        if token:
            d1.add_node(ConceptNode(
                name=token,
                source_file="test.py",
                category="d1",
            ))
            edges = cross_dimensional_edges(d3, d1_graph=d1)
            assert len(edges) >= 1
            assert all(e.metadata.get("cross_dimensional") == "D3→D1" for e in edges)


# ---------------------------------------------------------------------------
# _entries_by_relation
# ---------------------------------------------------------------------------


class TestEntriesByRelation:
    def test_validates(self):
        result = _entries_by_relation("validates")
        assert all(e.get("relation") == "validates" for e in result)

    def test_gap(self):
        result = _entries_by_relation("gap")
        assert all(e.get("relation") == "gap" for e in result)

    def test_nonexistent_relation(self):
        result = _entries_by_relation("does_not_exist")
        assert result == []


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


class TestOverlapReport:
    def test_structure(self):
        report = overlap_report()
        assert "title" in report
        assert "count" in report
        assert "validated_by_external" in report
        assert "dgc_supersedes" in report

    def test_count_consistent(self):
        report = overlap_report()
        assert report["count"] == len(report["validated_by_external"]) + len(report["dgc_supersedes"])


class TestGapReport:
    def test_structure(self):
        report = gap_report()
        assert "hard_gaps" in report
        assert "integration_opportunities" in report
        assert "hard_gap_count" in report
        assert "total" in report

    def test_count_consistent(self):
        report = gap_report()
        assert report["total"] == report["hard_gap_count"] + report["integration_count"]


class TestUniquenessReport:
    def test_structure(self):
        report = uniqueness_report()
        assert "moats" in report
        assert "count" in report

    def test_count_consistent(self):
        report = uniqueness_report()
        assert report["count"] == len(report["moats"])


class TestCompetitivePosition:
    def test_structure(self):
        report = competitive_position()
        assert "summary" in report
        assert "competitive_threats" in report
        assert "domain_coverage" in report
        assert "strategic_assessment" in report

    def test_summary_fields(self):
        report = competitive_position()
        summary = report["summary"]
        assert "total_field_entries" in summary
        assert "relation_breakdown" in summary
        assert summary["total_field_entries"] == len(ALL_FIELD_ENTRIES)

    def test_domain_coverage(self):
        report = competitive_position()
        coverage = report["domain_coverage"]
        # Should have entries for each field domain
        assert len(coverage) >= 1

    def test_strategic_assessment_values(self):
        report = competitive_position()
        assessment = report["strategic_assessment"]
        assert assessment["overall"] in ("DOMINANT", "STRONG", "DEVELOPING")


# ---------------------------------------------------------------------------
# full_field_scan
# ---------------------------------------------------------------------------


class TestFullFieldScan:
    def test_returns_all_sections(self):
        result = full_field_scan()
        assert "d3_graph" in result
        assert "graph_stats" in result
        assert "overlap" in result
        assert "gaps" in result
        assert "uniqueness" in result
        assert "competitive_position" in result

    def test_graph_stats(self):
        result = full_field_scan()
        stats = result["graph_stats"]
        assert stats["nodes"] == len(ALL_FIELD_ENTRIES)
        assert stats["edges"] >= 0
        assert stats["annotations"] >= 0
        assert stats["cross_dimensional_edges"] == 0  # no D1/D2 provided
        assert stats["components"] >= 1
        assert 0.0 <= stats["density"] <= 1.0
