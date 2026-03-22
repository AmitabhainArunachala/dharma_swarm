"""Population Control -- caps, culling, apoptosis, probation.

Enforces population bounds on the agent ecosystem. Mirrors biological
population dynamics: apoptosis (programmed death for unhealthy agents),
probation (monitoring period for newborns), and culling (making room
for fitter replacements when at capacity).

Grounded in:
- Beer VSM: requisite variety, not excess variety
- Biological apoptosis: programmed cell death for organism health
- Kauffman: autocatalytic sets need minimum viable complexity
- agent_constitution.py: MAX_STABLE_AGENTS = 8 (Four Shaktis x 2 aspects)
"""

from __future__ import annotations

import dataclasses
import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from dharma_swarm.agent_constitution import MAX_STABLE_AGENTS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protected agents -- cannot be culled under any circumstance.
# Operator = coordination plane (S2+S3). Witness = audit plane (S3*).
# Removing either collapses the VSM. Non-negotiable.
# ---------------------------------------------------------------------------

PROTECTED_AGENTS: frozenset[str] = frozenset({"operator", "witness"})

# Fitness floor for culling consideration. Agents above this are "healthy
# enough" that we won't cull them just to make room.
_CULL_FITNESS_CEILING: float = 0.4


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PopulationAssessment:
    """Result of checking whether a new agent can be added.

    Returned by ``PopulationController.can_add_agent()``. If ``can_add``
    is True and ``cull_candidate`` is set, the caller must execute the
    cull before adding the new agent.
    """

    can_add: bool
    current_population: int
    max_population: int
    cull_candidate: str | None = None
    cull_fitness: float | None = None
    reason: str = ""


@dataclass
class ApoptosisResult:
    """Audit record for a completed apoptosis event.

    Persisted to ``~/.dharma/replication/apoptosis.jsonl`` so the witness
    can retrospectively review every programmed death.
    """

    agent_name: str
    reason: str
    fitness_history: list[float]
    memory_archived_to: str
    deactivated_at: str


@dataclass
class ProbationStatus:
    """Tracking for an agent in its probation period.

    New agents are monitored for ``required_cycles`` heartbeat cycles.
    If fitness drops below apoptosis threshold for the configured
    consecutive count during probation, the agent is terminated early.
    Otherwise it graduates after the required number of cycles.
    """

    agent_name: str
    start_cycle: int
    current_cycle: int
    required_cycles: int
    fitness_scores: list[float] = field(default_factory=list)
    graduated: bool = False
    terminated: bool = False

    @property
    def cycles_remaining(self) -> int:
        """Cycles left before graduation eligibility."""
        elapsed = self.current_cycle - self.start_cycle
        return max(0, self.required_cycles - elapsed)

    @property
    def is_complete(self) -> bool:
        """True if probation has concluded (graduated or terminated)."""
        return self.graduated or self.terminated


# ---------------------------------------------------------------------------
# PopulationController
# ---------------------------------------------------------------------------

