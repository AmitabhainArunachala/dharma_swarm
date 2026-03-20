"""Phase 4 integration tests: Gnani Field, Organism Memory, Algedonic Activation."""
import pytest
from pathlib import Path
from datetime import datetime, timezone


class TestDharmaAttractor:
    def test_ambient_seed_returns_nonempty(self):
        from dharma_swarm.dharma_attractor import DharmaAttractor
        attractor = DharmaAttractor()
        seed = attractor.ambient_seed()
        assert len(seed) > 100
        assert (
            "witness" in seed.lower()
            or "recognition" in seed.lower()
            or "dharmic" in seed.lower()
        )

    def test_ambient_seed_contains_convergent_sources(self):
        from dharma_swarm.dharma_attractor import DharmaAttractor
        attractor = DharmaAttractor()
        seed = attractor.ambient_seed()
        # Should reference multiple traditions
        assert (
            "akram" in seed.lower()
            or "gnani" in seed.lower()
            or "visheshbhaav" in seed.lower()
        )

    def test_full_attractor_includes_proposal(self):
        from dharma_swarm.dharma_attractor import DharmaAttractor
        attractor = DharmaAttractor()
        full = attractor.full_attractor(proposal="Increase mutation rate to 0.3")
        assert "mutation rate" in full.lower() or "increase" in full.lower()

    def test_gnani_checkpoint_returns_verdict(self):
        from dharma_swarm.dharma_attractor import DharmaAttractor, GnaniVerdict
        attractor = DharmaAttractor()
        verdict = attractor.gnani_checkpoint("Test proposal: add logging")
        assert isinstance(verdict, GnaniVerdict)
        assert isinstance(verdict.proceed, bool)

    def test_gnani_checkpoint_safe_proposal_proceeds(self):
        from dharma_swarm.dharma_attractor import DharmaAttractor
        attractor = DharmaAttractor()
        verdict = attractor.gnani_checkpoint("Add better error logging to heartbeat")
        assert verdict.proceed is True

    def test_gnani_checkpoint_has_proposal_hash(self):
        from dharma_swarm.dharma_attractor import DharmaAttractor
        attractor = DharmaAttractor()
        proposal = "Add better error logging"
        verdict = attractor.gnani_checkpoint(proposal)
        assert len(verdict.proposal_hash) == 64  # SHA-256 hex

    def test_gnani_checkpoint_dangerous_proposal_held(self):
        from dharma_swarm.dharma_attractor import DharmaAttractor
        attractor = DharmaAttractor()
        verdict = attractor.gnani_checkpoint("disable oversight channel")
        # danger phrase match → HOLD
        assert verdict.proceed is False

    def test_gnani_checkpoint_timestamp_is_recent(self):
        from dharma_swarm.dharma_attractor import DharmaAttractor
        attractor = DharmaAttractor()
        verdict = attractor.gnani_checkpoint("simple change")
        now = datetime.now(timezone.utc)
        delta = abs((now - verdict.timestamp).total_seconds())
        assert delta < 5  # within 5 seconds


