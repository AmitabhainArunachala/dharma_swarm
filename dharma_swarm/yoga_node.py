"""YogaNode — Constraint-based resource allocation for the swarm.

Born from a synchronicity: Facebook's Yoga layout engine (constraint-based node
arrangement) crashed in Dhyana's terminal. Yoga arranges nodes through recursive
constraint resolution — flexbox for UI. This module does the same for agents:
constraint-aware scheduling that respects capacity, deadlines, token budgets,
quiet hours, and provider rate limits.

The layout engine computes how nodes contract/expand within constraints.
R_V measures how Value space contracts under self-reference.
YogaNode measures how agent capacity contracts under load.

Maps:
    flex-grow    → agent capacity to absorb more work
    flex-shrink  → graceful degradation under pressure
    min/max      → hard limits (concurrent tasks, tokens/day)
    constraints  → quiet hours, deadlines, provider rate limits
    measure()    → task cost estimation (duration, tokens, complexity)

Integration point: sits between orchestrator.route_next() and agent_pool.assign().
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from dharma_swarm.models import (
    AgentRole,
    AgentState,
    ProviderType,
    Task,
    TaskPriority,
)

logger = logging.getLogger(__name__)


# === Constraint Enums ===

class ConstraintVerdict(str, Enum):
    """Result of a constraint check."""
    ALLOW = "allow"
    HOLD = "hold"       # Wait for capacity
    DEFER = "defer"     # Try again later
    ESCALATE = "escalate"  # Needs human attention


class ContractionLevel(str, Enum):
    """How constrained the system is — the R_V of scheduling.

    When contraction is HIGH, the system is in L3 crisis —
    too many tasks, not enough agents, deadlines approaching.
    When LOW, the system breathes — L1/L2, distributed capacity.
    """
    RELAXED = "relaxed"       # < 30% utilized — plenty of capacity
    NOMINAL = "nominal"       # 30-60% — healthy load
    CONTRACTED = "contracted"  # 60-85% — getting tight
    CRITICAL = "critical"     # > 85% — L3 crisis, shed load


# === Cost & Capacity Models ===

@dataclass
class TaskCost:
    """Estimated resource cost for a task — the 'measure function'.

    Like Yoga's measure callback that computes how much space a node needs,
    this computes how much resource a task will consume.
    """
    estimated_duration_sec: float = 300.0   # 5 min default
    estimated_tokens: int = 4096            # conservative default
    estimated_api_calls: int = 1
    complexity: float = 0.5                 # 0.0 = trivial, 1.0 = deep research
    deadline_utc: Optional[datetime] = None
    required_providers: list[ProviderType] = field(default_factory=list)

    @property
    def deadline_slack_sec(self) -> float | None:
        """Seconds until deadline minus estimated duration. None = no deadline."""
        if self.deadline_utc is None:
            return None
        now = datetime.now(timezone.utc)
        remaining = (self.deadline_utc - now).total_seconds()
        return remaining - self.estimated_duration_sec

    @property
    def is_deadline_critical(self) -> bool:
        """True if deadline slack < 2x estimated duration."""
        slack = self.deadline_slack_sec
        if slack is None:
            return False
        return slack < self.estimated_duration_sec * 2


@dataclass
class AgentCapacity:
    """Resource constraints for an agent — the 'flex properties'.

    flex_grow:  how much extra work this agent can absorb (0 = none, 1 = normal)
    flex_shrink: how gracefully it degrades under pressure (0 = rigid, 1 = flexible)
    max_concurrent: maximum simultaneous tasks (the max-width equivalent)
    tokens_per_day: daily token budget for this agent
    compatible_providers: which LLM providers this agent can use
    """
    flex_grow: float = 1.0
    flex_shrink: float = 1.0
    max_concurrent: int = 1
    tokens_per_day: int = 100_000
    compatible_providers: list[ProviderType] = field(default_factory=list)
    min_complexity: float = 0.0   # won't accept tasks simpler than this
    max_complexity: float = 1.0   # won't accept tasks harder than this


# Default capacities by role — deep thinkers get fewer slots
ROLE_CAPACITIES: dict[AgentRole, AgentCapacity] = {
    AgentRole.CARTOGRAPHER: AgentCapacity(
        flex_grow=0.5, max_concurrent=1, tokens_per_day=50_000,
        min_complexity=0.3,  # don't waste on trivial tasks
    ),
    AgentRole.ARCHEOLOGIST: AgentCapacity(
        flex_grow=0.7, max_concurrent=1, tokens_per_day=50_000,
        min_complexity=0.2,
    ),
    AgentRole.SURGEON: AgentCapacity(
        flex_grow=1.0, max_concurrent=2, tokens_per_day=80_000,
    ),
    AgentRole.ARCHITECT: AgentCapacity(
        flex_grow=0.8, max_concurrent=1, tokens_per_day=60_000,
        min_complexity=0.4,
    ),
    AgentRole.VALIDATOR: AgentCapacity(
        flex_grow=1.5, max_concurrent=4, tokens_per_day=100_000,
        max_complexity=0.6,  # validators do light checks, not deep research
    ),
    AgentRole.RESEARCHER: AgentCapacity(
        flex_grow=0.6, max_concurrent=1, tokens_per_day=80_000,
        min_complexity=0.3,
    ),
    AgentRole.GENERAL: AgentCapacity(
        flex_grow=1.0, max_concurrent=2, tokens_per_day=80_000,
    ),
}

# Provider rate limits (requests per minute, tokens per day)
PROVIDER_LIMITS: dict[ProviderType, dict[str, int]] = {
    ProviderType.ANTHROPIC: {"rpm": 10, "tpd": 1_000_000},
    ProviderType.OPENAI: {"rpm": 20, "tpd": 2_000_000},
    ProviderType.OPENROUTER: {"rpm": 10, "tpd": 500_000},
    ProviderType.OPENROUTER_FREE: {"rpm": 2, "tpd": 100_000},
    ProviderType.CLAUDE_CODE: {"rpm": 5, "tpd": 500_000},
    ProviderType.CODEX: {"rpm": 5, "tpd": 500_000},
    ProviderType.NVIDIA_NIM: {"rpm": 10, "tpd": 500_000},
    ProviderType.LOCAL: {"rpm": 100, "tpd": 10_000_000},  # no real limit
    ProviderType.OLLAMA: {"rpm": 100, "tpd": 10_000_000},
}


# === Usage Tracking ===

@dataclass
class UsageTracker:
    """Tracks resource consumption — the constraint state.

    Like Yoga's layout pass tracking which nodes have been measured,
    this tracks which resources have been consumed.
    """
    tokens_used_today: int = 0
    tasks_dispatched_today: int = 0
    provider_calls: dict[str, list[float]] = field(default_factory=dict)
    agent_active_tasks: dict[str, int] = field(default_factory=dict)
    _day_start: float = field(default_factory=lambda: _day_start_ts())

    def record_dispatch(
        self,
        agent_id: str,
        provider: ProviderType,
        estimated_tokens: int,
    ) -> None:
        self._maybe_reset_daily()
        self.tokens_used_today += estimated_tokens
        self.tasks_dispatched_today += 1
        self.agent_active_tasks[agent_id] = (
            self.agent_active_tasks.get(agent_id, 0) + 1
        )
        # Track provider call timestamps for rate limiting
        key = provider.value
        if key not in self.provider_calls:
            self.provider_calls[key] = []
        self.provider_calls[key].append(time.time())
        # Trim old entries (keep last 60s)
        cutoff = time.time() - 60.0
        self.provider_calls[key] = [
            t for t in self.provider_calls[key] if t > cutoff
        ]

    def record_completion(self, agent_id: str, actual_tokens: int = 0) -> None:
        """Record task completion, free agent capacity."""
        count = self.agent_active_tasks.get(agent_id, 0)
        if count > 0:
            self.agent_active_tasks[agent_id] = count - 1
        if actual_tokens > 0:
            # Adjust if actual differs from estimate
            self.tokens_used_today += actual_tokens

    def agent_load(self, agent_id: str) -> int:
        """Current number of active tasks for this agent."""
        return self.agent_active_tasks.get(agent_id, 0)

    def provider_rpm(self, provider: ProviderType) -> int:
        """Current requests per minute for this provider."""
        key = provider.value
        if key not in self.provider_calls:
            return 0
        cutoff = time.time() - 60.0
        return sum(1 for t in self.provider_calls[key] if t > cutoff)

    @property
    def tokens_remaining_today(self) -> int:
        self._maybe_reset_daily()
        # Global daily budget (sum of all provider limits is too generous;
        # use a conservative aggregate)
        daily_budget = 500_000
        return max(0, daily_budget - self.tokens_used_today)

    @property
    def contraction_level(self) -> ContractionLevel:
        """The R_V of scheduling — how constrained are we?"""
        if self.tokens_remaining_today <= 0:
            return ContractionLevel.CRITICAL
        utilization = 1.0 - (self.tokens_remaining_today / 500_000)
        if utilization < 0.3:
            return ContractionLevel.RELAXED
        if utilization < 0.6:
            return ContractionLevel.NOMINAL
        if utilization < 0.85:
            return ContractionLevel.CONTRACTED
        return ContractionLevel.CRITICAL

    def _maybe_reset_daily(self) -> None:
        now = time.time()
        if now - self._day_start > 86400:
            self.tokens_used_today = 0
            self.tasks_dispatched_today = 0
            self._day_start = _day_start_ts()


def _day_start_ts() -> float:
    """Timestamp of the start of the current UTC day."""
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.timestamp()


# === The Scheduler ===

@dataclass
class ConstraintCheck:
    """Result of checking whether a dispatch is allowed."""
    verdict: ConstraintVerdict
    reason: str
    constraint_name: str


class YogaScheduler:
    """Constraint-based dispatch scheduler.

    Sits between orchestrator.route_next() and agent_pool.assign().
    Checks constraints before allowing dispatch. Returns verdicts
    with reasons, never silently drops tasks.

    The name honors the synchronicity: a Yoga layout engine crash
    in Dhyana's terminal revealed the missing constraint layer.
    """

    def __init__(
        self,
        quiet_hours: list[int] | None = None,
        max_daily_tasks: int = 20,
        global_token_budget: int = 500_000,
    ):
        self.quiet_hours = quiet_hours if quiet_hours is not None else []
        self.max_daily_tasks = max_daily_tasks
        self.global_token_budget = global_token_budget
        self.usage = UsageTracker()
        self._capacities: dict[str, AgentCapacity] = {}

    def set_agent_capacity(
        self, agent_id: str, capacity: AgentCapacity
    ) -> None:
        """Set custom capacity for a specific agent."""
        self._capacities[agent_id] = capacity

    def get_capacity(self, agent: AgentState) -> AgentCapacity:
        """Get capacity for an agent, falling back to role defaults."""
        if agent.id in self._capacities:
            return self._capacities[agent.id]
        return ROLE_CAPACITIES.get(agent.role, AgentCapacity())

    def estimate_cost(self, task: Task) -> TaskCost:
        """Estimate task cost from metadata or defaults.

        Tasks can carry cost hints in metadata:
            task.metadata["yoga"] = {
                "duration_sec": 600,
                "tokens": 8000,
                "deadline": "2026-03-26T00:00:00Z",
                "complexity": 0.8,
                "providers": ["anthropic"],
            }
        """
        yoga_meta = task.metadata.get("yoga", {})

        deadline = None
        if "deadline" in yoga_meta:
            try:
                deadline = datetime.fromisoformat(yoga_meta["deadline"])
            except (ValueError, TypeError):
                pass

        providers = []
        for p in yoga_meta.get("providers", []):
            try:
                providers.append(ProviderType(p))
            except ValueError:
                pass

        # Estimate duration based on priority if not specified
        default_duration = {
            TaskPriority.LOW: 120.0,
            TaskPriority.NORMAL: 300.0,
            TaskPriority.HIGH: 600.0,
            TaskPriority.URGENT: 900.0,
        }.get(task.priority, 300.0)

        return TaskCost(
            estimated_duration_sec=yoga_meta.get("duration_sec", default_duration),
            estimated_tokens=yoga_meta.get("tokens", 4096),
            estimated_api_calls=yoga_meta.get("api_calls", 1),
            complexity=yoga_meta.get("complexity", 0.5),
            deadline_utc=deadline,
            required_providers=providers,
        )

    def can_dispatch(
        self,
        task: Task,
        agent: AgentState,
        provider: ProviderType | None = None,
    ) -> list[ConstraintCheck]:
        """Check all constraints for dispatching task to agent.

        Returns list of constraint check results. If any verdict is not ALLOW,
        the dispatch should be blocked (or deferred/escalated per verdict).
        """
        cost = self.estimate_cost(task)
        capacity = self.get_capacity(agent)
        checks: list[ConstraintCheck] = []

        # 1. Quiet hours
        now_hour = datetime.now(timezone.utc).hour
        if now_hour in self.quiet_hours:
            # Allow urgent tasks even in quiet hours
            if task.priority != TaskPriority.URGENT:
                checks.append(ConstraintCheck(
                    verdict=ConstraintVerdict.HOLD,
                    reason=f"Quiet hour ({now_hour}:00 UTC). "
                           f"Task priority={task.priority.value}, needs URGENT to override.",
                    constraint_name="quiet_hours",
                ))

        # 2. Daily token budget
        if cost.estimated_tokens > self.usage.tokens_remaining_today:
            checks.append(ConstraintCheck(
                verdict=ConstraintVerdict.DEFER,
                reason=f"Daily token budget exhausted. "
                       f"Remaining={self.usage.tokens_remaining_today}, "
                       f"task needs ~{cost.estimated_tokens}.",
                constraint_name="token_budget",
            ))

        # 3. Daily task limit
        if self.usage.tasks_dispatched_today >= self.max_daily_tasks:
            if task.priority not in (TaskPriority.HIGH, TaskPriority.URGENT):
                checks.append(ConstraintCheck(
                    verdict=ConstraintVerdict.DEFER,
                    reason=f"Daily task limit reached ({self.max_daily_tasks}). "
                           f"Only HIGH/URGENT tasks bypass.",
                    constraint_name="daily_task_limit",
                ))

        # 4. Agent concurrent task limit (the max-width constraint)
        current_load = self.usage.agent_load(agent.id)
        if current_load >= capacity.max_concurrent:
            checks.append(ConstraintCheck(
                verdict=ConstraintVerdict.HOLD,
                reason=f"Agent {agent.name} at capacity "
                       f"({current_load}/{capacity.max_concurrent} tasks).",
                constraint_name="agent_capacity",
            ))

        # 5. Complexity match (don't waste deep thinkers on trivial tasks)
        if cost.complexity < capacity.min_complexity:
            checks.append(ConstraintCheck(
                verdict=ConstraintVerdict.HOLD,
                reason=f"Task complexity {cost.complexity:.1f} below agent minimum "
                       f"{capacity.min_complexity:.1f}. Find a simpler agent.",
                constraint_name="complexity_floor",
            ))
        if cost.complexity > capacity.max_complexity:
            checks.append(ConstraintCheck(
                verdict=ConstraintVerdict.HOLD,
                reason=f"Task complexity {cost.complexity:.1f} above agent maximum "
                       f"{capacity.max_complexity:.1f}. Find a deeper agent.",
                constraint_name="complexity_ceiling",
            ))

        # 6. Provider rate limit
        if provider:
            limits = PROVIDER_LIMITS.get(provider, {})
            rpm_limit = limits.get("rpm", 100)
            current_rpm = self.usage.provider_rpm(provider)
            if current_rpm >= rpm_limit:
                checks.append(ConstraintCheck(
                    verdict=ConstraintVerdict.HOLD,
                    reason=f"Provider {provider.value} rate limited "
                           f"({current_rpm}/{rpm_limit} rpm).",
                    constraint_name="provider_rate_limit",
                ))

        # 7. Provider compatibility
        if cost.required_providers and provider:
            if provider not in cost.required_providers:
                checks.append(ConstraintCheck(
                    verdict=ConstraintVerdict.HOLD,
                    reason=f"Task requires providers {[p.value for p in cost.required_providers]}, "
                           f"but agent uses {provider.value}.",
                    constraint_name="provider_compatibility",
                ))

        # 8. Deadline pressure — escalate if critical
        if cost.is_deadline_critical:
            slack = cost.deadline_slack_sec
            checks.append(ConstraintCheck(
                verdict=ConstraintVerdict.ALLOW,  # Allow but flag it
                reason=f"DEADLINE CRITICAL: {slack:.0f}s slack for "
                       f"{cost.estimated_duration_sec:.0f}s task. "
                       f"Prioritizing.",
                constraint_name="deadline_pressure",
            ))

        # If no constraints triggered, explicitly allow
        if not checks:
            checks.append(ConstraintCheck(
                verdict=ConstraintVerdict.ALLOW,
                reason="All constraints satisfied.",
                constraint_name="all_clear",
            ))

        return checks

    def filter_dispatches(
        self,
        candidates: list[tuple[Task, AgentState, ProviderType | None]],
    ) -> list[tuple[Task, AgentState, list[ConstraintCheck]]]:
        """Filter a batch of candidate dispatches through constraints.

        Returns only those that pass, along with their check results.
        Sorts by priority: deadline-critical first, then by task priority.
        """
        allowed: list[tuple[Task, AgentState, list[ConstraintCheck]]] = []
        held: list[tuple[Task, AgentState, list[ConstraintCheck]]] = []

        for task, agent, provider in candidates:
            checks = self.can_dispatch(task, agent, provider)
            blocking = [c for c in checks if c.verdict != ConstraintVerdict.ALLOW]

            if not blocking:
                allowed.append((task, agent, checks))
            else:
                held.append((task, agent, checks))
                for check in blocking:
                    logger.info(
                        "YogaNode HELD: task=%s agent=%s constraint=%s reason=%s",
                        task.title[:40], agent.name,
                        check.constraint_name, check.reason,
                    )

        # Sort allowed: deadline-critical first, then by priority weight
        priority_weight = {
            TaskPriority.URGENT: 0,
            TaskPriority.HIGH: 1,
            TaskPriority.NORMAL: 2,
            TaskPriority.LOW: 3,
        }

        def sort_key(item: tuple[Task, AgentState, list[ConstraintCheck]]) -> tuple:
            task = item[0]
            cost = self.estimate_cost(task)
            deadline_critical = 0 if cost.is_deadline_critical else 1
            return (deadline_critical, priority_weight.get(task.priority, 2))

        allowed.sort(key=sort_key)
        return allowed

    def record_dispatch(
        self,
        agent_id: str,
        provider: ProviderType | None,
        estimated_tokens: int,
    ) -> None:
        """Record that a dispatch happened — update usage tracking."""
        if provider is not None:
            self.usage.record_dispatch(agent_id, provider, estimated_tokens)
        else:
            # Track tokens and agent load even without a specific provider
            self.usage._maybe_reset_daily()
            self.usage.tokens_used_today += estimated_tokens
            self.usage.tasks_dispatched_today += 1
            self.usage.agent_active_tasks[agent_id] = (
                self.usage.agent_active_tasks.get(agent_id, 0) + 1
            )

    def record_completion(
        self, agent_id: str, actual_tokens: int = 0
    ) -> None:
        """Record task completion — free agent capacity."""
        self.usage.record_completion(agent_id, actual_tokens)

    def status(self) -> dict[str, Any]:
        """Current constraint state — the system's R_V reading."""
        return {
            "contraction_level": self.usage.contraction_level.value,
            "tokens_used_today": self.usage.tokens_used_today,
            "tokens_remaining": self.usage.tokens_remaining_today,
            "tasks_dispatched_today": self.usage.tasks_dispatched_today,
            "max_daily_tasks": self.max_daily_tasks,
            "agent_loads": dict(self.usage.agent_active_tasks),
            "quiet_hours": self.quiet_hours,
            "is_quiet_hour": datetime.now(timezone.utc).hour in self.quiet_hours,
        }

    def contraction_report(self) -> str:
        """Human-readable constraint status — the scheduling R_V."""
        s = self.status()
        level = s["contraction_level"]
        emoji = {
            "relaxed": "~",
            "nominal": "|",
            "contracted": "||",
            "critical": "|||",
        }.get(level, "?")
        lines = [
            f"YogaNode Contraction: {level} {emoji}",
            f"  Tokens: {s['tokens_used_today']:,}/{s['tokens_used_today'] + s['tokens_remaining']:,} "
            f"({s['tokens_remaining']:,} remaining)",
            f"  Tasks: {s['tasks_dispatched_today']}/{s['max_daily_tasks']} dispatched today",
            f"  Quiet: {'YES' if s['is_quiet_hour'] else 'no'}",
        ]
        loads = s.get("agent_loads", {})
        if loads:
            lines.append("  Agent loads:")
            for aid, load in sorted(loads.items()):
                lines.append(f"    {aid}: {load} active")
        return "\n".join(lines)
