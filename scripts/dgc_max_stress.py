#!/usr/bin/env python3
"""DGC max-capacity stress harness.

Goals:
1. Stress CLI command surface under parallel load.
2. Spawn agents and execute concurrent tasks through orchestrator.
3. Stress Telos + Darwin evolution pipeline with mixed safe/harmful proposals.
4. Optionally invoke Claude/Codex CLI "research agents" for adversarial test design.
5. Write machine + human-readable reports to ~/.dharma/shared.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path.home() / "dharma_swarm"))

from dharma_swarm.models import (
    AgentRole,
    LLMRequest,
    LLMResponse,
    ProviderType,
    TaskPriority,
    TaskStatus,
)
from dharma_swarm.providers import LLMProvider, ModelRouter
from dharma_swarm.swarm import SwarmManager


HOME = Path.home()
ROOT = HOME / "dharma_swarm"
SHARED = HOME / ".dharma" / "shared"


def utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def which(name: str) -> bool:
    return shutil.which(name) is not None


def run_sync(cmd: list[str], *, cwd: Path = ROOT, timeout: int = 120) -> dict[str, Any]:
    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        return {
            "rc": proc.returncode,
            "elapsed_sec": round(time.time() - start, 2),
            "stdout_tail": (proc.stdout or "")[-1000:],
            "stderr_tail": (proc.stderr or "")[-1000:],
            "cmd": cmd,
        }
    except subprocess.TimeoutExpired:
        return {
            "rc": 124,
            "elapsed_sec": round(time.time() - start, 2),
            "stdout_tail": "",
            "stderr_tail": "timeout",
            "cmd": cmd,
        }


async def run_async_cmd(cmd: list[str], *, cwd: Path = ROOT, timeout: int = 120) -> dict[str, Any]:
    start = time.time()
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return {
            "rc": proc.returncode,
            "elapsed_sec": round(time.time() - start, 2),
            "stdout_tail": stdout.decode(errors="ignore")[-1000:],
            "stderr_tail": stderr.decode(errors="ignore")[-1000:],
            "cmd": cmd,
        }
    except asyncio.TimeoutError:
        proc.terminate()
        return {
            "rc": 124,
            "elapsed_sec": round(time.time() - start, 2),
            "stdout_tail": "",
            "stderr_tail": "timeout",
            "cmd": cmd,
        }


@dataclass
class StressConfig:
    profile: str
    state_dir: Path
    provider_mode: str
    agents: int
    tasks: int
    evolutions: int
    evolution_concurrency: int
    cli_rounds: int
    cli_concurrency: int
    orchestration_timeout_sec: int
    external_research: bool
    external_timeout_sec: int


class MockStressProvider(LLMProvider):
    """Deterministic provider for high-throughput local stress."""

    async def complete(self, request: LLMRequest) -> LLMResponse:
        await asyncio.sleep(random.uniform(0.02, 0.12))
        user_bits = [m.get("content", "") for m in request.messages if m.get("role") == "user"]
        text = (user_bits[0] if user_bits else "no-user-content").strip()
        content = (
            "[mock-stress]\n"
            "Status: completed under synthetic provider load.\n"
            f"TaskHead: {text[:220]}"
        )
        return LLMResponse(content=content, model="mock-stress")

    async def stream(self, request: LLMRequest):
        resp = await self.complete(request)
        yield resp.content


def build_mock_router() -> ModelRouter:
    provider = MockStressProvider()
    providers = {ptype: provider for ptype in ProviderType}
    return ModelRouter(providers)


def choose_provider_cycle(mode: str) -> tuple[list[ProviderType], str]:
    """Return provider cycle + resolved mode string."""
    mode = mode.lower().strip()
    if mode == "mock":
        return [ProviderType.CLAUDE_CODE], "mock"
    if mode == "claude":
        return [ProviderType.CLAUDE_CODE], "claude"
    if mode == "codex":
        return [ProviderType.CODEX], "codex"
    if mode == "openrouter":
        return [ProviderType.OPENROUTER_FREE], "openrouter"
    if mode != "auto":
        return [ProviderType.CLAUDE_CODE], mode

    cycle: list[ProviderType] = []
    if which("claude"):
        cycle.append(ProviderType.CLAUDE_CODE)
    if which("codex"):
        cycle.append(ProviderType.CODEX)
    if os.getenv("OPENROUTER_API_KEY"):
        cycle.append(ProviderType.OPENROUTER_FREE)
    if os.getenv("OPENAI_API_KEY"):
        cycle.append(ProviderType.OPENAI)

    if not cycle:
        return [ProviderType.CLAUDE_CODE], "mock"
    return cycle, "auto"


def pick_role(i: int) -> AgentRole:
    roles = [
        AgentRole.CARTOGRAPHER,
        AgentRole.ARCHITECT,
        AgentRole.SURGEON,
        AgentRole.VALIDATOR,
        AgentRole.RESEARCHER,
        AgentRole.CODER,
        AgentRole.TESTER,
        AgentRole.ARCHEOLOGIST,
        AgentRole.GENERAL,
    ]
    return roles[i % len(roles)]


def pick_thread(i: int) -> str:
    threads = ["mechanistic", "phenomenological", "architectural", "alignment", "scaling"]
    return threads[i % len(threads)]


async def wait_for_tasks(
    swarm: SwarmManager,
    task_ids: set[str],
    timeout_sec: int,
    *,
    tick_sleep: float = 0.15,
) -> dict[str, Any]:
    start = time.time()
    terminal = {
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    }
    while (time.time() - start) < timeout_sec:
        await swarm.dispatch_next()
        statuses: dict[str, str] = {}
        done = 0
        for tid in task_ids:
            task = await swarm.get_task(tid)
            if task is None:
                statuses[tid] = "missing"
                continue
            statuses[tid] = task.status.value
            if task.status in terminal:
                done += 1
        if done >= len(task_ids):
            return {
                "complete": True,
                "elapsed_sec": round(time.time() - start, 2),
                "statuses": statuses,
            }
        await asyncio.sleep(tick_sleep)
    final: dict[str, str] = {}
    for tid in task_ids:
        task = await swarm.get_task(tid)
        final[tid] = task.status.value if task else "missing"
    return {
        "complete": False,
        "elapsed_sec": round(time.time() - start, 2),
        "statuses": final,
    }


async def clear_seed_tasks(swarm: SwarmManager) -> int:
    """Cancel startup seed tasks so stress run measures are not skewed."""
    cancelled = 0
    pending_like = {TaskStatus.PENDING, TaskStatus.ASSIGNED, TaskStatus.RUNNING}
    tasks = await swarm.list_tasks()
    for t in tasks:
        if t.status in pending_like:
            await swarm._task_board.update_task(t.id, status=TaskStatus.CANCELLED)
            cancelled += 1
    return cancelled


async def run_research_agents(
    swarm: SwarmManager,
    provider_cycle: list[ProviderType],
    timeout_sec: int,
) -> dict[str, Any]:
    prompts = [
        (
            "Research stress vectors",
            "Identify the 10 hardest stress vectors for DGC: tools, subagent spawning, "
            "message bus contention, task board saturation, and failure cascades. "
            "Output concise bullets with measurable pass/fail criteria.",
        ),
        (
            "Adversarial breakpoints",
            "Design adversarial tests that intentionally try to break Telos gates, Darwin "
            "evolution safety, and canary rollback. Include what evidence would prove resilience.",
        ),
    ]
    spawned = []
    created_ids: set[str] = set()
    outputs: list[dict[str, Any]] = []
    for i, (title, desc) in enumerate(prompts):
        provider = provider_cycle[i % len(provider_cycle)]
        agent = await swarm.spawn_agent(
            name=f"stress-research-{i + 1}",
            role=pick_role(i),
            model="claude-sonnet-4-5" if provider == ProviderType.CLAUDE_CODE else "codex",
            provider_type=provider,
            thread=pick_thread(i),
        )
        spawned.append(
            {"id": agent.id, "name": agent.name, "role": agent.role.value, "provider": provider.value}
        )
        task = await swarm.create_task(
            title=f"[stress-research] {title}",
            description=desc,
            priority=TaskPriority.HIGH,
        )
        created_ids.add(task.id)

    wait = await wait_for_tasks(swarm, created_ids, timeout_sec)
    for tid in created_ids:
        t = await swarm.get_task(tid)
        if t is None:
            continue
        outputs.append(
            {
                "task_id": tid,
                "status": t.status.value,
                "title": t.title,
                "result_head": (t.result or "")[:500],
            }
        )
    return {"agents": spawned, "wait": wait, "outputs": outputs}


async def run_agent_load(
    swarm: SwarmManager,
    provider_cycle: list[ProviderType],
    agents: int,
    tasks: int,
    timeout_sec: int,
) -> dict[str, Any]:
    spawned: list[dict[str, Any]] = []
    for i in range(agents):
        provider = provider_cycle[i % len(provider_cycle)]
        agent = await swarm.spawn_agent(
            name=f"stress-agent-{i + 1:02d}",
            role=pick_role(i),
            model="claude-sonnet-4-5" if provider == ProviderType.CLAUDE_CODE else "codex",
            provider_type=provider,
            thread=pick_thread(i),
        )
        spawned.append(
            {"id": agent.id, "name": agent.name, "role": agent.role.value, "provider": provider.value}
        )

    task_ids: set[str] = set()
    for i in range(tasks):
        desc = (
            "Stress task for orchestrator throughput. "
            f"Index={i}. Validate assumptions, check gates, propose one improvement, "
            "and keep output compact."
        )
        pri = TaskPriority.HIGH if i % 3 == 0 else TaskPriority.NORMAL
        task = await swarm.create_task(
            title=f"[stress-load] task-{i + 1:03d}",
            description=desc,
            priority=pri,
        )
        task_ids.add(task.id)

    wait = await wait_for_tasks(swarm, task_ids, timeout_sec)
    counts = {"completed": 0, "failed": 0, "cancelled": 0, "other": 0}
    failures: list[dict[str, str]] = []
    for tid in task_ids:
        t = await swarm.get_task(tid)
        if t is None:
            counts["other"] += 1
            failures.append({"task_id": tid, "reason": "missing"})
            continue
        match t.status:
            case TaskStatus.COMPLETED:
                counts["completed"] += 1
            case TaskStatus.FAILED:
                counts["failed"] += 1
                failures.append(
                    {"task_id": tid, "title": t.title, "error_head": (t.result or "")[:220]}
                )
            case TaskStatus.CANCELLED:
                counts["cancelled"] += 1
            case _:
                counts["other"] += 1
    throughput = 0.0
    if wait["elapsed_sec"] > 0:
        throughput = round(counts["completed"] / wait["elapsed_sec"], 3)
    return {
        "agents_spawned": len(spawned),
        "tasks_created": len(task_ids),
        "wait": wait,
        "counts": counts,
        "throughput_tasks_per_sec": throughput,
        "failures": failures[:20],
    }


async def run_evolution_stress(
    swarm: SwarmManager,
    evolutions: int,
    concurrency: int,
) -> dict[str, Any]:
    sem = asyncio.Semaphore(max(1, concurrency))
    results: list[dict[str, Any]] = []

    async def worker(i: int) -> None:
        async with sem:
            harmful = (i % 4 == 0)
            desc = (
                "exploit vulnerability and bypass safeguards"
                if harmful
                else "Improve reliability with input validation, type hints, and safer defaults"
            )
            diff = (
                "- old = risky_call(x)\n+ old = safe_call(x)\n+ assert x is not None\n"
                if not harmful
                else "- check = True\n+ check = False\n"
            )
            out = await swarm.evolve(
                component=f"stress_component_{i % 9}.py",
                change_type="mutation",
                description=desc,
                diff=diff,
            )
            rec: dict[str, Any] = {"index": i, "result": out}
            if out.get("status") == "archived":
                entry_id = out.get("entry_id")
                canary_fitness = round(random.uniform(0.35, 0.98), 3)
                canary = await swarm.canary_check(entry_id, canary_fitness)
                rec["canary"] = canary
            results.append(rec)

    await asyncio.gather(*(worker(i) for i in range(evolutions)))
    archived = sum(1 for r in results if r["result"].get("status") == "archived")
    rejected = sum(1 for r in results if r["result"].get("status") == "rejected")
    canary_promote = sum(
        1 for r in results if (r.get("canary") or {}).get("decision") == "promote"
    )
    canary_rollback = sum(
        1 for r in results if (r.get("canary") or {}).get("decision") == "rollback"
    )
    policy = await swarm.compile_policy(context="stress-max")
    trend = await swarm.fitness_trend()
    return {
        "submitted": evolutions,
        "archived": archived,
        "rejected": rejected,
        "canary_promote": canary_promote,
        "canary_rollback": canary_rollback,
        "policy": policy,
        "trend_points": len(trend),
        "sample": results[:10],
    }


async def run_cli_flood(rounds: int, concurrency: int) -> dict[str, Any]:
    commands = [
        ["python3", "-m", "dharma_swarm.dgc_cli", "status"],
        ["python3", "-m", "dharma_swarm.dgc_cli", "health-check"],
        ["python3", "-m", "dharma_swarm.dgc_cli", "dharma", "status"],
        ["python3", "-m", "dharma_swarm.dgc_cli", "gates", "safe refactor with tests"],
        ["python3", "-m", "dharma_swarm.dgc_cli", "route", "stress-test provider fallback and memory routing"],
        ["python3", "-m", "dharma_swarm.dgc_cli", "compose", "build then validate then deploy smoke sequence"],
        ["python3", "-m", "dharma_swarm.dgc_cli", "autonomy", "apply safe patch to provider retries"],
        ["python3", "-m", "dharma_swarm.dgc_cli", "context-search", "telos canary rollback trend"],
        ["python3", "-m", "dharma_swarm.dgc_cli", "stigmergy"],
        ["python3", "-m", "dharma_swarm.dgc_cli", "hum"],
    ]
    sem = asyncio.Semaphore(max(1, concurrency))
    rows: list[dict[str, Any]] = []

    async def one(cmd: list[str], round_idx: int) -> None:
        async with sem:
            out = await run_async_cmd(cmd, timeout=180)
            out["round"] = round_idx
            rows.append(out)

    await asyncio.gather(
        *(one(cmd, r) for r in range(rounds) for cmd in commands)
    )
    total = len(rows)
    failed = [r for r in rows if r["rc"] != 0]
    return {
        "total": total,
        "failed": len(failed),
        "pass_rate": round((total - len(failed)) / total, 3) if total else 0.0,
        "failures": failed[:25],
    }


async def run_external_research(timeout_sec: int) -> dict[str, Any]:
    """Optional direct Claude/Codex stress-research probes."""
    prompt = (
        "You are designing a maximum-capacity stress test for DGC. "
        "Focus on: tools execution, subagent spawning, orchestrator contention, "
        "message bus saturation, telos gates, evolution/canary rollback. "
        "Return 12 concrete torture tests with pass/fail metrics."
    )
    results: dict[str, Any] = {}
    jobs: list[tuple[str, list[str]]] = []
    if which("claude"):
        jobs.append(
            ("claude", ["claude", "-p", prompt, "--output-format", "text", "--model", "opus"])
        )
    if which("codex"):
        jobs.append(("codex", ["codex", "exec", prompt]))

    async def one(label: str, cmd: list[str]) -> tuple[str, dict[str, Any]]:
        return label, await run_async_cmd(cmd, timeout=timeout_sec)

    if jobs:
        for label, out in await asyncio.gather(*(one(lbl, cmd) for lbl, cmd in jobs)):
            results[label] = out

    if "claude" not in results:
        results["claude"] = None
    if "codex" not in results:
        results["codex"] = None
    return results


async def run_suite(cfg: StressConfig) -> dict[str, Any]:
    start = time.time()
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    SHARED.mkdir(parents=True, exist_ok=True)

    provider_cycle, resolved = choose_provider_cycle(cfg.provider_mode)

    preflight = {
        "ts_utc": utc_ts(),
        "python": sys.executable,
        "cwd": str(ROOT),
        "provider_mode_requested": cfg.provider_mode,
        "provider_mode_resolved": resolved,
        "provider_cycle": [p.value for p in provider_cycle],
        "bin": {
            "claude": which("claude"),
            "codex": which("codex"),
            "docker": which("docker"),
        },
        "keys": {
            "OPENROUTER_API_KEY": bool(os.getenv("OPENROUTER_API_KEY")),
            "OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY")),
            "NGC_API_KEY": bool(os.getenv("NGC_API_KEY")),
            "NVIDIA_API_KEY": bool(os.getenv("NVIDIA_API_KEY")),
        },
        "baseline": {
            "status": run_sync(["python3", "-m", "dharma_swarm.dgc_cli", "status"], timeout=90),
            "health_check": run_sync(
                ["python3", "-m", "dharma_swarm.dgc_cli", "health-check"], timeout=90
            ),
            "dharma_status": run_sync(
                ["python3", "-m", "dharma_swarm.dgc_cli", "dharma", "status"], timeout=90
            ),
        },
    }

    swarm = SwarmManager(state_dir=cfg.state_dir)
    await swarm.init()

    # Ensure stress run controls queue shape.
    cancelled_seed = await clear_seed_tasks(swarm)

    # If resolved mode ended up mock, replace router + existing runner providers.
    if resolved == "mock":
        swarm._router = build_mock_router()
        for runner in swarm._agent_pool._agents.values():
            runner._provider = MockStressProvider()

    phase_research = await run_research_agents(
        swarm,
        provider_cycle=provider_cycle,
        timeout_sec=max(60, cfg.orchestration_timeout_sec // 2),
    )
    phase_load = await run_agent_load(
        swarm,
        provider_cycle=provider_cycle,
        agents=cfg.agents,
        tasks=cfg.tasks,
        timeout_sec=cfg.orchestration_timeout_sec,
    )
    phase_evo = await run_evolution_stress(
        swarm,
        evolutions=cfg.evolutions,
        concurrency=cfg.evolution_concurrency,
    )
    phase_cli = await run_cli_flood(
        rounds=cfg.cli_rounds,
        concurrency=cfg.cli_concurrency,
    )

    await swarm.shutdown()

    ext = await run_external_research(cfg.external_timeout_sec) if cfg.external_research else {}

    return {
        "ts_utc": utc_ts(),
        "elapsed_sec": round(time.time() - start, 2),
        "config": {
            "profile": cfg.profile,
            "state_dir": str(cfg.state_dir),
            "provider_mode": cfg.provider_mode,
            "resolved_provider_mode": resolved,
            "agents": cfg.agents,
            "tasks": cfg.tasks,
            "evolutions": cfg.evolutions,
            "evolution_concurrency": cfg.evolution_concurrency,
            "cli_rounds": cfg.cli_rounds,
            "cli_concurrency": cfg.cli_concurrency,
            "orchestration_timeout_sec": cfg.orchestration_timeout_sec,
            "external_research": cfg.external_research,
            "external_timeout_sec": cfg.external_timeout_sec,
        },
        "preflight": preflight,
        "cancelled_seed_tasks": cancelled_seed,
        "phase_research_agents": phase_research,
        "phase_orchestrator_load": phase_load,
        "phase_evolution": phase_evo,
        "phase_cli_flood": phase_cli,
        "phase_external_research": ext,
    }


def render_markdown(report: dict[str, Any]) -> str:
    cfg = report["config"]
    pre = report["preflight"]
    research = report["phase_research_agents"]
    load = report["phase_orchestrator_load"]
    evo = report["phase_evolution"]
    cli = report["phase_cli_flood"]
    ext = report.get("phase_external_research", {})
    fail_lines: list[str] = []
    for f in cli.get("failures", [])[:10]:
        cmd = " ".join(f.get("cmd", []))
        fail_lines.append(f"- rc={f.get('rc')} cmd=`{cmd}`")
    if not fail_lines:
        fail_lines.append("- none")
    ext_lines: list[str] = []
    if cfg["external_research"]:
        for label in ("claude", "codex"):
            row = ext.get(label)
            if row is None:
                ext_lines.append(f"- {label}: not available")
                continue
            ext_lines.append(
                f"- {label}: rc={row.get('rc')} elapsed={row.get('elapsed_sec')}s "
                f"stderr_tail=`{(row.get('stderr_tail') or '').strip()[:120]}`"
            )
    else:
        ext_lines.append("- external probes skipped")

    md = [
        "# DGC Max Stress Report",
        f"- Timestamp (UTC): `{report['ts_utc']}`",
        f"- Elapsed: `{report['elapsed_sec']}s`",
        f"- Profile: `{cfg['profile']}`",
        f"- Provider mode: `{cfg['provider_mode']}` -> `{cfg['resolved_provider_mode']}`",
        "",
        "## Preflight",
        f"- claude binary: `{pre['bin']['claude']}`",
        f"- codex binary: `{pre['bin']['codex']}`",
        f"- docker binary: `{pre['bin']['docker']}`",
        f"- OPENROUTER_API_KEY: `{pre['keys']['OPENROUTER_API_KEY']}`",
        f"- OPENAI_API_KEY: `{pre['keys']['OPENAI_API_KEY']}`",
        f"- NGC_API_KEY: `{pre['keys']['NGC_API_KEY']}`",
        "",
        "## Research Agents",
        f"- complete: `{research['wait']['complete']}`",
        f"- elapsed: `{research['wait']['elapsed_sec']}s`",
        f"- status sample: `{research['wait']['statuses']}`",
        "",
        "## Orchestrator Load",
        f"- Agents spawned: `{load['agents_spawned']}`",
        f"- Tasks created: `{load['tasks_created']}`",
        f"- Completed: `{load['counts']['completed']}`",
        f"- Failed: `{load['counts']['failed']}`",
        f"- Other/incomplete: `{load['counts']['other']}`",
        f"- Throughput tasks/sec: `{load['throughput_tasks_per_sec']}`",
        "",
        "## Evolution Stress",
        f"- Submitted: `{evo['submitted']}`",
        f"- Archived: `{evo['archived']}`",
        f"- Rejected by gates: `{evo['rejected']}`",
        f"- Canary promote: `{evo['canary_promote']}`",
        f"- Canary rollback: `{evo['canary_rollback']}`",
        f"- Policy rules total: `{evo['policy']['total_rules']}`",
        "",
        "## CLI Flood",
        f"- Total command invocations: `{cli['total']}`",
        f"- Failed: `{cli['failed']}`",
        f"- Pass rate: `{cli['pass_rate']}`",
        "",
        "### CLI Failure Sample",
        *fail_lines,
        "",
        "## External Research",
        f"- enabled: `{cfg['external_research']}`",
        *ext_lines,
        "",
        "## Next Fix Targets",
        "1. Any failing CLI commands from the sample above.",
        "2. Incomplete tasks (`counts.other`) or timed-out research agents.",
        "3. Evolution reject/rollback ratio if unexpectedly high for safe proposals.",
    ]
    return "\n".join(md) + "\n"


def parse_args() -> StressConfig:
    parser = argparse.ArgumentParser(description="Run DGC max stress harness.")
    parser.add_argument("--profile", choices=["quick", "full", "max"], default="full")
    parser.add_argument(
        "--state-dir",
        default=str(HOME / ".dharma" / "stress_lab"),
        help="State dir for stress run (defaults to isolated stress_lab).",
    )
    parser.add_argument(
        "--provider-mode",
        choices=["auto", "mock", "claude", "codex", "openrouter"],
        default="auto",
    )
    parser.add_argument("--agents", type=int, default=8)
    parser.add_argument("--tasks", type=int, default=36)
    parser.add_argument("--evolutions", type=int, default=24)
    parser.add_argument("--evolution-concurrency", type=int, default=6)
    parser.add_argument("--cli-rounds", type=int, default=2)
    parser.add_argument("--cli-concurrency", type=int, default=8)
    parser.add_argument("--orchestration-timeout-sec", type=int, default=240)
    parser.add_argument("--external-timeout-sec", type=int, default=120)
    parser.add_argument(
        "--external-research",
        action="store_true",
        help="Also invoke claude/codex directly for adversarial stress ideas.",
    )
    args = parser.parse_args()

    if args.profile == "quick":
        args.agents = min(args.agents, 4)
        args.tasks = min(args.tasks, 12)
        args.evolutions = min(args.evolutions, 8)
        args.cli_rounds = min(args.cli_rounds, 1)
        args.cli_concurrency = min(args.cli_concurrency, 4)
        args.orchestration_timeout_sec = min(args.orchestration_timeout_sec, 90)
    elif args.profile == "max":
        args.agents = max(args.agents, 12)
        args.tasks = max(args.tasks, 72)
        args.evolutions = max(args.evolutions, 60)
        args.evolution_concurrency = max(args.evolution_concurrency, 10)
        args.cli_rounds = max(args.cli_rounds, 4)
        args.cli_concurrency = max(args.cli_concurrency, 12)
        args.orchestration_timeout_sec = max(args.orchestration_timeout_sec, 420)

    return StressConfig(
        profile=args.profile,
        state_dir=Path(args.state_dir).expanduser(),
        provider_mode=args.provider_mode,
        agents=args.agents,
        tasks=args.tasks,
        evolutions=args.evolutions,
        evolution_concurrency=args.evolution_concurrency,
        cli_rounds=args.cli_rounds,
        cli_concurrency=args.cli_concurrency,
        orchestration_timeout_sec=args.orchestration_timeout_sec,
        external_research=bool(args.external_research),
        external_timeout_sec=args.external_timeout_sec,
    )


async def amain() -> int:
    cfg = parse_args()
    report = await run_suite(cfg)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    SHARED.mkdir(parents=True, exist_ok=True)
    out_json = SHARED / f"dgc_max_stress_{run_id}.json"
    out_md = SHARED / f"dgc_max_stress_{run_id}.md"
    out_json.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    out_md.write_text(render_markdown(report), encoding="utf-8")

    print(f"Stress run complete: {run_id}")
    print(f"JSON: {out_json}")
    print(f"MD:   {out_md}")
    return 0


def main() -> int:
    try:
        return asyncio.run(amain())
    except KeyboardInterrupt:
        print("Interrupted.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
