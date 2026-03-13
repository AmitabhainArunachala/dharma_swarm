"""DGC doctor diagnostics.

Health and readiness checks for router/memory/provider execution lanes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from typing import Any
from urllib.parse import urlparse


HOME = Path.home()


@dataclass
class DoctorCheck:
    name: str
    status: str  # PASS | WARN | FAIL
    summary: str
    detail: str = ""
    fix: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _mask_secret(raw: str) -> str:
    if not raw:
        return ""
    if len(raw) <= 10:
        return "*" * len(raw)
    return f"{raw[:4]}...{raw[-4:]}"


def _add(checks: list[DoctorCheck], **kwargs: Any) -> None:
    checks.append(DoctorCheck(**kwargs))


def _venv_python() -> Path | None:
    candidate = HOME / "dharma_swarm" / ".venv" / "bin" / "python"
    if candidate.exists() and os.access(candidate, os.X_OK):
        return candidate
    return None


def _run_venv_probe(code: str, *, timeout_seconds: float) -> tuple[bool, str]:
    py = _venv_python()
    if py is None:
        return (False, "venv python not found")
    env = os.environ.copy()
    repo_root = str(HOME / "dharma_swarm")
    current_pp = env.get("PYTHONPATH", "").strip()
    env["PYTHONPATH"] = (
        repo_root
        if not current_pp
        else f"{repo_root}{os.pathsep}{current_pp}"
    )
    try:
        proc = subprocess.run(
            [str(py), "-c", code],
            capture_output=True,
            text=True,
            timeout=max(0.5, timeout_seconds),
            env=env,
        )
    except Exception as exc:
        return (False, str(exc))
    out = (proc.stdout or proc.stderr or "").strip()
    if proc.returncode == 0:
        return (True, out)
    return (False, out or f"rc={proc.returncode}")


def _check_env_autoload(checks: list[DoctorCheck]) -> None:
    cli_path = HOME / "dharma_swarm" / "dharma_swarm" / "dgc_cli.py"
    cli_has_bootstrap = False
    if cli_path.exists():
        try:
            cli_has_bootstrap = "_bootstrap_env()" in cli_path.read_text(errors="ignore")
        except Exception:
            cli_has_bootstrap = False

    dgc_path = shutil.which("dgc")
    active_path = Path(sys.argv[0]).expanduser()

    launchers: list[Path] = []
    if dgc_path:
        launchers.append(Path(dgc_path))
    if active_path.exists() and active_path not in launchers:
        launchers.append(active_path)

    if not launchers:
        _add(
            checks,
            name="env_autoload",
            status="FAIL",
            summary="`dgc` command not found on PATH",
            fix="Ensure dgc is installed and available on PATH.",
        )
        return

    details: list[str] = []
    launcher_ok = False
    for launcher in launchers:
        has_bootstrap = False
        delegates_to_cli = False
        if launcher.exists() and launcher.is_file():
            try:
                text = launcher.read_text(errors="ignore")
            except Exception:
                text = ""
            has_bootstrap = "_bootstrap_env()" in text
            delegates_to_cli = (
                "from dharma_swarm.dgc_cli import main" in text
                or "dharma_swarm.dgc_cli:main" in text
            )

        lane_ok = has_bootstrap or (delegates_to_cli and cli_has_bootstrap)
        launcher_ok = launcher_ok or lane_ok
        details.append(
            f"{launcher} bootstrap={has_bootstrap} delegates={delegates_to_cli} lane_ok={lane_ok}"
        )

    if launcher_ok and cli_has_bootstrap:
        _add(
            checks,
            name="env_autoload",
            status="PASS",
            summary="autoload wired for active launcher path(s) and CLI",
            detail=" | ".join(details),
        )
        return

    if launcher_ok or cli_has_bootstrap:
        _add(
            checks,
            name="env_autoload",
            status="WARN",
            summary="autoload wired in one path but not both",
            detail=" | ".join(details) + f" | cli={cli_has_bootstrap}",
            fix="Keep both launcher and dharma_swarm/dgc_cli.py env bootstrap enabled.",
        )
        return

    _add(
        checks,
        name="env_autoload",
        status="FAIL",
        summary="no env bootstrap detected in active launcher paths",
        fix="Add .env bootstrap to dgc launcher and dharma_swarm.dgc_cli.",
    )


def _check_router_env(checks: list[DoctorCheck]) -> None:
    required = (
        "DGC_ROUTER_REDIS_URL",
        "DGC_FASTTEXT_MODEL_PATH",
        "DGC_ROUTER_CANARY_PERCENT",
        "DGC_ROUTER_LEARNING_ENABLED",
    )
    missing = [key for key in required if not os.getenv(key, "").strip()]
    if missing:
        _add(
            checks,
            name="router_env",
            status="WARN",
            summary=f"missing {len(missing)} router env value(s)",
            detail=", ".join(missing),
            fix="Populate missing keys in ~/dharma_swarm/.env.",
        )
        return
    _add(
        checks,
        name="router_env",
        status="PASS",
        summary="core router env values present",
    )


def _check_worker_bins(checks: list[DoctorCheck], timeout_seconds: float) -> None:
    bins = ("claude", "codex")
    found = []
    details = []
    for name in bins:
        path = shutil.which(name)
        if not path:
            details.append(f"{name}=MISSING")
            continue
        found.append(name)
        try:
            proc = subprocess.run(
                [path, "--version"],
                capture_output=True,
                text=True,
                timeout=max(1.0, timeout_seconds),
            )
            line = (proc.stdout or proc.stderr or "").strip().splitlines()
            details.append(f"{name}=OK ({line[0] if line else 'version unknown'})")
        except Exception as exc:
            details.append(f"{name}=ERROR ({exc})")

    if found:
        _add(
            checks,
            name="worker_bins",
            status="PASS",
            summary=f"worker CLIs available: {', '.join(found)}",
            detail="; ".join(details),
        )
        return

    _add(
        checks,
        name="worker_bins",
        status="WARN",
        summary="no worker CLI found (`claude`/`codex`)",
        detail="; ".join(details),
        fix="Install at least one worker CLI and ensure it is on PATH.",
    )


def _check_provider_env(checks: list[DoctorCheck]) -> None:
    provider_keys = (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "NVIDIA_NIM_API_KEY",
        "OLLAMA_API_KEY",
    )
    present: list[str] = []
    for key in provider_keys:
        value = os.getenv(key, "").strip()
        if value:
            present.append(f"{key}={_mask_secret(value)}")

    ollama = os.getenv("OLLAMA_BASE_URL", "").strip()
    if ollama:
        present.append(f"OLLAMA_BASE_URL={ollama}")

    if present:
        _add(
            checks,
            name="provider_env",
            status="PASS",
            summary=f"provider lane configured ({len(present)} entries)",
            detail=", ".join(present),
        )
        return

    _add(
        checks,
        name="provider_env",
        status="WARN",
        summary="no provider credentials/endpoints found in env",
        fix="Set at least one provider key in env (.env or shell).",
    )


def _check_fasttext(checks: list[DoctorCheck]) -> None:
    path = os.getenv("DGC_FASTTEXT_MODEL_PATH", "").strip()
    if not path:
        path = str(HOME / ".dharma" / "models" / "lid.176.bin")
    model_path = Path(path)

    if not model_path.exists():
        _add(
            checks,
            name="fasttext",
            status="WARN",
            summary=f"model missing: {model_path}",
            fix="Download lid.176.bin and set DGC_FASTTEXT_MODEL_PATH.",
        )
        return

    size_mb = model_path.stat().st_size / (1024 * 1024)
    def _venv_fasttext_ok() -> bool:
        ok, out = _run_venv_probe(
            (
                "from dharma_swarm.router_v1 import _predict_fasttext_language; "
                "p=_predict_fasttext_language('日本語の文章です。'); "
                "print('ok' if p else 'none')"
            ),
            timeout_seconds=1.2,
        )
        return ok and "ok" in out

    try:
        from dharma_swarm.router_v1 import _predict_fasttext_language

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            pred = _predict_fasttext_language("日本語の文章です。")
        if pred and pred[0]:
            _add(
                checks,
                name="fasttext",
                status="PASS",
                summary=f"model loaded ({size_mb:.1f}MB), sample={pred[0]}:{pred[1]:.3f}",
            )
            return
        if _venv_fasttext_ok():
            _add(
                checks,
                name="fasttext",
                status="PASS",
                summary=f"model loaded via venv runtime ({size_mb:.1f}MB)",
                detail="Primary interpreter missing fasttext bindings; venv path works.",
            )
            return
    except Exception as exc:
        if _venv_fasttext_ok():
            _add(
                checks,
                name="fasttext",
                status="PASS",
                summary=f"model loaded via venv runtime ({size_mb:.1f}MB)",
                detail="Primary interpreter missing fasttext bindings; venv path works.",
            )
            return
        _add(
            checks,
            name="fasttext",
            status="WARN",
            summary=f"model exists ({size_mb:.1f}MB) but runtime failed",
            detail=str(exc),
            fix="Install fasttext-wheel in active runtime and verify import path.",
        )
        return

    _add(
        checks,
        name="fasttext",
        status="WARN",
        summary=f"model exists ({size_mb:.1f}MB) but prediction unavailable",
        fix="Check fasttext-wheel install and router_v1 fasttext path.",
    )


def _check_redis(checks: list[DoctorCheck], timeout_seconds: float, quick: bool) -> None:
    url = os.getenv("DGC_ROUTER_REDIS_URL", "").strip()
    if not url:
        _add(
            checks,
            name="redis",
            status="WARN",
            summary="DGC_ROUTER_REDIS_URL not set",
            fix="Set DGC_ROUTER_REDIS_URL in .env (e.g. redis://127.0.0.1:6379/0).",
        )
        return

    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 6379
    try:
        with socket.create_connection((host, port), timeout=max(0.2, timeout_seconds)):
            pass
    except Exception as exc:
        lowered = str(exc).lower()
        if "operation not permitted" in lowered or "permission denied" in lowered:
            _add(
                checks,
                name="redis",
                status="WARN",
                summary=f"redis probe blocked by runtime permissions ({host}:{port})",
                detail=str(exc),
                fix="Run `dgc doctor` directly in terminal (not sandbox) for live Redis probe.",
            )
            return
        _add(
            checks,
            name="redis",
            status="FAIL",
            summary=f"socket connect failed ({host}:{port})",
            detail=str(exc),
            fix="Run scripts/start_router_redis.sh then re-run `dgc doctor`.",
        )
        return

    if quick:
        _add(
            checks,
            name="redis",
            status="PASS",
            summary=f"socket reachable at {host}:{port}",
        )
        return

    redis_spec = importlib.util.find_spec("redis")
    if redis_spec is None:
        ok, out = _run_venv_probe(
            (
                "import redis; "
                "c=redis.Redis.from_url("
                f"'{url}', decode_responses=True, socket_connect_timeout=0.8, socket_timeout=0.8"
                "); "
                "print('ok' if c.ping() else 'none')"
            ),
            timeout_seconds=1.5,
        )
        if ok and "ok" in out:
            _add(
                checks,
                name="redis",
                status="PASS",
                summary=f"redis ping OK via venv runtime ({host}:{port})",
            )
            return
        _add(
            checks,
            name="redis",
            status="WARN",
            summary=f"socket reachable at {host}:{port}, but `redis` package missing",
            fix="Install router extras: pip install 'dharma-swarm[router]'.",
        )
        return

    try:
        import redis  # type: ignore

        client = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=max(0.2, timeout_seconds),
            socket_timeout=max(0.2, timeout_seconds),
        )
        ok = bool(client.ping())
        if ok:
            _add(
                checks,
                name="redis",
                status="PASS",
                summary=f"redis ping OK ({host}:{port})",
            )
            return
    except Exception as exc:
        _add(
            checks,
            name="redis",
            status="WARN",
            summary=f"socket reachable but ping failed ({host}:{port})",
            detail=str(exc),
            fix="Check redis credentials/network and redis Python package runtime.",
        )
        return

    _add(
        checks,
        name="redis",
        status="WARN",
        summary=f"socket reachable but redis ping response was unexpected ({host}:{port})",
    )


def _check_router_wiring(checks: list[DoctorCheck]) -> None:
    try:
        from dharma_swarm.providers import ModelRouter, ProviderType
        from dharma_swarm.resilience import CircuitBreakerRegistry
        from dharma_swarm.router_v1 import detect_language_profile

        _ = ModelRouter
        _ = ProviderType
        _ = CircuitBreakerRegistry
        _ = detect_language_profile("This is a router smoke test.")
        _add(
            checks,
            name="router_wiring",
            status="PASS",
            summary="router modules import and basic language detection works",
        )
    except Exception as exc:
        _add(
            checks,
            name="router_wiring",
            status="FAIL",
            summary="router module wiring/import failed",
            detail=str(exc),
            fix="Fix import/runtime errors in providers/resilience/router_v1.",
        )


def _check_router_paths(checks: list[DoctorCheck]) -> None:
    memory_db = Path(
        os.getenv(
            "DGC_ROUTER_MEMORY_DB",
            str(HOME / ".dharma" / "logs" / "router" / "routing_memory.sqlite3"),
        )
    )
    audit_log = Path(
        os.getenv(
            "DGC_ROUTER_AUDIT_LOG",
            str(HOME / ".dharma" / "logs" / "router" / "routing_decisions.jsonl"),
        )
    )
    needs = [memory_db.parent, audit_log.parent]
    missing = [str(path) for path in needs if not path.exists()]

    if missing:
        _add(
            checks,
            name="router_paths",
            status="WARN",
            summary=f"router log dirs missing ({len(missing)})",
            detail=", ".join(missing),
            fix="Create directories before long-run: mkdir -p ~/.dharma/logs/router",
        )
        return

    _add(
        checks,
        name="router_paths",
        status="PASS",
        summary="router log/memory directories exist",
    )


def run_doctor(*, timeout_seconds: float = 1.5, quick: bool = False) -> dict[str, Any]:
    checks: list[DoctorCheck] = []
    _check_env_autoload(checks)
    _check_router_env(checks)
    _check_worker_bins(checks, timeout_seconds=timeout_seconds)
    _check_provider_env(checks)
    _check_fasttext(checks)
    _check_redis(checks, timeout_seconds=timeout_seconds, quick=quick)
    _check_router_paths(checks)
    _check_router_wiring(checks)

    pass_count = sum(1 for c in checks if c.status == "PASS")
    warn_count = sum(1 for c in checks if c.status == "WARN")
    fail_count = sum(1 for c in checks if c.status == "FAIL")

    status = "PASS"
    if fail_count:
        status = "FAIL"
    elif warn_count:
        status = "WARN"

    fixes = [c.fix for c in checks if c.fix]
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "summary": {
            "total": len(checks),
            "pass": pass_count,
            "warn": warn_count,
            "fail": fail_count,
        },
        "checks": [c.to_dict() for c in checks],
        "recommended_fixes": fixes,
    }


def doctor_exit_code(report: dict[str, Any], *, strict: bool = False) -> int:
    summary = report.get("summary", {})
    fail_count = int(summary.get("fail", 0))
    warn_count = int(summary.get("warn", 0))
    if fail_count > 0:
        return 2
    if strict and warn_count > 0:
        return 1
    return 0


def render_doctor_report(report: dict[str, Any]) -> str:
    lines = ["=== DGC DOCTOR ==="]
    lines.append(
        "Overall: "
        f"{report.get('status', 'UNKNOWN')} "
        f"(pass={report.get('summary', {}).get('pass', 0)}, "
        f"warn={report.get('summary', {}).get('warn', 0)}, "
        f"fail={report.get('summary', {}).get('fail', 0)})"
    )

    for check in report.get("checks", []):
        status = str(check.get("status", "UNKNOWN"))
        name = str(check.get("name", "unknown"))
        summary = str(check.get("summary", "")).strip()
        detail = str(check.get("detail", "")).strip()
        lines.append(f"[{status}] {name}: {summary}")
        if detail:
            lines.append(f"  detail: {detail}")

    fixes = [str(item).strip() for item in report.get("recommended_fixes", []) if str(item).strip()]
    if fixes:
        lines.append("")
        lines.append("Recommended fixes:")
        for idx, item in enumerate(fixes, start=1):
            lines.append(f"{idx}. {item}")

    return "\n".join(lines)
