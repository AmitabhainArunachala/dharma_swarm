"""Tests for the Economic Spine — budget CRUD, mission state machine,
token operations, reallocation algorithm, audit trail, and edge cases.
"""

from __future__ import annotations

import pytest

from dharma_swarm.economic_spine import (
    AgentBudget,
    EconomicSpine,
    InsufficientBudgetError,
    INITIAL_AGENT_BUDGET,
    MissionRecord,
    MissionState,
    MISSION_TRANSITIONS,
)


# ---------------------------------------------------------------------------
# AgentBudget dataclass
# ---------------------------------------------------------------------------


class TestAgentBudget:
    def test_default_values(self):
        b = AgentBudget(agent_id="a1")
        assert b.agent_id == "a1"
        assert b.total_tokens_allocated == INITIAL_AGENT_BUDGET
        assert b.tokens_spent == 0
        assert b.tokens_earned == 0
        assert b.efficiency_score == 0.5
        assert b.mission_count == 0
        assert b.success_count == 0

    def test_tokens_remaining(self):
        b = AgentBudget(
            agent_id="a1",
            total_tokens_allocated=10000,
            tokens_spent=3000,
            tokens_earned=1000,
        )
        assert b.tokens_remaining == 8000  # 10000 + 1000 - 3000

    def test_tokens_remaining_zero_budget(self):
        b = AgentBudget(agent_id="a1", total_tokens_allocated=0)
        assert b.tokens_remaining == 0

    def test_success_rate_no_missions(self):
        b = AgentBudget(agent_id="a1")
        assert b.success_rate == 0.0

    def test_success_rate(self):
        b = AgentBudget(agent_id="a1", mission_count=10, success_count=7)
        assert b.success_rate == pytest.approx(0.7)

    def test_success_rate_all_successful(self):
        b = AgentBudget(agent_id="a1", mission_count=5, success_count=5)
        assert b.success_rate == 1.0

    def test_last_allocation_at_auto_set(self):
        b = AgentBudget(agent_id="a1")
        assert b.last_allocation_at  # non-empty string


# ---------------------------------------------------------------------------
# MissionRecord state machine
# ---------------------------------------------------------------------------


class TestMissionRecord:
    def test_default_creation(self):
        m = MissionRecord(agent_id="a1", task_description="test task")
        assert m.id  # non-empty UUID
        assert m.state == MissionState.RECEIVED
        assert m.state_history == []

    def test_valid_transition(self):
        m = MissionRecord(agent_id="a1")
        m.transition_to(MissionState.QUOTED, reason="quoted")
        assert m.state == MissionState.QUOTED
        assert len(m.state_history) == 1
        assert m.state_history[0]["from"] == "received"
        assert m.state_history[0]["to"] == "quoted"

    def test_full_happy_path(self):
        m = MissionRecord(agent_id="a1")
        transitions = [
            MissionState.QUOTED,
            MissionState.ACCEPTED,
            MissionState.EXECUTING,
            MissionState.DELIVERED,
            MissionState.VERIFIED,
            MissionState.PAID,
        ]
        for state in transitions:
            m.transition_to(state)
        assert m.state == MissionState.PAID
        assert len(m.state_history) == 6

    def test_invalid_transition_raises(self):
        m = MissionRecord(agent_id="a1")
        with pytest.raises(ValueError, match="Invalid transition"):
            m.transition_to(MissionState.PAID)

    def test_cancelled_from_received(self):
        m = MissionRecord(agent_id="a1")
        m.transition_to(MissionState.CANCELLED)
        assert m.state == MissionState.CANCELLED

    def test_cancelled_from_quoted(self):
        m = MissionRecord(agent_id="a1")
        m.transition_to(MissionState.QUOTED)
        m.transition_to(MissionState.CANCELLED)
        assert m.state == MissionState.CANCELLED

    def test_failed_can_retry(self):
        m = MissionRecord(agent_id="a1")
        m.transition_to(MissionState.QUOTED)
        m.transition_to(MissionState.ACCEPTED)
        m.transition_to(MissionState.EXECUTING)
        m.transition_to(MissionState.FAILED)
        # Can retry from FAILED → RECEIVED
        m.transition_to(MissionState.RECEIVED)
        assert m.state == MissionState.RECEIVED

    def test_paid_is_terminal(self):
        m = MissionRecord(agent_id="a1")
        m.transition_to(MissionState.QUOTED)
        m.transition_to(MissionState.ACCEPTED)
        m.transition_to(MissionState.EXECUTING)
        m.transition_to(MissionState.DELIVERED)
        m.transition_to(MissionState.VERIFIED)
        m.transition_to(MissionState.PAID)
        with pytest.raises(ValueError):
            m.transition_to(MissionState.RECEIVED)

    def test_cancelled_is_terminal(self):
        m = MissionRecord(agent_id="a1")
        m.transition_to(MissionState.CANCELLED)
        with pytest.raises(ValueError):
            m.transition_to(MissionState.RECEIVED)

    def test_transition_audit_trail_has_timestamp(self):
        m = MissionRecord(agent_id="a1")
        m.transition_to(MissionState.QUOTED, reason="initial quote")
        entry = m.state_history[0]
        assert "timestamp" in entry
        assert entry["reason"] == "initial quote"


