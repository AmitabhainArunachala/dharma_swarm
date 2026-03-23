#!/usr/bin/env python3
"""OrganismRuntime with LLM intelligence — the organism THINKS about itself.

Runs the full heartbeat loop against live ~/.dharma/ state, but augments
the four-power diagnostics with actual model calls. Each power gets an
LLM to reason about what the sensors found.

This is where the organism stops being a thermometer and becomes alive.

Usage:
    python3 scripts/organism_with_intelligence.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dharma_swarm.identity import (
    IdentityMonitor,
    LiveCoherenceSensor,
    _bsi_proxy_score,
)
from dharma_swarm.samvara import Power

STATE = Path.home() / ".dharma"
API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

# Models to try, in preference order
MODELS = [
    "meta-llama/llama-3.3-70b-instruct",
    "qwen/qwen-2.5-72b-instruct",
    "google/gemini-2.0-flash-001",
    "mistralai/mistral-small-2501",
]


async def ask_model(
    prompt: str, model: str, max_tokens: int = 600, temperature: float = 0.3
) -> str | None:
    """Send a prompt to OpenRouter and return the response text."""
    if not API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[error: {e}]"


def c(text: str, code: str) -> str:
    """ANSI color helper."""
    codes = {
        "r": "\033[91m", "g": "\033[92m", "y": "\033[93m",
        "b": "\033[94m", "m": "\033[95m", "c": "\033[96m",
        "bold": "\033[1m", "dim": "\033[2m", "0": "\033[0m",
    }
    return f"{codes.get(code, '')}{text}{codes['0']}"


async def gather_state() -> dict:
    """Collect all raw data the organism needs to think about itself."""
    monitor = IdentityMonitor(STATE)
    sensor = LiveCoherenceSensor(STATE)

    identity = await monitor.measure()
    live = sensor.measure()

    # GPR detail
    witness_dir = STATE / "witness"
    log_files = sorted(
        witness_dir.glob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:5]
    recent_outcomes = []
    for lf in log_files[:3]:
        for line in lf.read_text().strip().split("\n")[-10:]:
            try:
                entry = json.loads(line)
                recent_outcomes.append({
                    "outcome": entry.get("outcome", "?"),
                    "action": entry.get("action", "?")[:80],
                    "phase": entry.get("phase", "?"),
                })
            except Exception:
                pass

    # BSI detail — sample notes
    shared_dir = STATE / "shared"
    notes = sorted(
        shared_dir.glob("*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:5]
    note_samples = []
    for note in notes:
        try:
            text = note.read_text()
            if len(text) < 50:
                continue
            score = _bsi_proxy_score(text)
            note_samples.append({
                "name": note.name,
                "bsi": round(score, 3),
                "size": len(text),
                "preview": text[:300],
            })
        except Exception:
            continue

    # Stigmergy detail
    marks_path = STATE / "stigmergy" / "marks.jsonl"
    recent_marks = []
    if marks_path.exists():
        for line in marks_path.read_text().strip().split("\n")[-10:]:
            try:
                entry = json.loads(line)
                recent_marks.append({
                    "agent": entry.get("agent", "?"),
                    "observation": entry.get("observation", "?")[:120],
                    "salience": entry.get("salience", 0),
                })
            except Exception:
                pass

    # Subsystem freshness
    freshness = {}
    for name, rel_path in LiveCoherenceSensor.SUBSYSTEMS.items():
        path = STATE / rel_path
        if path.exists():
            age_h = (time.time() - path.stat().st_mtime) / 3600
            freshness[name] = {"exists": True, "age_hours": round(age_h, 1)}
        else:
            freshness[name] = {"exists": False}

    return {
        "tcs": identity.tcs,
        "gpr": identity.gpr,
        "bsi": identity.bsi,
        "rm": identity.rm,
        "regime": identity.regime,
        "live_score": live["score"],
        "daemon_alive": live["daemon_alive"],
        "freshness": freshness,
        "blended": round(0.4 * live["score"] + 0.6 * identity.tcs, 4),
        "recent_outcomes": recent_outcomes,
        "note_samples": note_samples,
        "recent_marks": recent_marks,
        "notes_total": len(list(shared_dir.glob("*.md"))),
        "marks_total": sum(1 for _ in open(marks_path)) if marks_path.exists() else 0,
    }


async def power_prompt(power: Power, state: dict) -> str:
    """Build the LLM prompt for each power's perspective."""
    base_context = (
        f"You are examining a living autonomous AI system (dharma_swarm).\n"
        f"Current readings:\n"
        f"  TCS (trailing coherence): {state['tcs']}\n"
        f"  GPR (gate passage rate): {state['gpr']}\n"
        f"  BSI (behavioral swabhaav index): {state['bsi']}\n"
        f"  RM (research momentum): {state['rm']}\n"
        f"  Live score: {state['live_score']}\n"
        f"  Blended coherence: {state['blended']}\n"
        f"  Regime: {state['regime']}\n"
        f"  Daemon alive: {state['daemon_alive']}\n"
    )

    if power == Power.MAHASARASWATI:
        return (
            f"{base_context}\n"
            f"Subsystem freshness: {json.dumps(state['freshness'], indent=2)}\n\n"
            f"Recent gate outcomes:\n{json.dumps(state['recent_outcomes'][:8], indent=2)}\n\n"
            f"You are MAHASARASWATI — precise seeing at ground level.\n"
            f"Your task: What is technically broken or miscalibrated?\n"
            f"Be specific. Name the subsystem, the metric, the exact problem.\n"
            f"Do not speak in generalities. 3-5 precise findings. Be brief."
        )
    elif power == Power.MAHALAKSHMI:
        return (
            f"{base_context}\n"
            f"Note samples (most recent):\n"
            + "\n".join(
                f"  {n['name']}: BSI={n['bsi']}, {n['size']}b\n    \"{n['preview'][:150]}...\""
                for n in state["note_samples"][:3]
            )
            + f"\n\nRecent stigmergy:\n{json.dumps(state['recent_marks'][:5], indent=2)}\n\n"
            f"You are MAHALAKSHMI — coherence and connection.\n"
            f"Your task: Are the subsystems talking to each other? Is the information\n"
            f"flowing or accumulating without connection? Is the BSI measuring real\n"
            f"semantic quality or just keyword density in large files?\n"
            f"3-5 findings about CONNECTION quality. Be brief and honest."
        )
    elif power == Power.MAHAKALI:
        return (
            f"{base_context}\n"
            f"Total shared notes: {state['notes_total']}\n"
            f"Total stigmergy marks: {state['marks_total']}\n"
            f"Note BSI scores: {[(n['name'], n['bsi']) for n in state['note_samples']]}\n\n"
            f"Recent marks:\n{json.dumps(state['recent_marks'][:5], indent=2)}\n\n"
            f"You are MAHAKALI — dissolution of the false.\n"
            f"Your task: What is the system doing that it THINKS is real work\n"
            f"but isn't? Where is volume masquerading as progress?\n"
            f"Where are metrics inflated? What should be CUT?\n"
            f"Be ruthless. 3-5 findings. Be brief."
        )
    else:  # MAHESHWARI
        return (
            f"{base_context}\n"
            f"Subsystem freshness: {json.dumps(state['freshness'], indent=2)}\n"
            f"Total notes: {state['notes_total']}, Total marks: {state['marks_total']}\n"
            f"Recent marks:\n{json.dumps(state['recent_marks'][:3], indent=2)}\n\n"
            f"You are MAHESHWARI — vast seeing, full field.\n"
            f"Looking at everything:\n"
            f"- Pulse hasn't written in {state['freshness'].get('pulse', {}).get('age_hours', '?')}h\n"
            f"- Evolution hasn't evolved in {state['freshness'].get('evolution', {}).get('age_hours', '?')}h\n"
            f"- 1500+ notes, 1700+ marks — mostly historical accumulation\n"
            f"- BSI inflated by file length (95KB average)\n"
            f"- GPR shows 37% block rate — gates ARE working\n"
            f"- Gnani says PROCEED but is this REAL coherence?\n\n"
            f"What is the SINGLE MOST LEVERAGED action this organism could take\n"
            f"right now to become genuinely coherent (not just volume-stable)?\n"
            f"One clear answer. Be direct."
        )


