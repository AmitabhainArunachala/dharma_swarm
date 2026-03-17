"""Tests for mathematical elegance bridges (Phase 7).

Verifies monadic composition, coalgebraic unfold, sheaf consistency,
and Fisher metric ranking work correctly.
"""

from __future__ import annotations

import pytest

from dharma_swarm.math_bridges import (
    AgentObservation,
    ProviderPerformance,
    TaskResult,
    check_sheaf_consistency,
    rank_providers_by_geometry,
    unfold_agent_step,
)


# ---------------------------------------------------------------------------
# Bridge 1: Monadic Task Composition
# ---------------------------------------------------------------------------

class TestTaskResult:
    def test_pure(self) -> None:
        r = TaskResult.pure(42)
        assert r.is_ok
        assert r.value == 42
        assert r.error is None

    def test_fail(self) -> None:
        r = TaskResult.fail("boom")
        assert not r.is_ok
        assert r.error == "boom"

    def test_bind_success_chain(self) -> None:
        def double(x: int) -> TaskResult:
            return TaskResult.pure(x * 2)

        def add_one(x: int) -> TaskResult:
            return TaskResult.pure(x + 1)

        result = TaskResult.pure(5).bind(double, "double").bind(add_one, "add_one")
        assert result.is_ok
        assert result.value == 11
        assert result.steps == ["double", "add_one"]

    def test_bind_short_circuits_on_error(self) -> None:
        call_count = 0

        def fail_step(x: int) -> TaskResult:
            return TaskResult.fail("step failed")

        def never_called(x: int) -> TaskResult:
            nonlocal call_count
            call_count += 1
            return TaskResult.pure(x)

        result = TaskResult.pure(1).bind(fail_step, "fail").bind(never_called, "skip")
        assert not result.is_ok
        assert result.error == "step failed"
        assert call_count == 0

    def test_bind_catches_exception(self) -> None:
        def explode(x: int) -> TaskResult:
            raise ValueError("kaboom")

        result = TaskResult.pure(1).bind(explode, "boom")
        assert not result.is_ok
        assert "kaboom" in result.error  # type: ignore[operator]

    def test_monad_left_unit(self) -> None:
        """Left unit law: pure(a).bind(f) == f(a)"""
        def f(x: int) -> TaskResult:
            return TaskResult.pure(x + 10)

        a = 5
        left = TaskResult.pure(a).bind(f)
        right = f(a)
        assert left.value == right.value

    def test_monad_right_unit(self) -> None:
        """Right unit law: m.bind(pure) == m"""
        m = TaskResult.pure(42)
        result = m.bind(TaskResult.pure)
        assert result.value == m.value


# ---------------------------------------------------------------------------
# Bridge 2: Coalgebraic Agent Lifecycle
# ---------------------------------------------------------------------------

class TestCoalgebra:
    def test_busy_with_result(self) -> None:
        obs = unfold_agent_step("busy", task_result="done", fitness=0.7)
        assert obs.next_status == "idle"
        assert obs.output == "done"
        assert obs.tasks_completed == 1

    def test_error_degrades_fitness(self) -> None:
        obs = unfold_agent_step("busy", error="timeout", fitness=0.5)
        assert obs.next_status == "idle"
        assert obs.fitness < 0.5

    def test_stopping_transitions_to_dead(self) -> None:
        obs = unfold_agent_step("stopping")
        assert obs.next_status == "dead"

    def test_idle_stays_idle(self) -> None:
        obs = unfold_agent_step("idle")
        assert obs.next_status == "idle"
        assert obs.output == "waiting"

    def test_unfold_trace(self) -> None:
        """Multiple unfold steps produce a trajectory (coinductive)."""
        states = ["idle"]
        for _ in range(3):
            obs = unfold_agent_step(states[-1])
            states.append(obs.next_status)
        assert states == ["idle", "idle", "idle", "idle"]


# ---------------------------------------------------------------------------
# Bridge 3: Sheaf Consistency
# ---------------------------------------------------------------------------

class TestSheafConsistency:
    def test_no_overlap(self) -> None:
        claims = {"agent1": {"key1": "v1"}, "agent2": {"key2": "v2"}}
        result = check_sheaf_consistency(claims)
        assert result["consistent"] is True
        assert result["agreements"] == 0
        assert result["obstructions"] == []

    def test_agreement(self) -> None:
        claims = {
            "agent1": {"temperature": 0.7},
            "agent2": {"temperature": 0.7},
        }
        result = check_sheaf_consistency(claims)
        assert result["consistent"] is True
        assert result["agreements"] == 1

    def test_obstruction(self) -> None:
        claims = {
            "agent1": {"best_model": "claude"},
            "agent2": {"best_model": "gpt4"},
        }
        result = check_sheaf_consistency(claims)
        assert result["consistent"] is False
        assert len(result["obstructions"]) == 1
        obs = result["obstructions"][0]
        assert obs["claim_key"] == "best_model"
        assert set(obs["agents"]) == {"agent1", "agent2"}

    def test_mixed(self) -> None:
        claims = {
            "a1": {"x": 1, "y": 2},
            "a2": {"x": 1, "y": 3},
            "a3": {"y": 2},
        }
        result = check_sheaf_consistency(claims)
        assert result["agreements"] == 1  # x agrees
        assert len(result["obstructions"]) == 1  # y disagrees

    def test_empty(self) -> None:
        result = check_sheaf_consistency({})
        assert result["consistent"] is True


# ---------------------------------------------------------------------------
# Bridge 4: Fisher Metric for Provider Routing
# ---------------------------------------------------------------------------

class TestProviderGeometry:
    def test_quality_score(self) -> None:
        perf = ProviderPerformance(
            provider_name="anthropic",
            mean_latency_ms=500.0,
            success_rate=0.95,
            mean_tokens_per_second=50.0,
            sample_count=100,
        )
        score = perf.quality_score
        assert 0.0 < score <= 1.0

    def test_zero_samples(self) -> None:
        perf = ProviderPerformance(provider_name="empty", sample_count=0)
        assert perf.quality_score == 0.0

    def test_ranking(self) -> None:
        fast = ProviderPerformance(
            provider_name="fast",
            mean_latency_ms=100.0,
            success_rate=0.99,
            mean_tokens_per_second=80.0,
            sample_count=50,
        )
        slow = ProviderPerformance(
            provider_name="slow",
            mean_latency_ms=5000.0,
            success_rate=0.7,
            mean_tokens_per_second=10.0,
            sample_count=50,
        )
        ranked = rank_providers_by_geometry([slow, fast])
        assert ranked[0] == "fast"
        assert ranked[1] == "slow"

    def test_ranking_empty(self) -> None:
        assert rank_providers_by_geometry([]) == []
