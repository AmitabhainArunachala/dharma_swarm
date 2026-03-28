"""Track comprehension debt across a repository over time.

Records per-PR scores and enables querying debt trends,
per-file hotspots, and overall trajectory. Uses append-only
JSONL for persistence -- simple, auditable, merge-friendly.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_PERSIST_PATH = Path.home() / ".dharma" / "verify" / "comprehension.jsonl"


class ComprehensionTracker:
    """Track and query comprehension debt across a repository.

    Records are appended to a JSONL file. Each record contains a PR ID,
    timestamp, overall score, comprehension debt, and files touched.

    Attributes:
        persist_path: Path to the JSONL file for persistence.
    """

    def __init__(self, persist_path: Path | None = None) -> None:
        """Initialize the tracker.

        Args:
            persist_path: Path to the JSONL persistence file.
                Defaults to ~/.dharma/verify/comprehension.jsonl.
        """
        self.persist_path = persist_path or _DEFAULT_PERSIST_PATH
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, pr_id: str, score: float, files: list[str]) -> None:
        """Append a review record.

        Args:
            pr_id: Unique identifier for the PR (e.g., "repo#123").
            score: Overall quality score in [0.0, 1.0].
            files: List of file paths reviewed in this PR.
        """
        clamped = min(max(score, 0.0), 1.0)
        entry = {
            "pr_id": pr_id,
            "timestamp": time.time(),
            "score": round(clamped, 4),
            "debt": round(1.0 - clamped, 4),
            "files": files,
        }
        with open(self.persist_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def _load_records(self) -> list[dict[str, Any]]:
        """Load all records from the persistence file."""
        if not self.persist_path.exists():
            return []
        records: list[dict[str, Any]] = []
        with open(self.persist_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return records

    def debt_by_file(self) -> dict[str, float]:
        """Compute average comprehension debt per file.

        Returns:
            Dict mapping file path to average debt (0.0-1.0).
            Files appearing in more reviews get a more stable average.
        """
        records = self._load_records()
        file_debts: dict[str, list[float]] = {}

        for record in records:
            debt = record.get("debt", 0.0)
            for filepath in record.get("files", []):
                file_debts.setdefault(filepath, []).append(debt)

        return {
            filepath: round(sum(debts) / len(debts), 4)
            for filepath, debts in file_debts.items()
            if debts
        }

    def trend(self, window_days: int = 7) -> float:
        """Compute debt trend over a time window.

        Splits the window into two halves: older and recent. Returns
        (recent_avg - older_avg). Negative means debt is decreasing
        (quality improving). Positive means debt is increasing.

        Args:
            window_days: Number of days to look back.

        Returns:
            Trend value. Positive = worsening, negative = improving,
            zero = stable or insufficient data.
        """
        records = self._load_records()
        if len(records) < 2:
            return 0.0

        now = time.time()
        cutoff = now - (window_days * 86400)
        midpoint = now - (window_days * 86400 / 2)

        recent: list[float] = []
        older: list[float] = []

        for record in records:
            ts = record.get("timestamp", 0.0)
            debt = record.get("debt", 0.0)
            if ts >= cutoff:
                if ts >= midpoint:
                    recent.append(debt)
                else:
                    older.append(debt)

        if not recent or not older:
            return 0.0

        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older)

        return round(recent_avg - older_avg, 4)

    def hotspots(self, top_n: int = 10) -> list[tuple[str, float]]:
        """Find files with the worst comprehension debt.

        Args:
            top_n: Number of top files to return.

        Returns:
            List of (file_path, avg_debt) tuples, sorted worst-first.
        """
        debts = self.debt_by_file()
        sorted_debts = sorted(debts.items(), key=lambda x: x[1], reverse=True)
        return sorted_debts[:top_n]
