"""Predictive self-model: the system predicts its own performance.

The litmus test (Cleeremans 2011): Can the system be surprised by its own behavior?

Three prediction primitives:
1. predict_completion_time(task_type, agent_count) → expected_ms
2. predict_failure_probability(task_type, agent_count) → float [0, 1]
3. score(record, actual_ms, success) → PredictionRecord with error + surprise flag

Persistence: ~/.dharma/self_model/predictions.jsonl
"""

from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PREDICTIONS_DIR = Path(os.getenv(
    "DHARMA_PREDICTIONS_DIR",
    str(Path.home() / ".dharma" / "self_model"),
))
_PREDICTIONS_FILE = _PREDICTIONS_DIR / "predictions.jsonl"

# Defaults when no history exists
_DEFAULT_DURATION_MS = 10_000.0
_DEFAULT_FAILURE_PROB = 0.2
_SURPRISE_SIGMA = 2.0  # Flag as surprise if error > 2 * historical std


@dataclass
class PredictionRecord:
    """A single self-prediction + its eventual scoring."""

    prediction_id: str
    pulse_id: str
    task_type: str
    agent_count: int
    predicted_duration_ms: float
    predicted_failure_prob: float
    actual_duration_ms: float | None = None
    actual_success: bool | None = None
    duration_error: float | None = None  # predicted - actual
    surprise: bool = False  # True if error > 2σ
    timestamp: str = ""


class SelfPredictor:
    """Maintains running statistics and generates predictions.

    Not a neural network. Not an LLM call. Just running statistics
    from historical pulse results. Simple, honest, auditable.
    """

    def __init__(self, history_path: Path | None = None) -> None:
        self._path = history_path or _PREDICTIONS_FILE
        self._history: list[PredictionRecord] = []
        self._load()

    def _load(self) -> None:
        """Load prediction history from JSONL."""
        if not self._path.exists():
            return
        try:
            for line in self._path.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                self._history.append(PredictionRecord(**{
                    k: v for k, v in data.items()
                    if k in PredictionRecord.__dataclass_fields__
                }))
        except Exception as exc:
            logger.warning("Failed to load prediction history: %s", exc)

    def _save_record(self, record: PredictionRecord) -> None:
        """Append one record to JSONL."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "a") as fh:
                fh.write(json.dumps(asdict(record), default=str) + "\n")
        except Exception as exc:
            logger.warning("Failed to save prediction: %s", exc)

    def predict(
        self,
        pulse_id: str,
        task_type: str = "general",
        agent_count: int = 1,
    ) -> PredictionRecord:
        """Generate a prediction based on historical performance.

        Uses running mean/std of past durations for the given task_type.
        If no history, returns conservative defaults.
        """
        from dharma_swarm.models import _new_id, _utc_now

        # Filter scored history for this task type
        scored = [
            r for r in self._history
            if r.actual_duration_ms is not None and r.task_type == task_type
        ]

        if scored:
            durations = [r.actual_duration_ms for r in scored if r.actual_duration_ms is not None]
            pred_duration = sum(durations) / len(durations)
            failures = sum(1 for r in scored if r.actual_success is False)
            pred_failure = failures / len(scored)
        else:
            pred_duration = _DEFAULT_DURATION_MS
            pred_failure = _DEFAULT_FAILURE_PROB

        record = PredictionRecord(
            prediction_id=_new_id(),
            pulse_id=pulse_id,
            task_type=task_type,
            agent_count=agent_count,
            predicted_duration_ms=round(pred_duration, 1),
            predicted_failure_prob=round(pred_failure, 4),
            timestamp=_utc_now().isoformat(),
        )

        self._history.append(record)
        self._save_record(record)
        return record

    def score(
        self,
        record: PredictionRecord,
        actual_ms: float,
        success: bool,
    ) -> PredictionRecord:
        """Score a prediction against actual outcome. Detect surprise."""
        record.actual_duration_ms = actual_ms
        record.actual_success = success
        record.duration_error = record.predicted_duration_ms - actual_ms

        # Detect surprise: is the error > 2σ from historical errors?
        scored = [
            r for r in self._history
            if r.duration_error is not None and r.task_type == record.task_type
        ]
        if len(scored) >= 3:
            errors = [abs(r.duration_error) for r in scored if r.duration_error is not None]
            mean_err = sum(errors) / len(errors)
            var_err = sum((e - mean_err) ** 2 for e in errors) / len(errors)
            std_err = math.sqrt(var_err) if var_err > 0 else 0.0
            record.surprise = abs(record.duration_error) > _SURPRISE_SIGMA * std_err if std_err > 0 else False
        else:
            record.surprise = False

        # Update persisted record (append the scored version)
        self._save_record(record)

        if record.surprise:
            logger.info(
                "SURPRISE: pulse %s duration error %.0fms (predicted %.0f, actual %.0f)",
                record.pulse_id, record.duration_error,
                record.predicted_duration_ms, actual_ms,
            )

        return record

    def calibration(self) -> dict[str, Any]:
        """Return calibration statistics for the self-model."""
        scored = [r for r in self._history if r.actual_duration_ms is not None]

        if not scored:
            return {"status": "insufficient_data", "count": 0}

        duration_errors = [
            abs(r.duration_error) for r in scored
            if r.duration_error is not None
        ]
        mean_abs_error = sum(duration_errors) / len(duration_errors) if duration_errors else 0.0

        success_count = sum(1 for r in scored if r.actual_success is True)
        failure_count = sum(1 for r in scored if r.actual_success is False)
        surprise_count = sum(1 for r in scored if r.surprise)

        return {
            "status": "measured",
            "total_predictions": len(scored),
            "mean_absolute_duration_error_ms": round(mean_abs_error, 1),
            "actual_failure_rate": round(
                failure_count / len(scored), 4
            ) if scored else 0.0,
            "surprise_rate": round(
                surprise_count / len(scored), 4
            ) if scored else 0.0,
            "surprise_count": surprise_count,
        }
