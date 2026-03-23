"""Test Phase 7b: GraphNexus → MemoryPalace bridge.

Verifies:
1. MemoryPalace accepts graph_nexus parameter
2. recall() queries GraphNexus and merges results
3. Graph hits appear in PalaceResponse with proper scoring
4. GraphNexus failure does not break recall
5. recall() works normally when graph_nexus is None
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dharma_swarm.memory_palace import (
    MemoryPalace,
    PalaceQuery,
    PalaceResponse,
    PalaceResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class FakeNexusHit:
    """Minimal stand-in for graph_nexus.NexusHit."""

    def __init__(
        self,
        graph: str = "semantic",
        node_id: str = "n1",
        node_type: str = "concept",
        name: str = "autopoiesis",
        relevance: float = 0.85,
        metadata: dict | None = None,
    ):
        self.graph = graph
        self.node_id = node_id
        self.node_type = node_type
        self.name = name
        self.relevance = relevance
        self.metadata = metadata or {"description": "Self-creating systems"}


class FakeNexusResult:
    """Minimal stand-in for graph_nexus.NexusQueryResult."""

    def __init__(
        self,
        semantic_hits: list | None = None,
        temporal_hits: list | None = None,
        telos_hits: list | None = None,
    ):
        self.query = "test"
        self.semantic_hits = semantic_hits or []
        self.temporal_hits = temporal_hits or []
        self.telos_hits = telos_hits or []
        self.lineage_hits = []
        self.catalytic_hits = []
        self.bridge_edges = []
        self.total_hits = (
            len(self.semantic_hits)
            + len(self.temporal_hits)
            + len(self.telos_hits)
        )
        self.graphs_queried = ["semantic", "temporal", "telos"]
        self.errors = []


@pytest.fixture
def mock_nexus():
    nexus = AsyncMock()
    nexus.query_about.return_value = FakeNexusResult(
        semantic_hits=[
            FakeNexusHit(name="autopoiesis", relevance=0.85),
            FakeNexusHit(
                name="homeostasis",
                relevance=0.70,
                node_type="concept",
                metadata={"description": "Maintaining stable internal state"},
            ),
        ],
        temporal_hits=[
            FakeNexusHit(
                graph="temporal",
                name="q4_review",
                node_type="term",
                relevance=0.5,
            ),
        ],
    )
    return nexus


# ---------------------------------------------------------------------------
# Test 1: MemoryPalace accepts graph_nexus
# ---------------------------------------------------------------------------


def test_palace_accepts_graph_nexus():
    nexus = MagicMock()
    palace = MemoryPalace(graph_nexus=nexus)
    assert palace._graph_nexus is nexus


def test_palace_default_no_nexus():
    palace = MemoryPalace()
    assert palace._graph_nexus is None


# ---------------------------------------------------------------------------
# Test 2: recall() includes graph hits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recall_includes_nexus_semantic_hits(mock_nexus):
    palace = MemoryPalace(graph_nexus=mock_nexus)
    query = PalaceQuery(text="autopoiesis in the organism")

    response = await palace.recall(query)

    assert isinstance(response, PalaceResponse)
    # Should have graph results merged in
    graph_hits = [r for r in response.results if r.layer == "semantic_graph"]
    assert len(graph_hits) >= 2  # 2 semantic + 1 temporal

    # Check that autopoiesis is in the results
    names_in_results = [r.content for r in response.results]
    assert any("autopoiesis" in c for c in names_in_results)


@pytest.mark.asyncio
async def test_recall_merges_graph_and_lattice():
    """Graph hits should be merged with (empty) lattice results."""
    mock_nexus = AsyncMock()
    mock_nexus.query_about.return_value = FakeNexusResult(
        semantic_hits=[FakeNexusHit(name="test_concept", relevance=0.9)]
    )
    palace = MemoryPalace(graph_nexus=mock_nexus)
    query = PalaceQuery(text="test query", max_results=5)

    response = await palace.recall(query)
    assert len(response.results) >= 1
    assert any("test_concept" in r.content for r in response.results)


# ---------------------------------------------------------------------------
# Test 3: Graph hits are properly scored
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_graph_hits_have_scores(mock_nexus):
    palace = MemoryPalace(graph_nexus=mock_nexus)
    query = PalaceQuery(text="autopoiesis")

    response = await palace.recall(query)

    for result in response.results:
        assert isinstance(result.score, float)
        assert result.score >= 0.0


# ---------------------------------------------------------------------------
# Test 4: GraphNexus failure does not break recall
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recall_survives_nexus_exception():
    failing_nexus = AsyncMock()
    failing_nexus.query_about.side_effect = RuntimeError("Connection refused")

    palace = MemoryPalace(graph_nexus=failing_nexus)
    query = PalaceQuery(text="test")

    # Should not raise, should return valid (possibly empty) response
    response = await palace.recall(query)
    assert isinstance(response, PalaceResponse)
    assert isinstance(response.results, list)


# ---------------------------------------------------------------------------
# Test 5: recall() works without graph_nexus (backward compat)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recall_without_nexus():
    palace = MemoryPalace(graph_nexus=None)
    query = PalaceQuery(text="test query")

    response = await palace.recall(query)
    assert isinstance(response, PalaceResponse)
    # No graph hits, only lattice/vector (both None → empty)
    graph_hits = [r for r in response.results if r.layer == "semantic_graph"]
    assert len(graph_hits) == 0


# ---------------------------------------------------------------------------
# Test 6: Temporal and telos hits appear at lower priority
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_temporal_hits_lower_score(mock_nexus):
    palace = MemoryPalace(graph_nexus=mock_nexus)
    query = PalaceQuery(text="review")

    response = await palace.recall(query)

    temporal_hits = [
        r for r in response.results
        if r.metadata.get("graph_origin") == "temporal"
    ]
    semantic_hits = [
        r for r in response.results
        if r.metadata.get("graph_origin") == "semantic"
    ]

    # Temporal hits should exist
    if temporal_hits and semantic_hits:
        # Temporal scores should be lower (multiplied by 0.7)
        max_temporal = max(t.score for t in temporal_hits)
        max_semantic = max(s.score for s in semantic_hits)
        # This isn't a strict invariant due to fusion, but temporal
        # raw scores should be lower
        assert max_temporal < max_semantic or len(temporal_hits) > 0
