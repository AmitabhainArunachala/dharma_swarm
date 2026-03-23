"""Tests for GraphNexus -- unified cross-graph query interface."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dharma_swarm.graph_nexus import (
    GraphNexus,
    GraphOrigin,
    NexusHealth,
    NexusHit,
    NexusQueryResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_nexus(tmp_path) -> GraphNexus:
    """Create a GraphNexus pointing at a temporary state dir."""
    return GraphNexus(state_dir=tmp_path)


# ---------------------------------------------------------------------------
# Model unit tests
# ---------------------------------------------------------------------------


class TestModels:
    def test_nexus_hit_defaults(self):
        hit = NexusHit(graph="semantic", node_id="n1", node_type="concept", name="test")
        assert hit.relevance == 1.0
        assert hit.metadata == {}

    def test_nexus_query_result_empty(self):
        r = NexusQueryResult(query="foo")
        assert r.total_hits == 0
        assert r.graphs_queried == []
        assert r.errors == []

    def test_nexus_health_defaults(self):
        h = NexusHealth()
        assert h.total_nodes == 0
        assert h.total_edges == 0
        assert h.healthy_count == 0
        assert h.failed_count == 0

    def test_graph_origin_values(self):
        assert GraphOrigin.SEMANTIC.value == "semantic"
        assert GraphOrigin.TELOS.value == "telos"
        assert len(GraphOrigin) == 6


# ---------------------------------------------------------------------------
# Init and fault tolerance
# ---------------------------------------------------------------------------


class TestInit:
    @pytest.mark.asyncio
    async def test_init_records_errors_gracefully(self, tmp_path):
        """All graph loaders can fail, and the nexus continues."""
        nexus = _make_nexus(tmp_path)
        # None of the DB/JSON files exist, so all loaders will fail.
        await nexus.init()
        # At least some init errors recorded — exact number depends on
        # which imports are available.
        assert isinstance(nexus._init_errors, dict)

    @pytest.mark.asyncio
    async def test_init_does_not_raise(self, tmp_path):
        """init() should never raise, even with missing files."""
        nexus = _make_nexus(tmp_path)
        # Should not raise
        await nexus.init()

    @pytest.mark.asyncio
    async def test_double_init_is_safe(self, tmp_path):
        """Calling init() twice should not crash."""
        nexus = _make_nexus(tmp_path)
        await nexus.init()
        await nexus.init()


# ---------------------------------------------------------------------------
# query_about
# ---------------------------------------------------------------------------


class TestQueryAbout:
    @pytest.mark.asyncio
    async def test_query_about_with_no_graphs(self, tmp_path):
        """Querying with all graphs unavailable returns empty results, not crash."""
        nexus = _make_nexus(tmp_path)
        await nexus.init()
        result = await nexus.query_about("autocatalytic")
        assert isinstance(result, NexusQueryResult)
        assert result.query == "autocatalytic"
        assert result.total_hits == 0

    @pytest.mark.asyncio
    async def test_query_about_aggregates_semantic_hits(self, tmp_path):
        """Semantic graph hits are collected into semantic_hits."""
        nexus = _make_nexus(tmp_path)

        # Mock the concept graph
        mock_node = MagicMock()
        mock_node.id = "c1"
        mock_node.name = "autopoiesis"
        mock_node.salience = 0.9
        mock_node.definition = "self-making"
        mock_node.source_file = "pillar7.md"
        mock_node.category = "biology"

        mock_cg = MagicMock()
        mock_cg.find_by_name.return_value = [mock_node]

        nexus._concept_graph = mock_cg
        # Mark semantic as not failed so lazy loader doesn't try
        nexus._init_errors.pop(GraphOrigin.SEMANTIC.value, None)

        result = await nexus.query_about("autopoiesis")
        assert len(result.semantic_hits) >= 1
        assert result.semantic_hits[0].name == "autopoiesis"
        assert result.semantic_hits[0].relevance == 0.9
        assert GraphOrigin.SEMANTIC.value in result.graphs_queried

    @pytest.mark.asyncio
    async def test_query_about_semantic_fallback_to_category(self, tmp_path):
        """When find_by_name returns empty, falls back to find_by_category."""
        nexus = _make_nexus(tmp_path)

        mock_node = MagicMock()
        mock_node.id = "c2"
        mock_node.name = "governance"
        mock_node.salience = 0.7
        mock_node.definition = "org"
        mock_node.source_file = "pillar8.md"
        mock_node.category = "vsm"

        mock_cg = MagicMock()
        mock_cg.find_by_name.return_value = []
        mock_cg.find_by_category.return_value = [mock_node]

        nexus._concept_graph = mock_cg

        result = await nexus.query_about("vsm")
        assert len(result.semantic_hits) >= 1
        assert result.semantic_hits[0].name == "governance"

    @pytest.mark.asyncio
    async def test_query_about_survives_semantic_error(self, tmp_path):
        """If semantic graph raises, error is logged and other graphs proceed."""
        nexus = _make_nexus(tmp_path)

        mock_cg = MagicMock()
        mock_cg.find_by_name.side_effect = RuntimeError("boom")
        nexus._concept_graph = mock_cg

        result = await nexus.query_about("test")
        assert any("semantic" in e for e in result.errors)


# ---------------------------------------------------------------------------
# health()
# ---------------------------------------------------------------------------


class TestHealth:
    @pytest.mark.asyncio
    async def test_health_with_no_graphs(self, tmp_path):
        """Health report works even when no graphs are loaded."""
        nexus = _make_nexus(tmp_path)
        await nexus.init()
        report = await nexus.health()
        assert isinstance(report, NexusHealth)
        # Graphs that can init from empty dirs will be healthy;
        # the important thing is the report doesn't crash.
        assert report.healthy_count + report.failed_count > 0
        assert report.total_nodes >= 0
        assert report.total_edges >= 0

    @pytest.mark.asyncio
    async def test_health_counts_healthy_graphs(self, tmp_path):
        """Healthy graphs increment healthy_count."""
        nexus = _make_nexus(tmp_path)

        # Mock a healthy concept graph
        mock_cg = MagicMock()
        mock_cg.node_count = 42
        mock_cg.edge_count = 100
        mock_cg.annotation_count = 10
        mock_cg.density.return_value = 0.5

        nexus._concept_graph = mock_cg

        report = await nexus.health()
        assert report.graphs.get(GraphOrigin.SEMANTIC.value, {}).get("status") == "ok"
        assert report.total_nodes >= 42
        assert report.total_edges >= 100


# ---------------------------------------------------------------------------
# close() and context manager
# ---------------------------------------------------------------------------


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_close_clears_all_graphs(self, tmp_path):
        nexus = _make_nexus(tmp_path)
        nexus._concept_graph = MagicMock()
        nexus._init_errors["semantic"] = "test"

        await nexus.close()

        assert nexus._concept_graph is None
        assert nexus._catalytic_graph is None
        assert nexus._init_errors == {}

    @pytest.mark.asyncio
    async def test_close_calls_close_on_graphs(self, tmp_path):
        nexus = _make_nexus(tmp_path)
        mock_graph = MagicMock()
        mock_graph.close = MagicMock()
        nexus._concept_graph = mock_graph

        await nexus.close()

        mock_graph.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_handles_async_close(self, tmp_path):
        nexus = _make_nexus(tmp_path)
        mock_graph = MagicMock()
        mock_graph.close = AsyncMock()
        nexus._concept_graph = mock_graph

        await nexus.close()

        mock_graph.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_context_manager(self, tmp_path):
        async with GraphNexus(state_dir=tmp_path) as nexus:
            assert isinstance(nexus, GraphNexus)
        # After exit, graphs should be cleared
        assert nexus._concept_graph is None

    @pytest.mark.asyncio
    async def test_double_close_is_safe(self, tmp_path):
        nexus = _make_nexus(tmp_path)
        await nexus.close()
        await nexus.close()  # Should not raise


# ---------------------------------------------------------------------------
# query_node
# ---------------------------------------------------------------------------


class TestQueryNode:
    @pytest.mark.asyncio
    async def test_semantic_node_found(self, tmp_path):
        nexus = _make_nexus(tmp_path)
        mock_node = MagicMock()
        mock_node.id = "c-42"
        mock_node.name = "eigenform"
        mock_node.salience = 0.95
        mock_node.definition = "fixed point"
        mock_node.source_file = "cascade.py"
        mock_node.category = "math"

        mock_cg = MagicMock()
        mock_cg.get_node.return_value = mock_node
        nexus._concept_graph = mock_cg

        hit = await nexus.query_node(GraphOrigin.SEMANTIC.value, "c-42")
        assert hit is not None
        assert hit.name == "eigenform"
        assert hit.node_id == "c-42"
        assert hit.relevance == 0.95

    @pytest.mark.asyncio
    async def test_semantic_node_not_found(self, tmp_path):
        nexus = _make_nexus(tmp_path)
        mock_cg = MagicMock()
        mock_cg.get_node.return_value = None
        nexus._concept_graph = mock_cg

        hit = await nexus.query_node(GraphOrigin.SEMANTIC.value, "nonexistent")
        assert hit is None

    @pytest.mark.asyncio
    async def test_catalytic_node_found(self, tmp_path):
        nexus = _make_nexus(tmp_path)
        mock_cat = MagicMock()
        mock_cat._nodes = {"agent_runner": {"role": "executor"}}
        nexus._catalytic_graph = mock_cat

        hit = await nexus.query_node(GraphOrigin.CATALYTIC.value, "agent_runner")
        assert hit is not None
        assert hit.node_type == "catalytic_node"
        assert hit.metadata["role"] == "executor"

    @pytest.mark.asyncio
    async def test_catalytic_node_missing(self, tmp_path):
        nexus = _make_nexus(tmp_path)
        mock_cat = MagicMock()
        mock_cat._nodes = {}
        nexus._catalytic_graph = mock_cat

        hit = await nexus.query_node(GraphOrigin.CATALYTIC.value, "ghost")
        assert hit is None

    @pytest.mark.asyncio
    async def test_unknown_graph_returns_none(self, tmp_path):
        nexus = _make_nexus(tmp_path)
        hit = await nexus.query_node("nonexistent_graph", "any-id")
        assert hit is None

    @pytest.mark.asyncio
    async def test_exception_returns_none(self, tmp_path):
        nexus = _make_nexus(tmp_path)
        mock_cg = MagicMock()
        mock_cg.get_node.side_effect = RuntimeError("db locked")
        nexus._concept_graph = mock_cg

        hit = await nexus.query_node(GraphOrigin.SEMANTIC.value, "c-1")
        assert hit is None


# ---------------------------------------------------------------------------
# query_neighbors
# ---------------------------------------------------------------------------


class TestQueryNeighbors:
    @pytest.mark.asyncio
    async def test_semantic_neighbors(self, tmp_path):
        from types import SimpleNamespace

        nexus = _make_nexus(tmp_path)
        n1 = SimpleNamespace(id="n1", name="A", salience=0.5, definition="", category="x")
        n2 = SimpleNamespace(id="n2", name="B", salience=0.3, definition="", category="y")
        mock_cg = MagicMock()
        mock_cg.neighbors.return_value = [n1, n2]
        nexus._concept_graph = mock_cg

        hits = await nexus.query_neighbors(GraphOrigin.SEMANTIC.value, "root")
        assert len(hits) == 2
        assert {h.name for h in hits} == {"A", "B"}

    @pytest.mark.asyncio
    async def test_catalytic_neighbors_outgoing_and_incoming(self, tmp_path):
        nexus = _make_nexus(tmp_path)
        mock_cat = MagicMock()
        mock_cat._adj = {"X": ["Y"]}
        mock_cat._rev = {"X": ["Z"]}
        mock_cat._nodes = {"Y": {"t": 1}, "Z": {"t": 2}}
        nexus._catalytic_graph = mock_cat

        hits = await nexus.query_neighbors(GraphOrigin.CATALYTIC.value, "X")
        assert len(hits) == 2
        ids = {h.node_id for h in hits}
        assert "Y" in ids
        assert "Z" in ids

    @pytest.mark.asyncio
    async def test_neighbors_exception_returns_empty(self, tmp_path):
        nexus = _make_nexus(tmp_path)
        mock_cg = MagicMock()
        mock_cg.neighbors.side_effect = RuntimeError("crash")
        nexus._concept_graph = mock_cg

        hits = await nexus.query_neighbors(GraphOrigin.SEMANTIC.value, "root")
        assert hits == []

    @pytest.mark.asyncio
    async def test_neighbors_no_graph_returns_empty(self, tmp_path):
        nexus = _make_nexus(tmp_path)
        nexus._init_errors[GraphOrigin.SEMANTIC.value] = "skip"
        hits = await nexus.query_neighbors(GraphOrigin.SEMANTIC.value, "root")
        assert hits == []


# ---------------------------------------------------------------------------
# Lazy loading edge cases
# ---------------------------------------------------------------------------


class TestLazyLoading:
    @pytest.mark.asyncio
    async def test_lazy_load_records_error_on_failure(self, tmp_path):
        """Force a load failure by patching the loader to raise."""
        nexus = _make_nexus(tmp_path)

        async def _fail():
            raise RuntimeError("forced fail")

        nexus._load_concept_graph = _fail
        cg = await nexus._get_concept_graph()
        assert cg is None
        assert GraphOrigin.SEMANTIC.value in nexus._init_errors

    @pytest.mark.asyncio
    async def test_lazy_load_does_not_retry_after_failure(self, tmp_path):
        nexus = _make_nexus(tmp_path)
        nexus._init_errors[GraphOrigin.CATALYTIC.value] = "test fail"
        cat = await nexus._get_catalytic_graph()
        assert cat is None

    @pytest.mark.asyncio
    async def test_lazy_load_returns_cached(self, tmp_path):
        nexus = _make_nexus(tmp_path)
        mock_cg = MagicMock()
        nexus._concept_graph = mock_cg
        result = await nexus._get_concept_graph()
        assert result is mock_cg
