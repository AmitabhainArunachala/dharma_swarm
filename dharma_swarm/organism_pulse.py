"""The organism's canonical heartbeat.

One function. Nine stages. Measured. Traced.

    sense → interpret → constrain → propose → execute → trace → evaluate → archive → adapt

This is NOT a daemon. This is a single invocation that returns a structured PulseResult.
The orchestrator calls this. The daemon wraps this. The CLI invokes this.

Usage:
    result = await run_pulse(task="summarize today's market data", agent_configs=agents)
    print(result.overall_health, result.duration_ms)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Awaitable, Sequence

from dharma_swarm.models import _new_id, _utc_now
from dharma_swarm.invariants import InvariantSnapshot, snapshot as take_invariant_snapshot
from dharma_swarm.self_prediction import PredictionRecord, SelfPredictor
from dharma_swarm.signal_bus import (
    SignalBus,
    SIGNAL_DIVERSITY_HEALTH,
    SIGNAL_TRANSCENDENCE_MARGIN,
)
from dharma_swarm.transcendence import (
    AgentConfig,
    AggregationMethod,
    EnsembleResult,
    TranscendenceMetrics,
    TranscendenceProtocol,
)
from dharma_swarm.telos_gates import check_action, GateCheckResult

logger = logging.getLogger(__name__)

_PULSE_LOG_DIR = Path.home() / ".dharma" / "pulse"


# ---------------------------------------------------------------------------
# PulseResult
# ---------------------------------------------------------------------------


@dataclass
class PulseResult:
    """Structured result of one organism pulse."""

    pulse_id: str = ""
    started_at: str = ""
    completed_at: str = ""
    duration_ms: float = 0.0

    # Per-stage timings (stage_name → ms)
    stage_timings: dict[str, float] = field(default_factory=dict)

    # Invariant snapshot
    invariants: InvariantSnapshot | None = None

    # Prediction
    prediction: PredictionRecord | None = None
    prediction_error: float | None = None

    # Action result
    task_id: str | None = None
    task_input: str = ""
    task_result: str = ""
    agent_count: int = 0
    transcendence_metrics: TranscendenceMetrics | None = None

    # Telos gate result
    gate_decision: str = ""  # "ALLOW" | "BLOCK" | "REVIEW"

    # Adaptations
    adaptations_applied: list[str] = field(default_factory=list)

    # Health
    overall_health: str = "unknown"


# ---------------------------------------------------------------------------
# Stage helpers
# ---------------------------------------------------------------------------


def _time_stage(name: str, timings: dict[str, float]):
    """Context-manager-like helper for timing stages."""
    class _Timer:
        def __init__(self):
            self.t0 = time.monotonic()
        def done(self):
            timings[name] = round((time.monotonic() - self.t0) * 1000, 1)
    return _Timer()


# ---------------------------------------------------------------------------
# The Pulse
# ---------------------------------------------------------------------------


async def run_pulse(
    task: str | None = None,
    agent_configs: Sequence[AgentConfig] | None = None,
    *,
    call_fn: Callable[[AgentConfig, str], Awaitable[str]] | None = None,
    scorer: Callable[[str, Any], float] | None = None,
    signal_bus: SignalBus | None = None,
    aggregation: AggregationMethod = AggregationMethod.QUALITY_WEIGHTED,
    temperature: float = 0.5,
    persist: bool = True,
) -> PulseResult:
    """Execute one complete organism pulse.

    Args:
        task: The task to execute. If None, returns a health-only pulse.
        agent_configs: Agent configurations. Must span 2+ model families for transcendence.
        call_fn: Async function (AgentConfig, prompt) -> str. Required for execution.
        scorer: Scores output quality. Higher = better.
        signal_bus: For emitting health signals. Created if None.
        aggregation: Aggregation method for ensemble.
        temperature: Concentration parameter.
        persist: Whether to save pulse log to disk.

    Returns:
        PulseResult with per-stage timings, invariants, predictions, and results.
    """
    pulse_id = _new_id()
    started_at = _utc_now().isoformat()
    t_start = time.monotonic()
    timings: dict[str, float] = {}
    bus = signal_bus or SignalBus()

    result = PulseResult(
        pulse_id=pulse_id,
        started_at=started_at,
        task_input=task or "",
    )

    # ── Stage 1: SENSE ──────────────────────────────────────────────
    timer = _time_stage("sense", timings)
    invariant_snap = take_invariant_snapshot()  # Uses defaults — caller can enrich
    result.invariants = invariant_snap
    timer.done()

    # ── Stage 2: INTERPRET ──────────────────────────────────────────
    timer = _time_stage("interpret", timings)
    task_type = _classify_task(task) if task else "health_only"
    agent_count = len(agent_configs) if agent_configs else 0
    timer.done()

    # ── Stage 3: CONSTRAIN ──────────────────────────────────────────
    timer = _time_stage("constrain", timings)
    if task:
        gate_result: GateCheckResult = check_action(action="execute_task", content=task)
        result.gate_decision = gate_result.decision.value if hasattr(gate_result.decision, 'value') else str(gate_result.decision)
        blocked = result.gate_decision == "BLOCK"
    else:
        result.gate_decision = "ALLOW"
        blocked = False
    timer.done()

    if blocked:
        result.task_result = f"Blocked by telos gate: {result.gate_decision}"
        result.overall_health = invariant_snap.overall if invariant_snap else "unknown"
        result.stage_timings = timings
        result.duration_ms = round((time.monotonic() - t_start) * 1000, 1)
        result.completed_at = _utc_now().isoformat()
        if persist:
            _persist_pulse(result)
        return result

    # ── Stage 4: PROPOSE ────────────────────────────────────────────
    timer = _time_stage("propose", timings)
    predictor = SelfPredictor()
    prediction = predictor.predict(
        pulse_id=pulse_id,
        task_type=task_type,
        agent_count=agent_count,
    )
    result.prediction = prediction
    timer.done()

    # ── Stage 5: EXECUTE ────────────────────────────────────────────
    timer = _time_stage("execute", timings)
    if task and agent_configs and call_fn:
        protocol = TranscendenceProtocol(
            call_fn=call_fn,
            scorer=scorer,
            aggregation=aggregation,
            temperature=temperature,
            persist=False,  # We persist at the pulse level
        )
        from dharma_swarm.transcendence import TranscendenceTask
        t_task = TranscendenceTask(prompt=task, task_type=task_type)
        ens = await protocol.execute(t_task, agent_configs)
        result.task_result = ens.ensemble_output
        result.agent_count = ens.metrics.n_agents
        result.transcendence_metrics = ens.metrics
        result.task_id = ens.id
    elif task:
        result.task_result = "(no agents configured — task recorded but not executed)"
    timer.done()

    # ── Stage 6: TRACE ──────────────────────────────────────────────
    timer = _time_stage("trace", timings)
    # Emit signals for downstream consumers
    if result.transcendence_metrics:
        bus.emit({
            "type": SIGNAL_TRANSCENDENCE_MARGIN,
            "pulse_id": pulse_id,
            "margin": result.transcendence_metrics.transcendence_margin,
        })
        bus.emit({
            "type": SIGNAL_DIVERSITY_HEALTH,
            "pulse_id": pulse_id,
            "behavioral_diversity": result.transcendence_metrics.behavioral_div,
            "status": result.transcendence_metrics.diversity_status,
        })
    timer.done()

    # ── Stage 7: EVALUATE ───────────────────────────────────────────
    timer = _time_stage("evaluate", timings)
    duration_ms = round((time.monotonic() - t_start) * 1000, 1)

    # Score the prediction
    if prediction and task:
        success = bool(result.task_result and result.task_result != "")
        scored_prediction = predictor.score(prediction, duration_ms, success)
        result.prediction = scored_prediction
        result.prediction_error = scored_prediction.duration_error

        if scored_prediction.surprise:
            result.adaptations_applied.append(
                f"SURPRISE: duration error {scored_prediction.duration_error:.0f}ms"
            )
    timer.done()

    # ── Stage 8: ARCHIVE ────────────────────────────────────────────
    timer = _time_stage("archive", timings)
    if persist:
        _persist_pulse(result)
    timer.done()

    # ── Stage 9: ADAPT ──────────────────────────────────────────────
    timer = _time_stage("adapt", timings)
    # Emit health summary
    result.overall_health = invariant_snap.overall if invariant_snap else "unknown"

    # If transcendence metrics show low diversity, flag it
    if result.transcendence_metrics and result.transcendence_metrics.behavioral_div < 0.2:
        result.adaptations_applied.append("WARNING: low behavioral diversity (<0.2)")
    timer.done()

    # ── Finalize ────────────────────────────────────────────────────
    result.stage_timings = timings
    result.duration_ms = round((time.monotonic() - t_start) * 1000, 1)
    result.completed_at = _utc_now().isoformat()

    logger.info(
        "Pulse %s completed in %.0fms, health=%s, agents=%d",
        pulse_id, result.duration_ms, result.overall_health, result.agent_count,
    )

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _classify_task(task: str) -> str:
    """Simple task type classification based on keywords."""
    lower = task.lower()
    if any(w in lower for w in ("predict", "forecast", "probability", "will")):
        return "prediction"
    if any(w in lower for w in ("code", "implement", "function", "class", "fix")):
        return "code"
    if any(w in lower for w in ("analyze", "research", "summarize", "review")):
        return "analysis"
    return "general"


def _persist_pulse(result: PulseResult) -> None:
    """Save pulse result to JSONL log."""
    try:
        _PULSE_LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = _PULSE_LOG_DIR / "pulse_log.jsonl"
        record = {
            "pulse_id": result.pulse_id,
            "started_at": result.started_at,
            "completed_at": result.completed_at,
            "duration_ms": result.duration_ms,
            "overall_health": result.overall_health,
            "agent_count": result.agent_count,
            "gate_decision": result.gate_decision,
            "task_type": _classify_task(result.task_input) if result.task_input else "none",
            "transcended": (
                result.transcendence_metrics.transcendence_margin > 0
                if result.transcendence_metrics else None
            ),
            "prediction_error": result.prediction_error,
            "surprise": result.prediction.surprise if result.prediction else False,
            "adaptations": result.adaptations_applied,
            "stage_timings": result.stage_timings,
        }
        with open(path, "a") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
    except Exception as exc:
        logger.warning("Failed to persist pulse: %s", exc)
