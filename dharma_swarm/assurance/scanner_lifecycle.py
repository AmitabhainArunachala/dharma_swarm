"""Canonical lifecycle representation scanner."""

from __future__ import annotations

from pathlib import Path

from dharma_swarm.assurance.report_schema import Finding, ScanReport, Severity

CANONICAL_STEPS = {
    "ActionProposal": Severity.LOW,
    "GateDecision": Severity.LOW,
    "ExecutionLease": Severity.HIGH,
    "ActionExecution": Severity.MEDIUM,
    "Outcome": Severity.LOW,
    "ValueEvent": Severity.LOW,
    "Contribution": Severity.LOW,
    "RoutingBias": Severity.MEDIUM,
    "ProjectionRefresh": Severity.MEDIUM,
}


def scan(
    *,
    repo_root: Path | None = None,
    changed_files: list[str] | None = None,
) -> ScanReport:
    del changed_files

    root = repo_root or Path(__file__).resolve().parents[2]
    report = ScanReport(scanner="lifecycle_audit")
    findings: list[Finding] = []
    fid = 0

    corpus_parts: list[str] = []
    for rel_path in (
        root / "dharma_swarm" / "telic_seam.py",
        root / "dharma_swarm" / "ontology.py",
        root / "dharma_swarm" / "orchestrator.py",
    ):
        if rel_path.exists():
            corpus_parts.append(rel_path.read_text(encoding="utf-8", errors="replace"))
    corpus = "\n".join(corpus_parts)

    for step, severity in CANONICAL_STEPS.items():
        if step in corpus:
            continue
        fid += 1
        findings.append(Finding(
            id=f"LC-{fid:03d}",
            severity=severity,
            category="missing_lifecycle_step",
            file="dharma_swarm/telic_seam.py",
            line=0,
            description=f"Canonical lifecycle step '{step}' is not represented in the current core files",
            evidence=step,
            proposed_fix=(
                "Either represent the step explicitly or document why it is intentionally absent from the lifecycle"
            ),
        ))

    report.findings = findings
    report.recompute_summary()
    return report
