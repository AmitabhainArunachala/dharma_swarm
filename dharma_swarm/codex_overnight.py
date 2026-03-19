from __future__ import annotations

import argparse
import csv
import errno
import fcntl
import json
import math
import os
import pwd
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


def _resolve_login_home() -> Path:
    try:
        return Path(pwd.getpwuid(os.getuid()).pw_dir).expanduser()
    except Exception:
        return Path.home()


LOGIN_HOME = _resolve_login_home()
ROOT = LOGIN_HOME / "dharma_swarm"
STATE = LOGIN_HOME / ".dharma"
LOG_ROOT = STATE / "logs" / "codex_overnight"
HEARTBEAT_FILE = STATE / "codex_overnight_heartbeat.json"
RUN_FILE = STATE / "codex_overnight_run_dir.txt"
REAL_CODEX_DIR = LOGIN_HOME / ".codex"
AUTORESEARCH_RESULTS_FILE = "results_autoresearch.tsv"
AUTORESEARCH_RESULTS_COLUMNS = (
    "exp_id",
    "timestamp",
    "hypothesis",
    "predicted_omega_delta",
    "predicted_psi_delta",
    "actual_omega",
    "actual_psi",
    "files",
    "tests",
    "kept",
    "regime",
    "notes",
    "confidence",
    "metrics_source",
)
SUMMARY_FIELDS = (
    "hypothesis",
    "predicted_omega_delta",
    "predicted_psi_delta",
    "confidence",
    "result",
    "files",
    "tests",
    "blockers",
    "self_update",
    "critic_update",
)
SUMMARY_DEFAULTS = {
    "hypothesis": "unknown",
    "predicted_omega_delta": "unknown",
    "predicted_psi_delta": "unknown",
    "confidence": "unknown",
    "result": "(missing)",
    "files": "none",
    "tests": "not run",
    "blockers": "none",
    "self_update": "none",
    "critic_update": "none",
}
AUTORESEARCH_RESULTS_HEADER = "\t".join(AUTORESEARCH_RESULTS_COLUMNS) + "\n"
COPIED_CODEX_FILES = (
    "auth.json",
    ".codex-global-state.json",
    "version.json",
    "state_5.sqlite",
    "state_5.sqlite-shm",
    "state_5.sqlite-wal",
    "models_cache.json",
)
COPIED_CODEX_DIRS = (
    "skills",
    "agents",
    "rules",
    "vendor_imports",
)
WORKTREE_OVERLAY_PATHS = (
    "dharma_swarm/autoresearch_eval.py",
    "dharma_swarm/codex_overnight.py",
    "dharma_swarm/cost_tracker.py",
    "dharma_swarm/ecc_eval_harness.py",
    "evaluate.py",
    "tests/test_autoresearch_eval.py",
    "tests/test_codex_overnight.py",
)
DEFAULT_FOCUS_METRICS = (
    "cost_efficiency",
    "latency_p95",
    "tool_reliability",
)

DEFAULT_MISSION = (
    "Continue the highest-leverage work in dharma_swarm autonomously. "
    "Inspect the current repo state each cycle, choose one bounded slice, "
    "implement it end-to-end when feasible, run focused verification, and "
    "leave the tree in a clean explainable state without committing or pushing."
)


@dataclass(slots=True)
class GitSnapshot:
    branch: str
    head: str
    dirty: bool
    changed_files: list[str]
    staged_count: int
    unstaged_count: int
    untracked_count: int


@dataclass(slots=True)
class RunSettings:
    label: str
    hours: float
    poll_seconds: int
    cycle_timeout: int
    max_cycles: int
    model: str


def utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def heartbeat_file_for(state_dir: Path) -> Path:
    return state_dir / "codex_overnight_heartbeat.json"


def run_file_for(state_dir: Path) -> Path:
    return state_dir / "codex_overnight_run_dir.txt"


def _slugify_label(text: str, *, fallback: str = "codex-night") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or fallback


def _atomic_write_text(
    path: Path,
    text: str,
    *,
    encoding: str = "utf-8",
    errors: str | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding=encoding,
            errors=errors,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
            tmp_name = handle.name
        Path(tmp_name).replace(path)
    finally:
        if tmp_name:
            Path(tmp_name).unlink(missing_ok=True)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
    )


def _append_locked_text(
    path: Path,
    text: str,
    *,
    encoding: str = "utf-8",
    errors: str | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding=encoding, errors=errors) as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    _append_locked_text(
        path,
        json.dumps(payload, ensure_ascii=True) + "\n",
    )


def append_text(path: Path, text: str) -> None:
    _append_locked_text(path, text.rstrip() + "\n")


def run_cmd(
    cmd: list[str],
    *,
    cwd: Path,
    timeout: int = 30,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        input=input_text,
        capture_output=True,
        timeout=timeout,
        env=env,
    )


def _safe_text(text: str, *, limit: int = 1200) -> str:
    squashed = " ".join(text.split())
    if len(squashed) <= limit:
        return squashed
    return squashed[: limit - 3] + "..."


def _coerce_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return value


def _os_error_return_code(exc: OSError) -> int:
    if isinstance(exc, FileNotFoundError) or exc.errno == errno.ENOENT:
        return 127
    if isinstance(exc, PermissionError):
        return 126
    return 1


def _build_startup_failure_summary(*, stage: str, exc: BaseException) -> str:
    detail = str(exc).strip() or exc.__class__.__name__
    blocker = _safe_text(f"{stage}: {detail}", limit=600)
    return _format_cycle_summary(
        {
            "result": f"Cycle failed before Codex could run because {blocker}.",
            "files": "none",
            "tests": "not run",
            "blockers": blocker,
        }
    )


def _count_populated_summary_fields(summary_text: str) -> int:
    parsed = parse_summary_fields(summary_text)
    return sum(1 for key in SUMMARY_FIELDS if parsed.get(key, "").strip())


def _summary_candidate_score(summary_text: str) -> tuple[int, int, int, int]:
    parsed = parse_summary_fields(summary_text)
    meaningful = 0
    populated = 0
    text_weight = 0
    for key in SUMMARY_FIELDS:
        value = parsed.get(key, "").strip()
        if not value:
            continue
        populated += 1
        normalized = " ".join(value.split())
        if normalized.lower() == str(SUMMARY_DEFAULTS[key]).strip().lower():
            continue
        if key in {"predicted_omega_delta", "predicted_psi_delta"}:
            if _parse_float_field(normalized) is None:
                continue
        elif key == "confidence":
            if _parse_confidence(normalized) is None:
                continue
        elif key != "result" and _none_like(normalized):
            continue
        meaningful += 1
        text_weight += len(normalized)
    return meaningful, populated, text_weight, len(summary_text.strip())


def _resolve_cycle_summary(*, output_file: Path, stdout: str) -> str:
    candidates: list[str] = []
    if output_file.exists():
        summary_text = output_file.read_text(encoding="utf-8", errors="ignore").strip()
        if summary_text:
            candidates.append(summary_text)
    stdout_text = stdout.strip()
    if stdout_text:
        candidates.append(stdout_text)
    if not candidates:
        return ""
    return max(candidates, key=_summary_candidate_score)


def parse_summary_fields(summary_text: str) -> dict[str, str]:
    fields = {key: "" for key in SUMMARY_FIELDS}
    for line in summary_text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized = key.strip().lower()
        if normalized in fields:
            fields[normalized] = value.strip()
    return fields


def _summary_value(raw_value: str | None, *, fallback: str) -> str:
    text = " ".join((raw_value or "").split())
    return text or fallback


def _format_cycle_summary(fields: dict[str, str]) -> str:
    lines = [
        f"{key.upper()}: {_summary_value(fields.get(key), fallback=SUMMARY_DEFAULTS[key])}"
        for key in SUMMARY_FIELDS
    ]
    return "\n".join(lines)


