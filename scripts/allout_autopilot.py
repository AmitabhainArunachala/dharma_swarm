#!/usr/bin/env python3
"""All-out autonomous supervisor for dharma_swarm.

Goals per cycle:
1) Run core health/test checks.
2) Read N local files from the ecosystem.
3) Generate a fresh 3-5 step TODO plan from findings.
4) Every Nth cycle: evolve the prompt via 3-layer master prompt engineer.
5) Repeat for a fixed wall-clock duration.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add project root to path so imports work when run as a script
import sys
sys.path.insert(0, str(Path.home() / "dharma_swarm"))

from dharma_swarm.master_prompt_engineer import (
    assess_quality,
    generate_local_prompt,
    record_cycle,
    should_evolve_prompt,
)

ROOT = Path.home() / "dharma_swarm"
STATE = Path.home() / ".dharma"
LOG_DIR = STATE / "logs" / "allout"
HEARTBEAT_FILE = STATE / "allout_heartbeat.json"
SHARED_DIR = STATE / "shared"
COMPOUNDING_LEDGER_FILE = SHARED_DIR / "compounding_ledger.jsonl"

NOISE_STEP_PATTERNS = (
    "append nightly summary",
    "emit final",
    "handoff at 04:00",
    "generate nightly findings",
    "capture performance deltas",
)

INTELLIGENCE_STEP_PATTERNS = (
    "resolve highest-value todo/fixme",
    "add focused tests",
    "run full `pytest",
    "run cli command-dispatch tests",
    "run engine safety tests",
    "run integration tests",
    "run provider core tests",
    "run provider quality tests",
    "run pulse + living-layer tests",
)

INFRA_STEP_PATTERNS = (
    "nvidia rag services",
    "dgc rag health",
    "rag retrieval quality",
    "data flywheel endpoint mapping",
    "flywheel job lifecycle",
)

_HEAL_LAST_ATTEMPT: dict[str, float] = {}


@dataclass
class CycleCommand:
    label: str
    cmd: list[str]
    cwd: Path
    timeout: int = 600
    optional: bool = False


def utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def jst_now() -> str:
    return subprocess.check_output(
        ["date", "+%Y-%m-%d %H:%M:%S %Z"],
        env={**os.environ, "TZ": "Asia/Tokyo"},
        text=True,
    ).strip()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def append_line(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=True) + "\n")


def run_cmd(cmd: list[str], *, cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def _is_local_http_base(url: str) -> bool:
    low = url.strip().lower()
    return (
        low.startswith("http://127.0.0.1")
        or low.startswith("http://localhost")
        or low.startswith("http://0.0.0.0")
    )


def _accelerator_mode() -> str:
    configured = any(
        os.getenv(key, "").strip()
        for key in ("DGC_NVIDIA_RAG_URL", "DGC_NVIDIA_INGEST_URL", "DGC_DATA_FLYWHEEL_URL")
    )
    raw = os.getenv("DGC_ACCELERATOR_MODE", "enabled" if configured else "dormant")
    mode = raw.strip().lower()
    return mode or ("enabled" if configured else "dormant")


def _accelerators_enabled() -> bool:
    return _accelerator_mode() not in {"0", "off", "disabled", "none", "dormant"}


def _step_uses_accelerators(step: str) -> bool:
    low = step.strip().lower()
    return any(p in low for p in INFRA_STEP_PATTERNS) or any(
        token in low
        for token in (
            "dgc rag health",
            "dgc flywheel jobs",
            "rag retrieval quality",
            "flywheel endpoint",
            "nvidia rag",
        )
    )


def _resolve_default_path(env_key: str, fallback: Path) -> Path:
    custom = os.getenv(env_key, "").strip()
    if custom:
        return Path(custom).expanduser()
    return fallback


def _cooldown_allows_heal(target: str) -> bool:
    cooldown = int(os.getenv("ALLOUT_HEAL_COOLDOWN_SEC", "300"))
    now = time.time()
    last = _HEAL_LAST_ATTEMPT.get(target, 0.0)
    if (now - last) < max(1, cooldown):
        return False
    _HEAL_LAST_ATTEMPT[target] = now
    return True


def _docker_compose_available() -> bool:
    try:
        proc = subprocess.run(
            ["/Applications/Docker.app/Contents/Resources/bin/docker", "compose", "version"],
            text=True,
            capture_output=True,
            timeout=20,
        )
        return proc.returncode == 0
    except Exception:
        return False


def _local_host_has_nvidia_gpu_runtime() -> bool:
    if sys.platform == "darwin":
        return False
    try:
        proc = subprocess.run(
            ["nvidia-smi", "-L"],
            text=True,
            capture_output=True,
            timeout=10,
        )
        return proc.returncode == 0 and bool((proc.stdout or "").strip())
    except Exception:
        return False


def _compose_up(compose_file: Path, *, cwd: Path, project_name: str, services: list[str] | None = None) -> tuple[int, str]:
    if not compose_file.exists():
        return (2, f"missing_compose_file={compose_file}")
    cmd = [
        "/Applications/Docker.app/Contents/Resources/bin/docker",
        "compose",
        "-f",
        str(compose_file),
        "-p",
        project_name,
        "up",
        "-d",
    ]
    no_build = os.getenv("ALLOUT_HEAL_NO_BUILD", "1") == "1"
    if no_build:
        cmd.append("--no-build")
    if services:
        cmd.extend(services)

    env = dict(os.environ)
    # Blueprint files typically rely on NGC_API_KEY; fall back from NVIDIA_API_KEY when needed.
    if not env.get("NGC_API_KEY") and env.get("NVIDIA_API_KEY"):
        env["NGC_API_KEY"] = env["NVIDIA_API_KEY"]

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            text=True,
            capture_output=True,
            timeout=int(os.getenv("ALLOUT_HEAL_COMPOSE_TIMEOUT_SEC", "180")),
        )
    except Exception as exc:
        return (2, f"compose_exception={exc}")
    detail = (proc.stdout or "") + (proc.stderr or "")
    if (
        proc.returncode != 0
        and no_build
        and os.getenv("ALLOUT_HEAL_ALLOW_BUILD", "0") == "1"
    ):
        cmd_with_build = [x for x in cmd if x != "--no-build"]
        try:
            proc2 = subprocess.run(
                cmd_with_build,
                cwd=str(cwd),
                env=env,
                text=True,
                capture_output=True,
                timeout=int(os.getenv("ALLOUT_HEAL_COMPOSE_TIMEOUT_SEC", "180")),
            )
            detail2 = (proc2.stdout or "") + (proc2.stderr or "")
            combo = (detail + "\n--- retry_with_build ---\n" + detail2)[-900:]
            return (proc2.returncode, combo)
        except Exception as exc:
            return (2, f"{detail[-400:]}\nretry_with_build_exception={exc}")
    return (proc.returncode, detail[-600:])


def _diagnose_compose_output(text: str) -> str:
    low = text.lower()
    if "ngc_api_key is required" in low or "required variable ngc_api_key is missing" in low:
        return "missing_ngc_api_key"
    if "permission denied while trying to connect to the docker daemon socket" in low:
        return "docker_socket_permission_denied"
    if "connect: operation not permitted" in low and "docker.sock" in low:
        return "docker_socket_blocked"
    if "manifest for" in low and "not found" in low:
        return "missing_image_manifest"
    if "no such file or directory" in low and "docker.sock" in low:
        return "docker_not_running"
    if "network_mode host" in low and "not supported" in low:
        return "host_network_unsupported"
    return "compose_failed"


def heal_nvidia_rag_local() -> dict[str, Any]:
    if not _docker_compose_available():
        return {"ok": False, "detail": "docker_compose_unavailable"}
    if not _local_host_has_nvidia_gpu_runtime():
        return {"ok": False, "detail": "local_nvidia_gpu_runtime_unavailable"}
    rag_repo = _resolve_default_path(
        "DGC_NVIDIA_RAG_REPO",
        Path.home() / "DHARMIC_GODEL_CLAW" / "cloned_source" / "nvidia-rag",
    )
    rag_compose = _resolve_default_path(
        "DGC_NVIDIA_RAG_COMPOSE_RAG",
        rag_repo / "deploy" / "compose" / "docker-compose-rag-server.yaml",
    )
    ingest_compose = _resolve_default_path(
        "DGC_NVIDIA_RAG_COMPOSE_INGEST",
        rag_repo / "deploy" / "compose" / "docker-compose-ingestor-server.yaml",
    )
    if not rag_repo.exists():
        return {"ok": False, "detail": f"missing_repo={rag_repo}"}

    if not (os.getenv("NGC_API_KEY") or os.getenv("NVIDIA_API_KEY")):
        return {"ok": False, "detail": "missing_ngc_api_key"}
    rc_ing, out_ing = _compose_up(
        ingest_compose,
        cwd=rag_repo,
        project_name=os.getenv("DGC_NVIDIA_RAG_PROJECT", "dgc-rag"),
        services=["ingestor-server"],
    )
    rc_rag, out_rag = _compose_up(
        rag_compose,
        cwd=rag_repo,
        project_name=os.getenv("DGC_NVIDIA_RAG_PROJECT", "dgc-rag"),
        services=["rag-server"],
    )

    rag_base = os.getenv("DGC_NVIDIA_RAG_URL", "http://127.0.0.1:8081/v1").rstrip("/")
    ing_base = os.getenv("DGC_NVIDIA_INGEST_URL", "http://127.0.0.1:8082/v1").rstrip("/")
    wait_sec = float(os.getenv("ALLOUT_HEAL_WAIT_SEC", "2.0"))
    retries = int(os.getenv("ALLOUT_HEAL_RETRIES", "4"))
    rag_code = "000"
    ing_code = "000"
    for _ in range(max(1, retries)):
        time.sleep(wait_sec)
        rag_code = probe_http_status(f"{rag_base}/health")
        ing_code = probe_http_status(f"{ing_base}/health")
        if rag_code in {"200", "401", "403"} and ing_code in {"200", "401", "403"}:
            break
    ok = rag_code in {"200", "401", "403"} and ing_code in {"200", "401", "403"}
    diag = "ok" if ok else _diagnose_compose_output(f"{out_ing}\n{out_rag}")
    return {
        "ok": ok,
        "rag_code": rag_code,
        "ingest_code": ing_code,
        "diag": diag,
        "compose_ing_rc": rc_ing,
        "compose_rag_rc": rc_rag,
        "ing_tail": out_ing,
        "rag_tail": out_rag,
    }


def heal_flywheel_local() -> dict[str, Any]:
    if not _docker_compose_available():
        return {"ok": False, "detail": "docker_compose_unavailable"}
    fw_repo = _resolve_default_path(
        "DGC_NVIDIA_FLYWHEEL_REPO",
        Path.home() / "DHARMIC_GODEL_CLAW" / "cloned_source" / "data-flywheel",
    )
    fw_compose = _resolve_default_path(
        "DGC_NVIDIA_FLYWHEEL_COMPOSE",
        fw_repo / "deploy" / "docker-compose.yaml",
    )
    if not fw_repo.exists():
        return {"ok": False, "detail": f"missing_repo={fw_repo}"}
    rc_fw, out_fw = _compose_up(
        fw_compose,
        cwd=fw_repo / "deploy",
        project_name=os.getenv("DGC_NVIDIA_FLYWHEEL_PROJECT", "dgc-flywheel"),
        services=["redis", "mongodb", "elasticsearch", "api"],
    )
    base = os.getenv("DGC_DATA_FLYWHEEL_URL", "http://127.0.0.1:8000/api").rstrip("/")
    wait_sec = float(os.getenv("ALLOUT_HEAL_WAIT_SEC", "2.0"))
    retries = int(os.getenv("ALLOUT_HEAL_RETRIES", "4"))
    primary = f"{base}/jobs"
    alt = f"{base[:-4]}/jobs" if base.endswith("/api") else f"{base}/api/jobs"
    p_code = "000"
    a_code = "000"
    for _ in range(max(1, retries)):
        time.sleep(wait_sec)
        p_code = probe_http_status(primary)
        a_code = probe_http_status(alt)
        if p_code in {"200", "401", "403"} or a_code in {"200", "401", "403"}:
            break
    ok = p_code in {"200", "401", "403"} or a_code in {"200", "401", "403"}
    diag = "ok" if ok else _diagnose_compose_output(out_fw)
    return {
        "ok": ok,
        "primary_code": p_code,
        "alt_code": a_code,
        "diag": diag,
        "compose_rc": rc_fw,
        "compose_tail": out_fw,
    }


def command_matrix() -> list[CycleCommand]:
    profile = os.getenv("AUTONOMY_PROFILE", "workspace_auto")
    cmds: list[CycleCommand] = [
        CycleCommand("status", ["python3", "-m", "dharma_swarm.dgc_cli", "status"], ROOT, 120),
        CycleCommand("health-check", ["python3", "-m", "dharma_swarm.dgc_cli", "health-check"], ROOT, 180),
        CycleCommand("dharma-status", ["python3", "-m", "dharma_swarm.dgc_cli", "dharma", "status"], ROOT, 180),
        CycleCommand(
            "mission-status",
            [
                "python3",
                "-m",
                "dharma_swarm.dgc_cli",
                "mission-status",
                "--profile",
                profile,
                "--strict-core",
                "--require-tracked",
                "--json",
            ],
            ROOT,
            180,
        ),
        CycleCommand(
            "tests-provider",
            [
                "python3",
                "-m",
                "pytest",
                "-q",
                "tests/test_providers.py",
                "tests/test_providers_quality_track.py",
                "--tb=short",
            ],
            ROOT,
            900,
        ),
        CycleCommand(
            "tests-integrations",
            [
                "python3",
                "-m",
                "pytest",
                "-q",
                "tests/test_integrations_nvidia_rag.py",
                "tests/test_integrations_data_flywheel.py",
                "--tb=short",
            ],
            ROOT,
            900,
        ),
        CycleCommand(
            "tests-engine",
            [
                "python3",
                "-m",
                "pytest",
                "-q",
                "tests/test_engine_settings.py",
                "tests/test_engine_provider_runner.py",
                "--tb=short",
            ],
            ROOT,
            900,
        ),
    ]

    if _accelerators_enabled() and (os.getenv("DGC_NVIDIA_RAG_URL") or os.getenv("DGC_NVIDIA_INGEST_URL")):
        cmds.extend(
            [
                CycleCommand(
                    "rag-health",
                    ["python3", "-m", "dharma_swarm.dgc_cli", "rag", "health", "--service", "rag"],
                    ROOT,
                    180,
                    optional=True,
                ),
                CycleCommand(
                    "ingest-health",
                    ["python3", "-m", "dharma_swarm.dgc_cli", "rag", "health", "--service", "ingest"],
                    ROOT,
                    180,
                    optional=True,
                ),
            ]
        )

    if _accelerators_enabled() and os.getenv("DGC_DATA_FLYWHEEL_URL"):
        cmds.append(
            CycleCommand(
                "flywheel-jobs",
                ["python3", "-m", "dharma_swarm.dgc_cli", "flywheel", "jobs"],
                ROOT,
                180,
                optional=True,
            )
        )

    return cmds


def collect_candidates() -> list[Path]:
    candidates: list[Path] = []
    roots = [ROOT / "dharma_swarm", ROOT / "tests", ROOT / "docs", Path.home() / "CLAUDE.md"]

    for root in roots:
        if root.is_file():
            candidates.append(root)
            continue
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in {".git", "__pycache__", ".venv", ".mypy_cache"} for part in path.parts):
                continue
            if path.suffix.lower() not in {".py", ".md", ".toml", ".json", ".yaml", ".yml"}:
                continue
            candidates.append(path)
    return candidates


def score_file(path: Path) -> int:
    score = 0
    name = path.name.lower()
    if "test" in name:
        score += 1
    if "provider" in name or "integration" in name:
        score += 2
    if "swarm" in name or "dharma" in name:
        score += 2
    if "todo" in name or "protocol" in name:
        score += 2
    try:
        txt = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return score
    if "TODO" in txt or "FIXME" in txt:
        score += 4
    score += min(3, txt.count("TODO") + txt.count("FIXME"))
    return score


def sample_files(n: int) -> list[Path]:
    candidates = collect_candidates()
    if not candidates:
        return []
    ranked = sorted(candidates, key=score_file, reverse=True)
    top = ranked[: max(n * 4, n)]
    random.shuffle(top)
    chosen = sorted(top[:n], key=lambda p: str(p))
    return chosen


def read_file_signals(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return {"path": str(path), "error": str(e)}

    lines = text.splitlines()
    is_markdown = path.suffix.lower() in {".md", ".markdown"}
    if is_markdown:
        # Markdown often references TODO conceptually; don't treat as actionable debt.
        todo = 0
    else:
        todo_pat = re.compile(r"\b(TODO|FIXME|XXX)\b")
        todo = len([1 for ln in lines if todo_pat.search(ln)])
    funcs = len([1 for ln in lines if ln.strip().startswith("def ")])
    classes = len([1 for ln in lines if ln.strip().startswith("class ")])
    tests = len([1 for ln in lines if ln.strip().startswith("def test_")])
    return {
        "path": str(path),
        "lines": len(lines),
        "todo_markers": todo,
        "defs": funcs,
        "classes": classes,
        "tests": tests,
    }


def normalize_step_text(step: str) -> str:
    text = step.strip().lower()
    text = re.sub(r"`[^`]+`", "<path>", text)
    text = re.sub(r"\s+", " ", text)
    return text


def step_priority(step: str) -> tuple[int, str]:
    """Return (priority, category) for ranking top actions."""
    low = step.strip().lower()
    if any(p in low for p in NOISE_STEP_PATTERNS):
        return (0, "noise")
    if any(p in low for p in INTELLIGENCE_STEP_PATTERNS):
        return (90, "intelligence")
    if any(p in low for p in INFRA_STEP_PATTERNS):
        return (80, "infra")
    if "test" in low or "verify" in low:
        return (70, "quality")
    return (50, "general")


def collect_historical_steps(limit_files: int = 400) -> list[str]:
    """Collect historical TODO steps from allout cycle files + YOLO task list."""
    steps: list[str] = []
    todo_files = sorted(SHARED_DIR.glob("allout_todo_cycle_*.md"))[-limit_files:]
    step_pat = re.compile(r"^\d+\.\s+(.+)$")
    for path in todo_files:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            m = step_pat.match(line.strip())
            if m:
                steps.append(m.group(1).strip())

    yolo_file = ROOT / "docs" / "plans" / "YOLO_4AM_TASKS.md"
    if yolo_file.exists():
        for line in yolo_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            m = step_pat.match(line.strip())
            if m:
                steps.append(m.group(1).strip())
    return steps


def rank_top_steps(steps: list[str], limit: int = 20) -> list[dict[str, Any]]:
    """Rank steps by strategic value + frequency while suppressing noise."""
    by_norm: dict[str, dict[str, Any]] = {}
    include_noise = os.getenv("ALLOUT_INCLUDE_NOISE", "0") == "1"
    for step in steps:
        norm = normalize_step_text(step)
        priority, category = step_priority(step)
        if category == "noise" and not include_noise:
            continue
        if category == "infra" and not _accelerators_enabled():
            continue
        entry = by_norm.setdefault(
            norm,
            {"count": 0, "example": step, "priority": priority, "category": category},
        )
        entry["count"] += 1
        if priority > entry["priority"]:
            entry["priority"] = priority
            entry["category"] = category
            entry["example"] = step

    ranked_list: list[dict[str, Any]] = []
    for norm, value in by_norm.items():
        score = value["count"] * 10 + value["priority"]
        ranked_list.append(
            {
                "normalized": norm,
                "count": value["count"],
                "example": value["example"],
                "priority": value["priority"],
                "category": value["category"],
                "score": score,
            }
        )

    ranked = sorted(
        ranked_list,
        key=lambda x: (-x["score"], -x["count"], x["normalized"]),
    )
    return ranked[:limit]


def write_top20_file(run_dir: Path, cycle: int, ranked: list[dict[str, Any]]) -> Path:
    out = SHARED_DIR / f"allout_top20_cycle_{cycle:03d}.md"
    lines = [
        f"# AllOut Top-20 Backlog (Cycle {cycle})",
        f"- Generated (UTC): {utc_ts()}",
        f"- Generated (JST): {jst_now()}",
        "- Ranking: score = frequency*10 + strategic_priority (noise suppressed by default)",
        "",
        "## Ranked Items",
    ]
    for i, item in enumerate(ranked, start=1):
        lines.append(
            f"{i}. [{item['count']}x] ({item['category']} score={item['score']}) {item['example']}"
        )
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    append_line(run_dir / "allout.log", f"[{utc_ts()}] top20_file={out}")
    return out


def probe_http_status(url: str) -> str:
    try:
        proc = subprocess.run(
            ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", url],
            text=True,
            capture_output=True,
            timeout=20,
        )
        code = (proc.stdout or "").strip() or "000"
        return code
    except Exception:
        return "000"


def map_source_to_test(path_str: str) -> list[str]:
    p = Path(path_str)
    if p.suffix != ".py":
        return []
    stem = p.stem
    candidate = ROOT / "tests" / f"test_{stem}.py"
    if candidate.exists():
        return [str(candidate.relative_to(ROOT))]
    if stem == "providers":
        return ["tests/test_providers.py", "tests/test_providers_quality_track.py"]
    if stem == "swarm":
        return ["tests/test_swarm.py"]
    return []


def execute_single_step(step: str) -> dict[str, Any]:
    text = step.strip()
    low = text.lower()

    def _result(action: str, rc: int, verify: str) -> dict[str, Any]:
        return {"step": text, "action": action, "rc": rc, "verify": verify}

    if _step_uses_accelerators(text) and not _accelerators_enabled():
        return _result("skip_disabled_accelerator", 0, f"accelerator_mode={_accelerator_mode()}")

    if "nvidia rag services" in low:
        rag_base = os.getenv("DGC_NVIDIA_RAG_URL", "http://127.0.0.1:8081/v1").rstrip("/")
        ing_base = os.getenv("DGC_NVIDIA_INGEST_URL", "http://127.0.0.1:8082/v1").rstrip("/")
        rag_code = probe_http_status(f"{rag_base}/health")
        ing_code = probe_http_status(f"{ing_base}/health")
        ok_codes = {"200", "401", "403"}
        rc = 0 if rag_code in ok_codes and ing_code in ok_codes else 2
        if rc != 0 and os.getenv("ALLOUT_SELF_HEAL_INFRA", "1") == "1" and _cooldown_allows_heal("rag"):
            if _is_local_http_base(rag_base) and _is_local_http_base(ing_base):
                heal = heal_nvidia_rag_local()
                rag_code = heal.get("rag_code", rag_code)
                ing_code = heal.get("ingest_code", ing_code)
                rc = 0 if rag_code in ok_codes and ing_code in ok_codes else 2
                return _result(
                    "heal_and_probe_rag",
                    rc,
                    f"rag={rag_code} ingest={ing_code} heal_ok={heal.get('ok')} "
                    f"compose_ing_rc={heal.get('compose_ing_rc')} compose_rag_rc={heal.get('compose_rag_rc')} "
                    f"diag={heal.get('diag', heal.get('detail', 'unknown'))}",
                )
        return _result("probe_rag_health", rc, f"rag={rag_code} ingest={ing_code}")

    if "data flywheel endpoint mapping" in low:
        base = os.getenv("DGC_DATA_FLYWHEEL_URL", "http://127.0.0.1:8000/api").rstrip("/")
        primary = f"{base}/jobs"
        alt = f"{base[:-4]}/jobs" if base.endswith("/api") else f"{base}/api/jobs"
        p_code = probe_http_status(primary)
        a_code = probe_http_status(alt)
        ok_codes = {"200", "401", "403"}
        rc = 0 if (p_code in ok_codes or a_code in ok_codes) else 2
        if rc != 0 and os.getenv("ALLOUT_SELF_HEAL_INFRA", "1") == "1" and _cooldown_allows_heal("flywheel"):
            if _is_local_http_base(base):
                heal = heal_flywheel_local()
                p_code = heal.get("primary_code", p_code)
                a_code = heal.get("alt_code", a_code)
                rc = 0 if (p_code in ok_codes or a_code in ok_codes) else 2
                return _result(
                    "heal_and_probe_flywheel",
                    rc,
                    f"primary={primary}:{p_code} alt={alt}:{a_code} "
                    f"heal_ok={heal.get('ok')} compose_rc={heal.get('compose_rc')} "
                    f"diag={heal.get('diag', heal.get('detail', 'unknown'))}",
                )
        verify = f"primary={primary}:{p_code} alt={alt}:{a_code}"
        return _result("probe_flywheel_endpoints", rc, verify)

    if "verify `dgc rag health --service rag`" in low:
        proc = run_cmd(
            ["python3", "-m", "dharma_swarm.dgc_cli", "rag", "health", "--service", "rag"],
            cwd=ROOT,
            timeout=180,
        )
        if proc.returncode != 0 and os.getenv("ALLOUT_SELF_HEAL_INFRA", "1") == "1" and _cooldown_allows_heal("rag-cli"):
            heal = heal_nvidia_rag_local()
            proc = run_cmd(
                ["python3", "-m", "dharma_swarm.dgc_cli", "rag", "health", "--service", "rag"],
                cwd=ROOT,
                timeout=180,
            )
            return _result(
                "heal_then_verify_rag_health_cmd",
                proc.returncode,
                f"heal_ok={heal.get('ok')} diag={heal.get('diag', heal.get('detail', 'unknown'))} "
                f"output={(proc.stdout or proc.stderr)[-220:]}",
            )
        return _result("verify_rag_health_cmd", proc.returncode, (proc.stdout or proc.stderr)[-300:])

    if "run cli command-dispatch tests" in low:
        proc = run_cmd(["python3", "-m", "pytest", "-q", "tests/test_dgc_cli.py", "--tb=short"], cwd=ROOT, timeout=900)
        return _result("pytest_cli_dispatch", proc.returncode, (proc.stdout or "")[-300:])

    if "run engine safety tests" in low:
        proc = run_cmd(["python3", "-m", "pytest", "-q", "tests/test_engine_settings.py", "tests/test_engine_provider_runner.py", "--tb=short"], cwd=ROOT, timeout=900)
        return _result("pytest_engine_safety", proc.returncode, (proc.stdout or "")[-300:])

    if "run integration tests" in low:
        proc = run_cmd(
            [
                "python3",
                "-m",
                "pytest",
                "-q",
                "tests/test_integrations_nvidia_rag.py",
                "tests/test_integrations_data_flywheel.py",
                "--tb=short",
            ],
            cwd=ROOT,
            timeout=900,
        )
        return _result("pytest_integrations", proc.returncode, (proc.stdout or "")[-300:])

    if "run provider core tests" in low:
        proc = run_cmd(["python3", "-m", "pytest", "-q", "tests/test_providers.py", "--tb=short"], cwd=ROOT, timeout=900)
        return _result("pytest_provider_core", proc.returncode, (proc.stdout or "")[-300:])

    if "run provider quality tests" in low:
        proc = run_cmd(["python3", "-m", "pytest", "-q", "tests/test_providers_quality_track.py", "--tb=short"], cwd=ROOT, timeout=900)
        return _result("pytest_provider_quality", proc.returncode, (proc.stdout or "")[-300:])

    if "run pulse + living-layer tests" in low:
        proc = run_cmd(["python3", "-m", "pytest", "-q", "tests/test_pulse.py", "tests/test_shakti.py", "tests/test_stigmergy.py", "tests/test_subconscious.py", "--tb=short"], cwd=ROOT, timeout=1200)
        return _result("pytest_living_layers", proc.returncode, (proc.stdout or "")[-300:])

    if "run swarm smoke tests" in low:
        proc = run_cmd(["python3", "-m", "pytest", "-q", "tests/test_swarm.py", "--tb=short"], cwd=ROOT, timeout=1200)
        return _result("pytest_swarm_smoke", proc.returncode, (proc.stdout or "")[-300:])

    if "verify `dgc health-check`" in low:
        proc = run_cmd(["python3", "-m", "dharma_swarm.dgc_cli", "health-check"], cwd=ROOT, timeout=240)
        return _result("verify_health_check_cmd", proc.returncode, (proc.stdout or proc.stderr)[-300:])

    if "verify `dgc status` baseline" in low:
        proc = run_cmd(["python3", "-m", "dharma_swarm.dgc_cli", "status"], cwd=ROOT, timeout=240)
        return _result("verify_status_cmd", proc.returncode, (proc.stdout or proc.stderr)[-300:])

    if "verify `dgc flywheel jobs` service reachability" in low:
        proc = run_cmd(["python3", "-m", "dharma_swarm.dgc_cli", "flywheel", "jobs"], cwd=ROOT, timeout=240)
        if proc.returncode != 0 and os.getenv("ALLOUT_SELF_HEAL_INFRA", "1") == "1" and _cooldown_allows_heal("flywheel-cli"):
            heal = heal_flywheel_local()
            proc = run_cmd(["python3", "-m", "dharma_swarm.dgc_cli", "flywheel", "jobs"], cwd=ROOT, timeout=240)
            return _result(
                "heal_then_verify_flywheel_jobs_cmd",
                proc.returncode,
                f"heal_ok={heal.get('ok')} diag={heal.get('diag', heal.get('detail', 'unknown'))} "
                f"output={(proc.stdout or proc.stderr)[-220:]}",
            )
        return _result("verify_flywheel_jobs_cmd", proc.returncode, (proc.stdout or proc.stderr)[-300:])

    if "verify `dgc dharma status` signed kernel and gate counts" in low:
        proc = run_cmd(["python3", "-m", "dharma_swarm.dgc_cli", "dharma", "status"], cwd=ROOT, timeout=240)
        return _result("verify_dharma_status_cmd", proc.returncode, (proc.stdout or proc.stderr)[-300:])

    if "verify canary/rollback status unchanged unless intentional" in low:
        proc = run_cmd(
            ["python3", "-m", "pytest", "-q", "tests/test_evolution.py", "--tb=short"],
            cwd=ROOT,
            timeout=1200,
        )
        return _result("verify_canary_rollback_tests", proc.returncode, (proc.stdout or "")[-300:])

    if "check rag retrieval quality on one canonical query" in low:
        proc = run_cmd(
            ["python3", "-m", "dharma_swarm.dgc_cli", "rag", "search", "kernel", "optimization", "--top-k", "3"],
            cwd=ROOT,
            timeout=240,
        )
        if proc.returncode != 0 and os.getenv("ALLOUT_SELF_HEAL_INFRA", "1") == "1" and _cooldown_allows_heal("rag-search"):
            heal = heal_nvidia_rag_local()
            proc = run_cmd(
                ["python3", "-m", "dharma_swarm.dgc_cli", "rag", "search", "kernel", "optimization", "--top-k", "3"],
                cwd=ROOT,
                timeout=240,
            )
            return _result(
                "heal_then_rag_retrieval_probe",
                proc.returncode,
                f"heal_ok={heal.get('ok')} diag={heal.get('diag', heal.get('detail', 'unknown'))} "
                f"output={(proc.stdout or proc.stderr)[-220:]}",
            )
        return _result("rag_retrieval_probe", proc.returncode, (proc.stdout or proc.stderr)[-300:])

    if "check flywheel job lifecycle with one dry-run payload" in low:
        # Dry-run probe only: do not create mutable jobs when endpoint is unavailable.
        proc = run_cmd(["python3", "-m", "dharma_swarm.dgc_cli", "flywheel", "jobs"], cwd=ROOT, timeout=240)
        if proc.returncode != 0 and os.getenv("ALLOUT_SELF_HEAL_INFRA", "1") == "1" and _cooldown_allows_heal("flywheel-jobs"):
            heal = heal_flywheel_local()
            proc = run_cmd(["python3", "-m", "dharma_swarm.dgc_cli", "flywheel", "jobs"], cwd=ROOT, timeout=240)
            return _result(
                "heal_then_flywheel_lifecycle_probe",
                proc.returncode,
                f"heal_ok={heal.get('ok')} diag={heal.get('diag', heal.get('detail', 'unknown'))} "
                f"output={(proc.stdout or proc.stderr)[-220:]}",
            )
        return _result("flywheel_lifecycle_probe", proc.returncode, (proc.stdout or proc.stderr)[-300:])

    if "export current open tasks and status counts" in low:
        db = STATE / "db" / "tasks.db"
        if not db.exists():
            return _result("export_task_counts", 2, f"missing_db={db}")
        import sqlite3

        conn = sqlite3.connect(str(db))
        try:
            rows = conn.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status").fetchall()
        finally:
            conn.close()
        out = SHARED_DIR / "task_status_counts.json"
        payload = {str(k): int(v) for k, v in rows}
        out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return _result("export_task_counts", 0, f"wrote={out}")

    if "refill task board if pending tasks fall below threshold" in low:
        db = STATE / "db" / "tasks.db"
        if not db.exists():
            return _result("refill_task_board", 2, f"missing_db={db}")
        import sqlite3

        conn = sqlite3.connect(str(db))
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE status IN ('pending','assigned','running')"
            ).fetchone()
            active = int(row[0] if row else 0)
        finally:
            conn.close()
        if active >= 6:
            return _result("refill_task_board", 0, f"active_tasks={active} (no refill needed)")
        proc = run_cmd(
            [
                "python3",
                "-m",
                "dharma_swarm.cli",
                "task",
                "create",
                "AllOut auto-refill task",
                "--description",
                "Automatically injected by plan-do-verify loop to maintain queue floor.",
                "--priority",
                "high",
                "--state-dir",
                str(STATE),
            ],
            cwd=ROOT,
            timeout=120,
        )
        return _result("refill_task_board", proc.returncode, f"active_before={active}")

    if "generate nightly findings note in `~/.dharma/shared/`" in low:
        note = SHARED_DIR / "nightly_findings.md"
        latest = sorted((STATE / "logs" / "allout").glob("*/allout.log"))
        summary = "No allout logs found."
        if latest:
            tail = latest[-1].read_text(encoding="utf-8", errors="ignore")[-2000:]
            summary = tail
        note.write_text(f"# Nightly Findings\n\nGenerated: {utc_ts()}\n\n```\n{summary}\n```\n", encoding="utf-8")
        return _result("generate_nightly_findings", 0, f"wrote={note}")

    if "append nightly summary to `~/.dharma/logs/caffeine/`" in low:
        out = STATE / "logs" / "caffeine" / "nightly_summary.md"
        append_line(out, f"- {utc_ts()} allout cycle summary appended")
        return _result("append_caffeine_summary", 0, f"wrote={out}")

    if "capture performance deltas from previous loop" in low:
        logs = sorted((STATE / "logs" / "allout").glob("*/snapshots.jsonl"))
        if len(logs) < 2:
            return _result("capture_perf_delta", 2, "not_enough_runs_for_delta")
        def _last_elapsed(path: Path) -> float:
            lines = [ln for ln in path.read_text(encoding="utf-8", errors="ignore").splitlines() if ln.strip()]
            if not lines:
                return 0.0
            obj = json.loads(lines[-1])
            return float(obj.get("cycle_elapsed_sec", 0.0))
        cur = _last_elapsed(logs[-1])
        prev = _last_elapsed(logs[-2])
        delta = cur - prev
        out = SHARED_DIR / "performance_delta.md"
        out.write_text(
            f"# Performance Delta\n\nGenerated: {utc_ts()}\n\n- previous: {prev:.2f}s\n- current: {cur:.2f}s\n- delta: {delta:+.2f}s\n",
            encoding="utf-8",
        )
        return _result("capture_perf_delta", 0, f"delta={delta:+.2f}s")

    if "emit final “handoff at 04:00 jst” report" in low or "emit final \"handoff at 04:00 jst\" report" in low:
        out = SHARED_DIR / "handoff_04jst_report.md"
        out.write_text(
            f"# Handoff 04:00 JST Report\n\nGenerated: {utc_ts()}\n\n- Loop active and reporting.\n- Verify status via scripts/status_allout_tmux.sh.\n",
            encoding="utf-8",
        )
        return _result("emit_handoff_report", 0, f"wrote={out}")

    if "full `pytest tests/" in low or "full pytest" in low:
        proc = run_cmd(["python3", "-m", "pytest", "tests/", "-q", "--tb=short"], cwd=ROOT, timeout=1800)
        return _result("full_pytest", proc.returncode, (proc.stdout or "")[-300:])

    if "focused tests for uncovered module" in low or "resolve highest-value todo/fixme in" in low:
        path_match = re.search(r"`([^`]+)`", text)
        if path_match:
            tests = map_source_to_test(path_match.group(1))
            if tests:
                proc = run_cmd(["python3", "-m", "pytest", "-q", *tests, "--tb=short"], cwd=ROOT, timeout=1200)
                return _result("targeted_pytest", proc.returncode, f"tests={tests}")
            return _result("targeted_review_only", 0, "no mapped tests for target file")
        return _result("targeted_review_only", 0, "no target path found")

    if "review new logs for repeated warnings" in low:
        latest = sorted((STATE / "logs" / "allout").glob("*/allout.log"))
        if not latest:
            return _result("scan_logs", 2, "no allout logs found")
        text_log = latest[-1].read_text(encoding="utf-8", errors="ignore")
        warns = len(re.findall(r"\bWARN\b", text_log))
        fails = len(re.findall(r"\bFAIL\b", text_log))
        return _result("scan_logs", 0, f"warn={warns} fail={fails}")

    return _result("noop_unmapped_step", 0, "no action mapping; skipped safely")


def execute_ranked_steps(ranked: list[dict[str, Any]], max_actions: int) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    allow_noops = os.getenv("ALLOUT_KEEP_NOOPS", "0") == "1"

    def _push_if_meaningful(result: dict[str, Any]) -> None:
        if result.get("action") == "noop_unmapped_step" and not allow_noops:
            return
        actions.append(result)

    for item in ranked:
        if len(actions) >= max_actions:
            break
        if _step_uses_accelerators(str(item.get("example", ""))) and not _accelerators_enabled():
            continue
        _push_if_meaningful(execute_single_step(item["example"]))

    fallback_steps = [
        "Run provider core tests (`tests/test_providers.py`).",
        "Run engine safety tests (`tests/test_engine_settings.py` + `tests/test_engine_provider_runner.py`).",
        "Run integration tests (`tests/test_integrations_nvidia_rag.py` + `tests/test_integrations_data_flywheel.py`).",
        "Verify `dgc status` baseline.",
        "Verify `dgc health-check`.",
    ]
    for step in fallback_steps:
        if len(actions) >= max_actions:
            break
        _push_if_meaningful(execute_single_step(step))

    return actions


def build_todo(
    cycle: int,
    command_results: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    min_steps: int,
    max_steps: int,
) -> list[str]:
    steps: list[str] = []
    failed = [r for r in command_results if r["rc"] != 0]
    labels = {r["label"] for r in failed}

    if _accelerators_enabled() and ("rag-health" in labels or "ingest-health" in labels):
        steps.append("Bring up NVIDIA RAG services and verify `/v1/health` on ports 8081/8082.")
    if _accelerators_enabled() and "flywheel-jobs" in labels:
        steps.append("Fix Data Flywheel endpoint mapping and confirm `GET /api/jobs` returns 200.")
    if {"tests-provider", "tests-integrations", "tests-engine"} & labels:
        steps.append("Triage failing test subset and patch root cause before next cycle.")

    todo_files = [s for s in signals if s.get("todo_markers", 0) > 0]
    if todo_files:
        top = sorted(todo_files, key=lambda s: s.get("todo_markers", 0), reverse=True)[:2]
        for item in top:
            steps.append(f"Resolve highest-value TODO/FIXME in `{item['path']}` with tests.")

    thin_tests = [s for s in signals if s.get("defs", 0) >= 8 and s.get("tests", 0) == 0 and str(s.get("path", "")).endswith(".py")]
    if thin_tests:
        steps.append(f"Add focused tests for uncovered module `{thin_tests[0]['path']}`.")

    if len(steps) < min_steps:
        steps.append("Run full `pytest tests/ -q --tb=short` and record regressions to morning report.")
    if len(steps) < min_steps:
        steps.append("Review new logs for repeated warnings and convert one into an actionable fix task.")

    return steps[: max_steps]


def extract_test_counts(results: list[dict[str, Any]]) -> dict[str, int]:
    """Extract pass/fail counts from pytest output in command results."""
    passed = 0
    failed = 0
    for r in results:
        if not r["label"].startswith("tests-"):
            continue
        stdout = r.get("stdout_tail", "")
        # pytest summary line: "N passed, M failed in X.XXs"
        m = re.search(r"(\d+)\s+passed", stdout)
        if m:
            passed += int(m.group(1))
        m = re.search(r"(\d+)\s+failed", stdout)
        if m:
            failed += int(m.group(1))
    return {"passed": passed, "failed": failed}


def format_signals_for_prompt(signals: list[dict[str, Any]]) -> str:
    """Format file signals into a compact string for the prompt engineer."""
    lines = []
    for sig in signals:
        if "error" in sig:
            lines.append(f"  {sig['path']}: ERROR {sig['error']}")
        else:
            markers = []
            if sig.get("todo_markers", 0) > 0:
                markers.append(f"TODO={sig['todo_markers']}")
            if sig.get("tests", 0) > 0:
                markers.append(f"tests={sig['tests']}")
            if sig.get("defs", 0) > 0:
                markers.append(f"defs={sig['defs']}")
            extra = f" ({', '.join(markers)})" if markers else ""
            lines.append(f"  {Path(sig['path']).name}: {sig.get('lines', 0)} lines{extra}")
    return "\n".join(lines) if lines else "No files reviewed."


def run_prompt_evolution(
    cycle: int,
    results: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    todo_steps: list[str],
    log_file: Path,
) -> str | None:
    """Run the 3-layer prompt evolution if this cycle is due.

    Returns the evolved prompt text, or None if not this cycle.
    """
    evolve_every = int(os.getenv("ALLOUT_EVOLVE_EVERY", "3"))
    if not should_evolve_prompt(cycle, every_n=evolve_every):
        return None

    append_line(log_file, f"[{utc_ts()}] EVOLVE cycle={cycle} triggering prompt evolution")

    test_counts = extract_test_counts(results)
    file_signals_text = format_signals_for_prompt(signals)
    prev_todo_text = "\n".join(f"  {i + 1}. {s}" for i, s in enumerate(todo_steps))

    # Try LLM-powered evolution, fall back to local
    evolved = None
    if os.getenv("OPENROUTER_API_KEY") and os.getenv("ALLOUT_LLM_EVOLVE", "0") == "1":
        try:
            from dharma_swarm.master_prompt_engineer import generate_evolved_prompt

            evolved = asyncio.run(generate_evolved_prompt(
                test_summary=f"Passed: {test_counts['passed']}, Failed: {test_counts['failed']}",
                file_signals=file_signals_text,
                prev_todo=prev_todo_text,
                cycle_number=cycle,
            ))
            append_line(log_file, f"[{utc_ts()}] EVOLVE LLM prompt generated ({len(evolved)} chars)")
        except Exception as exc:
            append_line(log_file, f"[{utc_ts()}] EVOLVE LLM failed: {exc}, falling back to local")

    if evolved is None:
        evolved = generate_local_prompt(
            test_summary=f"Passed: {test_counts['passed']}, Failed: {test_counts['failed']}",
            file_signals=file_signals_text,
            prev_todo=prev_todo_text,
            cycle_number=cycle,
        )
        append_line(log_file, f"[{utc_ts()}] EVOLVE local prompt generated ({len(evolved)} chars)")

    # Write evolved prompt
    evolved_file = SHARED_DIR / f"evolved_prompt_cycle_{cycle:03d}.md"
    evolved_file.write_text(evolved, encoding="utf-8")

    # Also write as LATEST for other systems to pick up
    latest = SHARED_DIR / "EVOLVED_PROMPT.md"
    latest.write_text(
        f"# Evolved Prompt -- Cycle {cycle}\n"
        f"Generated: {utc_ts()}\n\n{evolved}\n",
        encoding="utf-8",
    )

    return evolved


def maybe_enqueue_tasks(todo_steps: list[str], cycle: int) -> list[dict[str, Any]]:
    if os.getenv("ALLOUT_ENQUEUE_TASKS", "0") != "1":
        return []
    out: list[dict[str, Any]] = []
    for idx, step in enumerate(todo_steps, start=1):
        title = f"AllOut cycle {cycle} step {idx}"
        proc = run_cmd(
            [
                "python3",
                "-m",
                "dharma_swarm.cli",
                "task",
                "create",
                title,
                "--description",
                step,
                "--priority",
                "high",
                "--state-dir",
                str(STATE),
            ],
            cwd=ROOT,
            timeout=120,
        )
        out.append({"title": title, "rc": proc.returncode})
    return out


def build_compounding_event(
    *,
    run_id: str,
    cycle: int,
    jst: str,
    results: list[dict[str, Any]],
    todo_steps: list[str],
    ranked_top20: list[dict[str, Any]],
    executed_actions: list[dict[str, Any]],
    files_reviewed: list[str],
    cycle_elapsed_sec: float,
) -> dict[str, Any]:
    checks_total = len(results)
    checks_ok = sum(1 for r in results if int(r.get("rc", 1)) == 0)
    mission_rc = next(
        (int(r.get("rc", 1)) for r in results if str(r.get("label")) == "mission-status"),
        1,
    )
    action_total = len(executed_actions)
    action_ok = sum(1 for a in executed_actions if int(a.get("rc", 1)) == 0)
    action_noop = sum(1 for a in executed_actions if str(a.get("action")) == "noop_unmapped_step")

    return {
        "ts_utc": utc_ts(),
        "run_id": run_id,
        "cycle": cycle,
        "jst": jst,
        "checks_total": checks_total,
        "checks_ok": checks_ok,
        "checks_fail": checks_total - checks_ok,
        "mission_status_rc": mission_rc,
        "todo_count": len(todo_steps),
        "top20_count": len(ranked_top20),
        "actions_total": action_total,
        "actions_ok": action_ok,
        "actions_fail": action_total - action_ok,
        "actions_noop": action_noop,
        "files_reviewed_count": len(files_reviewed),
        "files_reviewed": files_reviewed[:20],
        "cycle_elapsed_sec": round(float(cycle_elapsed_sec), 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all-out autonomous supervision.")
    parser.add_argument("--hours", type=float, default=6.0)
    parser.add_argument("--poll-seconds", type=int, default=300)
    parser.add_argument("--files-per-cycle", type=int, default=10)
    parser.add_argument("--todo-min", type=int, default=3)
    parser.add_argument("--todo-max", type=int, default=5)
    parser.add_argument("--max-cycles", type=int, default=0, help="Optional hard cap on cycle count (0 = unlimited).")
    args = parser.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    SHARED_DIR.mkdir(parents=True, exist_ok=True)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = LOG_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    log_file = run_dir / "allout.log"
    snap_file = run_dir / "snapshots.jsonl"
    morning_file = SHARED_DIR / f"allout_morning_{run_id}.md"

    append_line(log_file, f"[{utc_ts()}] allout start run_id={run_id} jst={jst_now()}")
    append_line(
        log_file,
        f"[{utc_ts()}] config hours={args.hours} poll={args.poll_seconds}s files={args.files_per_cycle}",
    )

    start = time.time()
    max_seconds = None if args.hours <= 0 else max(60, int(args.hours * 3600))
    cycle = 0
    if max_seconds is None:
        append_line(log_file, f"[{utc_ts()}] continuous_mode=1 (hours<=0)")

    while ((max_seconds is None) or ((time.time() - start) < max_seconds)) and (
        args.max_cycles <= 0 or cycle < args.max_cycles
    ):
        cycle += 1
        cycle_start = time.time()
        append_line(log_file, f"[{utc_ts()}] cycle={cycle} start jst={jst_now()}")

        results: list[dict[str, Any]] = []
        for item in command_matrix():
            begun = time.time()
            proc = run_cmd(item.cmd, cwd=item.cwd, timeout=item.timeout)
            elapsed = round(time.time() - begun, 2)
            results.append(
                {
                    "label": item.label,
                    "rc": proc.returncode,
                    "elapsed_sec": elapsed,
                    "optional": item.optional,
                    "stdout_tail": (proc.stdout or "")[-1200:],
                    "stderr_tail": (proc.stderr or "")[-1200:],
                }
            )
            level = "OK" if proc.returncode == 0 else ("WARN" if item.optional else "FAIL")
            append_line(log_file, f"[{utc_ts()}] {level} {item.label} rc={proc.returncode} t={elapsed}s")

        files = sample_files(args.files_per_cycle)
        signals = [read_file_signals(p) for p in files]
        todo_steps = build_todo(cycle, results, signals, args.todo_min, args.todo_max)
        enqueued = maybe_enqueue_tasks(todo_steps, cycle)

        historical_steps = collect_historical_steps()
        ranked_top20 = rank_top_steps(historical_steps, limit=20)
        top20_file = write_top20_file(run_dir, cycle, ranked_top20)

        executed_actions: list[dict[str, Any]] = []
        if os.getenv("ALLOUT_EXECUTE", "1") == "1":
            max_actions = int(os.getenv("ALLOUT_ACTIONS_PER_CYCLE", "3"))
            executed_actions = execute_ranked_steps(ranked_top20, max_actions=max(1, max_actions))
            for act in executed_actions:
                level = "OK" if act["rc"] == 0 else "WARN"
                append_line(
                    log_file,
                    f"[{utc_ts()}] {level} action={act['action']} rc={act['rc']} verify={act['verify']}",
                )

        todo_md = SHARED_DIR / f"allout_todo_cycle_{cycle:03d}.md"
        todo_lines = [
            f"# AllOut Cycle {cycle} TODO",
            f"- Generated (UTC): {utc_ts()}",
            f"- Generated (JST): {jst_now()}",
            "",
            "## Steps",
        ]
        for idx, step in enumerate(todo_steps, start=1):
            todo_lines.append(f"{idx}. {step}")
        todo_lines.extend(["", "## Files Reviewed"])
        for sig in signals:
            if "error" in sig:
                todo_lines.append(f"- `{sig['path']}` error={sig['error']}")
            else:
                todo_lines.append(
                    f"- `{sig['path']}` lines={sig['lines']} todo={sig['todo_markers']} defs={sig['defs']} tests={sig['tests']}"
                )
        todo_md.write_text("\n".join(todo_lines) + "\n", encoding="utf-8")

        snapshot = {
            "ts_utc": utc_ts(),
            "run_id": run_id,
            "cycle": cycle,
            "jst": jst_now(),
            "results": [{"label": r["label"], "rc": r["rc"], "elapsed_sec": r["elapsed_sec"]} for r in results],
            "files_reviewed": [s.get("path") for s in signals],
            "todo_file": str(todo_md),
            "todo_steps": todo_steps,
            "top20_file": str(top20_file),
            "top20_count": len(ranked_top20),
            "tasks_enqueued": enqueued,
            "actions_executed": executed_actions,
            "cycle_elapsed_sec": round(time.time() - cycle_start, 2),
        }
        compounding_event = build_compounding_event(
            run_id=run_id,
            cycle=cycle,
            jst=snapshot["jst"],
            results=results,
            todo_steps=todo_steps,
            ranked_top20=ranked_top20,
            executed_actions=executed_actions,
            files_reviewed=[str(p) for p in snapshot["files_reviewed"]],
            cycle_elapsed_sec=float(snapshot["cycle_elapsed_sec"]),
        )
        snapshot["compounding_event"] = compounding_event
        append_line(snap_file, json.dumps(snapshot, ensure_ascii=True))
        append_jsonl(COMPOUNDING_LEDGER_FILE, compounding_event)
        write_json(HEARTBEAT_FILE, snapshot)

        # --- Master Prompt Engineer integration ---
        # Record cycle for history tracking (feeds META + QUALITY layers)
        test_counts = extract_test_counts(results)
        quality_verdict = assess_quality()
        record_cycle(
            cycle_number=cycle,
            todo_steps=todo_steps,
            test_results=test_counts,
            files_reviewed=[s.get("path", "") for s in signals],
            quality_verdict=quality_verdict,
        )

        # Run prompt evolution every Nth cycle
        evolved = run_prompt_evolution(cycle, results, signals, todo_steps, log_file)
        if evolved:
            snapshot["evolved_prompt_length"] = len(evolved)
            snapshot["quality_verdict"] = quality_verdict
            append_line(log_file, f"[{utc_ts()}] EVOLVE quality={quality_verdict}")

        append_line(log_file, f"[{utc_ts()}] cycle={cycle} done elapsed={snapshot['cycle_elapsed_sec']}s verdict={quality_verdict}")
        sleep_for = max(5, args.poll_seconds)
        time.sleep(sleep_for)

    append_line(log_file, f"[{utc_ts()}] allout complete run_id={run_id} jst={jst_now()}")
    write_json(
        HEARTBEAT_FILE,
        {
            "ts_utc": utc_ts(),
            "run_id": run_id,
            "status": "complete",
            "jst": jst_now(),
            "log": str(log_file),
            "snapshots": str(snap_file),
        },
    )

    summary = [
        "# AllOut Morning Summary",
        f"- Run ID: `{run_id}`",
        f"- Completed (UTC): `{utc_ts()}`",
        f"- Log: `{log_file}`",
        f"- Snapshots: `{snap_file}`",
        f"- Compounding ledger: `{COMPOUNDING_LEDGER_FILE}`",
        "",
        "Latest TODO artifacts:",
    ]
    for todo in sorted(SHARED_DIR.glob("allout_todo_cycle_*.md"))[-10:]:
        summary.append(f"- `{todo}`")
    morning_file.write_text("\n".join(summary) + "\n", encoding="utf-8")

    if os.getenv("ALLOUT_WRITE_24H_REPORT", "1") == "1":
        report_cmd = [
            "python3",
            "scripts/compounding_ledger.py",
            "--hours",
            "24",
            "--write",
        ]
        proc = run_cmd(report_cmd, cwd=ROOT, timeout=120)
        if proc.returncode == 0:
            append_line(log_file, f"[{utc_ts()}] compounding_report ok")
        else:
            append_line(
                log_file,
                f"[{utc_ts()}] compounding_report warn rc={proc.returncode} tail={(proc.stderr or proc.stdout)[-300:]}",
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
