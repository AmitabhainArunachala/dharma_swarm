"""Tests for dharma_swarm.orchestrate -- orchestration plans and auto-selection."""

import json
from datetime import datetime, timezone

import pytest

from dharma_swarm.orchestrate import (
    AgentSpec,
    PLANS,
    SwarmPlan,
    auto_select_plan,
    plan_deployment,
    plan_full_build,
    plan_research_deep_dive,
    plan_small_maintenance,
    save_state,
)


# ---------------------------------------------------------------------------
# AgentSpec
# ---------------------------------------------------------------------------


def test_agent_spec_defaults():
    spec = AgentSpec(name="test", role="testing", prompt="do the thing")
    assert spec.priority == 5
    assert spec.timeout == 300
    assert spec.loops == 1


def test_agent_spec_custom():
    spec = AgentSpec(
        name="urgent",
        role="fixer",
        prompt="fix now",
        priority=1,
        timeout=600,
        loops=3,
    )
    assert spec.priority == 1
    assert spec.timeout == 600
    assert spec.loops == 3


# ---------------------------------------------------------------------------
# SwarmPlan
# ---------------------------------------------------------------------------


def test_swarm_plan_defaults():
    plan = SwarmPlan()
    assert plan.agents == []
    assert plan.reasoning == ""
    assert plan.timestamp == ""


def test_swarm_plan_with_agents():
    plan = SwarmPlan(
        agents=[
            AgentSpec(name="a1", role="r1", prompt="p1"),
            AgentSpec(name="a2", role="r2", prompt="p2"),
        ],
        reasoning="test plan",
        timestamp="2026-03-07T00:00:00Z",
    )
    assert len(plan.agents) == 2
    assert plan.reasoning == "test plan"


# ---------------------------------------------------------------------------
# Pre-defined plans
# ---------------------------------------------------------------------------


def test_plan_small_maintenance():
    plan = plan_small_maintenance()
    assert isinstance(plan, SwarmPlan)
    assert len(plan.agents) == 3
    names = {a.name for a in plan.agents}
    assert "health-checker" in names
    assert "memory-consolidator" in names
    assert "next-actions" in names
    assert plan.timestamp != ""


def test_plan_full_build():
    plan = plan_full_build()
    assert isinstance(plan, SwarmPlan)
    assert len(plan.agents) == 5
    names = {a.name for a in plan.agents}
    assert "synthesizer" in names
    assert "builder" in names
    assert "critic" in names
    assert "researcher" in names
    assert "validator" in names


def test_plan_research_deep_dive():
    plan = plan_research_deep_dive()
    assert isinstance(plan, SwarmPlan)
    assert len(plan.agents) == 4
    names = {a.name for a in plan.agents}
    assert "rv-researcher" in names
    assert "genome-researcher" in names
    assert "ecosystem-mapper" in names
    assert "connection-finder" in names


def test_plan_deployment():
    plan = plan_deployment()
    assert isinstance(plan, SwarmPlan)
    assert len(plan.agents) == 3
    names = {a.name for a in plan.agents}
    assert "agni-ops" in names
    assert "packager" in names
    assert "cron-wirer" in names


def test_all_plans_have_timestamps():
    for name, plan_fn in PLANS.items():
        plan = plan_fn()
        assert plan.timestamp != "", f"Plan '{name}' missing timestamp"


def test_all_plans_have_reasoning():
    for name, plan_fn in PLANS.items():
        plan = plan_fn()
        assert len(plan.reasoning) > 10, f"Plan '{name}' missing reasoning"


def test_all_plans_agents_have_prompts():
    for name, plan_fn in PLANS.items():
        plan = plan_fn()
        for agent in plan.agents:
            assert len(agent.prompt) > 20, (
                f"Plan '{name}', agent '{agent.name}' has empty/short prompt"
            )


def test_plans_dict_keys():
    assert "maintenance" in PLANS
    assert "build" in PLANS
    assert "research" in PLANS
    assert "deploy" in PLANS
    assert len(PLANS) == 4


# ---------------------------------------------------------------------------
# auto_select_plan
# ---------------------------------------------------------------------------


def test_auto_select_plan_failing_tests():
    state = {"tests": "3 failed, 100 passed"}
    plan = auto_select_plan(state)
    assert "maintenance" in plan.reasoning.lower() or "failing" in plan.reasoning.lower()
    # Should select maintenance plan (3 agents)
    assert len(plan.agents) <= 3


def test_auto_select_plan_many_running_agents():
    state = {"running_agents": 5, "tests": "100 passed"}
    plan = auto_select_plan(state)
    assert "already running" in plan.reasoning.lower()
    assert len(plan.agents) == 1  # only the consolidator


def test_auto_select_plan_stuck_work():
    state = {"running_agents": 0, "tests": "all passed", "stuck": "R_V paper is blocked on FDR correction"}
    plan = auto_select_plan(state)
    assert "stuck" in plan.reasoning.lower()
    assert len(plan.agents) == 5  # full build


def test_auto_select_plan_no_agent_notes():
    state = {"running_agents": 0, "tests": "all passed"}
    plan = auto_select_plan(state)
    assert "fresh" in plan.reasoning.lower() or "no previous" in plan.reasoning.lower()
    assert len(plan.agents) == 5  # full build


def test_auto_select_plan_many_existing_notes():
    state = {
        "running_agents": 0,
        "tests": "all passed",
        "agent_notes": {"a": "...", "b": "...", "c": "...", "d": "..."},
    }
    plan = auto_select_plan(state)
    assert "consolidat" in plan.reasoning.lower()


def test_auto_select_plan_few_notes_defaults_to_research():
    state = {
        "running_agents": 0,
        "tests": "all passed",
        "agent_notes": {"a": "some notes"},
    }
    plan = auto_select_plan(state)
    assert len(plan.agents) == 4  # research deep dive


def test_auto_select_plan_empty_state():
    """Empty state (no notes, no tests) should go to full build."""
    state = {}
    plan = auto_select_plan(state)
    assert len(plan.agents) == 5


# ---------------------------------------------------------------------------
# save_state
# ---------------------------------------------------------------------------


def test_save_state(tmp_path, monkeypatch):
    import dharma_swarm.orchestrate as orch

    state_file = tmp_path / "orchestrator_state.json"
    monkeypatch.setattr(orch, "STATE_FILE", state_file)

    plan = SwarmPlan(
        agents=[AgentSpec(name="t", role="r", prompt="p")],
        reasoning="test",
        timestamp="2026-03-07T00:00:00Z",
    )
    save_state(plan, {"notes_count": 3})

    assert state_file.exists()
    data = json.loads(state_file.read_text())
    assert data["last_run"] == "2026-03-07T00:00:00Z"
    assert data["agents_spawned"] == 1
    assert data["agent_names"] == ["t"]
    assert data["results"]["notes_count"] == 3


# ---------------------------------------------------------------------------
# Agent priority ordering
# ---------------------------------------------------------------------------


def test_maintenance_priority_order():
    plan = plan_small_maintenance()
    priorities = [a.priority for a in plan.agents]
    # Verify priorities are assigned (not all the same)
    assert len(set(priorities)) > 1


def test_full_build_priority_order():
    plan = plan_full_build()
    # Synthesizer should be highest priority (lowest number)
    synthesizer = next(a for a in plan.agents if a.name == "synthesizer")
    assert synthesizer.priority == 1
