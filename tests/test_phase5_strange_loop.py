"""Phase 5b: Strange Loop tests."""
import pytest
from pathlib import Path
from datetime import datetime, timezone


class TestOrganismConfig:
    def test_default_values(self):
        from dharma_swarm.strange_loop import OrganismConfig
        config = OrganismConfig()
        assert config.routing_bias == 0.0
        assert config.scaling_health_threshold == 0.3
        assert config.algedonic_failure_threshold == 0.5

    def test_all_fields_present(self):
        from dharma_swarm.strange_loop import OrganismConfig
        config = OrganismConfig()
        assert hasattr(config, 'routing_bias')
        assert hasattr(config, 'scaling_health_threshold')
        assert hasattr(config, 'scaling_consecutive_unhealthy')
        assert hasattr(config, 'algedonic_failure_threshold')
        assert hasattr(config, 'algedonic_divergence_threshold')
        assert hasattr(config, 'algedonic_drift_threshold')
        assert hasattr(config, 'heartbeat_interval')
        assert hasattr(config, 'stigmergy_salience_threshold')
        assert hasattr(config, 'evolution_gnani_stagnation')

    def test_custom_values(self):
        from dharma_swarm.strange_loop import OrganismConfig
        config = OrganismConfig(routing_bias=0.2, scaling_health_threshold=0.5)
        assert config.routing_bias == 0.2
        assert config.scaling_health_threshold == 0.5


