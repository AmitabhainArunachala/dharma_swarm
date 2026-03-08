"""DAG Executor -- runs CompositionPlan steps in topological wave order.

Takes the DAG built by SkillComposer and actually executes it:
waves of concurrent steps, context flowing from upstream artifacts,
retry logic, and failure propagation (skip downstream on failure).

The runner_fn is pluggable: in tests it's a mock, in production it
wires to agent_runner.run_task().
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Coroutine
from typing import Any

from pydantic import BaseModel, Field

from dharma_swarm.skill_composer import CompositionPlan, SkillComposer, SkillStep

logger = logging.getLogger(__name__)

# Type alias for the pluggable runner function.
RunnerFn = Callable[[SkillStep, str], Coroutine[Any, Any, str]]


# -- Result models -----------------------------------------------------------


class StepResult(BaseModel):
    """Result of executing a single skill step."""

    step_id: str
    skill_name: str
    success: bool
    output: str = ""
    error: str = ""
    duration_seconds: float = 0.0
    retries_used: int = 0


class ExecutionResult(BaseModel):
    """Result of executing a full composition plan."""

    plan_task: str
    status: str = "completed"  # completed | partial | failed
    steps_completed: int = 0
    steps_failed: int = 0
    steps_skipped: int = 0
    step_results: list[StepResult] = Field(default_factory=list)
    total_duration_seconds: float = 0.0


# -- Default runner ----------------------------------------------------------


async def _default_runner(step: SkillStep, context: str) -> str:
    """Mock runner that returns step description. Used when no runner_fn given."""
    return f"[mock] Completed: {step.task}"


# -- DAG Executor ------------------------------------------------------------


class DAGExecutor:
    """Executes a CompositionPlan by running steps in topological wave order.

    Each wave's steps run concurrently via asyncio.gather. Context from
    upstream artifacts is injected automatically. Failed steps cause all
    downstream dependents to be skipped.

    Args:
        composer: The SkillComposer that built (and tracks artifacts for) the plan.
        runner_fn: Async callable(step, context) -> output string.
                   Defaults to a mock that echoes the step description.
    """

    def __init__(
        self,
        composer: SkillComposer,
        runner_fn: RunnerFn | None = None,
    ) -> None:
        self._composer = composer
        self._runner_fn: RunnerFn = runner_fn or _default_runner

    # -- Public API ----------------------------------------------------------

    async def execute(
        self,
        plan: CompositionPlan,
        on_step_complete: Callable[[StepResult], Coroutine[Any, Any, Any]] | None = None,
    ) -> ExecutionResult:
        """Execute the plan wave by wave.

        For each wave:
        1. Get ready steps (skip any whose upstream failed).
        2. Build context for each step from upstream artifacts.
        3. Run all steps in the wave concurrently (asyncio.gather).
        4. Record artifacts from completed steps.
        5. Handle failures: mark downstream for skipping.
        6. Move to next wave.

        Args:
            plan: The composition plan to execute.
            on_step_complete: Optional async callback fired after each step.

        Returns:
            ExecutionResult with per-step detail and aggregate counts.
        """
        t0 = time.monotonic()
        plan.status = "running"

        waves = plan.execution_order()
        failed_ids: set[str] = set()
        results: list[StepResult] = []
        completed = 0
        failed = 0
        skipped = 0

        for wave in waves:
            # Partition wave into runnable vs. skipped
            runnable: list[SkillStep] = []
            for step in wave:
                if self._has_failed_ancestor(step, failed_ids):
                    sr = StepResult(
                        step_id=step.step_id,
                        skill_name=step.skill_name,
                        success=False,
                        error="Skipped: upstream dependency failed",
                    )
                    results.append(sr)
                    skipped += 1
                    failed_ids.add(step.step_id)
                    if on_step_complete:
                        await on_step_complete(sr)
                else:
                    runnable.append(step)

            if not runnable:
                continue

            # Run all runnable steps concurrently
            coros = [self._run_step(plan, step) for step in runnable]
            wave_results: list[StepResult] = await asyncio.gather(*coros)

            for sr in wave_results:
                results.append(sr)
                if sr.success:
                    completed += 1
                else:
                    failed += 1
                    failed_ids.add(sr.step_id)
                if on_step_complete:
                    await on_step_complete(sr)

        # Determine overall status
        total = completed + failed + skipped
        if total == 0:
            status = "completed"
        elif completed == total:
            status = "completed"
        elif completed == 0:
            status = "failed"
        else:
            status = "partial"

        plan.status = status

        return ExecutionResult(
            plan_task=plan.task,
            status=status,
            steps_completed=completed,
            steps_failed=failed,
            steps_skipped=skipped,
            step_results=results,
            total_duration_seconds=time.monotonic() - t0,
        )

    async def execute_step_only(
        self, plan: CompositionPlan, step_id: str
    ) -> StepResult:
        """Execute a single step by ID (useful for manual/debug runs).

        Args:
            plan: The composition plan containing the step.
            step_id: ID of the step to execute.

        Returns:
            StepResult for the executed step.

        Raises:
            ValueError: If step_id not found in the plan.
        """
        step = self._find_step(plan, step_id)
        return await self._run_step(plan, step)

    # -- Internal helpers ----------------------------------------------------

    async def _run_step(
        self, plan: CompositionPlan, step: SkillStep
    ) -> StepResult:
        """Run a single step with retry logic.

        1. Build context from upstream artifacts.
        2. Call runner_fn(step, context).
        3. On success: record artifact in the plan.
        4. On failure: retry up to step.retry times.

        Args:
            plan: The composition plan (for context and artifact recording).
            step: The step to run.

        Returns:
            StepResult capturing success/failure, output, timing, retries.
        """
        context = self._composer.get_context_for_step(plan, step)
        last_error = ""
        retries_used = 0
        max_attempts = 1 + step.retry

        for attempt in range(max_attempts):
            t0 = time.monotonic()
            try:
                output = await asyncio.wait_for(
                    self._runner_fn(step, context),
                    timeout=step.timeout,
                )
                duration = time.monotonic() - t0

                # Record artifact for downstream steps
                self._composer.record_artifact(
                    plan,
                    step_id=step.step_id,
                    artifact_type="output",
                    content=output,
                    metadata={"attempt": attempt + 1},
                )

                logger.info(
                    "Step %s completed in %.2fs (attempt %d/%d)",
                    step.step_id,
                    duration,
                    attempt + 1,
                    max_attempts,
                )

                return StepResult(
                    step_id=step.step_id,
                    skill_name=step.skill_name,
                    success=True,
                    output=output,
                    duration_seconds=duration,
                    retries_used=retries_used,
                )

            except asyncio.TimeoutError:
                duration = time.monotonic() - t0
                last_error = f"Timeout after {step.timeout}s"
                retries_used = attempt + 1
                logger.warning(
                    "Step %s timed out (attempt %d/%d)",
                    step.step_id,
                    attempt + 1,
                    max_attempts,
                )

            except Exception as exc:  # noqa: BLE001
                duration = time.monotonic() - t0
                last_error = str(exc)
                retries_used = attempt + 1
                logger.warning(
                    "Step %s failed: %s (attempt %d/%d)",
                    step.step_id,
                    last_error,
                    attempt + 1,
                    max_attempts,
                )

        # All attempts exhausted
        return StepResult(
            step_id=step.step_id,
            skill_name=step.skill_name,
            success=False,
            error=last_error,
            duration_seconds=duration,
            retries_used=retries_used,
        )

    def _has_failed_ancestor(
        self, step: SkillStep, failed_ids: set[str]
    ) -> bool:
        """Check if any direct dependency of this step has failed."""
        return bool(set(step.depends_on) & failed_ids)

    @staticmethod
    def _find_step(plan: CompositionPlan, step_id: str) -> SkillStep:
        """Look up a step by ID, raising ValueError if missing."""
        for step in plan.steps:
            if step.step_id == step_id:
                return step
        raise ValueError(f"Step '{step_id}' not found in plan")