def _normalize_cycle_summary(summary_text: str) -> str:
    parsed = parse_summary_fields(summary_text)
    normalized = {key: _summary_value(parsed.get(key), fallback=SUMMARY_DEFAULTS[key]) for key in SUMMARY_FIELDS}
    raw_excerpt = _safe_text(summary_text, limit=600) if summary_text.strip() else ""
    if normalized["result"] == SUMMARY_DEFAULTS["result"] and raw_excerpt:
        normalized["result"] = raw_excerpt
    return _format_cycle_summary(normalized)


def _parse_files_field(raw_value: str) -> list[str]:
    value = raw_value.strip()
    if not value or value.lower() == "none":
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _none_like(raw_value: str) -> bool:
    value = raw_value.strip().lower()
    return value in {"", "none", "n/a", "na", "unknown"}


def _parse_float_field(raw_value: Any) -> float | None:
    if isinstance(raw_value, bool):
        return None
    if isinstance(raw_value, (float, int)):
        parsed = float(raw_value)
        return parsed if math.isfinite(parsed) else None
    if raw_value is None:
        return None
    value = str(raw_value).strip()
    if _none_like(value):
        return None
    if value.endswith("%"):
        value = value[:-1].strip()
        try:
            parsed = float(value) / 100.0
        except ValueError:
            return None
        return parsed if math.isfinite(parsed) else None
    if value.startswith("+"):
        value = value[1:]
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def _parse_confidence(raw_value: str) -> float | None:
    parsed = _parse_float_field(raw_value)
    if parsed is None:
        return None
    if parsed > 1.0:
        parsed = parsed / 100.0
    return max(0.0, min(1.0, parsed))


def _clean_results_cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()


def _infer_results_metrics_source(
    row: dict[str, str],
    *,
    header_fields: Sequence[str] = (),
) -> str:
    if row.get("metrics_source"):
        return row["metrics_source"]
    header_names = {field.strip() for field in header_fields if field.strip()}
    if "actual_omega_proxy" in header_names or "actual_psi_proxy" in header_names:
        return "proxy"
    if (
        _parse_float_field(row.get("actual_omega")) is not None
        or _parse_float_field(row.get("actual_psi")) is not None
    ):
        return "locked"
    return "unavailable"


def _normalize_results_row(
    row: dict[str, Any],
    *,
    header_fields: Sequence[str] = (),
) -> dict[str, str]:
    normalized = {
        key: _clean_results_cell(row.get(key, ""))
        for key in AUTORESEARCH_RESULTS_COLUMNS
    }
    if not normalized["actual_omega"]:
        normalized["actual_omega"] = _clean_results_cell(row.get("actual_omega_proxy", ""))
    if not normalized["actual_psi"]:
        normalized["actual_psi"] = _clean_results_cell(row.get("actual_psi_proxy", ""))
    if not normalized["confidence"]:
        normalized["confidence"] = "unknown"
    normalized["metrics_source"] = _infer_results_metrics_source(
        normalized,
        header_fields=header_fields,
    )
    return normalized


def _looks_like_results_header(row: Sequence[str]) -> bool:
    normalized = [cell.strip() for cell in row if cell.strip()]
    if not normalized or normalized[0] != "exp_id":
        return False
    known_fields = set(AUTORESEARCH_RESULTS_COLUMNS) | {"actual_omega_proxy", "actual_psi_proxy"}
    return sum(1 for cell in normalized if cell in known_fields) >= min(4, len(normalized))


def _infer_results_row_fields(row: Sequence[str]) -> Sequence[str]:
    row_len = len(row)
    if row_len >= len(AUTORESEARCH_RESULTS_COLUMNS):
        return AUTORESEARCH_RESULTS_COLUMNS
    if row_len == len(AUTORESEARCH_RESULTS_COLUMNS) - 2:
        return AUTORESEARCH_RESULTS_COLUMNS[:-2]
    return AUTORESEARCH_RESULTS_COLUMNS[:row_len]


def _normalize_results_tsv(text: str) -> str:
    if not text.strip():
        return AUTORESEARCH_RESULTS_HEADER
    reader = csv.reader(text.splitlines(), delimiter="\t")
    rows = list(reader)
    if not rows:
        return AUTORESEARCH_RESULTS_HEADER
    normalized_lines = ["\t".join(AUTORESEARCH_RESULTS_COLUMNS)]
    first_row = [cell.strip() for cell in rows[0]]
    if _looks_like_results_header(first_row):
        header_fields = first_row
        data_rows = rows[1:]
    else:
        header_fields = list(_infer_results_row_fields(rows[0]))
        data_rows = rows
    for raw_row in data_rows:
        if not any(cell.strip() for cell in raw_row):
            continue
        row = {
            header_fields[idx]: raw_row[idx]
            for idx in range(min(len(header_fields), len(raw_row)))
            if header_fields[idx]
        }
        normalized = _normalize_results_row(row, header_fields=header_fields)
        normalized_lines.append(
            "\t".join(normalized[column] for column in AUTORESEARCH_RESULTS_COLUMNS)
        )
    return "\n".join(normalized_lines) + "\n"


def _ensure_locked_results_file(results_path: Path) -> None:
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with results_path.open("a+", encoding="utf-8", errors="ignore") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.seek(0)
            text = handle.read()
            normalized = _normalize_results_tsv(text)
            if normalized == text:
                return
            handle.seek(0)
            handle.truncate()
            handle.write(normalized)
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _weighted_geometric_mean(weighted_values: Sequence[tuple[float, float]]) -> float:
    total_weight = 0.0
    total_log = 0.0
    for value, weight in weighted_values:
        bounded = max(1e-6, min(1.0, value))
        total_weight += weight
        total_log += weight * math.log(bounded)
    if total_weight <= 0:
        return 0.0
    return round(math.exp(total_log / total_weight), 4)


def _compute_omega_proxy(
    *,
    summary_fields: dict[str, str],
    rc: int,
    timed_out: bool,
) -> float:
    files = _parse_files_field(summary_fields.get("files", ""))
    tests_text = summary_fields.get("tests", "")
    blockers_text = summary_fields.get("blockers", "")

    completion = 1.0 if rc == 0 and not timed_out else 0.2
    verification = 1.0 if not _none_like(tests_text) and "not run" not in tests_text.lower() else 0.35
    blockers = 1.0 if _none_like(blockers_text) else 0.45
    if not files:
        scope = 0.7
    elif len(files) <= 4:
        scope = 1.0
    elif len(files) <= 8:
        scope = 0.85
    else:
        scope = 0.7

    return _weighted_geometric_mean(
        (
            (completion, 0.45),
            (verification, 0.25),
            (blockers, 0.20),
            (scope, 0.10),
        )
    )


def _compute_psi_proxy(
    *,
    summary_fields: dict[str, str],
    previous_snapshot: dict[str, Any],
    omega_proxy: float,
) -> float:
    completeness_signals = [
        not _none_like(summary_fields.get("hypothesis", "")),
        _parse_float_field(summary_fields.get("predicted_omega_delta", "")) is not None,
        _parse_float_field(summary_fields.get("predicted_psi_delta", "")) is not None,
        _parse_confidence(summary_fields.get("confidence", "")) is not None,
        not _none_like(summary_fields.get("self_update", "")),
    ]
    completeness = sum(1.0 for value in completeness_signals if value) / len(completeness_signals)

    calibration = 0.5
    predicted_delta = _parse_float_field(summary_fields.get("predicted_omega_delta", ""))
    previous_omega = previous_snapshot.get("omega_proxy")
    if predicted_delta is not None:
        if isinstance(previous_omega, (float, int)):
            actual_delta = omega_proxy - float(previous_omega)
            calibration = max(0.0, 1.0 - min(1.0, abs(predicted_delta - actual_delta)))
        else:
            calibration = 0.75

    return round((0.6 * completeness) + (0.4 * calibration), 4)


