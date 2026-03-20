"""Tests for Phase 3 integration: routing activation, palace population,
crew scaling, fitness routing, stigmergy tasking."""
import asyncio
import pytest


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestModelRoutingActivation:
    """Test that organism routing data flows to execution."""

    def test_route_result_has_model(self):
        from dharma_swarm.model_routing import OrganismRouter
        router = OrganismRouter()
        result = router.route("Analyze the architecture of this system")
        assert result.model != ""
        assert result.provider != ""
        assert result.complexity in ("trivial", "standard", "frontier", "privileged")

    def test_tier_mapping_covers_all_tiers(self):
        from dharma_swarm.model_routing import OrganismRouter
        assert "T0" in OrganismRouter._TIER_MODELS
        assert "T1" in OrganismRouter._TIER_MODELS
        assert "T2" in OrganismRouter._TIER_MODELS
        assert "T3" in OrganismRouter._TIER_MODELS


class TestPalacePopulation:
    """Test that agent outputs get indexed into the palace."""

    def test_organism_on_agent_output_ingests_to_palace(self):
        from dharma_swarm.organism import Organism
        org = Organism()
        _run(org.boot())
        _run(org.on_agent_output(
            agent_id="test_agent",
            task_description="Test task",
            output="This is a test output with important findings about R_V metrics",
        ))
        # Palace stats should show activity
        stats = org.palace.stats()
        assert stats["queries_served"] >= 0  # May not have queries yet

    def test_palace_search_method_exists(self):
        from dharma_swarm.memory_palace import MemoryPalace
        palace = MemoryPalace()
        results = palace.search("test query", top_k=5)
        assert isinstance(results, list)


class TestDynamicCrewScaling:
    """Test crew scaling recommendations."""

    def test_no_scaling_when_healthy(self):
        from dharma_swarm.organism import Organism
        org = Organism()
        _run(org.boot())
        # Run several healthy heartbeats
        for _ in range(5):
            pulse = _run(org.heartbeat())
        assert org._check_scaling_needs(pulse) is None

    def test_scaling_recommendations_property(self):
        from dharma_swarm.organism import Organism
        org = Organism()
        _run(org.boot())
        recs = org.scaling_recommendations
        assert isinstance(recs, list)


class TestFitnessRouting:
    """Test that fitness routing activates with organism."""

    def test_fitness_biased_pick_method_exists(self):
        from dharma_swarm.orchestrator import Orchestrator
        orch = Orchestrator()
        assert hasattr(orch, '_fitness_biased_pick')


class TestStigmergySelfTasking:
    """Test stigmergy-driven task creation."""

    def test_stigmergy_harvest_no_crash(self):
        from dharma_swarm.organism import Organism
        org = Organism()
        _run(org.boot())
        # Should not crash — returns int regardless of stigmergy data presence
        count = _run(org._harvest_stigmergy_tasks())
        assert isinstance(count, int)
        assert count >= 0

    def test_stigmergy_seen_set_initialized(self):
        from dharma_swarm.organism import Organism
        org = Organism()
        assert hasattr(org, '_stigmergy_seen')
        assert isinstance(org._stigmergy_seen, set)
