"""Tests for ReplicationProtocol -- checkpoint-gated agent replication pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dharma_swarm.agent_constitution import (
    AgentSpec,
    ConstitutionalLayer,
    DynamicRoster,
)
from dharma_swarm.genome_inheritance import GenomeTemplate
from dharma_swarm.models import (
    AgentRole,
    GateCheckResult,
    GateDecision,
    GateResult,
    ProviderType,
)
from dharma_swarm.population_control import PopulationAssessment, PopulationController
from dharma_swarm.replication_protocol import (
    ReplicationOutcome,
    ReplicationProposal,
    ReplicationProtocol,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_proposal_data(**overrides: object) -> dict:
    """Build a minimal valid proposal data dict."""
    defaults = dict(
        proposed_role="scanner",
        capability_gap="vulnerability scanning",
        parent_agent="operator",
        generation=0,
        severity=0.5,
        justification="We need a scanner.",
    )
    defaults.update(overrides)
    return defaults


def make_child_spec(name: str = "scanner_g1_20260322") -> AgentSpec:
    """Create a child AgentSpec for mocking."""
    return AgentSpec(
        name=name,
        role=AgentRole.WORKER,
        layer=ConstitutionalLayer.DIRECTOR,
        vsm_function="Replicated for scanning",
        domain="scanning",
        system_prompt="You are a scanner agent.",
        default_provider=ProviderType.OPENROUTER,
        default_model="test-model",
        backup_models=[],
        constitutional_gates=["SATYA"],
        max_concurrent_workers=3,
        memory_namespace=name,
        spawn_authority=[],
        audit_cycle_seconds=0.0,
    )


def make_genome_template(child_name: str = "scanner_g1_20260322") -> GenomeTemplate:
    """Create a GenomeTemplate for mocking."""
    return GenomeTemplate(
        parent_name="operator",
        parent_generation=0,
        child_name=child_name,
        child_generation=1,
        kernel_signature="sha256_mock",
        inherited_gates=["SATYA"],
        system_prompt="child prompt",
        inherited_corpus_claims=[],
        inherited_memory_keys=[],
        role_specialization="vulnerability scanning",
        model="test-model",
        provider="openrouter",
        wake_interval_seconds=3600.0,
        spawn_authority=[],
    )


def make_gate_allow() -> GateCheckResult:
    """Create a GateCheckResult that ALLOWs."""
    return GateCheckResult(
        decision=GateDecision.ALLOW,
        reason="All gates passed",
        gate_results={"SATYA": (GateResult.PASS, "OK")},
    )


def make_gate_block() -> GateCheckResult:
    """Create a GateCheckResult that BLOCKs."""
    return GateCheckResult(
        decision=GateDecision.BLOCK,
        reason="AHIMSA gate failed",
        gate_results={"AHIMSA": (GateResult.FAIL, "Blocked")},
    )


def make_kernel_mock(*, valid: bool = True) -> MagicMock:
    """Create a mock DharmaKernel."""
    k = MagicMock()
    k.verify_integrity.return_value = valid
    k.compute_signature.return_value = "sha256_mock"
    return k


def make_kernel_guard_mock(*, valid: bool = True) -> MagicMock:
    """Create a mock KernelGuard whose load() returns a kernel."""
    guard = MagicMock()
    kernel = make_kernel_mock(valid=valid)
    guard.load = AsyncMock(return_value=kernel)
    guard.save = AsyncMock()
    return guard


# ---------------------------------------------------------------------------
# ReplicationProposal model tests
# ---------------------------------------------------------------------------


class TestReplicationProposal:
    def test_creation(self) -> None:
        p = ReplicationProposal(
            proposed_role="scanner",
            capability_gap="vulnerability scanning",
            parent_agent="operator",
            generation=0,
            severity=0.5,
        )
        assert p.status == "proposed"
        assert p.child_agent_name is None
        assert p.failure_reason is None

    def test_serialization_roundtrip(self) -> None:
        p = ReplicationProposal(
            proposed_role="monitor",
            capability_gap="system monitoring",
            parent_agent="witness",
            generation=1,
        )
        json_str = p.model_dump_json()
        p2 = ReplicationProposal.model_validate_json(json_str)
        assert p2.proposed_role == "monitor"
        assert p2.capability_gap == "system monitoring"

    def test_from_differentiation_proposal(self) -> None:
        dp_data = {
            "proposed_role": "analyst",
            "justification": "Gap in analysis capability",
            "capability_gap": "deep analysis",
            "evidence_cycles": [1, 2, 3],
        }
        p = ReplicationProposal.from_differentiation_proposal(
            dp_data=dp_data,
            parent_agent="research_director",
            generation=1,
            severity=0.7,
        )
        assert p.proposed_role == "analyst"
        assert p.parent_agent == "research_director"
        assert p.generation == 1
        assert p.severity == 0.7
        assert p.evidence_cycles == [1, 2, 3]


# ---------------------------------------------------------------------------
# ReplicationOutcome model tests
# ---------------------------------------------------------------------------


class TestReplicationOutcome:
    def test_success_outcome(self) -> None:
        proposal = ReplicationProposal(
            proposed_role="scanner",
            capability_gap="scanning",
            parent_agent="operator",
        )
        outcome = ReplicationOutcome(
            proposal=proposal,
            success=True,
            child_agent_name="scanner_g1_20260322",
        )
        assert outcome.success is True
        assert outcome.child_agent_name == "scanner_g1_20260322"

    def test_failure_outcome(self) -> None:
        proposal = ReplicationProposal(
            proposed_role="scanner",
            capability_gap="scanning",
            parent_agent="operator",
            status="failed",
            failure_reason="Generation cap exceeded",
        )
        outcome = ReplicationOutcome(
            proposal=proposal,
            success=False,
            error="Generation cap exceeded",
        )
        assert outcome.success is False
        assert outcome.error == "Generation cap exceeded"


# ---------------------------------------------------------------------------
# Proposal persistence
# ---------------------------------------------------------------------------


class TestProposalPersistence:
    def test_persist_and_load(self, tmp_path: Path) -> None:
        proto = ReplicationProtocol(state_dir=tmp_path)
        proposal = ReplicationProposal(
            proposed_role="persisted",
            capability_gap="persistence testing",
            parent_agent="operator",
        )
        proto._persist_proposal(proposal)
        loaded = proto.load_proposals()
        assert len(loaded) == 1
        assert loaded[0].proposed_role == "persisted"

    def test_get_pending_proposals(self, tmp_path: Path) -> None:
        proto = ReplicationProtocol(state_dir=tmp_path)
        # Write proposals with different statuses
        for role, status in [("a", "proposed"), ("b", "in_progress"), ("c", "proposed"), ("d", "materialized")]:
            p = ReplicationProposal(
                proposed_role=role,
                capability_gap=f"gap_{role}",
                parent_agent="operator",
                status=status,
            )
            proto._persist_proposal(p)

        pending = proto.get_pending_proposals()
        assert len(pending) == 2
        roles = {p.proposed_role for p in pending}
        assert roles == {"a", "c"}

    def test_persist_updates_existing(self, tmp_path: Path) -> None:
        proto = ReplicationProtocol(state_dir=tmp_path)
        p1 = ReplicationProposal(
            proposed_role="updater",
            capability_gap="the_gap",
            parent_agent="operator",
            status="proposed",
        )
        proto._persist_proposal(p1)
        # Now update status
        p1.status = "materialized"
        proto._persist_proposal(p1)
        loaded = proto.load_proposals()
        assert len(loaded) == 1
        assert loaded[0].status == "materialized"


# ---------------------------------------------------------------------------
# Validation (G1)
# ---------------------------------------------------------------------------


class TestValidation:
    def test_missing_required_field(self, tmp_path: Path) -> None:
        proto = ReplicationProtocol(state_dir=tmp_path)
        with pytest.raises(ValueError, match="Missing required field"):
            proto._validate_proposal({"proposed_role": "test"})

    def test_generation_cap(self, tmp_path: Path) -> None:
        config = MagicMock()
        config.max_generations = 2
        roster = DynamicRoster(state_dir=tmp_path)
        proto = ReplicationProtocol(
            state_dir=tmp_path,
            config=config,
            dynamic_roster=roster,
        )
        with pytest.raises(ValueError, match="exceeds max_generations"):
            proto._validate_proposal(make_proposal_data(generation=3))

    def test_missing_parent(self, tmp_path: Path) -> None:
        config = MagicMock()
        config.max_generations = 5
        roster = DynamicRoster(state_dir=tmp_path)
        proto = ReplicationProtocol(
            state_dir=tmp_path,
            config=config,
            dynamic_roster=roster,
        )
        with pytest.raises(ValueError, match="not found in roster"):
            proto._validate_proposal(make_proposal_data(parent_agent="ghost_agent"))

    def test_duplicate_detection(self, tmp_path: Path) -> None:
        config = MagicMock()
        config.max_generations = 5
        roster = DynamicRoster(state_dir=tmp_path)
        proto = ReplicationProtocol(
            state_dir=tmp_path,
            config=config,
            dynamic_roster=roster,
        )
        # Persist an in_progress proposal with the same capability_gap
        existing = ReplicationProposal(
            proposed_role="scanner",
            capability_gap="vulnerability scanning",
            parent_agent="operator",
            status="in_progress",
        )
        proto._persist_proposal(existing)

        with pytest.raises(ValueError, match="Duplicate proposal"):
            proto._validate_proposal(make_proposal_data())


# ---------------------------------------------------------------------------
# Full pipeline (mocked)
# ---------------------------------------------------------------------------


class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_full_pipeline_success(self, tmp_path: Path) -> None:
        child_spec = make_child_spec()
        child_name = child_spec.name
        genome = make_genome_template(child_name)

        # Build mocks
        config = MagicMock()
        config.max_generations = 2

        roster = DynamicRoster(state_dir=tmp_path)

        gate_keeper = MagicMock()
        gate_keeper.check.return_value = make_gate_allow()

        kernel_guard = make_kernel_guard_mock(valid=True)

        pop_ctrl = MagicMock(spec=PopulationController)
        pop_ctrl.can_add_agent.return_value = PopulationAssessment(
            can_add=True,
            current_population=6,
            max_population=8,
            reason="Below cap",
        )
        pop_ctrl.start_probation.return_value = MagicMock()
        pop_ctrl.execute_apoptosis = MagicMock()

        genome_inh = MagicMock()
        genome_inh.compose_child_spec = AsyncMock(return_value=(child_spec, genome))

        agent_registry = MagicMock()
        agent_registry.is_budget_exceeded.return_value = False
        agent_registry.register_agent.return_value = {"name": child_name}

        proto = ReplicationProtocol(
            state_dir=tmp_path,
            config=config,
            kernel_guard=kernel_guard,
            gate_keeper=gate_keeper,
            population_controller=pop_ctrl,
            genome_inheritance=genome_inh,
            agent_registry=agent_registry,
            dynamic_roster=roster,
        )

        outcome = await proto.run(make_proposal_data())
        assert outcome.success is True
        assert outcome.child_agent_name == child_name
        assert outcome.error is None

        # Child should be in roster
        assert roster.get(child_name) is not None

    @pytest.mark.asyncio
    async def test_pipeline_gate_failure(self, tmp_path: Path) -> None:
        config = MagicMock()
        config.max_generations = 2

        roster = DynamicRoster(state_dir=tmp_path)

        gate_keeper = MagicMock()
        gate_keeper.check.return_value = make_gate_block()

        kernel_guard = make_kernel_guard_mock(valid=True)

        pop_ctrl = MagicMock(spec=PopulationController)
        pop_ctrl.can_add_agent.return_value = PopulationAssessment(
            can_add=True,
            current_population=6,
            max_population=8,
            reason="Below cap",
        )

        agent_registry = MagicMock()
        agent_registry.is_budget_exceeded.return_value = False

        proto = ReplicationProtocol(
            state_dir=tmp_path,
            config=config,
            kernel_guard=kernel_guard,
            gate_keeper=gate_keeper,
            population_controller=pop_ctrl,
            genome_inheritance=MagicMock(),
            agent_registry=agent_registry,
            dynamic_roster=roster,
        )

        outcome = await proto.run(make_proposal_data())
        assert outcome.success is False
        assert "BLOCKED" in (outcome.error or "")

        # Check proposal marked as failed
        proposals = proto.load_proposals()
        assert len(proposals) == 1
        assert proposals[0].status == "failed"

    @pytest.mark.asyncio
    async def test_pipeline_population_cap_no_cull(self, tmp_path: Path) -> None:
        config = MagicMock()
        config.max_generations = 2

        roster = DynamicRoster(state_dir=tmp_path)

        pop_ctrl = MagicMock(spec=PopulationController)
        pop_ctrl.can_add_agent.return_value = PopulationAssessment(
            can_add=False,
            current_population=8,
            max_population=8,
            reason="At cap, all agents healthy",
        )

        agent_registry = MagicMock()
        agent_registry.is_budget_exceeded.return_value = False

        proto = ReplicationProtocol(
            state_dir=tmp_path,
            config=config,
            kernel_guard=make_kernel_guard_mock(),
            gate_keeper=MagicMock(),
            population_controller=pop_ctrl,
            genome_inheritance=MagicMock(),
            agent_registry=agent_registry,
            dynamic_roster=roster,
        )

        outcome = await proto.run(make_proposal_data())
        assert outcome.success is False
        assert "blocked" in (outcome.error or "").lower()


# ---------------------------------------------------------------------------
# Witness trail
# ---------------------------------------------------------------------------


class TestWitnessTrail:
    @pytest.mark.asyncio
    async def test_witness_written_on_success(self, tmp_path: Path) -> None:
        child_spec = make_child_spec()
        child_name = child_spec.name
        genome = make_genome_template(child_name)

        config = MagicMock()
        config.max_generations = 2

        roster = DynamicRoster(state_dir=tmp_path)

        gate_keeper = MagicMock()
        gate_keeper.check.return_value = make_gate_allow()

        pop_ctrl = MagicMock(spec=PopulationController)
        pop_ctrl.can_add_agent.return_value = PopulationAssessment(
            can_add=True, current_population=6, max_population=8, reason="OK",
        )
        pop_ctrl.start_probation.return_value = MagicMock()

        genome_inh = MagicMock()
        genome_inh.compose_child_spec = AsyncMock(return_value=(child_spec, genome))

        agent_registry = MagicMock()
        agent_registry.is_budget_exceeded.return_value = False
        agent_registry.register_agent.return_value = {}

        proto = ReplicationProtocol(
            state_dir=tmp_path,
            config=config,
            kernel_guard=make_kernel_guard_mock(),
            gate_keeper=gate_keeper,
            population_controller=pop_ctrl,
            genome_inheritance=genome_inh,
            agent_registry=agent_registry,
            dynamic_roster=roster,
        )

        await proto.run(make_proposal_data())

        witness_file = tmp_path / "witness" / "replication.jsonl"
        assert witness_file.exists()
        lines = [
            json.loads(line)
            for line in witness_file.read_text().splitlines()
            if line.strip()
        ]
        # Expect at least G1_PASS, S_PASS, G2_PASS, M_MATERIALIZED
        event_types = [entry["type"] for entry in lines]
        assert "G1_PASS" in event_types
        assert "S_PASS" in event_types
        assert "G2_PASS" in event_types
        assert "M_MATERIALIZED" in event_types

    @pytest.mark.asyncio
    async def test_witness_written_on_failure(self, tmp_path: Path) -> None:
        proto = ReplicationProtocol(state_dir=tmp_path)
        # Will fail at validation (missing parent_agent field value)
        outcome = await proto.run({"proposed_role": "test", "capability_gap": "test"})
        assert outcome.success is False

        witness_file = tmp_path / "witness" / "replication.jsonl"
        assert witness_file.exists()
        lines = [
            json.loads(line)
            for line in witness_file.read_text().splitlines()
            if line.strip()
        ]
        event_types = [entry["type"] for entry in lines]
        assert "REPLICATION_FAILED" in event_types


# ---------------------------------------------------------------------------
# Severity threshold
# ---------------------------------------------------------------------------


class TestSeverityThreshold:
    @pytest.mark.asyncio
    async def test_low_severity_rejected(self, tmp_path: Path) -> None:
        config = MagicMock()
        config.max_generations = 5

        roster = DynamicRoster(state_dir=tmp_path)

        pop_ctrl = MagicMock(spec=PopulationController)
        pop_ctrl.can_add_agent.return_value = PopulationAssessment(
            can_add=True, current_population=6, max_population=8, reason="OK",
        )

        agent_registry = MagicMock()
        agent_registry.is_budget_exceeded.return_value = False

        proto = ReplicationProtocol(
            state_dir=tmp_path,
            config=config,
            kernel_guard=make_kernel_guard_mock(),
            gate_keeper=MagicMock(),
            population_controller=pop_ctrl,
            genome_inheritance=MagicMock(),
            agent_registry=agent_registry,
            dynamic_roster=roster,
        )

        outcome = await proto.run(make_proposal_data(severity=0.1))
        assert outcome.success is False
        assert "severity" in (outcome.error or "").lower()
