"""Tests for agent_constitution.py — canonical 6-agent stable roster."""

from __future__ import annotations

import pytest

from dharma_swarm.agent_constitution import (
    AgentSpec,
    CONSTITUTIONAL_ROSTER,
    ConstitutionalLayer,
    MAX_STABLE_AGENTS,
    can_spawn_worker,
    get_agent_by_role,
    get_agent_spec,
    get_agents_by_layer,
    get_expected_roster_size,
    get_max_workers,
    get_stable_agent_names,
)
from dharma_swarm.models import AgentRole, ProviderType


# ---------------------------------------------------------------------------
# Roster integrity
# ---------------------------------------------------------------------------


class TestRosterIntegrity:
    def test_roster_has_six_agents(self):
        assert len(CONSTITUTIONAL_ROSTER) == 6

    def test_all_names_unique(self):
        names = [spec.name for spec in CONSTITUTIONAL_ROSTER]
        assert len(names) == len(set(names))

    def test_all_roles_unique(self):
        roles = [spec.role for spec in CONSTITUTIONAL_ROSTER]
        assert len(roles) == len(set(roles))

    def test_known_agent_names(self):
        names = set(get_stable_agent_names())
        expected = {"operator", "archivist", "research_director", "systems_architect", "strategist", "witness"}
        assert names == expected

    def test_all_agents_are_frozen_dataclasses(self):
        for spec in CONSTITUTIONAL_ROSTER:
            assert isinstance(spec, AgentSpec)
            with pytest.raises(AttributeError):
                spec.name = "hacked"  # type: ignore[misc]

    def test_max_stable_agents_ceiling(self):
        assert MAX_STABLE_AGENTS == 8
        assert len(CONSTITUTIONAL_ROSTER) <= MAX_STABLE_AGENTS


# ---------------------------------------------------------------------------
# AgentSpec field validation
# ---------------------------------------------------------------------------


class TestAgentSpecFields:
    @pytest.mark.parametrize("spec", CONSTITUTIONAL_ROSTER, ids=lambda s: s.name)
    def test_non_empty_fields(self, spec: AgentSpec):
        assert spec.name
        assert spec.domain
        assert spec.system_prompt
        assert spec.vsm_function
        assert spec.default_model
        assert spec.memory_namespace

    @pytest.mark.parametrize("spec", CONSTITUTIONAL_ROSTER, ids=lambda s: s.name)
    def test_valid_provider(self, spec: AgentSpec):
        assert isinstance(spec.default_provider, ProviderType)

    @pytest.mark.parametrize("spec", CONSTITUTIONAL_ROSTER, ids=lambda s: s.name)
    def test_valid_role(self, spec: AgentSpec):
        assert isinstance(spec.role, AgentRole)

    @pytest.mark.parametrize("spec", CONSTITUTIONAL_ROSTER, ids=lambda s: s.name)
    def test_valid_layer(self, spec: AgentSpec):
        assert isinstance(spec.layer, ConstitutionalLayer)

    @pytest.mark.parametrize("spec", CONSTITUTIONAL_ROSTER, ids=lambda s: s.name)
    def test_has_constitutional_gates(self, spec: AgentSpec):
        assert len(spec.constitutional_gates) >= 1

    @pytest.mark.parametrize("spec", CONSTITUTIONAL_ROSTER, ids=lambda s: s.name)
    def test_has_backup_models(self, spec: AgentSpec):
        assert len(spec.backup_models) >= 1


# ---------------------------------------------------------------------------
# Layer organization
# ---------------------------------------------------------------------------


class TestLayers:
    def test_cortex_has_two_agents(self):
        cortex = get_agents_by_layer(ConstitutionalLayer.CORTEX)
        assert len(cortex) == 2
        names = {s.name for s in cortex}
        assert names == {"operator", "archivist"}

    def test_director_has_three_agents(self):
        directors = get_agents_by_layer(ConstitutionalLayer.DIRECTOR)
        assert len(directors) == 3
        names = {s.name for s in directors}
        assert names == {"research_director", "systems_architect", "strategist"}

    def test_audit_has_one_agent(self):
        audit = get_agents_by_layer(ConstitutionalLayer.AUDIT)
        assert len(audit) == 1
        assert audit[0].name == "witness"


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


class TestLookups:
    def test_get_agent_spec_found(self):
        spec = get_agent_spec("operator")
        assert spec is not None
        assert spec.name == "operator"

    def test_get_agent_spec_not_found(self):
        assert get_agent_spec("nonexistent") is None

    def test_get_agent_by_role_found(self):
        spec = get_agent_by_role(AgentRole.WITNESS)
        assert spec is not None
        assert spec.name == "witness"

    def test_get_agent_by_role_not_found(self):
        assert get_agent_by_role(AgentRole.GENERAL) is None

    def test_get_expected_roster_size(self):
        assert get_expected_roster_size() == 6

    def test_get_stable_agent_names_returns_list(self):
        names = get_stable_agent_names()
        assert isinstance(names, list)
        assert len(names) == 6


# ---------------------------------------------------------------------------
# Spawn authority
# ---------------------------------------------------------------------------


class TestSpawnAuthority:
    def test_operator_can_spawn_triage_worker(self):
        assert can_spawn_worker("operator", "triage_worker") is True

    def test_operator_cannot_spawn_experiment_runner(self):
        assert can_spawn_worker("operator", "experiment_runner") is False

    def test_witness_cannot_spawn_anything(self):
        spec = get_agent_spec("witness")
        assert spec is not None
        assert spec.spawn_authority == []
        assert can_spawn_worker("witness", "anything") is False

    def test_unknown_agent_cannot_spawn(self):
        assert can_spawn_worker("ghost", "worker") is False

    def test_max_workers_operator(self):
        assert get_max_workers("operator") == 5

    def test_max_workers_witness(self):
        assert get_max_workers("witness") == 0

    def test_max_workers_unknown(self):
        assert get_max_workers("ghost") == 0

    def test_research_director_spawn_authority(self):
        spec = get_agent_spec("research_director")
        assert spec is not None
        assert "experiment_runner" in spec.spawn_authority
        assert "literature_digger" in spec.spawn_authority


# ---------------------------------------------------------------------------
# Witness-specific
# ---------------------------------------------------------------------------


class TestWitnessAgent:
    def test_witness_has_audit_cycle(self):
        spec = get_agent_spec("witness")
        assert spec is not None
        assert spec.audit_cycle_seconds == 3600.0

    def test_non_audit_agents_have_zero_audit_cycle(self):
        for spec in CONSTITUTIONAL_ROSTER:
            if spec.layer != ConstitutionalLayer.AUDIT:
                assert spec.audit_cycle_seconds == 0.0, f"{spec.name} should have 0 audit cycle"


# ---------------------------------------------------------------------------
# ConstitutionalLayer enum
# ---------------------------------------------------------------------------


class TestConstitutionalLayerEnum:
    def test_values(self):
        assert ConstitutionalLayer.CORTEX.value == "cortex"
        assert ConstitutionalLayer.DIRECTOR.value == "director"
        assert ConstitutionalLayer.AUDIT.value == "audit"

    def test_layer_count(self):
        assert len(ConstitutionalLayer) == 3
