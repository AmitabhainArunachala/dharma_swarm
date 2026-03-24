"""Tests for the Telic Seam — Phase A/A.2 write-through metabolic loop.

Verifies:
1. New ontology types exist (ActionProposal, GateDecisionRecord, Outcome, VentureCell,
   ValueEvent, Contribution)
2. TelicSeam.record_dispatch creates ActionProposal
3. TelicSeam.record_gate_decision creates GateDecisionRecord + links
4. TelicSeam.record_outcome creates Outcome + lineage edge
5. TelicSeam.record_value_event creates ValueEvent with composite scoring
6. TelicSeam.record_contribution creates Contribution with attributed_value
7. Full loop: dispatch → gate → outcome → value_event → contribution → lineage
8. Idempotency: duplicate calls return same IDs
9. Stats reflect the metabolic state
"""

import pytest

from dharma_swarm.lineage import LineageGraph
from dharma_swarm.models import (
    GateCheckResult,
    GateDecision,
    GateResult,
    Task,
    TaskPriority,
)
from dharma_swarm.ontology import OntologyRegistry
from dharma_swarm.ontology_runtime import get_shared_registry, reset_shared_registry
from dharma_swarm.telic_seam import TelicSeam, get_seam, reset_seam


@pytest.fixture
def registry():
    return OntologyRegistry.create_dharma_registry()


@pytest.fixture
def lineage(tmp_path):
    return LineageGraph(db_path=tmp_path / "test_lineage.db")


@pytest.fixture
def seam(registry, lineage):
    return TelicSeam(registry=registry, lineage=lineage)


@pytest.fixture
def sample_task():
    return Task(
        title="Compute R_V for Mistral-7B",
        description="Run p0_canonical_pipeline on base model",
        priority=TaskPriority.HIGH,
    )


@pytest.fixture
def gate_allow():
    return GateCheckResult(
        decision=GateDecision.ALLOW,
        reason="All gates passed",
        gate_results={
            "AHIMSA": (GateResult.PASS, ""),
            "SATYA": (GateResult.PASS, ""),
        },
    )


