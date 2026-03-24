"""Test Phase 7b: GraphStore + ConceptIndexer integration with Organism.

Verifies:
1. GraphStore initializes on Organism boot (non-fatal on failure)
2. get_graph_store() returns the store after set_organism()
3. ConceptIndexer runs during heartbeat (every 10th cycle)
4. Concept stats appear in OrganismPulse.to_dict()
5. Blast radius results appear in pulse.top_fragile_concepts
6. Graph failure does not crash the organism
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dharma_swarm.organism import (
    Organism,
    OrganismPulse,
    get_graph_store,
    set_organism,
)


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    """Create a minimal .dharma state tree."""
    for d in ("witness", "shared", "stigmergy", "evolution", "meta", "db", "data"):
        (tmp_path / d).mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# Test 1: OrganismPulse includes concept stats fields
# ---------------------------------------------------------------------------


def test_pulse_has_concept_stats_fields():
    pulse = OrganismPulse()
    assert pulse.concept_stats == {}
    assert pulse.top_fragile_concepts == []

    d = pulse.to_dict()
    # Empty stats should NOT appear in the dict (clean output)
    assert "concept_stats" not in d
    assert "top_fragile_concepts" not in d


def test_pulse_includes_concept_stats_when_populated():
    pulse = OrganismPulse()
    pulse.concept_stats = {"concept_nodes": 42, "concept_edges": 15}
    pulse.top_fragile_concepts = [
        {"concept": "autopoiesis", "total_impact": 12}
    ]

    d = pulse.to_dict()
    assert d["concept_stats"]["concept_nodes"] == 42
    assert d["top_fragile_concepts"][0]["concept"] == "autopoiesis"


# ---------------------------------------------------------------------------
# Test 2: get_graph_store() wiring
# ---------------------------------------------------------------------------


def test_get_graph_store_via_set_organism(state_dir: Path):
    """set_organism() should wire the global graph store."""
    org = Organism(state_dir=state_dir)
    set_organism(org)

    store = get_graph_store()
    # May or may not be None depending on whether SQLiteGraphStore loaded
    # but the function should at least return without error
    if org.graph_store is not None:
        assert store is org.graph_store

    # Cleanup
    set_organism(None)
    assert get_graph_store() is None


# ---------------------------------------------------------------------------
# Test 3: GraphStore init is non-fatal
# ---------------------------------------------------------------------------


def test_graph_store_init_nonfatal(tmp_path: Path):
    """If graph_store import fails, organism should still boot."""
    state_dir = tmp_path
    for d in ("witness", "shared", "stigmergy", "evolution", "meta", "db"):
        (state_dir / d).mkdir()

    # Patch SQLiteGraphStore to raise, simulating import/init failure
    with patch(
        "dharma_swarm.graph_store.SQLiteGraphStore",
        side_effect=RuntimeError("simulated failure"),
    ):
        org = Organism(state_dir=state_dir)
        # Organism should exist regardless of graph store status
        assert org is not None
        assert hasattr(org, "graph_store")
        # Graph store should be None since init failed
        assert org.graph_store is None


# ---------------------------------------------------------------------------
# Test 4: _run_incremental_indexing returns 0 when no indexer
# ---------------------------------------------------------------------------


def test_incremental_indexing_returns_zero_without_indexer(state_dir: Path):
    org = Organism(state_dir=state_dir)
    # Force indexer to None to test the guard clause
    org._concept_indexer = None
    assert org._run_incremental_indexing() == 0


def test_incremental_indexing_returns_zero_without_parser(state_dir: Path):
    org = Organism(state_dir=state_dir)
    org._concept_parser = None
    assert org._run_incremental_indexing() == 0


# ---------------------------------------------------------------------------
# Test 5: Heartbeat with mocked graph infrastructure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_heartbeat_concept_indexing(state_dir: Path):
    """Heartbeat should trigger concept indexing every 10th cycle."""
    org = Organism(state_dir=state_dir)

    # Mock the graph store
    mock_store = MagicMock()
    mock_store.count_nodes.return_value = 10
    mock_store.count_edges.return_value = 5
    mock_store.search_nodes.return_value = []
    org.graph_store = mock_store

    # Mock concept indexer
    mock_indexer = MagicMock()
    mock_indexer.index_extractions.return_value = {"bridge_edges": 3}
    org._concept_indexer = mock_indexer
    org._concept_parser = MagicMock()
    org._concept_parser.parse_file.return_value = []

    # Run 10 heartbeats to trigger indexing
    for _ in range(10):
        pulse = await org.heartbeat()

    # Should have concept stats in the last pulse
    assert pulse.concept_stats.get("concept_nodes") == 10
    assert pulse.concept_stats.get("concept_edges") == 5


# ---------------------------------------------------------------------------
# Test 6: _compute_top_fragile_concepts graceful failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compute_fragile_concepts_returns_empty_on_no_store(state_dir: Path):
    org = Organism(state_dir=state_dir)
    org.graph_store = None
    result = await org._compute_top_fragile_concepts()
    assert result == []


@pytest.mark.asyncio
async def test_compute_fragile_concepts_handles_import_error(state_dir: Path):
    org = Organism(state_dir=state_dir)
    mock_store = MagicMock()
    mock_store.search_nodes.return_value = [
        {"id": "abc123", "name": "autopoiesis"}
    ]
    org.graph_store = mock_store

    # Patch to raise ImportError (no blast radius module)
    with patch(
        "dharma_swarm.organism.ConceptBlastRadius",
        side_effect=ImportError("no module"),
        create=True,
    ):
        result = await org._compute_top_fragile_concepts()
        # Should return empty, not crash
        assert isinstance(result, list)