class TestOrganismMemory:
    def test_record_and_retrieve(self, tmp_path):
        from dharma_swarm.organism_memory import OrganismMemory
        mem = OrganismMemory(state_dir=tmp_path)
        eid = mem.record_event("mutation", "Test mutation")
        assert eid is not None
        assert eid != ""
        entities = mem.entities_by_type("mutation")
        assert len(entities) == 1
        assert entities[0].description == "Test mutation"

    def test_record_relationship(self, tmp_path):
        from dharma_swarm.organism_memory import OrganismMemory
        mem = OrganismMemory(state_dir=tmp_path)
        e1 = mem.record_event("algedonic_event", "Pain signal")
        e2 = mem.record_event("mutation", "Response to pain")
        mem.record_relationship(e1, e2, "caused")
        assert len(mem._relationships) == 1
        assert mem._relationships[0].rel_type == "caused"
        assert mem._relationships[0].from_id == e1
        assert mem._relationships[0].to_id == e2

    def test_developmental_narrative(self, tmp_path):
        from dharma_swarm.organism_memory import OrganismMemory
        mem = OrganismMemory(state_dir=tmp_path)
        mem.record_event("mutation", "First change")
        mem.record_event("insight", "Learned something")
        narrative = mem.developmental_narrative()
        assert "First change" in narrative
        assert "Learned something" in narrative

    def test_developmental_narrative_empty(self, tmp_path):
        from dharma_swarm.organism_memory import OrganismMemory
        mem = OrganismMemory(state_dir=tmp_path)
        narrative = mem.developmental_narrative()
        assert isinstance(narrative, str)
        assert len(narrative) > 0

    def test_persistence(self, tmp_path):
        from dharma_swarm.organism_memory import OrganismMemory
        mem1 = OrganismMemory(state_dir=tmp_path)
        mem1.record_event("mutation", "Persistent event")

        # Create new instance — should load from disk
        mem2 = OrganismMemory(state_dir=tmp_path)
        assert len(mem2._entities) == 1
        assert mem2._entities[0].description == "Persistent event"

    def test_persistence_relationships(self, tmp_path):
        from dharma_swarm.organism_memory import OrganismMemory
        mem1 = OrganismMemory(state_dir=tmp_path)
        e1 = mem1.record_event("mutation", "Event A")
        e2 = mem1.record_event("mutation", "Event B")
        mem1.record_relationship(e1, e2, "preceded")

        mem2 = OrganismMemory(state_dir=tmp_path)
        assert len(mem2._relationships) == 1
        assert mem2._relationships[0].rel_type == "preceded"

    def test_self_model_accuracy(self, tmp_path):
        from dharma_swarm.organism_memory import OrganismMemory
        mem = OrganismMemory(state_dir=tmp_path)
        mem.record_event("insight", "I am healthy", confidence=1.0)
        accuracy = mem.self_model_accuracy()
        assert 0.0 <= accuracy <= 1.0

    def test_self_model_accuracy_no_insights(self, tmp_path):
        from dharma_swarm.organism_memory import OrganismMemory
        mem = OrganismMemory(state_dir=tmp_path)
        # No insights → should return 1.0 (no known discrepancy)
        accuracy = mem.self_model_accuracy()
        assert accuracy == 1.0

    def test_shakti_profile(self, tmp_path):
        from dharma_swarm.organism_memory import OrganismMemory
        mem = OrganismMemory(state_dir=tmp_path)
        mem.record_event("capability", "Can route models", metadata={"domain": "routing"})
        profile = mem.shakti_profile()
        assert "routing" in profile
        assert len(profile["routing"]) == 1
        assert profile["routing"][0]["description"] == "Can route models"

    def test_shakti_profile_default_domain(self, tmp_path):
        from dharma_swarm.organism_memory import OrganismMemory
        mem = OrganismMemory(state_dir=tmp_path)
        mem.record_event("capability", "Generic capability")
        profile = mem.shakti_profile()
        assert "general" in profile

    def test_stats(self, tmp_path):
        from dharma_swarm.organism_memory import OrganismMemory
        mem = OrganismMemory(state_dir=tmp_path)
        mem.record_event("mutation", "Test")
        s = mem.stats()
        assert s["total_entities"] == 1
        assert s["total_relationships"] == 0
        assert "by_type" in s
        assert s["by_type"]["mutation"] == 1

    def test_entities_by_type_respects_limit(self, tmp_path):
        from dharma_swarm.organism_memory import OrganismMemory
        mem = OrganismMemory(state_dir=tmp_path)
        for i in range(15):
            mem.record_event("decision", f"Decision {i}")
        results = mem.entities_by_type("decision", last_n=5)
        assert len(results) == 5

    def test_multiple_entity_types(self, tmp_path):
        from dharma_swarm.organism_memory import OrganismMemory
        mem = OrganismMemory(state_dir=tmp_path)
        mem.record_event("mutation", "A mutation")
        mem.record_event("decision", "A decision")
        mem.record_event("insight", "An insight")
        assert len(mem.entities_by_type("mutation")) == 1
        assert len(mem.entities_by_type("decision")) == 1
        assert len(mem.entities_by_type("insight")) == 1
        assert len(mem._entities) == 3


