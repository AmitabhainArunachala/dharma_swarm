"""AutoProposer: Closes the autonomy loop.

Observes fitness metrics and system health, generates mutation proposals
when issues are detected, and submits them to the Darwin Engine for
evaluation and integration.

The missing link: detect -> propose -> test -> integrate (no human needed).

Observation sources:
    1. Fitness drop: organism fitness below threshold -> propose optimization
    2. Failure patterns: same error 3+ times -> propose fix
    3. Stigmergy hot spots: many agents mark same file -> propose refactor
    4. Provider failures: circuit breaker trips -> propose rebalancing
    5. Stale tasks: tasks stuck beyond threshold -> propose recovery

Safety:
    - All proposals pass through telos gates before execution
    - Max 3 proposals per cycle, max 10 per day
    - Every observation and proposal logged to ~/.dharma/auto_proposer/
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

from pydantic import BaseModel, Field

from dharma_swarm.models import _new_id, _utc_now

if TYPE_CHECKING:
    from dharma_swarm.evolution import DarwinEngine, Proposal
    from dharma_swarm.fitness_predictor import FitnessPredictor
    from dharma_swarm.monitor import SystemMonitor
    from dharma_swarm.stigmergy import StigmergyStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ObservationType(str, Enum):
    """Classification of what the AutoProposer observed."""

    FITNESS_DROP = "fitness_drop"
    FAILURE_PATTERN = "failure_pattern"
    STIGMERGY_HOTSPOT = "stigmergy_hotspot"
    PROVIDER_FAILURE = "provider_failure"
    STALE_TASKS = "stale_tasks"
    FITNESS_PLATEAU = "fitness_plateau"
    TEST_FAILURE_CLUSTER = "test_failure_cluster"
    EVOLUTION_STAGNATION = "evolution_stagnation"


class ProposalSource(str, Enum):
    """How the proposal was generated."""

    AUTO_FITNESS = "auto_fitness"
    AUTO_FAILURE = "auto_failure"
    AUTO_HOTSPOT = "auto_hotspot"
    AUTO_PROVIDER = "auto_provider"
    AUTO_STALE = "auto_stale"
    AUTO_PLATEAU = "auto_plateau"
    AUTO_TEST_CLUSTER = "auto_test_cluster"
    AUTO_EVOLUTION_STAGNATION = "auto_evolution_stagnation"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class Observation(BaseModel):
    """A single observation from the system's health/fitness signals."""

    id: str = Field(default_factory=_new_id)
    timestamp: datetime = Field(default_factory=_utc_now)
    observation_type: ObservationType
    severity: str = "medium"  # "low", "medium", "high"
    description: str
    source_data: dict[str, Any] = Field(default_factory=dict)


class ProposalRecord(BaseModel):
    """Log entry for a generated proposal."""

    id: str = Field(default_factory=_new_id)
    timestamp: datetime = Field(default_factory=_utc_now)
    observation_id: str
    observation_type: str
    component: str
    change_type: str
    description: str
    source: ProposalSource
    submitted: bool = False
    proposal_id: Optional[str] = None


class CycleLog(BaseModel):
    """Summary of one observe-propose-submit cycle."""

    id: str = Field(default_factory=_new_id)
    timestamp: datetime = Field(default_factory=_utc_now)
    observations_collected: int = 0
    proposals_generated: int = 0
    proposals_submitted: int = 0
    throttled: int = 0
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

_DEFAULT_FITNESS_THRESHOLD: float = 0.3
_DEFAULT_FAILURE_REPEAT_THRESHOLD: int = 3
_DEFAULT_HOTSPOT_MIN_MARKS: int = 5
_DEFAULT_STALE_TASK_HOURS: float = 2.0
_MAX_PROPOSALS_PER_CYCLE: int = 3
_MAX_PROPOSALS_PER_DAY: int = 10


# ---------------------------------------------------------------------------
# AutoProposer
# ---------------------------------------------------------------------------


