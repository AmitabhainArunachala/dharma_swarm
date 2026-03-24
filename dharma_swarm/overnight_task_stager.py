"""Overnight Task Stager -- bounded, verifiable task queue for overnight loops.

Compiles tasks from multiple sources:
  1. Test coverage gaps (pytest analysis)
  2. Human-curated queue (~/.dharma/overnight/queue.yaml)
  3. Trajectory-informed priorities (historical success/failure data)

Each task has:
  - A clear goal
  - An acceptance criterion (mechanical pass/fail)
  - A time budget
  - A max token budget

Inspired by: Karpathy AutoResearch (time-boxed experiments),
Atlas Bayesian Optimization (acquisition function for task selection).

This module is pure Python analysis -- no LLM calls.
"""

from __future__ import annotations

import json
import logging
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml

    _YAML_AVAILABLE = True
except ImportError:  # pragma: no cover
    _YAML_AVAILABLE = False

logger = logging.getLogger(__name__)

STATE_DIR = Path.home() / ".dharma"
OVERNIGHT_DIR = STATE_DIR / "overnight"
DHARMA_SWARM_ROOT = Path.home() / "dharma_swarm"

# Valid task types
TASK_TYPES = frozenset(
    {"test_coverage", "claim_verification", "benchmark", "refactor_proposal", "custom"}
)

# Valid status values
STATUSES = frozenset({"pending", "in_progress", "completed", "failed", "dead_cycle"})


@dataclass
class OvernightTask:
    """A bounded, verifiable task for the overnight loop."""

    task_id: str
    goal: str  # One-sentence description
    task_type: str  # One of TASK_TYPES
    acceptance_criterion: str  # Human-readable description of pass/fail
    timeout_seconds: float = 900.0  # 15 minutes default
    max_tokens: int = 50_000
    priority: float = 0.0  # Higher = run first
    status: str = "pending"
    result: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return asdict(self)