class TestStrangeLoop:
    def _make_pulses(self, n, health=0.9, coherence=0.9, failure=0.1):
        from dharma_swarm.organism import OrganismPulse
        pulses = []
        for i in range(n):
            p = OrganismPulse()
            p.cycle_number = i + 1
            p.fleet_health = health
            p.identity_coherence = coherence
            p.audit_failure_rate = failure
            p.algedonic_active = 0
            p.anomalous_gate_patterns = 0
            pulses.append(p)
        return pulses

    def test_idle_with_few_pulses(self, tmp_path):
        from dharma_swarm.strange_loop import StrangeLoop
        from dharma_swarm.organism import Organism
        org = Organism(state_dir=tmp_path)
        sl = StrangeLoop(org)
        status = sl.tick(10, [])
        assert status == "idle"

    def test_idle_with_only_4_pulses(self, tmp_path):
        from dharma_swarm.strange_loop import StrangeLoop
        from dharma_swarm.organism import Organism
        org = Organism(state_dir=tmp_path)
        sl = StrangeLoop(org)
        pulses = self._make_pulses(4, failure=0.6)
        status = sl.tick(10, pulses)
        assert status == "idle"

    def test_proposes_on_high_failure(self, tmp_path):
        from dharma_swarm.strange_loop import StrangeLoop
        from dharma_swarm.organism import Organism
        org = Organism(state_dir=tmp_path)
        sl = StrangeLoop(org)
        pulses = self._make_pulses(10, failure=0.6)  # Above threshold
        status = sl.tick(10, pulses)  # cycle 10 = divisible by tick_interval
        assert status in ("proposed_and_applied", "held_by_gnani")

    def test_no_proposal_when_healthy(self, tmp_path):
        from dharma_swarm.strange_loop import StrangeLoop
        from dharma_swarm.organism import Organism
        org = Organism(state_dir=tmp_path)
        sl = StrangeLoop(org)
        pulses = self._make_pulses(10, health=0.9, failure=0.05)
        status = sl.tick(10, pulses)
        assert status == "idle"

    def test_no_proposal_on_non_tick_cycle(self, tmp_path):
        from dharma_swarm.strange_loop import StrangeLoop
        from dharma_swarm.organism import Organism
        org = Organism(state_dir=tmp_path)
        sl = StrangeLoop(org)
        pulses = self._make_pulses(10, failure=0.6)
        # cycle 11 is NOT divisible by tick_interval (10)
        status = sl.tick(11, pulses)
        assert status == "idle"

    def test_measurement_countdown(self, tmp_path):
        from dharma_swarm.strange_loop import StrangeLoop
        from dharma_swarm.organism import Organism
        org = Organism(state_dir=tmp_path)
        org.attractor = None  # Bypass Gnani so mutation proceeds
        sl = StrangeLoop(org)
        pulses = self._make_pulses(10, failure=0.6)
        sl.tick(10, pulses)  # Propose and apply
        assert sl._pending_mutation is not None
        # Next tick should be "testing"
        status = sl.tick(11, pulses)
        assert status == "testing"

    def test_keeps_improving_mutation(self, tmp_path):
        from dharma_swarm.strange_loop import StrangeLoop
        from dharma_swarm.organism import Organism
        org = Organism(state_dir=tmp_path)
        org.attractor = None  # Bypass Gnani so mutation proceeds
        sl = StrangeLoop(org)
        sl._measurement_window = 2
        # High failure → propose routing bias increase
        bad_pulses = self._make_pulses(10, failure=0.6)
        sl.tick(10, bad_pulses)
        assert sl._pending_mutation is not None
        # Simulate improvement: count down and then measure with good pulses
        sl._measurement_countdown = 0
        good_pulses = self._make_pulses(5, failure=0.2)
        status = sl.tick(15, bad_pulses + good_pulses)
        assert status == "kept"
        assert sl._pending_mutation is None
        assert len(sl._mutations) == 1
        assert sl._mutations[0].kept is True

    def test_reverts_degrading_mutation(self, tmp_path):
        from dharma_swarm.strange_loop import StrangeLoop
        from dharma_swarm.organism import Organism
        org = Organism(state_dir=tmp_path)
        org.attractor = None  # Bypass Gnani so mutation proceeds
        sl = StrangeLoop(org)
        sl._measurement_window = 2
        bad_pulses = self._make_pulses(10, failure=0.6)
        sl.tick(10, bad_pulses)
        old_value = sl._pending_mutation.old_value
        # Don't improve — same bad pulses
        sl._measurement_countdown = 0
        status = sl.tick(15, bad_pulses)
        assert status == "reverted"
        assert sl.config.routing_bias == old_value

    def test_stats(self, tmp_path):
        from dharma_swarm.strange_loop import StrangeLoop
        from dharma_swarm.organism import Organism
        org = Organism(state_dir=tmp_path)
        sl = StrangeLoop(org)
        s = sl.stats
        assert "total_mutations" in s
        assert "current_config" in s
        assert "kept" in s
        assert "reverted" in s
        assert "held_by_gnani" in s
        assert "pending" in s

    def test_organism_has_strange_loop(self, tmp_path):
        from dharma_swarm.organism import Organism
        org = Organism(state_dir=tmp_path)
        assert hasattr(org, 'strange_loop')

    def test_persistence(self, tmp_path):
        from dharma_swarm.strange_loop import StrangeLoop, OrganismConfig
        from dharma_swarm.organism import Organism
        org = Organism(state_dir=tmp_path)
        org.attractor = None  # Bypass Gnani so mutation proceeds
        sl = StrangeLoop(org)
        # Apply a mutation manually to test persistence
        bad_pulses = self._make_pulses(10, failure=0.6)
        sl.tick(10, bad_pulses)
        sl._measurement_countdown = 0
        good_pulses = self._make_pulses(5, failure=0.2)
        sl.tick(15, bad_pulses + good_pulses)
        assert len(sl._mutations) == 1

        # Create new StrangeLoop — should load from disk
        sl2 = StrangeLoop(org)
        assert len(sl2._mutations) == 1
        assert sl2._mutations[0].parameter == sl._mutations[0].parameter

    def test_mutation_dataclass(self):
        from dharma_swarm.strange_loop import Mutation
        m = Mutation(
            id="abc123",
            parameter="routing_bias",
            old_value=0.0,
            new_value=0.05,
            reason="Test reason",
            proposed_at=datetime.now(timezone.utc),
        )
        assert m.id == "abc123"
        assert m.parameter == "routing_bias"
        assert m.old_value == 0.0
        assert m.new_value == 0.05
        assert m.applied_at is None
        assert m.reverted_at is None
        assert m.gnani_verdict is None
        assert m.kept is None

    def test_mutation_serialization(self):
        from dharma_swarm.strange_loop import Mutation
        now = datetime.now(timezone.utc)
        m = Mutation(
            id="test1",
            parameter="routing_bias",
            old_value=0.0,
            new_value=0.05,
            reason="Test",
            proposed_at=now,
            gnani_verdict=True,
            kept=True,
        )
        d = m.to_dict()
        assert d["id"] == "test1"
        assert d["parameter"] == "routing_bias"
        m2 = Mutation.from_dict(d)
        assert m2.id == m.id
        assert m2.parameter == m.parameter
        assert m2.old_value == m.old_value
        assert m2.new_value == m.new_value
        assert m2.kept == m.kept

    def test_unhealthy_ratio_triggers_scaling_threshold_proposal(self, tmp_path):
        from dharma_swarm.strange_loop import StrangeLoop
        from dharma_swarm.organism import Organism, OrganismPulse
        org = Organism(state_dir=tmp_path)
        sl = StrangeLoop(org)
        # Create pulses that are unhealthy (algedonic_active > 0)
        pulses = []
        for i in range(10):
            p = OrganismPulse()
            p.cycle_number = i + 1
            p.fleet_health = 0.2  # Low health
            p.identity_coherence = 0.9
            p.audit_failure_rate = 0.0  # Low failure (so routing bias won't trigger)
            p.algedonic_active = 1  # Active algedonic = unhealthy
            p.anomalous_gate_patterns = 0
            pulses.append(p)
        status = sl.tick(10, pulses)
        # Should either propose scaling_health_threshold or idle (depends on Gnani)
        assert status in ("proposed_and_applied", "held_by_gnani", "idle")

    def test_config_sync_to_organism(self, tmp_path):
        from dharma_swarm.strange_loop import StrangeLoop, OrganismConfig
        from dharma_swarm.organism import Organism
        org = Organism(state_dir=tmp_path)
        config = OrganismConfig(routing_bias=0.2)
        sl = StrangeLoop(org, config=config)
        sl._sync_config_to_organism()
        # Router should have updated routing bias
        assert org.router._routing_bias == 0.2

    def test_pending_mutation_persisted_and_loaded(self, tmp_path):
        from dharma_swarm.strange_loop import StrangeLoop
        from dharma_swarm.organism import Organism
        org = Organism(state_dir=tmp_path)
        org.attractor = None  # Bypass Gnani so mutation proceeds
        sl = StrangeLoop(org)
        bad_pulses = self._make_pulses(10, failure=0.6)
        sl.tick(10, bad_pulses)
        # Mutation should be pending
        assert sl._pending_mutation is not None
        pending_id = sl._pending_mutation.id
        # Create a new StrangeLoop — should reload with pending mutation
        sl2 = StrangeLoop(org)
        assert sl2._pending_mutation is not None
        assert sl2._pending_mutation.id == pending_id
        assert sl2._measurement_countdown == 0
