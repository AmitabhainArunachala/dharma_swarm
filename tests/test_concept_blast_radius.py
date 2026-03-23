"""Tests for concept_blast_radius.py — cross-graph impact analysis."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dharma_swarm.concept_blast_radius import (
    BlastRadiusReport,
    ConceptBlastRadius,
)


# ---------------------------------------------------------------------------
# BlastRadiusReport model tests
# ---------------------------------------------------------------------------


class TestBlastRadiusReport:
    def test_defaults(self):
        r = BlastRadiusReport(concept_id="abc")
        assert r.concept_id == "abc"
        assert r.concept_name == ""
        assert r.affected_code_files == []
        assert r.affected_concepts == []
        assert r.affected_temporal_terms == []
        assert r.affected_objectives == []
        assert r.affected_catalytic_nodes == []
        assert r.bridge_details == []
        assert r.total_impact == 0

    def test_populated_report(self):
        r = BlastRadiusReport(
            concept_id="id-1",
            concept_name="autopoiesis",
            affected_code_files=["a.py", "b.py"],
            affected_concepts=["self-reference", "enaction"],
            affected_temporal_terms=["2026-Q1"],
            affected_objectives=["obj-1"],
            affected_catalytic_nodes=["cat-1", "cat-2"],
            total_impact=8,
        )
        assert r.total_impact == 8
        assert len(r.affected_code_files) == 2

    def test_report_serialization(self):
        r = BlastRadiusReport(concept_id="test", concept_name="dharma")
        d = r.model_dump()
        assert d["concept_id"] == "test"
        assert d["concept_name"] == "dharma"
        assert isinstance(d["affected_code_files"], list)


# ---------------------------------------------------------------------------
# ConceptBlastRadius tests (with mocked graphs)
# ---------------------------------------------------------------------------


def _mock_concept_node(node_id="c1", name="autopoiesis", source_file="varela.py"):
    return SimpleNamespace(id=node_id, name=name, source_file=source_file)


def _mock_concept_graph(nodes=None, neighbors=None, find_by_name_result=None):
    """Create a mock ConceptGraph."""
    cg = MagicMock()
    nodes = nodes or []
    node_map = {n.id: n for n in nodes}
    cg.get_node = MagicMock(side_effect=lambda nid: node_map.get(nid))
    cg.neighbors = MagicMock(return_value=neighbors or [])
    cg.find_by_name = MagicMock(return_value=find_by_name_result or [])
    cg.all_nodes = MagicMock(return_value=nodes)
    return cg


class TestConceptBlastRadiusCompute:
    @pytest.mark.asyncio
    async def test_compute_no_graph(self, tmp_path):
        """When ConceptGraph fails to load, returns empty report."""
        br = ConceptBlastRadius(state_dir=tmp_path)
        report = await br.compute("nonexistent")
        assert report.concept_id == "nonexistent"
        assert report.total_impact == 0

    @pytest.mark.asyncio
    async def test_compute_with_concept(self, tmp_path):
        """With a concept node, gets name and source file."""
        node = _mock_concept_node()
        cg = _mock_concept_graph(nodes=[node])

        br = ConceptBlastRadius(state_dir=tmp_path)
        with patch.object(br, "_load_concept_graph", new_callable=AsyncMock, return_value=cg):
            with patch.object(br, "_collect_bridge_impacts", new_callable=AsyncMock):
                with patch.object(br, "_collect_temporal_cooccurrences", new_callable=AsyncMock):
                    report = await br.compute("c1")

        assert report.concept_name == "autopoiesis"
        assert "varela.py" in report.affected_code_files

    @pytest.mark.asyncio
    async def test_compute_with_neighbors(self, tmp_path):
        """Neighbors are included in affected_concepts."""
        node = _mock_concept_node()
        n1 = _mock_concept_node("n1", "enaction")
        n2 = _mock_concept_node("n2", "self-reference")
        cg = _mock_concept_graph(nodes=[node], neighbors=[n1, n2])

        br = ConceptBlastRadius(state_dir=tmp_path)
        with patch.object(br, "_load_concept_graph", new_callable=AsyncMock, return_value=cg):
            with patch.object(br, "_collect_bridge_impacts", new_callable=AsyncMock):
                with patch.object(br, "_collect_temporal_cooccurrences", new_callable=AsyncMock):
                    report = await br.compute("c1")

        assert "enaction" in report.affected_concepts
        assert "self-reference" in report.affected_concepts

    @pytest.mark.asyncio
    async def test_compute_total_impact_calculation(self, tmp_path):
        """total_impact = sum of all affected lists."""
        node = _mock_concept_node(source_file="")  # no source file
        n1 = _mock_concept_node("n1", "a")
        n2 = _mock_concept_node("n2", "b")
        cg = _mock_concept_graph(nodes=[node], neighbors=[n1, n2])

        br = ConceptBlastRadius(state_dir=tmp_path)
        with patch.object(br, "_load_concept_graph", new_callable=AsyncMock, return_value=cg):
            with patch.object(br, "_collect_bridge_impacts", new_callable=AsyncMock):
                with patch.object(br, "_collect_temporal_cooccurrences", new_callable=AsyncMock):
                    report = await br.compute("c1")

        assert report.total_impact == 2  # 2 neighbors, no files

    @pytest.mark.asyncio
    async def test_compute_source_file_dedup(self, tmp_path):
        """Source file not duplicated if already in affected_code_files."""
        node = _mock_concept_node(source_file="shared.py")
        cg = _mock_concept_graph(nodes=[node])

        async def _add_file(concept_id, report):
            report.affected_code_files.append("shared.py")

        br = ConceptBlastRadius(state_dir=tmp_path)
        with patch.object(br, "_load_concept_graph", new_callable=AsyncMock, return_value=cg):
            with patch.object(br, "_collect_bridge_impacts", side_effect=_add_file):
                with patch.object(br, "_collect_temporal_cooccurrences", new_callable=AsyncMock):
                    report = await br.compute("c1")

        # Should appear only once despite being from both node.source_file and bridge
        assert report.affected_code_files.count("shared.py") == 1


class TestConceptBlastRadiusComputeByName:
    @pytest.mark.asyncio
    async def test_compute_by_name_found(self, tmp_path):
        """When name matches a concept, delegates to compute()."""
        node = _mock_concept_node("c1", "autopoiesis", "varela.py")
        cg = _mock_concept_graph(nodes=[node], find_by_name_result=[node])

        br = ConceptBlastRadius(state_dir=tmp_path)
        with patch.object(br, "_load_concept_graph", new_callable=AsyncMock, return_value=cg):
            with patch.object(br, "_collect_bridge_impacts", new_callable=AsyncMock):
                with patch.object(br, "_collect_temporal_cooccurrences", new_callable=AsyncMock):
                    report = await br.compute_by_name("autopoiesis")

        assert report.concept_name == "autopoiesis"

    @pytest.mark.asyncio
    async def test_compute_by_name_not_found(self, tmp_path):
        """When no match, returns partial report with name: prefix."""
        cg = _mock_concept_graph(find_by_name_result=[])

        br = ConceptBlastRadius(state_dir=tmp_path)
        with patch.object(br, "_load_concept_graph", new_callable=AsyncMock, return_value=cg):
            with patch.object(br, "_collect_temporal_cooccurrences", new_callable=AsyncMock):
                report = await br.compute_by_name("nonexistent")

        assert report.concept_id == "name:nonexistent"
        assert report.concept_name == "nonexistent"

    @pytest.mark.asyncio
    async def test_compute_by_name_no_graph(self, tmp_path):
        """When graph fails to load, still returns partial report."""
        br = ConceptBlastRadius(state_dir=tmp_path)
        report = await br.compute_by_name("dharma")
        assert report.concept_id == "name:dharma"
        assert report.concept_name == "dharma"


class TestMultiCompute:
    @pytest.mark.asyncio
    async def test_multi_compute_returns_all(self, tmp_path):
        br = ConceptBlastRadius(state_dir=tmp_path)
        results = await br.multi_compute(["a", "b", "c"])
        assert len(results) == 3
        assert all(isinstance(v, BlastRadiusReport) for v in results.values())

    @pytest.mark.asyncio
    async def test_multi_compute_empty(self, tmp_path):
        br = ConceptBlastRadius(state_dir=tmp_path)
        results = await br.multi_compute([])
        assert results == {}


class TestHighestImpact:
    @pytest.mark.asyncio
    async def test_highest_impact_no_graph(self, tmp_path):
        """When no graph, returns empty list."""
        br = ConceptBlastRadius(state_dir=tmp_path)
        results = await br.highest_impact(top_n=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_highest_impact_sorts_by_total(self, tmp_path):
        n1 = _mock_concept_node("c1", "a", "")
        n2 = _mock_concept_node("c2", "b", "")
        cg = _mock_concept_graph(nodes=[n1, n2])

        # Make c2 have higher impact than c1
        call_count = [0]

        async def _mock_compute(concept_id):
            call_count[0] += 1
            impact = 10 if concept_id == "c2" else 2
            return BlastRadiusReport(
                concept_id=concept_id,
                total_impact=impact,
            )

        br = ConceptBlastRadius(state_dir=tmp_path)
        with patch.object(br, "_load_concept_graph", new_callable=AsyncMock, return_value=cg):
            with patch.object(br, "compute", side_effect=_mock_compute):
                results = await br.highest_impact(top_n=1)

        assert len(results) == 1
        assert results[0].concept_id == "c2"
        assert results[0].total_impact == 10