# ---------------------------------------------------------------------------
# Mission transitions coverage
# ---------------------------------------------------------------------------


class TestMissionTransitions:
    def test_all_states_have_transition_entry(self):
        for state in MissionState:
            assert state in MISSION_TRANSITIONS

    def test_terminal_states_have_empty_transitions(self):
        assert MISSION_TRANSITIONS[MissionState.PAID] == set()
        assert MISSION_TRANSITIONS[MissionState.CANCELLED] == set()


# ---------------------------------------------------------------------------
# EconomicSpine — CRUD
# ---------------------------------------------------------------------------


class TestEconomicSpineBudgets:
    def test_create_budget(self):
        spine = EconomicSpine()
        budget = spine.get_or_create_budget("agent-1")
        assert budget.agent_id == "agent-1"
        assert budget.total_tokens_allocated == INITIAL_AGENT_BUDGET
        assert budget.tokens_remaining == INITIAL_AGENT_BUDGET

    def test_get_existing_budget(self):
        spine = EconomicSpine()
        spine.get_or_create_budget("agent-1")
        budget = spine.get_or_create_budget("agent-1")
        assert budget.agent_id == "agent-1"

    def test_multiple_agents(self):
        spine = EconomicSpine()
        b1 = spine.get_or_create_budget("a1")
        b2 = spine.get_or_create_budget("a2")
        assert b1.agent_id == "a1"
        assert b2.agent_id == "a2"


# ---------------------------------------------------------------------------
# EconomicSpine — Token operations
# ---------------------------------------------------------------------------


class TestEconomicSpineTokens:
    def test_spend_tokens_success(self):
        spine = EconomicSpine()
        spine.get_or_create_budget("a1")
        assert spine.spend_tokens("a1", 5000) is True
        budget = spine.get_or_create_budget("a1")
        assert budget.tokens_spent == 5000

    def test_spend_tokens_over_budget_still_succeeds(self):
        """spend_tokens always returns True — tracking only, no enforcement."""
        spine = EconomicSpine()
        spine.get_or_create_budget("a1")
        # Spending more than available still succeeds (tracking only)
        assert spine.spend_tokens("a1", INITIAL_AGENT_BUDGET + 1) is True
        budget = spine.get_or_create_budget("a1")
        assert budget.tokens_remaining < 0

    def test_spend_tokens_exact_budget(self):
        spine = EconomicSpine()
        spine.get_or_create_budget("a1")
        assert spine.spend_tokens("a1", INITIAL_AGENT_BUDGET) is True
        budget = spine.get_or_create_budget("a1")
        assert budget.tokens_remaining == 0

    def test_earn_tokens(self):
        spine = EconomicSpine()
        spine.get_or_create_budget("a1")
        spine.earn_tokens("a1", 2000)
        budget = spine.get_or_create_budget("a1")
        assert budget.tokens_earned == 2000
        assert budget.tokens_remaining == INITIAL_AGENT_BUDGET + 2000

    def test_spend_then_earn(self):
        spine = EconomicSpine()
        spine.get_or_create_budget("a1")
        spine.spend_tokens("a1", 3000)
        spine.earn_tokens("a1", 1000)
        budget = spine.get_or_create_budget("a1")
        assert budget.tokens_remaining == INITIAL_AGENT_BUDGET - 3000 + 1000

    def test_multiple_spends(self):
        spine = EconomicSpine()
        spine.get_or_create_budget("a1")
        spine.spend_tokens("a1", 1000)
        spine.spend_tokens("a1", 2000)
        budget = spine.get_or_create_budget("a1")
        assert budget.tokens_spent == 3000


# ---------------------------------------------------------------------------
# EconomicSpine — Mission lifecycle
# ---------------------------------------------------------------------------


