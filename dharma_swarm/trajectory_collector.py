"""Trajectory collection for dharma_swarm agents.

Captures full agent trajectories (prompt → LLM response → outcome) at
IPA-like chunk boundaries (each tool call or task completion). These
trajectories feed the self-improving loop: scored by ThinkodynamicScorer,
top trajectories reinforce strategies, and eventually train the system's
own model.

Inspired by Alibaba ALE's ROLL component (arXiv:2512.24873) but governed
by thinkodynamic fitness rather than sparse terminal reward.

Storage: ~/.dharma/trajectories/ as JSONL, one line per completed trajectory.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_TRAJECTORY_DIR = Path.home() / ".dharma" / "trajectories"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class TrajectoryChunk(BaseModel):
    """One semantic interaction chunk — everything up to an LLM response.

    Analogous to IPA's chunk-level MDP: each chunk is an atomic RL action.
    """

    chunk_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    agent_id: str = ""
    task_id: str = ""
    timestamp: float = Field(default_factory=time.time)
    prompt: str = ""
    response: str = ""
    model: str = ""
    provider: str = ""
    tokens_used: int = 0
    latency_ms: float = 0.0
    gate_result: str = ""  # "pass" | "block" | "reroute"
    metadata: dict[str, Any] = Field(default_factory=dict)


class TrajectoryOutcome(BaseModel):
    """Outcome of a completed trajectory."""

    success: bool = False
    result_preview: str = ""
    error: str = ""
    fitness_score: Optional[dict[str, float]] = None
    thinkodynamic_score: Optional[dict[str, float]] = None
    gates_passed: list[str] = Field(default_factory=list)
    gates_failed: list[str] = Field(default_factory=list)


class Trajectory(BaseModel):
    """Full agent task trajectory — sequence of chunks + outcome.

    This is the unit of training data for the generational model pipeline.
    Each trajectory represents one complete task execution.
    """

    trajectory_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    agent_id: str = ""
    task_id: str = ""
    task_title: str = ""
    started_at: float = Field(default_factory=time.time)
    completed_at: float = 0.0
    chunks: list[TrajectoryChunk] = Field(default_factory=list)
    outcome: TrajectoryOutcome = Field(default_factory=TrajectoryOutcome)
    total_tokens: int = 0
    total_latency_ms: float = 0.0
    config_snapshot: dict[str, Any] = Field(default_factory=dict)

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    @property
    def duration_seconds(self) -> float:
        if self.completed_at and self.started_at:
            return self.completed_at - self.started_at
        return 0.0


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------


class TrajectoryCollector:
    """Collects agent trajectories and persists them for training.

    Usage:
        collector = TrajectoryCollector()

        # Start a trajectory when agent begins a task
        traj = collector.start_trajectory(agent_id="agent-1", task_id="task-1", task_title="Fix bug")

        # Record each chunk (prompt → response)
        collector.add_chunk(traj.trajectory_id, TrajectoryChunk(
            agent_id="agent-1", task_id="task-1",
            prompt="Fix the auth bug", response="I'll update the middleware...",
            model="claude-opus-4-6", provider="anthropic",
            tokens_used=1500, latency_ms=2340.0,
        ))

        # Complete the trajectory with outcome
        collector.complete_trajectory(traj.trajectory_id, TrajectoryOutcome(
            success=True,
            result_preview="Fixed auth middleware...",
            fitness_score={"correctness": 1.0, "elegance": 0.8},
        ))

    Trajectories are persisted to ~/.dharma/trajectories/ as JSONL.
    """

    def __init__(self, output_dir: Optional[Path] = None) -> None:
        self._output_dir = output_dir or _TRAJECTORY_DIR
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._active: dict[str, Trajectory] = {}
        self._completed_count: int = 0
        self._output_file = self._output_dir / "trajectories.jsonl"

    @property
    def active_count(self) -> int:
        return len(self._active)

    @property
    def completed_count(self) -> int:
        return self._completed_count

    def start_trajectory(
        self,
        agent_id: str,
        task_id: str,
        task_title: str = "",
        config_snapshot: Optional[dict[str, Any]] = None,
    ) -> Trajectory:
        """Begin collecting a new trajectory."""
        traj = Trajectory(
            agent_id=agent_id,
            task_id=task_id,
            task_title=task_title,
            config_snapshot=config_snapshot or {},
        )
        self._active[traj.trajectory_id] = traj
        logger.debug(
            "Trajectory %s started (agent=%s, task=%s)",
            traj.trajectory_id, agent_id, task_id,
        )
        return traj

    def add_chunk(self, trajectory_id: str, chunk: TrajectoryChunk) -> None:
        """Add a chunk to an active trajectory."""
        traj = self._active.get(trajectory_id)
        if traj is None:
            logger.warning("Cannot add chunk to unknown trajectory %s", trajectory_id)
            return
        traj.chunks.append(chunk)
        traj.total_tokens += chunk.tokens_used
        traj.total_latency_ms += chunk.latency_ms

    def complete_trajectory(
        self,
        trajectory_id: str,
        outcome: TrajectoryOutcome,
    ) -> Optional[Trajectory]:
        """Complete a trajectory, persist it, and remove from active set."""
        traj = self._active.pop(trajectory_id, None)
        if traj is None:
            logger.warning("Cannot complete unknown trajectory %s", trajectory_id)
            return None

        traj.completed_at = time.time()
        traj.outcome = outcome
        self._completed_count += 1
        self._persist(traj)

        logger.info(
            "Trajectory %s completed (agent=%s, chunks=%d, tokens=%d, success=%s)",
            traj.trajectory_id,
            traj.agent_id,
            traj.chunk_count,
            traj.total_tokens,
            outcome.success,
        )
        return traj

    def abandon_trajectory(self, trajectory_id: str) -> None:
        """Remove an active trajectory without persisting (e.g., on agent crash)."""
        traj = self._active.pop(trajectory_id, None)
        if traj:
            logger.debug("Trajectory %s abandoned", trajectory_id)

    def get_active(self, trajectory_id: str) -> Optional[Trajectory]:
        """Get an active trajectory by ID."""
        return self._active.get(trajectory_id)

    def _persist(self, traj: Trajectory) -> None:
        """Append completed trajectory to JSONL file."""
        try:
            with open(self._output_file, "a") as f:
                f.write(traj.model_dump_json() + "\n")
        except OSError:
            logger.warning("Failed to persist trajectory %s", traj.trajectory_id, exc_info=True)

    # -- Bulk operations ---------------------------------------------------

    def load_trajectories(
        self,
        min_fitness: Optional[float] = None,
        success_only: bool = False,
        limit: int = 0,
    ) -> list[Trajectory]:
        """Load persisted trajectories with optional filtering.

        Args:
            min_fitness: Minimum weighted fitness score to include.
            success_only: Only include successful trajectories.
            limit: Maximum number to return (0 = no limit).

        Returns:
            List of trajectories matching the criteria.
        """
        results: list[Trajectory] = []
        if not self._output_file.exists():
            return results

        with open(self._output_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    traj = Trajectory.model_validate_json(line)
                except Exception:
                    continue

                if success_only and not traj.outcome.success:
                    continue
                if min_fitness is not None and traj.outcome.fitness_score:
                    # Use weighted_fitness if available, else average
                    scores = traj.outcome.fitness_score
                    avg = sum(scores.values()) / max(len(scores), 1)
                    if avg < min_fitness:
                        continue
                results.append(traj)
                if limit and len(results) >= limit:
                    break

        return results

    def stats(self) -> dict[str, Any]:
        """Return summary statistics."""
        return {
            "active_trajectories": self.active_count,
            "completed_trajectories": self.completed_count,
            "output_file": str(self._output_file),
            "output_exists": self._output_file.exists(),
            "output_size_bytes": self._output_file.stat().st_size if self._output_file.exists() else 0,
        }


# ---------------------------------------------------------------------------
# Global collector instance
# ---------------------------------------------------------------------------

_global_collector: Optional[TrajectoryCollector] = None


def get_collector() -> TrajectoryCollector:
    """Get or create the global trajectory collector."""
    global _global_collector
    if _global_collector is None:
        _global_collector = TrajectoryCollector()
    return _global_collector
