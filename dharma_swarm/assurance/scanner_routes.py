"""Frontend/backend route contract scanner."""

from __future__ import annotations

import re
from pathlib import Path

from dharma_swarm.assurance.report_schema import Finding, ScanReport, Severity

BACKEND_ROUTE_RE = re.compile(r"""@router\.(get|post|put|patch|delete)\(\s*["']([^"']+)["']""")
PREFIX_RE = re.compile(r"""APIRouter\([^)]*prefix\s*=\s*["']([^"']+)["']""")
FRONTEND_CALL_RE = re.compile(r"""api(Get|Post|Put|Patch|Delete)\s*<[^>]+>\(""")


def _normalize_frontend_path(raw_path: str) -> str:
    path = raw_path
    if "${qs" in path:
        path = path.split("${qs", 1)[0]
    path = path.split("?", 1)[0]
    path = re.sub(r"""\$\{[^}]+\}""", "{param}", path)
    return path.rstrip("?") or path


def _path_matches(route_path: str, frontend_path: str) -> bool:
    route_segments = route_path.strip("/").split("/")
    frontend_segments = frontend_path.strip("/").split("/")
    if len(route_segments) != len(frontend_segments):
        return False

    for route_seg, frontend_seg in zip(route_segments, frontend_segments):
        if route_seg.startswith("{") and route_seg.endswith("}"):
            continue
        if frontend_seg.startswith("{") and frontend_seg.endswith("}"):
            continue
        if route_seg != frontend_seg:
            return False
    return True


def _scan_backend_routes(repo_root: Path) -> set[tuple[str, str]]:
    route_set: set[tuple[str, str]] = set()
    routers_dir = repo_root / "api" / "routers"
    for router_file in routers_dir.rglob("*.py"):
        try:
            content = router_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        prefix_match = PREFIX_RE.search(content)
        prefix = prefix_match.group(1) if prefix_match else ""
        for method, path in BACKEND_ROUTE_RE.findall(content):
            route_set.add((method.upper(), f"{prefix}{path}"))
    return route_set


def _scan_frontend_calls(repo_root: Path) -> list[tuple[str, str, int, str]]:
    api_file = repo_root / "dashboard" / "src" / "lib" / "api.ts"
    if not api_file.exists():
        return []

    try:
        lines = api_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    calls: list[tuple[str, str, int, str]] = []
    for idx, line in enumerate(lines, start=1):
        match = FRONTEND_CALL_RE.search(line)
        if not match:
            continue

        method = match.group(1).upper()
        open_paren = line.find("(", match.start())
        if open_paren < 0:
            continue

        quote_char = ""
        quote_pos = -1
        for candidate in ('"', "`"):
            pos = line.find(candidate, open_paren)
            if pos != -1 and (quote_pos == -1 or pos < quote_pos):
                quote_char = candidate
                quote_pos = pos
        if quote_pos == -1:
            continue

        if quote_char == '"':
            end_pos = line.find('"', quote_pos + 1)
        else:
            end_pos = line.rfind("`")
        if end_pos <= quote_pos:
            continue

        raw_path = line[quote_pos + 1:end_pos]
        calls.append((method, _normalize_frontend_path(raw_path), idx, line.strip()))
    return calls


def _route_exists(route_set: set[tuple[str, str]], method: str, path: str) -> bool:
    for candidate_method, candidate_path in route_set:
        if candidate_method == method and _path_matches(candidate_path, path):
            return True
    return False


def _candidate_backend_paths(route_set: set[tuple[str, str]], method: str, path: str) -> list[str]:
    leaf = path.rstrip("/").split("/")[-1]
    return sorted(
        candidate_path
        for candidate_method, candidate_path in route_set
        if candidate_method == method and candidate_path.rstrip("/").split("/")[-1] == leaf
    )


def scan(
    *,
    repo_root: Path | None = None,
    changed_files: list[str] | None = None,
) -> ScanReport:
    del changed_files

    root = repo_root or Path(__file__).resolve().parents[2]
    report = ScanReport(scanner="route_contract")
    findings: list[Finding] = []
    route_set = _scan_backend_routes(root)
    frontend_calls = _scan_frontend_calls(root)
    fid = 0

    for method, path, line_no, evidence in frontend_calls:
        if _route_exists(route_set, method, path):
            continue
        fid += 1
        suggestions = ", ".join(_candidate_backend_paths(route_set, method, path)[:3])
        findings.append(Finding(
            id=f"RC-{fid:03d}",
            severity=Severity.HIGH,
            category="missing_backend_route",
            file="dashboard/src/lib/api.ts",
            line=line_no,
            description=f"Frontend calls {method} {path}, but no matching backend route exists",
            evidence=evidence + (f" | similar backend paths: {suggestions}" if suggestions else ""),
            proposed_fix=(
                "Align the frontend helper with the backend route or add the missing backend endpoint"
            ),
        ))

    report.findings = findings
    report.recompute_summary()
    return report