@pytest.fixture
def gate_block():
    return GateCheckResult(
        decision=GateDecision.BLOCK,
        reason="AHIMSA violation: Harmful content",
        gate_results={
            "AHIMSA": (GateResult.FAIL, "Harmful content"),
            "SATYA": (GateResult.PASS, ""),
        },
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Ontology Type Registration
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestOntologyTypes:
    """Verify new metabolic loop types are registered."""

    def test_action_proposal_type_exists(self, registry):
        t = registry.get_type("ActionProposal")
        assert t is not None
        assert "task_id" in t.properties
        assert "agent_id" in t.properties
        assert "status" in t.properties
        assert "action_type" in t.properties

    def test_gate_decision_record_type_exists(self, registry):
        t = registry.get_type("GateDecisionRecord")
        assert t is not None
        assert "proposal_id" in t.properties
        assert "decision" in t.properties
        assert "gate_results" in t.properties

    def test_outcome_type_exists(self, registry):
        t = registry.get_type("Outcome")
        assert t is not None
        assert "proposal_id" in t.properties
        assert "success" in t.properties
        assert "fitness_score" in t.properties

    def test_value_event_type_exists(self, registry):
        t = registry.get_type("ValueEvent")
        assert t is not None
        assert "outcome_id" in t.properties
        assert "composite_value" in t.properties
        assert "behavioral_signal" in t.properties
        assert "success_value" in t.properties

    def test_contribution_type_exists(self, registry):
        t = registry.get_type("Contribution")
        assert t is not None
        assert "value_event_id" in t.properties
        assert "agent_id" in t.properties
        assert "credit_share" in t.properties
        assert "attributed_value" in t.properties

    def test_venture_cell_type_exists(self, registry):
        t = registry.get_type("VentureCell")
        assert t is not None
        assert "name" in t.properties
        assert "autonomy_stage" in t.properties
        assert "domain" in t.properties

    def test_metabolic_links_registered(self, registry):
        """Verify the metabolic loop links exist."""
        links = registry.get_links_for("ActionProposal")
        link_names = {ld.name for ld in links}
        assert "has_gate_decision" in link_names
        assert "has_outcome" in link_names

    def test_value_event_links_registered(self, registry):
        links = registry.get_links_for("Outcome")
        link_names = {ld.name for ld in links}
        assert "has_value_event" in link_names

    def test_contribution_links_registered(self, registry):
        links = registry.get_links_for("ValueEvent")
        link_names = {ld.name for ld in links}
        assert "has_contribution" in link_names

    def test_venture_cell_links(self, registry):
        links = registry.get_links_for("VentureCell")
        link_names = {ld.name for ld in links}
        assert "cell_has_agent" in link_names
        assert "cell_has_thread" in link_names

    def test_total_types_increased(self, registry):
        """Should have 14 types (8 original + 6 metabolic)."""
        assert registry.stats()["registered_types"] >= 14

    def test_save_load_round_trip(self, registry, tmp_path):
        """New types survive save/load cycle."""
        # Create some objects
        registry.create_object("ActionProposal", {
            "task_id": "t1", "agent_id": "a1",
            "action_type": "dispatch", "title": "Test",
            "status": "proposed", "priority": "normal",
        })
        registry.create_object("VentureCell", {
            "name": "R_V Research",
            "domain": "research",
            "autonomy_stage": 2,
            "status": "active",
        })

        path = tmp_path / "ontology.json"
        registry.save(path)

        # Load into fresh registry
        fresh = OntologyRegistry.create_dharma_registry()
        count = fresh.load(path)
        assert count > 0
        assert len(fresh.get_objects_by_type("ActionProposal")) == 1
        assert len(fresh.get_objects_by_type("VentureCell")) == 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TelicSeam — Record Dispatch
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestRecordDispatch:
    def test_creates_action_proposal(self, seam, sample_task):
        proposal_id = seam.record_dispatch(sample_task, "agent_alpha")
        assert proposal_id is not None

        obj = seam.registry.get_object(proposal_id)
        assert obj is not None
        assert obj.type_name == "ActionProposal"
        assert obj.properties["task_id"] == sample_task.id
        assert obj.properties["agent_id"] == "agent_alpha"
        assert obj.properties["status"] == "proposed"
        assert obj.properties["priority"] == "high"

    def test_stores_task_id_mapping(self, seam, sample_task):
        proposal_id = seam.record_dispatch(sample_task, "agent_alpha")
        assert seam.get_proposal_for_task(sample_task.id) == proposal_id

    def test_multiple_dispatches(self, seam):
        tasks = [
            Task(title=f"Task {i}", priority=TaskPriority.NORMAL)
            for i in range(5)
        ]
        ids = [seam.record_dispatch(t, f"agent_{i}") for i, t in enumerate(tasks)]
        assert all(pid is not None for pid in ids)
        assert len(set(ids)) == 5  # All unique

    def test_default_seam_uses_shared_registry(
        self,
        tmp_path,
        monkeypatch,
        sample_task,
    ):
        monkeypatch.setenv("DHARMA_ONTOLOGY_PATH", str(tmp_path / "ontology.json"))
        reset_shared_registry()
        reset_seam()

        seam = get_seam()
        proposal_id = seam.record_dispatch(sample_task, "agent_alpha")

        assert seam.registry is get_shared_registry()
        assert proposal_id is not None

        reset_shared_registry()
        reloaded = get_shared_registry()
        proposal = reloaded.get_object(proposal_id)
        assert proposal is not None
        assert proposal.properties["agent_id"] == "agent_alpha"

        reset_seam()
        reset_shared_registry()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TelicSeam — Record Gate Decision
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestRecordGateDecision:
    def test_creates_gate_decision_record(self, seam, sample_task, gate_allow):
        proposal_id = seam.record_dispatch(sample_task, "agent_alpha")
        gate_id = seam.record_gate_decision(proposal_id, gate_allow)

        assert gate_id is not None
        obj = seam.registry.get_object(gate_id)
        assert obj is not None
        assert obj.type_name == "GateDecisionRecord"
        assert obj.properties["decision"] == "allow"

    def test_links_to_proposal(self, seam, sample_task, gate_allow):
        proposal_id = seam.record_dispatch(sample_task, "agent_alpha")
        gate_id = seam.record_gate_decision(proposal_id, gate_allow)

        links = seam.registry.get_links(source_id=proposal_id, link_name="has_gate_decision")
        assert len(links) == 1
        assert links[0].target_id == gate_id

    def test_updates_proposal_status_allow(self, seam, sample_task, gate_allow):
        proposal_id = seam.record_dispatch(sample_task, "agent_alpha")
        seam.record_gate_decision(proposal_id, gate_allow)

        proposal = seam.registry.get_object(proposal_id)
        assert proposal.properties["status"] == "approved"

    def test_updates_proposal_status_block(self, seam, sample_task, gate_block):
        proposal_id = seam.record_dispatch(sample_task, "agent_alpha")
        seam.record_gate_decision(proposal_id, gate_block)

        proposal = seam.registry.get_object(proposal_id)
        assert proposal.properties["status"] == "rejected"

    def test_none_proposal_returns_none(self, seam, gate_allow):
        result = seam.record_gate_decision(None, gate_allow)
        assert result is None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TelicSeam — Record Outcome
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestRecordOutcome:
    def test_creates_outcome_object(self, seam, sample_task):
        seam.record_dispatch(sample_task, "agent_alpha")
        outcome_id = seam.record_outcome(
            sample_task, "agent_alpha",
            success=True,
            result_summary="R_V = 0.73 for Mistral-7B",
            duration_ms=1234.5,
        )
        assert outcome_id is not None

        obj = seam.registry.get_object(outcome_id)
        assert obj is not None
        assert obj.type_name == "Outcome"
        assert obj.properties["success"] is True
        assert "R_V = 0.73" in obj.properties["result_summary"]

    def test_links_outcome_to_proposal(self, seam, sample_task):
        proposal_id = seam.record_dispatch(sample_task, "agent_alpha")
        outcome_id = seam.record_outcome(
            sample_task, "agent_alpha", success=True,
        )

        links = seam.registry.get_links(source_id=proposal_id, link_name="has_outcome")
        assert len(links) == 1
        assert links[0].target_id == outcome_id

    def test_updates_proposal_status_completed(self, seam, sample_task):
        proposal_id = seam.record_dispatch(sample_task, "agent_alpha")
        seam.record_outcome(sample_task, "agent_alpha", success=True)

        proposal = seam.registry.get_object(proposal_id)
        assert proposal.properties["status"] == "completed"

    def test_records_lineage_edge(self, seam, sample_task):
        seam.record_dispatch(sample_task, "agent_alpha")
        seam.record_outcome(
            sample_task, "agent_alpha",
            success=True, result_summary="done",
        )

        edges = seam.lineage.edges_for_task(sample_task.id)
        assert len(edges) == 1
        assert edges[0].agent == "agent_alpha"
        assert edges[0].operation == "task_execution"
        assert sample_task.id in edges[0].input_artifacts

    def test_failure_outcome(self, seam, sample_task):
        proposal_id = seam.record_dispatch(sample_task, "agent_alpha")
        outcome_id = seam.record_outcome(
            sample_task, "agent_alpha",
            success=False,
            error="OOM on RunPod",
        )
        assert outcome_id is not None

        obj = seam.registry.get_object(outcome_id)
        assert obj.properties["success"] is False
        assert "OOM" in obj.properties["error"]

        proposal = seam.registry.get_object(proposal_id)
        assert proposal.properties["status"] == "failed"

    def test_outcome_without_prior_dispatch(self, seam, sample_task):
        """Outcome can be recorded even without a dispatch (graceful)."""
        outcome_id = seam.record_outcome(
            sample_task, "agent_alpha", success=True,
        )
        assert outcome_id is not None

    def test_outcome_idempotent_for_proposal(self, seam, sample_task):
        proposal_id = seam.record_dispatch(sample_task, "agent_alpha")

        outcome_id_1 = seam.record_outcome(
            sample_task,
            "agent_alpha",
            success=True,
            result_summary="first",
        )
        outcome_id_2 = seam.record_outcome(
            sample_task,
            "agent_alpha",
            success=False,
            error="retry race",
        )

        assert proposal_id is not None
        assert outcome_id_1 == outcome_id_2
        assert len(seam.registry.get_objects_by_type("Outcome")) == 1
        assert len(seam.registry.get_links(source_id=proposal_id, link_name="has_outcome")) == 1
        assert len(seam.lineage.edges_for_task(sample_task.id)) == 1

        stats = seam.stats()
        assert stats["duplicate_suppressions"]["outcomes"] == 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Full Metabolic Loop
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestFullLoop:
    def test_dispatch_gate_outcome_lineage(self, seam, sample_task, gate_allow):
        """Full Phase A loop: dispatch → gate → execute → outcome → lineage."""
        # 1. Dispatch creates ActionProposal
        proposal_id = seam.record_dispatch(sample_task, "agent_alpha")
        assert proposal_id is not None

        # 2. Gate check creates GateDecisionRecord
        gate_id = seam.record_gate_decision(proposal_id, gate_allow)
        assert gate_id is not None

        # 3. Execution creates Outcome + lineage
        outcome_id = seam.record_outcome(
            sample_task, "agent_alpha",
            success=True,
            result_summary="R_V contraction confirmed",
            duration_ms=5432.1,
            fitness_score=0.85,
        )
        assert outcome_id is not None

        # Verify the full chain via ontology
        proposal = seam.registry.get_object(proposal_id)
        assert proposal.properties["status"] == "completed"

        gate_links = seam.registry.get_links(
            source_id=proposal_id, link_name="has_gate_decision",
        )
        assert len(gate_links) == 1

        outcome_links = seam.registry.get_links(
            source_id=proposal_id, link_name="has_outcome",
        )
        assert len(outcome_links) == 1

        # Verify lineage
        edges = seam.lineage.edges_for_task(sample_task.id)
        assert len(edges) == 1
        assert edges[0].metadata["success"] is True
        assert edges[0].metadata["proposal_id"] == proposal_id

    def test_stats_reflect_loop(self, seam, sample_task, gate_allow):
        """Stats should show metabolic activity."""
        seam.record_dispatch(sample_task, "agent_alpha")
        seam.record_gate_decision(
            seam.get_proposal_for_task(sample_task.id), gate_allow,
        )
        seam.record_outcome(sample_task, "agent_alpha", success=True)

        stats = seam.stats()
        assert stats["proposals"] == 1
        assert stats["gate_decisions"] == 1
        assert stats["outcomes"] == 1
        assert stats["lineage_edges"] == 1
        assert stats["registered_types"] >= 14
        assert stats["duplicate_suppressions_total"] == 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TelicSeam — Record ValueEvent (Phase A.2)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestValueEvent:
    def test_record_value_event_creates_object(self, seam, sample_task):
        seam.record_dispatch(sample_task, "agent_alpha")
        outcome_id = seam.record_outcome(
            sample_task, "agent_alpha", success=True,
            result_summary="done", duration_ms=5000.0,
        )
        assert outcome_id is not None

        ve_id = seam.record_value_event(
            outcome_id, sample_task, "agent_alpha",
            result_text="done", success=True, duration_ms=5000.0,
        )
        assert ve_id is not None

        obj = seam.registry.get_object(ve_id)
        assert obj is not None
        assert obj.type_name == "ValueEvent"
        assert obj.properties["outcome_id"] == outcome_id
        assert obj.properties["agent_id"] == "agent_alpha"
        assert obj.properties["scoring_method"] == "metrics_v1"

    def test_value_event_links_to_outcome(self, seam, sample_task):
        seam.record_dispatch(sample_task, "agent_alpha")
        outcome_id = seam.record_outcome(
            sample_task, "agent_alpha", success=True,
        )
        ve_id = seam.record_value_event(
            outcome_id, sample_task, "agent_alpha",
            result_text="result", success=True, duration_ms=1000.0,
        )

        links = seam.registry.get_links(
            source_id=outcome_id, link_name="has_value_event",
        )
        assert len(links) == 1
        assert links[0].target_id == ve_id

    def test_value_event_computes_composite(self, seam, sample_task):
        seam.record_dispatch(sample_task, "agent_alpha")
        outcome_id = seam.record_outcome(
            sample_task, "agent_alpha", success=True,
        )
        ve_id = seam.record_value_event(
            outcome_id, sample_task, "agent_alpha",
            result_text="result", success=True, duration_ms=5000.0,
        )
        obj = seam.registry.get_object(ve_id)
        cv = obj.properties["composite_value"]
        assert 0.0 <= cv <= 1.0
        assert obj.properties["success_value"] == 1.0

    def test_value_event_failure_path(self, seam, sample_task):
        seam.record_dispatch(sample_task, "agent_alpha")
        outcome_id = seam.record_outcome(
            sample_task, "agent_alpha", success=False, error="OOM",
        )
        ve_id = seam.record_value_event(
            outcome_id, sample_task, "agent_alpha",
            result_text="OOM error", success=False, duration_ms=1000.0,
        )
        obj = seam.registry.get_object(ve_id)
        assert obj.properties["success_value"] == 0.0
        # Failure composite should be lower than success composite
        assert obj.properties["composite_value"] < 1.0

    def test_value_event_idempotent(self, seam, sample_task):
        seam.record_dispatch(sample_task, "agent_alpha")
        outcome_id = seam.record_outcome(
            sample_task, "agent_alpha", success=True,
        )
        ve_id_1 = seam.record_value_event(
            outcome_id, sample_task, "agent_alpha",
            result_text="result", success=True, duration_ms=1000.0,
        )
        ve_id_2 = seam.record_value_event(
            outcome_id, sample_task, "agent_alpha",
            result_text="result", success=True, duration_ms=1000.0,
        )
        assert ve_id_1 == ve_id_2
        assert seam.stats()["duplicate_suppressions"]["value_events"] == 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TelicSeam — Record Contribution (Phase A.2)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestContribution:
    def _make_value_event(self, seam, sample_task):
        """Helper: dispatch → outcome → value_event, return (outcome_id, ve_id, composite)."""
        seam.record_dispatch(sample_task, "agent_alpha")
        outcome_id = seam.record_outcome(
            sample_task, "agent_alpha", success=True,
            result_summary="done", duration_ms=5000.0,
        )
        ve_id = seam.record_value_event(
            outcome_id, sample_task, "agent_alpha",
            result_text="done", success=True, duration_ms=5000.0,
        )
        ve_obj = seam.registry.get_object(ve_id)
        cv = ve_obj.properties["composite_value"]
        return outcome_id, ve_id, cv

    def test_record_contribution_creates_object(self, seam, sample_task):
        _, ve_id, cv = self._make_value_event(seam, sample_task)
        c_id = seam.record_contribution(
            ve_id, "agent_alpha", composite_value=cv,
        )
        assert c_id is not None

        obj = seam.registry.get_object(c_id)
        assert obj is not None
        assert obj.type_name == "Contribution"
        assert obj.properties["attributed_value"] == cv * 1.0
        assert obj.properties["credit_share"] == 1.0

    def test_contribution_links_to_value_event(self, seam, sample_task):
        _, ve_id, cv = self._make_value_event(seam, sample_task)
        c_id = seam.record_contribution(
            ve_id, "agent_alpha", composite_value=cv,
        )

        links = seam.registry.get_links(
            source_id=ve_id, link_name="has_contribution",
        )
        assert len(links) == 1
        assert links[0].target_id == c_id

    def test_contribution_idempotent(self, seam, sample_task):
        _, ve_id, cv = self._make_value_event(seam, sample_task)
        c_id_1 = seam.record_contribution(
            ve_id, "agent_alpha", composite_value=cv,
        )
        c_id_2 = seam.record_contribution(
            ve_id, "agent_alpha", composite_value=cv,
        )
        assert c_id_1 == c_id_2
        assert seam.stats()["duplicate_suppressions"]["contributions"] == 1

    def test_contribution_default_credit_share(self, seam, sample_task):
        _, ve_id, cv = self._make_value_event(seam, sample_task)
        c_id = seam.record_contribution(
            ve_id, "agent_alpha", composite_value=cv,
        )
        obj = seam.registry.get_object(c_id)
        assert obj.properties["credit_share"] == 1.0
        assert obj.properties["attributed_value"] == cv

    def test_contribution_partial_credit(self, seam, sample_task):
        _, ve_id, cv = self._make_value_event(seam, sample_task)
        c_id = seam.record_contribution(
            ve_id, "agent_beta", credit_share=0.5, composite_value=cv,
        )
        obj = seam.registry.get_object(c_id)
        assert obj.properties["credit_share"] == 0.5
        assert abs(obj.properties["attributed_value"] - cv * 0.5) < 1e-9


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# VentureCell
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestVentureCell:
    def test_create_venture_cell(self, registry):
        obj, errors = registry.create_object("VentureCell", {
            "name": "R_V Research",
            "domain": "research",
            "autonomy_stage": 2,
            "status": "active",
        })
        assert obj is not None
        assert not errors
        assert obj.properties["name"] == "R_V Research"

    def test_create_venture_cell_with_kpis(self, registry):
        obj, errors = registry.create_object("VentureCell", {
            "name": "Jagat Kalyan",
            "domain": "community",
            "autonomy_stage": 1,
            "status": "incubating",
            "kpis": {
                "welfare_tons": 0,
                "partners": 0,
                "pilot_started": False,
            },
        })
        assert obj is not None
        assert not errors
        assert obj.properties["kpis"]["welfare_tons"] == 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TelicSeam — Query Agent Fitness (Phase B.1)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestQueryAgentFitness:
    def test_no_data_returns_neutral(self, seam):
        score, n = seam.query_agent_fitness("nonexistent_agent")
        assert score == pytest.approx(0.5)
        assert n == 0

    def test_single_contribution(self, seam, sample_task):
        seam.record_dispatch(sample_task, "agent_alpha")
        outcome_id = seam.record_outcome(
            sample_task, "agent_alpha", success=True,
            result_summary="done", duration_ms=5000.0,
        )
        ve_id = seam.record_value_event(
            outcome_id, sample_task, "agent_alpha",
            result_text="done", success=True, duration_ms=5000.0,
        )
        ve_obj = seam.registry.get_object(ve_id)
        cv = ve_obj.properties["composite_value"]
        seam.record_contribution(
            ve_id, "agent_alpha", composite_value=cv,
        )

        score, n = seam.query_agent_fitness("agent_alpha")
        assert n == 1
        # Bayesian smoothed: (5*0.5 + cv) / (5 + 1)
        expected = (5 * 0.5 + cv) / 6
        assert score == pytest.approx(expected, abs=1e-6)

    def test_multiple_contributions_smoothed(self, seam):
        # Create 3 contributions manually with known attributed_values
        for i in range(3):
            t = Task(title=f"Task {i}", priority=TaskPriority.HIGH)
            seam.record_dispatch(t, "agent_alpha")
            oid = seam.record_outcome(t, "agent_alpha", success=True,
                                       result_summary="ok", duration_ms=1000.0)
            ve_id = seam.record_value_event(
                oid, t, "agent_alpha",
                result_text="ok", success=True, duration_ms=1000.0,
            )
            ve_obj = seam.registry.get_object(ve_id)
            cv = ve_obj.properties["composite_value"]
            seam.record_contribution(
                ve_id, "agent_alpha", composite_value=cv,
            )

        score, n = seam.query_agent_fitness("agent_alpha")
        assert n == 3
        # Score should not be raw mean — it should be Bayesian smoothed toward 0.5
        assert 0.0 < score < 1.0

    def test_cell_id_filter(self, seam, sample_task):
        seam.record_dispatch(sample_task, "agent_alpha")
        oid = seam.record_outcome(sample_task, "agent_alpha", success=True,
                                   result_summary="done", duration_ms=5000.0)
        ve_id = seam.record_value_event(
            oid, sample_task, "agent_alpha",
            result_text="done", success=True, duration_ms=5000.0,
            cell_id="rv_cell",
        )
        ve_obj = seam.registry.get_object(ve_id)
        cv = ve_obj.properties["composite_value"]
        seam.record_contribution(
            ve_id, "agent_alpha", composite_value=cv,
            cell_id="rv_cell",
        )

        # Matching cell_id → finds data
        score_match, n_match = seam.query_agent_fitness(
            "agent_alpha", cell_id="rv_cell",
        )
        assert n_match == 1

        # Non-matching cell_id → no data, returns prior
        score_miss, n_miss = seam.query_agent_fitness(
            "agent_alpha", cell_id="other_cell",
        )
        assert n_miss == 0
        assert score_miss == pytest.approx(0.5)

    def test_task_type_filter(self, seam, sample_task):
        seam.record_dispatch(sample_task, "agent_alpha")
        oid = seam.record_outcome(sample_task, "agent_alpha", success=True,
                                   result_summary="done", duration_ms=5000.0)
        ve_id = seam.record_value_event(
            oid, sample_task, "agent_alpha",
            result_text="done", success=True, duration_ms=5000.0,
        )
        ve_obj = seam.registry.get_object(ve_id)
        cv = ve_obj.properties["composite_value"]
        seam.record_contribution(
            ve_id, "agent_alpha", composite_value=cv,
            task_type="experiment",
        )

        # Matching task_type → finds data
        score_match, n_match = seam.query_agent_fitness(
            "agent_alpha", task_type="experiment",
        )
        assert n_match == 1

        # Non-matching → prior
        score_miss, n_miss = seam.query_agent_fitness(
            "agent_alpha", task_type="build",
        )
        assert n_miss == 0

    def test_low_sample_count_stays_near_prior(self, seam, sample_task):
        """With only 1-2 samples, score should stay close to 0.5 (prior)."""
        seam.record_dispatch(sample_task, "agent_alpha")
        oid = seam.record_outcome(sample_task, "agent_alpha", success=True,
                                   result_summary="perfect", duration_ms=100.0)
        ve_id = seam.record_value_event(
            oid, sample_task, "agent_alpha",
            result_text="perfect", success=True, duration_ms=100.0,
        )
        ve_obj = seam.registry.get_object(ve_id)
        cv = ve_obj.properties["composite_value"]
        seam.record_contribution(
            ve_id, "agent_alpha", composite_value=cv,
        )

        score, n = seam.query_agent_fitness("agent_alpha")
        assert n == 1
        # With prior weight 5, one sample can't move far from 0.5
        assert abs(score - 0.5) < 0.2


class TestLifecycleIntegrityReport:
    def test_clean_chain_reports_no_issues(self, seam, sample_task):
        seam.record_dispatch(sample_task, "agent_alpha")
        outcome_id = seam.record_outcome(sample_task, "agent_alpha", success=True)
        ve_id = seam.record_value_event(
            outcome_id,
            sample_task,
            "agent_alpha",
            success=True,
            duration_ms=1000.0,
            cell_id="rv_cell",
        )
        ve_obj = seam.registry.get_object(ve_id)
        seam.record_contribution(
            ve_id,
            "agent_alpha",
            composite_value=ve_obj.properties["composite_value"],
            cell_id="rv_cell",
            task_type=ve_obj.properties["task_type"],
        )

        report = seam.lifecycle_integrity_report()

        assert report["is_clean"] is True
        assert report["issue_count"] == 0

    def test_detects_agent_id_mismatch_between_proposal_and_outcome(self, seam, sample_task):
        seam.record_dispatch(sample_task, "agent_alpha")
        seam.record_outcome(sample_task, "display_name_only", success=True)

        report = seam.lifecycle_integrity_report()

        assert report["is_clean"] is False
        assert len(report["proposal_outcome_agent_mismatches"]) == 1

    def test_detects_duplicate_orphan_outcomes_for_single_proposal(self, seam, sample_task):
        proposal_id = seam.record_dispatch(sample_task, "agent_alpha")
        seam.record_outcome(sample_task, "agent_alpha", success=True)
        corrupt, errors = seam.registry.create_object(
            "Outcome",
            {
                "proposal_id": proposal_id,
                "task_id": sample_task.id,
                "agent_id": "agent_alpha",
                "success": False,
                "error": "legacy retry race",
            },
            created_by="test_corruption",
        )

        assert corrupt is not None
        assert not errors

        report = seam.lifecycle_integrity_report()

        assert report["is_clean"] is False
        assert len(report["duplicate_outcomes_per_proposal"]) == 1
        assert len(report["orphan_outcomes"]) == 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Fitness-biased Routing (Phase B.1)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestFitnessRouting:
    def test_feature_flag_off_returns_none(self, seam, sample_task):
        """With ENABLE_FITNESS_ROUTING unset, _fitness_biased_pick returns None."""
        import os
        from dharma_swarm.orchestrator import Orchestrator

        os.environ.pop("ENABLE_FITNESS_ROUTING", None)
        orch = Orchestrator.__new__(Orchestrator)

        from dharma_swarm.models import AgentRole, AgentState
        agents = [
            AgentState(id="a1", name="a1", role=AgentRole.CODER),
            AgentState(id="a2", name="a2", role=AgentRole.CODER),
        ]
        result = orch._fitness_biased_pick(agents, sample_task)
        assert result is None

    def test_fitness_biased_pick_prefers_higher_attributed_value(self, seam, sample_task):
        """With flag on, higher-attributed_value agent wins."""
        import os
        import dharma_swarm.telic_seam as _ts_mod
        os.environ["ENABLE_FITNESS_ROUTING"] = "true"

        # Point module singleton to test seam so _fitness_biased_pick reads our data
        old_seam = _ts_mod._SEAM
        _ts_mod._SEAM = seam

        try:
            from dharma_swarm.orchestrator import Orchestrator
            from dharma_swarm.models import AgentRole, AgentState

            # Create contributions: agent_a has high value, agent_b has low
            for agent_name, success in [("agent_a", True), ("agent_b", False)]:
                t = Task(title=f"Task for {agent_name}", priority=TaskPriority.HIGH)
                seam.record_dispatch(t, agent_name)
                oid = seam.record_outcome(t, agent_name, success=success,
                                           result_summary="ok", duration_ms=5000.0)
                ve_id = seam.record_value_event(
                    oid, t, agent_name,
                    result_text="ok", success=success, duration_ms=5000.0,
                )
                ve_obj = seam.registry.get_object(ve_id)
                cv = ve_obj.properties["composite_value"]
                seam.record_contribution(
                    ve_id, agent_name, composite_value=cv,
                )

            orch = Orchestrator.__new__(Orchestrator)
            orch._telic_seam = seam  # Wire test seam into instance
            agents = [
                AgentState(id="agent_b", name="agent_b", role=AgentRole.CODER),
                AgentState(id="agent_a", name="agent_a", role=AgentRole.CODER),
            ]

            # Seed random to avoid exploration
            import random
            random.seed(42)  # 42 gives random() > 0.1 first call

            result = orch._fitness_biased_pick(agents, sample_task)
            # agent_a (success=True) should have higher score than agent_b (success=False)
            assert result is not None
            assert result.id == "agent_a"
        finally:
            os.environ.pop("ENABLE_FITNESS_ROUTING", None)
            _ts_mod._SEAM = old_seam

    def test_fitness_within_role_matched_subset(self, seam, sample_task):
        """Role match narrows candidates, fitness picks within."""
        import os
        os.environ["ENABLE_FITNESS_ROUTING"] = "true"

        try:
            from dharma_swarm.orchestrator import Orchestrator
            from dharma_swarm.models import AgentRole, AgentState

            orch = Orchestrator.__new__(Orchestrator)
            orch._telic_seam = seam  # Wire test seam into instance

            # Two coders + one researcher
            agents = [
                AgentState(id="a1", name="a1", role=AgentRole.CODER),
                AgentState(id="a2", name="a2", role=AgentRole.CODER),
                AgentState(id="a3", name="a3", role=AgentRole.RESEARCHER),
            ]

            # Task with preferred_roles=["coder"]
            t = Task(
                title="Code task",
                priority=TaskPriority.HIGH,
                metadata={"coordination_preferred_roles": ["coder"]},
            )

            result = orch._select_idle_agent(t, agents)
            # Should pick from coders, not researcher
            assert result is not None
            assert result.id in ("a1", "a2")
        finally:
            os.environ.pop("ENABLE_FITNESS_ROUTING", None)

    def test_exploration_sometimes_random(self, seam, sample_task):
        """With exploration, some picks should be random."""
        import os
        import random
        os.environ["ENABLE_FITNESS_ROUTING"] = "true"

        try:
            from dharma_swarm.orchestrator import Orchestrator
            from dharma_swarm.models import AgentRole, AgentState

            orch = Orchestrator.__new__(Orchestrator)
            orch._telic_seam = seam  # Wire test seam into instance

            picks = {"a1": 0, "a2": 0}
            for i in range(100):
                random.seed(i)
                agents = [
                    AgentState(id="a1", name="a1", role=AgentRole.CODER),
                    AgentState(id="a2", name="a2", role=AgentRole.CODER),
                ]
                result = orch._fitness_biased_pick(agents, sample_task)
                if result:
                    picks[result.id] += 1

            # With 10% exploration, both agents should get some picks
            # (even with identical fitness, exploration picks randomly)
            assert picks["a1"] > 0
            assert picks["a2"] > 0
        finally:
            os.environ.pop("ENABLE_FITNESS_ROUTING", None)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Singleton
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestSingleton:
    def test_get_seam_returns_same_instance(self):
        reset_seam()
        a = get_seam()
        b = get_seam()
        assert a is b
        reset_seam()

    def test_reset_clears_singleton(self):
        reset_seam()
        a = get_seam()
        reset_seam()
        b = get_seam()
        assert a is not b
        reset_seam()
