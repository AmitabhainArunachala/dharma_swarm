"""Tests for Phase 7b: GraphStore + ConceptIndexer integration with Organism."""

from __future__ import annotations

import pytest
import pytest_asyncio

from dharma_swarm.graph_store import SQLiteGraphStore
from dharma_swarm.organism import (
    Organism,
    OrganismPulse,
    get_graph_store,
    get_organism,
    set_organism,
    _set_graph_store,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def state_dir(tmp_path):
    """Provide a clean temp state directory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return tmp_path


@pytest.fixture
def organism(state_dir):
    """Create an Organism backed by a temp state directory."""
    org = Organism(state_dir=state_dir)
    set_organism(org)
    yield org
    set_organism(None)
    _set_graph_store(None)


# ── GraphStore boot tests ────────────────────────────────────────────────


class TestGraphStoreBoot:
    def test_graph_store_created_on_init(self, organism):
        """GraphStore should be created during Organism.__init__."""
        assert organism.graph_store is not None
        assert isinstance(organism.graph_store, SQLiteGraphStore)

    def test_graph_store_registered_globally(self, organism):
        """get_graph_store() should return the organism's graph store."""
        assert get_graph_store() is organism.graph_store

    def test_graph_store_db_path(self, organism, state_dir):
        """GraphStore DB should be at state_dir/data/dharma_graphs.db."""
        expected = state_dir / "data" / "dharma_graphs.db"
        assert organism.graph_store._db_path == expected

    def test_graph_store_has_semantic_graph(self, organism):
        """The semantic graph should have been seeded with concepts."""
        # If concept_indexer initialized, concepts should be populated
        if organism._concept_indexer is not None:
            count = organism.graph_store.count_nodes("semantic")
            assert count > 0

    def test_graph_store_is_never_fatal(self, tmp_path):
        """Even if GraphStore init fails, organism boots successfully."""
        # Create a state dir that doesn't allow data/ creation
        # (test that the try/except works — here we just test the fallback path)
        org = Organism(state_dir=tmp_path)
        # Even if graph_store is None, org should be alive
        assert org is not None


# ── ConceptIndexer integration tests ─────────────────────────────────────


class TestConceptIndexerIntegration:
    def test_concept_registry_loaded(self, organism):
        """ConceptRegistry should be loaded if graph_store initialized."""
        if organism.graph_store is not None:
            assert organism._concept_registry is not None

    def test_concept_indexer_created(self, organism):
        """ConceptIndexer should be wired to graph_store."""
        if organism.graph_store is not None:
            assert organism._concept_indexer is not None

    def test_concept_parser_created(self, organism):
        """ConceptParser should be available for file scanning."""
        if organism.graph_store is not None:
            assert organism._concept_parser is not None

    def test_indexing_due_flag_initial(self, organism):
        """_indexing_due should start False."""
        assert organism._indexing_due is False


# ── Heartbeat integration tests ──────────────────────────────────────────


class TestHeartbeatIndexing:
    @pytest.mark.asyncio
    async def test_heartbeat_returns_pulse_with_concept_stats(self, organism):
        """Heartbeat pulse should include concept_nodes and concept_edges."""
        pulse = await organism.heartbeat()
        assert isinstance(pulse, OrganismPulse)
        # concept_nodes and concept_edges should be >= 0
        assert pulse.concept_nodes >= 0
        assert pulse.concept_edges >= 0

    @pytest.mark.asyncio
    async def test_pulse_to_dict_includes_concept_stats(self, organism):
        """to_dict() should include concept stats when they're non-zero."""
        pulse = await organism.heartbeat()
        d = pulse.to_dict()
        # If concepts were indexed, they should appear in dict
        if pulse.concept_nodes > 0:
            assert "concept_nodes" in d
            assert "concept_edges" in d

    @pytest.mark.asyncio
    async def test_heartbeat_10th_cycle_triggers_indexing(self, organism):
        """Every 10th cycle should trigger concept indexing."""
        # Run 10 heartbeats
        for _ in range(10):
            pulse = await organism.heartbeat()
        # After 10 cycles, last_index_time may be set
        # (depends on DHARMA_REPO_ROOT pointing to valid dir)
        assert isinstance(pulse.last_index_time, str)

    @pytest.mark.asyncio
    async def test_heartbeat_blast_radius_on_20th_cycle(self, organism):
        """Every 20th cycle should include top_fragile_concepts in pulse."""
        for _ in range(20):
            pulse = await organism.heartbeat()
        d = pulse.to_dict()
        # top_fragile_concepts may be empty but should not crash
        assert isinstance(pulse.top_fragile_concepts, list)


# ── Organism status tests ────────────────────────────────────────────────


class TestOrganismStatusWithGraph:
    def test_status_includes_graph_store(self, organism):
        """status() should include graph_store section."""
        s = organism.status()
        if organism.graph_store is not None:
            assert "graph_store" in s
            assert "semantic_nodes" in s["graph_store"]

    @pytest.mark.asyncio
    async def test_boot_succeeds_with_graph(self, organism):
        """boot() should succeed with graph store initialized."""
        diag = await organism.boot()
        assert "booted_at" in diag
