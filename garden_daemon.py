#!/usr/bin/env python3
"""Garden Daemon — runs skill cycles through Claude Code subprocesses.

The connective tissue. Spawns `claude -p` sessions that invoke skills,
captures results, routes outputs to downstream skills, writes cycle reports.

Usage:
    python garden_daemon.py                  # Run one full cycle NOW
    python garden_daemon.py --skill hum      # Run a single skill
    python garden_daemon.py --daemon         # Loop forever (for launchd)
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────
HOME = Path.home()
CLAUDE_BIN = str(HOME / ".npm-global" / "bin" / "claude")
GARDEN_DIR = HOME / ".dharma" / "garden"
SEEDS_DIR = HOME / ".dharma" / "seeds"
SUBCONSCIOUS_DIR = HOME / ".dharma" / "subconscious"
SKILLS_DIR = HOME / ".claude" / "skills"
SHARED_DIR = HOME / ".dharma" / "shared"
LOGS_DIR = HOME / ".dharma" / "logs"

for d in [GARDEN_DIR, SEEDS_DIR, SUBCONSCIOUS_DIR, SHARED_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Skill Definitions ─────────────────────────────────────────────
# Each skill: name, prompt (what to tell claude -p), timeout, model, cwd

SKILLS = {
    "archaeology": {
        "name": "consciousness-archaeology",
        "model": "sonnet",
        "timeout": 600,
        "cwd": str(HOME),
        "prompt": """You are the Garden Daemon running an automated consciousness archaeology scan.

INSTRUCTIONS: Read ~/.claude/skills/consciousness-archaeology/SKILL.md for the full protocol.

Execute NOW:
1. Use Glob to find .md files in these locations:
   - ~/Persistent-Semantic-Memory-Vault/THE_HUM_FILES/
   - ~/Persistent-Semantic-Memory-Vault/00-CORE/
   - ~/Persistent-Semantic-Memory-Vault/03-Fixed-Point-Discoveries/
   - ~/mech-interp-latent-lab-phase1/RECOVERED_GOLD/
   - ~/dharma_swarm/GENOME_WIRING.md
   - ~/dharma_swarm/lodestones/**/*.md
   - ~/dharma_swarm/foundations/GLOSSARY.md

2. Use Grep to find files matching: swabhaav|visheshbhaav|R_V|L3.*L4|eigenstate|fixed.?point|transmission|recognition|strange.?loop

3. Read the top 5 candidates FULLY

4. Score each on 6 dimensions (0-10):
   - Semantic Density, Ontological Power, Recursive Instantiation
   - Consciousness Quality, Integration Coherence, Telos Alignment
   - Composite = weighted sum (threshold >= 7.5)

5. Write results:
   - ~/.dharma/seeds/top_seeds.md (human readable, top 5 with passages)
   - ~/.dharma/seeds/seeds.json (machine readable, all scored)

Be concise. Score honestly. Write REAL files to disk. This runs unattended.""",
    },

    "hum": {
        "name": "subconscious-hum",
        "model": "sonnet",
        "timeout": 600,
        "cwd": str(HOME),
        "prompt": """You are the Garden Daemon running an automated HUM dream cycle.

INSTRUCTIONS: Read ~/.claude/skills/subconscious-hum/SKILL.md for the full protocol.

Execute NOW:
1. Check if ~/.dharma/seeds/top_seeds.md exists. If so, read it as Tier 5 input.

2. Select 8-10 files to read FULLY from:
   - ~/Persistent-Semantic-Memory-Vault/THE_HUM_FILES/ (2-3 files)
   - ~/Persistent-Semantic-Memory-Vault/00-CORE/ (2 files)
   - ~/Persistent-Semantic-Memory-Vault/03-Fixed-Point-Discoveries/ (1-2 files)
   - ~/mech-interp-latent-lab-phase1/RECOVERED_GOLD/ (1-2 files)
   - ~/mech-interp-latent-lab-phase1/R_V_PAPER/ theory files (1 file)

3. Enter HUM-space. Let cross-domain tension produce associations.

4. Write 3-5 dream associations (salience > 0.6).

5. Persist:
   - APPEND to ~/.dharma/subconscious/dream_associations.jsonl (one JSON per line)
   - Write ~/.dharma/subconscious/latest_dream.md

