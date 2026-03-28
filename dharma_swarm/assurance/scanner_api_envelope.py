"""API response-envelope contract scanner."""

from __future__ import annotations

from pathlib import Path

from dharma_swarm.assurance.report_schema import Finding, ScanReport, Severity


def _find_line(lines: list[str], needle: str) -> int:
    for idx, line in enumerate(lines, start=1):
        if needle in line:
            return idx
    return 0


def _function_window(lines: list[str], signature: str) -> tuple[int, int]:
    start = _find_line(lines, signature)
    if not start:
        return 0, 0

    brace_depth = 0
    saw_open = False
    for idx in range(start - 1, len(lines)):
        line = lines[idx]
        brace_depth += line.count("{")
        if line.count("{"):
            saw_open = True
        brace_depth -= line.count("}")
        if saw_open and brace_depth <= 0:
            return start, idx + 1
    return start, len(lines)


def scan(
    *,
    repo_root: Path | None = None,
    changed_files: list[str] | None = None,
) -> ScanReport:
    del changed_files

    root = repo_root or Path(__file__).resolve().parents[2]
    report = ScanReport(scanner="api_envelope")
    backend_models = root / "api" / "models.py"
    frontend_api = root / "dashboard" / "src" / "lib" / "api.ts"

    if not backend_models.exists() or not frontend_api.exists():
        return report

    try:
        backend_text = backend_models.read_text(encoding="utf-8", errors="replace")
        frontend_lines = frontend_api.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return report

    backend_wraps = "class ApiResponse" in backend_text
    typed_start, typed_end = _function_window(frontend_lines, "async function _fetchWrapped<T>(")
    typed_wrapper_text = "\n".join(frontend_lines[typed_start - 1:typed_end]) if typed_start else ""
    typed_wrapper_lines = typed_wrapper_text.splitlines()
    typed_wrapper_line = 0
    if typed_start:
        for needle in (
            "const data: T = await res.json();",
            "data: json as T,",
            "data: json as T",
        ):
            rel_line = _find_line(typed_wrapper_lines, needle)
            if rel_line:
                typed_wrapper_line = typed_start - 1 + rel_line
                break
    checks_data_envelope = '"data" in json' in typed_wrapper_text or "'data' in json" in typed_wrapper_text
    checks_status_envelope = (
        '"status" in json' in typed_wrapper_text or "'status' in json" in typed_wrapper_text
    )
    typed_wrapper_uses_envelope = (
        checks_data_envelope
        and checks_status_envelope
        and (
            "return json.data as T;" in typed_wrapper_text
            or "data: json.data as T," in typed_wrapper_text
            or "data: json.data as T" in typed_wrapper_text
        )
    )
    legacy_unwrap_line = _find_line(frontend_lines, "return json.data as T;")

    if backend_wraps and typed_wrapper_line and legacy_unwrap_line and not typed_wrapper_uses_envelope:
        report.findings = [
            Finding(
                id="AE-001",
                severity=Severity.HIGH,
                category="typed_fetch_envelope_mismatch",
                file="dashboard/src/lib/api.ts",
                line=typed_wrapper_line,
                description=(
                    "Typed fetch wrapper returns the backend ApiResponse envelope as payload T "
                    "instead of unwrapping ApiResponse.data"
                ),
                evidence=(
                    f"typed wrapper line {typed_wrapper_line} parses res.json() directly as T, "
                    f"while legacy apiFetch unwraps json.data at line {legacy_unwrap_line}"
                ),
                proposed_fix=(
                    "Unwrap backend ApiResponse in _fetchWrapped() or remove the duplicate typed "
                    "wrapper path"
                ),
            )
        ]
        report.recompute_summary()

    return report
