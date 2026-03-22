"""S3* Sporadic Auditor -- random audit of system outputs for drift.

Beer's Viable System Model System 3*: random spot-checks that bypass
the normal reporting chain. Picks random recent evaluations, re-scores
deterministically, and flags drift.

Runs every 900s (configurable), picks ONE audit type randomly per tick
(Beer's paranoid-but-lazy S3*).

Audit types:
    score_drift       Re-score a recent evolution entry, check delta.
    evolution_elegance Re-run elegance scoring on recent proposals.
    notes_mimicry     Scan recent shared notes for performative language.
    stigmergy_stale   Check for stale stigmergy marks (>7 days).
"""

from __future__ import annotations

import json
import logging
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from dharma_swarm.models import _new_id, _utc_now

logger = logging.getLogger(__name__)


class AuditFinding(BaseModel):
    """Result of a single audit check.

    Attributes:
        id: Unique finding identifier.
        audit_type: Which audit produced this finding.
        severity: One of ``low``, ``medium``, ``high``.
        description: Human-readable summary.
        expected: What was expected (optional).
        actual: What was observed (optional).
        drift_magnitude: Numeric measure of deviation (0 = none).
        timestamp: When the finding was created.
    """

    id: str = Field(default_factory=_new_id)
    audit_type: str
    severity: str = "low"  # low, medium, high
    description: str
    expected: str = ""
    actual: str = ""
    drift_magnitude: float = 0.0
    timestamp: datetime = Field(default_factory=_utc_now)


