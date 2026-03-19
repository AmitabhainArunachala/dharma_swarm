"""S4 Environmental Intelligence -- zeitgeist awareness.

Beer's Viable System Model System 4: outside-and-future awareness.
Scans local files for research-relevant signals and optionally uses
``claude -p`` subprocess for AI landscape scanning (when available).

Output: ``~/.dharma/meta/zeitgeist.md`` + ``zeitgeist.jsonl``
Daily cadence.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from dharma_swarm.models import _new_id, _utc_now

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class ZeitgeistSignal(BaseModel):
    """A detected environmental signal.

    Attributes:
        id: Unique signal identifier.
        source: Origin of the signal (local_scan, claude_scan, manual).
        category: Signal classification bucket.
        title: Human-readable summary.
        relevance_score: Relevance to active research, 0.0--1.0.
        keywords: Matched keywords that triggered the signal.
        description: Extended explanation.
        timestamp: UTC timestamp of detection.
    """

    id: str = Field(default_factory=_new_id)
    source: str  # "local_scan", "claude_scan", "manual"
    category: str  # "competing_research", "tool_release", "methodology", "threat", "opportunity"
    title: str
    relevance_score: float = 0.0
    keywords: list[str] = Field(default_factory=list)
    description: str = ""
    timestamp: datetime = Field(default_factory=_utc_now)


# ---------------------------------------------------------------------------
# Keyword dictionaries
# ---------------------------------------------------------------------------

# Keywords relevant to the two active research tracks (R_V + URA).
RESEARCH_KEYWORDS: set[str] = {
    "mechanistic interpretability",
    "participation ratio",
    "self-reference",
    "recursive",
    "eigenform",
    "value matrix",
    "attention head",
    "contraction",
    "phase transition",
    "consciousness",
    "self-model",
    "strange loop",
    "GEB",
    "fixed point",
    "transformer geometry",
    "representation collapse",
    "SAE",
    "sparse autoencoder",
    "circuit",
    "superposition",
}

# Keywords that indicate competitive or contradictory external work.
THREAT_KEYWORDS: set[str] = {
    "scooped",
    "preprint",
    "arxiv",
    "competing",
    "similar finding",
    "reproduced",
    "replicated",
    "contradicts",
}


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


class ZeitgeistScanner:
    """S4 scanner that detects research-relevant environmental signals.

    The scanner inspects local state (shared notes, stigmergy density) and
    optionally delegates to ``claude -p`` for broader landscape awareness.
    Results are persisted as a Markdown summary and a JSONL log.

    Args:
        state_dir: Root of the ``.dharma`` state tree.  Defaults to
            ``~/.dharma``.
    """

    def __init__(self, state_dir: Path | None = None) -> None:
        self._state_dir = state_dir or (Path.home() / ".dharma")
        self._meta_dir = self._state_dir / "meta"
        self._signals: list[ZeitgeistSignal] = []
        self._output_path = self._meta_dir / "zeitgeist.md"
        self._log_path = self._meta_dir / "zeitgeist.jsonl"

    # -- public API ---------------------------------------------------------

    async def scan(self) -> list[ZeitgeistSignal]:
        """Run all available scan sources and persist results.

        Returns:
            List of newly detected signals.
        """
        self._signals = []

        # Always do local scan
        local_signals = await self._scan_local()
        self._signals.extend(local_signals)

        # Try claude scan if not in Claude Code session
        if not os.environ.get("CLAUDECODE"):
            try:
                claude_signals = await self._scan_claude()
                self._signals.extend(claude_signals)
            except Exception as exc:
                logger.debug("Claude scan unavailable: %s", exc)

        # Persist
        self._save()

        return self._signals

    def keyword_relevance(self, text: str) -> float:
        """Score *text* relevance against ``RESEARCH_KEYWORDS``.

        Returns:
            Float in [0.0, 1.0].  One point per keyword match, capped
            at 5 (= 1.0).
        """
        text_lower = text.lower()
        matches = sum(1 for kw in RESEARCH_KEYWORDS if kw.lower() in text_lower)
        return min(1.0, matches / 5.0)

    def detect_threats(self, text: str) -> list[str]:
        """Return threat keywords found in *text*."""
        text_lower = text.lower()
        return [kw for kw in THREAT_KEYWORDS if kw.lower() in text_lower]

    @property
    def signals(self) -> list[ZeitgeistSignal]:
        """Return a copy of the most-recently scanned signals."""
        return list(self._signals)

    @property
    def latest_threats(self) -> list[ZeitgeistSignal]:
        """Return signals classified as ``threat``."""
        return [s for s in self._signals if s.category == "threat"]

    # -- scan sources -------------------------------------------------------

    async def _scan_local(self) -> list[ZeitgeistSignal]:
        """Scan local state files for research-relevant signals."""
        signals: list[ZeitgeistSignal] = []

        # Check shared notes for mentions of external work
        shared_dir = self._state_dir / "shared"
        if shared_dir.exists():
            note_paths = sorted(
                shared_dir.glob("*.md"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:10]
            for note_path in note_paths:
                try:
                    text = note_path.read_text()
                    text_lower = text.lower()
                    matched_kw = [
                        kw for kw in RESEARCH_KEYWORDS if kw.lower() in text_lower
                    ]
                    threat_kw = [
                        kw for kw in THREAT_KEYWORDS if kw.lower() in text_lower
                    ]

                    if matched_kw:
                        relevance = min(1.0, len(matched_kw) / 5.0)
                        category = "threat" if threat_kw else "methodology"
                        signals.append(
                            ZeitgeistSignal(
                                source="local_scan",
                                category=category,
                                title=f"Keywords in {note_path.name}",
                                relevance_score=round(relevance, 2),
                                keywords=matched_kw[:5],
                                description=(
                                    f"Found {len(matched_kw)} research keywords"
                                    + (
                                        f", {len(threat_kw)} threat keywords"
                                        if threat_kw
                                        else ""
                                    )
                                ),
                            )
                        )
                except Exception:
                    continue

        # Check stigmergy marks for density signals
        marks_path = self._state_dir / "stigmergy" / "marks.jsonl"
        if marks_path.exists():
            try:
                content = marks_path.read_text().strip()
                if content:
                    lines = content.split("\n")
                    if len(lines) > 1000:
                        signals.append(
                            ZeitgeistSignal(
                                source="local_scan",
                                category="opportunity",
                                title="High stigmergy density",
                                relevance_score=0.3,
                                description=f"{len(lines)} marks indicate active colony intelligence",
                            )
                        )
            except Exception:
                pass

        return signals

    async def _scan_claude(self) -> list[ZeitgeistSignal]:
        """Use ``claude -p`` for AI landscape scan.

        Currently a stub that returns no signals.  A real implementation
        would invoke ``claude -p`` with a structured prompt and parse the
        JSON response.
        """
        return []

    # -- persistence --------------------------------------------------------

    def _save(self) -> None:
        """Persist signals to disk as JSONL log and Markdown summary."""
        self._meta_dir.mkdir(parents=True, exist_ok=True)

        # Append to JSONL log
        with open(self._log_path, "a") as fh:
            for sig in self._signals:
                fh.write(sig.model_dump_json() + "\n")

        # Write summary markdown
        now_str = _utc_now().strftime("%Y-%m-%d %H:%M UTC")
        lines: list[str] = [f"# Zeitgeist -- {now_str}\n"]
        for sig in self._signals:
            lines.append(
                f"- [{sig.category}] {sig.title} (relevance={sig.relevance_score})"
            )
            if sig.keywords:
                lines.append(f"  Keywords: {', '.join(sig.keywords)}")
        if not self._signals:
            lines.append("No signals detected.")
        self._output_path.write_text("\n".join(lines) + "\n")

    # -- loading historical signals -----------------------------------------

    def load_history(self) -> list[ZeitgeistSignal]:
        """Load all previously logged signals from the JSONL file.

        Returns:
            List of ``ZeitgeistSignal`` instances, oldest first.
        """
        signals: list[ZeitgeistSignal] = []
        if not self._log_path.exists():
            return signals
        try:
            for line in self._log_path.read_text().strip().split("\n"):
                if line.strip():
                    signals.append(ZeitgeistSignal.model_validate_json(line))
        except Exception as exc:
            logger.warning("Failed to load zeitgeist history: %s", exc)
        return signals

    def clear(self) -> None:
        """Reset in-memory signal list (does not delete persisted files)."""
        self._signals = []

    def _parse_witness_timestamp(self, value: Any) -> datetime | None:
        """Parse witness timestamps from append-only logs into UTC datetimes."""
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    # -- S3↔S4 bridge --------------------------------------------------

    async def ingest_gate_patterns(self, window_hours: float = 24) -> list[ZeitgeistSignal]:
        """S3->S4: Read gate results and detect operational patterns.

        This closes the S3<->S4 gap identified in the VSM audit.
        Gates (S3) produce witness logs; zeitgeist (S4) detects patterns in them.

        Args:
            window_hours: How far back to look in witness logs.

        Returns:
            List of newly generated signals from gate pattern analysis.
        """
        witness_dir = self._state_dir / "witness"
        if not witness_dir.exists():
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        total = 0
        outcomes: dict[str, int] = {"PASS": 0, "BLOCKED": 0, "WARN": 0}

        for log_file in sorted(witness_dir.glob("witness_*.jsonl"), reverse=True):
            try:
                for line in log_file.read_text().splitlines():
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts = self._parse_witness_timestamp(entry.get("ts"))
                    if ts is None:
                        continue
                    if ts < cutoff:
                        continue
                    total += 1
                    outcome = entry.get("outcome", "").upper()
                    if outcome in outcomes:
                        outcomes[outcome] += 1
            except Exception:
                continue

        if total == 0:
            return []

        signals: list[ZeitgeistSignal] = []
        block_rate = outcomes["BLOCKED"] / total
        review_rate = outcomes["WARN"] / total

        if block_rate > 0.3:
            sig = ZeitgeistSignal(
                source="gate_pattern",
                category="threat",
                title="High gate block rate",
                relevance_score=round(min(1.0, block_rate), 2),
                keywords=["gate", "block", "safety"],
                description=(
                    f"{outcomes['BLOCKED']}/{total} gate checks blocked "
                    f"({block_rate:.0%}) in last {window_hours}h"
                ),
            )
            signals.append(sig)

        if review_rate > 0.5:
            sig = ZeitgeistSignal(
                source="gate_pattern",
                category="opportunity",
                title="Many reviews suggest evolving gate parameters",
                relevance_score=round(min(1.0, review_rate * 0.8), 2),
                keywords=["gate", "review", "evolution"],
                description=(
                    f"{outcomes['WARN']}/{total} gate checks triggered review "
                    f"({review_rate:.0%}) in last {window_hours}h"
                ),
            )
            signals.append(sig)

        self._signals.extend(signals)
        return signals

    def emit_to_gates(self) -> dict:
        """S4->S3: Summarize environmental intelligence for gate consumption.

        Returns a dict that telos_gates can read to adjust behavior.
        Keys:
            threat_level: Fraction of current signals that are threats (0.0-1.0).
            opportunity_count: Number of opportunity signals.
            latest_signals: Last 5 signal summaries for context.
        """
        total = len(self._signals)
        threat_count = sum(1 for s in self._signals if s.category == "threat")
        opportunity_count = sum(1 for s in self._signals if s.category == "opportunity")

        return {
            "threat_level": round(threat_count / total, 3) if total > 0 else 0.0,
            "opportunity_count": opportunity_count,
            "latest_signals": [
                {"category": s.category, "title": s.title, "relevance": s.relevance_score}
                for s in self._signals[-5:]
            ],
        }
