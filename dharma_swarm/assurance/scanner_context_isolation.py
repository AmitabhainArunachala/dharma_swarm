"""Context assembly isolation scanner."""

from __future__ import annotations

from pathlib import Path

from dharma_swarm.assurance.report_schema import Finding, ScanReport, Severity


def _find_line(lines: list[str], needle: str) -> int:
    for idx, line in enumerate(lines, start=1):
        if needle in line:
            return idx
    return 0


def scan(
    *,
    repo_root: Path | None = None,
    changed_files: list[str] | None = None,
) -> ScanReport:
    del changed_files

    root = repo_root or Path(__file__).resolve().parents[2]
    report = ScanReport(scanner="context_isolation")
    context_file = root / "dharma_swarm" / "context.py"
    if not context_file.exists():
        return report

    try:
        lines = context_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return report

    text = "\n".join(lines)
    build_signature_line = _find_line(lines, "def build_agent_context(")
    read_signature_line = _find_line(lines, "def read_agent_notes(")
    call_line = _find_line(lines, "notes = read_agent_notes(")

    build_has_state_dir = "state_dir: Path | None = None" in text
    read_notes_is_global = "if not SHARED_DIR.exists():" in text and 'distilled_path = STATE_DIR / "context" / "distilled"' in text
    read_notes_accepts_state_dir = "def read_agent_notes(exclude_role: str | None = None, max_per_agent: int = 500, state_dir" in text
    forwards_state_dir = "read_agent_notes(exclude_role=role, max_per_agent=notes_budget // 5, state_dir=state_dir)" in text

    if build_has_state_dir and read_notes_is_global and call_line and not read_notes_accepts_state_dir and not forwards_state_dir:
        report.findings = [
            Finding(
                id="CI-001",
                severity=Severity.HIGH,
                category="state_dir_isolation_leak",
                file="dharma_swarm/context.py",
                line=call_line or build_signature_line or read_signature_line,
                description=(
                    "build_agent_context(state_dir=...) does not fully isolate swarm notes because "
                    "read_agent_notes() still reads global SHARED_DIR and STATE_DIR"
                ),
                evidence=(
                    f"build_agent_context exposes state_dir at line {build_signature_line}, "
                    f"calls read_agent_notes() at line {call_line}, and read_agent_notes() "
                    f"uses global note paths starting at line {read_signature_line}"
                ),
                proposed_fix=(
                    "Thread state_dir through read_agent_notes() and derive note/distilled paths "
                    "from the caller-provided state root"
                ),
            )
        ]
        report.recompute_summary()

    return report