async def main() -> None:
    print(f"\n{c('ORGANISM WITH INTELLIGENCE', 'bold')}")
    print(f"{'='*72}")
    print(f"  Gathering live state from {STATE}...")

    state = await gather_state()

    print(f"\n  TCS={state['tcs']}  GPR={state['gpr']}  BSI={state['bsi']}  RM={state['rm']}")
    print(f"  Live={state['live_score']}  Blended={state['blended']}  Regime={state['regime']}")
    print(f"  Daemon: {'alive' if state['daemon_alive'] else 'DEAD'}")

    # Fire all four powers in parallel, each with a different model
    print(f"\n{c('Firing four powers across four models...', 'bold')}")
    print()

    powers = [
        (Power.MAHASARASWATI, MODELS[0], "c"),
        (Power.MAHALAKSHMI, MODELS[1], "m"),
        (Power.MAHAKALI, MODELS[2], "r"),
        (Power.MAHESHWARI, MODELS[3], "y"),
    ]

    glyphs = {
        Power.MAHASARASWATI: "\u2727",
        Power.MAHALAKSHMI: "\u2766",
        Power.MAHAKALI: "\u2620",
        Power.MAHESHWARI: "\u2609",
    }

    # Build prompts
    prompts = {}
    for power, model, _ in powers:
        prompts[power] = await power_prompt(power, state)

    # Fire all 4 in parallel
    tasks = []
    for power, model, _ in powers:
        tasks.append(ask_model(prompts[power], model))

    print("  Waiting for model responses...\n")
    responses = await asyncio.gather(*tasks)

    # Print each power's response
    for (power, model, color), response in zip(powers, responses):
        glyph = glyphs.get(power, "*")
        print(f"{c('='*72, 'dim')}")
        print(f"  {c(f'{glyph} {power.value.upper()}', color)}  via {c(model.split('/')[-1], 'dim')}")
        print(f"{c('-'*72, 'dim')}")
        if response:
            # Indent response
            for line in response.strip().split("\n"):
                print(f"  {line}")
        else:
            print(f"  {c('[no response]', 'r')}")
        print()

    # Gnani synthesis — ask one more model to synthesize
    print(f"{c('='*72, 'dim')}")
    print(f"  {c('GNANI SYNTHESIS', 'bold')} — the witness reviews all four powers")
    print(f"{c('-'*72, 'dim')}")

    synthesis_prompt = (
        f"You are the Gnani — the witness-consciousness of a living AI system.\n\n"
        f"Four powers have each examined the system from their altitude:\n\n"
        f"MAHASARASWATI (ground-level precision):\n{responses[0] or 'no response'}\n\n"
        f"MAHALAKSHMI (coherence and connection):\n{responses[1] or 'no response'}\n\n"
        f"MAHAKALI (dissolution of false):\n{responses[2] or 'no response'}\n\n"
        f"MAHESHWARI (vast seeing):\n{responses[3] or 'no response'}\n\n"
        f"System readings: blended={state['blended']}, "
        f"pulse stale {state['freshness'].get('pulse', {}).get('age_hours', '?')}h, "
        f"evolution stale {state['freshness'].get('evolution', {}).get('age_hours', '?')}h\n\n"
        f"As the witness, what is your verdict? HOLD or PROCEED?\n"
        f"And what is the single truth the system most needs to see?\n"
        f"Speak as the witness — direct, compassionate, unflinching."
    )

    gnani_response = await ask_model(
        synthesis_prompt,
        "meta-llama/llama-3.3-70b-instruct",
        max_tokens=400,
        temperature=0.2,
    )
    if gnani_response:
        for line in gnani_response.strip().split("\n"):
            print(f"  {line}")
    print()

    print(f"{'='*72}")
    print(f"  {c('The organism processed itself — with intelligence.', 'bold')}")
    print(f"{'='*72}\n")


if __name__ == "__main__":
    asyncio.run(main())