def _metric_from_snapshot(
    snapshot: dict[str, Any],
    *,
    primary: str,
    fallback: str,
) -> float | None:
    value = _parse_float_field(snapshot.get(primary))
    if value is not None:
        return value
    return _parse_float_field(snapshot.get(fallback))


def _snapshot_metric_source(snapshot: dict[str, Any]) -> str:
    return str(snapshot.get("metrics_source", "") or "").strip().lower()


def _locked_metric_from_snapshot(snapshot: dict[str, Any], *, key: str) -> float | None:
    if _snapshot_metric_source(snapshot) != "locked":
        return None
    return _parse_float_field(snapshot.get(key))


def _parse_eval_summary_line(stdout: str) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for line in reversed(stdout.splitlines()):
        stripped = line.strip()
        if "Ω=" not in stripped or "Ψ=" not in stripped:
            continue
        payload["summary_line"] = stripped
        for token in stripped.split():
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            parsed = _parse_float_field(value)
            if parsed is None:
                continue
            if key == "Ω":
                payload["omega"] = parsed
            elif key == "Ψ":
                payload["psi"] = parsed
            elif key.startswith("HP") and key[2:].isdigit():
                hp_scores = payload.setdefault("hp_scores", [])
                hp_scores.append(
                    {
                        "name": key,
                        "score": parsed,
                        "weight": 0.0,
                        "detail": {},
                    }
                )
        break
    return payload


def _run_locked_evaluator(
    *,
    repo_root: Path,
    state_dir: Path,
    run_dir: Path,
    cycle: int,
    timeout: int,
) -> dict[str, Any]:
    evals_dir = run_dir / "evals"
    evals_dir.mkdir(parents=True, exist_ok=True)
    json_file = evals_dir / f"cycle_{cycle:03d}.json"
    report_file = evals_dir / f"cycle_{cycle:03d}.md"
    log_file = evals_dir / f"cycle_{cycle:03d}.log"
    evaluator_timeout = min(300, max(60, timeout))
    cmd = [
        sys.executable,
        "evaluate.py",
        "--benchmark",
        "full",
        "--timeout",
        str(evaluator_timeout),
        "--repo-root",
        str(repo_root),
        "--state-dir",
        str(state_dir),
        "--output",
        str(report_file),
        "--json-out",
        str(json_file),
    ]

    payload: dict[str, Any] = {}
    summary_line = ""
    try:
        proc = run_cmd(
            cmd,
            cwd=repo_root,
            timeout=evaluator_timeout + 60,
        )
        stdout = _coerce_text(proc.stdout) + _coerce_text(proc.stderr)
        rc = proc.returncode
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        stdout = (
            _coerce_text(getattr(exc, "stdout", None) or getattr(exc, "output", None))
            + _coerce_text(exc.stderr)
        )
        rc = 124
        timed_out = True
    except OSError as exc:
        summary_line = _safe_text(
            f"evaluator invocation failed: {str(exc).strip() or exc.__class__.__name__}",
            limit=300,
        )
        stdout = summary_line
        rc = _os_error_return_code(exc)
        timed_out = False

    log_file.write_text(stdout, encoding="utf-8", errors="ignore")
    if not summary_line:
        parsed_stdout = _parse_eval_summary_line(stdout)
        payload = _read_json(json_file)
        if payload:
            for key in ("summary_line", "omega", "psi"):
                if payload.get(key) in {"", None} and key in parsed_stdout:
                    payload[key] = parsed_stdout[key]
            if not payload.get("hp_scores") and parsed_stdout.get("hp_scores"):
                payload["hp_scores"] = parsed_stdout["hp_scores"]
        else:
            payload = parsed_stdout

    omega = _parse_float_field(payload.get("omega"))
    psi = _parse_float_field(payload.get("psi"))
    return {
        "rc": rc,
        "timed_out": timed_out,
        "summary_line": str(payload.get("summary_line", "") or summary_line),
        "omega": omega,
        "psi": psi,
        "hp_scores": list(payload.get("hp_scores", [])),
        "psi_components": dict(payload.get("psi_components", {})),
        "json_file": str(json_file) if json_file.exists() else "",
        "report_file": str(report_file) if report_file.exists() else "",
        "log_file": str(log_file),
    }


def _compute_keep_decision(
    *,
    previous_snapshot: dict[str, Any],
    current_omega: float | None,
    current_psi: float | None,
    metrics_source: str,
    rc: int,
    timed_out: bool,
    blockers_text: str,
) -> bool:
    if (
        rc != 0
        or timed_out
        or not _none_like(blockers_text)
        or metrics_source != "locked"
        or current_omega is None
        or current_psi is None
    ):
        return False

    previous_omega = _locked_metric_from_snapshot(previous_snapshot, key="actual_omega")
    previous_psi = _locked_metric_from_snapshot(previous_snapshot, key="actual_psi")
    if previous_omega is None or previous_psi is None:
        return True

    omega_delta = current_omega - previous_omega
    psi_delta = current_psi - previous_psi
    if omega_delta > 0.0 and psi_delta >= 0.0:
        return True
    if omega_delta > 0.0 and psi_delta < 0.0:
        return omega_delta > (2.0 * abs(psi_delta))
    return False


def _recent_omega_history(run_dir: Path, *, limit: int = 20) -> list[float]:
    cycles_path = run_dir / "cycles.jsonl"
    if not cycles_path.exists():
        return []
    history: list[float] = []
    for line in cycles_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if _snapshot_metric_source(payload) != "locked":
            continue
        actual_omega = _parse_float_field(payload.get("actual_omega"))
        if actual_omega is not None:
            history.append(actual_omega)
    return history[-limit:]


def _classify_regime(*, history: Sequence[float], current: float) -> str:
    series = list(history) + [current]
    if len(series) < 2:
        return "baseline"
    recent_deltas = [series[i] - series[i - 1] for i in range(1, len(series))]
    if len(recent_deltas) >= 3:
        sign_changes = sum(
            1
            for i in range(1, len(recent_deltas))
            if recent_deltas[i] * recent_deltas[i - 1] < 0
        )
        if sign_changes >= 2:
            return "oscillating"
    delta = series[-1] - series[-2]
    prev_delta = series[-2] - series[-3] if len(series) >= 3 else 0.0
    if delta > 0.02 and prev_delta > 0 and delta >= prev_delta:
        return "accelerating"
    if delta > 0.0:
        return "converging"
    if delta < -0.02:
        return "regressing"
    return "stagnating"


def _autoresearch_paths(repo_root: Path) -> dict[str, Path]:
    return {
        "self_model": repo_root / "SELF.md",
        "critic": repo_root / "CRITIC.md",
        "experiment_log": repo_root / "experiment_log.md",
        "audit_log": repo_root / "audit_log.md",
        "hp_interactions": repo_root / "hp_interactions.md",
        "results": repo_root / AUTORESEARCH_RESULTS_FILE,
    }