class OvernightTaskStager:
    """Compiles and manages the overnight task queue.

    Scans multiple task sources, ranks them by priority, persists
    a JSONL queue to disk, and provides pull-based task consumption.
    """

    def __init__(
        self,
        date: str | None = None,
        state_dir: Path | None = None,
        dharma_root: Path | None = None,
    ) -> None:
        self.date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.state_dir = state_dir or STATE_DIR
        self.dharma_root = dharma_root or DHARMA_SWARM_ROOT
        self.overnight_dir = self.state_dir / "overnight" / self.date
        self.overnight_dir.mkdir(parents=True, exist_ok=True)
        self.queue_path = self.overnight_dir / "task_queue.jsonl"
        self._tasks: list[OvernightTask] = []
        self._task_index: dict[str, OvernightTask] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compile_queue(self) -> list[OvernightTask]:
        """Scan all task sources, rank, persist queue.

        Returns:
            Ordered list of tasks (highest priority first).
        """
        self._tasks = []
        self._scan_test_coverage_gaps()
        self._scan_human_curated_queue()
        self._scan_loop_templates()
        self._apply_trajectory_insights()
        self._rank_tasks()
        self._persist_queue()
        self._task_index = {t.task_id: t for t in self._tasks}
        return list(self._tasks)

    def has_tasks(self) -> bool:
        """Any pending tasks remaining?"""
        return any(t.status == "pending" for t in self._tasks)

    def next_task(self) -> OvernightTask | None:
        """Pull the highest-priority pending task.

        Marks it in_progress and records start time.
        Returns None when the queue is exhausted.
        """
        for task in self._tasks:
            if task.status == "pending":
                task.status = "in_progress"
                task.started_at = time.time()
                self._update_on_disk(task)
                return task
        return None

    def record_result(self, task_id: str, status: str, result: str = "") -> None:
        """Mark a task completed/failed/dead_cycle.

        Args:
            task_id: The task to update.
            status: Terminal status (completed, failed, dead_cycle).
            result: Human-readable result description.
        """
        task = self._task_index.get(task_id)
        if task is None:
            return
        task.status = status
        task.result = result
        task.completed_at = time.time()
        self._update_on_disk(task)

    def stats(self) -> dict[str, int]:
        """Summary counts by status."""
        counts = Counter(t.status for t in self._tasks)
        return {
            "total": len(self._tasks),
            "pending": counts.get("pending", 0),
            "in_progress": counts.get("in_progress", 0),
            "completed": counts.get("completed", 0),
            "failed": counts.get("failed", 0),
            "dead_cycle": counts.get("dead_cycle", 0),
        }

    # ------------------------------------------------------------------
    # Task source scanners
    # ------------------------------------------------------------------

    def _scan_test_coverage_gaps(self) -> None:
        """Find modules with no corresponding test file.

        For each ``dharma_swarm/*.py`` without a matching
        ``tests/test_*.py``, creates a task to write basic smoke tests.
        Priority scales with module line count (larger = higher priority,
        capped at 10.0).
        """
        src_dir = self.dharma_root / "dharma_swarm"
        test_dir = self.dharma_root / "tests"
        if not src_dir.exists():
            return
        for src_file in sorted(src_dir.glob("*.py")):
            if src_file.name.startswith("_"):
                continue
            module_name = src_file.stem
            test_file = test_dir / f"test_{module_name}.py"
            if not test_file.exists():
                try:
                    line_count = len(src_file.read_text().splitlines())
                except Exception:
                    line_count = 0
                self._tasks.append(
                    OvernightTask(
                        task_id=f"test_coverage_{module_name}",
                        goal=(
                            f"Write basic smoke tests for {module_name}.py "
                            f"({line_count} lines, no existing tests)"
                        ),
                        task_type="test_coverage",
                        acceptance_criterion=(
                            f"tests/test_{module_name}.py exists and "
                            f"pytest tests/test_{module_name}.py passes"
                        ),
                        timeout_seconds=900.0,
                        priority=min(line_count / 100.0, 10.0),
                        metadata={
                            "module": module_name,
                            "line_count": line_count,
                            "src_path": str(src_file),
                        },
                    )
                )

    def _scan_human_curated_queue(self) -> None:
        """Read human-curated tasks from ``queue.yaml``.

        Expected format::

            - id: my_task
              goal: "Do the thing"
              type: custom
              acceptance: "The thing is done"
              timeout: 600
              max_tokens: 30000
              priority: 8.0
              metadata: {}
        """
        if not _YAML_AVAILABLE:
            logger.debug("PyYAML not installed; skipping queue.yaml scan")
            return
        queue_file = self.state_dir / "overnight" / "queue.yaml"
        if not queue_file.exists():
            return
        try:
            data = yaml.safe_load(queue_file.read_text())
            if not isinstance(data, list):
                logger.warning("queue.yaml is not a list; skipping")
                return
            for item in data:
                if not isinstance(item, dict) or "goal" not in item:
                    continue
                self._tasks.append(
                    OvernightTask(
                        task_id=item.get(
                            "id",
                            f"custom_{int(time.time())}_{len(self._tasks)}",
                        ),
                        goal=item["goal"],
                        task_type=item.get("type", "custom"),
                        acceptance_criterion=item.get(
                            "acceptance", "Manual review required"
                        ),
                        timeout_seconds=float(item.get("timeout", 900)),
                        max_tokens=int(item.get("max_tokens", 50_000)),
                        priority=float(item.get("priority", 5.0)),
                        metadata=item.get("metadata", {}),
                    )
                )
        except Exception as e:
            logger.warning("Failed to read queue.yaml: %s", e)

    def _scan_loop_templates(self) -> None:
        """Discover loop template scripts and create benchmark tasks.

        Scans ``tools/loop_templates/`` for .py files (excluding __init__.py
        and progress_protocol.py).  Each becomes a benchmark task that the
        overnight director runs to convergence.
        """
        templates_dir = self.dharma_root / "tools" / "loop_templates"
        if not templates_dir.exists():
            return
        skip = {"__init__.py", "progress_protocol.py"}
        for template_file in sorted(templates_dir.glob("*.py")):
            if template_file.name in skip:
                continue
            template_name = template_file.stem
            self._tasks.append(
                OvernightTask(
                    task_id=f"benchmark_{template_name}",
                    goal=f"Run {template_name} loop template to convergence",
                    task_type="benchmark",
                    acceptance_criterion=f"{template_name} convergence metric improved from baseline",
                    timeout_seconds=600.0,
                    priority=3.0,  # Lower than test coverage gaps
                    metadata={
                        "template_name": template_name,
                        "template_path": str(template_file),
                    },
                )
            )

    def _apply_trajectory_insights(self) -> None:
        """Adjust task priorities based on historical trajectory data.

        Reads ~/.dharma/trajectories/trajectories.jsonl and learns:
        - Which task types have high success rates (boost priority)
        - Which task types repeatedly fail (reduce priority / add feasibility penalty)

        This is the Atlas-inspired feasibility classifier: learn from failures
        to steer away from predicted failure regions.
        """
        traj_path = self.state_dir / "trajectories" / "trajectories.jsonl"
        if not traj_path.exists():
            return

        # Gather success/failure counts by task_title prefix
        success_counts: dict[str, int] = {}
        failure_counts: dict[str, int] = {}
        try:
            with open(traj_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        traj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    title = traj.get("task_title", "")
                    outcome = traj.get("outcome", {})
                    # Normalize title to a type key (first 2 words)
                    type_key = "_".join(title.lower().split()[:2]) if title else "unknown"
                    if outcome.get("success", False):
                        success_counts[type_key] = success_counts.get(type_key, 0) + 1
                    else:
                        failure_counts[type_key] = failure_counts.get(type_key, 0) + 1
        except Exception as e:
            logger.warning("Failed to read trajectory data: %s", e)
            return

        if not success_counts and not failure_counts:
            return

        # Adjust task priorities based on historical patterns
        for task in self._tasks:
            type_key = "_".join(task.goal.lower().split()[:2]) if task.goal else "unknown"
            successes = success_counts.get(type_key, 0)
            failures = failure_counts.get(type_key, 0)
            total = successes + failures
            if total > 0:
                success_rate = successes / total
                # Boost high-success types, penalize high-failure types
                if success_rate > 0.7:
                    task.priority *= 1.2
                elif success_rate < 0.3 and total >= 3:
                    task.priority *= 0.5  # Feasibility penalty
                task.metadata["trajectory_success_rate"] = round(success_rate, 2)
                task.metadata["trajectory_total"] = total

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rank_tasks(self) -> None:
        """Sort tasks by UCB acquisition score (priority + exploration bonus).

        UCB1 formula: score = mean_success_rate + c * sqrt(ln(N) / n_i)
        where N = total historical attempts, n_i = attempts for this task type.
        Falls back to raw priority when no history exists.

        Inspired by: Atlas Bayesian Optimization acquisition functions,
        AlphaEvolve island-based diversity maintenance.
        """
        import math

        # Load historical attempt counts from trajectory insights
        total_attempts = 0
        type_attempts: dict[str, int] = {}
        type_successes: dict[str, int] = {}

        for task in self._tasks:
            total_hist = task.metadata.get("trajectory_total", 0)
            if total_hist > 0:
                type_key = task.task_type
                type_attempts[type_key] = type_attempts.get(type_key, 0) + total_hist
                sr = task.metadata.get("trajectory_success_rate", 0.5)
                type_successes[type_key] = type_successes.get(type_key, 0) + int(sr * total_hist)
                total_attempts += total_hist

        exploration_constant = 1.41  # sqrt(2), standard UCB1

        for task in self._tasks:
            base_priority = task.priority
            n_i = type_attempts.get(task.task_type, 0)

            if total_attempts > 0 and n_i > 0:
                mean_success = type_successes.get(task.task_type, 0) / n_i
                exploration_bonus = exploration_constant * math.sqrt(
                    math.log(total_attempts) / n_i
                )
                ucb_score = mean_success + exploration_bonus
                # Blend UCB with base priority (UCB for exploration, priority for domain knowledge)
                task.priority = base_priority * 0.5 + ucb_score * 5.0
            # else: keep base_priority (cold start — no history)

        self._tasks.sort(key=lambda t: t.priority, reverse=True)

    def _persist_queue(self) -> None:
        """Write task queue to JSONL on disk."""
        try:
            with open(self.queue_path, "w") as f:
                for task in self._tasks:
                    f.write(json.dumps(task.to_dict(), ensure_ascii=True) + "\n")
        except Exception as e:
            logger.warning("Failed to persist task queue: %s", e)

    def _update_on_disk(self, task: OvernightTask) -> None:
        """Rewrite queue file with updated statuses."""
        try:
            self._persist_queue()
        except Exception:
            pass
