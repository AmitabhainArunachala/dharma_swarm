"""Benchmark registry for tracking eval baselines and detecting regressions.

Persists to ``~/.dharma/evals/benchmarks.json``.  Seeds four default
benchmarks on first load when the file does not yet exist.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_DEFAULT_PATH = Path.home() / ".dharma" / "evals" / "benchmarks.json"

_DEFAULT_BENCHMARKS: list[dict[str, Any]] = [
    {"name": "gate_pass_rate", "metric": "ratio", "baseline_value": 0.8, "threshold": 0.7},
    {"name": "import_health", "metric": "ratio", "baseline_value": 1.0, "threshold": 1.0},
    {"name": "test_collection", "metric": "count", "baseline_value": 5000, "threshold": 4500},
    {"name": "eval_pass_rate", "metric": "ratio", "baseline_value": 0.9, "threshold": 0.7},
]


@dataclass
class Benchmark:
    """A single tracked eval benchmark."""
    name: str
    metric: str
    baseline_value: float
    threshold: float
    last_measured: float = 0.0
    last_value: float = 0.0


class BenchmarkRegistry:
    """Registry that persists eval benchmarks as JSON and checks for regressions."""

    def __init__(self, path: Path | None = None) -> None:
        self._path: Path = path or _DEFAULT_PATH
        self._benchmarks: dict[str, Benchmark] = {}
        self.load()

    # -- persistence -----------------------------------------------------------

    def load(self) -> None:
        """Load benchmarks from disk, seeding defaults if the file is absent."""
        if self._path.exists():
            try:
                with open(self._path) as fh:
                    data = json.load(fh)
                self._benchmarks = {d["name"]: Benchmark(**d) for d in data}
                return
            except (json.JSONDecodeError, KeyError, TypeError):
                pass  # corrupt -- fall through to defaults
        self._benchmarks = {d["name"]: Benchmark(**d) for d in _DEFAULT_BENCHMARKS}
        self.save()

    def save(self) -> None:
        """Atomically write benchmarks to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps([asdict(b) for b in self._benchmarks.values()], indent=2)
        fd, tmp = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(payload)
            os.replace(tmp, self._path)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    # -- public API ------------------------------------------------------------

    def register(self, name: str, metric: str, baseline: float, threshold: float) -> Benchmark:
        """Add or update a benchmark and persist immediately."""
        bm = Benchmark(name=name, metric=metric, baseline_value=baseline, threshold=threshold)
        self._benchmarks[name] = bm
        self.save()
        return bm

    def check(self, name: str, current_value: float) -> bool:
        """Return True if *current_value* meets or exceeds the threshold.

        Raises ``KeyError`` if the benchmark has not been registered.
        """
        return current_value >= self._benchmarks[name].threshold

    def update(self, name: str, value: float) -> None:
        """Record a new measurement. Raises ``KeyError`` if unknown."""
        bm = self._benchmarks[name]
        bm.last_value = value
        bm.last_measured = time.time()
        self.save()

    def report(self) -> list[dict[str, Any]]:
        """Return all benchmarks with a ``status`` field ('ok' or 'regression')."""
        out: list[dict[str, Any]] = []
        for bm in self._benchmarks.values():
            entry = asdict(bm)
            is_ok = bm.last_measured == 0.0 or bm.last_value >= bm.threshold
            entry["status"] = "ok" if is_ok else "regression"
            out.append(entry)
        return out

    def __len__(self) -> int:
        return len(self._benchmarks)

    def __contains__(self, name: str) -> bool:
        return name in self._benchmarks