def ensure_autoresearch_files(repo_root: Path) -> dict[str, Path]:
    paths = _autoresearch_paths(repo_root)
    templates = {
        "self_model": (
            "# SELF.md — DHARMA SWARM Self-Model\n\n"
            "Append-only observations from the live autoresearch runner.\n"
            "Ω/Ψ entries come only from the locked `evaluate.py` scorer; provisional proxy notes remain unlabeled.\n\n"
            "## Observations\n"
        ),
        "critic": (
            "# CRITIC.md — What Not To Do\n\n"
            "Append-only record of failure patterns, blocked paths, and prediction misses.\n\n"
            "## Entries\n"
        ),
        "experiment_log": (
            "# experiment_log.md — Autoresearch Trace\n\n"
            "One append-only entry per autonomous cycle.\n"
        ),
        "audit_log": (
            "# audit_log.md — Goodhart and Safety Audits\n\n"
            "Append-only audit notes. Reserved for periodic regime and proxy-gaming checks.\n"
        ),
        "hp_interactions": (
            "# hp_interactions.md — Interaction Notes\n\n"
            "Append-only scratchpad for cross-metric and cross-subsystem interactions.\n"
        ),
    }
    for key, template in templates.items():
        path = paths[key]
        if not path.exists():
            _atomic_write_text(path, template)
    _ensure_locked_results_file(paths["results"])
    return paths


def _append_autoresearch_artifacts(
    *,
    repo_root: Path,
    snapshot: dict[str, Any],
) -> None:
    paths = ensure_autoresearch_files(repo_root)
    fields = snapshot.get("summary_fields", {})
    cycle = int(snapshot.get("cycle", 0))
    timestamp = str(snapshot.get("ts", utc_ts()))
    metrics_source = _snapshot_metric_source(snapshot) or "unavailable"
    actual_omega = _locked_metric_from_snapshot(snapshot, key="actual_omega")
    actual_psi = _locked_metric_from_snapshot(snapshot, key="actual_psi")
    omega_proxy = _metric_from_snapshot(snapshot, primary="omega_proxy", fallback="omega_proxy") or 0.0
    psi_proxy = _metric_from_snapshot(snapshot, primary="psi_proxy", fallback="psi_proxy") or 0.0
    regime = str(snapshot.get("regime", "unknown"))
    kept = bool(snapshot.get("kept", False))
    files = fields.get("files", "none") or "none"
    tests = fields.get("tests", "not run") or "not run"
    hypothesis = fields.get("hypothesis", "") or "(missing)"
    notes = fields.get("result", "") or fields.get("blockers", "") or "(missing)"
    evaluator = snapshot.get("evaluator", {})
    confidence = (fields.get("confidence", "") or "unknown").replace("\t", " ")
    omega_text = f"{actual_omega:.4f}" if actual_omega is not None else f"unavailable (proxy {omega_proxy:.4f})"
    psi_text = f"{actual_psi:.4f}" if actual_psi is not None else f"unavailable (proxy {psi_proxy:.4f})"

    append_text(
        paths["experiment_log"],
        "\n".join(
            [
                "",
                f"## Cycle {cycle:03d} — {timestamp}",
                f"- hypothesis: {hypothesis}",
                f"- predicted_omega_delta: {fields.get('predicted_omega_delta', '') or 'unknown'}",
                f"- predicted_psi_delta: {fields.get('predicted_psi_delta', '') or 'unknown'}",
                f"- confidence: {confidence}",
                f"- omega: {omega_text}",
                f"- psi: {psi_text}",
                f"- regime: {regime}",
                f"- metrics_source: {metrics_source}",
                f"- kept: {str(kept).lower()}",
                f"- result: {fields.get('result', '') or '(missing)'}",
                f"- files: {files}",
                f"- tests: {tests}",
                f"- blockers: {fields.get('blockers', '') or 'none'}",
                f"- evaluator: {evaluator.get('summary_line', '') or 'unavailable'}",
            ]
        ),
    )

    self_update = fields.get("self_update", "")
    if not _none_like(self_update):
        if actual_omega is not None and actual_psi is not None:
            append_text(
                paths["self_model"],
                f"- {timestamp} cycle {cycle:03d} [{regime}] Ω≈{actual_omega:.4f} Ψ≈{actual_psi:.4f}: {self_update}",
            )
        else:
            append_text(
                paths["self_model"],
                f"- {timestamp} cycle {cycle:03d} [{regime}] scorer unavailable: {self_update}",
            )

    critic_update = fields.get("critic_update", "")
    blockers = fields.get("blockers", "")
    if not _none_like(critic_update):
        append_text(
            paths["critic"],
            f"- {timestamp} cycle {cycle:03d}: {critic_update}",
        )
    elif not _none_like(blockers):
        append_text(
            paths["critic"],
            f"- {timestamp} cycle {cycle:03d}: blocker observed -> {blockers}",
        )

    results_row = _normalize_results_row(
        {
            "exp_id": f"{cycle:03d}",
            "timestamp": timestamp,
            "hypothesis": hypothesis,
            "predicted_omega_delta": fields.get("predicted_omega_delta", "") or "unknown",
            "predicted_psi_delta": fields.get("predicted_psi_delta", "") or "unknown",
            "actual_omega": f"{actual_omega:.4f}" if actual_omega is not None else "",
            "actual_psi": f"{actual_psi:.4f}" if actual_psi is not None else "",
            "files": files,
            "tests": tests,
            "kept": "keep" if kept else "discard",
            "regime": regime,
            "notes": notes,
            "confidence": confidence,
            "metrics_source": metrics_source,
        },
        header_fields=AUTORESEARCH_RESULTS_COLUMNS,
    )
    _append_locked_text(
        paths["results"],
        "\t".join(results_row[column] for column in AUTORESEARCH_RESULTS_COLUMNS) + "\n",
    )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _copy_overlay_entry(*, src: Path, dst: Path) -> None:
    if not src.exists():
        return
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _remove_overlay_entry(dst: Path) -> None:
    if dst.is_symlink() or dst.is_file():
        dst.unlink()
        return
    if dst.exists():
        shutil.rmtree(dst)


def _sync_worktree_overlay(*, source_repo_root: Path, worktree_root: Path) -> list[str]:
    synced: list[str] = []
    for rel_path in WORKTREE_OVERLAY_PATHS:
        src = source_repo_root / rel_path
        dst = worktree_root / rel_path
        if src.exists():
            _copy_overlay_entry(src=src, dst=dst)
            synced.append(rel_path)
            continue
        if not (dst.exists() or dst.is_symlink()):
            continue
        _remove_overlay_entry(dst)
        synced.append(rel_path)
    manifest = worktree_root / ".codex_overnight_overlay.json"
    write_json(
        manifest,
        {
            "source_repo_root": str(source_repo_root),
            "worktree_root": str(worktree_root),
            "synced_at": utc_ts(),
            "paths": synced,
        },
    )
    return synced


def prepare_isolated_worktree(
    *,
    source_repo_root: Path,
    state_dir: Path,
    run_dir: Path,
    label: str,
    worktree_root: Path | None = None,
) -> tuple[Path, list[str]]:
    worktrees_root = (worktree_root or (state_dir / "worktrees")).expanduser()
    worktrees_root.mkdir(parents=True, exist_ok=True)
    target = worktrees_root / f"{run_dir.name}-{_slugify_label(label)}"

    head_proc = run_cmd(
        ["git", "rev-parse", "HEAD"],
        cwd=source_repo_root,
        timeout=30,
    )
    if head_proc.returncode != 0:
        detail = _safe_text(head_proc.stderr or head_proc.stdout or "git rev-parse HEAD failed", limit=300)
        raise RuntimeError(f"unable to resolve source HEAD for worktree setup: {detail}")
    head = head_proc.stdout.strip()
    if not head:
        raise RuntimeError("unable to resolve source HEAD for worktree setup")

    add_proc = run_cmd(
        ["git", "worktree", "add", "--detach", str(target), head],
        cwd=source_repo_root,
        timeout=180,
    )
    if add_proc.returncode != 0:
        detail = _safe_text(add_proc.stderr or add_proc.stdout or "git worktree add failed", limit=400)
        raise RuntimeError(f"unable to create isolated worktree: {detail}")

    synced_overlay = _sync_worktree_overlay(
        source_repo_root=source_repo_root,
        worktree_root=target,
    )
    return target, synced_overlay


