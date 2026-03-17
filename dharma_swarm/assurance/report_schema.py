"""Pydantic models for assurance scanner output."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Finding(BaseModel):
    id: str
    severity: Severity
    category: str
    file: str = ""
    line: int = 0
    description: str
    evidence: str = ""
    proposed_fix: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScanSummary(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    total: int = 0


class ScanReport(BaseModel):
    scanner: str
    version: str = "1.0.0"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    findings: list[Finding] = Field(default_factory=list)
    summary: ScanSummary = Field(default_factory=ScanSummary)

    def recompute_summary(self) -> None:
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for finding in self.findings:
            counts[finding.severity.value] += 1
        self.summary = ScanSummary(**counts, total=sum(counts.values()))