class TestEconomicSpineMissions:
    def test_create_mission(self):
        spine = EconomicSpine()
        mission = spine.create_mission("a1", "do something", 5000)
        assert mission.agent_id == "a1"
        assert mission.tokens_quoted == 5000
        assert mission.state == MissionState.RECEIVED

    def test_transition_mission(self):
        spine = EconomicSpine()
        m = spine.create_mission("a1", "task", 1000)
        m2 = spine.transition_mission(m.id, MissionState.QUOTED)
        assert m2.state == MissionState.QUOTED

    def test_full_mission_lifecycle(self):
        spine = EconomicSpine()
        m = spine.create_mission("a1", "full lifecycle", 5000)
        spine.transition_mission(m.id, MissionState.QUOTED)
        spine.transition_mission(m.id, MissionState.ACCEPTED)
        spine.transition_mission(m.id, MissionState.EXECUTING)
        spine.transition_mission(
            m.id, MissionState.DELIVERED, tokens_actual=4500
        )
        spine.transition_mission(
            m.id, MissionState.VERIFIED, quality_score=0.9
        )
        spine.transition_mission(m.id, MissionState.PAID)

        final = spine.get_mission(m.id)
        assert final is not None
        assert final.state == MissionState.PAID
        assert final.tokens_actual == 4500
        assert final.quality_score == 0.9
        assert len(final.state_history) == 6

    def test_mission_not_found(self):
        spine = EconomicSpine()
        with pytest.raises(ValueError, match="Mission not found"):
            spine.transition_mission("nonexistent", MissionState.QUOTED)

    def test_invalid_mission_transition(self):
        spine = EconomicSpine()
        m = spine.create_mission("a1", "task", 1000)
        with pytest.raises(ValueError, match="Invalid transition"):
            spine.transition_mission(m.id, MissionState.PAID)

    def test_get_mission(self):
        spine = EconomicSpine()
        m = spine.create_mission("a1", "retrieve me", 2000)
        retrieved = spine.get_mission(m.id)
        assert retrieved is not None
        assert retrieved.task_description == "retrieve me"

    def test_get_nonexistent_mission(self):
        spine = EconomicSpine()
        assert spine.get_mission("does-not-exist") is None

    def test_mission_failure_increments_count(self):
        spine = EconomicSpine()
        spine.get_or_create_budget("a1")
        m = spine.create_mission("a1", "fail task", 1000)
        spine.transition_mission(m.id, MissionState.QUOTED)
        spine.transition_mission(m.id, MissionState.ACCEPTED)
        spine.transition_mission(m.id, MissionState.EXECUTING)
        spine.transition_mission(m.id, MissionState.FAILED)
        budget = spine.get_or_create_budget("a1")
        assert budget.mission_count == 1
        assert budget.success_count == 0

    def test_mission_success_increments_count(self):
        spine = EconomicSpine()
        spine.get_or_create_budget("a1")
        m = spine.create_mission("a1", "success task", 1000)
        spine.transition_mission(m.id, MissionState.QUOTED)
        spine.transition_mission(m.id, MissionState.ACCEPTED)
        spine.transition_mission(m.id, MissionState.EXECUTING)
        spine.transition_mission(m.id, MissionState.DELIVERED)
        spine.transition_mission(m.id, MissionState.VERIFIED)
        spine.transition_mission(m.id, MissionState.PAID)
        budget = spine.get_or_create_budget("a1")
        assert budget.mission_count == 1
        assert budget.success_count == 1

    def test_get_agent_missions(self):
        spine = EconomicSpine()
        spine.create_mission("a1", "task 1", 1000)
        spine.create_mission("a1", "task 2", 2000)
        spine.create_mission("a2", "other agent", 3000)
        missions = spine.get_agent_missions("a1")
        assert len(missions) == 2


# ---------------------------------------------------------------------------
# EconomicSpine — Reallocation algorithm
# ---------------------------------------------------------------------------


