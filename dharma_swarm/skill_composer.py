"""Skill Composer -- DAG-based skill composition for complex tasks.

Goes beyond simple parallel spawning: skills compose into dependency
graphs where the output of one step feeds as context into the next.
The natural flow is research -> build -> validate -> deploy, but
arbitrary DAGs are supported via explicit dependency declarations.

Topologically sorted into parallel "waves" for execution: steps
within a wave have no inter-dependencies and run concurrently.
"""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from dharma_swarm.intent_router import IntentRouter
    from dharma_swarm.skills import SkillRegistry

logger = logging.getLogger(__name__)

# Maximum steps per plan -- matches agent fleet size cap.
MAX_STEPS = 7

# Canonical phase ordering used by auto-compose.
_PHASE_KEYWORDS: dict[str, list[str]] = {
    "research": ["scan", "research", "analyze", "explore", "discover", "read", "map", "investigate"],
    "build": ["build", "implement", "create", "write", "code", "develop", "fix", "patch", "refactor"],
    "validate": ["test", "validate", "verify", "check", "assert", "qa"],
    "deploy": ["deploy", "ship", "release", "publish", "push"],
}

_PHASE_ORDER = ["research", "build", "validate", "deploy"]


# -- Models ---------------------------------------------------------------


class SkillStep(BaseModel):
    """A single step in a skill composition DAG."""

    skill_name: str
    task: str
    depends_on: list[str] = Field(default_factory=list)
    step_id: str = ""
    parallel_group: str = ""
    timeout: float = 300.0
    retry: int = 0


class HandoffArtifact(BaseModel):
    """Typed output from a skill step, passed to downstream steps."""

    step_id: str
    skill_name: str
    artifact_type: str  # code_diff, analysis, test_results, context, plan
    content: str
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CompositionPlan(BaseModel):
    """A full DAG of skill steps for a complex task."""

    task: str
    steps: list[SkillStep] = Field(default_factory=list)
    artifacts: dict[str, HandoffArtifact] = Field(default_factory=dict)
    status: str = "pending"

    # -- DAG queries -------------------------------------------------------

    def execution_order(self) -> list[list[SkillStep]]:
        """Topological sort into parallel waves.

        Returns a list of waves. Each wave contains steps whose
        dependencies are fully satisfied by prior waves.

        Raises:
            ValueError: If the dependency graph contains a cycle.
        """
        step_map: dict[str, SkillStep] = {s.step_id: s for s in self.steps}
        in_degree: dict[str, int] = {s.step_id: 0 for s in self.steps}
        children: dict[str, list[str]] = defaultdict(list)

        for step in self.steps:
            for dep in step.depends_on:
                if dep in step_map:
                    in_degree[step.step_id] += 1
                    children[dep].append(step.step_id)

        waves: list[list[SkillStep]] = []
        remaining = set(in_degree.keys())

        while remaining:
            # Collect all nodes with in-degree 0
            wave_ids = [sid for sid in remaining if in_degree[sid] == 0]
            if not wave_ids:
                raise ValueError(
                    "Circular dependency detected among steps: "
                    + ", ".join(sorted(remaining))
                )
            wave = [step_map[sid] for sid in sorted(wave_ids)]
            waves.append(wave)

            for sid in wave_ids:
                remaining.discard(sid)
                for child in children[sid]:
                    in_degree[child] -= 1

        return waves

    def ready_steps(self) -> list[SkillStep]:
        """Steps whose dependencies are all satisfied (have artifacts)."""
        completed = set(self.artifacts.keys())
        ready: list[SkillStep] = []
        for step in self.steps:
            if step.step_id in completed:
                continue  # already done
            if all(dep in completed for dep in step.depends_on):
                ready.append(step)
        return ready


# -- Composer --------------------------------------------------------------


def _classify_phase(task_lower: str) -> str:
    """Classify a task fragment into a canonical phase."""
    for phase in _PHASE_ORDER:
        keywords = _PHASE_KEYWORDS[phase]
        if any(kw in task_lower for kw in keywords):
            return phase
    return "build"  # default


def _make_step_id(skill_name: str, index: int) -> str:
    """Generate a deterministic step id."""
    return f"{skill_name}-{index}"