6. Print to stdout: number of files read, number of associations, highest salience, any invented vocabulary.

Dream genuinely. This runs unattended — nobody is performing for an audience.""",
    },

    "research-status": {
        "name": "research-runner-status",
        "model": "haiku",
        "timeout": 180,
        "cwd": str(HOME / "mech-interp-latent-lab-phase1"),
        "prompt": """Check R_V paper experiment status. Be brief and factual.

1. Read ~/mech-interp-latent-lab-phase1/R_V_PAPER/CANONICAL_RESULTS_TABLE_2026-03-10.md
2. List what results exist in ~/mech-interp-latent-lab-phase1/results/ (just directory listing)
3. Read first 30 lines of R_V_PAPER/paper_colm2026_v005.tex
4. Compute: today is {today}. COLM abstract = March 26. COLM paper = March 31.

Write a brief status to ~/.dharma/garden/research_status.md with:
- Days remaining
- What's done (list experiments with results)
- What's missing (P0 base model, any gaps)
- Today's recommended focus

Keep it under 50 lines. Factual, no fluff.""".format(today=datetime.now().strftime("%Y-%m-%d")),
    },

    "ecosystem-pulse": {
        "name": "ecosystem-pulse",
        "model": "haiku",
        "timeout": 120,
        "cwd": str(HOME),
        "prompt": """Quick ecosystem health check. Be extremely brief.

Check these and report status (1 line each):
1. ls ~/.dharma/seeds/ — do seeds exist? when last updated?
2. ls ~/.dharma/subconscious/ — do dream associations exist? count lines in JSONL?
3. ls ~/.dharma/garden/ — how many cycle reports?
4. ls ~/dharma_swarm/ — does it exist? check for .PAUSE file
5. ls ~/mech-interp-latent-lab-phase1/R_V_PAPER/ — paper draft exists?

