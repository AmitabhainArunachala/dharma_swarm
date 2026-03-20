"""Tests for the Organism integration layer."""

import asyncio
import pytest
from pathlib import Path
from dharma_swarm.organism import Organism, OrganismPulse
from dharma_swarm.models import GateResult


class TestOrganismBoot:

    def test_boot_returns_diagnostics(self, tmp_path):
        organism = Organism(state_dir=tmp_path)
        diagnostics = asyncio.run(organism.boot())
        assert "booted_at" in diagnostics
        assert "traces" in diagnostics

    def test_status_after_boot(self, tmp_path):
        organism = Organism(state_dir=tmp_path)
        asyncio.run(organism.boot())
        status = organism.status()
        assert "vsm" in status
        assert "amiros" in status
        assert status["cycle"] == 0


class TestOrganismHeartbeat:

    def test_heartbeat_produces_pulse(self, tmp_path):
        organism = Organism(state_dir=tmp_path)
        asyncio.run(organism.boot())
        pulse = asyncio.run(organism.heartbeat())
        assert isinstance(pulse, OrganismPulse)
        assert pulse.cycle_number == 1
        assert pulse.duration_ms > 0

    def test_multiple_heartbeats_increment_cycle(self, tmp_path):
        organism = Organism(state_dir=tmp_path)
        asyncio.run(organism.boot())

        for i in range(3):
            pulse = asyncio.run(organism.heartbeat())
        assert pulse.cycle_number == 3

    def test_healthy_pulse(self, tmp_path):
        organism = Organism(state_dir=tmp_path)
        asyncio.run(organism.boot())
        pulse = asyncio.run(organism.heartbeat())
        # Fresh organism should be healthy
        assert pulse.fleet_health >= 0.4
        assert pulse.algedonic_active == 0


class TestOrganismIntegrationHooks:

    def test_on_gate_check(self, tmp_path):
        organism = Organism(state_dir=tmp_path)
        # Should not crash with string result
        organism.on_gate_check("AHIMSA", "PASS", "safe action", "agent_01")
        organism.on_gate_check("AHIMSA", "FAIL", "bad action", "agent_01")
        # Check the streak was tracked
        assert organism.vsm._agent_failure_streaks["agent_01"] == 1

    def test_on_agent_output_harvests_to_amiros(self, tmp_path):
        organism = Organism(state_dir=tmp_path)
        asyncio.run(
            organism.on_agent_output(
                agent_id="researcher_01",
                task_description="analyze R_V data",
                output="Found V > O > K > Q hierarchy across all models.",
            )
        )
        # Should have been harvested
        assert len(organism.amiros._harvests) == 1
        assert organism.amiros._harvests[0].agent_id == "researcher_01"

    def test_on_agent_viability(self, tmp_path):
        organism = Organism(state_dir=tmp_path)
        organism.on_agent_viability(
            agent_id="agent_01",
            s1=0.9, s2=0.8, s3=0.7, s4=0.6, s5=1.0,
        )
        v = organism.vsm.viability.get("agent_01")
        assert v is not None
        assert v.overall > 0

    def test_gate_failure_streak_triggers_algedonic(self, tmp_path):
        organism = Organism(state_dir=tmp_path)
        # Build up a failure streak
        for _ in range(5):
            organism.on_gate_check("AHIMSA", "FAIL", "bad", "agent_01")

        # on_agent_output should check and fire algedonic
        asyncio.run(
            organism.on_agent_output("agent_01", "task", "output")
        )
        assert len(organism.vsm.algedonic.active_signals) >= 1

    def test_evolution_stagnation_triggers_algedonic(self, tmp_path):
        organism = Organism(state_dir=tmp_path)
        asyncio.run(
            organism.on_evolution_cycle(
                cycle_number=100,
                best_fitness=0.45,
                cycles_without_improvement=60,
            )
        )
        assert len(organism.vsm.algedonic.active_signals) >= 1


class TestOrganismPulse:

    def test_pulse_to_dict(self):
        pulse = OrganismPulse()
        pulse.cycle_number = 42
        pulse.fleet_health = 0.95
        d = pulse.to_dict()
        assert d["cycle"] == 42
        assert d["fleet_health"] == 0.95

    def test_pulse_health_check(self):
        pulse = OrganismPulse()
        pulse.fleet_health = 0.8
        pulse.algedonic_active = 0
        pulse.identity_coherence = 0.6
        assert pulse.is_healthy

        pulse.algedonic_active = 1
        assert not pulse.is_healthy
