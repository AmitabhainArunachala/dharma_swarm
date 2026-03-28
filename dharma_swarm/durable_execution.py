"""Durable execution with crash-recovery checkpointing.

Every workflow step is checkpointed to disk. On restart, execution resumes
from the last successful checkpoint -- no duplicate work, no lost state.

Inspired by:
  - LangGraph: durable execution with state persistence at every node
  - OpenAI Codex: 4 persistent markdown files surviving 25-hour runs
  - Temporal/Durable Functions: deterministic replay from event log

Grounded in:
  - dharma_swarm continuity_harness.py: extends snapshot pattern
  - Varela (Pillar 7): autopoietic self-maintenance through state preservation
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_WORKFLOW_DIR = Path(
    os.getenv("DHARMA_WORKFLOW_DIR", str(Path.home() / ".dharma" / "workflows"))
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Step status
# ---------------------------------------------------------------------------


class StepStatus(str, Enum):
    """Lifecycle state for a single workflow step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# ---------------------------------------------------------------------------
# Workflow step
# ---------------------------------------------------------------------------


@dataclass
class WorkflowStep:
    """A single step in a durable workflow DAG."""

    step_id: str
    name: str
    status: StepStatus = StepStatus.PENDING
    started_at: str = ""
    completed_at: str = ""
    result: Any = None
    error: str | None = None
    depends_on: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowStep:
        data = dict(data)
        data["status"] = StepStatus(data["status"])
        return cls(**data)


# ---------------------------------------------------------------------------
# Durable workflow
# ---------------------------------------------------------------------------


