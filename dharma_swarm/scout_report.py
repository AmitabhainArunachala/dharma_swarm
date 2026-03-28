"""Scout Report — structured output schema for domain scout agents.

Every scout writes a ScoutReport. Every synthesis agent reads them.
This is the contract between Tier 1 (scouts) and Tier 2 (synthesis).

Usage:
    from dharma_swarm.scout_report import ScoutReport, Finding, write_report, read_latest

    report = ScoutReport(
        domain="architecture",
        model="xiaomi/mimo-v2-pro",
        findings=[Finding(title="SwarmManager is a god object", severity="medium", ...)],
    )
    write_report(report)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

SCOUTS_DIR = Path.home() / ".dharma" / "scouts"


class Finding(BaseModel):
    """A single observation from a scout."""

    title: str = Field(description="One-line summary")
    severity: str = Field(
        default="info",
        description="critical | high | medium | low | info",
    )
    category: str = Field(
        default="observation",
        description="bug | regression | improvement | observation | research_lead",
    )
    description: str = Field(default="", description="Detailed explanation")
    file_path: str | None = Field(default=None, description="Relevant file if any")
    line_number: int | None = Field(default=None)
    confidence: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Scout's confidence in this finding (0-1)",
    )
    actionable: bool = Field(
        default=False,
        description="Can this be turned into a code change?",
    )
    suggested_action: str | None = Field(
        default=None,
        description="What should be done about this",
    )


class ScoutReport(BaseModel):
    """Structured report from a domain scout agent."""

    domain: str = Field(description="Scout domain: architecture, tests, routing, evolution, security, stigmergy, external")
    model: str = Field(description="Model that generated this report")
    provider: str = Field(default="openrouter", description="Provider used")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    duration_seconds: float = Field(default=0.0)
    files_read: list[str] = Field(default_factory=list)
    commands_run: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    meta_observations: str = Field(
        default="",
        description="Free-form meta-level observations (the 'reading between the lines' part)",
    )
    raw_response: str = Field(
        default="",
        description="Full model response before parsing",
    )
    token_usage: dict[str, int] = Field(default_factory=dict)
    error: str | None = Field(default=None)

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "critical")

    @property
    def actionable_count(self) -> int:
        return sum(1 for f in self.findings if f.actionable)

    @property
    def high_confidence_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.confidence >= 0.8]


def _ensure_dirs(domain: str) -> Path:
    """Ensure scout output directory exists."""
    domain_dir = SCOUTS_DIR / domain
    domain_dir.mkdir(parents=True, exist_ok=True)
    return domain_dir


def write_report(report: ScoutReport) -> Path:
    """Write a scout report to disk. Returns the path written."""
    domain_dir = _ensure_dirs(report.domain)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    report_path = domain_dir / f"{date_str}.json"

    # Atomic write
    tmp_path = report_path.with_suffix(".tmp")
    tmp_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    tmp_path.rename(report_path)

    # Also write latest symlink-like file
    latest_path = domain_dir / "latest.json"
    latest_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    # Append to JSONL log
    log_path = domain_dir / "history.jsonl"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(report.model_dump_json() + "\n")

    logger.info(
        "Scout report written: %s (%d findings, %d actionable)",
        report_path, len(report.findings), report.actionable_count,
    )
    return report_path


def read_latest(domain: str) -> ScoutReport | None:
    """Read the latest report for a domain."""
    latest = SCOUTS_DIR / domain / "latest.json"
    if not latest.exists():
        return None
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
        return ScoutReport(**data)
    except Exception as e:
        logger.warning("Failed to read scout report %s: %s", latest, e)
        return None


def read_all_latest() -> dict[str, ScoutReport]:
    """Read latest reports from all domains."""
    reports: dict[str, ScoutReport] = {}
    if not SCOUTS_DIR.exists():
        return reports
    for domain_dir in sorted(SCOUTS_DIR.iterdir()):
        if domain_dir.is_dir() and domain_dir.name != "synthesis":
            report = read_latest(domain_dir.name)
            if report is not None:
                reports[domain_dir.name] = report
    return reports


def report_summary(report: ScoutReport) -> str:
    """One-line summary for logging/display."""
    crit = report.critical_count
    act = report.actionable_count
    total = len(report.findings)
    status = "CRITICAL" if crit > 0 else "OK"
    return (
        f"[{status}] {report.domain}: {total} findings "
        f"({crit} critical, {act} actionable) "
        f"via {report.model} in {report.duration_seconds:.1f}s"
    )
