"""Unified trace schema for the eval plane.

Every evaluation signal -- test results, health anomalies, prediction errors,
flywheel metrics, hook outputs -- lands as an EvalTrace appended to a single
JSONL file at ~/.dharma/evals/traces.jsonl.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

_DEFAULT_PATH = Path.home() / ".dharma" / "evals" / "traces.jsonl"
_VALID_SOURCES = frozenset({"eval", "health", "inference", "flywheel", "hook"})


@dataclass(slots=True)
class EvalTrace:
    """A single evaluation event."""

    timestamp: float
    source: str  # "eval" | "health" | "inference" | "flywheel" | "hook"
    name: str
    passed: Optional[bool]
    value: float
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.source not in _VALID_SOURCES:
            raise ValueError(f"source must be one of {sorted(_VALID_SOURCES)}, got {self.source!r}")

    def to_jsonl_line(self) -> str:
        """Serialize to a single JSON string (no trailing newline)."""
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def from_eval_result(cls, name: str, passed: bool, duration_s: float) -> EvalTrace:
        """Create a trace from an eval/test result."""
        return cls(timestamp=time.time(), source="eval", name=name,
                   passed=passed, value=duration_s, metadata={"unit": "seconds"})

    @classmethod
    def from_prediction_error(cls, agent: str, error: float, free_energy: float) -> EvalTrace:
        """Create a trace from an active-inference prediction error."""
        return cls(timestamp=time.time(), source="inference",
                   name=f"prediction_error:{agent}", passed=None, value=error,
                   metadata={"free_energy": free_energy, "agent": agent})

    @classmethod
    def from_health_anomaly(cls, anomaly_type: str, severity: float) -> EvalTrace:
        """Create a trace from a health-monitor anomaly."""
        return cls(timestamp=time.time(), source="health",
                   name=f"anomaly:{anomaly_type}", passed=False, value=severity,
                   metadata={"anomaly_type": anomaly_type})


class TraceLog:
    """Append-only JSONL log of EvalTrace records."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path: Path = path or _DEFAULT_PATH

    def append(self, trace: EvalTrace) -> None:
        """Append a single trace to the log file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a") as fh:
            fh.write(trace.to_jsonl_line() + "\n")

    def recent(self, n: int = 20) -> list[EvalTrace]:
        """Return the last *n* traces (oldest first)."""
        if not self.path.exists():
            return []
        lines: list[str] = []
        with open(self.path) as fh:
            for line in fh:
                s = line.strip()
                if s:
                    lines.append(s)
        out: list[EvalTrace] = []
        for raw in lines[-n:]:
            try:
                out.append(EvalTrace(**json.loads(raw)))
            except (json.JSONDecodeError, TypeError):
                continue
        return out

    def summary(self) -> dict:
        """Count by source + pass rate for eval traces."""
        by_source: dict[str, int] = {}
        eval_total = eval_passed = 0
        if not self.path.exists():
            return {"by_source": by_source, "eval_pass_rate": None}
        with open(self.path) as fh:
            for line in fh:
                s = line.strip()
                if not s:
                    continue
                try:
                    d = json.loads(s)
                except json.JSONDecodeError:
                    continue
                src = d.get("source", "unknown")
                by_source[src] = by_source.get(src, 0) + 1
                if src == "eval" and d.get("passed") is not None:
                    eval_total += 1
                    if d["passed"]:
                        eval_passed += 1
        rate: Optional[float] = eval_passed / eval_total if eval_total else None
        return {"by_source": by_source, "eval_pass_rate": rate}
