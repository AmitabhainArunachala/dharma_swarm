"""Tests for ontology_agents.py — runtime agent projection into ontology."""

from __future__ import annotations

from types import SimpleNamespace

from dharma_swarm.models import AgentRole
from dharma_swarm.ontology import OntologyRegistry
from dharma_swarm.ontology_agents import (
    agent_display_name,
    agent_slug,
    build_agent_identity_properties,
    canonical_model_key,
    find_agent_identity,
    mark_agent_retiring,
    model_label,
    upsert_agent_identity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry() -> OntologyRegistry:
    """Create a fresh OntologyRegistry with all dharma types (incl. AgentIdentity)."""
    return OntologyRegistry.create_dharma_registry()


def _mock_agent(**kw):
    defaults = dict(
        id="agent-123",
        name="systems_architect",
        role=SimpleNamespace(value="architect"),
        status=SimpleNamespace(value="busy"),
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        current_task="test task",
        started_at="2026-03-22T00:00:00Z",
        last_heartbeat=None,
        tasks_completed=5,
        fitness_average=0.85,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# String helpers
# ---------------------------------------------------------------------------


class TestStringHelpers:
    def test_agent_slug_normal(self):
        assert agent_slug("systems_architect") == "systems-architect"

    def test_agent_slug_spaces(self):
        assert agent_slug("Research Director") == "research-director"

    def test_agent_slug_empty(self):
        assert agent_slug("") == "agent"

    def test_agent_slug_none(self):
        assert agent_slug(None) == "agent"

    def test_agent_display_name_underscore(self):
        assert agent_display_name("systems_architect") == "Systems Architect"

    def test_agent_display_name_with_spaces(self):
        assert agent_display_name("Research Director") == "Research Director"

    def test_agent_display_name_empty(self):
        assert agent_display_name("") == "Agent"

    def test_model_label_with_provider(self):
        assert model_label("anthropic/claude-sonnet-4") == "claude-sonnet-4"

    def test_model_label_without_provider(self):
        assert model_label("claude-sonnet-4") == "claude-sonnet-4"

    def test_model_label_empty(self):
        assert model_label("") == ""

    def test_canonical_model_key(self):
        assert canonical_model_key("anthropic", "claude-sonnet-4") == "anthropic::claude-sonnet-4"

    def test_canonical_model_key_no_provider(self):
        assert canonical_model_key("", "claude-sonnet-4") == "claude-sonnet-4"

    def test_canonical_model_key_no_model(self):
        assert canonical_model_key("anthropic", "") == "anthropic"


# ---------------------------------------------------------------------------
# build_agent_identity_properties
# ---------------------------------------------------------------------------


class TestBuildProperties:
    def test_from_mock_agent(self):
        agent = _mock_agent()
        props = build_agent_identity_properties(agent)
        assert props["name"] == "systems_architect"
        assert props["agent_id"] == "agent-123"
        assert props["agent_slug"] == "systems-architect"
        assert props["display_name"] == "Systems Architect"
        assert props["role"] == "architect"
        assert props["status"] == "busy"
        assert props["provider"] == "anthropic"
        assert props["model"] == "claude-sonnet-4-20250514"
        assert props["last_active"] == ""
        assert props["tasks_completed"] == 5
        assert props["fitness_average"] == 0.85

    def test_from_minimal_agent(self):
        agent = SimpleNamespace()
        props = build_agent_identity_properties(agent)
        assert props["name"] == "agent"
        assert props["role"] == "general"
        assert props["status"] == "unknown"


# ---------------------------------------------------------------------------
# find_agent_identity
# ---------------------------------------------------------------------------


class TestFindAgentIdentity:
    def test_find_by_agent_id(self):
        reg = _make_registry()
        agent = _mock_agent()
        upsert_agent_identity(agent, registry=reg, persist=False)

        found = find_agent_identity(reg, agent_id="agent-123")
        assert found is not None
        assert found.properties["agent_id"] == "agent-123"

    def test_find_by_name(self):
        reg = _make_registry()
        agent = _mock_agent(name="witness")
        upsert_agent_identity(agent, registry=reg, persist=False)

        found = find_agent_identity(reg, name="witness")
        assert found is not None
        assert found.properties["name"] == "witness"

    def test_find_not_found(self):
        reg = _make_registry()
        assert find_agent_identity(reg, agent_id="ghost") is None


# ---------------------------------------------------------------------------
# upsert_agent_identity
# ---------------------------------------------------------------------------


class TestUpsertAgentIdentity:
    def test_create_new(self):
        reg = _make_registry()
        agent = _mock_agent()
        obj = upsert_agent_identity(agent, registry=reg, persist=False)
        assert obj is not None
        assert obj.properties["name"] == "systems_architect"

    def test_update_existing(self):
        reg = _make_registry()
        agent = _mock_agent(tasks_completed=1)
        upsert_agent_identity(agent, registry=reg, persist=False)

        # Update with more tasks
        agent2 = _mock_agent(tasks_completed=10)
        obj = upsert_agent_identity(agent2, registry=reg, persist=False)
        assert obj is not None
        assert obj.properties["tasks_completed"] == 10

    def test_idempotent(self):
        reg = _make_registry()
        agent = _mock_agent()
        upsert_agent_identity(agent, registry=reg, persist=False)
        upsert_agent_identity(agent, registry=reg, persist=False)

        # Should still be one identity
        identities = reg.get_objects_by_type("AgentIdentity")
        assert len(identities) == 1


# ---------------------------------------------------------------------------
# mark_agent_retiring
# ---------------------------------------------------------------------------


class TestMarkAgentRetiring:
    def test_retire_existing(self):
        reg = _make_registry()
        agent = _mock_agent()
        upsert_agent_identity(agent, registry=reg, persist=False)

        obj = mark_agent_retiring("agent-123", registry=reg, persist=False)
        assert obj is not None
        assert obj.properties["status"] == "stopping"

    def test_retire_by_name(self):
        reg = _make_registry()
        agent = _mock_agent()
        upsert_agent_identity(agent, registry=reg, persist=False)

        obj = mark_agent_retiring("", name="systems_architect", registry=reg, persist=False)
        assert obj is not None
        assert obj.properties["status"] == "stopping"

    def test_retire_nonexistent(self):
        reg = _make_registry()
        assert mark_agent_retiring("ghost", registry=reg, persist=False) is None


# ---------------------------------------------------------------------------
# Enum sync guard — ontology must accept all AgentRole values
# ---------------------------------------------------------------------------


class TestOntologyEnumSync:
    def test_all_agent_roles_in_ontology_enum(self):
        """Every AgentRole value must be accepted by the AgentIdentity ontology type.

        Regression guard: the ontology's role enum diverged from models.py once
        already — constitutional roles (operator, archivist, etc.) were missing,
        causing upsert_agent_identity() to silently fail in production.
        """
        reg = _make_registry()
        agent_type = reg.get_type("AgentIdentity")
        assert agent_type is not None
        role_prop = agent_type.properties["role"]
        ontology_roles = set(role_prop.enum_values)
        model_roles = {r.value for r in AgentRole}
        missing = model_roles - ontology_roles
        assert missing == set(), (
            f"AgentRole values missing from ontology AgentIdentity.role enum: {missing}"
        )

    def test_constitutional_roles_upsert_succeeds(self):
        """Each constitutional agent role can be upserted into the ontology."""
        constitutional_roles = [
            "operator", "archivist", "research_director",
            "systems_architect", "strategist", "witness",
        ]
        for role in constitutional_roles:
            reg = _make_registry()
            agent = _mock_agent(
                id=f"agent-{role}",
                name=role,
                role=SimpleNamespace(value=role),
            )
            obj = upsert_agent_identity(agent, registry=reg, persist=False)
            assert obj is not None, f"upsert failed for constitutional role '{role}'"
            assert obj.properties["role"] == role
