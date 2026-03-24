"""Integration test: Full organism lifecycle.

Tests the complete flow: task → gate → execute → evolve → witness.
This validates that all subsystems are wired and the organism
behaves as a coherent autopoietic system.

Ground: Varela (autopoiesis — cognition IS self-maintenance).
"""

import asyncio
import pytest
from pathlib import Path

from dharma_swarm.organism import Organism, OrganismPulse, set_organism, get_organism
from dharma_swarm.models import GateResult


class TestFullLifecycle:
    """Task → Gate → Execute → Evolve → Witness."""

    def test_boot_heartbeat_gate_output_evolve(self, tmp_path):
        """Full lifecycle in a single test: the organism breathes."""
        organism = Organism(state_dir=tmp_path)
        set_organism(organism)

        # Phase 1: BOOT — the organism wakes up
        diagnostics = asyncio.run(organism.boot())
        assert "booted_at" in diagnostics
        assert "traces" in diagnostics

        # Phase 2: HEARTBEAT — the organism checks itself
        pulse = asyncio.run(organism.heartbeat())
        assert isinstance(pulse, OrganismPulse)
        assert pulse.cycle_number == 1
        assert pulse.fleet_health >= 0.4

        # Phase 3: GATE — a task arrives and passes gates
        gate_pattern = organism.on_gate_check(
            gate_name="AHIMSA",
            result="PASS",
            action_description="analyze R_V data across 8 models",
            agent_id="researcher_01",
        )
        # First check should not be anomalous
        assert gate_pattern is None or not gate_pattern.is_anomalous

        # Phase 4: EXECUTE — agent produces output
        asyncio.run(organism.on_agent_output(
            agent_id="researcher_01",
            task_description="analyze R_V data",
            output="Found V > O > K > Q hierarchy across all 8 models. "
                   "R_V contraction correlates with task complexity (r=0.87).",
        ))

        # Verify AMIROS harvested the output
        assert len(organism.amiros._harvests) == 1
        harvest = organism.amiros._harvests[0]
        assert harvest.agent_id == "researcher_01"
        assert "R_V" in harvest.raw_text

        # Phase 5: VIABILITY — agent reports its health
        organism.on_agent_viability(
            agent_id="researcher_01",
            s1=0.95,  # operations fine
            s2=0.85,  # coordination good
            s3=0.90,  # control strong
            s4=0.80,  # intelligence adequate
            s5=1.00,  # identity coherent
        )
        v = organism.vsm.viability.get("researcher_01")
        assert v is not None
        assert v.overall > 0.7

        # Phase 6: EVOLVE — evolution cycle completes
        asyncio.run(organism.on_evolution_cycle(
            cycle_number=1,
            best_fitness=0.72,
            cycles_without_improvement=0,
        ))
        # No algedonic signals for a healthy evolution
        assert len(organism.vsm.algedonic.active_signals) == 0

        # Phase 7: WITNESS — second heartbeat captures everything
        pulse2 = asyncio.run(organism.heartbeat())
        assert pulse2.cycle_number == 2
        assert pulse2.fleet_health > 0

        # Phase 8: STATUS — full organism observability
        status = organism.status()
        assert "vsm" in status
        assert "amiros" in status
        assert "palace" in status
        assert "router" in status
        assert status["cycle"] == 2

        # Cleanup singleton
        set_organism(None)

    def test_algedonic_fires_on_gate_streak(self, tmp_path):
        """Gate failures trigger algedonic bypass to operator."""
        organism = Organism(state_dir=tmp_path)

        # 5 consecutive gate failures
        for _ in range(5):
            organism.on_gate_check("AHIMSA", "FAIL", "bad action", "rogue_agent")

        # Agent output triggers streak check → algedonic
        asyncio.run(organism.on_agent_output(
            "rogue_agent", "suspicious task", "suspicious output",
        ))

        assert len(organism.vsm.algedonic.active_signals) >= 1
        signal = organism.vsm.algedonic.active_signals[0]
        assert signal.severity in ("warning", "critical", "emergency")

    def test_evolution_stagnation_fires_algedonic(self, tmp_path):
        """Stagnant evolution triggers algedonic emergency."""
        organism = Organism(state_dir=tmp_path)

        asyncio.run(organism.on_evolution_cycle(
            cycle_number=100,
            best_fitness=0.30,
            cycles_without_improvement=60,
        ))

        assert len(organism.vsm.algedonic.active_signals) >= 1

    def test_model_routing_integration(self, tmp_path):
        """Organism router classifies and routes tasks."""
        organism = Organism(state_dir=tmp_path)

        # Trivial EN task
        d1 = organism.router.classify_and_route("translate this text")
        assert d1.recommended_tier in ("T0", "T1")

        # Frontier JP task
        d2 = organism.router.classify_and_route("このアーキテクチャを分析してください")
        assert "JP" in d2.reasoning

        # Router stats tracked
        s = organism.router.stats()
        assert s["total_decisions"] == 2

    def test_memory_palace_integration(self, tmp_path):
        """Memory Palace responds to queries (without full lattice)."""
        organism = Organism(state_dir=tmp_path)

        from dharma_swarm.memory_palace import PalaceQuery
        response = asyncio.run(organism.palace.recall(
            PalaceQuery(text="R_V metric results", agent_id="researcher_01")
        ))
        assert response.query_text == "R_V metric results"
        assert response.duration_ms > 0

        # Palace stats tracked
        s = organism.palace.stats()
        assert s["queries_served"] == 1


class TestSingletonOrganismWiring:
    """Test the global organism singleton for cross-module wiring."""

    def test_set_and_get(self, tmp_path):
        org = Organism(state_dir=tmp_path)
        set_organism(org)
        assert get_organism() is org
        set_organism(None)
        assert get_organism() is None

    def test_none_by_default(self):
        """Before any organism is booted, get_organism returns None."""
        # Save current state
        current = get_organism()
        set_organism(None)
        assert get_organism() is None
        # Restore
        if current is not None:
            set_organism(current)


class TestMultiAgentOrchestration:
    """Test organism handling multiple agents simultaneously."""

    def test_multiple_agents_tracked(self, tmp_path):
        organism = Organism(state_dir=tmp_path)

        # Three agents report viability
        for i, agent_id in enumerate(["alpha", "beta", "gamma"]):
            organism.on_agent_viability(
                agent_id=agent_id,
                s1=0.9 - i * 0.1,
                s2=0.8,
                s3=0.7 + i * 0.05,
            )

        assert organism.vsm.viability.get("alpha") is not None
        assert organism.vsm.viability.get("beta") is not None
        assert organism.vsm.viability.get("gamma") is not None

        # Fleet health should reflect all three
        health = organism.vsm.viability.fleet_health()
        assert 0.5 < health < 1.0

    def test_mixed_gate_results(self, tmp_path):
        organism = Organism(state_dir=tmp_path)

        # Agent alpha passes all gates
        for _ in range(3):
            organism.on_gate_check("AHIMSA", "PASS", "ok", "alpha")

        # Agent beta fails repeatedly
        for _ in range(5):
            organism.on_gate_check("SATYA", "FAIL", "bad", "beta")

        # Alpha's streak should be 0, beta's should be 5
        assert organism.vsm._agent_failure_streaks["alpha"] == 0
        assert organism.vsm._agent_failure_streaks["beta"] == 5
