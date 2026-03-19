"""Perception-Action Loop — the heartbeat that replaces cron.

The core architectural shift: from five fixed-interval loops to a single
precision-gated endogenous cycle where the SYSTEM decides when to sense
and when to act, based on prediction errors against its own model.

Timing is endogenous:
  - High prediction errors → precision drops → cycle ACCELERATES
  - Low prediction errors → precision rises → cycle DECELERATES
  - Base period: 60s. Range: 10s (crisis) to 600s (deep stability)

The four phases:
  PERCEIVE  → sense stigmergy, health, filesystem, signals
  DELIBERATE → complexity route, S3-S4-S5 triangle, EFE scoring
  COMMIT    → pre-mortem, checkpoint, execute
  VERIFY    → environmental checks, update model, update fitness

Cron remains as emergency fallback, not primary mechanism.

Grounded in: SYNTHESIS.md Phase 2, Principles #3 #6 #7
Sources: Friston active inference, pymdp, neuroscience precision-weighting
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Coroutine

from pydantic import BaseModel

from dharma_swarm.complexity_router import ComplexityRoute, ComplexityRouter
from dharma_swarm.cost_ledger import CostLedger
from dharma_swarm.environmental_verifier import verify_action
from dharma_swarm.loop_detector import ActionRecord, LoopDetector
from dharma_swarm.models import _new_id

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class LoopConfig(BaseModel):
    """Configuration for the perception-action loop."""
    base_period_seconds: float = 60.0
    min_period_seconds: float = 10.0
    max_period_seconds: float = 600.0
    precision_ema_alpha: float = 0.1  # EMA smoothing for precision updates
    initial_precision: float = 0.5
    salience_threshold: float = 0.3  # Minimum salience for perception
    max_actions_per_cycle: int = 3
    prediction_error_window: int = 20  # Rolling window for precision calc
    quiet_hours_start: int = 2  # 2 AM
    quiet_hours_end: int = 5  # 5 AM


# ---------------------------------------------------------------------------
# Perception state
# ---------------------------------------------------------------------------

class PerceptionModality(str, Enum):
    """What the system can sense."""
    STIGMERGY = "stigmergy"
    HEALTH = "health"
    FILESYSTEM = "filesystem"
    SIGNALS = "signals"
    DEADLINES = "deadlines"


@dataclass
class Percept:
    """A single perception from any modality."""
    modality: PerceptionModality
    timestamp: str = ""
    observation: str = ""
    salience: float = 0.5  # [0,1] — importance
    prediction_error: float = 0.0  # |expected - observed|
    data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class WorldModel:
    """The system's model of itself and its environment.

    Updated after every VERIFY phase. Prediction errors against this
    model drive the precision mechanism.
    """
    # Expected state (predictions)
    expected_daemon_alive: dict[str, bool] = field(default_factory=lambda: {
        "dharma_swarm": False,
        "mycelium": False,
    })
    expected_stigmergy_density: int = 50
    expected_mark_age_hours: float = 24.0
    expected_signal_freshness: dict[str, float] = field(default_factory=dict)

    # Observed state (updated by PERCEIVE)
    observed_daemon_alive: dict[str, bool] = field(default_factory=dict)
    observed_stigmergy_density: int = 0
    observed_mark_age_hours: float = 0.0
    observed_signal_freshness: dict[str, float] = field(default_factory=dict)

    # Model quality
    last_updated: str = ""
    total_prediction_errors: float = 0.0
    update_count: int = 0

    def compute_prediction_error(self) -> float:
        """Compute aggregate prediction error across all modalities."""
        errors: list[float] = []

        # Daemon state errors
        for name in self.expected_daemon_alive:
            expected = self.expected_daemon_alive.get(name, False)
            observed = self.observed_daemon_alive.get(name, False)
            errors.append(1.0 if expected != observed else 0.0)

        # Stigmergy density error (normalized)
        if self.expected_stigmergy_density > 0:
            density_err = abs(self.observed_stigmergy_density - self.expected_stigmergy_density) / max(
                self.expected_stigmergy_density, 1
            )
            errors.append(min(1.0, density_err))

        if not errors:
            return 0.0

        return sum(errors) / len(errors)

    def update_expectations(self) -> None:
        """Update expectations based on observations (Bayesian-ish update).

        Simple rule: expected = 0.7 * observed + 0.3 * old_expected
        This makes the model track reality while being slightly conservative.
        """
        alpha = 0.7

        for name in self.observed_daemon_alive:
            self.expected_daemon_alive[name] = self.observed_daemon_alive[name]

        self.expected_stigmergy_density = int(
            alpha * self.observed_stigmergy_density
            + (1 - alpha) * self.expected_stigmergy_density
        )

        self.last_updated = datetime.now(timezone.utc).isoformat()
        self.update_count += 1


# ---------------------------------------------------------------------------
# Candidate action
# ---------------------------------------------------------------------------

@dataclass
class CandidateAction:
    """A proposed action from the DELIBERATE phase."""
    id: str = ""
    action_type: str = ""
    target: str = ""
    description: str = ""
    source_percept: Percept | None = None
    complexity_route: ComplexityRoute = ComplexityRoute.FAST
    expected_free_energy: float = 0.0  # Lower is better
    priority: float = 0.0  # Higher is more urgent
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id:
            self.id = _new_id()


# ---------------------------------------------------------------------------
# The Loop
# ---------------------------------------------------------------------------

class PerceptionActionLoop:
    """The living heartbeat of dharma_swarm v0.3.0.

    Replaces orchestrate_live's five fixed-interval loops with a single
    precision-gated cycle. The system itself decides when to pay attention
    and when to act.

    Usage::

        loop = PerceptionActionLoop(
            config=LoopConfig(),
            sensors=[stigmergy_sensor, health_sensor, ...],
            action_handler=my_action_handler,
        )
        await loop.run(shutdown_event)

    The `sensors` are async callables that return list[Percept].
    The `action_handler` is an async callable that executes a CandidateAction.
    """

    def __init__(
        self,
        config: LoopConfig | None = None,
        sensors: list[Callable[[], Coroutine[Any, Any, list[Percept]]]] | None = None,
        action_handler: Callable[[CandidateAction], Coroutine[Any, Any, dict[str, Any]]] | None = None,
        complexity_router: ComplexityRouter | None = None,
        cost_ledger: CostLedger | None = None,
        loop_detector: LoopDetector | None = None,
    ) -> None:
        self.config = config or LoopConfig()
        self.sensors = sensors or []
        self.action_handler = action_handler
        self.complexity_router = complexity_router or ComplexityRouter()
        self.cost_ledger = cost_ledger or CostLedger()
        self.loop_detector = loop_detector or LoopDetector()

        # State
        self.precision: float = self.config.initial_precision
        self.world_model = WorldModel()
        self.cycle_count: int = 0
        self.last_cycle_time: float = 0.0
        self.percepts_buffer: list[Percept] = []

        # Metrics
        self.total_actions_taken: int = 0
        self.total_actions_skipped: int = 0
        self.precision_history: list[float] = []

        # State file for persistence
        self._state_dir = Path.home() / ".dharma" / "perception_loop"
        self._state_dir.mkdir(parents=True, exist_ok=True)

    @property
    def current_period(self) -> float:
        """Compute current cycle period based on precision.

        High precision (stable) → longer period → less frequent sensing
        Low precision (surprised) → shorter period → more frequent sensing

        period = base / (1 + k * (1 - precision))
        Where k scales the sensitivity to precision changes.
        """
        k = 4.0  # Sensitivity factor
        period = self.config.base_period_seconds / (1.0 + k * (1.0 - self.precision))
        return max(
            self.config.min_period_seconds,
            min(self.config.max_period_seconds, period),
        )

    def _is_quiet_hours(self) -> bool:
        """Check if we're in quiet hours (reduced activity)."""
        hour = datetime.now().hour
        return self.config.quiet_hours_start <= hour < self.config.quiet_hours_end

    # ---- PHASE 1: PERCEIVE ----

    async def perceive(self) -> list[Percept]:
        """Run all sensors and collect percepts.

        Filters by salience threshold. Variety attenuation: not all
        signals are processed.
        """
        all_percepts: list[Percept] = []

        for sensor in self.sensors:
            try:
                percepts = await asyncio.wait_for(sensor(), timeout=30.0)
                all_percepts.extend(percepts)
            except asyncio.TimeoutError:
                logger.warning("Sensor %s timed out", sensor.__name__ if hasattr(sensor, '__name__') else '?')
            except Exception as e:
                logger.error("Sensor error: %s", e)

        # Filter by salience
        filtered = [p for p in all_percepts if p.salience >= self.config.salience_threshold]

        # Sort by salience (highest first)
        filtered.sort(key=lambda p: p.salience, reverse=True)

        # Compute prediction errors
        for p in filtered:
            # Simple: salience IS a proxy for surprise in current implementation
            # Will be refined when generative model is explicit
            p.prediction_error = abs(p.salience - 0.5) * 2  # Normalize to [0,1]

        self.percepts_buffer = filtered
        return filtered

    # ---- PHASE 2: DELIBERATE ----

    async def deliberate(self, percepts: list[Percept]) -> list[CandidateAction]:
        """Generate candidate actions from percepts.

        Uses complexity router to determine fast vs slow path.
        Generates at most max_actions_per_cycle candidates.
        """
        candidates: list[CandidateAction] = []

        for percept in percepts[:self.config.max_actions_per_cycle * 2]:
            # Generate candidate from percept
            candidate = self._percept_to_candidate(percept)
            if candidate is None:
                continue

            # Classify complexity
            classification = self.complexity_router.classify(
                action_type=candidate.action_type,
                target=candidate.target,
            )
            candidate.complexity_route = classification.route

            # Score expected free energy (simplified)
            # EFE = Risk + Ambiguity - Novelty
            risk = 1.0 - percept.salience  # High salience = low risk of ignoring
            ambiguity = percept.prediction_error
            novelty = 0.3 if classification.route == ComplexityRoute.SLOW else 0.1
            candidate.expected_free_energy = risk + ambiguity - novelty
            candidate.priority = percept.salience

            candidates.append(candidate)

        # Sort by priority (highest first)
        candidates.sort(key=lambda c: c.priority, reverse=True)

        return candidates[:self.config.max_actions_per_cycle]

    def _percept_to_candidate(self, percept: Percept) -> CandidateAction | None:
        """Convert a percept into a candidate action.

        This is where domain-specific logic lives. Each modality
        has its own action generation rules.
        """
        if percept.modality == PerceptionModality.HEALTH:
            # Health percepts generate health-related actions
            return CandidateAction(
                action_type="health_check",
                target=percept.data.get("target", ""),
                description=percept.observation,
                source_percept=percept,
            )
        elif percept.modality == PerceptionModality.STIGMERGY:
            # High-salience marks generate investigation actions
            return CandidateAction(
                action_type="investigate_mark",
                target=percept.data.get("file_path", ""),
                description=percept.observation,
                source_percept=percept,
            )
        elif percept.modality == PerceptionModality.SIGNALS:
            return CandidateAction(
                action_type="process_signal",
                target=percept.data.get("source", ""),
                description=percept.observation,
                source_percept=percept,
            )
        elif percept.modality == PerceptionModality.DEADLINES:
            return CandidateAction(
                action_type="deadline_action",
                target=percept.data.get("deadline_name", ""),
                description=percept.observation,
                source_percept=percept,
            )
        elif percept.modality == PerceptionModality.FILESYSTEM:
            return CandidateAction(
                action_type="filesystem_check",
                target=percept.data.get("path", ""),
                description=percept.observation,
                source_percept=percept,
            )

        return None

    # ---- PHASE 3: COMMIT ----

    async def commit(self, candidate: CandidateAction) -> dict[str, Any]:
        """Execute a candidate action through the action handler.

        Pre-flight checks:
        1. Cost budget check
        2. Loop detection
        3. Checkpoint state
        """
        # Pre-flight: cost check
        if self.cost_ledger.should_stop():
            logger.warning("Budget exhausted, skipping action: %s", candidate.action_type)
            self.total_actions_skipped += 1
            return {"skipped": True, "reason": "budget_exhausted"}

        # Pre-flight: loop check
        loop_result = self.loop_detector.check()
        if loop_result.should_break:
            logger.warning(
                "Loop detected (%s), breaking: %s",
                loop_result.severity.value, loop_result.recommendation,
            )
            self.total_actions_skipped += 1
            return {"skipped": True, "reason": "loop_detected", "loop": loop_result.recommendation}

        # Checkpoint state before action
        self._save_cycle_state()

        # Execute
        result: dict[str, Any] = {"executed": False}
        if self.action_handler:
            try:
                handler_result = await asyncio.wait_for(
                    self.action_handler(candidate),
                    timeout=120.0,
                )
                if not isinstance(handler_result, dict):
                    result = {"executed": False, "error": "invalid_handler_result"}
                    logger.error(
                        "Action handler returned non-dict result for %s: %r",
                        candidate.action_type,
                        handler_result,
                    )
                else:
                    result = dict(handler_result)
                    if "executed" not in result:
                        result["executed"] = True
                    if result.get("executed"):
                        self.total_actions_taken += 1
            except asyncio.TimeoutError:
                result = {"executed": False, "error": "timeout"}
                logger.error("Action timed out: %s", candidate.action_type)
            except Exception as e:
                result = {"executed": False, "error": str(e)}
                logger.error("Action failed: %s — %s", candidate.action_type, e)

        # Record for loop detection
        self.loop_detector.record(ActionRecord(
            action_type=candidate.action_type,
            target=candidate.target,
            result="success" if result.get("executed") else "error",
            error_type=result.get("error", ""),
        ))

        return result

    # ---- PHASE 4: VERIFY ----

    async def verify(self, candidate: CandidateAction, result: dict[str, Any]) -> float:
        """Verify action outcome and update precision.

        Returns the prediction error (used for precision updating).
        """
        if not result.get("executed"):
            prediction_error = 0.5
            self._update_precision(prediction_error)
            self.world_model.total_prediction_errors += prediction_error
            return prediction_error

        # Run environmental verification
        try:
            verification = await verify_action(
                action_id=candidate.id,
                action_type=candidate.action_type,
                target=candidate.target,
            )
        except Exception as e:
            prediction_error = 1.0
            self._update_precision(prediction_error)
            self.world_model.total_prediction_errors += prediction_error
            logger.error("Verification failed: %s — %s", candidate.action_type, e)
            return prediction_error

        prediction_error = verification.prediction_error

        # Update precision (EMA)
        self._update_precision(prediction_error)

        # Update world model
        self.world_model.total_prediction_errors += prediction_error
        verification_passed = getattr(verification, "passed", None)
        if verification_passed is None:
            verification_overall = getattr(verification, "overall", None)
            verification_passed = verification_overall not in {"fail", "error"}

        if verification_passed:
            self.world_model.update_expectations()
        else:
            logger.warning(
                "Skipping world model update after failed verification: %s %s",
                candidate.action_type,
                candidate.target,
            )

        return prediction_error

    def _update_precision(self, prediction_error: float) -> None:
        """Update precision via exponential moving average.

        Small errors → precision increases → system acts more decisively.
        Large errors → precision decreases → system becomes more cautious.

        Asymmetric alpha: fast reaction to surprise (0.3), slow calm-down (0.05).
        Linear target: error=0.9 → target=0.1 (drops hard, unlike the old
        1/(1+error) formula which could never drop below 0.5).
        """
        # Asymmetric alpha: surprise accelerates, calm decelerates
        alpha = 0.3 if prediction_error > 0.3 else 0.05
        target = max(0.05, 1.0 - prediction_error)
        self.precision = (1 - alpha) * self.precision + alpha * target
        self.precision = max(0.05, min(0.95, self.precision))
        self.precision_history.append(self.precision)

        # Keep history bounded
        if len(self.precision_history) > self.config.prediction_error_window:
            self.precision_history = self.precision_history[-self.config.prediction_error_window:]

    # ---- MAIN LOOP ----

    async def run(self, shutdown_event: asyncio.Event | None = None) -> None:
        """Run the perception-action loop until shutdown.

        This replaces orchestrate_live's five concurrent loops.
        """
        shutdown = shutdown_event or asyncio.Event()
        logger.info(
            "Perception-action loop starting (precision=%.2f, period=%.0fs)",
            self.precision, self.current_period,
        )

        while not shutdown.is_set():
            cycle_start = time.monotonic()
            self.cycle_count += 1

            try:
                # Quiet hours: extend period
                if self._is_quiet_hours():
                    await asyncio.wait_for(
                        shutdown.wait(),
                        timeout=self.config.max_period_seconds,
                    )
                    continue

                # PHASE 1: PERCEIVE
                percepts = await self.perceive()

                if not percepts:
                    # Nothing to do — wait for next cycle
                    await asyncio.wait_for(
                        shutdown.wait(),
                        timeout=self.current_period,
                    )
                    continue

                # PHASE 2: DELIBERATE
                candidates = await self.deliberate(percepts)

                # PHASE 3 + 4: COMMIT + VERIFY for each candidate
                for candidate in candidates:
                    if shutdown.is_set():
                        break

                    result = await self.commit(candidate)
                    if result.get("skipped"):
                        continue

                    await self.verify(candidate, result)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Cycle %d error: %s", self.cycle_count, e)
                # On error, increase uncertainty → shorten next cycle
                self._update_precision(1.0)

            # Wait for next cycle (adaptive period)
            elapsed = time.monotonic() - cycle_start
            self.last_cycle_time = elapsed
            wait_time = max(0, self.current_period - elapsed)

            if wait_time > 0:
                try:
                    await asyncio.wait_for(shutdown.wait(), timeout=wait_time)
                except asyncio.TimeoutError:
                    pass  # Normal — timeout means it's time for next cycle

            # Log cycle summary periodically
            if self.cycle_count % 10 == 0:
                logger.info(
                    "Cycle %d: precision=%.2f period=%.0fs actions=%d/%d percepts=%d",
                    self.cycle_count, self.precision, self.current_period,
                    self.total_actions_taken, self.total_actions_taken + self.total_actions_skipped,
                    len(self.percepts_buffer),
                )

        logger.info("Perception-action loop stopped after %d cycles", self.cycle_count)
        self._save_cycle_state()

    # ---- State persistence ----

    def _save_cycle_state(self) -> None:
        """Save current loop state to disk for crash recovery."""
        state = {
            "cycle_count": self.cycle_count,
            "precision": self.precision,
            "current_period": self.current_period,
            "total_actions_taken": self.total_actions_taken,
            "total_actions_skipped": self.total_actions_skipped,
            "precision_history": self.precision_history[-10:],
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            state_file = self._state_dir / "loop_state.json"
            state_file.write_text(json.dumps(state, indent=2))
        except Exception as e:
            logger.error("Failed to save loop state: %s", e)

    def load_state(self) -> bool:
        """Load previous loop state from disk (for crash recovery).

        Returns True if state was loaded successfully.
        """
        state_file = self._state_dir / "loop_state.json"
        if not state_file.exists():
            return False

        try:
            state = json.loads(state_file.read_text())
            self.cycle_count = state.get("cycle_count", 0)
            self.precision = state.get("precision", self.config.initial_precision)
            self.total_actions_taken = state.get("total_actions_taken", 0)
            self.total_actions_skipped = state.get("total_actions_skipped", 0)
            self.precision_history = state.get("precision_history", [])
            logger.info(
                "Loaded loop state: cycle=%d precision=%.2f",
                self.cycle_count, self.precision,
            )
            return True
        except Exception as e:
            logger.error("Failed to load loop state: %s", e)
            return False

    def status(self) -> dict[str, Any]:
        """Return current loop status for monitoring."""
        return {
            "running": True,
            "cycle_count": self.cycle_count,
            "precision": round(self.precision, 3),
            "current_period_seconds": round(self.current_period, 1),
            "total_actions_taken": self.total_actions_taken,
            "total_actions_skipped": self.total_actions_skipped,
            "last_cycle_seconds": round(self.last_cycle_time, 2),
            "quiet_hours": self._is_quiet_hours(),
            "loop_detector_total": self.loop_detector.total_actions,
            "budget_utilization": round(self.cost_ledger.budget_utilization() * 100, 1),
        }


# ---------------------------------------------------------------------------
# Built-in sensors
# ---------------------------------------------------------------------------

def _tail_marks(path: Path, max_lines: int = 200) -> list[str]:
    """Read last *max_lines* from a JSONL file via seek-from-end.

    Returns raw JSON strings (no parsing). Fast even on 500KB+ files
    because it only reads ~25KB from the tail.
    """
    if not path.exists():
        return []
    try:
        size = path.stat().st_size
        if size == 0:
            return []
        # For small files, just read the whole thing
        if size < 32_768:  # 32KB
            with open(path, "r") as f:
                return [ln for ln in f.read().splitlines() if ln.strip()][-max_lines:]
        # For large files, seek from end
        chunk_size = min(size, max_lines * 256)  # ~256 bytes per line estimate
        with open(path, "rb") as f:
            f.seek(max(0, size - chunk_size))
            if f.tell() > 0:
                f.readline()  # discard partial first line
            raw = f.read().decode("utf-8", errors="replace")
        lines = [ln for ln in raw.splitlines() if ln.strip()]
        return lines[-max_lines:]
    except Exception as e:
        logger.error("_tail_marks error: %s", e)
        return []


async def stigmergy_sensor() -> list[Percept]:
    """Sense stigmergy marks — high-salience marks become percepts.

    Uses tail-read (last 200 lines) instead of loading the entire JSONL
    file, so this completes in <1s even on a 500KB marks file.
    """
    from dharma_swarm.stigmergy import StigmergyStore, StigmergicMark

    store = StigmergyStore()
    percepts: list[Percept] = []

    try:
        # Cheap pre-check: if no marks at all, bail immediately
        if store.density() == 0:
            return percepts

        # Tail-read last 200 lines instead of full file load
        raw_lines = _tail_marks(store._marks_file, max_lines=200)
        for line in raw_lines:
            try:
                mark = StigmergicMark.model_validate_json(line)
            except Exception:
                continue
            if mark.salience >= 0.6 and mark.source != "test":
                percepts.append(Percept(
                    modality=PerceptionModality.STIGMERGY,
                    observation=mark.observation[:200],
                    salience=mark.salience,
                    data={
                        "file_path": mark.file_path,
                        "agent": mark.agent,
                        "action": mark.action,
                        "mark_id": mark.id,
                    },
                ))

        # Sort by salience descending, limit to 5
        percepts.sort(key=lambda p: p.salience, reverse=True)
        percepts = percepts[:5]
    except Exception as e:
        logger.error("Stigmergy sensor error: %s", e)

    return percepts


async def health_sensor() -> list[Percept]:
    """Sense daemon health — dead daemons become high-salience percepts."""
    percepts: list[Percept] = []
    daemon_pids = {
        "dharma_swarm": Path.home() / ".dharma" / "daemon.pid",
        "mycelium": Path.home() / ".dharma" / "mycelium" / "daemon.pid",
    }

    for name, pid_file in daemon_pids.items():
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                try:
                    os.kill(pid, 0)
                    # Alive — low salience
                except ProcessLookupError:
                    # Dead — high salience
                    percepts.append(Percept(
                        modality=PerceptionModality.HEALTH,
                        observation=f"Daemon {name} PID {pid} is DEAD (stale PID file)",
                        salience=0.9,
                        data={"target": name, "pid": pid, "pid_file": str(pid_file)},
                    ))
            except ValueError:
                percepts.append(Percept(
                    modality=PerceptionModality.HEALTH,
                    observation=f"Daemon {name} PID file corrupt",
                    salience=0.8,
                    data={"target": name, "pid_file": str(pid_file)},
                ))

    return percepts


async def signal_sensor() -> list[Percept]:
    """Sense cross-instance signals from agni-workspace."""
    percepts: list[Percept] = []
    signal_file = Path.home() / "agni-workspace" / "signals" / "agni_to_mac.jsonl"

    if not signal_file.exists():
        return percepts

    try:
        # Read last 10 lines (most recent signals)
        lines = signal_file.read_text().splitlines()
        for line in lines[-10:]:
            line = line.strip()
            if not line:
                continue
            try:
                sig = json.loads(line)
                priority_salience = {
                    "critical": 0.95,
                    "high": 0.8,
                    "normal": 0.5,
                    "low": 0.3,
                }
                percepts.append(Percept(
                    modality=PerceptionModality.SIGNALS,
                    observation=sig.get("message", "")[:200],
                    salience=priority_salience.get(sig.get("priority", "normal"), 0.5),
                    data={
                        "source": sig.get("from", "unknown"),
                        "type": sig.get("type", "unknown"),
                        "proposed_action": sig.get("proposed_action", ""),
                    },
                ))
            except json.JSONDecodeError:
                continue
    except Exception as e:
        logger.error("Signal sensor error: %s", e)

    return percepts
