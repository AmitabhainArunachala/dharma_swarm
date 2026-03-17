"""Changed-file test gap scanner."""

from __future__ import annotations

import subprocess
from pathlib import Path

from dharma_swarm.assurance.report_schema import Finding, ScanReport, Severity

SOURCE_PREFIXES = ("dharma_swarm/", "api/")


def _git_changed_files(repo_root: Path) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return []

    if proc.returncode != 0:
        return []

    changed: list[str] = []
    for raw_line in proc.stdout.splitlines():
        if len(raw_line) < 4:
            continue
        status = raw_line[:2]
        if "D" in status:
            continue
        path = raw_line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        if path:
            changed.append(path)
    return changed


def _is_source_file(path: str) -> bool:
    if path.startswith("tests/"):
        return False
    return path.endswith(".py") and path.startswith(SOURCE_PREFIXES)


def _has_obvious_test(repo_root: Path, rel_path: str) -> bool:
    tests_dir = repo_root / "tests"
    if not tests_dir.exists():
        return False

    stem = Path(rel_path).stem
    exact = tests_dir / f"test_{stem}.py"
    if exact.exists():
        return True

    for test_file in tests_dir.glob("test_*.py"):
        try:
            content = test_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if stem in content or rel_path in content:
            return True
    return False


def scan(
    *,
    repo_root: Path | None = None,
    changed_files: list[str] | None = None,
) -> ScanReport:
    root = repo_root or Path(__file__).resolve().parents[2]
    report = ScanReport(scanner="test_gap")
    findings: list[Finding] = []
    fid = 0
    changes = changed_files or _git_changed_files(root)

    for rel_path in changes:
        if not _is_source_file(rel_path):
            continue
        if _has_obvious_test(root, rel_path):
            continue
        fid += 1
        findings.append(Finding(
            id=f"TG-{fid:03d}",
            severity=Severity.MEDIUM,
            category="missing_obvious_test_coverage",
            file=rel_path,
            line=0,
            description=(
                "Changed source file has no obvious paired test file or direct test reference "
                "(heuristic check)"
            ),
            evidence=rel_path,
            proposed_fix=(
                "Add or update an invariant, contract, or integration test that names this module explicitly"
            ),
        ))

    report.findings = findings
    report.recompute_summary()
    return report
