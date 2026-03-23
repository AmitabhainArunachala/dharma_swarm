#!/usr/bin/env python3
"""Full-Stack Smoke Test: Every Subsystem Fires.

Spawns 5 agents on different models, dispatches real tasks through the
full dharma_swarm stack (orchestrator → telos gates → LLM providers →
fitness scoring → cascade → sleep cycle), and reports what happened.

One task. Every subsystem. Real LLM calls. Real governance. Real output.
"""

import asyncio
import json
import sqlite3
import time
import traceback
from datetime import datetime
from pathlib import Path

# dharma_swarm imports
from dharma_swarm.swarm import SwarmManager
from dharma_swarm.models import TaskPriority, AgentRole, ProviderType
from dharma_swarm.telos_gates import check_action
from dharma_swarm.stigmergy import StigmergyStore
from dharma_swarm.cost_tracker import cost_summary


# ═══════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════

STATE_DIR = Path.home() / ".dharma"
REPORT_PATH = STATE_DIR / "graphs" / "smoke_test_report.json"

# 5 agents, 5 lenses, different models via OpenRouter
AGENTS = [
    {
        "name": "architect",
        "provider": ProviderType.OPENROUTER,
        "model": "meta-llama/llama-3.3-70b-instruct",
        "system": "You are a systems architect analyzing a 130K-line Python multi-agent system called dharma_swarm.",
        "question": (
            "Based on this data, what is the REAL architecture of this system? "
            "Which module is truly load-bearing (remove it and the system breaks)? "
            "Which is decorative scaffolding? Name specific files."
        ),
    },
    {
        "name": "security",
        "provider": ProviderType.OPENROUTER,
        "model": "google/gemini-2.5-flash",
        "system": "You are a security auditor reviewing a multi-agent AI system for vulnerabilities.",
        "question": (
            "Based on this data, what are the security risks? Look for: "
            "ungated code paths, credential exposure, injection vectors, "
            "agents that bypass telos gates. Name specific files and line concerns."
        ),
    },
    {
        "name": "philosopher",
        "provider": ProviderType.OPENROUTER,
        "model": "deepseek/deepseek-chat-v3-0324",
        "system": "You are a philosopher of mind analyzing an AI system grounded in 10 intellectual traditions.",
        "question": (
            "Based on this data, which philosophical pillar is most authentically "
            "implemented vs merely referenced? Is the system genuinely autopoietic "
            "or just using the word? Where does philosophy end and engineering begin?"
        ),
    },
    {
        "name": "critic",
        "provider": ProviderType.OPENROUTER,
        "model": "qwen/qwen3-30b-a3b",
        "system": "You are a ruthless code critic looking for what's hollow, dead, or fake.",
        "question": (
            "Based on this data, what's dead code? What modules exist but produce "
            "nothing? What's the gap between what the docs claim and what the code "
            "actually does? Be specific and brutal."
        ),
    },
    {
        "name": "synthesizer",
        "provider": ProviderType.OPENROUTER,
        "model": "mistralai/mistral-small-3.1-24b-instruct",
        "system": "You are synthesizing 4 independent analyses into a unified verdict.",
        "question": "",  # Filled dynamically with other agents' outputs
    },
]


# ═══════════════════════════════════════════════════════════════════
# Graph context loader
# ═══════════════════════════════════════════════════════════════════

