"""Harness Audit — 7-dimension system health scorecard.

Scores dharma_swarm across 7 categories (0-10 each), stores results as JSON
with historical tracking.  Self-improvement cycle reads audit score to
prioritize which categories to fix first.

Pure Python measurement — no LLM calls.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

STATE_DIR = Path.home() / ".dharma"
AUDITS_DIR = STATE_DIR / "audits"
AUDIT_HISTORY = AUDITS_DIR / "history.jsonl"
DHARMA_SWARM_DIR = Path.home() / "dharma_swarm"
PACKAGE_DIR = DHARMA_SWARM_DIR / "dharma_swarm"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class AuditScore:
    """Score for a single audit category."""
    name: str
    score: float = 0.0           # 0-10
    max_score: float = 10.0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AuditReport:
    """Full 7-dimension scorecard."""
    timestamp: str = ""
    categories: list[dict[str, Any]] = field(default_factory=list)
    overall_score: float = 0.0   # Average of all categories
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Category scorers
# ---------------------------------------------------------------------------

def _score_tool_coverage() -> AuditScore:
    """Score 1: Tool Coverage — modules registered vs actively used."""
    try:
        # Count Python modules in dharma_swarm/
        py_files = list(PACKAGE_DIR.glob("*.py"))
        total_modules = len([f for f in py_files if not f.name.startswith("_")])

        # Count modules with tests
        test_dir = DHARMA_SWARM_DIR / "tests"
        test_files = list(test_dir.glob("test_*.py")) if test_dir.exists() else []
        tested_modules = len(test_files)

        coverage_ratio = min(tested_modules / max(total_modules, 1), 1.0)
        score = coverage_ratio * 10.0

        return AuditScore(
            name="tool_coverage",
            score=round(score, 1),
            details={
                "total_modules": total_modules,
                "tested_modules": tested_modules,
                "coverage_ratio": round(coverage_ratio, 3),
            },
        )
    except Exception as e:
        return AuditScore(name="tool_coverage", details={"error": str(e)})


def _score_context_efficiency() -> AuditScore:
    """Score 2: Context Efficiency — state directory size and freshness."""
    try:
        total_size = 0
        stale_files = 0
        fresh_files = 0
        now = time.time()
        stale_threshold = 7 * 86400  # 7 days

        for path in STATE_DIR.rglob("*"):
            if path.is_file():
                total_size += path.stat().st_size
                age = now - path.stat().st_mtime
                if age > stale_threshold:
                    stale_files += 1
                else:
                    fresh_files += 1

        total_files = stale_files + fresh_files
        freshness_ratio = fresh_files / max(total_files, 1)
        size_mb = total_size / (1024 * 1024)

        # Penalize large state dirs and high stale ratio
        size_penalty = max(0, min(1, 1 - (size_mb - 50) / 200))  # Full score under 50MB
        score = (freshness_ratio * 6.0 + size_penalty * 4.0)

        return AuditScore(
            name="context_efficiency",
            score=round(min(score, 10.0), 1),
            details={
                "total_size_mb": round(size_mb, 1),
                "total_files": total_files,
                "fresh_files": fresh_files,
                "stale_files": stale_files,
                "freshness_ratio": round(freshness_ratio, 3),
            },
        )
    except Exception as e:
        return AuditScore(name="context_efficiency", details={"error": str(e)})


def _score_quality_gates() -> AuditScore:
    """Score 3: Quality Gates — telos gate configuration health."""
    try:
        from dharma_swarm.telos_gates import TelosGatekeeper

        gk = TelosGatekeeper()
        gate_count = len(gk.gates) if hasattr(gk, "gates") else 0

        # Check gate log exists
        witness_dir = STATE_DIR / "witness"
        witness_files = list(witness_dir.glob("*.jsonl")) if witness_dir.exists() else []

        score = min(gate_count, 10) + min(len(witness_files), 2)
        score = min(score / 1.2, 10.0)

        return AuditScore(
            name="quality_gates",
            score=round(score, 1),
            details={
                "gate_count": gate_count,
                "witness_logs": len(witness_files),
            },
        )
    except Exception as e:
        return AuditScore(name="quality_gates", details={"error": str(e)})


def _score_memory_persistence() -> AuditScore:
    """Score 4: Memory Persistence — agent memory banks populated."""
    try:
        memory_dir = STATE_DIR / "agent_memory"
        if not memory_dir.exists():
            return AuditScore(name="memory_persistence", score=2.0,
                              details={"status": "no memory dir"})

        banks = list(memory_dir.glob("*.json")) + list(memory_dir.glob("*.jsonl"))
        total_entries = 0
        for bank in banks:
            try:
                if bank.suffix == ".jsonl":
                    total_entries += sum(1 for _ in bank.open())
                else:
                    data = json.loads(bank.read_text())
                    total_entries += len(data) if isinstance(data, list) else 1
            except Exception:
                pass

        score = min(len(banks) * 2 + total_entries * 0.1, 10.0)

        return AuditScore(
            name="memory_persistence",
            score=round(score, 1),
            details={
                "memory_banks": len(banks),
                "total_entries": total_entries,
            },
        )
    except Exception as e:
        return AuditScore(name="memory_persistence", details={"error": str(e)})


def _score_eval_coverage() -> AuditScore:
    """Score 5: Eval Coverage — evals defined and passing."""
    try:
        from dharma_swarm.ecc_eval_harness import load_latest
        latest = load_latest()
        if not latest:
            return AuditScore(name="eval_coverage", score=0.0,
                              details={"status": "no eval results"})

        total = latest.get("total", 0)
        passed = latest.get("passed", 0)
        pass_rate = passed / max(total, 1)

        # Score: eval count contributes + pass rate contributes
        count_score = min(total, 9) * 0.5   # Max 4.5 from count
        rate_score = pass_rate * 5.5          # Max 5.5 from pass rate
        score = count_score + rate_score

        return AuditScore(
            name="eval_coverage",
            score=round(min(score, 10.0), 1),
            details={
                "total_evals": total,
                "passed": passed,
                "pass_rate": round(pass_rate, 3),
            },
        )
    except Exception as e:
        return AuditScore(name="eval_coverage", details={"error": str(e)})


def _score_security_guardrails() -> AuditScore:
    """Score 6: Security Guardrails — kernel integrity, signed axioms."""
    try:
        from dharma_swarm.dharma_kernel import DharmaKernel

        kernel = DharmaKernel()
        axiom_count = len(kernel.axioms) if hasattr(kernel, "axioms") else 0

        # Check if kernel verification passes
        verified = False
        if hasattr(kernel, "verify"):
            try:
                verified = kernel.verify()
            except Exception:
                pass
        elif axiom_count > 0:
            verified = True  # Has axioms = basic integrity

        score = 5.0 if verified else 0.0
        score += min(axiom_count, 10) * 0.5

        return AuditScore(
            name="security_guardrails",
            score=round(min(score, 10.0), 1),
            details={
                "axiom_count": axiom_count,
                "kernel_verified": verified,
            },
        )
    except Exception as e:
        return AuditScore(name="security_guardrails", details={"error": str(e)})


def _score_cost_efficiency() -> AuditScore:
    """Score 7: Cost Efficiency — token spend tracking."""
    try:
        # Check for cost tracking in evolution archive
        archive_path = STATE_DIR / "evolution" / "archive.jsonl"
        if not archive_path.exists():
            return AuditScore(name="cost_efficiency", score=5.0,
                              details={"status": "no archive"})

        total_tokens = 0
        entry_count = 0
        with archive_path.open() as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    total_tokens += entry.get("tokens_used", 0)
                    entry_count += 1
                except (json.JSONDecodeError, KeyError):
                    continue

        avg_tokens = total_tokens / max(entry_count, 1)
        # Lower token use per entry = more efficient
        efficiency = max(0, 1 - avg_tokens / 10000)  # 10K tokens = 0 efficiency
        score = efficiency * 7 + 3  # Base 3 for having tracking

        return AuditScore(
            name="cost_efficiency",
            score=round(min(score, 10.0), 1),
            details={
                "total_tokens": total_tokens,
                "entry_count": entry_count,
                "avg_tokens_per_entry": round(avg_tokens, 0),
            },
        )
    except Exception as e:
        return AuditScore(name="cost_efficiency", details={"error": str(e)})


# ---------------------------------------------------------------------------
# Audit runner
# ---------------------------------------------------------------------------

ALL_SCORERS = [
    _score_tool_coverage,
    _score_context_efficiency,
    _score_quality_gates,
    _score_memory_persistence,
    _score_eval_coverage,
    _score_security_guardrails,
    _score_cost_efficiency,
]


def run_audit() -> AuditReport:
    """Run full 7-category audit and return report."""
    t0 = time.monotonic()
    categories = []
    for scorer in ALL_SCORERS:
        try:
            result = scorer()
            categories.append(result.to_dict())
        except Exception as e:
            categories.append(AuditScore(
                name=scorer.__name__.replace("_score_", ""),
                details={"error": str(e)},
            ).to_dict())

    scores = [c["score"] for c in categories]
    overall = sum(scores) / len(scores) if scores else 0.0

    report = AuditReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        categories=categories,
        overall_score=round(overall, 1),
        duration_seconds=time.monotonic() - t0,
    )
    return report


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_audit(report: AuditReport) -> Path:
    """Save audit to disk and append to history."""
    AUDITS_DIR.mkdir(parents=True, exist_ok=True)

    latest = AUDITS_DIR / "latest.json"
    latest.write_text(json.dumps(report.to_dict(), indent=2))

    with AUDIT_HISTORY.open("a") as f:
        f.write(json.dumps(report.to_dict()) + "\n")

    return latest


def load_audit_history() -> list[dict]:
    """Load audit history from JSONL."""
    if not AUDIT_HISTORY.exists():
        return []
    entries = []
    for line in AUDIT_HISTORY.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def load_latest_audit() -> dict | None:
    """Load the most recent audit report."""
    latest = AUDITS_DIR / "latest.json"
    if latest.exists():
        return json.loads(latest.read_text())
    return None


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def format_scorecard(report: dict) -> str:
    """Format audit as human-readable scorecard."""
    lines = []
    lines.append(f"Harness Audit — {report['timestamp'][:19]}")
    lines.append(f"{'=' * 55}")
    lines.append(f"  Overall: {report['overall_score']}/10")
    lines.append(f"  Duration: {report['duration_seconds']:.2f}s")
    lines.append("")

    for cat in report.get("categories", []):
        score = cat["score"]
        bar_len = int(score)
        bar = "#" * bar_len + "." * (10 - bar_len)
        lines.append(f"  {cat['name']:<25} [{bar}] {score:.1f}/10")
        if cat.get("details", {}).get("error"):
            lines.append(f"    error: {cat['details']['error'][:60]}")

    return "\n".join(lines)


def format_audit_trend(history: list[dict], last_n: int = 10) -> str:
    """Format audit trend over time."""
    recent = history[-last_n:]
    if not recent:
        return "No audit history yet."

    lines = []
    lines.append(f"Audit Trend (last {len(recent)} runs)")
    lines.append(f"{'=' * 55}")

    for run in recent:
        ts = run["timestamp"][:16]
        overall = run.get("overall_score", 0.0)
        bar_len = int(overall)
        bar = "#" * bar_len + "." * (10 - bar_len)
        lines.append(f"  {ts}  [{bar}] {overall:.1f}/10")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry points
# ---------------------------------------------------------------------------

def cmd_audit() -> int:
    """Run audit and print scorecard."""
    report = run_audit()
    save_audit(report)
    print(format_scorecard(report.to_dict()))
    return 0


def cmd_audit_trend() -> int:
    """Print audit trend."""
    history = load_audit_history()
    print(format_audit_trend(history))
    return 0
