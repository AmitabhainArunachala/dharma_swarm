"""Ownership boundary scanner."""

from __future__ import annotations

from pathlib import Path

from dharma_swarm.assurance.report_schema import Finding, ScanReport, Severity


def scan(
    *,
    repo_root: Path | None = None,
    changed_files: list[str] | None = None,
) -> ScanReport:
    del changed_files

    root = repo_root or Path(__file__).resolve().parents[2]
    report = ScanReport(scanner="ownership_audit")
    findings: list[Finding] = []
    fid = 0

    orchestrator = root / "dharma_swarm" / "orchestrator.py"
    ontology = root / "dharma_swarm" / "ontology.py"

    if orchestrator.exists():
        text = orchestrator.read_text(encoding="utf-8", errors="replace")
        if "OntologyRegistry" in text or "create_object(" in text:
            fid += 1
            findings.append(Finding(
                id=f"OW-{fid:03d}",
                severity=Severity.MEDIUM,
                category="orchestrator_ontology_coupling",
                file="dharma_swarm/orchestrator.py",
                line=0,
                description="Orchestrator appears to manipulate ontology objects directly",
                evidence="OntologyRegistry/create_object references detected in orchestrator",
                proposed_fix="Keep operational discipline in orchestrator and semantic truth writes in the seam/ontology layer",
            ))

    if ontology.exists():
        text = ontology.read_text(encoding="utf-8", errors="replace").lower()
        runtime_terms = [term for term in ("heartbeat", "retry", "pid", "launchd") if term in text]
        if runtime_terms:
            fid += 1
            findings.append(Finding(
                id=f"OW-{fid:03d}",
                severity=Severity.MEDIUM,
                category="ontology_runtime_leak",
                file="dharma_swarm/ontology.py",
                line=0,
                description="Ontology layer appears to mention runtime-state concerns",
                evidence=", ".join(runtime_terms),
                proposed_fix="Keep runtime coordination state out of ontology unless it is truly semantic truth",
            ))

    report.findings = findings
    report.recompute_summary()
    return report
