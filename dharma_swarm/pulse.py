"""DGC Pulse v2 — dharma_swarm daemon wrapping Claude Code headless.

The key insight: `claude -p` IS a real agent (tools, file access, bash).
dharma_swarm API calls are NOT. So we use dharma_swarm for:
  - Daemon scheduling (Garden Daemon heartbeat, quiet hours, rate limits)
  - Thread rotation (mechanistic/phenomenological/architectural/alignment/scaling)
  - Circuit breaker (3 failures → pause, downtrend → switch thread)
  - Telos gates (check prompt before sending)
  - Memory persistence (log results to strange loop)
  - Human overrides (.PAUSE, .FOCUS, .INJECT)
And `claude -p` for actual execution.

Usage:
  python3 -m dharma_swarm.pulse              # Single pulse
  python3 -m dharma_swarm.pulse --daemon     # Continuous (Garden Daemon cycle)
  python3 -m dharma_swarm.pulse --status     # Check state
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dharma_swarm.context import (
    read_agni_state,
    read_manifest,
    read_memory_context,
    read_trishula_inbox,
)
from dharma_swarm.daemon_config import DaemonConfig, THREAD_PROMPTS, V7_BASE_RULES
from dharma_swarm.thread_manager import ThreadManager
from dharma_swarm.telos_gates import DEFAULT_GATEKEEPER

logger = logging.getLogger(__name__)

HOME = Path.home()
DGC = HOME / "dgc-core"
STATE_DIR = HOME / ".dharma"


def build_prompt(
    thread: str,
    thread_prompt: str,
    agni_state: dict,
    memory_ctx: str,
    trishula_ctx: str,
    manifest_ctx: str,
    inject: str | None = None,
) -> str:
    """Build the pulse prompt with v7 rules and thread context."""
    now = datetime.now(timezone.utc)

    prompt = f"""You are DGC Pulse v2 — the autonomous heartbeat of Dhyana's system.
Time: {now.isoformat()}
Active thread: {thread}

{V7_BASE_RULES}

## Current Research Thread: {thread}
{thread_prompt}

## AGNI VPS State
{json.dumps(agni_state, indent=2)[:800]}

## Trishula Inbox
{trishula_ctx}

## Recent Memories
{memory_ctx}

## Ecosystem
{manifest_ctx}
"""

    if inject:
        prompt += f"\n## INJECTED FOCUS\n{inject}\n"

    prompt += """
## Your Task
1. Check if AGNI state is stale (PRIORITIES > 48h = stale)
2. Check trishula inbox for anything needing attention
3. Based on the active research thread, identify one concrete next action
4. If nothing needs action, log a witness observation about the system state