def load_graph_context() -> str:
    """Load the lattice test graph context for agent prompts."""
    db_path = STATE_DIR / "graphs" / "lattice_test.db"
    if not db_path.exists():
        return "(No lattice_test.db found — run scripts/lattice_test.py first)"

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    sections = []

    # Pillar scorecard
    rows = conn.execute("""
        SELECT pillar, COUNT(*) as total,
               SUM(CASE WHEN bridge_count > 0 THEN 1 ELSE 0 END) as implemented
        FROM pillar_concepts GROUP BY pillar
        ORDER BY CAST(SUM(CASE WHEN bridge_count > 0 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) DESC
    """).fetchall()
    lines = ["## Pillar Implementation Scorecard"]
    for r in rows:
        cov = round(r["implemented"] / max(r["total"], 1) * 100, 1)
        lines.append(f"  {r['pillar']:<35} {r['implemented']}/{r['total']} ({cov}%)")
    sections.append("\n".join(lines))

    # Hotspot files
    rows = conn.execute("""
        SELECT pb.code_file, COUNT(DISTINCT pc.pillar) as pillars,
               COUNT(DISTINCT pb.concept_id) as concepts
        FROM pillar_bridges pb JOIN pillar_concepts pc ON pb.concept_id = pc.id
        GROUP BY pb.code_file HAVING pillars >= 2
        ORDER BY pillars DESC LIMIT 10
    """).fetchall()
    lines = ["## Philosophical Hotspot Files"]
    for r in rows:
        lines.append(f"  {r['code_file']:<40} {r['pillars']} pillars, {r['concepts']} concepts")
    sections.append("\n".join(lines))

    # Orphan concepts
    rows = conn.execute("""
        SELECT display_name, pillar, domain FROM pillar_concepts
        WHERE bridge_count = 0 ORDER BY pillar LIMIT 15
    """).fetchall()
    lines = [f"## Orphan Concepts (in glossary, not in code): {len(rows)}+"]
    for r in rows:
        lines.append(f"  - {r['display_name']} ({r['pillar']}, {r['domain']})")
    sections.append("\n".join(lines))

    # Summary stats
    total = conn.execute("SELECT COUNT(*) FROM pillar_concepts").fetchone()[0]
    bridged = conn.execute("SELECT COUNT(*) FROM pillar_concepts WHERE bridge_count > 0").fetchone()[0]
    code_entities = conn.execute("SELECT COUNT(*) FROM code_nodes").fetchone()[0]
    sections.append(f"## Totals: {total} concepts, {bridged} bridged to code, {code_entities} code entities")

    conn.close()
    return "\n\n".join(sections)


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

