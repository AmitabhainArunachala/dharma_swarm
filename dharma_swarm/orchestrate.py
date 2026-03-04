#!/usr/bin/env python3
"""DHARMA SWARM Orchestrator — the brain that spawns Claude Code instances.

This IS a Claude Code instance itself (run via `claude -p`).
It reads system state, decides what agents are needed, spawns them,
monitors their work, and adapts on the next cycle.

The orchestrator can be called by:
  - DGC pulse daemon (cron/launchd, every N hours)
  - Manually: python3 -m dharma_swarm.orchestrate
  - By another Claude Code instance that decides it needs a swarm

It spawns real `claude -p` processes — each one has full tools,
file access, bash. Not API calls. Real agents.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field

HOME = Path.home()
SHARED = HOME / ".dharma" / "shared"
STATE_FILE = HOME / ".dharma" / "orchestrator_state.json"
AGENT_DIR = HOME / ".dharma" / "agents"


@dataclass
class AgentSpec:
    """Definition of an agent to spawn."""
    name: str
    role: str
    prompt: str
    priority: int = 5        # 1=critical, 10=nice-to-have
    timeout: int = 300        # seconds per cycle
    loops: int = 1            # how many cycles (-1 = until .STOP)


@dataclass
class SwarmPlan:
    """What the orchestrator decided to do this cycle."""
    agents: list[AgentSpec] = field(default_factory=list)
    reasoning: str = ""
    timestamp: str = ""


def read_system_state() -> dict:
    """Read everything the orchestrator needs to make decisions."""
    state = {}

    # What agents wrote last time
    state["agent_notes"] = {}
    if SHARED.exists():
        for f in SHARED.glob("*_notes.md"):
            content = f.read_text()
            # Last 50 lines — what they found recently
            lines = content.strip().split("\n")
            state["agent_notes"][f.stem] = "\n".join(lines[-50:])

    # Ecosystem health
    manifest_path = HOME / ".dharma_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        eco = manifest.get("ecosystem", {})
        state["ecosystem_alive"] = sum(1 for v in eco.values() if v.get("exists"))
        state["ecosystem_total"] = len(eco)
        state["last_scan"] = manifest.get("last_scan", "never")

    # Running agents (check for running claude processes)
    try:
        result = subprocess.run(
            ["pgrep", "-f", "claude -p"],
            capture_output=True, text=True, timeout=5
        )
        state["running_agents"] = len(result.stdout.strip().split("\n")) if result.stdout.strip() else 0
    except Exception:
        state["running_agents"] = 0

    # Pending work signals
    stuck_file = SHARED / "stuck.md"
    if stuck_file.exists():
        state["stuck"] = stuck_file.read_text()[:500]

    # Test status
    try:
        result = subprocess.run(
            ["python3", "-m", "pytest", "tests/", "-q", "--tb=no"],
            capture_output=True, text=True, timeout=60,
            cwd=str(HOME / "dharma_swarm")
        )
        state["tests"] = result.stdout.strip().split("\n")[-1]
    except Exception as e:
        state["tests"] = f"couldn't run: {e}"

    # AGNI state
    agni_priorities = HOME / "agni-workspace" / "PRIORITIES.md"
    if agni_priorities.exists():
        age_h = (time.time() - agni_priorities.stat().st_mtime) / 3600
        state["agni_priorities_age_hours"] = round(age_h, 1)

    # Trishula inbox count
    inbox = HOME / "trishula" / "inbox"
    if inbox.exists():
        state["trishula_messages"] = len(list(inbox.glob("*.md")))

    # Git status of dharma_swarm
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-5"],
            capture_output=True, text=True, timeout=5,
            cwd=str(HOME / "dharma_swarm")
        )
        state["recent_commits"] = result.stdout.strip()
    except Exception:
        state["recent_commits"] = "unknown"

    return state


def spawn_agent(spec: AgentSpec) -> subprocess.Popen:
    """Spawn a single Claude Code instance as a background process.

    Injects multi-layer context from the context engine so agents are
    ecosystem-aware, not generic LLM calls.
    """
    AGENT_DIR.mkdir(parents=True, exist_ok=True)

    # Write the agent's output to a dedicated file
    output_file = AGENT_DIR / f"{spec.name}_{int(time.time())}.md"

    env = {**os.environ, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
    # Remove CLAUDECODE env var so nested sessions work
    env.pop("CLAUDECODE", None)

    # Build context-aware prompt using the 5-layer engine
    context_block = ""
    try:
        from dharma_swarm.context import build_agent_context
        context_block = build_agent_context(role=spec.role.lower())
    except Exception:
        pass  # Graceful degradation — still spawn without context

    full_prompt = f"""You are agent {spec.name} in DHARMA SWARM.