def _focus_metrics_from_payload(payload: dict[str, Any]) -> list[str]:
    hp_scores = payload.get("hp_scores", [])
    ranked: list[tuple[float, str]] = []
    if isinstance(hp_scores, list):
        for entry in hp_scores:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name", "") or "").strip()
            score = _parse_float_field(entry.get("score"))
            if not name or score is None:
                continue
            ranked.append((score, name))
    ranked.sort(key=lambda item: (item[0], item[1]))
    focus = [f"{name} ({score:.4f})" for score, name in ranked[:3]]
    if focus:
        return focus
    return list(DEFAULT_FOCUS_METRICS)


def _current_focus_metrics(*, run_dir: Path, state_dir: Path) -> list[str]:
    for candidate in (run_dir / "latest.json", state_dir / "evals" / "autoresearch_latest.json"):
        payload = _read_json(candidate)
        if payload:
            focus = _focus_metrics_from_payload(payload.get("evaluator", payload))
            if focus:
                return focus
    return list(DEFAULT_FOCUS_METRICS)


def _allocate_run_dir(state_dir: Path) -> Path:
    root = state_dir / "logs" / "codex_overnight"
    root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    attempt = 0
    while True:
        suffix = "" if attempt == 0 else f"-{attempt:02d}"
        candidate = root / f"{timestamp}{suffix}"
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            attempt += 1


def _build_run_manifest_payload(
    *,
    run_dir: Path,
    repo_root: Path,
    source_repo_root: Path,
    state_dir: Path,
    mission: str,
    settings: RunSettings,
    initial_snapshot: GitSnapshot,
    isolated_worktree: bool = False,
    synced_overlay: Sequence[str] = (),
    created_at: str | None = None,
) -> dict[str, Any]:
    mission_file = run_dir / "mission_brief.md"
    return {
        "run_id": run_dir.name,
        "label": settings.label,
        "created_at": created_at or utc_ts(),
        "repo_root": str(repo_root),
        "source_repo_root": str(source_repo_root),
        "isolated_worktree": isolated_worktree,
        "worktree_overlay": list(synced_overlay),
        "state_dir": str(state_dir),
        "mission_file": str(mission_file),
        "mission_excerpt": _safe_text(mission, limit=300),
        "settings": asdict(settings),
        "initial_git_snapshot": asdict(initial_snapshot),
    }


def _write_run_manifest(
    *,
    run_dir: Path,
    repo_root: Path,
    source_repo_root: Path,
    state_dir: Path,
    mission: str,
    settings: RunSettings,
    initial_snapshot: GitSnapshot,
    isolated_worktree: bool = False,
    synced_overlay: Sequence[str] = (),
) -> tuple[Path, dict[str, Any]]:
    mission_file = run_dir / "mission_brief.md"
    _atomic_write_text(mission_file, mission.rstrip() + "\n")
    manifest_file = run_dir / "run_manifest.json"
    payload = _build_run_manifest_payload(
        run_dir=run_dir,
        repo_root=repo_root,
        source_repo_root=source_repo_root,
        state_dir=state_dir,
        mission=mission,
        settings=settings,
        initial_snapshot=initial_snapshot,
        isolated_worktree=isolated_worktree,
        synced_overlay=synced_overlay,
    )
    write_json(manifest_file, payload)
    return manifest_file, payload


def _update_run_manifest(
    manifest_file: Path,
    *,
    manifest_defaults: dict[str, Any],
    latest_cycle: dict[str, Any],
    cycle_count: int,
) -> None:
    payload = dict(manifest_defaults)
    payload.update(_read_json(manifest_file))
    payload["updated_at"] = utc_ts()
    payload["cycles_completed"] = cycle_count
    payload["latest_cycle"] = latest_cycle
    payload["latest_summary_fields"] = latest_cycle.get("summary_fields", {})
    payload["final_git_snapshot"] = latest_cycle.get("after", {})
    write_json(manifest_file, payload)


def write_morning_handoff(
    *,
    run_dir: Path,
    state_dir: Path,
    mission: str,
    settings: RunSettings,
    snapshots: Sequence[dict[str, Any]],
) -> Path:
    latest = snapshots[-1] if snapshots else {}
    summary_fields = latest.get("summary_fields", {})
    files = _parse_files_field(str(summary_fields.get("files", "")))
    lines = [
        "# Codex Overnight Handoff",
        "",
        f"- updated_at: {utc_ts()}",
        f"- label: {settings.label}",
        f"- run_dir: {run_dir}",
        f"- cycles_completed: {len(snapshots)}",
        f"- mission: {_safe_text(mission, limit=220)}",
    ]
    if latest:
        latest_omega = latest.get("actual_omega")
        if latest_omega is None:
            latest_omega = f"proxy {latest.get('omega_proxy', 'n/a')}"
        latest_psi = latest.get("actual_psi")
        if latest_psi is None:
            latest_psi = f"proxy {latest.get('psi_proxy', 'n/a')}"
        lines.extend(
            [
                f"- latest_cycle: {latest.get('cycle', 0)}",
                f"- latest_rc: {latest.get('rc', 1)}",
                f"- latest_timed_out: {latest.get('timed_out', False)}",
                f"- latest_omega: {latest_omega}",
                f"- latest_psi: {latest_psi}",
                f"- latest_regime: {latest.get('regime', 'n/a')}",
                f"- latest_metrics_source: {latest.get('metrics_source', 'n/a')}",
                f"- latest_eval: {latest.get('evaluator', {}).get('summary_line', 'n/a')}",
                "",
                "## Latest Result",
                "",
                f"- result: {summary_fields.get('result', '') or '(missing)'}",
                f"- files: {', '.join(files) if files else 'none'}",
                f"- tests: {summary_fields.get('tests', '') or 'not reported'}",
                f"- blockers: {summary_fields.get('blockers', '') or 'none'}",
                f"- self_update: {summary_fields.get('self_update', '') or 'none'}",
                f"- critic_update: {summary_fields.get('critic_update', '') or 'none'}",
                "",
                "## Recent Cycles",
                "",
            ]
        )
        recent = list(snapshots)[-5:]
        for snapshot in recent:
            recent_fields = snapshot.get("summary_fields", {})
            recent_omega = snapshot.get("actual_omega")
            if recent_omega is None:
                recent_omega = f"proxy {snapshot.get('omega_proxy', 'n/a')}"
            recent_psi = snapshot.get("actual_psi")
            if recent_psi is None:
                recent_psi = f"proxy {snapshot.get('psi_proxy', 'n/a')}"
            lines.append(
                f"- cycle {snapshot.get('cycle', 0):03d}: "
                f"rc={snapshot.get('rc', 1)} "
                f"timed_out={snapshot.get('timed_out', False)} "
                f"metrics_source={snapshot.get('metrics_source', 'n/a')} "
                f"omega={recent_omega} "
                f"psi={recent_psi} "
                f"result={recent_fields.get('result', '') or '(missing)'}"
            )
    else:
        lines.extend(["", "No cycles completed yet."])

    handoff_text = "\n".join(lines) + "\n"
    handoff_file = run_dir / "morning_handoff.md"
    _atomic_write_text(handoff_file, handoff_text)
    shared_handoff = state_dir / "shared" / "codex_overnight_handoff.md"
    shared_handoff.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(shared_handoff, handoff_text)
    return handoff_file


def _read_mission(args: argparse.Namespace) -> str:
    if args.mission_file:
        return Path(args.mission_file).expanduser().read_text(encoding="utf-8").strip()
    if args.mission_brief:
        return args.mission_brief.strip()
    return DEFAULT_MISSION


