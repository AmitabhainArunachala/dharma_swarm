"""Storage/path scanner."""

from __future__ import annotations

import re
from pathlib import Path

from dharma_swarm.assurance.report_schema import Finding, ScanReport, Severity

PATH_PATTERNS = [
    re.compile(r"""Path\(\s*["']([^"']+)["']\s*\)"""),
    re.compile(r"""["'](~/[^"']+)["']"""),
    re.compile(r"""["'](/Users/[^"']+)["']"""),
    re.compile(r"""["'](~/.dharma/[^"']+)["']"""),
    re.compile(r"""["'](\.dharma/[^"']+)["']"""),
]
DELETED_PATHS = {
    "~/dgc-core",
    "~/DHARMIC_GODEL_CLAW",
    "~/dgc-core/",
    "~/DHARMIC_GODEL_CLAW/",
}
VALID_BASES = {
    "~/.dharma/",
    "~/dharma_swarm/",
    "~/mech-interp-latent-lab-phase1/",
    "~/agni-workspace/",
    "~/trishula/",
    "~/jagat_kalyan/",
    "~/Persistent-Semantic-Memory-Vault/",
    "~/.claude/",
    "~/Desktop/KAILASH ABODE OF SHIVA/",
}


def _expand_path(path_str: str) -> Path:
    if path_str.startswith("~/"):
        return Path.home() / path_str[2:]
    return Path(path_str)


def _base_check_for_path(path_str: str) -> str | None:
    if path_str.startswith("~/.dharma/"):
        return "~/.dharma/"
    if path_str.startswith("~/"):
        parts = path_str[2:].split("/", 1)
        if parts and parts[0]:
            return f"~/{parts[0]}/"
        return "~/"
    if path_str.startswith("/Users/"):
        parts = path_str.split("/")
        if len(parts) >= 5 and parts[3]:
            return "/".join(parts[:4]) + "/"
        if len(parts) >= 4:
            return "/".join(parts[:3]) + "/"
    return None


def _resolve_target_files(
    *,
    repo_root: Path | None = None,
    changed_files: list[str] | None = None,
) -> tuple[Path, list[Path]]:
    root = repo_root or Path(__file__).resolve().parents[2]
    pkg_dir = root / "dharma_swarm"

    def _eligible(candidate: Path) -> bool:
        return (
            candidate.suffix == ".py"
            and "tests" not in candidate.parts
            and "assurance" not in candidate.parts
        )

    if changed_files:
        targets: list[Path] = []
        for raw in changed_files:
            candidate = Path(raw)
            if not candidate.is_absolute():
                candidate = root / candidate
            if _eligible(candidate):
                targets.append(candidate)
        return root, targets
    return root, [path for path in pkg_dir.rglob("*.py") if _eligible(path)]


def scan(
    *,
    repo_root: Path | None = None,
    changed_files: list[str] | None = None,
) -> ScanReport:
    report = ScanReport(scanner="storage_path")
    findings: list[Finding] = []
    fid = 0
    root, target_files = _resolve_target_files(repo_root=repo_root, changed_files=changed_files)
    message_bus_locations: list[tuple[Path, int, str, str]] = []

    for pyfile in target_files:
        if not pyfile.exists():
            continue
        try:
            content = pyfile.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        lines = content.splitlines()
        for line_no, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue

            for pattern in PATH_PATTERNS:
                for match in pattern.finditer(line):
                    path_str = match.group(1)
                    for deleted in DELETED_PATHS:
                        if path_str.startswith(deleted) or path_str.rstrip("/") == deleted.rstrip("/"):
                            fid += 1
                            findings.append(Finding(
                                id=f"SP-{fid:03d}",
                                severity=Severity.HIGH,
                                category="deleted_path_reference",
                                file=str(pyfile.relative_to(root)),
                                line=line_no,
                                description=f"References deleted path '{path_str}'",
                                evidence=stripped,
                                proposed_fix="Update to the current path or remove the stale reference",
                            ))

                    if path_str.startswith("~/") or path_str.startswith("/Users/"):
                        base_check = _base_check_for_path(path_str)
                        if (
                            base_check
                            and not _expand_path(base_check).exists()
                            and base_check not in VALID_BASES
                        ):
                            fid += 1
                            findings.append(Finding(
                                id=f"SP-{fid:03d}",
                                severity=Severity.MEDIUM,
                                category="nonexistent_base_path",
                                file=str(pyfile.relative_to(root)),
                                line=line_no,
                                description=f"Base directory '{base_check}' does not exist on this machine",
                                evidence=stripped,
                                proposed_fix="Guard the path or update it to the real base directory",
                            ))

            if "MessageBus" in line and ("message_bus.db" in line or "messages.db" in line):
                basename = "message_bus.db" if "message_bus.db" in line else "messages.db"
                message_bus_locations.append((pyfile, line_no, basename, stripped))
            elif ("message_bus.db" in line or "messages.db" in line) and "MessageBus" in content:
                basename = "message_bus.db" if "message_bus.db" in line else "messages.db"
                message_bus_locations.append((pyfile, line_no, basename, stripped))

    basenames = sorted({entry[2] for entry in message_bus_locations})
    if len(basenames) > 1:
        fid += 1
        evidence = "; ".join(
            f"{path.relative_to(root)}:{line_no} -> {basename}"
            for path, line_no, basename, _ in message_bus_locations
        )
        first_path, first_line, _, first_snippet = message_bus_locations[0]
        findings.append(Finding(
            id=f"SP-{fid:03d}",
            severity=Severity.CRITICAL,
            category="message_bus_path_split",
            file=str(first_path.relative_to(root)),
            line=first_line,
            description=(
                "MessageBus storage uses inconsistent database basenames across components: "
                + ", ".join(basenames)
            ),
            evidence=f"{first_snippet} | {evidence}",
            proposed_fix=(
                "Standardize MessageBus path derivation so all agents and the swarm "
                "read the same mailbox"
            ),
        ))

    report.findings = findings
    report.recompute_summary()
    return report
