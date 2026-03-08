"""Tests for dharma_swarm.dag_executor -- DAG execution engine."""

import asyncio
import time

import pytest

from dharma_swarm.dag_executor import DAGExecutor, ExecutionResult, StepResult
from dharma_swarm.skill_composer import CompositionPlan, SkillComposer, SkillStep


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _composer() -> SkillComposer:
    """Bare SkillComposer (no registry/router)."""
    return SkillComposer()


def _plan(steps: list[dict], task: str = "test task") -> CompositionPlan:
    """Build a CompositionPlan from step dicts."""
    return _composer().compose_from_steps(task, steps)


async def _echo_runner(step: SkillStep, context: str) -> str:
    """Runner that echoes step task + context length."""
    return f"done:{step.task}|ctx={len(context)}"


# ---------------------------------------------------------------------------
# 1. Single-step plan
# ---------------------------------------------------------------------------


async def test_single_step_plan():
    composer = _composer()
    plan = composer.compose_from_steps("simple", [
        {"skill_name": "builder", "task": "build it", "step_id": "s1"},
    ])
    executor = DAGExecutor(composer, runner_fn=_echo_runner)
    result = await executor.execute(plan)

    assert result.status == "completed"
    assert result.steps_completed == 1
    assert result.steps_failed == 0
    assert result.steps_skipped == 0
    assert len(result.step_results) == 1
    assert result.step_results[0].success is True
    assert "done:build it" in result.step_results[0].output


# ---------------------------------------------------------------------------
# 2. Multi-wave plan (correct order)
# ---------------------------------------------------------------------------


async def test_multi_wave_order():
    """Steps execute in dependency order: wave 0 before wave 1."""
    order: list[str] = []

    async def tracking_runner(step: SkillStep, ctx: str) -> str:
        order.append(step.step_id)
        return f"ok:{step.step_id}"

    composer = _composer()
    plan = composer.compose_from_steps("chained", [
        {"skill_name": "a", "task": "first", "step_id": "w0"},
        {"skill_name": "b", "task": "second", "step_id": "w1", "depends_on": ["w0"]},
    ])
    executor = DAGExecutor(composer, runner_fn=tracking_runner)
    result = await executor.execute(plan)

    assert result.status == "completed"
    assert order == ["w0", "w1"]


# ---------------------------------------------------------------------------
# 3. Concurrent steps within same wave
# ---------------------------------------------------------------------------


async def test_concurrent_within_wave():
    """Two independent steps overlap in time (run concurrently)."""
    timestamps: dict[str, tuple[float, float]] = {}

    async def slow_runner(step: SkillStep, ctx: str) -> str:
        t0 = time.monotonic()
        await asyncio.sleep(0.1)
        timestamps[step.step_id] = (t0, time.monotonic())
        return "ok"

    composer = _composer()
    plan = composer.compose_from_steps("parallel", [
        {"skill_name": "a", "task": "alpha", "step_id": "p1"},
        {"skill_name": "b", "task": "beta", "step_id": "p2"},
    ])
    executor = DAGExecutor(composer, runner_fn=slow_runner)

    t_start = time.monotonic()
    result = await executor.execute(plan)
    wall = time.monotonic() - t_start

    assert result.steps_completed == 2
    # If truly concurrent, wall time < 2 * 0.1s
    assert wall < 0.25, f"Expected concurrent execution, got {wall:.3f}s"


# ---------------------------------------------------------------------------
# 4. Failed step skips downstream dependents
# ---------------------------------------------------------------------------


async def test_failed_step_skips_downstream():
    call_count = 0

    async def failing_runner(step: SkillStep, ctx: str) -> str:
        nonlocal call_count
        call_count += 1
        if step.step_id == "s1":
            raise RuntimeError("boom")
        return "ok"

    composer = _composer()
    plan = composer.compose_from_steps("cascade", [
        {"skill_name": "a", "task": "fail here", "step_id": "s1"},
        {"skill_name": "b", "task": "depends", "step_id": "s2", "depends_on": ["s1"]},
    ])
    executor = DAGExecutor(composer, runner_fn=failing_runner)
    result = await executor.execute(plan)

    assert result.status == "failed"
    assert result.steps_failed == 1
    assert result.steps_skipped == 1
    # The downstream step should never be called
    assert call_count == 1
    # Verify the skip reason
    skipped = [r for r in result.step_results if r.step_id == "s2"]
    assert len(skipped) == 1
    assert "Skipped" in skipped[0].error