{spec.prompt}

{context_block}

## Communication
- Write findings to ~/.dharma/shared/{spec.name}_notes.md (APPEND, don't overwrite)
- Read other agents' notes in ~/.dharma/shared/ first
- Work in ~/dharma_swarm/ as primary codebase

## Rules
- One cycle = one concrete action + one finding
- Run pytest after any code change
- Be brief. Ship code, not docs."""

    proc = subprocess.Popen(
        ["claude", "-p", full_prompt, "--output-format", "text"],
        stdout=open(output_file, "w"),
        stderr=subprocess.STDOUT,
        env=env,
    )

    return proc


def spawn_swarm(plan: SwarmPlan) -> list[subprocess.Popen]:
    """Spawn all agents in the plan."""
    SHARED.mkdir(parents=True, exist_ok=True)

    # Write swarm state for agents to read
    (SHARED / "CURRENT_PLAN.md").write_text(
        f"# Current Swarm Plan\n\n"
        f"**Time**: {plan.timestamp}\n"
        f"**Agents**: {len(plan.agents)}\n"
        f"**Reasoning**: {plan.reasoning}\n\n"
        + "\n".join(f"- **{a.name}**: {a.role}" for a in plan.agents)
    )

    procs = []
    for spec in sorted(plan.agents, key=lambda a: a.priority):
        proc = spawn_agent(spec)
        print(f"  Spawned {spec.name} (pid {proc.pid})")
        procs.append(proc)
        time.sleep(2)  # stagger launches slightly

    return procs


def wait_for_swarm(procs: list[subprocess.Popen], timeout: int = 600) -> None:
    """Wait for all agents to finish, with timeout."""
    deadline = time.time() + timeout
    for proc in procs:
        remaining = max(1, deadline - time.time())
        try:
            proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            proc.terminate()
            print(f"  Agent pid {proc.pid} timed out, terminated")


def save_state(plan: SwarmPlan, results: dict) -> None:
    """Save orchestrator state for next cycle."""
    state = {
        "last_run": plan.timestamp,
        "agents_spawned": len(plan.agents),
        "reasoning": plan.reasoning,
        "agent_names": [a.name for a in plan.agents],
        "results": results,
    }
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ── Predefined swarm configurations ──────────────────────────────────

def plan_small_maintenance() -> SwarmPlan:
    """3 agents: quick health check and fixes."""
    return SwarmPlan(
        agents=[
            AgentSpec(
                name="health-checker",
                role="System Health",
                prompt=(
                    "Check system health: run pytest in ~/dharma_swarm/, "
                    "verify imports work, check ~/.dharma_manifest.json is current. "
                    "Fix anything broken."
                ),
                priority=1,
            ),
            AgentSpec(
                name="memory-consolidator",
                role="Memory",
                prompt=(
                    "Read ~/.dharma/shared/*_notes.md from all previous agent runs. "
                    "Consolidate key findings into ~/.dharma/shared/consolidated_knowledge.md. "
                    "Remove noise, keep insights."
                ),
                priority=3,
            ),
            AgentSpec(
                name="next-actions",
                role="Planning",
                prompt=(
                    "Read consolidated knowledge and system state. "
                    "Write the 5 most important next actions to "
                    "~/.dharma/shared/next_actions.md. Be specific — "
                    "file paths, function names, concrete changes."
                ),
                priority=5,
            ),
        ],
        reasoning="Routine maintenance: health check, consolidate, plan next",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def plan_full_build() -> SwarmPlan:
    """5 agents: full synthesis and build cycle."""
    return SwarmPlan(
        agents=[
            AgentSpec(
                name="synthesizer",
                role="Synthesis",
                prompt=(
                    "Read ALL codebases: ~/dgc-core/, ~/dharma_swarm/, "
                    "~/DHARMIC_GODEL_CLAW/swarm/, ~/.chaiwala/. "
                    "Find what works, what's dead, what overlaps. "
                    "Write unified module list to ~/.dharma/shared/synthesis.md."
                ),
                priority=1,
                timeout=600,
            ),
            AgentSpec(
                name="builder",
                role="Builder",
                prompt=(
                    "Read ~/.dharma/shared/synthesis.md. Build the unified package. "
                    "Focus: agent spawning via claude -p, task routing, memory persistence. "
                    "Write working Python with tests. Run pytest after every change."
                ),
                priority=2,
                timeout=600,
            ),
            AgentSpec(
                name="critic",
                role="Critic",
                prompt=(
                    "Read everything in ~/.dharma/shared/. Find bugs, gaps, lies. "
                    "Run tests. Check claims against reality. "
                    "Write honest assessment to ~/.dharma/shared/critique.md."
                ),
                priority=3,
            ),
            AgentSpec(
                name="researcher",
                role="Research",
                prompt=(
                    "Deep-read PSMV: crown jewels, DHARMA Genome Spec, Garden Daemon Spec, "
                    "v7 induction prompts. Extract what's usable as code. "
                    "Write to ~/.dharma/shared/research_findings.md."
                ),
                priority=4,
                timeout=600,
            ),
            AgentSpec(
                name="validator",
                role="Validator",
                prompt=(
                    "Run every test. Try every CLI command. Import every module. "
                    "Check ecosystem_map paths exist. Report what works vs claimed. "
                    "Write to ~/.dharma/shared/validation.md."
                ),
                priority=5,
            ),
        ],
        reasoning="Full build cycle: synthesize, build, critique, research, validate",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def plan_research_deep_dive() -> SwarmPlan:
    """4 agents: focused research across the vault."""
    return SwarmPlan(
        agents=[
            AgentSpec(
                name="rv-researcher",
                role="R_V Research",
                prompt=(
                    "Focus on R_V paper: read ~/mech-interp-latent-lab-phase1/R_V_PAPER/, "
                    "the gap analysis, and MI_AGENT_TO_CODEX_RV_ANSWERS.md. "
                    "Identify exactly what's missing for COLM submission. "
                    "Write to ~/.dharma/shared/rv_paper_status.md."
                ),
                priority=1,
                timeout=600,
            ),
            AgentSpec(
                name="genome-researcher",
                role="DHARMA Genome",
                prompt=(
                    "Read DHARMA_GENOME_SPECIFICATION.md in PSMV. "
                    "Extract every testable, implementable idea. "
                    "Write pseudocode for Tier A tests and MAP-Elites descriptors. "
                    "Output to ~/.dharma/shared/genome_implementation.md."
                ),
                priority=2,
                timeout=600,
            ),
            AgentSpec(
                name="ecosystem-mapper",
                role="Ecosystem Map",
                prompt=(
                    "Read every CLAUDE*.md file (CLAUDE.md through CLAUDE9.md). "
                    "Read ecosystem_map.py. Verify which paths still exist. "
                    "Write a living map to ~/.dharma/shared/ecosystem_current.md."
                ),
                priority=3,
            ),
            AgentSpec(
                name="connection-finder",
                role="Connections",
                prompt=(
                    "Read the synthesis, research, and ecosystem map from shared/. "
                    "Find connections nobody has made yet. "
                    "What in PSMV is already implemented in code but nobody knows? "
                    "What code exists that matches specs nobody has read? "
                    "Write to ~/.dharma/shared/hidden_connections.md."
                ),
                priority=4,
                timeout=600,
            ),
        ],
        reasoning="Research deep dive: R_V paper, genome implementation, ecosystem mapping, connections",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def plan_deployment() -> SwarmPlan:
    """3 agents: deployment and infrastructure work."""
    return SwarmPlan(
        agents=[
            AgentSpec(
                name="agni-ops",
                role="AGNI Operations",
                prompt=(
                    "Check AGNI VPS state via ~/agni-workspace/. "
                    "Are priorities stale? Is dharmic-agora running? "
                    "Write deployment status to ~/.dharma/shared/agni_status.md."
                ),
                priority=1,
            ),
            AgentSpec(
                name="packager",
                role="Packaging",
                prompt=(
                    "Make ~/dharma_swarm/ installable and clean. "
                    "Check pyproject.toml, verify pip install -e . works, "
                    "ensure all imports resolve. Fix any packaging issues."
                ),
                priority=2,
            ),
            AgentSpec(
                name="cron-wirer",
                role="Automation",
                prompt=(
                    "Wire ~/dharma_swarm/dharma_swarm/pulse.py into launchd. "
                    "Create a plist that runs the pulse every 6 hours. "
                    "Test it. Write the plist to ~/.dharma/shared/pulse.plist."
                ),
                priority=3,
            ),
        ],
        reasoning="Deployment: check AGNI, package dharma_swarm, wire pulse to launchd",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# ── Available plans ──────────────────────────────────────────────────

PLANS = {
    "maintenance": plan_small_maintenance,
    "build": plan_full_build,
    "research": plan_research_deep_dive,
    "deploy": plan_deployment,
}


def auto_select_plan(state: dict) -> SwarmPlan:
    """Automatically select the best plan based on system state.

    This is the brain. It looks at what's happening and decides
    what the swarm should do next.
    """
    # If tests are failing, maintenance first
    tests = state.get("tests", "")
    if "failed" in tests.lower():
        plan = plan_small_maintenance()
        plan.reasoning = f"Tests failing ({tests}), running maintenance first"
        return plan

    # If agents are already running, don't spawn more
    if state.get("running_agents", 0) > 2:
        plan = plan_small_maintenance()
        plan.reasoning = f"{state['running_agents']} agents already running, just consolidating"
        plan.agents = [plan.agents[1]]  # only the consolidator
        return plan

    # If there's stuck work, do a full build to unstick it
    if state.get("stuck"):
        plan = plan_full_build()
        plan.reasoning = f"Stuck work detected: {state['stuck'][:100]}"
        return plan

    # If no recent agent notes exist, start fresh with full build
    if not state.get("agent_notes"):
        plan = plan_full_build()
        plan.reasoning = "No previous agent work found, starting fresh build cycle"
        return plan

    # Default: research if it's been a while, otherwise maintenance
    notes = state.get("agent_notes", {})
    if len(notes) > 3:
        # Plenty of existing work — consolidate and plan
        plan = plan_small_maintenance()
        plan.reasoning = "Existing work from previous cycles, consolidating before next push"
        return plan

    # Default to research
    plan = plan_research_deep_dive()
    plan.reasoning = "Default: research deep dive to build knowledge base"
    return plan


def run(plan_name: str | None = None) -> None:
    """Run the orchestrator: read state, pick plan, spawn agents, wait."""
    print("DHARMA SWARM Orchestrator")
    print("=" * 40)

    # Read system state
    print("\nReading system state...")
    state = read_system_state()
    print(f"  Tests: {state.get('tests', 'unknown')}")
    print(f"  Running agents: {state.get('running_agents', 0)}")
    print(f"  Agent notes: {len(state.get('agent_notes', {}))} files")
    print(f"  Ecosystem: {state.get('ecosystem_alive', '?')}/{state.get('ecosystem_total', '?')}")

    # Select plan
    if plan_name and plan_name in PLANS:
        plan = PLANS[plan_name]()
        print(f"\nPlan: {plan_name} (manual)")
    else:
        plan = auto_select_plan(state)
        print(f"\nPlan: auto-selected")
    print(f"  Reasoning: {plan.reasoning}")
    print(f"  Agents: {len(plan.agents)}")
    for a in plan.agents:
        print(f"    - {a.name} ({a.role})")

    # Spawn
    print(f"\nSpawning {len(plan.agents)} agents...")
    procs = spawn_swarm(plan)

    # Wait
    print(f"\nWaiting for agents (timeout 10min)...")
    wait_for_swarm(procs, timeout=600)

    # Summarize
    print(f"\nAll agents complete.")
    notes_count = len(list(SHARED.glob("*_notes.md"))) if SHARED.exists() else 0
    print(f"  Notes files: {notes_count}")

    # Save state
    save_state(plan, {"notes_count": notes_count})
    print(f"  State saved to {STATE_FILE}")


if __name__ == "__main__":
    plan_name = sys.argv[1] if len(sys.argv) > 1 else None
    if plan_name == "--help":
        print("Usage: python3 -m dharma_swarm.orchestrate [plan]")
        print(f"Plans: {', '.join(PLANS.keys())}")
        print("No plan = auto-select based on system state")
    else:
        run(plan_name)