class AutoProposer:
    """Closes the autonomy loop: observe -> propose -> submit.

    Connects the SystemMonitor's health/anomaly detection and the
    FitnessPredictor's fitness signals to the DarwinEngine's proposal
    pipeline. Runs as part of the swarm tick loop.

    Args:
        darwin_engine: The evolution engine that processes proposals.
        system_monitor: Health and anomaly detection system.
        fitness_predictor: Fitness estimation from historical data.
        stigmergy: Optional stigmergy store for hotspot detection.
        log_dir: Directory for JSONL logs.
        fitness_threshold: Minimum acceptable fitness before proposing.
        failure_repeat_threshold: How many repeats of same error before proposing.
        hotspot_min_marks: Minimum stigmergy marks to flag a hotspot.
        stale_task_hours: Hours before a task is considered stale.
        max_per_cycle: Maximum proposals generated per cycle.
        max_per_day: Maximum proposals generated per day.
    """

    def __init__(
        self,
        darwin_engine: DarwinEngine,
        system_monitor: SystemMonitor,
        fitness_predictor: FitnessPredictor,
        stigmergy: StigmergyStore | None = None,
        log_dir: Path | None = None,
        fitness_threshold: float = _DEFAULT_FITNESS_THRESHOLD,
        failure_repeat_threshold: int = _DEFAULT_FAILURE_REPEAT_THRESHOLD,
        hotspot_min_marks: int = _DEFAULT_HOTSPOT_MIN_MARKS,
        stale_task_hours: float = _DEFAULT_STALE_TASK_HOURS,
        max_per_cycle: int = _MAX_PROPOSALS_PER_CYCLE,
        max_per_day: int = _MAX_PROPOSALS_PER_DAY,
    ) -> None:
        self._engine = darwin_engine
        self._monitor = system_monitor
        self._predictor = fitness_predictor
        self._stigmergy = stigmergy

        self._log_dir = log_dir or (Path.home() / ".dharma" / "auto_proposer")
        self._fitness_threshold = fitness_threshold
        self._failure_repeat_threshold = max(2, failure_repeat_threshold)
        self._hotspot_min_marks = max(2, hotspot_min_marks)
        self._stale_task_hours = max(0.5, stale_task_hours)
        self._max_per_cycle = max(1, max_per_cycle)
        self._max_per_day = max(1, max_per_day)

        # Daily throttle state
        self._daily_count: int = 0
        self._daily_reset_date: str = ""

        # Observation log (in-memory buffer flushed to JSONL)
        self._observations_file = self._log_dir / "observations.jsonl"
        self._proposals_file = self._log_dir / "proposals.jsonl"
        self._cycles_file = self._log_dir / "cycles.jsonl"

    # -- throttling ----------------------------------------------------------

    def _check_daily_reset(self) -> None:
        """Reset daily counter if the date has changed."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._daily_reset_date:
            self._daily_reset_date = today
            self._daily_count = 0

    def _can_propose(self) -> bool:
        """Check whether we're within the daily proposal budget."""
        self._check_daily_reset()
        return self._daily_count < self._max_per_day

    def _record_proposal_count(self, count: int) -> None:
        """Increment the daily proposal counter."""
        self._check_daily_reset()
        self._daily_count += count

    # -- logging -------------------------------------------------------------

    async def _log_jsonl(self, path: Path, data: BaseModel) -> None:
        """Append a Pydantic model as a JSON line to the given file."""
        import asyncio

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a") as fh:
                fh.write(data.model_dump_json() + "\n")

        await asyncio.to_thread(_write)

    # -- observation collection ----------------------------------------------

    async def _observe_fitness(self) -> list[Observation]:
        """Check mean fitness from the health report."""
        observations: list[Observation] = []
        try:
            report = await self._monitor.check_health()
            if report.mean_fitness is not None and report.mean_fitness < self._fitness_threshold:
                observations.append(Observation(
                    observation_type=ObservationType.FITNESS_DROP,
                    severity="high" if report.mean_fitness < self._fitness_threshold * 0.5 else "medium",
                    description=(
                        f"Mean fitness {report.mean_fitness:.3f} below threshold "
                        f"{self._fitness_threshold:.3f}"
                    ),
                    source_data={
                        "mean_fitness": report.mean_fitness,
                        "threshold": self._fitness_threshold,
                        "failure_rate": report.failure_rate,
                    },
                ))
        except Exception as exc:
            logger.debug("AutoProposer fitness observation failed: %s", exc)
        return observations

    async def _observe_failures(self) -> list[Observation]:
        """Detect repeated failure patterns from anomalies."""
        observations: list[Observation] = []
        try:
            report = await self._monitor.check_health()
            # Count anomalies by type
            type_counts: Counter[str] = Counter()
            for anomaly in report.anomalies:
                type_counts[anomaly.anomaly_type] += 1

            for anomaly_type, count in type_counts.items():
                if count >= self._failure_repeat_threshold:
                    observations.append(Observation(
                        observation_type=ObservationType.FAILURE_PATTERN,
                        severity="high",
                        description=(
                            f"Anomaly type '{anomaly_type}' detected {count} times "
                            f"(threshold: {self._failure_repeat_threshold})"
                        ),
                        source_data={
                            "anomaly_type": anomaly_type,
                            "count": count,
                            "threshold": self._failure_repeat_threshold,
                        },
                    ))

            # Also check for high failure rate as a pattern
            if report.failure_rate > 0.3:
                observations.append(Observation(
                    observation_type=ObservationType.FAILURE_PATTERN,
                    severity="high" if report.failure_rate > 0.5 else "medium",
                    description=(
                        f"System failure rate {report.failure_rate:.1%} exceeds 30% — "
                        f"systematic issue suspected"
                    ),
                    source_data={
                        "failure_rate": report.failure_rate,
                        "total_traces": report.total_traces,
                    },
                ))
        except Exception as exc:
            logger.debug("AutoProposer failure observation failed: %s", exc)
        return observations

    async def _observe_hotspots(self) -> list[Observation]:
        """Detect stigmergy hotspots — files marked by many agents."""
        observations: list[Observation] = []
        if self._stigmergy is None:
            return observations
        try:
            hot = await self._stigmergy.hot_paths(
                window_hours=24,
                min_marks=self._hotspot_min_marks,
            )
            for file_path, mark_count in hot[:5]:  # Top 5 hotspots
                observations.append(Observation(
                    observation_type=ObservationType.STIGMERGY_HOTSPOT,
                    severity="medium" if mark_count < 10 else "high",
                    description=(
                        f"File '{file_path}' has {mark_count} stigmergy marks "
                        f"in 24h (threshold: {self._hotspot_min_marks})"
                    ),
                    source_data={
                        "file_path": file_path,
                        "mark_count": mark_count,
                        "threshold": self._hotspot_min_marks,
                    },
                ))
        except Exception as exc:
            logger.debug("AutoProposer hotspot observation failed: %s", exc)
        return observations

    async def _observe_provider_failures(self) -> list[Observation]:
        """Detect provider-level circuit breaker trips from health report."""
        observations: list[Observation] = []
        try:
            report = await self._monitor.check_health()
            # Look for agents with critical health (likely provider issues)
            critical_agents = [
                ah for ah in report.agent_health
                if ah.status.value == "critical"
            ]
            if critical_agents:
                observations.append(Observation(
                    observation_type=ObservationType.PROVIDER_FAILURE,
                    severity="high",
                    description=(
                        f"{len(critical_agents)} agent(s) in CRITICAL state: "
                        f"{', '.join(a.agent_name for a in critical_agents[:3])}"
                    ),
                    source_data={
                        "critical_agents": [
                            {"name": a.agent_name, "success_rate": a.success_rate}
                            for a in critical_agents
                        ],
                    },
                ))
        except Exception as exc:
            logger.debug("AutoProposer provider failure observation failed: %s", exc)
        return observations

    async def _observe_stale_tasks(self) -> list[Observation]:
        """Detect stale/stuck anomalies from the monitor's anomaly list."""
        observations: list[Observation] = []
        try:
            report = await self._monitor.check_health()
            # Silent agents are proxies for stale work
            silent = [
                a for a in report.anomalies
                if a.anomaly_type == "agent_silent"
            ]
            if silent:
                observations.append(Observation(
                    observation_type=ObservationType.STALE_TASKS,
                    severity="medium",
                    description=(
                        f"{len(silent)} agent(s) gone silent — "
                        f"possible stale task or deadlock"
                    ),
                    source_data={
                        "silent_agents": [a.description for a in silent[:5]],
                    },
                ))

            # Throughput drop is also a stale indicator
            throughput_drops = [
                a for a in report.anomalies
                if a.anomaly_type == "throughput_drop"
            ]
            if throughput_drops:
                observations.append(Observation(
                    observation_type=ObservationType.STALE_TASKS,
                    severity="low",
                    description=(
                        f"Throughput drop detected — system may be stalled"
                    ),
                    source_data={
                        "drops": [a.description for a in throughput_drops],
                    },
                ))
        except Exception as exc:
            logger.debug("AutoProposer stale task observation failed: %s", exc)
        return observations

    async def _observe_fitness_plateau(self) -> list[Observation]:
        """Detect fitness plateau — meta-evolution stuck in a band."""
        observations: list[Observation] = []
        try:
            import json as _pj
            meta_path = self._log_dir.parent / "evolution" / "meta_archive.jsonl"
            if meta_path.exists():
                lines = meta_path.read_text().strip().split("\n")
                recent = lines[-20:]  # Last 20 meta entries
                fitnesses = []
                for line in recent:
                    if not line.strip():
                        continue
                    entry = _pj.loads(line)
                    mf = entry.get("meta_fitness", 0.0)
                    if mf:
                        fitnesses.append(mf)
                if len(fitnesses) >= 10:
                    # Plateau: stddev < 0.02 across recent entries
                    mean_f = sum(fitnesses) / len(fitnesses)
                    variance = sum((f - mean_f) ** 2 for f in fitnesses) / len(fitnesses)
                    stddev = variance ** 0.5
                    if stddev < 0.02:
                        observations.append(Observation(
                            observation_type=ObservationType.FITNESS_PLATEAU,
                            severity="high",
                            description=(
                                f"Meta-fitness plateaued at {mean_f:.3f} "
                                f"(stddev={stddev:.4f} over {len(fitnesses)} cycles) — "
                                f"evolution may be stuck in local optimum"
                            ),
                            source_data={
                                "mean_fitness": mean_f,
                                "stddev": stddev,
                                "sample_size": len(fitnesses),
                            },
                        ))
        except Exception as exc:
            logger.debug("AutoProposer fitness plateau observation failed: %s", exc)
        return observations

    async def _observe_test_failure_clusters(self) -> list[Observation]:
        """Detect clusters of test failures in specific modules."""
        observations: list[Observation] = []
        try:
            import json as _tj
            archive_path = self._log_dir.parent / "evolution" / "archive.jsonl"
            if archive_path.exists():
                lines = archive_path.read_text().strip().split("\n")
                fail_counts: dict[str, int] = {}
                for line in lines[-30:]:
                    if not line.strip():
                        continue
                    entry = _tj.loads(line)
                    fitness = entry.get("fitness", {})
                    if isinstance(fitness, dict) and fitness.get("correctness", 1.0) == 0.0:
                        comp = entry.get("component", "unknown")
                        fail_counts[comp] = fail_counts.get(comp, 0) + 1
                for comp, count in fail_counts.items():
                    if count >= 3:
                        observations.append(Observation(
                            observation_type=ObservationType.TEST_FAILURE_CLUSTER,
                            severity="high",
                            description=(
                                f"Component '{comp}' has {count} consecutive evolution "
                                f"failures (correctness=0.0) — systematic test issue"
                            ),
                            source_data={
                                "component": comp,
                                "failure_count": count,
                                "file_path": f"dharma_swarm/{comp}" if not comp.startswith("dharma_swarm/") else comp,
                            },
                        ))
        except Exception as exc:
            logger.debug("AutoProposer test failure cluster observation failed: %s", exc)
        return observations

    async def _observe_evolution_stagnation(self) -> list[Observation]:
        """Detect evolution stagnation — many cycles with zero archived proposals."""
        observations: list[Observation] = []
        try:
            import json as _sj
            archive_path = self._log_dir.parent / "evolution" / "archive.jsonl"
            if archive_path.exists():
                lines = archive_path.read_text().strip().split("\n")
                total = len([l for l in lines if l.strip()])
                if total > 0:
                    recent = lines[-20:]
                    recent_zero = sum(
                        1 for l in recent if l.strip() and
                        _sj.loads(l).get("fitness", {}).get("correctness", 0.0) == 0.0
                    )
                    if recent_zero > 15:  # 75%+ of recent entries are zero
                        observations.append(Observation(
                            observation_type=ObservationType.EVOLUTION_STAGNATION,
                            severity="high",
                            description=(
                                f"Evolution stagnating: {recent_zero}/20 recent archive "
                                f"entries have correctness=0.0 — proposals not being tested "
                                f"or all failing"
                            ),
                            source_data={
                                "zero_fitness_count": recent_zero,
                                "total_recent": 20,
                                "archive_size": total,
                            },
                        ))
        except Exception as exc:
            logger.debug("AutoProposer evolution stagnation observation failed: %s", exc)
        return observations

    async def observe(self) -> list[Observation]:
        """Collect observations from all sources.

        Runs all observation coroutines concurrently and merges results.

        Returns:
            List of observations, sorted by severity (high first).
        """
        results = await asyncio.gather(
            self._observe_fitness(),
            self._observe_failures(),
            self._observe_hotspots(),
            self._observe_provider_failures(),
            self._observe_stale_tasks(),
            self._observe_fitness_plateau(),
            self._observe_test_failure_clusters(),
            self._observe_evolution_stagnation(),
            return_exceptions=True,
        )

        observations: list[Observation] = []
        for result in results:
            if isinstance(result, list):
                observations.extend(result)
            elif isinstance(result, Exception):
                logger.debug("Observation source failed: %s", result)

        # Sort: high > medium > low
        severity_order = {"high": 0, "medium": 1, "low": 2}
        observations.sort(key=lambda o: severity_order.get(o.severity, 3))

        return observations

    # -- proposal generation -------------------------------------------------

    def _observation_to_proposal_params(
        self, observation: Observation
    ) -> dict[str, Any] | None:
        """Map an observation to DarwinEngine.propose() parameters.

        Returns None if the observation doesn't warrant a proposal.
        """
        otype = observation.observation_type

        if otype == ObservationType.FITNESS_DROP:
            mean_f = observation.source_data.get("mean_fitness", 0.0)
            return {
                "component": "dharma_swarm/fitness_predictor.py",
                "change_type": "mutation",
                "description": (
                    f"Optimize fitness scoring: mean fitness {mean_f:.3f} "
                    f"below threshold. Investigate scoring weights, "
                    f"predictor calibration, or evaluation criteria."
                ),
                "source": ProposalSource.AUTO_FITNESS,
            }

        if otype == ObservationType.FAILURE_PATTERN:
            anomaly_type = observation.source_data.get("anomaly_type", "unknown")
            if anomaly_type != "unknown":
                return {
                    "component": "dharma_swarm/monitor.py",
                    "change_type": "mutation",
                    "description": (
                        f"Address repeated '{anomaly_type}' anomaly pattern: "
                        f"{observation.description}. "
                        f"Investigate root cause and add resilience."
                    ),
                    "source": ProposalSource.AUTO_FAILURE,
                }
            # High failure rate
            failure_rate = observation.source_data.get("failure_rate", 0.0)
            return {
                "component": "dharma_swarm/agent_runner.py",
                "change_type": "mutation",
                "description": (
                    f"Reduce system failure rate ({failure_rate:.1%}): "
                    f"review error handling, retry logic, and fallback paths."
                ),
                "source": ProposalSource.AUTO_FAILURE,
            }

        if otype == ObservationType.STIGMERGY_HOTSPOT:
            file_path = observation.source_data.get("file_path", "unknown")
            mark_count = observation.source_data.get("mark_count", 0)
            return {
                "component": file_path,
                "change_type": "mutation",
                "description": (
                    f"Refactor hotspot file '{file_path}' ({mark_count} marks in 24h): "
                    f"high agent activity suggests complexity or coupling issues."
                ),
                "source": ProposalSource.AUTO_HOTSPOT,
            }

        if otype == ObservationType.PROVIDER_FAILURE:
            return {
                "component": "dharma_swarm/providers.py",
                "change_type": "mutation",
                "description": (
                    f"Rebalance provider routing: {observation.description}. "
                    f"Adjust circuit breaker thresholds or add failover paths."
                ),
                "source": ProposalSource.AUTO_PROVIDER,
            }

        if otype == ObservationType.STALE_TASKS:
            return {
                "component": "dharma_swarm/orchestrator.py",
                "change_type": "mutation",
                "description": (
                    f"Improve task lifecycle: {observation.description}. "
                    f"Add timeout detection, automatic retry, or dead-letter queue."
                ),
                "source": ProposalSource.AUTO_STALE,
            }

        if otype == ObservationType.FITNESS_PLATEAU:
            return {
                "component": "dharma_swarm/meta_evolution.py",
                "change_type": "mutation",
                "description": (
                    f"Break fitness plateau: {observation.description}. "
                    f"Increase mutation variance, try novel crossover, or reset population diversity."
                ),
                "source": ProposalSource.AUTO_PLATEAU,
            }

        if otype == ObservationType.TEST_FAILURE_CLUSTER:
            comp = observation.source_data.get("file_path", "dharma_swarm/evolution.py")
            return {
                "component": comp,
                "change_type": "fix",
                "description": (
                    f"Fix test failure cluster: {observation.description}. "
                    f"Component needs test profile or source-level fix for evolution to work."
                ),
                "source": ProposalSource.AUTO_TEST_CLUSTER,
            }

        if otype == ObservationType.EVOLUTION_STAGNATION:
            return {
                "component": "dharma_swarm/evolution.py",
                "change_type": "mutation",
                "description": (
                    f"Address evolution stagnation: {observation.description}. "
                    f"Root cause: proposals may lack test_results or target untestable components."
                ),
                "source": ProposalSource.AUTO_EVOLUTION_STAGNATION,
            }

        return None

    async def propose(self, observations: list[Observation]) -> list[Proposal]:
        """Generate mutation proposals from observations.

        Applies throttling (per-cycle and per-day limits) and fitness
        prediction filtering.

        Args:
            observations: Observations from the observe() phase.

        Returns:
            List of Proposal objects ready for submission to the Darwin Engine.
        """
        if not self._can_propose():
            logger.info(
                "AutoProposer daily limit reached (%d/%d) — skipping",
                self._daily_count, self._max_per_day,
            )
            return []

        proposals: list[Proposal] = []
        remaining_budget = min(
            self._max_per_cycle,
            self._max_per_day - self._daily_count,
        )

        for observation in observations:
            if remaining_budget <= 0:
                break

            params = self._observation_to_proposal_params(observation)
            if params is None:
                continue

            source = params.pop("source")

            try:
                # Check if the predictor thinks this is worth attempting
                from dharma_swarm.fitness_predictor import ProposalFeatures

                features = ProposalFeatures(
                    component=params["component"],
                    change_type=params["change_type"],
                    diff_size=0,  # No diff yet — this is a proposal
                )
                if not self._predictor.should_attempt(features, threshold=0.2):
                    logger.debug(
                        "AutoProposer: skipping low-predicted-fitness proposal for %s",
                        params["component"],
                    )
                    continue

                proposal = await self._engine.propose(**params)
                proposals.append(proposal)
                remaining_budget -= 1

                # Log the proposal
                record = ProposalRecord(
                    observation_id=observation.id,
                    observation_type=observation.observation_type.value,
                    component=params["component"],
                    change_type=params["change_type"],
                    description=params["description"],
                    source=source,
                    submitted=True,
                    proposal_id=proposal.id,
                )
                await self._log_jsonl(self._proposals_file, record)

            except Exception as exc:
                logger.warning(
                    "AutoProposer: failed to create proposal from %s observation: %s",
                    observation.observation_type.value, exc,
                )

        self._record_proposal_count(len(proposals))
        return proposals

    # -- full cycle ----------------------------------------------------------

    async def cycle(self) -> CycleLog:
        """Execute one full observe -> propose -> submit loop.

        Returns:
            A CycleLog summarizing what happened.
        """
        cycle_log = CycleLog()

        # Phase 1: Observe
        try:
            observations = await self.observe()
            cycle_log.observations_collected = len(observations)

            # Log observations
            for obs in observations:
                await self._log_jsonl(self._observations_file, obs)

        except Exception as exc:
            cycle_log.errors.append(f"observe failed: {exc}")
            logger.warning("AutoProposer observe phase failed: %s", exc)
            await self._log_jsonl(self._cycles_file, cycle_log)
            return cycle_log

        if not observations:
            logger.debug("AutoProposer: no observations — system looks healthy")
            await self._log_jsonl(self._cycles_file, cycle_log)
            return cycle_log

        # Phase 2: Propose
        try:
            proposals = await self.propose(observations)
            cycle_log.proposals_generated = len(proposals)
            cycle_log.throttled = max(
                0, len(observations) - len(proposals)
            )
        except Exception as exc:
            cycle_log.errors.append(f"propose failed: {exc}")
            logger.warning("AutoProposer propose phase failed: %s", exc)
            await self._log_jsonl(self._cycles_file, cycle_log)
            return cycle_log

        if not proposals:
            logger.debug("AutoProposer: no proposals generated this cycle")
            await self._log_jsonl(self._cycles_file, cycle_log)
            return cycle_log

        # Phase 3: Submit to Darwin Engine
        try:
            cycle_result = await self._engine.run_cycle(proposals)
            cycle_log.proposals_submitted = cycle_result.proposals_archived
            logger.info(
                "AutoProposer cycle complete: %d observations -> %d proposals -> "
                "%d archived (best_fitness=%.3f)",
                cycle_log.observations_collected,
                cycle_log.proposals_generated,
                cycle_log.proposals_submitted,
                cycle_result.best_fitness,
            )
        except Exception as exc:
            cycle_log.errors.append(f"submit failed: {exc}")
            logger.warning("AutoProposer submit phase failed: %s", exc)

        await self._log_jsonl(self._cycles_file, cycle_log)
        return cycle_log

    # -- introspection -------------------------------------------------------

    @property
    def daily_count(self) -> int:
        """How many proposals have been generated today."""
        self._check_daily_reset()
        return self._daily_count

    @property
    def daily_remaining(self) -> int:
        """How many proposals can still be generated today."""
        self._check_daily_reset()
        return max(0, self._max_per_day - self._daily_count)

    def status(self) -> dict[str, Any]:
        """Return a summary of the AutoProposer's state."""
        self._check_daily_reset()
        return {
            "daily_count": self._daily_count,
            "daily_remaining": self.daily_remaining,
            "max_per_cycle": self._max_per_cycle,
            "max_per_day": self._max_per_day,
            "fitness_threshold": self._fitness_threshold,
            "failure_repeat_threshold": self._failure_repeat_threshold,
            "hotspot_min_marks": self._hotspot_min_marks,
            "stale_task_hours": self._stale_task_hours,
            "has_stigmergy": self._stigmergy is not None,
            "log_dir": str(self._log_dir),
        }
