"""Shared progress protocol for overnight loop templates.

The loop templates already write detailed JSONL traces. This module adds a
small, durable state file that answers the operator questions the raw traces
do not:

- What is this loop trying to optimize?
- Did the latest iteration improve the objective?
- What should the loop do next?
- Is the loop converging, stalling, or regressing?
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ProgressSnapshot:
    """Operator-facing snapshot for a loop."""

    loop_name: str
    objective: str
    status: str
    iteration: int
    target_metric: dict[str, Any]
    current_metric: dict[str, Any]
    best_metric: dict[str, Any]
    verifier: dict[str, Any]
    artifact_delta: dict[str, Any]
    next_best_task: str
    progress_delta: float = 0.0
    plateau_streak: int = 0
    notes: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LoopProgressTracker:
    """Persist the latest state and append a compact history."""

    def __init__(self, loop_name: str, log_dir: Path) -> None:
        self.loop_name = loop_name
        self.log_dir = log_dir
        self.snapshot_path = log_dir / f"{loop_name}_progress.json"
        self.history_path = log_dir / f"{loop_name}_progress.jsonl"

    def start(self, objective: str, config: dict[str, Any]) -> None:
        self._append({
            "event": "loop_start",
            "loop_name": self.loop_name,
            "objective": objective,
            "config": config,
            "timestamp": _utc_now(),
        })

    def record(self, snapshot: ProgressSnapshot) -> None:
        payload = snapshot.to_dict()
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        self.snapshot_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        self._append({"event": "iteration", **payload})

    def finish(self, summary: dict[str, Any]) -> None:
        self._append({
            "event": "loop_end",
            "loop_name": self.loop_name,
            "summary": summary,
            "timestamp": _utc_now(),
        })

    def _append(self, payload: dict[str, Any]) -> None:
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, default=str) + "\n")
