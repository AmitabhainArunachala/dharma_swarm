"""Contradiction handling helpers for AutoGrade."""

from __future__ import annotations

from dharma_swarm.auto_research.models import ResearchReport


def unresolved_high_severity_contradictions(report: ResearchReport) -> int:
    total = 0
    for contradiction in report.contradictions:
        severity = str(contradiction.get("severity", "")).strip().lower()
        status = str(contradiction.get("status", "")).strip().lower()
        if severity == "high" and status != "resolved":
            total += 1
    return total


def contradiction_handling(report: ResearchReport) -> float:
    if not report.contradictions:
        return 1.0
    unresolved = unresolved_high_severity_contradictions(report)
    if unresolved:
        return 0.0
    resolved = sum(
        1
        for contradiction in report.contradictions
        if str(contradiction.get("status", "")).strip().lower() == "resolved"
    )
    return resolved / len(report.contradictions)
