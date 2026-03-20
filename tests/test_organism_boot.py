"""Tests for organism boot integration."""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestOrganismBoot:
    """Test that organism boots correctly and integrates with swarm."""

    def test_organism_singleton(self):
        from dharma_swarm.organism import get_organism, set_organism, Organism
        # Initially None
        import dharma_swarm.organism as mod
        old = mod._global_organism
        try:
            mod._global_organism = None
            assert get_organism() is None
            org = Organism()
            set_organism(org)
            assert get_organism() is org
        finally:
            mod._global_organism = old

    def test_organism_boot_diagnostics(self):
        from dharma_swarm.organism import Organism
        org = Organism()
        diag = _run(org.boot())
        assert "booted_at" in diag
        assert "amiros" in diag

    def test_organism_heartbeat(self):
        from dharma_swarm.organism import Organism
        org = Organism()
        _run(org.boot())
        pulse = _run(org.heartbeat())
        assert pulse.cycle_number == 1
        assert pulse.is_healthy

    def test_organism_status(self):
        from dharma_swarm.organism import Organism
        org = Organism()
        _run(org.boot())
        status = org.status()
        assert "vsm" in status
        assert "amiros" in status
        assert "palace" in status
        assert "router" in status


class TestAMIROSPersistence:
    """Test AMIROS JSON persistence."""

    def test_amiros_save_load(self, tmp_path):
        from dharma_swarm.amiros import AMIROSRegistry
        reg = AMIROSRegistry(state_dir=tmp_path)
        reg.harvest(source="test", agent_id="a1", raw_text="hello world")

        # Check file was created
        persist_dir = tmp_path / "amiros"
        assert persist_dir.exists()

        # Create new registry from same path — should load persisted data
        reg2 = AMIROSRegistry(state_dir=tmp_path)
        stats = reg2.stats()
        assert stats.get("harvests", {}).get("total", 0) > 0


class TestContextCompilerPalace:
    """Test Memory Palace integration in context compiler."""

    def test_palace_section_weight_exists(self):
        from dharma_swarm.context_compiler import ContextCompiler
        assert "Memory Palace" in ContextCompiler._SECTION_WEIGHTS


class TestOrganismRouting:
    """Test model routing via organism."""

    def test_router_route_returns_result(self):
        from dharma_swarm.model_routing import OrganismRouter
        router = OrganismRouter()
        result = router.route("Write a Python unit test")
        assert result is not None
        assert hasattr(result, 'model')
