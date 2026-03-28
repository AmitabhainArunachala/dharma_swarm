"""Tests for DynamicRoster -- runtime-added agents overlay on constitutional roster."""

from __future__ import annotations

import pytest
from pathlib import Path

from dharma_swarm.agent_constitution import (
    AgentSpec,
    CONSTITUTIONAL_ROSTER,
    ConstitutionalLayer,
    DynamicRoster,
    MAX_STABLE_AGENTS,
)
from dharma_swarm.models import AgentRole, ProviderType


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def make_spec(name: str, **overrides: object) -> AgentSpec:
    """Create a minimal AgentSpec for testing."""
    defaults: dict[str, object] = dict(
        name=name,
        role=AgentRole.WORKER,
        layer=ConstitutionalLayer.DIRECTOR,
        vsm_function="test function",
        domain="test domain",
        system_prompt="You are a test agent.",
        default_provider=ProviderType.OPENROUTER,
        default_model="test-model",
        backup_models=[],
        constitutional_gates=["SATYA"],
        max_concurrent_workers=3,
        memory_namespace=name,
        spawn_authority=[],
        audit_cycle_seconds=0.0,
    )
    defaults.update(overrides)
    return AgentSpec(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDynamicRoster:
    def test_roster_loads_static_agents(self, tmp_path: Path) -> None:
        roster = DynamicRoster(state_dir=tmp_path)
        all_agents = roster.get_all()
        assert len(all_agents) == len(CONSTITUTIONAL_ROSTER)
        static_names = {s.name for s in CONSTITUTIONAL_ROSTER}
        loaded_names = {s.name for s in all_agents}
        assert loaded_names == static_names

    def test_roster_add_dynamic_agent(self, tmp_path: Path) -> None:
        roster = DynamicRoster(state_dir=tmp_path)
        initial = roster.population
        roster.add(make_spec("test_agent_alpha"))
        assert roster.population == initial + 1
        # Verify persisted to disk
        assert (tmp_path / "replication" / "dynamic_roster.json").exists()

    def test_roster_remove_dynamic_agent(self, tmp_path: Path) -> None:
        roster = DynamicRoster(state_dir=tmp_path)
        roster.add(make_spec("ephemeral"))
        pop_after_add = roster.population
        removed = roster.remove("ephemeral")
        assert removed.name == "ephemeral"
        assert roster.population == pop_after_add - 1

    def test_roster_cannot_remove_static(self, tmp_path: Path) -> None:
        roster = DynamicRoster(state_dir=tmp_path)
        with pytest.raises(ValueError, match="Cannot remove static agent"):
            roster.remove("operator")

    def test_roster_cannot_shadow_static(self, tmp_path: Path) -> None:
        roster = DynamicRoster(state_dir=tmp_path)
        with pytest.raises(ValueError, match="Cannot shadow static agent"):
            roster.add(make_spec("operator"))

    def test_roster_population_cap(self, tmp_path: Path) -> None:
        roster = DynamicRoster(state_dir=tmp_path)
        # Fill up to MAX_STABLE_AGENTS
        slots = MAX_STABLE_AGENTS - roster.population
        for i in range(slots):
            roster.add(make_spec(f"filler_{i}"))
        assert roster.population == MAX_STABLE_AGENTS
        with pytest.raises(ValueError, match="Population at cap"):
            roster.add(make_spec("one_too_many"))

    def test_roster_persistence_roundtrip(self, tmp_path: Path) -> None:
        roster1 = DynamicRoster(state_dir=tmp_path)
        roster1.add(make_spec("persistent_agent"))
        # Create a brand-new roster from the same directory
        roster2 = DynamicRoster(state_dir=tmp_path)
        spec = roster2.get("persistent_agent")
        assert spec is not None
        assert spec.name == "persistent_agent"
        assert spec.domain == "test domain"

    def test_roster_is_static_is_dynamic(self, tmp_path: Path) -> None:
        roster = DynamicRoster(state_dir=tmp_path)
        roster.add(make_spec("dynamic_one"))
        assert roster.is_static("operator") is True
        assert roster.is_dynamic("operator") is False
        assert roster.is_dynamic("dynamic_one") is True
        assert roster.is_static("dynamic_one") is False

    def test_roster_get_by_name(self, tmp_path: Path) -> None:
        roster = DynamicRoster(state_dir=tmp_path)
        roster.add(make_spec("findme"))
        # Static lookup
        assert roster.get("operator") is not None
        assert roster.get("operator").name == "operator"  # type: ignore[union-attr]
        # Dynamic lookup
        assert roster.get("findme") is not None
        assert roster.get("findme").name == "findme"  # type: ignore[union-attr]
        # Missing
        assert roster.get("ghost") is None

    def test_roster_dynamic_count(self, tmp_path: Path) -> None:
        roster = DynamicRoster(state_dir=tmp_path)
        assert roster.dynamic_count == 0
        roster.add(make_spec("d1"))
        roster.add(make_spec("d2"))
        assert roster.dynamic_count == 2

    def test_roster_add_duplicate_dynamic(self, tmp_path: Path) -> None:
        roster = DynamicRoster(state_dir=tmp_path)
        roster.add(make_spec("dup"))
        with pytest.raises(ValueError, match="already exists"):
            roster.add(make_spec("dup"))
