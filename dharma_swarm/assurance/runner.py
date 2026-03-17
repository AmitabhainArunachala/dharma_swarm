"""Assurance scanner orchestration and rendering."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dharma_swarm.assurance import (
    scanner_api_envelope,
    scanner_context_isolation,
    scanner_lifecycle,
    scanner_ownership,
    scanner_providers,
    scanner_routes,
    scanner_storage,
    scanner_test_gaps,
)
from dharma_swarm.assurance.report_schema import ScanReport

SCANNER_FUNCS = (
    scanner_routes.scan,
    scanner_api_envelope.scan,
    scanner_providers.scan,
    scanner_storage.scan,
    scanner_context_isolation.scan,
    scanner_lifecycle.scan,
    scanner_ownership.scan,
    scanner_test_gaps.scan,
)
_SEVERITY_WEIGHT = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def scan_reports(
    *,
    repo_root: Path | None = None,
    changed_files: list[str] | None = None,
) -> list[ScanReport]:
    root = repo_root or Path(__file__).resolve().parents[2]
    return [
        scanner(repo_root=root, changed_files=changed_files)
        for scanner in SCANNER_FUNCS
    ]


def _report_status(report: ScanReport) -> str:
    if report.summary.critical or report.summary.high:
        return "FAIL"
    if report.summary.medium or report.summary.low:
        return "WARN"
    return "PASS"


def run_assurance(
    *,
    repo_root: Path | None = None,
    changed_files: list[str] | None = None,
) -> dict[str, Any]:
    root = repo_root or Path(__file__).resolve().parents[2]
    reports = scan_reports(repo_root=root, changed_files=changed_files)
    summary = {
        "critical": sum(report.summary.critical for report in reports),
        "high": sum(report.summary.high for report in reports),
        "medium": sum(report.summary.medium for report in reports),
        "low": sum(report.summary.low for report in reports),
        "total": sum(report.summary.total for report in reports),
        "scanners": len(reports),
    }

    status = "PASS"
    if summary["critical"] or summary["high"]:
        status = "FAIL"
    elif summary["medium"] or summary["low"]:
        status = "WARN"

    recommended_fixes: list[str] = []
    for report in reports:
        for finding in report.findings:
            if finding.proposed_fix and finding.proposed_fix not in recommended_fixes:
                recommended_fixes.append(finding.proposed_fix)

    return {
        "status": status,
        "summary": summary,
        "reports": [report.model_dump(mode="json") for report in reports],
        "recommended_fixes": recommended_fixes,
        "repo_root": str(root),
        "changed_files": list(changed_files or []),
    }


def assurance_checks(assurance_report: dict[str, Any]) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    for report_dict in assurance_report.get("reports", []):
        report = ScanReport.model_validate(report_dict)
        findings = sorted(
            report_dict.get("findings", []),
            key=lambda item: _SEVERITY_WEIGHT.get(str(item.get("severity", "")), 0),
            reverse=True,
        )
        headline = "no discrepancies detected"
        if findings:
            headline = str(findings[0].get("description", "")).strip() or headline
        checks.append(
            {
                "name": f"assurance_{report.scanner}",
                "status": _report_status(report),
                "summary": headline,
                "detail": (
                    f"critical={report.summary.critical} high={report.summary.high} "
                    f"medium={report.summary.medium} low={report.summary.low}"
                ),
            }
        )
    return checks


def render_assurance_report(assurance_report: dict[str, Any]) -> str:
    lines = [
        "Assurance Mesh:",
        (
            "  "
            f"{assurance_report.get('status', 'UNKNOWN')} "
            f"(critical={assurance_report.get('summary', {}).get('critical', 0)}, "
            f"high={assurance_report.get('summary', {}).get('high', 0)}, "
            f"medium={assurance_report.get('summary', {}).get('medium', 0)}, "
            f"low={assurance_report.get('summary', {}).get('low', 0)})"
        ),
    ]

    for report in assurance_report.get("reports", []):
        findings = report.get("findings", [])
        lines.append(
            f"  - {report.get('scanner', 'unknown')}: "
            f"{report.get('summary', {}).get('total', 0)} finding(s)"
        )
        for finding in findings[:3]:
            lines.append(
                f"    [{str(finding.get('severity', '')).upper()}] "
                f"{finding.get('file', '')}:{finding.get('line', 0)} "
                f"{finding.get('description', '')}"
            )
        extra = max(0, len(findings) - 3)
        if extra:
            lines.append(f"    ... {extra} more")

    return "\n".join(lines)