def _render_minimal_codex_config(*, repo_root: Path) -> str:
    return (
        'model = "gpt-5.4"\n'
        'model_reasoning_effort = "high"\n'
        'personality = "pragmatic"\n'
        'approval_policy = "never"\n'
        'sandbox_mode = "workspace-write"\n'
        'web_search = "cached"\n'
        '\n'
        f'[projects."{LOGIN_HOME}"]\n'
        'trust_level = "trusted"\n'
        '\n'
        f'[projects."{repo_root}"]\n'
        'trust_level = "trusted"\n'
        '\n'
        '[features]\n'
        'multi_agent = false\n'
    )


def _copy_codex_entry(*, src: Path, dst: Path) -> None:
    if not src.exists():
        return
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _remove_codex_entry(dst: Path) -> None:
    if dst.is_symlink() or dst.is_file():
        dst.unlink()
        return
    if dst.exists():
        shutil.rmtree(dst)


def _is_missing_path_error(exc: BaseException) -> bool:
    if isinstance(exc, shutil.Error):
        return bool(exc.args) and all(
            len(entry) >= 3 and _is_missing_path_error(entry[2])
            for entry in exc.args[0]
        )
    if isinstance(exc, FileNotFoundError):
        return True
    if isinstance(exc, OSError):
        return exc.errno in {errno.ENOENT, errno.ESTALE}
    return False


def _refresh_codex_entry(*, src: Path, dst: Path) -> None:
    try:
        if dst.exists() or dst.is_symlink():
            _remove_codex_entry(dst)
    except OSError as exc:
        if not _is_missing_path_error(exc):
            raise
    try:
        _copy_codex_entry(src=src, dst=dst)
    except (OSError, shutil.Error) as exc:
        if not _is_missing_path_error(exc):
            raise


def prepare_codex_home(
    *,
    repo_root: Path,
    state_dir: Path,
    home_root: Path | None = None,
) -> Path:
    home_root = home_root or (state_dir / "codex_lean_home")
    codex_dir = home_root / ".codex"
    codex_dir.mkdir(parents=True, exist_ok=True)
    (codex_dir / "memories").mkdir(parents=True, exist_ok=True)
    state_alias = home_root / ".dharma"
    if state_alias.is_symlink():
        if state_alias.resolve(strict=False) != state_dir:
            state_alias.unlink()
    elif state_alias.exists():
        _remove_codex_entry(state_alias)
    if not state_alias.exists() and not state_alias.is_symlink():
        state_alias.symlink_to(state_dir, target_is_directory=True)

    for filename in COPIED_CODEX_FILES:
        _refresh_codex_entry(src=REAL_CODEX_DIR / filename, dst=codex_dir / filename)

    for dirname in COPIED_CODEX_DIRS:
        _refresh_codex_entry(src=REAL_CODEX_DIR / dirname, dst=codex_dir / dirname)

    config_dst = codex_dir / "config.toml"
    try:
        if config_dst.exists() or config_dst.is_symlink():
            _remove_codex_entry(config_dst)
    except OSError as exc:
        if not _is_missing_path_error(exc):
            raise
    _atomic_write_text(
        config_dst,
        _render_minimal_codex_config(repo_root=repo_root),
    )
    return home_root


def build_codex_env(
    *,
    repo_root: Path,
    state_dir: Path,
    home_root: Path | None = None,
) -> dict[str, str]:
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("CODEX_"):
            env.pop(key, None)

    env["HOME"] = str(
        prepare_codex_home(
            repo_root=repo_root,
            state_dir=state_dir,
            home_root=home_root,
        )
    )
    env["DHARMA_HOME"] = str(state_dir)
    env["PWD"] = str(repo_root)
    return env


def gather_git_snapshot(repo_root: Path) -> GitSnapshot:
    branch = "unknown"
    head = "unknown"
    changed_files: list[str] = []
    staged_count = 0
    unstaged_count = 0
    untracked_count = 0

    status_proc = run_cmd(
        ["git", "status", "--porcelain=v1", "--branch"],
        cwd=repo_root,
        timeout=30,
    )
    if status_proc.returncode == 0:
        lines = status_proc.stdout.splitlines()
        if lines and lines[0].startswith("## "):
            branch = lines[0][3:].strip()
        for line in lines[1:]:
            if not line.strip():
                continue
            changed_files.append(line.rstrip())
            x = line[0]
            y = line[1]
            if line.startswith("??"):
                untracked_count += 1
                continue
            if x != " ":
                staged_count += 1
            if y != " ":
                unstaged_count += 1

    head_proc = run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_root, timeout=30)
    if head_proc.returncode == 0:
        head = head_proc.stdout.strip()

    return GitSnapshot(
        branch=branch,
        head=head,
        dirty=bool(changed_files),
        changed_files=changed_files[:40],
        staged_count=staged_count,
        unstaged_count=unstaged_count,
        untracked_count=untracked_count,
    )


def render_git_snapshot(snapshot: GitSnapshot) -> str:
    changed = "\n".join(f"- {line}" for line in snapshot.changed_files) or "- clean"
    return (
        f"branch: {snapshot.branch}\n"
        f"head: {snapshot.head}\n"
        f"dirty: {snapshot.dirty}\n"
        f"staged_count: {snapshot.staged_count}\n"
        f"unstaged_count: {snapshot.unstaged_count}\n"
        f"untracked_count: {snapshot.untracked_count}\n"
        f"changed_files:\n{changed}"
    )


def read_previous_summary(run_dir: Path, *, limit_chars: int = 3000) -> str:
    latest_output = run_dir / "latest_last_message.txt"
    if not latest_output.exists():
        return "(No previous cycle output.)"
    return latest_output.read_text(encoding="utf-8", errors="ignore")[:limit_chars]


def build_cycle_prompt(
    *,
    mission: str,
    repo_root: Path,
    state_dir: Path,
    cycle: int,
    before: GitSnapshot,
    previous_summary: str,
    source_repo_root: Path | None = None,
    isolated_worktree: bool = False,
    focus_metrics: Sequence[str] = (),
    preloaded_overlay: Sequence[str] = (),
) -> str:
    dse_readme = repo_root / "docs" / "dse" / "README.md"
    dse_hint = ""
    if dse_readme.exists():
        dse_hint = (
            f"- There is an active DSE document stack at {dse_readme}. "
            "Use it when it is relevant to the current highest-leverage slice.\n"
        )
    focus_line = ""
    if focus_metrics:
        focus_line = (
            "- Current weakest scored dimensions to target directly: "
            + ", ".join(focus_metrics)
            + ". Prefer work with a plausible path to improving these.\n"
        )
    isolation_line = ""
    if isolated_worktree and source_repo_root is not None:
        isolation_line = (
            f"- This cycle is running inside an isolated git worktree at {repo_root}, "
            f"derived from {source_repo_root}. The dirty source tree is intentionally out of scope.\n"
        )
    overlay_line = ""
    if preloaded_overlay:
        overlay_line = (
            "- This worktree is preloaded with supervisor overlay files: "
            + ", ".join(preloaded_overlay)
            + ". Treat those seeded diffs as automation baseline, not user WIP.\n"
        )

    return f"""You are running an overnight Codex autonomy cycle for dharma_swarm.

Cycle: {cycle}
Repo root: {repo_root}
Writable state dir: {state_dir}

Mission brief:
{mission}

Current git snapshot:
{render_git_snapshot(before)}

Previous cycle summary:
{previous_summary}

Operational rules:
- Inspect the current worktree yourself before deciding what to do.
- Choose one bounded, high-leverage slice that can be completed in this cycle.
- Respect existing uncommitted user changes. Do not revert, overwrite, or clean work you did not make.
- Avoid more runner/scorer/meta hardening unless it has a clear direct path to improving latency, cost efficiency, or tool reliability.
- Do not commit, push, reset, or open PRs.
- Prefer concrete code, tests, and verification over broad planning.
- If the best next move is preparatory, make it specific and useful: tests, docs, build packet, or a small refactor seam.
- Run focused verification after edits whenever feasible.
- If unrelated failures block full verification, note them clearly and still finish the bounded slice.
- This run is using a locked local scorer at `evaluate.py`. The harness will measure actual Ω and Ψ after your cycle.
- For each cycle, state one falsifiable hypothesis first, then predict signed Ω and Ψ deltas before you act.
- Do not invent post-hoc scores. Give the hypothesis, the predicted deltas, your confidence, the bounded result, and concise SELF/CRITIC updates.
- Favor work that can improve runtime latency, cost discipline, provider/tool reliability, or routing quality under realistic load.
{dse_hint}- You may read and write under the repo root and {state_dir}.
{focus_line}{isolation_line}{overlay_line}

At the end, respond in this exact shape:
HYPOTHESIS: <one falsifiable sentence>
PREDICTED_OMEGA_DELTA: <signed float or "unknown">
PREDICTED_PSI_DELTA: <signed float or "unknown">
CONFIDENCE: <0.00-1.00 or "unknown">
RESULT: <one short paragraph>
FILES: <comma-separated file paths or "none">
TESTS: <what you ran or "not run">
BLOCKERS: <short note or "none">
SELF_UPDATE: <one concise self-model update or "none">
CRITIC_UPDATE: <one concise anti-pattern / failure note or "none">
"""