class SkillComposer:
    """Composes skills into execution DAGs.

    Uses the IntentRouter for task decomposition and the SkillRegistry
    for skill lookup, then wires dependencies based on canonical phase
    ordering: research -> build -> validate -> deploy.
    """

    def __init__(
        self,
        registry: SkillRegistry | None = None,
        router: IntentRouter | None = None,
    ):
        self._registry = registry
        self._router = router

    def compose(self, task: str) -> CompositionPlan:
        """Build a composition plan from a task description.

        Uses the IntentRouter to decompose, then builds dependency graph
        following the natural flow:
          - research/scan steps have no dependencies
          - build/implement steps depend on research results
          - validate/test steps depend on build steps
          - deploy steps depend on validate steps

        Args:
            task: Natural language task description.

        Returns:
            A CompositionPlan with topologically ordered steps.

        Raises:
            ValueError: If task is empty or produces too many steps.
        """
        if not task or not task.strip():
            raise ValueError("Task description must not be empty")

        # Decompose via router if available, else split naively
        if self._router:
            decomposed = self._router.decompose(task)
            sub_tasks = [(st.primary_skill or "builder", st.task) for st in decomposed.sub_tasks]
        else:
            sub_tasks = [("builder", task)]

        # Enforce ceiling
        if len(sub_tasks) > MAX_STEPS:
            sub_tasks = sub_tasks[:MAX_STEPS]

        # Classify each sub-task into a phase and build steps
        phase_steps: dict[str, list[SkillStep]] = defaultdict(list)
        all_steps: list[SkillStep] = []
        idx = 0

        for skill_name, sub_task in sub_tasks:
            phase = _classify_phase(sub_task.lower())
            step = SkillStep(
                skill_name=skill_name,
                task=sub_task,
                step_id=_make_step_id(skill_name, idx),
                parallel_group=phase,
                timeout=300.0,
            )
            phase_steps[phase].append(step)
            all_steps.append(step)
            idx += 1

        # Wire dependencies: each phase depends on all steps of the prior phase
        for i, phase in enumerate(_PHASE_ORDER):
            if phase not in phase_steps:
                continue
            # Find the most recent prior phase that has steps
            for j in range(i - 1, -1, -1):
                prior_phase = _PHASE_ORDER[j]
                if prior_phase in phase_steps:
                    prior_ids = [s.step_id for s in phase_steps[prior_phase]]
                    for step in phase_steps[phase]:
                        step.depends_on = list(prior_ids)
                    break

        return CompositionPlan(task=task, steps=all_steps, status="pending")

    def compose_from_steps(
        self, task: str, steps: list[dict]
    ) -> CompositionPlan:
        """Build a plan from explicitly provided step dicts.

        Each dict should have at minimum 'skill_name' and 'task'.
        Optional: 'depends_on', 'step_id', 'parallel_group', 'timeout', 'retry'.

        Args:
            task: Overall task description.
            steps: List of step specification dicts.

        Returns:
            A CompositionPlan with the given steps.

        Raises:
            ValueError: If too many steps or task is empty.
        """
        if not task or not task.strip():
            raise ValueError("Task description must not be empty")
        if len(steps) > MAX_STEPS:
            raise ValueError(
                f"Plan exceeds maximum of {MAX_STEPS} steps (got {len(steps)})"
            )

        skill_steps: list[SkillStep] = []
        for i, spec in enumerate(steps):
            step_id = spec.get("step_id") or _make_step_id(
                spec.get("skill_name", "step"), i
            )
            skill_steps.append(
                SkillStep(
                    skill_name=spec.get("skill_name", "builder"),
                    task=spec.get("task", ""),
                    depends_on=spec.get("depends_on", []),
                    step_id=step_id,
                    parallel_group=spec.get("parallel_group", ""),
                    timeout=spec.get("timeout", 300.0),
                    retry=spec.get("retry", 0),
                )
            )

        return CompositionPlan(task=task, steps=skill_steps, status="pending")

    def record_artifact(
        self,
        plan: CompositionPlan,
        step_id: str,
        artifact_type: str,
        content: str,
        metadata: dict | None = None,
    ) -> HandoffArtifact:
        """Record output from a completed step.

        Args:
            plan: The composition plan to update.
            step_id: ID of the step that produced this artifact.
            artifact_type: One of code_diff, analysis, test_results, context, plan.
            content: The artifact content.
            metadata: Optional metadata dict.

        Returns:
            The created HandoffArtifact.

        Raises:
            ValueError: If step_id is not found in the plan.
        """
        step_ids = {s.step_id for s in plan.steps}
        if step_id not in step_ids:
            raise ValueError(f"Step '{step_id}' not found in plan")

        # Find the skill_name for this step
        skill_name = ""
        for step in plan.steps:
            if step.step_id == step_id:
                skill_name = step.skill_name
                break

        artifact = HandoffArtifact(
            step_id=step_id,
            skill_name=skill_name,
            artifact_type=artifact_type,
            content=content,
            metadata=metadata or {},
        )
        plan.artifacts[step_id] = artifact

        # Update plan status if all steps have artifacts
        if len(plan.artifacts) == len(plan.steps):
            plan.status = "completed"
        elif plan.status == "pending":
            plan.status = "running"

        return artifact

    def get_context_for_step(
        self, plan: CompositionPlan, step: SkillStep
    ) -> str:
        """Build context for a step from upstream artifacts.

        Assembles all artifacts from steps this step depends on into a
        single context string suitable for injection into the agent's
        system prompt.

        Args:
            plan: The composition plan.
            step: The step that needs context.

        Returns:
            Assembled context string, empty if no upstream artifacts.
        """
        if not step.depends_on:
            return ""

        sections: list[str] = []
        for dep_id in step.depends_on:
            artifact = plan.artifacts.get(dep_id)
            if artifact is None:
                continue
            header = f"[{artifact.artifact_type}] from {artifact.skill_name} ({dep_id})"
            sections.append(f"--- {header} ---\n{artifact.content}")

        return "\n\n".join(sections)