# ---------------------------------------------------------------------------
# 5. Retry on failure
# ---------------------------------------------------------------------------


async def test_retry_on_failure():
    """Step with retry=2 is attempted 3 times total before failing."""
    attempts = 0

    async def flaky_runner(step: SkillStep, ctx: str) -> str:
        nonlocal attempts
        attempts += 1
        raise ValueError("still broken")

    composer = _composer()
    plan = composer.compose_from_steps("retry", [
        {"skill_name": "a", "task": "flaky", "step_id": "r1", "retry": 2},
    ])
    executor = DAGExecutor(composer, runner_fn=flaky_runner)
    result = await executor.execute(plan)

    assert result.steps_failed == 1
    assert attempts == 3  # 1 initial + 2 retries
    assert result.step_results[0].retries_used == 3


async def test_retry_succeeds_on_second_attempt():
    """Step fails once, succeeds on retry."""
    attempts = 0

    async def flaky_then_ok(step: SkillStep, ctx: str) -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ValueError("transient")
        return "recovered"

    composer = _composer()
    plan = composer.compose_from_steps("retry-ok", [
        {"skill_name": "a", "task": "flaky", "step_id": "r1", "retry": 1},
    ])
    executor = DAGExecutor(composer, runner_fn=flaky_then_ok)
    result = await executor.execute(plan)

    assert result.status == "completed"
    assert result.step_results[0].success is True
    assert result.step_results[0].output == "recovered"
    assert attempts == 2


# ---------------------------------------------------------------------------
# 6. Context flows from upstream to downstream
# ---------------------------------------------------------------------------


async def test_context_flows_downstream():
    """Downstream step receives context assembled from upstream artifacts."""
    received_context: list[str] = []

    async def ctx_capture(step: SkillStep, ctx: str) -> str:
        received_context.append(ctx)
        return f"output-from-{step.step_id}"

    composer = _composer()
    plan = composer.compose_from_steps("ctx-flow", [
        {"skill_name": "scanner", "task": "scan code", "step_id": "scan"},
        {"skill_name": "builder", "task": "build it", "step_id": "build", "depends_on": ["scan"]},
    ])
    executor = DAGExecutor(composer, runner_fn=ctx_capture)
    result = await executor.execute(plan)

    assert result.status == "completed"
    # First step has no upstream context
    assert received_context[0] == ""
    # Second step should have upstream artifact content
    assert "output-from-scan" in received_context[1]
    assert "scanner" in received_context[1]


# ---------------------------------------------------------------------------
# 7. on_step_complete callback fires
# ---------------------------------------------------------------------------


async def test_on_step_complete_callback():
    callback_results: list[StepResult] = []

    async def on_complete(sr: StepResult) -> None:
        callback_results.append(sr)

    composer = _composer()
    plan = composer.compose_from_steps("callback", [
        {"skill_name": "a", "task": "alpha", "step_id": "c1"},
        {"skill_name": "b", "task": "beta", "step_id": "c2"},
    ])
    executor = DAGExecutor(composer, runner_fn=_echo_runner)
    await executor.execute(plan, on_step_complete=on_complete)

    assert len(callback_results) == 2
    ids = {r.step_id for r in callback_results}
    assert ids == {"c1", "c2"}


# ---------------------------------------------------------------------------
# 8. Empty plan
# ---------------------------------------------------------------------------


async def test_empty_plan():
    composer = _composer()
    plan = CompositionPlan(task="empty", steps=[], status="pending")
    executor = DAGExecutor(composer, runner_fn=_echo_runner)
    result = await executor.execute(plan)

    assert result.status == "completed"
    assert result.steps_completed == 0
    assert result.steps_failed == 0
    assert result.steps_skipped == 0
    assert result.step_results == []


# ---------------------------------------------------------------------------
# 9. All steps fail -> status "failed"
# ---------------------------------------------------------------------------


async def test_all_fail_status():
    async def always_fail(step: SkillStep, ctx: str) -> str:
        raise RuntimeError("nope")

    composer = _composer()
    plan = composer.compose_from_steps("doom", [
        {"skill_name": "a", "task": "fail1", "step_id": "f1"},
        {"skill_name": "b", "task": "fail2", "step_id": "f2"},
    ])
    executor = DAGExecutor(composer, runner_fn=always_fail)
    result = await executor.execute(plan)

    assert result.status == "failed"
    assert result.steps_completed == 0
    assert result.steps_failed == 2