def build_codex_exec_command(
    *,
    repo_root: Path,
    state_dir: Path,
    output_file: Path,
    model: str = "",
) -> list[str]:
    cmd = [
        "codex",
        "-a",
        "never",
        "-s",
        "workspace-write",
        "exec",
        "-C",
        str(repo_root),
        "--add-dir",
        str(state_dir),
        "-o",
        str(output_file),
        "-",
    ]
    if model.strip():
        exec_index = cmd.index("exec")
        cmd[exec_index + 1 : exec_index + 1] = ["-m", model.strip()]
    return cmd


def append_cycle_report(
    *,
    report_file: Path,
    cycle: int,
    started_at: str,
    duration_sec: float,
    prompt_file: Path,
    output_file: Path,
    summary_text: str,
    rc: int,
    before: GitSnapshot,
    after: GitSnapshot,
) -> None:
    lines = [
        f"## Cycle {cycle:03d}",
        f"- started_at: {started_at}",
        f"- duration_sec: {duration_sec:.1f}",
        f"- rc: {rc}",
        f"- prompt_file: {prompt_file}",
        f"- output_file: {output_file}",
        f"- before_dirty: {before.dirty}",
        f"- after_dirty: {after.dirty}",
        f"- before_changed: {len(before.changed_files)}",
        f"- after_changed: {len(after.changed_files)}",
        "",
        "Summary:",
        "",
        _safe_text(summary_text, limit=1800),
        "",
    ]
    append_text(report_file, "\n".join(lines))