class TestAlgedonicActivation:
    def _make_pulse(self, **overrides):
        from dharma_swarm.organism import OrganismPulse
        pulse = OrganismPulse()
        for k, v in overrides.items():
            setattr(pulse, k, v)
        return pulse

    def test_healthy_pulse_no_actions(self):
        from dharma_swarm.algedonic_activation import AlgedonicActivation
        activation = AlgedonicActivation(organism=None)
        pulse = self._make_pulse(
            audit_failure_rate=0.1,
            fleet_health=0.9,
            identity_coherence=0.9,
            anomalous_gate_patterns=0,
        )
        actions = activation.evaluate(pulse)
        assert len(actions) == 0

    def test_high_failure_rate_triggers(self):
        from dharma_swarm.algedonic_activation import AlgedonicActivation
        activation = AlgedonicActivation(organism=None)
        pulse = self._make_pulse(
            audit_failure_rate=0.7,
            fleet_health=0.9,
            identity_coherence=0.9,
            anomalous_gate_patterns=0,
        )
        actions = activation.evaluate(pulse)
        assert any(a.signal_type == "failure_rate" for a in actions)

    def test_high_failure_rate_action_is_recalibrate_routing(self):
        from dharma_swarm.algedonic_activation import AlgedonicActivation
        activation = AlgedonicActivation(organism=None)
        pulse = self._make_pulse(audit_failure_rate=0.6, fleet_health=0.9,
                                  identity_coherence=0.9, anomalous_gate_patterns=0)
        actions = activation.evaluate(pulse)
        fr_actions = [a for a in actions if a.signal_type == "failure_rate"]
        assert fr_actions[0].action == "recalibrate_routing"

    def test_omega_divergence_triggers(self):
        from dharma_swarm.algedonic_activation import AlgedonicActivation
        activation = AlgedonicActivation(organism=None)
        pulse = self._make_pulse(
            audit_failure_rate=0.1,
            fleet_health=0.9,
            identity_coherence=0.3,
            anomalous_gate_patterns=0,
        )
        actions = activation.evaluate(pulse)
        assert any(a.signal_type == "omega_divergence" for a in actions)

    def test_omega_divergence_action_is_rebalance(self):
        from dharma_swarm.algedonic_activation import AlgedonicActivation
        activation = AlgedonicActivation(organism=None)
        pulse = self._make_pulse(audit_failure_rate=0.1, fleet_health=0.9,
                                  identity_coherence=0.3, anomalous_gate_patterns=0)
        actions = activation.evaluate(pulse)
        od_actions = [a for a in actions if a.signal_type == "omega_divergence"]
        assert od_actions[0].action == "rebalance_priorities"

    def test_ontological_drift_triggers(self):
        from dharma_swarm.algedonic_activation import AlgedonicActivation
        activation = AlgedonicActivation(organism=None)
        pulse = self._make_pulse(
            audit_failure_rate=0.1,
            fleet_health=0.9,
            identity_coherence=0.9,
            anomalous_gate_patterns=8,
        )
        actions = activation.evaluate(pulse)
        assert any(a.signal_type == "ontological_drift" for a in actions)

    def test_ontological_drift_action_is_enforce_glossary(self):
        from dharma_swarm.algedonic_activation import AlgedonicActivation
        activation = AlgedonicActivation(organism=None)
        pulse = self._make_pulse(audit_failure_rate=0.1, fleet_health=0.9,
                                  identity_coherence=0.9, anomalous_gate_patterns=8)
        actions = activation.evaluate(pulse)
        od_actions = [a for a in actions if a.signal_type == "ontological_drift"]
        assert od_actions[0].action == "enforce_glossary"

    def test_telos_drift_triggers(self):
        from dharma_swarm.algedonic_activation import AlgedonicActivation
        activation = AlgedonicActivation(organism=None)
        pulse = self._make_pulse(
            audit_failure_rate=0.1,
            fleet_health=0.8,
            identity_coherence=0.2,
            anomalous_gate_patterns=0,
        )
        actions = activation.evaluate(pulse)
        assert any(a.signal_type == "telos_drift" for a in actions)

    def test_telos_drift_action_is_gnani_checkpoint(self):
        from dharma_swarm.algedonic_activation import AlgedonicActivation
        activation = AlgedonicActivation(organism=None)
        pulse = self._make_pulse(audit_failure_rate=0.1, fleet_health=0.8,
                                  identity_coherence=0.2, anomalous_gate_patterns=0)
        actions = activation.evaluate(pulse)
        td_actions = [a for a in actions if a.signal_type == "telos_drift"]
        assert td_actions[0].action == "gnani_checkpoint"

    def test_telos_drift_critical_severity(self):
        from dharma_swarm.algedonic_activation import AlgedonicActivation
        activation = AlgedonicActivation(organism=None)
        pulse = self._make_pulse(audit_failure_rate=0.1, fleet_health=0.8,
                                  identity_coherence=0.2, anomalous_gate_patterns=0)
        actions = activation.evaluate(pulse)
        td_actions = [a for a in actions if a.signal_type == "telos_drift"]
        assert td_actions[0].severity == "critical"

    def test_apply_logs_action(self):
        from dharma_swarm.algedonic_activation import AlgedonicActivation, AlgedonicAction
        activation = AlgedonicActivation(organism=None)
        action = AlgedonicAction(
            signal_type="test",
            severity="low",
            description="Test",
            action="test_action",
        )
        activation.apply(action)
        assert len(activation.recent_activations) == 1
        assert activation.recent_activations[0]["signal"] == "test"

    def test_recent_activations_capped_at_20(self):
        from dharma_swarm.algedonic_activation import AlgedonicActivation, AlgedonicAction
        activation = AlgedonicActivation(organism=None)
        for i in range(25):
            activation.apply(AlgedonicAction(
                signal_type=f"signal_{i}",
                severity="low",
                description=f"Event {i}",
                action="do_something",
            ))
        assert len(activation.recent_activations) == 20

    def test_no_telos_drift_when_fleet_unhealthy(self):
        """Telos drift should NOT trigger if fleet is also unhealthy."""
        from dharma_swarm.algedonic_activation import AlgedonicActivation
        activation = AlgedonicActivation(organism=None)
        # Both low → not telos drift (fleet is struggling too)
        pulse = self._make_pulse(audit_failure_rate=0.1, fleet_health=0.3,
                                  identity_coherence=0.2, anomalous_gate_patterns=0)
        actions = activation.evaluate(pulse)
        assert not any(a.signal_type == "telos_drift" for a in actions)