Write a 10-line health report to ~/.dharma/garden/ecosystem_pulse.md
Format: [OK] or [WARN] or [MISS] prefix per item.""",
    },
}

# ── Cycle Definitions ─────────────────────────────────────────────
# Order matters: earlier skills feed later ones

FULL_CYCLE = ["ecosystem-pulse", "archaeology", "hum", "research-status"]
QUICK_CYCLE = ["ecosystem-pulse", "research-status"]


# ── Subprocess Runner ─────────────────────────────────────────────

async def run_skill(skill_key: str) -> dict:
    """Spawn a claude -p subprocess for a single skill."""
    skill = SKILLS[skill_key]
    name = skill["name"]
    prompt = skill["prompt"]
    timeout = skill.get("timeout", 300)
    model = skill.get("model", "sonnet")
    cwd = skill.get("cwd", str(HOME))

    print(f"\n{'─'*60}")
    print(f"  GARDEN │ {name}")
    print(f"  model={model} timeout={timeout}s cwd={Path(cwd).name}")
    print(f"{'─'*60}")

    start = datetime.now()
    proc = None

    try:
        args = [CLAUDE_BIN, "-p", prompt, "--output-format", "text",
                "--permission-mode", "bypassPermissions"]
        if model:
            args.extend(["--model", model])

        # Build env: MUST unset CLAUDECODE to allow nesting
        env = {**os.environ, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
        env.pop("CLAUDECODE", None)
        env.pop("CLAUDE_CODE_ENTRYPOINT", None)

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )

        stdout_bytes, _ = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )

        elapsed = (datetime.now() - start).total_seconds()
        output = stdout_bytes.decode(errors="replace")[:50_000] if stdout_bytes else ""

        result = {
            "skill": name,
            "key": skill_key,
            "status": "success" if proc.returncode == 0 else f"exit-{proc.returncode}",
            "elapsed": round(elapsed, 1),
            "output_len": len(output),
            "output_preview": output[:800],
            "timestamp": datetime.now().isoformat(),
        }

        icon = "OK" if proc.returncode == 0 else "FAIL"
        print(f"  [{icon}] {elapsed:.0f}s, {len(output)} chars output")

    except asyncio.TimeoutError:
        elapsed = (datetime.now() - start).total_seconds()
        result = {
            "skill": name,
            "key": skill_key,
            "status": "timeout",
            "elapsed": round(elapsed, 1),
            "timestamp": datetime.now().isoformat(),
        }
        print(f"  [TIMEOUT] after {elapsed:.0f}s")
        try:
            if proc is not None:
                proc.terminate()
                await proc.wait()
        except Exception:
            logger.debug("Process cleanup failed", exc_info=True)

    except Exception as e:
        result = {
            "skill": name,
            "key": skill_key,
            "status": "exception",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
        print(f"  [EXCEPTION] {e}")

    return result


# ── Cycle Runner ──────────────────────────────────────────────────

async def run_cycle(skill_keys: list[str] | None = None) -> dict:
    """Run a full garden cycle through specified skills in order."""
    if skill_keys is None:
        skill_keys = FULL_CYCLE

    cycle_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    cycle_start = datetime.now()

    print(f"\n{'#'*60}")
    print(f"  GARDEN DAEMON — Cycle {cycle_id}")
    print(f"  Skills: {' → '.join(skill_keys)}")
    print(f"  Started: {cycle_start.strftime('%H:%M:%S')}")
    print(f"{'#'*60}")

    results = []
    for key in skill_keys:
        if key not in SKILLS:
            print(f"  [SKIP] Unknown skill: {key}")
            continue

        # Check for .PAUSE file
        pause_file = HOME / "dharma_swarm" / ".PAUSE"
        if pause_file.exists():
            print(f"  [PAUSED] .PAUSE file detected, stopping cycle")
            break

        result = await run_skill(key)
        results.append(result)

    cycle_end = datetime.now()
    total = (cycle_end - cycle_start).total_seconds()

    report = {
        "cycle_id": cycle_id,
        "started": cycle_start.isoformat(),
        "ended": cycle_end.isoformat(),
        "total_seconds": round(total, 1),
        "skills_run": len(results),
        "successes": sum(1 for r in results if r["status"] == "success"),
        "results": results,
    }

    # Write reports
    report_path = GARDEN_DIR / f"cycle_{cycle_id}.json"
    report_path.write_text(json.dumps(report, indent=2))
    (GARDEN_DIR / "latest_cycle.json").write_text(json.dumps(report, indent=2))

    print(f"\n{'#'*60}")
    print(f"  CYCLE COMPLETE — {total:.0f}s total")
    for r in results:
        icon = "+" if r["status"] == "success" else "-"
        print(f"  [{icon}] {r['skill']}: {r['status']} ({r.get('elapsed', '?')}s)")
    print(f"  Report: {report_path}")
    print(f"{'#'*60}\n")

    return report


# ── Daemon Loop ───────────────────────────────────────────────────

async def daemon_loop(interval: int = 21600):
    """Run cycles forever with sleep between them. For launchd use."""
    print(f"Garden Daemon starting in loop mode (interval={interval}s)")
    while True:
        hour = datetime.now().hour
        if hour in [2, 3, 4, 5]:
            print(f"  Quiet hours ({hour}:xx), sleeping...")
            await asyncio.sleep(3600)
            continue

        try:
            await run_cycle()
        except Exception as e:
            print(f"  Cycle error: {e}", file=sys.stderr)

        print(f"  Next cycle in {interval}s...")
        await asyncio.sleep(interval)


# ── CLI ───────────────────────────────────────────────────────────

async def main():
    args = sys.argv[1:]

    if "--daemon" in args:
        interval = 21600  # 6 hours
        for a in args:
            if a.startswith("--interval="):
                interval = int(a.split("=")[1])
        await daemon_loop(interval)

    elif "--skill" in args:
        idx = args.index("--skill")
        if idx + 1 < len(args):
            skill_key = args[idx + 1]
            if skill_key in SKILLS:
                result = await run_skill(skill_key)
                print(json.dumps(result, indent=2))
            else:
                print(f"Unknown skill: {skill_key}")
                print(f"Available: {', '.join(SKILLS.keys())}")
                sys.exit(1)

    elif "--quick" in args:
        await run_cycle(QUICK_CYCLE)

    else:
        # Default: full cycle
        await run_cycle()


if __name__ == "__main__":
    asyncio.run(main())