class Auditor:
    """S3* sporadic auditor.

    Each call to :meth:`tick` randomly selects one audit type and
    executes it. If an anomaly is detected an :class:`AuditFinding`
    is returned and stored internally; otherwise ``None`` is returned.

    Args:
        state_dir: Root state directory (default ``~/.dharma``).
    """

    AUDIT_TYPES: tuple[str, ...] = (
        "score_drift",
        "evolution_elegance",
        "notes_mimicry",
        "stigmergy_stale",
    )

    def __init__(self, state_dir: Path | None = None) -> None:
        self._state_dir = state_dir or (Path.home() / ".dharma")
        self._findings: list[AuditFinding] = []

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def tick(self) -> AuditFinding | None:
        """Run one random audit.

        Returns:
            An ``AuditFinding`` if an anomaly was detected, else ``None``.
        """
        audit_type = random.choice(self.AUDIT_TYPES)
        return await self._run_audit(audit_type)

    async def run_specific(self, audit_type: str) -> AuditFinding | None:
        """Run a specific audit type by name.

        Args:
            audit_type: One of ``AUDIT_TYPES``.

        Returns:
            An ``AuditFinding`` if an anomaly was detected, else ``None``.

        Raises:
            ValueError: If *audit_type* is not recognized.
        """
        if audit_type not in self.AUDIT_TYPES:
            raise ValueError(
                f"Unknown audit type {audit_type!r}. "
                f"Must be one of {self.AUDIT_TYPES}"
            )
        return await self._run_audit(audit_type)

    @property
    def findings(self) -> list[AuditFinding]:
        """All accumulated findings (copies)."""
        return list(self._findings)

    def clear_findings(self) -> None:
        """Discard all accumulated findings."""
        self._findings.clear()

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def _run_audit(self, audit_type: str) -> AuditFinding | None:
        """Dispatch to the appropriate audit method."""
        try:
            if audit_type == "score_drift":
                return await self._audit_score_drift()
            elif audit_type == "evolution_elegance":
                return await self._audit_elegance()
            elif audit_type == "notes_mimicry":
                return await self._audit_notes_mimicry()
            elif audit_type == "stigmergy_stale":
                return await self._audit_stigmergy_stale()
        except Exception as exc:
            logger.debug("Audit %s failed: %s", audit_type, exc)
        return None

    # ------------------------------------------------------------------
    # Individual audits
    # ------------------------------------------------------------------

    async def _audit_score_drift(self) -> AuditFinding | None:
        """Re-score a recent evolution entry and check for drift."""
        archive_path = self._state_dir / "evolution" / "archive.jsonl"
        if not archive_path.exists():
            return None

        try:
            text = archive_path.read_text().strip()
            if not text:
                return None
            lines = text.split("\n")
            recent = lines[-min(10, len(lines)):]
            line = random.choice(recent)
            entry = json.loads(line)

            fitness = entry.get("fitness", {})
            if isinstance(fitness, dict):
                for key, val in fitness.items():
                    if isinstance(val, (int, float)) and (val < -0.01 or val > 1.01):
                        finding = AuditFinding(
                            audit_type="score_drift",
                            severity="high",
                            description=(
                                f"Fitness dimension {key}={val} "
                                f"out of [0,1] range"
                            ),
                            expected="[0.0, 1.0]",
                            actual=str(val),
                            drift_magnitude=abs(val - max(0.0, min(1.0, val))),
                        )
                        self._findings.append(finding)
                        return finding
        except Exception:
            logger.debug("Auditor finding creation failed", exc_info=True)
        return None

    async def _audit_elegance(self) -> AuditFinding | None:
        """Re-run elegance scoring on a random source file."""
        try:
            from dharma_swarm.elegance import evaluate_elegance
        except ImportError:
            return None

        src_dir = Path(__file__).parent
        py_files = list(src_dir.glob("*.py"))
        if not py_files:
            return None

        chosen = random.choice(py_files)
        try:
            source = chosen.read_text()
        except OSError:
            return None

        score = evaluate_elegance(source)

        if score.overall_score < 0.2:
            finding = AuditFinding(
                audit_type="evolution_elegance",
                severity="medium",
                description=(
                    f"{chosen.name} has low elegance score: "
                    f"{score.overall_score:.3f}"
                ),
                actual=(
                    f"overall={score.overall_score:.3f}, "
                    f"complexity={score.cyclomatic_complexity}"
                ),
                drift_magnitude=0.5 - score.overall_score,
            )
            self._findings.append(finding)
            return finding
        return None

    async def _audit_notes_mimicry(self) -> AuditFinding | None:
        """Scan recent shared notes for performative language."""
        shared_dir = self._state_dir / "shared"
        if not shared_dir.exists():
            return None

        try:
            from dharma_swarm.metrics import MetricsAnalyzer
        except ImportError:
            return None

        analyzer = MetricsAnalyzer()

        notes = sorted(
            shared_dir.glob("*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:5]

        for note in notes:
            try:
                text = note.read_text()
            except OSError:
                continue
            if analyzer.detect_mimicry(text):
                finding = AuditFinding(
                    audit_type="notes_mimicry",
                    severity="medium",
                    description=f"Mimicry detected in {note.name}",
                    actual="Performative language patterns found",
                )
                self._findings.append(finding)
                return finding
        return None

    async def _audit_stigmergy_stale(self) -> AuditFinding | None:
        """Check for stale stigmergy marks older than 7 days."""
        marks_path = self._state_dir / "stigmergy" / "marks.jsonl"
        if not marks_path.exists():
            return None

        try:
            text = marks_path.read_text().strip()
            if not text:
                return None
        except OSError:
            return None

        cutoff = (_utc_now() - timedelta(days=7)).isoformat()
        stale_count = 0
        total_count = 0

        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            total_count += 1
            try:
                mark = json.loads(stripped)
                ts = mark.get("timestamp", "")
                if ts and ts < cutoff:
                    stale_count += 1
            except json.JSONDecodeError:
                continue

        if total_count > 0 and stale_count / total_count > 0.5:
            finding = AuditFinding(
                audit_type="stigmergy_stale",
                severity="low",
                description=(
                    f"{stale_count}/{total_count} stigmergy marks "
                    f"are >7 days old"
                ),
                drift_magnitude=stale_count / total_count,
            )
            self._findings.append(finding)
            return finding
        return None

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"Auditor(state_dir={self._state_dir!r}, "
            f"findings={len(self._findings)})"
        )