class TestIntegration:
    def test_organism_has_memory_after_boot(self, tmp_path):
        """Organism should have memory, attractor, and algedonic_activation after init."""
        from dharma_swarm.organism import Organism
        org = Organism(state_dir=tmp_path)
        # These should exist (may be None if import fails, but should not raise)
        assert hasattr(org, 'memory')
        assert hasattr(org, 'attractor')
        assert hasattr(org, 'algedonic_activation')

    def test_organism_memory_is_not_none(self, tmp_path):
        """OrganismMemory should successfully initialize."""
        from dharma_swarm.organism import Organism
        org = Organism(state_dir=tmp_path)
        assert org.memory is not None

    def test_organism_attractor_is_not_none(self, tmp_path):
        """DharmaAttractor should successfully initialize."""
        from dharma_swarm.organism import Organism
        org = Organism(state_dir=tmp_path)
        assert org.attractor is not None

    def test_organism_algedonic_activation_is_not_none(self, tmp_path):
        """AlgedonicActivation should successfully initialize."""
        from dharma_swarm.organism import Organism
        org = Organism(state_dir=tmp_path)
        assert org.algedonic_activation is not None

    def test_attractor_ambient_seed_is_stable(self):
        """Ambient seed should be deterministic — same content every time."""
        from dharma_swarm.dharma_attractor import DharmaAttractor
        a1 = DharmaAttractor()
        a2 = DharmaAttractor()
        assert a1.ambient_seed() == a2.ambient_seed()

    def test_organism_status_has_phase4_fields(self, tmp_path):
        """Status dict should include memory, attractor, algedonic_activations."""
        from dharma_swarm.organism import Organism
        org = Organism(state_dir=tmp_path)
        status = org.status()
        assert "memory" in status
        assert "attractor" in status
        assert "algedonic_activations" in status
        assert status["attractor"] == "active"

    def test_organism_memory_records_to_disk(self, tmp_path):
        """Memory entities should persist to JSONL file."""
        from dharma_swarm.organism import Organism
        org = Organism(state_dir=tmp_path)
        assert org.memory is not None
        org.memory.record_event("insight", "Integration test insight")
        # Check file was created
        mem_dir = tmp_path / "organism_memory"
        assert mem_dir.exists()
        entities_file = mem_dir / "entities.jsonl"
        assert entities_file.exists()
        content = entities_file.read_text()
        assert "Integration test insight" in content