class DurableWorkflow:
    """Crash-recoverable workflow state machine.

    Maintains a DAG of steps with dependency tracking. Every state mutation
    auto-checkpoints to disk so execution can resume from the last successful
    step after a crash or restart.
    """

    def __init__(
        self,
        workflow_id: str,
        persist_dir: Path | None = None,
    ) -> None:
        self.workflow_id = workflow_id
        self._persist_dir = persist_dir or DEFAULT_WORKFLOW_DIR / workflow_id
        self._steps: dict[str, WorkflowStep] = {}
        self._order: list[str] = []  # insertion order for deterministic iteration
        self._created_at: str = _utc_now_iso()

    # -- Step registration ---------------------------------------------------

    def add_step(
        self,
        step_id: str,
        name: str,
        depends_on: list[str] | None = None,
    ) -> WorkflowStep:
        """Register a new step in the workflow DAG.

        Args:
            step_id: Unique identifier for the step.
            name: Human-readable step name.
            depends_on: List of step_ids this step depends on.

        Returns:
            The newly created WorkflowStep.

        Raises:
            ValueError: If step_id already exists or a dependency is unknown.
        """
        if step_id in self._steps:
            raise ValueError(f"Step '{step_id}' already exists")
        deps = depends_on or []
        for dep in deps:
            if dep not in self._steps:
                raise ValueError(
                    f"Dependency '{dep}' not found. "
                    f"Known steps: {list(self._steps.keys())}"
                )
        step = WorkflowStep(step_id=step_id, name=name, depends_on=deps)
        self._steps[step_id] = step
        self._order.append(step_id)
        return step

    def get_step(self, step_id: str) -> WorkflowStep:
        """Return a step by ID.

        Raises:
            KeyError: If step_id is not found.
        """
        if step_id not in self._steps:
            raise KeyError(f"Step '{step_id}' not found")
        return self._steps[step_id]

    # -- Dependency queries --------------------------------------------------

    def ready_steps(self) -> list[WorkflowStep]:
        """Return steps whose dependencies are all COMPLETED and status is PENDING.

        These are the steps that can be executed next (potentially in parallel).
        """
        ready: list[WorkflowStep] = []
        for step_id in self._order:
            step = self._steps[step_id]
            if step.status != StepStatus.PENDING:
                continue
            deps_met = all(
                self._steps[dep].status == StepStatus.COMPLETED
                for dep in step.depends_on
            )
            if deps_met:
                ready.append(step)
        return ready

    # -- State transitions ---------------------------------------------------

    def mark_running(self, step_id: str) -> None:
        """Transition step to RUNNING and auto-checkpoint."""
        step = self.get_step(step_id)
        step.status = StepStatus.RUNNING
        step.started_at = _utc_now_iso()
        self.checkpoint()

    def mark_completed(self, step_id: str, result: Any = None) -> None:
        """Transition step to COMPLETED with optional result and auto-checkpoint."""
        step = self.get_step(step_id)
        step.status = StepStatus.COMPLETED
        step.completed_at = _utc_now_iso()
        step.result = result
        self.checkpoint()

    def mark_failed(self, step_id: str, error: str) -> None:
        """Transition step to FAILED with error message and auto-checkpoint.

        Dependents of a failed step will never become ready (their dependency
        will never reach COMPLETED).
        """
        step = self.get_step(step_id)
        step.status = StepStatus.FAILED
        step.completed_at = _utc_now_iso()
        step.error = error
        self.checkpoint()

    # -- Completion check ----------------------------------------------------

    def is_complete(self) -> bool:
        """Return True if all steps are in a terminal state (COMPLETED, FAILED, or SKIPPED)."""
        terminal = {StepStatus.COMPLETED, StepStatus.FAILED, StepStatus.SKIPPED}
        return all(s.status in terminal for s in self._steps.values())

    # -- Persistence ---------------------------------------------------------

    def checkpoint(self) -> Path:
        """Persist full workflow state to disk atomically.

        Uses tmp+rename for crash safety (same pattern as checkpoint.py).

        Returns:
            Path to the state file.
        """
        state = {
            "workflow_id": self.workflow_id,
            "created_at": self._created_at,
            "checkpointed_at": _utc_now_iso(),
            "steps": [self._steps[sid].to_dict() for sid in self._order],
        }

        target = self._persist_dir / "state.json"
        target.parent.mkdir(parents=True, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(
            dir=str(target.parent), suffix=".tmp", prefix=".dw_"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps(state, indent=2, default=str))
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, target)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        logger.debug("Checkpointed workflow %s to %s", self.workflow_id, target)
        return target

    @classmethod
    def restore(
        cls,
        workflow_id: str,
        persist_dir: Path | None = None,
    ) -> DurableWorkflow:
        """Restore a workflow from its on-disk checkpoint.

        Args:
            workflow_id: The workflow to restore.
            persist_dir: Override the persist directory. If None, uses the
                default location for the given workflow_id.

        Returns:
            A DurableWorkflow with all steps and statuses restored.

        Raises:
            FileNotFoundError: If no checkpoint exists.
            json.JSONDecodeError: If the checkpoint file is corrupt.
        """
        base = persist_dir or DEFAULT_WORKFLOW_DIR / workflow_id
        state_path = base / "state.json"

        if not state_path.exists():
            raise FileNotFoundError(
                f"No checkpoint found at {state_path}"
            )

        data = json.loads(state_path.read_text(encoding="utf-8"))
        wf = cls(workflow_id=data["workflow_id"], persist_dir=base)
        wf._created_at = data.get("created_at", wf._created_at)

        # Rebuild steps in order
        for step_data in data["steps"]:
            step = WorkflowStep.from_dict(step_data)
            wf._steps[step.step_id] = step
            wf._order.append(step.step_id)

        logger.info(
            "Restored workflow %s (%d steps) from %s",
            workflow_id,
            len(wf._steps),
            state_path,
        )
        return wf

    # -- Summary -------------------------------------------------------------

    def summary(self) -> dict[str, int]:
        """Return step counts grouped by status.

        Returns:
            Dict mapping status name to count, e.g.
            {"pending": 2, "completed": 3, "failed": 0, ...}
        """
        counts: dict[str, int] = {s.value: 0 for s in StepStatus}
        for step in self._steps.values():
            counts[step.status.value] += 1
        return counts

    @property
    def steps(self) -> list[WorkflowStep]:
        """Return all steps in insertion order."""
        return [self._steps[sid] for sid in self._order]