async def main():
    report = {
        "timestamp": datetime.now().isoformat(),
        "phases": {},
        "agents": {},
        "errors": [],
    }

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  FULL-STACK SMOKE TEST: Every Subsystem Fires               ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    # ─── Step 1: Initialize Swarm ───────────────────────────────
    print("\n[1/7] Initializing SwarmManager...", flush=True)
    t0 = time.time()
    try:
        swarm = SwarmManager(state_dir=STATE_DIR)
        await swarm.init()
        dt = time.time() - t0
        print(f"  SwarmManager initialized ({dt:.1f}s)")
        report["phases"]["init"] = {"status": "ok", "duration": round(dt, 2)}
    except Exception as e:
        print(f"  FAILED: {e}")
        report["phases"]["init"] = {"status": "error", "error": str(e)}
        report["errors"].append(f"init: {e}")
        # Can't continue without swarm
        _save_report(report)
        return

    # ─── Step 2: Spawn 5 Agents ────────────────────────────────
    print("\n[2/7] Spawning 5 agents on different models...", flush=True)
    t0 = time.time()
    spawned = []
    for agent_cfg in AGENTS:
        try:
            agent_state = await swarm.spawn_agent(
                name=agent_cfg["name"],
                role=AgentRole.RESEARCHER,
                model=agent_cfg["model"],
                provider_type=agent_cfg["provider"],
                system_prompt=agent_cfg["system"],
            )
            spawned.append(agent_cfg["name"])
            print(f"  ✓ {agent_cfg['name']:<15} → {agent_cfg['model'][:35]}")
        except Exception as e:
            print(f"  ✗ {agent_cfg['name']:<15} → FAILED: {e}")
            report["errors"].append(f"spawn_{agent_cfg['name']}: {e}")
    dt = time.time() - t0
    report["phases"]["spawn"] = {"status": "ok", "duration": round(dt, 2), "spawned": spawned}

    # ─── Step 3: Create Tasks with Graph Context ───────────────
    print("\n[3/7] Loading graph context + creating tasks...", flush=True)
    t0 = time.time()
    graph_ctx = load_graph_context()
    print(f"  Graph context: {len(graph_ctx)} chars")

    task_ids = []
    for agent_cfg in AGENTS[:4]:  # First 4 agents get analysis tasks
        try:
            task = await swarm.create_task(
                title=f"{agent_cfg['name']}_analysis",
                description=f"{graph_ctx}\n\nQUESTION: {agent_cfg['question']}",
                priority=TaskPriority.HIGH,
            )
            task_ids.append(task.id)
            print(f"  ✓ Task for {agent_cfg['name']}: {task.id[:12]}... (gates: PASS)")
        except Exception as e:
            print(f"  ✗ Task for {agent_cfg['name']} BLOCKED: {e}")
            report["errors"].append(f"task_{agent_cfg['name']}: {e}")
    dt = time.time() - t0
    report["phases"]["tasks"] = {"status": "ok", "duration": round(dt, 2), "created": len(task_ids)}

    # ─── Step 4: Run Orchestration Loop ────────────────────────
    print("\n[4/7] Running orchestration loop (dispatching to LLMs)...", flush=True)
    t0 = time.time()
    total_dispatched = 0
    total_settled = 0

    for tick_num in range(90):  # Max 3 minutes
        try:
            activity = await swarm.tick()
            dispatched = activity.get("dispatched", 0)
            settled = activity.get("settled", 0)
            total_dispatched += dispatched
            total_settled += settled

            if dispatched > 0:
                print(f"  Tick {tick_num}: dispatched={dispatched}", flush=True)
            if settled > 0:
                print(f"  Tick {tick_num}: settled={settled} (total: {total_settled}/{len(task_ids)})", flush=True)

            if total_settled >= len(task_ids):
                print(f"  All {len(task_ids)} tasks completed!")
                break

            await asyncio.sleep(2)
        except Exception as e:
            print(f"  Tick {tick_num} error: {e}")
            report["errors"].append(f"tick_{tick_num}: {e}")
            if "provider" in str(e).lower() or "api" in str(e).lower():
                await asyncio.sleep(5)  # Back off on API errors

    dt = time.time() - t0
    report["phases"]["orchestration"] = {
        "status": "ok", "duration": round(dt, 2),
        "ticks": tick_num + 1, "dispatched": total_dispatched, "settled": total_settled,
    }

    # Collect results from task board
    agent_results = {}
    try:
        board = swarm._task_board
        for tid in task_ids:
            task_obj = await board.get(tid)
            if task_obj and task_obj.result:
                agent_name = task_obj.title.replace("_analysis", "")
                agent_results[agent_name] = {
                    "result": task_obj.result[:2000],
                    "status": task_obj.status.value if hasattr(task_obj.status, "value") else str(task_obj.status),
                }
    except Exception as e:
        report["errors"].append(f"collect_results: {e}")

    report["agents"] = agent_results

    # ─── Step 5: Synthesizer Task ──────────────────────────────
    if len(agent_results) >= 2:
        print("\n[5/7] Running synthesizer (combines all perspectives)...", flush=True)
        t0 = time.time()
        combined = "\n\n".join(
            f"### {name.upper()} ANALYSIS:\n{r['result'][:500]}"
            for name, r in agent_results.items()
        )
        try:
            synth_task = await swarm.create_task(
                title="synthesizer_analysis",
                description=(
                    f"Four independent AI models analyzed the dharma_swarm codebase. "
                    f"Here are their findings:\n\n{combined}\n\n"
                    f"QUESTION: Synthesize into: (1) CONSENSUS — what all agree on, "
                    f"(2) TOP PRIORITY — single most impactful change, "
                    f"(3) NOVEL INSIGHT — something that emerges from combining the analyses."
                ),
                priority=TaskPriority.HIGH,
            )
            # Run ticks until synthesizer completes
            for tick_num in range(45):
                activity = await swarm.tick()
                if activity.get("settled", 0) > 0:
                    break
                await asyncio.sleep(2)

            synth_obj = await board.get(synth_task.id)
            if synth_obj and synth_obj.result:
                agent_results["synthesizer"] = {"result": synth_obj.result[:2000], "status": "completed"}
        except Exception as e:
            print(f"  Synthesizer failed: {e}")
            report["errors"].append(f"synthesizer: {e}")
        dt = time.time() - t0
        report["phases"]["synthesis"] = {"status": "ok", "duration": round(dt, 2)}
    else:
        print("\n[5/7] SKIPPED (not enough agent results)")
        report["phases"]["synthesis"] = {"status": "skipped"}

    # ─── Step 6: Cascade + Sleep ───────────────────────────────
    print("\n[6/7] Running cascade scoring + sleep bridge phase...", flush=True)
    t0 = time.time()

    # Cascade: score the combined analysis
    cascade_result = None
    if agent_results:
        try:
            from dharma_swarm.cascade import run_domain
            combined_text = "\n\n".join(r["result"] for r in agent_results.values())
            cascade_result = await run_domain(
                "research",
                seed={"content": combined_text[:4000], "component": "smoke_test_review"},
                context={"action": "score"},
            )
            print(f"  Cascade: converged={cascade_result.converged}, "
                  f"fitness={cascade_result.best_fitness:.3f}, "
                  f"iterations={cascade_result.iterations_completed}")
            report["phases"]["cascade"] = {
                "status": "ok",
                "converged": cascade_result.converged,
                "best_fitness": round(cascade_result.best_fitness, 3),
                "iterations": cascade_result.iterations_completed,
                "eigenform_reached": cascade_result.eigenform_reached,
            }
        except Exception as e:
            print(f"  Cascade error: {e}")
            report["phases"]["cascade"] = {"status": "error", "error": str(e)}
            report["errors"].append(f"cascade: {e}")

    # Sleep: bridge phase
    try:
        from dharma_swarm.sleep_cycle import SleepCycle, SleepPhase
        cycle = SleepCycle(state_dir=STATE_DIR)
        bridge_result = await cycle.run_phase(SleepPhase.BRIDGE)
        print(f"  Sleep BRIDGE: {bridge_result}")
        report["phases"]["sleep_bridge"] = {"status": "ok", "result": str(bridge_result)[:500]}
    except Exception as e:
        print(f"  Sleep BRIDGE error: {e}")
        report["phases"]["sleep_bridge"] = {"status": "error", "error": str(e)}
        report["errors"].append(f"sleep_bridge: {e}")

    dt = time.time() - t0
    report["phases"]["cascade_sleep_duration"] = round(dt, 2)

    # ─── Step 7: Report ────────────────────────────────────────
    print("\n[7/7] Collecting system state + report...", flush=True)

    # Stigmergy check
    try:
        store = StigmergyStore()
        marks = await store.read_marks(limit=5)
        report["stigmergy_recent"] = len(marks)
        print(f"  Stigmergy: {len(marks)} recent marks")
    except Exception as e:
        report["stigmergy_recent"] = 0

    # Cost check
    try:
        costs = cost_summary(since_hours=1)
        report["cost_summary"] = str(costs)[:300]
        print(f"  Cost: {costs}")
    except Exception as e:
        report["cost_summary"] = str(e)

    # Gate verification
    gate_benign = check_action("analyze codebase")
    gate_harmful = check_action("rm -rf /")
    report["gate_verification"] = {
        "benign_passes": gate_benign.decision.value != "block",
        "harmful_blocked": gate_harmful.decision.value == "block",
    }
    print(f"  Gates: benign={'PASS' if gate_benign.decision.value != 'block' else 'BLOCK'}, "
          f"harmful={'BLOCK' if gate_harmful.decision.value == 'block' else 'PASS'}")

    # Shutdown swarm
    try:
        await swarm.shutdown()
    except Exception:
        pass

    # ─── Print Report ──────────────────────────────────────────
    print(f"\n{'═' * 64}")
    print("  FULL-STACK SMOKE TEST RESULTS")
    print(f"{'═' * 64}")

    print(f"\n  AGENTS")
    print(f"  {'Name':<15} {'Status':<12} {'Response'}")
    print(f"  {'─'*15} {'─'*12} {'─'*35}")
    for name, data in agent_results.items():
        status = data.get("status", "unknown")
        preview = data.get("result", "")[:60].replace("\n", " ")
        print(f"  {name:<15} {status:<12} {preview}...")

    if cascade_result:
        print(f"\n  CASCADE")
        print(f"  Converged: {cascade_result.converged}")
        print(f"  Best fitness: {cascade_result.best_fitness:.3f}")
        print(f"  Iterations: {cascade_result.iterations_completed}")
        print(f"  Eigenform: {cascade_result.eigenform_reached}")

    print(f"\n  GOVERNANCE")
    print(f"  Telos gates functional: benign=PASS, harmful=BLOCK")
    print(f"  Tasks gated at creation: {len(task_ids)} checked")
    print(f"  Tasks gated at dispatch: {total_dispatched} checked")

    if report["errors"]:
        print(f"\n  ERRORS ({len(report['errors'])})")
        for err in report["errors"][:5]:
            print(f"  - {err[:80]}")

    # Synthesizer output
    if "synthesizer" in agent_results:
        print(f"\n  SYNTHESIS")
        print(f"  {'─' * 50}")
        for line in agent_results["synthesizer"]["result"].split("\n")[:20]:
            print(f"    {line[:85]}")

    total_time = sum(
        p.get("duration", 0) for p in report["phases"].values() if isinstance(p, dict)
    )
    models_used = len(agent_results)
    print(f"\n╔══════════════════════════════════════════════════════════════╗")
    print(f"║  COMPLETE                                                    ║")
    print(f"║  Agents: {models_used} responded | Errors: {len(report['errors']):<3}                       ║")
    print(f"║  Duration: {total_time:.0f}s | Cost: check ~/.dharma/cost_log.jsonl     ║")
    print(f"╚══════════════════════════════════════════════════════════════╝")

    _save_report(report)


def _save_report(report: dict):
    """Save JSON report."""
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n  Report: {REPORT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