# ---------------------------------------------------------------------------
# 10. Partial success -> status "partial"
# ---------------------------------------------------------------------------


async def test_partial_status():
    async def half_fail(step: SkillStep, ctx: str) -> str:
        if step.step_id == "ok":
            return "fine"
        raise RuntimeError("nope")

    composer = _composer()
    plan = composer.compose_from_steps("mixed", [
        {"skill_name": "a", "task": "good", "step_id": "ok"},
        {"skill_name": "b", "task": "bad", "step_id": "fail"},
    ])
    executor = DAGExecutor(composer, runner_fn=half_fail)
    result = await executor.execute(plan)

    assert result.status == "partial"
    assert result.steps_completed == 1
    assert result.steps_failed == 1


# ---------------------------------------------------------------------------
# 11. execute_step_only
# ---------------------------------------------------------------------------


async def test_execute_step_only():
    composer = _composer()
    plan = composer.compose_from_steps("single", [
        {"skill_name": "x", "task": "just this", "step_id": "only"},
    ])
    executor = DAGExecutor(composer, runner_fn=_echo_runner)
    sr = await executor.execute_step_only(plan, "only")

    assert sr.success is True
    assert sr.step_id == "only"
    assert "just this" in sr.output


async def test_execute_step_only_missing():
    composer = _composer()
    plan = CompositionPlan(task="empty", steps=[], status="pending")
    executor = DAGExecutor(composer, runner_fn=_echo_runner)

    with pytest.raises(ValueError, match="not found"):
        await executor.execute_step_only(plan, "ghost")


# ---------------------------------------------------------------------------
# 12. Timeout handling
# ---------------------------------------------------------------------------


async def test_timeout_handling():
    async def slow_forever(step: SkillStep, ctx: str) -> str:
        await asyncio.sleep(10)
        return "never"

    composer = _composer()
    plan = composer.compose_from_steps("timeout", [
        {"skill_name": "a", "task": "slow", "step_id": "t1", "timeout": 0.1},
    ])
    executor = DAGExecutor(composer, runner_fn=slow_forever)
    result = await executor.execute(plan)

    assert result.steps_failed == 1
    assert "Timeout" in result.step_results[0].error


# ---------------------------------------------------------------------------
# 13. Mock runner receives correct context
# ---------------------------------------------------------------------------


async def test_runner_receives_correct_context():
    """Verify runner_fn gets the step and assembled context string."""
    captured: list[tuple[str, str]] = []

    async def spy_runner(step: SkillStep, ctx: str) -> str:
        captured.append((step.step_id, ctx))
        return "spied"

    composer = _composer()
    plan = composer.compose_from_steps("spy", [
        {"skill_name": "a", "task": "origin", "step_id": "src"},
        {"skill_name": "b", "task": "dest", "step_id": "dst", "depends_on": ["src"]},
    ])
    executor = DAGExecutor(composer, runner_fn=spy_runner)
    await executor.execute(plan)

    # First step: no upstream context
    assert captured[0] == ("src", "")
    # Second step: has upstream artifact from "src"
    step_id, ctx = captured[1]
    assert step_id == "dst"
    assert "spied" in ctx  # content from upstream
    assert "src" in ctx    # step_id reference in context header


# ---------------------------------------------------------------------------
# 14. ExecutionResult has correct counts
# ---------------------------------------------------------------------------


async def test_execution_result_counts():
    """Three-wave plan: 1 ok, 1 fail, 1 skipped => partial, counts correct."""
    async def selective(step: SkillStep, ctx: str) -> str:
        if step.step_id == "mid":
            raise RuntimeError("fail")
        return "ok"

    composer = _composer()
    plan = composer.compose_from_steps("counts", [
        {"skill_name": "a", "task": "pass", "step_id": "top"},
        {"skill_name": "b", "task": "fail", "step_id": "mid", "depends_on": ["top"]},
        {"skill_name": "c", "task": "skip", "step_id": "bot", "depends_on": ["mid"]},
    ])
    executor = DAGExecutor(composer, runner_fn=selective)
    result = await executor.execute(plan)

    assert result.plan_task == "counts"
    assert result.status == "partial"
    assert result.steps_completed == 1
    assert result.steps_failed == 1
    assert result.steps_skipped == 1
    assert len(result.step_results) == 3
    assert result.total_duration_seconds > 0
