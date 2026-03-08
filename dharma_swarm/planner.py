"""Planner module -- plan-before-execute enforcement.

Implements the Manus/Devin/Traycer pattern: planning and execution are
separated. The planner generates structured task plans; executors receive
plans and follow them. Planners are read-only — they cannot write code.

The EvolutionPlan model already exists in evolution.py. This module adds
the general-purpose TaskPlan for non-evolution work.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from dharma_swarm.models import Task, _new_id, _utc_now

logger = logging.getLogger(__name__)


class PlanStep(BaseModel):
    """A single step in a task plan."""

    index: int
    description: str
    files_to_read: list[str] = Field(default_factory=list)
    files_to_modify: list[str] = Field(default_factory=list)
    verification: str = ""
    status: str = "pending"  # pending, in_progress, completed, skipped


class TaskPlan(BaseModel):
    """Structured plan for a task, generated before execution.

    This is the Manus/Kiro pattern: plans are explicit, numbered,
    and injected into executor context. Plans can be validated
    before execution begins.
    """

    id: str = Field(default_factory=_new_id)
    task_id: str = ""
    task_title: str = ""
    summary: str = ""
    steps: list[PlanStep] = Field(default_factory=list)
    think_notes: str = ""
    complexity_rating: int = Field(default=1, ge=1, le=10)
    created_at: str = Field(default_factory=lambda: _utc_now().isoformat())
    planner_agent: str = "task_planner"


class Planner:
    """Task planner that generates structured plans before execution.

    The planner is intentionally limited: it reads files and generates plans
    but never writes code. This is the Traycer read-only pattern.

    Usage:
        planner = Planner()
        plan = planner.create_plan(task)
        # Validate plan, then pass to executor
        context = planner.format_plan_for_injection(plan)
        # Inject context into executor's system prompt
    """

    def create_plan(
        self,
        task: Task,
        files_to_read: list[str] | None = None,
        files_to_modify: list[str] | None = None,
        think_notes: str = "",
    ) -> TaskPlan:
        """Create a structured plan for a task.

        This is a lightweight plan creation — no LLM call. For LLM-generated
        plans, use create_plan_with_provider().

        Args:
            task: The task to plan for.
            files_to_read: Files the executor should read before starting.
            files_to_modify: Files the executor is expected to modify.
            think_notes: Planner's reasoning about the approach.

        Returns:
            A TaskPlan ready for validation and injection.
        """
        steps: list[PlanStep] = []

        # Step 1: Always read relevant files first (v0/Devin read-before-write)
        if files_to_read:
            steps.append(PlanStep(
                index=1,
                description="Read relevant files to understand current state",
                files_to_read=list(files_to_read),
                verification="Confirm understanding of existing code structure",
            ))

        # Step 2: Implementation steps (one per file to modify)
        if files_to_modify:
            for i, filepath in enumerate(files_to_modify, start=len(steps) + 1):
                steps.append(PlanStep(
                    index=i,
                    description=f"Modify {filepath} according to task requirements",
                    files_to_read=[filepath],
                    files_to_modify=[filepath],
                    verification=f"Verify {filepath} changes are correct",
                ))

        # Step 3: Verification
        steps.append(PlanStep(
            index=len(steps) + 1,
            description="Run tests and verify all changes",
            verification="All tests pass, no regressions",
        ))

        # Complexity rating heuristic
        n_files = len(files_to_modify or [])
        complexity = min(max(n_files, 1), 10)

        plan = TaskPlan(
            task_id=task.id,
            task_title=task.title,
            summary=f"Plan for: {task.title}",
            steps=steps,
            think_notes=think_notes or f"Planning task: {task.title}",
            complexity_rating=complexity,
        )

        logger.info(
            "Created plan %s for task %s: %d steps, complexity=%d",
            plan.id, task.id, len(steps), complexity,
        )
        return plan

    async def create_plan_with_provider(
        self,
        task: Task,
        provider: Any,
        context: str = "",
    ) -> TaskPlan:
        """Generate an LLM-powered plan for a task.

        The provider is used in read-only mode (generates text, never writes files).

        Args:
            task: The task to plan for.
            provider: LLM provider (must have async complete() method).
            context: Additional context to include in the planning prompt.

        Returns:
            A TaskPlan with LLM-generated steps.
        """
        from dharma_swarm.models import LLMRequest

        prompt = (
            f"You are a PLANNER. You create plans but NEVER write code.\n"
            f"Task: {task.title}\n"
            f"Description: {task.description}\n"
            f"\n{context}\n\n"
            f"Generate a numbered plan with steps. For each step:\n"
            f"1. What to do (one sentence)\n"
            f"2. What files to read first\n"
            f"3. What files to modify\n"
            f"4. How to verify the step succeeded\n"
            f"\nRate complexity 1-10.\n"
            f"Think carefully about risks and alternatives."
        )

        request = LLMRequest(
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": prompt}],
            system="You are a planning agent. Generate structured plans. Never write code.",
            max_tokens=2000,
            temperature=0.3,
        )

        response = await provider.complete(request)

        # Parse response into plan (simplified -- real parsing would be more robust)
        plan = TaskPlan(
            task_id=task.id,
            task_title=task.title,
            summary=response.content[:200],
            think_notes=response.content,
            planner_agent="llm_planner",
        )

        logger.info("LLM plan %s created for task %s", plan.id, task.id)
        return plan

    @staticmethod
    def format_plan_for_injection(plan: TaskPlan) -> str:
        """Format a plan as text for injection into an executor's context.

        This is the Manus pattern: plans are injected as events into the
        agent's context stream.

        Args:
            plan: The plan to format.

        Returns:
            Formatted plan string ready for system prompt injection.
        """
        lines = [
            f"## EXECUTION PLAN (plan_id={plan.id})",
            f"Task: {plan.task_title}",
            f"Complexity: {plan.complexity_rating}/10",
            f"Summary: {plan.summary}",
            "",
            "### Steps:",
        ]

        for step in plan.steps:
            status_mark = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]", "skipped": "[-]"}.get(step.status, "[ ]")
            lines.append(f"{status_mark} {step.index}. {step.description}")
            if step.files_to_read:
                lines.append(f"     Read: {', '.join(step.files_to_read)}")
            if step.files_to_modify:
                lines.append(f"     Modify: {', '.join(step.files_to_modify)}")
            if step.verification:
                lines.append(f"     Verify: {step.verification}")

        lines.append("")
        lines.append(f"Planner notes: {plan.think_notes[:500]}")
        lines.append("")
        lines.append(
            "IMPORTANT: Follow this plan step by step. "
            "Do not skip steps. Do not add steps not in the plan. "
            "If you encounter a problem, note it and continue."
        )

        return "\n".join(lines)

    @staticmethod
    def update_step_status(
        plan: TaskPlan, step_index: int, status: str
    ) -> TaskPlan:
        """Update the status of a specific plan step.

        Args:
            plan: The plan to update.
            step_index: 1-based index of the step.
            status: New status (pending, in_progress, completed, skipped).

        Returns:
            The updated plan.
        """
        for step in plan.steps:
            if step.index == step_index:
                step.status = status
                break
        return plan