class TestEconomicSpineReallocation:
    def test_equal_efficiency_equal_allocation(self):
        spine = EconomicSpine()
        for aid in ("a1", "a2", "a3"):
            b = spine.get_or_create_budget(aid)
            # All same efficiency
        allocs = spine.reallocate_budgets(30000)
        assert len(allocs) == 3
        assert sum(allocs.values()) <= 30000

    def test_higher_efficiency_gets_more(self):
        spine = EconomicSpine()
        b1 = spine.get_or_create_budget("a1")
        b2 = spine.get_or_create_budget("a2")

        # Manually set efficiencies
        b1.efficiency_score = 0.9
        spine._save_budget(b1)
        b2.efficiency_score = 0.1
        spine._save_budget(b2)

        allocs = spine.reallocate_budgets(20000)
        assert allocs["a1"] > allocs["a2"]

    def test_floor_allocation(self):
        spine = EconomicSpine()
        b1 = spine.get_or_create_budget("a1")
        b2 = spine.get_or_create_budget("a2")

        b1.efficiency_score = 1.0
        spine._save_budget(b1)
        b2.efficiency_score = 0.0
        spine._save_budget(b2)

        allocs = spine.reallocate_budgets(20000)
        # Even with 0.0 efficiency, agent should get floor allocation
        assert allocs["a2"] > 0

    def test_empty_swarm_reallocation(self):
        spine = EconomicSpine()
        allocs = spine.reallocate_budgets(10000)
        assert allocs == {}

    def test_single_agent_gets_all(self):
        spine = EconomicSpine()
        spine.get_or_create_budget("solo")
        allocs = spine.reallocate_budgets(50000)
        assert allocs["solo"] == 50000


# ---------------------------------------------------------------------------
# EconomicSpine — Reporting
# ---------------------------------------------------------------------------


class TestEconomicSpineReporting:
    def test_agent_stats(self):
        spine = EconomicSpine()
        spine.get_or_create_budget("a1")
        spine.spend_tokens("a1", 2000)
        stats = spine.get_agent_stats("a1")
        assert stats["agent_id"] == "a1"
        assert stats["tokens_spent"] == 2000
        assert "tokens_remaining" in stats
        assert "efficiency_score" in stats

    def test_swarm_economics_empty(self):
        spine = EconomicSpine()
        econ = spine.get_swarm_economics()
        assert econ["total_agents"] == 0

    def test_swarm_economics(self):
        spine = EconomicSpine()
        spine.get_or_create_budget("a1")
        spine.get_or_create_budget("a2")
        spine.spend_tokens("a1", 1000)
        spine.earn_tokens("a2", 500)
        econ = spine.get_swarm_economics()
        assert econ["total_agents"] == 2
        assert econ["total_spent"] == 1000
        assert econ["total_earned"] == 500

    def test_mission_audit_trail(self):
        spine = EconomicSpine()
        m = spine.create_mission("a1", "audited task", 1000)
        spine.transition_mission(m.id, MissionState.QUOTED, reason="q1")
        spine.transition_mission(m.id, MissionState.ACCEPTED, reason="a1")
        trail = spine.get_mission_audit_trail(m.id)
        assert len(trail) == 2
        assert trail[0]["from"] == "received"
        assert trail[0]["to"] == "quoted"

    def test_mission_audit_trail_not_found(self):
        spine = EconomicSpine()
        trail = spine.get_mission_audit_trail("nonexistent")
        assert trail == []


# ---------------------------------------------------------------------------
# EconomicSpine — Edge cases
# ---------------------------------------------------------------------------


class TestEconomicSpineEdgeCases:
    def test_zero_budget_agent_still_spends(self):
        """Zero-budget agent can still spend — tracking only, no enforcement."""
        spine = EconomicSpine()
        b = spine.get_or_create_budget("a1")
        b.total_tokens_allocated = 0
        spine._save_budget(b)
        assert spine.spend_tokens("a1", 1) is True
        updated = spine.get_or_create_budget("a1")
        assert updated.tokens_remaining < 0

    def test_concurrent_missions(self):
        spine = EconomicSpine()
        m1 = spine.create_mission("a1", "task1", 1000)
        m2 = spine.create_mission("a1", "task2", 2000)
        assert m1.id != m2.id
        # Both should be retrievable
        assert spine.get_mission(m1.id) is not None
        assert spine.get_mission(m2.id) is not None

    def test_efficiency_update(self):
        spine = EconomicSpine()
        spine.get_or_create_budget("a1")
        spine.spend_tokens("a1", 1000)
        spine.earn_tokens("a1", 500)
        spine.update_efficiency("a1", 0.9)
        b = spine.get_or_create_budget("a1")
        assert 0.0 <= b.efficiency_score <= 1.0

    def test_close(self):
        spine = EconomicSpine()
        spine.get_or_create_budget("a1")
        spine.close()
        # After close, operations should raise
        with pytest.raises(Exception):
            spine.get_or_create_budget("a1")