class PopulationController:
    """Enforces population bounds and fitness-based lifecycle management.

    This is the apoptotic membrane of the swarm. It answers three questions
    on every replication cycle:
    1. Can we add an agent? (population cap + resource budget)
    2. Should we cull an agent? (lowest fitness, non-protected)
    3. Should we kill an agent? (apoptosis: sustained low fitness)

    All state is persisted under ``state_dir / replication /`` so decisions
    survive process restart (SignalBus is in-process only -- G2 gotcha).

    Args:
        state_dir: Root dharma state directory. Defaults to ``~/.dharma``.
        max_population: Hard ceiling on total agent count.
        apoptosis_fitness_threshold: Fitness below this triggers apoptosis
            countdown.
        apoptosis_cycle_count: Consecutive low-fitness cycles before death.
        probation_cycles: Heartbeat cycles a new agent must survive.
        daily_token_budget: Combined daily token budget for all agents.
    """

    def __init__(
        self,
        state_dir: Path | None = None,
        max_population: int = MAX_STABLE_AGENTS,
        apoptosis_fitness_threshold: float = 0.2,
        apoptosis_cycle_count: int = 5,
        probation_cycles: int = 10,
        daily_token_budget: int = 500_000,
    ) -> None:
        self._state_dir = state_dir or Path.home() / ".dharma"
        self._max_population = max_population
        self._apoptosis_threshold = apoptosis_fitness_threshold
        self._apoptosis_cycles = apoptosis_cycle_count
        self._probation_cycles = probation_cycles
        self._daily_token_budget = daily_token_budget

        # Persistence paths
        self._replication_dir = self._state_dir / "replication"
        self._probation_path = self._replication_dir / "probation.json"
        self._apoptosis_log_path = self._replication_dir / "apoptosis.jsonl"

        # In-memory probation state, loaded from disk
        self._probation: dict[str, ProbationStatus] = {}
        self._load_probation()

    # ------------------------------------------------------------------
    # Population assessment
    # ------------------------------------------------------------------

    def can_add_agent(
        self,
        current_agents: list[str],
        fitness_fn: Callable[[str], float] | None = None,
    ) -> PopulationAssessment:
        """Check if the population can accept one more agent.

        If below cap, returns ``can_add=True`` immediately. If at cap,
        identifies the lowest-fitness non-protected agent as a cull
        candidate -- but only if that agent's fitness is below the
        cull ceiling (0.4). A healthy-but-full swarm rejects new agents.

        Args:
            current_agents: Names of all currently active agents.
            fitness_fn: Callable that returns composite fitness for a
                given agent name. If None, defaults to 0.5 for all.

        Returns:
            PopulationAssessment with the decision and rationale.
        """
        pop = len(current_agents)

        if pop < self._max_population:
            return PopulationAssessment(
                can_add=True,
                current_population=pop,
                max_population=self._max_population,
                reason=f"Population below cap ({pop}/{self._max_population})",
            )

        # At capacity -- try to find a cull candidate
        candidate = self._identify_cull_candidate(current_agents, fitness_fn)
        if candidate is not None:
            name, fitness = candidate
            return PopulationAssessment(
                can_add=True,
                current_population=pop,
                max_population=self._max_population,
                cull_candidate=name,
                cull_fitness=fitness,
                reason=(
                    f"At cap but can cull '{name}' "
                    f"(fitness={fitness:.3f} < {_CULL_FITNESS_CEILING})"
                ),
            )

        return PopulationAssessment(
            can_add=False,
            current_population=pop,
            max_population=self._max_population,
            reason=(
                f"At cap ({pop}/{self._max_population}), "
                f"all non-protected agents have fitness >= {_CULL_FITNESS_CEILING}"
            ),
        )

    def _identify_cull_candidate(
        self,
        agents: list[str],
        fitness_fn: Callable[[str], float] | None = None,
    ) -> tuple[str, float] | None:
        """Find the lowest-fitness non-protected, non-probation agent.

        Returns (name, fitness) or None if no viable candidate exists.
        Protected agents and agents still in probation are excluded.
        Only agents with fitness below ``_CULL_FITNESS_CEILING`` qualify.
        """
        candidates: list[tuple[str, float]] = []

        for name in agents:
            if name in PROTECTED_AGENTS:
                continue
            # Don't cull agents still in probation -- too new to evaluate fairly
            if name in self._probation and not self._probation[name].is_complete:
                continue

            fitness = 0.5  # Default when no fitness data available
            if fitness_fn is not None:
                try:
                    fitness = float(fitness_fn(name))
                except Exception:
                    logger.warning(
                        "Failed to get fitness for '%s', using default 0.5", name
                    )

            candidates.append((name, fitness))

        if not candidates:
            return None

        # Sort ascending by fitness -- lowest first
        candidates.sort(key=lambda x: x[1])
        lowest_name, lowest_fitness = candidates[0]

        if lowest_fitness < _CULL_FITNESS_CEILING:
            return (lowest_name, lowest_fitness)

        return None

    # ------------------------------------------------------------------
    # Apoptosis
    # ------------------------------------------------------------------

    def check_apoptosis(
        self,
        agent_name: str,
        recent_fitness_scores: list[float],
    ) -> bool:
        """Check if an agent qualifies for apoptosis.

        Returns True if the agent has been below the apoptosis fitness
        threshold for ``apoptosis_cycle_count`` consecutive cycles.
        Protected agents always return False.

        Args:
            agent_name: The agent to evaluate.
            recent_fitness_scores: Ordered list of fitness scores
                (oldest first). At least ``apoptosis_cycle_count``
                entries are required.
        """
        if agent_name in PROTECTED_AGENTS:
            return False

        if len(recent_fitness_scores) < self._apoptosis_cycles:
            return False

        # Check the last N scores
        tail = recent_fitness_scores[-self._apoptosis_cycles :]
        return all(score < self._apoptosis_threshold for score in tail)

    def execute_apoptosis(
        self,
        agent_name: str,
        reason: str,
        fitness_history: list[float],
    ) -> ApoptosisResult:
        """Deactivate an agent and archive its memory.

        This is programmed death -- the agent's memory is preserved in
        ``~/.dharma/archive/{name}/`` for post-mortem analysis and
        potential genome reuse, then removed from active state.

        Emits ``AGENT_APOPTOSIS`` to the SignalBus so the replication
        monitor loop can cancel the agent's asyncio task.

        Args:
            agent_name: Agent to deactivate.
            reason: Human-readable explanation for the death.
            fitness_history: Full fitness history for audit trail.

        Returns:
            ApoptosisResult with archive location and timestamp.

        Raises:
            ValueError: If ``agent_name`` is in PROTECTED_AGENTS.
        """
        if agent_name in PROTECTED_AGENTS:
            raise ValueError(f"Cannot apoptose protected agent '{agent_name}'")

        # Archive agent memory
        archive_dir = self._state_dir / "archive" / agent_name
        archive_dir.mkdir(parents=True, exist_ok=True)

        memory_src = self._state_dir / "agent_memory" / agent_name
        archive_dest = archive_dir / "memory"
        if memory_src.exists():
            if archive_dest.exists():
                shutil.rmtree(archive_dest)
            shutil.copytree(memory_src, archive_dest)

        timestamp = datetime.now(timezone.utc).isoformat()

        result = ApoptosisResult(
            agent_name=agent_name,
            reason=reason,
            fitness_history=fitness_history[-10:],  # Last 10 scores
            memory_archived_to=str(archive_dir),
            deactivated_at=timestamp,
        )

        # Append to apoptosis audit log (JSONL, append-only)
        self._apoptosis_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._apoptosis_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(dataclasses.asdict(result), default=str) + "\n")

        # Remove from probation if present
        self._probation.pop(agent_name, None)
        self._save_probation()

        # Emit signal (wrap in try/except per codebase convention -- G2)
        self._emit_apoptosis_signal(agent_name, reason)

        logger.info(
            "Apoptosis executed: agent='%s' reason='%s' archive='%s'",
            agent_name, reason, archive_dir,
        )

        return result

    def _emit_apoptosis_signal(self, agent_name: str, reason: str) -> None:
        """Emit AGENT_APOPTOSIS signal to the bus."""
        try:
            from dharma_swarm.signal_bus import (
                SIGNAL_AGENT_APOPTOSIS,
                SignalBus,
            )

            SignalBus.get().emit({
                "type": SIGNAL_AGENT_APOPTOSIS,
                "agent_name": agent_name,
                "reason": reason,
            })
        except Exception:
            pass  # SignalBus may not be available in test contexts

    # ------------------------------------------------------------------
    # Probation
    # ------------------------------------------------------------------

    def start_probation(
        self,
        agent_name: str,
        start_cycle: int = 0,
    ) -> ProbationStatus:
        """Begin probation monitoring for a newly created agent.

        The agent will be tracked for ``probation_cycles`` heartbeat
        cycles. During probation the agent cannot be culled (too new),
        but CAN be terminated via apoptosis if it consistently fails.

        Args:
            agent_name: The new agent entering probation.
            start_cycle: The current cycle number at creation time.

        Returns:
            ProbationStatus tracking object.
        """
        status = ProbationStatus(
            agent_name=agent_name,
            start_cycle=start_cycle,
            current_cycle=start_cycle,
            required_cycles=self._probation_cycles,
        )
        self._probation[agent_name] = status
        self._save_probation()

        logger.info(
            "Probation started: agent='%s' cycles=%d start=%d",
            agent_name, self._probation_cycles, start_cycle,
        )
        return status

    def update_probation(
        self,
        agent_name: str,
        cycle: int,
        fitness: float,
    ) -> ProbationStatus:
        """Update probation status with a new cycle's fitness score.

        Checks for graduation (enough cycles passed) and early
        termination (apoptosis conditions met during probation).

        Args:
            agent_name: Agent in probation.
            cycle: Current heartbeat cycle number.
            fitness: Composite fitness score for this cycle.

        Returns:
            Updated ProbationStatus.

        Raises:
            ValueError: If agent is not in probation.
        """
        if agent_name not in self._probation:
            raise ValueError(f"Agent '{agent_name}' is not in probation")

        status = self._probation[agent_name]
        if status.is_complete:
            return status

        status.current_cycle = cycle
        status.fitness_scores.append(fitness)

        # Check graduation: enough cycles served
        if status.cycles_remaining <= 0:
            status.graduated = True
            logger.info(
                "Probation graduated: agent='%s' avg_fitness=%.3f",
                agent_name,
                sum(status.fitness_scores) / len(status.fitness_scores)
                if status.fitness_scores
                else 0.0,
            )

        # Check early termination: apoptosis conditions during probation
        if not status.graduated and self.check_apoptosis(
            agent_name, status.fitness_scores
        ):
            status.terminated = True
            logger.warning(
                "Probation terminated: agent='%s' (sustained low fitness)",
                agent_name,
            )

        self._save_probation()
        return status

    def get_probation_status(self, agent_name: str) -> ProbationStatus | None:
        """Return probation status for an agent, or None if not tracked."""
        return self._probation.get(agent_name)

    def get_all_probation(self) -> dict[str, ProbationStatus]:
        """Return all probation records (active and completed)."""
        return dict(self._probation)

    def is_in_probation(self, agent_name: str) -> bool:
        """True if the agent is currently in an active (incomplete) probation."""
        status = self._probation.get(agent_name)
        return status is not None and not status.is_complete

    # ------------------------------------------------------------------
    # Resource budget
    # ------------------------------------------------------------------

    def check_resource_budget(
        self,
        current_daily_tokens: int,
    ) -> tuple[bool, str]:
        """Check if daily token budget permits new agent creation.

        Returns (within_budget, reason). Rejects when budget is
        exhausted or nearly exhausted (< 10K tokens remaining).

        Args:
            current_daily_tokens: Tokens consumed so far today.
        """
        if current_daily_tokens >= self._daily_token_budget:
            return (
                False,
                f"Daily token budget exhausted "
                f"({current_daily_tokens:,}/{self._daily_token_budget:,})",
            )

        remaining = self._daily_token_budget - current_daily_tokens
        if remaining < 10_000:
            return (
                False,
                f"Daily token budget nearly exhausted "
                f"({remaining:,} remaining)",
            )

        return (
            True,
            f"Budget OK ({remaining:,}/{self._daily_token_budget:,} remaining)",
        )

    # ------------------------------------------------------------------
    # Persistence (probation state)
    # ------------------------------------------------------------------

    def _load_probation(self) -> None:
        """Load probation state from disk."""
        if not self._probation_path.exists():
            return
        try:
            data = json.loads(self._probation_path.read_text(encoding="utf-8"))
            for name, entry in data.items():
                self._probation[name] = ProbationStatus(**entry)
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            logger.warning("Failed to load probation state: %s", exc)

    def _save_probation(self) -> None:
        """Persist probation state to disk (atomic rewrite)."""
        self._replication_dir.mkdir(parents=True, exist_ok=True)
        data = {
            name: dataclasses.asdict(status)
            for name, status in self._probation.items()
        }
        # Atomic write: write to tmp then rename
        tmp = self._probation_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(data, indent=2, default=str),
            encoding="utf-8",
        )
        tmp.replace(self._probation_path)

    # ------------------------------------------------------------------
    # Health report
    # ------------------------------------------------------------------

    def health_report(
        self,
        agents: list[str],
        fitness_fn: Callable[[str], float] | None = None,
    ) -> dict[str, Any]:
        """Generate a population health summary.

        Useful for the witness audit cycle and the TUI status display.

        Args:
            agents: Names of all currently active agents.
            fitness_fn: Optional callable to get composite fitness by name.

        Returns:
            Dict with population metrics, categorized agent lists,
            and budget status.
        """
        protected = [a for a in agents if a in PROTECTED_AGENTS]
        in_probation = [a for a in agents if self.is_in_probation(a)]
        graduated = [
            a
            for a in agents
            if a in self._probation and self._probation[a].graduated
        ]

        # Compute fitness distribution if function available
        fitness_map: dict[str, float] = {}
        if fitness_fn is not None:
            for name in agents:
                try:
                    fitness_map[name] = float(fitness_fn(name))
                except Exception:
                    fitness_map[name] = 0.5

        report: dict[str, Any] = {
            "total_population": len(agents),
            "max_population": self._max_population,
            "headroom": self._max_population - len(agents),
            "protected": protected,
            "in_probation": in_probation,
            "graduated": graduated,
            "daily_token_budget": self._daily_token_budget,
            "apoptosis_threshold": self._apoptosis_threshold,
            "apoptosis_cycle_count": self._apoptosis_cycles,
            "probation_cycles": self._probation_cycles,
        }

        if fitness_map:
            report["fitness_map"] = fitness_map
            values = list(fitness_map.values())
            report["mean_fitness"] = round(sum(values) / len(values), 4)
            report["min_fitness"] = round(min(values), 4)
            report["max_fitness"] = round(max(values), 4)

        return report

    def get_apoptosis_log(self) -> list[dict[str, Any]]:
        """Read the full apoptosis audit log from disk.

        Returns list of ApoptosisResult dicts, one per line in the
        JSONL file. Returns empty list if file doesn't exist.
        """
        if not self._apoptosis_log_path.exists():
            return []
        results: list[dict[str, Any]] = []
        try:
            for line in self._apoptosis_log_path.read_text(
                encoding="utf-8"
            ).splitlines():
                line = line.strip()
                if line:
                    results.append(json.loads(line))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read apoptosis log: %s", exc)
        return results
