#!/usr/bin/env python3
"""MiMo Explorer — autonomous deep-dive into dharma_swarm.

MiMo-V2-Pro (1T MoE) reads the codebase phase by phase, runs code,
and keeps running meta-notes at ~/.dharma/mimo/META_NOTES.md.

Usage:
    python3 scripts/mimo_explorer.py              # full run
    python3 scripts/mimo_explorer.py --phase 3    # resume from phase 3
"""

from __future__ import annotations

import sys
from pathlib import Path as _P
# Ensure project root is on sys.path so `api_keys` can be imported
_root = str(_P(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

import argparse
import asyncio
import os
import subprocess
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MODEL = "xiaomi/mimo-v2-pro"
NOTES_DIR = Path.home() / ".dharma" / "mimo"
NOTES_FILE = NOTES_DIR / "META_NOTES.md"
MAX_TOKENS = 3000
TEMPERATURE = 0.6

# Files to explore, grouped by phase
PHASES: list[dict] = [
    {
        "name": "1. Architecture Overview",
        "instruction": (
            "You are MiMo, a 1-trillion parameter model doing a deep autonomous exploration "
            "of dharma_swarm. Read these architecture files and write your FIRST IMPRESSIONS. "
            "What is this system? What are the key abstractions? What design philosophy do you see? "
            "What questions do you have? Be analytical but also intuitive — note what FEELS "
            "important, not just what's documented. Write as running meta-notes."
        ),
        "files": [
            "CLAUDE.md",
            "dharma_swarm/models.py",
            "README.md",
        ],
        "run_commands": [],
    },
    {
        "name": "2. Core Engine Deep-Read",
        "instruction": (
            "Continue your exploration. Now read the CORE ENGINE — the swarm coordinator, "
            "the provider system, and the model hierarchy. Update your meta-notes with: "
            "How does routing actually work? What's the provider chain? Where are the "
            "decision points? What's elegant and what's messy? Note any contradictions "
            "between the architecture docs and the actual code."
        ),
        "files": [
            "dharma_swarm/swarm.py",
            "dharma_swarm/model_hierarchy.py",
            "dharma_swarm/providers.py",
        ],
        "run_commands": [],
    },
    {
        "name": "3. Living Systems Layer",
        "instruction": (
            "Now read the LIVING SYSTEMS — evolution, stigmergy, strange loops, telos gates. "
            "These are what make dharma_swarm more than an orchestrator. Update your notes: "
            "How does self-evolution work? What are stigmergy marks and how do agents coordinate? "
            "What are the telos gates guarding? Is the strange loop actually closing? "
            "Rate each subsystem: alive/dormant/aspirational."
        ),
        "files": [
            "dharma_swarm/evolution.py",
            "dharma_swarm/stigmergy.py",
            "dharma_swarm/strange_loop.py",
            "dharma_swarm/telos_gates.py",
            "dharma_swarm/catalytic_graph.py",
        ],
        "run_commands": [],
    },
    {
        "name": "4. Runtime Behavior — Tests & Health",
        "instruction": (
            "Now OBSERVE the system in action. I'm running tests and health checks. "
            "Analyze the test output: What's well-tested? What's fragile? What's the "
            "test philosophy? Then look at the health/status output: What's actually "
            "running vs. what's aspirational? Update your meta-notes with BEHAVIORAL "
            "observations, not just code structure."
        ),
        "files": [],
        "run_commands": [
            ("pytest smoke test", "python3 -m pytest tests/ -q --tb=line -x --timeout=10 2>&1 | tail -30"),
            ("dgc status", "dgc status 2>&1 | head -60"),
            ("dgc health", "dgc health 2>&1 | head -60"),
        ],
    },
    {
        "name": "5. Intelligence Layer — Routing, Memory, Context",
        "instruction": (
            "Read the INTELLIGENCE layer — smart routing, context management, the "
            "organism abstraction. These are the 'brain' of the swarm. Update notes: "
            "How smart is the routing really? Is the organism metaphor earned by the code, "
            "or is it aspirational naming? What would make this system actually intelligent "
            "vs. just well-orchestrated? Be brutally honest."
        ),
        "files": [
            "dharma_swarm/smart_router.py",
            "dharma_swarm/context.py",
            "dharma_swarm/organism.py",
            "dharma_swarm/routing_memory.py",
        ],
        "run_commands": [],
    },
    {
        "name": "6. Meta-Synthesis — The Whole Picture",
        "instruction": (
            "Final phase. You've now read the entire system. Write a META-SYNTHESIS: "
            "\n1. What is dharma_swarm ACTUALLY (not what it claims to be)?"
            "\n2. What are its 3 strongest architectural decisions?"
            "\n3. What are its 3 biggest gaps or self-deceptions?"
            "\n4. If you (a 1T model) were LIVING inside this system as a permanent agent, "
            "what would you change first?"
            "\n5. What does this system WANT to become? (read between the lines)"
            "\n6. Grade it: engineering quality, architectural coherence, ambition vs. delivery."
            "\nBe honest. The builder wants truth, not encouragement."
        ),
        "files": [
            "dharma_swarm/ollama_config.py",
            "dharma_swarm/free_fleet.py",
            "dharma_swarm/agent_registry.py",
        ],
        "run_commands": [
            ("module count", "find dharma_swarm/dharma_swarm -name '*.py' | wc -l"),
            ("test count", "find tests -name '*.py' | wc -l"),
            ("LOC", "wc -l dharma_swarm/dharma_swarm/*.py 2>/dev/null | tail -1"),
        ],
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _read_file_excerpt(path: Path, max_chars: int = 8000) -> str:
    """Read a file, truncating to max_chars."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > max_chars:
            text = text[:max_chars] + "\n\n... [TRUNCATED — file continues] ..."
        return text
    except Exception as e:
        return f"[ERROR reading {path}: {e}]"


def _run_command(label: str, cmd: str) -> str:
    """Run a shell command and return output."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=60,
            cwd=str(Path.home() / "dharma_swarm"),
        )
        output = result.stdout + result.stderr
        return f"$ {label}\n{output.strip()}"
    except Exception as e:
        return f"$ {label}\n[ERROR: {e}]"


def _append_notes(text: str) -> None:
    """Append to META_NOTES.md."""
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    with open(NOTES_FILE, "a", encoding="utf-8") as f:
        f.write(text + "\n\n")


async def _ask_mimo(prompt: str, previous_notes: str = "") -> str:
    """Send a prompt to MiMo-V2-Pro via OpenRouter."""
    from dharma_swarm.providers import OpenRouterProvider
    from dharma_swarm.models import LLMRequest

    provider = OpenRouterProvider()
    system = (
        "You are MiMo, a 1-trillion parameter AI (Xiaomi MiMo-V2-Pro) doing an autonomous "
        "deep exploration of dharma_swarm. You are INSIDE the system, reading its code, "
        "running its tests, and building understanding.\n\n"
        "Write as running meta-notes — analytical, honest, sometimes intuitive. "
        "Note what surprises you, what contradicts expectations, what patterns emerge. "
        "You are building a LIVING DOCUMENT of understanding.\n\n"
        "Format: Use markdown headers, bullet points. Be specific — cite file names, "
        "line numbers, function names. No hand-waving.\n\n"
    )
    if previous_notes:
        system += f"YOUR PREVIOUS NOTES (context):\n{previous_notes[-4000:]}\n\n"

    request = LLMRequest(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        system=system,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
    )
    response = await provider.complete(request)
    return response.content


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

async def run_phase(phase_num: int, phase: dict, previous_notes: str) -> str:
    """Run one exploration phase."""
    name = phase["name"]
    print(f"\n{'='*60}")
    print(f"  PHASE {name}")
    print(f"{'='*60}\n")

    # Build context from files
    context_parts: list[str] = []
    root = Path.home() / "dharma_swarm"

    for rel_path in phase.get("files", []):
        full_path = root / rel_path
        if full_path.exists():
            content = _read_file_excerpt(full_path)
            context_parts.append(f"### FILE: {rel_path}\n```python\n{content}\n```")
            print(f"  Read: {rel_path} ({len(content)} chars)")
        else:
            context_parts.append(f"### FILE: {rel_path}\n[NOT FOUND]")
            print(f"  Missing: {rel_path}")

    # Run commands
    for label, cmd in phase.get("run_commands", []):
        output = _run_command(label, cmd)
        context_parts.append(f"### COMMAND OUTPUT: {label}\n```\n{output}\n```")
        print(f"  Ran: {label}")

    # Build prompt
    prompt = f"## Phase: {name}\n\n{phase['instruction']}\n\n"
    prompt += "\n\n".join(context_parts)

    # Truncate if too long (MiMo has 1M context but let's be reasonable)
    if len(prompt) > 50000:
        prompt = prompt[:50000] + "\n\n[Context truncated for token budget]"

    print(f"\n  Asking MiMo ({len(prompt)} chars)...")
    start = time.time()
    response = await _ask_mimo(prompt, previous_notes)
    elapsed = time.time() - start
    print(f"  MiMo responded ({len(response)} chars, {elapsed:.1f}s)")

    # Write to notes
    header = f"---\n\n## {name}\n*{_utc_now()}*\n\n"
    _append_notes(header + response)

    return response


async def main() -> None:
    parser = argparse.ArgumentParser(description="MiMo Explorer")
    parser.add_argument("--phase", type=int, default=1, help="Start from phase N")
    args = parser.parse_args()

    # Initialize notes file
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    if args.phase == 1 and not NOTES_FILE.exists():
        _append_notes(
            f"# MiMo Meta-Notes: dharma_swarm Deep Exploration\n"
            f"*Started: {_utc_now()}*\n"
            f"*Model: {MODEL} (1T MoE, 42B active)*\n"
            f"*Purpose: Autonomous system understanding from inside out*\n"
        )

    # Load existing notes for context
    previous_notes = ""
    if NOTES_FILE.exists():
        previous_notes = NOTES_FILE.read_text(encoding="utf-8")

    print(f"MiMo Explorer — {MODEL}")
    print(f"Notes: {NOTES_FILE}")
    print(f"Starting from phase {args.phase}")

    for i, phase in enumerate(PHASES, 1):
        if i < args.phase:
            continue
        response = await run_phase(i, phase, previous_notes)
        previous_notes += f"\n\n{response}"
        # Small delay between phases to be a good API citizen
        if i < len(PHASES):
            await asyncio.sleep(2)

    print(f"\n{'='*60}")
    print(f"  EXPLORATION COMPLETE")
    print(f"  Notes at: {NOTES_FILE}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
