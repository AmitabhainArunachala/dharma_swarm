"""Tests for Phase 7b: GraphNexus → MemoryPalace bridge integration."""

from __future__ import annotations

import pytest
import pytest_asyncio

from dharma_swarm.graph_store import SQLiteGraphStore
from dharma_swarm.memory_palace import MemoryPalace, PalaceQuery, PalaceResult


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def graph_store(tmp_path):
    """Fresh SQLiteGraphStore with seeded semantic data."""
    db = tmp_path / "test_graphs.db"
    store = SQLiteGraphStore(db)

    # Seed concepts with varying edge/bridge counts
    store.upsert_node("semantic", {
        "id": "c-autopoiesis",
        "kind": "concept",
        "name": "autopoiesis",
        "data": {
            "definition": "Self-producing system that maintains its own organization",
            "domain": "biology",
        },
    })
    store.upsert_node("semantic", {
        "id": "c-vsm",
        "kind": "concept",
        "name": "viable system model",
        "data": {
            "definition": "Stafford Beer's model for viable organizational structure",
            "domain": "cybernetics",
        },
    })
    store.upsert_node("semantic", {
        "id": "c-stigmergy",
        "kind": "concept",
        "name": "stigmergy",
        "data": {
            "definition": "Indirect coordination through environmental modifications",
            "domain": "swarm",
        },
    })

    # Edges: autopoiesis has 2 edges, vsm has 1
    store.upsert_edge("semantic", {
        "source_id": "c-autopoiesis",
        "target_id": "c-vsm",
        "kind": "related_to",
    })
    store.upsert_edge("semantic", {
        "source_id": "c-autopoiesis",
        "target_id": "c-stigmergy",
        "kind": "related_to",
    })

    # Bridge: code file → autopoiesis
    store.upsert_node("code", {
        "id": "file::dharma_swarm/organism.py",
        "kind": "file",
        "name": "dharma_swarm/organism.py",
    })
    store.upsert_bridge({
        "id": "bridge-organism-autopoiesis",
        "source_graph": "code",
        "source_id": "file::dharma_swarm/organism.py",
        "target_graph": "semantic",
        "target_id": "c-autopoiesis",
        "kind": "references_concept",
        "confidence": 0.9,
    })

    yield store
    store.close()


# ── _search_graph tests ──────────────────────────────────────────────────


class TestSearchGraph:
    def test_search_returns_palace_results(self, graph_store):
        """_search_graph should return PalaceResult objects."""
        palace = MemoryPalace(graph_store=graph_store)
        results = palace._search_graph("autopoiesis")
        assert len(results) >= 1
        assert isinstance(results[0], PalaceResult)

    def test_search_content_includes_concept_name(self, graph_store):
        """Result content should contain the concept name and definition."""
        palace = MemoryPalace(graph_store=graph_store)
        results = palace._search_graph("autopoiesis")
        assert len(results) >= 1
        assert "autopoiesis" in results[0].content
        assert "Self-producing" in results[0].content

    def test_search_score_reflects_centrality(self, graph_store):
        """Higher edge/bridge counts should produce higher scores."""
        palace = MemoryPalace(graph_store=graph_store)
        results = palace._search_graph("autopoiesis")
        assert len(results) >= 1
        # autopoiesis has 2 edges + 1 bridge, so score > base 0.5
        assert results[0].score > 0.5

    def test_search_metadata_has_graph_origin(self, graph_store):
        """Result metadata should include origin='graph_nexus'."""
        palace = MemoryPalace(graph_store=graph_store)
        results = palace._search_graph("autopoiesis")
        assert len(results) >= 1
        assert results[0].metadata.get("origin") == "graph_nexus"

    def test_search_returns_empty_without_graph(self):
        """_search_graph with no graph_store returns empty."""
        palace = MemoryPalace(graph_store=None)
        results = palace._search_graph("anything")
        assert results == []

    def test_search_no_match_returns_empty(self, graph_store):
        """Search for non-existent term returns empty list."""
        palace = MemoryPalace(graph_store=graph_store)
        results = palace._search_graph("xyznonexistent99")
        assert results == []


# ── recall() integration tests ───────────────────────────────────────────


class TestRecallWithGraphBridge:
    @pytest.mark.asyncio
    async def test_recall_includes_graph_results(self, graph_store):
        """recall() should include graph-sourced results in the response."""
        palace = MemoryPalace(graph_store=graph_store)
        query = PalaceQuery(text="autopoiesis", max_results=10)
        response = await palace.recall(query)
        # Should have at least 1 result from the graph
        assert len(response.results) >= 1
        # At least one should be from graph source
        graph_results = [r for r in response.results if "graph:" in r.source]
        assert len(graph_results) >= 1

    @pytest.mark.asyncio
    async def test_recall_without_graph_still_works(self):
        """recall() without graph_store should not fail."""
        palace = MemoryPalace(graph_store=None)
        query = PalaceQuery(text="anything", max_results=10)
        response = await palace.recall(query)
        # Should return empty results, not crash
        assert isinstance(response.results, list)

    @pytest.mark.asyncio
    async def test_recall_deduplicates_graph_and_other_results(self, graph_store):
        """Graph results should not duplicate content from other sources."""
        palace = MemoryPalace(graph_store=graph_store)
        query = PalaceQuery(text="autopoiesis", max_results=10)
        response = await palace.recall(query)
        contents = [r.content[:200] for r in response.results]
        # No exact duplicates in first 200 chars
        assert len(contents) == len(set(contents))


# ── Constructor tests ────────────────────────────────────────────────────


class TestMemoryPalaceConstructor:
    def test_graph_store_is_optional(self):
        """MemoryPalace should work without graph_store."""
        palace = MemoryPalace()
        assert palace._graph_store is None

    def test_graph_store_is_stored(self, graph_store):
        """graph_store should be stored on the instance."""
        palace = MemoryPalace(graph_store=graph_store)
        assert palace._graph_store is graph_store