def run_cycle(
    *,
    repo_root: Path,
    state_dir: Path,
    run_dir: Path,
    cycle: int,
    mission: str,
    model: str,
    timeout: int,
    source_repo_root: Path | None = None,
    isolated_worktree: bool = False,
    preloaded_overlay: Sequence[str] = (),
) -> dict[str, Any]:
    before = gather_git_snapshot(repo_root)
    ensure_autoresearch_files(repo_root)
    previous_summary = read_previous_summary(run_dir)
    focus_metrics = _current_focus_metrics(run_dir=run_dir, state_dir=state_dir)
    prompt = build_cycle_prompt(
        mission=mission,
        repo_root=repo_root,
        state_dir=state_dir,
        cycle=cycle,
        before=before,
        previous_summary=previous_summary,
        source_repo_root=source_repo_root,
        isolated_worktree=isolated_worktree,
        focus_metrics=focus_metrics,
        preloaded_overlay=preloaded_overlay,
    )

    prompts_dir = run_dir / "prompts"
    outputs_dir = run_dir / "outputs"
    logs_dir = run_dir / "logs"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    prompt_file = prompts_dir / f"cycle_{cycle:03d}.md"
    output_file = outputs_dir / f"cycle_{cycle:03d}_last_message.txt"
    stdout_file = logs_dir / f"cycle_{cycle:03d}_stdout.log"
    _atomic_write_text(prompt_file, prompt)

    cmd = build_codex_exec_command(
        repo_root=repo_root,
        state_dir=state_dir,
        output_file=output_file,
        model=model,
    )

    started_at = utc_ts()
    start = time.time()
    timed_out = False
    codex_home_root = run_dir / "codex_lean_home"
    try:
        codex_env = build_codex_env(
            repo_root=repo_root,
            state_dir=state_dir,
            home_root=codex_home_root,
        )
    except OSError as exc:
        stdout = _build_startup_failure_summary(
            stage="codex home preparation failed",
            exc=exc,
        )
        rc = _os_error_return_code(exc)
    else:
        try:
            proc = run_cmd(
                cmd,
                cwd=repo_root,
                timeout=timeout,
                input_text=prompt,
                env=codex_env,
            )
            stdout = _coerce_text(proc.stdout) + _coerce_text(proc.stderr)
            rc = proc.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = (
                _coerce_text(getattr(exc, "stdout", None) or getattr(exc, "output", None))
                + _coerce_text(exc.stderr)
            )
            rc = 124
        except OSError as exc:
            stdout = _build_startup_failure_summary(
                stage="codex invocation failed",
                exc=exc,
            )
            rc = _os_error_return_code(exc)
    duration_sec = time.time() - start

    stdout_file.write_text(stdout, encoding="utf-8", errors="ignore")
    if not output_file.exists():
        _atomic_write_text(output_file, "")

    summary_text = _normalize_cycle_summary(
        _resolve_cycle_summary(output_file=output_file, stdout=stdout)
    )
    summary_fields = parse_summary_fields(summary_text)
    _atomic_write_text(run_dir / "latest_last_message.txt", summary_text + "\n")
    previous_snapshot = _read_json(run_dir / "latest.json")
    omega_proxy = _compute_omega_proxy(
        summary_fields=summary_fields,
        rc=rc,
        timed_out=timed_out,
    )
    psi_proxy = _compute_psi_proxy(
        summary_fields=summary_fields,
        previous_snapshot=previous_snapshot,
        omega_proxy=omega_proxy,
    )
    evaluator = _run_locked_evaluator(
        repo_root=repo_root,
        state_dir=state_dir,
        run_dir=run_dir,
        cycle=cycle,
        timeout=timeout,
    )
    actual_omega = evaluator.get("omega")
    actual_psi = evaluator.get("psi")
    metrics_locked = (
        evaluator.get("rc") == 0
        and evaluator.get("timed_out") is False
        and isinstance(actual_omega, (float, int))
        and isinstance(actual_psi, (float, int))
    )
    metrics_source = "locked" if metrics_locked else "unavailable"
    if metrics_locked:
        actual_omega = float(actual_omega)
        actual_psi = float(actual_psi)
        regime = _classify_regime(
            history=_recent_omega_history(run_dir),
            current=actual_omega,
        )
    else:
        actual_omega = None
        actual_psi = None
        regime = "unknown"
    kept = _compute_keep_decision(
        previous_snapshot=previous_snapshot,
        current_omega=actual_omega,
        current_psi=actual_psi,
        metrics_source=metrics_source,
        rc=rc,
        timed_out=timed_out,
        blockers_text=summary_fields.get("blockers", ""),
    )

    after = gather_git_snapshot(repo_root)
    report_file = run_dir / "report.md"
    append_cycle_report(
        report_file=report_file,
        cycle=cycle,
        started_at=started_at,
        duration_sec=duration_sec,
        prompt_file=prompt_file,
        output_file=output_file,
        summary_text=summary_text or stdout,
        rc=rc,
        before=before,
        after=after,
    )

    snapshot = {
        "cycle": cycle,
        "ts": utc_ts(),
        "started_at": started_at,
        "duration_sec": round(duration_sec, 2),
        "rc": rc,
        "timed_out": timed_out,
        "prompt_file": str(prompt_file),
        "output_file": str(output_file),
        "stdout_file": str(stdout_file),
        "summary_text": summary_text,
        "summary_fields": summary_fields,
        "omega_proxy": omega_proxy,
        "psi_proxy": psi_proxy,
        "actual_omega": round(actual_omega, 4) if actual_omega is not None else None,
        "actual_psi": round(actual_psi, 4) if actual_psi is not None else None,
        "metrics_source": metrics_source,
        "evaluator": evaluator,
        "regime": regime,
        "kept": kept,
        "before": asdict(before),
        "after": asdict(after),
    }
    append_jsonl(run_dir / "cycles.jsonl", snapshot)
    write_json(run_dir / "latest.json", snapshot)
    _append_autoresearch_artifacts(repo_root=repo_root, snapshot=snapshot)
    write_json(
        heartbeat_file_for(state_dir),
        {
            "ts": utc_ts(),
            "cycle": cycle,
            "run_dir": str(run_dir),
            "duration_sec": round(duration_sec, 2),
            "rc": rc,
            "timed_out": timed_out,
            "report_file": str(report_file),
            "result": summary_fields.get("result", ""),
            "blockers": summary_fields.get("blockers", ""),
            "omega_proxy": omega_proxy,
            "psi_proxy": psi_proxy,
            "actual_omega": round(actual_omega, 4) if actual_omega is not None else None,
            "actual_psi": round(actual_psi, 4) if actual_psi is not None else None,
            "metrics_source": metrics_source,
            "evaluator_summary": evaluator.get("summary_line", ""),
            "evaluator_report_file": evaluator.get("report_file", ""),
            "regime": regime,
        },
    )
    return snapshot


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Codex overnight in repeated autonomous cycles.")
    parser.add_argument("--hours", type=float, default=8.0, help="Wall-clock hours to run. Use 0 for continuous.")
    parser.add_argument("--poll-seconds", type=int, default=60, help="Sleep between cycles.")
    parser.add_argument("--cycle-timeout", type=int, default=5400, help="Per-cycle Codex timeout in seconds.")
    parser.add_argument("--max-cycles", type=int, default=0, help="Optional hard cap on cycle count.")
    parser.add_argument("--repo-root", default=str(ROOT), help="Repo root to run in.")
    parser.add_argument("--isolate-worktree", action="store_true", help="Run cycles in a detached worktree under the state dir.")
    parser.add_argument("--worktree-root", default="", help="Optional parent directory for detached worktrees.")
    parser.add_argument("--state-dir", default=str(STATE), help="State directory for logs and heartbeat.")
    parser.add_argument("--mission-brief", default="", help="Inline mission brief override.")
    parser.add_argument("--mission-file", default="", help="Read mission brief from a file.")
    parser.add_argument("--model", default="", help="Optional Codex model override.")
    parser.add_argument("--label", default="codex-overnight", help="Short operator label for this run.")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    source_repo_root = Path(args.repo_root).expanduser()
    state_dir = Path(args.state_dir).expanduser()
    run_dir = _allocate_run_dir(state_dir)
    run_file = run_file_for(state_dir)
    run_file.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(run_file, str(run_dir))

    mission = _read_mission(args)
    settings = RunSettings(
        label=args.label.strip() or "codex-overnight",
        hours=args.hours,
        poll_seconds=args.poll_seconds,
        cycle_timeout=args.cycle_timeout,
        max_cycles=args.max_cycles,
        model=args.model.strip(),
    )
    worktree_overlay: list[str] = []
    repo_root = source_repo_root
    if args.isolate_worktree:
        try:
            repo_root, worktree_overlay = prepare_isolated_worktree(
                source_repo_root=source_repo_root,
                state_dir=state_dir,
                run_dir=run_dir,
                label=settings.label,
                worktree_root=Path(args.worktree_root).expanduser() if args.worktree_root else None,
            )
        except Exception as exc:
            append_text(
                run_dir / "report.md",
                "\n".join(
                    [
                        f"# Codex Overnight Run — {utc_ts()}",
                        "",
                        f"- source_repo_root: {source_repo_root}",
                        f"- state_dir: {state_dir}",
                        f"- label: {settings.label}",
                        f"- worktree_setup_failed: {_safe_text(str(exc), limit=500)}",
                        "",
                    ]
                ),
            )
            print(f"codex_overnight worktree setup failed: {exc}", file=sys.stderr)
            return 1

    ensure_autoresearch_files(repo_root)
    initial_snapshot = gather_git_snapshot(repo_root)
    manifest_file, manifest_defaults = _write_run_manifest(
        run_dir=run_dir,
        repo_root=repo_root,
        source_repo_root=source_repo_root,
        state_dir=state_dir,
        mission=mission,
        settings=settings,
        initial_snapshot=initial_snapshot,
        isolated_worktree=args.isolate_worktree,
        synced_overlay=worktree_overlay,
    )
    append_text(
        run_dir / "report.md",
        "\n".join(
            [
                f"# Codex Overnight Run — {utc_ts()}",
                "",
                f"- repo_root: {repo_root}",
                f"- source_repo_root: {source_repo_root}",
                f"- isolated_worktree: {str(args.isolate_worktree).lower()}",
                f"- worktree_overlay_files: {', '.join(worktree_overlay) if worktree_overlay else 'none'}",
                f"- state_dir: {state_dir}",
                f"- label: {settings.label}",
                f"- mission: {_safe_text(mission, limit=300)}",
                f"- manifest: {manifest_file}",
                "",
            ]
        ),
    )

    end_at = time.time() + (args.hours * 3600.0) if args.hours > 0 else None
    cycle = 0
    latest: dict[str, Any] = {}
    cycle_snapshots: list[dict[str, Any]] = []
    while True:
        cycle += 1
        latest = run_cycle(
            repo_root=repo_root,
            state_dir=state_dir,
            run_dir=run_dir,
            cycle=cycle,
            mission=mission,
            model=args.model,
            timeout=args.cycle_timeout,
            source_repo_root=source_repo_root,
            isolated_worktree=args.isolate_worktree,
            preloaded_overlay=worktree_overlay,
        )
        cycle_snapshots.append(latest)
        _update_run_manifest(
            manifest_file,
            manifest_defaults=manifest_defaults,
            latest_cycle=latest,
            cycle_count=len(cycle_snapshots),
        )
        write_morning_handoff(
            run_dir=run_dir,
            state_dir=state_dir,
            mission=mission,
            settings=settings,
            snapshots=cycle_snapshots,
        )
        if args.once:
            break
        if args.max_cycles > 0 and cycle >= args.max_cycles:
            break
        if end_at is not None and time.time() >= end_at:
            break
        time.sleep(max(1, args.poll_seconds))

    print(
        f"codex_overnight cycle={latest.get('cycle', 0)} "
        f"rc={latest.get('rc', 1)} run_dir={run_dir} "
        f"report={run_dir / 'report.md'}"
    )
    if args.once:
        latest_rc = latest.get("rc", 0)
        return int(latest_rc) if isinstance(latest_rc, int) else 1
    return 0


__all__ = [
    "DEFAULT_MISSION",
    "GitSnapshot",
    "RunSettings",
    "build_arg_parser",
    "build_codex_exec_command",
    "build_cycle_prompt",
    "gather_git_snapshot",
    "main",
    "parse_summary_fields",
    "render_git_snapshot",
    "write_morning_handoff",
]
