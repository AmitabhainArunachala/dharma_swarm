"""Review Bridge — deterministic code review findings → DarwinEngine Proposals.

Runs ruff (static analysis) + QualityForge scoring on flagged files, converts
HIGH/CRITICAL findings into Proposal objects for the evolution pipeline.

No LLM calls.  Pure Python static analysis → structured evolution input.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

from dharma_swarm.evolution import Proposal

logger = logging.getLogger(__name__)

DHARMA_SWARM_DIR = Path.home() / "dharma_swarm"
PACKAGE_DIR = DHARMA_SWARM_DIR / "dharma_swarm"

# Ruff rule severity mapping (subset — extend as needed)
_CRITICAL_PREFIXES = {"F", "S", "B"}   # pyflakes, bandit, bugbear
_HIGH_PREFIXES = {"E", "W", "C9"}      # pep8 errors, warnings, mccabe


# ---------------------------------------------------------------------------
# Ruff integration
# ---------------------------------------------------------------------------

def _run_ruff(target: Path | None = None) -> list[dict[str, Any]]:
    """Run ruff check with JSON output, return list of findings.

    Each finding is a dict with keys: code, message, filename, location, etc.
    """
    target_path = str(target or PACKAGE_DIR)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", target_path,
             "--output-format", "json", "--no-fix"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.stdout.strip():
            return json.loads(result.stdout)
        return []
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
        logger.warning("ruff check failed: %s", e)
        return []


def _classify_severity(code: str) -> str:
    """Map ruff rule code to severity: critical, high, medium, low."""
    if not code:
        return "low"
    prefix = code[0]
    if prefix in _CRITICAL_PREFIXES:
        return "critical"
    two_char = code[:2]
    if two_char in _HIGH_PREFIXES or prefix in {"E", "W"}:
        return "high"
    return "medium"


# ---------------------------------------------------------------------------
# QualityForge integration
# ---------------------------------------------------------------------------

def _score_file(path: Path) -> dict[str, float] | None:
    """Score a file with QualityForge, return score dict or None on error."""
    try:
        from dharma_swarm.quality_forge import QualityForge
        forge = QualityForge()
        score = forge.score_artifact(path)
        return {
            "stars": score.stars,
            "elegance_sub": score.elegance_sub,
            "behavioral_sub": score.behavioral_sub,
            "dharmic": score.dharmic,
        }
    except Exception as e:
        logger.warning("QualityForge failed on %s: %s", path, e)
        return None


# ---------------------------------------------------------------------------
# Finding → Proposal conversion
# ---------------------------------------------------------------------------

def _finding_to_proposal(finding: dict[str, Any], cycle_id: str | None = None) -> Proposal:
    """Convert a ruff finding into a DarwinEngine Proposal."""
    code = finding.get("code", "")
    message = finding.get("message", "")
    filename = finding.get("filename", "")
    location = finding.get("location", {})
    row = location.get("row", 0)

    # Make path relative to dharma_swarm dir
    rel_path = filename
    try:
        rel_path = str(Path(filename).relative_to(DHARMA_SWARM_DIR))
    except ValueError:
        pass

    severity = _classify_severity(code)

    return Proposal(
        component=rel_path,
        change_type="mutation",
        description=f"[{severity.upper()}] {code}: {message} (line {row})",
        spec_ref=code,
        predicted_fitness=0.6 if severity in ("critical", "high") else 0.4,
        execution_risk_level="low" if severity == "medium" else "medium",
        metadata={
            "source": "review_bridge",
            "ruff_code": code,
            "severity": severity,
            "line": row,
            "message": message,
        },
        cycle_id=cycle_id,
    )


# ---------------------------------------------------------------------------
# ReviewBridge class
# ---------------------------------------------------------------------------

class ReviewBridge:
    """Bridge from static analysis + quality scoring to evolution proposals."""

    def __init__(
        self,
        target: Path | None = None,
        min_severity: str = "high",
        max_proposals: int = 10,
    ) -> None:
        self.target = target or PACKAGE_DIR
        self.min_severity = min_severity
        self.max_proposals = max_proposals
        self._severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    def scan(self) -> list[dict[str, Any]]:
        """Run ruff, return findings filtered by min_severity."""
        findings = _run_ruff(self.target)
        min_rank = self._severity_order.get(self.min_severity, 2)
        filtered = []
        for f in findings:
            sev = _classify_severity(f.get("code", ""))
            if self._severity_order.get(sev, 3) <= min_rank:
                f["_severity"] = sev
                filtered.append(f)
        # Sort by severity (critical first)
        filtered.sort(key=lambda f: self._severity_order.get(f.get("_severity", "low"), 3))
        return filtered[:self.max_proposals]

    def score_flagged_files(self, findings: list[dict]) -> dict[str, dict]:
        """Score unique files from findings with QualityForge."""
        scored: dict[str, dict] = {}
        seen_files: set[str] = set()
        for f in findings:
            filename = f.get("filename", "")
            if filename and filename not in seen_files:
                seen_files.add(filename)
                path = Path(filename)
                if path.exists() and path.suffix == ".py":
                    score = _score_file(path)
                    if score:
                        scored[filename] = score
        return scored

    def propose(self, cycle_id: str | None = None) -> list[Proposal]:
        """Full pipeline: scan → score → convert to proposals."""
        findings = self.scan()
        if not findings:
            logger.info("ReviewBridge: no findings above %s severity", self.min_severity)
            return []

        # Score flagged files (enrichment, not gating)
        scores = self.score_flagged_files(findings)
        logger.info(
            "ReviewBridge: %d findings, %d files scored",
            len(findings), len(scores),
        )

        proposals = []
        for f in findings:
            p = _finding_to_proposal(f, cycle_id=cycle_id)
            # Enrich with QualityForge score if available
            filename = f.get("filename", "")
            if filename in scores:
                p.metadata = p.metadata or {}
                p.metadata["forge_score"] = scores[filename]
            proposals.append(p)

        return proposals

    async def scan_and_propose(self, cycle_id: str | None = None) -> list[Proposal]:
        """Async wrapper for use in orchestrate_live evolution loop."""
        return self.propose(cycle_id=cycle_id)


# ---------------------------------------------------------------------------
# CLI entry points
# ---------------------------------------------------------------------------

def cmd_review_scan() -> int:
    """Run review bridge and print findings."""
    bridge = ReviewBridge()
    proposals = bridge.propose()
    if not proposals:
        print("ReviewBridge: no findings")
        return 0
    print(f"ReviewBridge: {len(proposals)} proposals")
    print(f"{'=' * 55}")
    for p in proposals:
        sev = (p.metadata or {}).get("severity", "?")
        print(f"  [{sev.upper():8s}] {p.spec_ref}: {p.description[:70]}")
        print(f"            {p.component}")
    return 0