## Rules
- Do NOT create files unless necessary
- Do NOT push to VPS — sync daemons handle it
- Log observations to ~/dgc-core/memory/witness/
- Be brief. Be real. No theater.
- SILENCE IS VALID — if nothing needs doing, say so in one sentence.
"""
    return prompt


def run_claude_headless(prompt: str, timeout: int = 120) -> str:
    """Run Claude Code in headless mode — the REAL agent."""
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text"],
            capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"},
        )
        if result.returncode == 0:
            return result.stdout[:5000]
        return f"Error (rc={result.returncode}): {result.stderr[:500]}"
    except subprocess.TimeoutExpired:
        return "TIMEOUT: Claude Code exceeded limit"
    except FileNotFoundError:
        return "ERROR: claude CLI not found in PATH"
    except Exception as e:
        return f"ERROR: {e}"


async def _store_pulse_result(result: str, thread: str) -> None:
    """Store pulse result in dharma_swarm memory."""
    try:
        from dharma_swarm.memory import StrangeLoopMemory
        from dharma_swarm.models import MemoryLayer

        db_path = STATE_DIR / "db" / "memory.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        mem = StrangeLoopMemory(db_path)
        await mem.init_db()
        await mem.remember(
            f"[pulse:{thread}] {result[:500]}",
            layer=MemoryLayer.WITNESS,
            source="pulse",
            tags=["pulse", thread],
        )
        await mem.close()
    except Exception as e:
        logger.warning("Failed to store pulse result: %s", e)


def pulse(config: DaemonConfig | None = None) -> str:
    """Execute one pulse cycle with full daemon infrastructure."""
    cfg = config or DaemonConfig()

    # Init state dir
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / "db").mkdir(exist_ok=True)

    # Thread manager
    tm = ThreadManager(cfg, STATE_DIR)

    # Check human overrides
    pause_path = STATE_DIR / cfg.pause_file
    if pause_path.exists():
        return "PAUSED: .PAUSE file exists"

    focus = tm.check_focus_override(STATE_DIR)
    if focus:
        tm._current_thread = focus

    inject = tm.check_inject_override(STATE_DIR)

    # Check quiet hours
    if datetime.now().hour in cfg.quiet_hours:
        return f"QUIET: Hour {datetime.now().hour} is in quiet hours"

    # Check circuit breaker
    if cfg.circuit_breaker.is_broken:
        return "CIRCUIT BREAKER: Too many consecutive failures"

    # Gather context
    thread = tm.current_thread
    thread_prompt = THREAD_PROMPTS.get(thread, "")
    agni_state = read_agni_state()
    memory_ctx = read_memory_context()
    trishula_ctx = read_trishula_inbox()
    manifest_ctx = read_manifest()

    # Build prompt
    prompt = build_prompt(
        thread=thread,
        thread_prompt=thread_prompt,
        agni_state=agni_state,
        memory_ctx=memory_ctx,
        trishula_ctx=trishula_ctx,
        manifest_ctx=manifest_ctx,
        inject=inject,
    )

    # Telos gate check
    gate_result = DEFAULT_GATEKEEPER.check(action="pulse", content=prompt[:2000])
    if gate_result.decision.value == "block":
        return f"TELOS BLOCK: {gate_result.reason}"

    # Execute via Claude Code headless
    print(f"[pulse] Thread: {thread} | Executing...")
    result = run_claude_headless(prompt)

    # Record
    tm.record_contribution()
    if result.startswith("ERROR") or result.startswith("TIMEOUT"):
        tripped = cfg.circuit_breaker.record_failure()
        if tripped:
            print("[pulse] Circuit breaker tripped! Rotating thread.")
            tm.rotate()
    else:
        cfg.circuit_breaker.record_success()

    # Store in memory (async)
    asyncio.run(_store_pulse_result(result, thread))

    # Log to pulse log
    log_path = STATE_DIR / "pulse.log"
    with open(log_path, "a") as f:
        f.write(f"\n--- PULSE @ {datetime.now(timezone.utc).isoformat()} [{thread}] ---\n")
        f.write(f"{result[:500]}\n")

    # Rotate thread for next pulse
    tm.rotate()

    return result


def daemon_loop(config: DaemonConfig | None = None):
    """Run continuous pulse loop with Garden Daemon parameters."""
    cfg = config or DaemonConfig()
    interval = int(cfg.heartbeat_interval)
    max_daily = cfg.max_daily_contributions
    daily_count = 0
    last_date = datetime.now().date()

    print(f"DGC Pulse v2 daemon starting.")
    print(f"  Heartbeat: {interval}s ({interval/3600:.1f}h)")
    print(f"  Max daily: {max_daily}")
    print(f"  Quiet hours: {cfg.quiet_hours}")
    print(f"  Threads: {cfg.threads}")

    while True:
        now = datetime.now()

        # Reset daily counter
        if now.date() != last_date:
            daily_count = 0
            last_date = now.date()

        # Rate limit
        if daily_count >= max_daily:
            print(f"[{now.isoformat()[:19]}] Daily limit ({max_daily}) reached. Sleeping.")
            time.sleep(3600)
            continue

        try:
            print(f"\n[{now.isoformat()[:19]}] Pulsing... (#{daily_count + 1}/{max_daily})")
            result = pulse(cfg)
            if not result.startswith(("PAUSED", "QUIET", "CIRCUIT")):
                daily_count += 1
            print(f"Result: {result[:200]}")
        except Exception as e:
            print(f"Pulse error: {e}")

        time.sleep(interval)


def show_status():
    """Show pulse status from dharma_swarm state."""
    log_path = STATE_DIR / "pulse.log"
    if not log_path.exists():
        print("No pulse log yet.")
        return

    # Show last 3 entries
    content = log_path.read_text()
    entries = content.split("--- PULSE @")
    if len(entries) <= 1:
        print("No pulses recorded yet.")
        return

    print(f"Total pulse entries: {len(entries) - 1}")
    for entry in entries[-3:]:
        if entry.strip():
            print(f"--- PULSE @{entry[:300]}")

    # Thread state
    try:
        cfg = DaemonConfig()
        tm = ThreadManager(cfg, STATE_DIR)
        stats = tm.stats()
        print(f"\nCurrent thread: {stats['current_thread']}")
        print(f"Contributions: {stats['contributions']}")
    except Exception:
        pass


if __name__ == "__main__":
    if "--daemon" in sys.argv:
        daemon_loop()
    elif "--status" in sys.argv:
        show_status()
    elif "--swarm" in sys.argv:
        # Spawn a full swarm instead of a single pulse
        from dharma_swarm.orchestrate import run
        plan = sys.argv[sys.argv.index("--swarm") + 1] if len(sys.argv) > sys.argv.index("--swarm") + 1 else None
        run(plan)
    else:
        result = pulse()
        print(result)
