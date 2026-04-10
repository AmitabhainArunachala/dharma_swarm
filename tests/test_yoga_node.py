"""Tests for YogaNode — constraint-based resource allocation."""

import time
from datetime import datetime, timedelta, timezone

import pytest

from dharma_swarm.models import (
    AgentRole,
    AgentState,
    AgentStatus,
    ProviderType,
    Task,
    TaskPriority,
)
from dharma_swarm.yoga_node import (
    AgentCapacity,
    ContractionLevel,
    ConstraintVerdict,
    ROLE_CAPACITIES,
    TaskCost,
    UsageTracker,
    YogaScheduler,
    _day_start_ts,
)


# === Fixtures ===

def _agent(
    name: str = "test-agent",
    role: AgentRole = AgentRole.GENERAL,
    agent_id: str = "ag-001",
) -> AgentState:
    return AgentState(id=agent_id, name=name, role=role, status=AgentStatus.IDLE)


def _task(
    title: str = "test-task",
    priority: TaskPriority = TaskPriority.NORMAL,
    metadata: dict | None = None,
) -> Task:
    return Task(title=title, priority=priority, metadata=metadata or {})


# === TaskCost Tests ===

class TestTaskCost:
    def test_no_deadline(self):
        cost = TaskCost()
        assert cost.deadline_slack_sec is None
        assert cost.is_deadline_critical is False

    def test_deadline_far_future(self):
        cost = TaskCost(
            estimated_duration_sec=300,
            deadline_utc=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        assert cost.deadline_slack_sec > 0
        assert cost.is_deadline_critical is False

    def test_deadline_critical(self):
        cost = TaskCost(
            estimated_duration_sec=300,
            deadline_utc=datetime.now(timezone.utc) + timedelta(seconds=400),
        )
        # slack = 400 - 300 = 100, threshold = 300*2 = 600 → critical
        assert cost.is_deadline_critical is True

    def test_deadline_past(self):
        cost = TaskCost(
            estimated_duration_sec=300,
            deadline_utc=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        assert cost.deadline_slack_sec < 0
        assert cost.is_deadline_critical is True


# === UsageTracker Tests ===

class TestUsageTracker:
    def test_initial_state(self):
        tracker = UsageTracker()
        assert tracker.tokens_used_today == 0
        assert tracker.tasks_dispatched_today == 0
        assert tracker.contraction_level == ContractionLevel.RELAXED

    def test_record_dispatch(self):
        tracker = UsageTracker()
        tracker.record_dispatch("ag-001", ProviderType.ANTHROPIC, 10_000)
        assert tracker.tokens_used_today == 10_000
        assert tracker.tasks_dispatched_today == 1
        assert tracker.agent_load("ag-001") == 1

    def test_record_completion(self):
        tracker = UsageTracker()
        tracker.record_dispatch("ag-001", ProviderType.ANTHROPIC, 5000)
        assert tracker.agent_load("ag-001") == 1
        tracker.record_completion("ag-001")
        assert tracker.agent_load("ag-001") == 0

    def test_completion_without_dispatch(self):
        """Completion on agent with no load should not go negative."""
        tracker = UsageTracker()
        tracker.record_completion("ag-unknown")
        assert tracker.agent_load("ag-unknown") == 0

    def test_provider_rpm_tracking(self):
        tracker = UsageTracker()
        for _ in range(5):
            tracker.record_dispatch("ag-001", ProviderType.ANTHROPIC, 1000)
        assert tracker.provider_rpm(ProviderType.ANTHROPIC) == 5
        assert tracker.provider_rpm(ProviderType.OPENAI) == 0

    def test_contraction_levels(self):
        tracker = UsageTracker()
        assert tracker.contraction_level == ContractionLevel.RELAXED

        # Push to nominal (30-60%)
        tracker.tokens_used_today = 200_000
        assert tracker.contraction_level == ContractionLevel.NOMINAL

        # Push to contracted (60-85%)
        tracker.tokens_used_today = 400_000
        assert tracker.contraction_level == ContractionLevel.CONTRACTED

        # Push to critical (>85%)
        tracker.tokens_used_today = 450_000
        assert tracker.contraction_level == ContractionLevel.CRITICAL

        # At or over budget
        tracker.tokens_used_today = 500_000
        assert tracker.contraction_level == ContractionLevel.CRITICAL

    def test_tokens_remaining(self):
        tracker = UsageTracker()
        assert tracker.tokens_remaining_today == 500_000
        tracker.tokens_used_today = 123_456
        assert tracker.tokens_remaining_today == 500_000 - 123_456


# === YogaScheduler Tests ===

class TestYogaScheduler:
    def test_all_clear(self):
        yoga = YogaScheduler(quiet_hours=[])
        task = _task()
        agent = _agent()
        checks = yoga.can_dispatch(task, agent)
        assert len(checks) == 1
        assert checks[0].verdict == ConstraintVerdict.ALLOW
        assert checks[0].constraint_name == "all_clear"

    def test_quiet_hours_block(self):
        now_hour = datetime.now(timezone.utc).hour
        yoga = YogaScheduler(quiet_hours=[now_hour])
        task = _task(priority=TaskPriority.NORMAL)
        agent = _agent()
        checks = yoga.can_dispatch(task, agent)
        blocked = [c for c in checks if c.verdict != ConstraintVerdict.ALLOW]
        assert len(blocked) == 1
        assert blocked[0].constraint_name == "quiet_hours"

    def test_quiet_hours_urgent_bypass(self):
        now_hour = datetime.now(timezone.utc).hour
        yoga = YogaScheduler(quiet_hours=[now_hour])
        task = _task(priority=TaskPriority.URGENT)
        agent = _agent()
        checks = yoga.can_dispatch(task, agent)
        blocked = [c for c in checks if c.verdict != ConstraintVerdict.ALLOW]
        assert len(blocked) == 0

    def test_quiet_hours_operator_bypass(self):
        now_hour = datetime.now(timezone.utc).hour
        yoga = YogaScheduler(quiet_hours=[now_hour])
        task = _task(
            priority=TaskPriority.NORMAL,
            metadata={"created_via": "operator"},
        )
        task.created_by = "operator"
        agent = _agent()
        checks = yoga.can_dispatch(task, agent)
        blocked = [c for c in checks if c.verdict != ConstraintVerdict.ALLOW]
        assert len(blocked) == 0

    def test_token_budget_exceeded(self):
        yoga = YogaScheduler(quiet_hours=[], global_token_budget=500_000)
        yoga.usage.tokens_used_today = 499_000
        task = _task(metadata={"yoga": {"tokens": 5000}})
        agent = _agent()
        checks = yoga.can_dispatch(task, agent)
        blocked = [c for c in checks if c.verdict != ConstraintVerdict.ALLOW]
        assert any(c.constraint_name == "token_budget" for c in blocked)

    def test_daily_task_limit(self):
        yoga = YogaScheduler(quiet_hours=[], max_daily_tasks=5)
        yoga.usage.tasks_dispatched_today = 5
        task = _task(priority=TaskPriority.NORMAL)
        agent = _agent()
        checks = yoga.can_dispatch(task, agent)
        blocked = [c for c in checks if c.verdict != ConstraintVerdict.ALLOW]
        assert any(c.constraint_name == "daily_task_limit" for c in blocked)

    def test_daily_task_limit_high_bypass(self):
        yoga = YogaScheduler(quiet_hours=[], max_daily_tasks=5)
        yoga.usage.tasks_dispatched_today = 5
        task = _task(priority=TaskPriority.HIGH)
        agent = _agent()
        checks = yoga.can_dispatch(task, agent)
        blocked = [c for c in checks if c.constraint_name == "daily_task_limit"]
        assert len(blocked) == 0

    def test_agent_concurrent_limit(self):
        yoga = YogaScheduler(quiet_hours=[])
        agent = _agent(role=AgentRole.CARTOGRAPHER)
        # Cartographer has max_concurrent=1
        yoga.usage.agent_active_tasks[agent.id] = 1
        task = _task()
        checks = yoga.can_dispatch(task, agent)
        blocked = [c for c in checks if c.verdict != ConstraintVerdict.ALLOW]
        assert any(c.constraint_name == "agent_capacity" for c in blocked)

    def test_complexity_floor(self):
        yoga = YogaScheduler(quiet_hours=[])
        agent = _agent(role=AgentRole.ARCHITECT)
        # Architect has min_complexity=0.4
        task = _task(metadata={"yoga": {"complexity": 0.1}})
        checks = yoga.can_dispatch(task, agent)
        blocked = [c for c in checks if c.verdict != ConstraintVerdict.ALLOW]
        assert any(c.constraint_name == "complexity_floor" for c in blocked)

    def test_complexity_ceiling(self):
        yoga = YogaScheduler(quiet_hours=[])
        agent = _agent(role=AgentRole.VALIDATOR)
        # Validator has max_complexity=0.6
        task = _task(metadata={"yoga": {"complexity": 0.9}})
        checks = yoga.can_dispatch(task, agent)
        blocked = [c for c in checks if c.verdict != ConstraintVerdict.ALLOW]
        assert any(c.constraint_name == "complexity_ceiling" for c in blocked)

    def test_provider_rate_limit(self):
        yoga = YogaScheduler(quiet_hours=[])
        # Fill up Anthropic RPM
        for _ in range(10):
            yoga.usage.provider_calls.setdefault("anthropic", []).append(time.time())
        task = _task()
        agent = _agent()
        checks = yoga.can_dispatch(task, agent, provider=ProviderType.ANTHROPIC)
        blocked = [c for c in checks if c.verdict != ConstraintVerdict.ALLOW]
        assert any(c.constraint_name == "provider_rate_limit" for c in blocked)

    def test_provider_compatibility(self):
        yoga = YogaScheduler(quiet_hours=[])
        task = _task(metadata={"yoga": {"providers": ["anthropic"]}})
        agent = _agent()
        checks = yoga.can_dispatch(task, agent, provider=ProviderType.OPENAI)
        blocked = [c for c in checks if c.verdict != ConstraintVerdict.ALLOW]
        assert any(c.constraint_name == "provider_compatibility" for c in blocked)


class TestYogaSchedulerEstimation:
    def test_default_cost(self):
        yoga = YogaScheduler()
        task = _task()
        cost = yoga.estimate_cost(task)
        assert cost.estimated_tokens == 4096
        assert cost.complexity == 0.5
        assert cost.deadline_utc is None

    def test_metadata_override(self):
        yoga = YogaScheduler()
        task = _task(metadata={"yoga": {
            "tokens": 16000,
            "complexity": 0.9,
            "duration_sec": 1200,
            "deadline": "2026-12-31T23:59:59+00:00",
            "providers": ["anthropic", "openai"],
        }})
        cost = yoga.estimate_cost(task)
        assert cost.estimated_tokens == 16000
        assert cost.complexity == 0.9
        assert cost.estimated_duration_sec == 1200
        assert cost.deadline_utc is not None
        assert len(cost.required_providers) == 2

    def test_priority_duration_defaults(self):
        yoga = YogaScheduler()
        for priority, expected in [
            (TaskPriority.LOW, 120.0),
            (TaskPriority.NORMAL, 300.0),
            (TaskPriority.HIGH, 600.0),
            (TaskPriority.URGENT, 900.0),
        ]:
            task = _task(priority=priority)
            cost = yoga.estimate_cost(task)
            assert cost.estimated_duration_sec == expected, f"Failed for {priority}"

    def test_invalid_deadline_ignored(self):
        yoga = YogaScheduler()
        task = _task(metadata={"yoga": {"deadline": "not-a-date"}})
        cost = yoga.estimate_cost(task)
        assert cost.deadline_utc is None

    def test_invalid_provider_ignored(self):
        yoga = YogaScheduler()
        task = _task(metadata={"yoga": {"providers": ["nonexistent"]}})
        cost = yoga.estimate_cost(task)
        assert cost.required_providers == []


class TestYogaSchedulerFiltering:
    def test_filter_dispatches_allows_clean(self):
        yoga = YogaScheduler(quiet_hours=[])
        candidates = [
            (_task(title="t1"), _agent(agent_id="a1"), None),
            (_task(title="t2"), _agent(agent_id="a2"), None),
        ]
        allowed = yoga.filter_dispatches(candidates)
        assert len(allowed) == 2

    def test_filter_dispatches_drops_blocked(self):
        yoga = YogaScheduler(quiet_hours=[], max_daily_tasks=1)
        yoga.usage.tasks_dispatched_today = 1
        candidates = [
            (_task(title="normal"), _agent(agent_id="a1"), None),
            (_task(title="urgent", priority=TaskPriority.URGENT), _agent(agent_id="a2"), None),
        ]
        allowed = yoga.filter_dispatches(candidates)
        # Only urgent should pass
        assert len(allowed) == 1
        assert allowed[0][0].title == "urgent"

    def test_filter_priority_ordering(self):
        yoga = YogaScheduler(quiet_hours=[])
        candidates = [
            (_task(title="low", priority=TaskPriority.LOW), _agent(agent_id="a1"), None),
            (_task(title="urgent", priority=TaskPriority.URGENT), _agent(agent_id="a2"), None),
            (_task(title="normal", priority=TaskPriority.NORMAL), _agent(agent_id="a3"), None),
        ]
        allowed = yoga.filter_dispatches(candidates)
        titles = [a[0].title for a in allowed]
        assert titles == ["urgent", "normal", "low"]


class TestYogaSchedulerTracking:
    def test_record_dispatch_and_completion(self):
        yoga = YogaScheduler(quiet_hours=[])
        yoga.record_dispatch("ag-001", ProviderType.ANTHROPIC, 5000)
        assert yoga.usage.tokens_used_today == 5000
        assert yoga.usage.agent_load("ag-001") == 1
        yoga.record_completion("ag-001")
        assert yoga.usage.agent_load("ag-001") == 0

    def test_record_dispatch_no_provider(self):
        yoga = YogaScheduler(quiet_hours=[])
        yoga.record_dispatch("ag-001", None, 3000)
        assert yoga.usage.tokens_used_today == 3000
        assert yoga.usage.agent_load("ag-001") == 1

    def test_status_dict(self):
        yoga = YogaScheduler(quiet_hours=[2, 3])
        s = yoga.status()
        assert "contraction_level" in s
        assert "tokens_used_today" in s
        assert "agent_loads" in s
        assert s["quiet_hours"] == [2, 3]

    def test_contraction_report(self):
        yoga = YogaScheduler(quiet_hours=[])
        report = yoga.contraction_report()
        assert "YogaNode Contraction:" in report
        assert "Tokens:" in report
        assert "Tasks:" in report


class TestRoleCapacities:
    def test_all_roles_have_defaults(self):
        """Every role used in ROLE_CAPACITIES should be a valid AgentRole."""
        for role in ROLE_CAPACITIES:
            assert isinstance(role, AgentRole)

    def test_get_capacity_fallback(self):
        yoga = YogaScheduler()
        # CODER doesn't have an explicit capacity → falls back to default
        agent = _agent(role=AgentRole.CODER)
        capacity = yoga.get_capacity(agent)
        assert capacity.max_concurrent >= 1

    def test_custom_capacity(self):
        yoga = YogaScheduler()
        custom = AgentCapacity(max_concurrent=10, tokens_per_day=1_000_000)
        yoga.set_agent_capacity("ag-custom", custom)
        agent = _agent(agent_id="ag-custom")
        assert yoga.get_capacity(agent).max_concurrent == 10


class TestDayStartTs:
    def test_day_start_is_past(self):
        ts = _day_start_ts()
        assert ts <= time.time()

    def test_day_start_is_today(self):
        ts = _day_start_ts()
        now = time.time()
        assert now - ts < 86400
