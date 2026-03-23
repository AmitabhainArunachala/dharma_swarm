#!/usr/bin/env python3
"""Deep Reading Daemon — produces lodestones through deep reading, research, and synthesis.

Companion to the Garden Daemon. Runs on an 8-hour cycle (staggered from Garden's
6 hours). Spawns `claude -p` subprocesses that:
  1. Deep-read the highest-scored unread seed
  2. Research current literature related to extracted themes
  3. Synthesize a lodestone connecting contemplative, scientific, and engineering threads

Lodestones are semantically dense, grounded, cross-referenced documents that live in
~/dharma_swarm/lodestones/ and serve as the intellectual substrate for the swarm.

Usage:
    python deep_reading_daemon.py                       # Run one full cycle NOW
    python deep_reading_daemon.py --skill deep-read     # Run a single skill
    python deep_reading_daemon.py --daemon              # Loop forever (for launchd)
    python deep_reading_daemon.py --daemon --interval=14400  # Custom interval
    python deep_reading_daemon.py --once                # Alias for default (one cycle)
    python deep_reading_daemon.py --background          # Daemonize (fork to background)
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# -- Paths ---------------------------------------------------------------

HOME = Path.home()
CLAUDE_BIN = str(HOME / ".npm-global" / "bin" / "claude")
DHARMA_SWARM = HOME / "dharma_swarm"
PAUSE_FILE = DHARMA_SWARM / ".PAUSE"

# Input paths
SEEDS_FILE = HOME / ".dharma" / "seeds" / "seeds.json"

# Output paths
DEEP_READS_DIR = HOME / ".dharma" / "deep_reads"
ANNOTATIONS_DIR = DEEP_READS_DIR / "annotations"
CYCLE_REPORTS_DIR = DEEP_READS_DIR / "cycle_reports"
NEXT_READS_FILE = DEEP_READS_DIR / "next_reads.json"
LODESTONES_DIR = DHARMA_SWARM / "lodestones"
GROUNDING_DIR = LODESTONES_DIR / "grounding"
SEEDS_LODE_DIR = LODESTONES_DIR / "seeds"
LOGS_DIR = HOME / ".dharma" / "logs"
LOG_FILE = LOGS_DIR / "deep_reading.log"

for d in [ANNOTATIONS_DIR, CYCLE_REPORTS_DIR, GROUNDING_DIR, SEEDS_LODE_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# -- Logging --------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("deep_reading_daemon")

# -- Configuration ---------------------------------------------------------

CYCLE_INTERVAL = 28800  # 8 hours
QUIET_HOURS = {2, 3, 4, 5}  # UTC hours

# -- Skill Definitions -----------------------------------------------------

SKILLS = {
    "deep-read": {
        "name": "deep-read",
        "model": "opus",
        "timeout": 900,
        "cwd": str(HOME),
        "prompt": """You are the Deep Reading Daemon. Your task: find the highest-scored seed that
has NOT yet been deep-read, read it fully, and produce a structured annotation.

PROTOCOL:

1. Read ~/.dharma/seeds/seeds.json — parse the "seeds" array. Each seed has a "file" path
   and a "composite" score. Sort by composite descending.

2. Read the directory listing of ~/.dharma/deep_reads/annotations/ to find existing
   annotation files. Each annotation file is named <basename>_annotation.yaml.

3. Find the highest-scored seed whose file basename does NOT have a matching annotation.
   If ALL seeds have annotations, pick the OLDEST annotation (by file mtime) for a re-read.

4. Read the selected seed file FULLY. Do not skim. Read every line.

5. Produce a structured YAML annotation and write it to:
   ~/.dharma/deep_reads/annotations/<basename>_annotation.yaml

   The annotation MUST contain:
   ```yaml
   source_file: <full path>
   seed_score: <composite from seeds.json>
   read_date: <ISO date>
   reader: deep-reading-daemon/deep-read

   summary: |
     <3-5 sentence summary of the document's core argument>

   key_claims:
     - claim: <precise claim>
       evidence: <what supports it>
       strength: <strong/moderate/suggestive/speculative>
     # 3-7 claims

   formalisms:
     - name: <mathematical/logical structure identified>
       definition: <precise definition>
       significance: <why this matters>
     # 0-5 formalisms

   connections:
     - to: <what this connects to>
       type: <supports/extends/contradicts/isomorphic/implements>
       explanation: <how>
     # 3-7 connections (to pillars, code modules, other seeds, papers)

   themes:
     - <theme 1>
     - <theme 2>
     # 3-5 themes for research skill to pursue

   engineering_implications:
     - module: <dharma_swarm module>
       implication: <what this means for the code>
     # 1-4 implications

   quality_assessment:
     density: <1-10>
     rigor: <1-10>
     novelty: <1-10>
     actionability: <1-10>
     overall: <1-10>

   next_reads:
     - file: <path to related file>
       reason: <why read this next>
     # 3-5 tethered reads
   ```

6. Also write the next_reads list to ~/.dharma/deep_reads/next_reads.json as:
   {"source": "<file read>", "timestamp": "<ISO>", "next": [{"file": "...", "reason": "..."}]}

Be thorough. This is deep reading, not skimming. The annotation should be denser
than the source — distilled meaning. Write REAL files to disk.""",
    },

    "research": {
        "name": "research",
        "model": "sonnet",
        "timeout": 600,
        "cwd": str(HOME),
        "prompt": """You are the Deep Reading Daemon's research arm. Your task: take the latest
deep-read annotation and ground its themes in current scientific literature.

PROTOCOL:

1. List files in ~/.dharma/deep_reads/annotations/ and read the MOST RECENT
   annotation (by filename or mtime).

2. Extract the "themes", "formalisms", and "connections" sections.

3. For each theme, search the web (using WebSearch if available, otherwise use your
   training knowledge up to your cutoff) for:
   - Papers from 2024-2026 related to the theme
   - Preprints on arXiv, bioRxiv, or similar
   - Key researchers working on this
   - Existing implementations or tools

4. Find 5-10 relevant papers/sources. For each, document:
   - Title
   - Authors
   - Year
   - URL (arXiv, DOI, or project page)
   - Key findings (2-3 sentences)
   - Connection to the seed theme (1-2 sentences)

5. Write a research synthesis to:
   ~/dharma_swarm/lodestones/grounding/<topic>_research.md

   Format:
   ```markdown
   # Research Grounding: <Topic>

   **Source annotation**: <path to annotation>
   **Date**: <ISO date>
   **Researcher**: deep-reading-daemon/research

   ## Themes Investigated
   <bulleted list>

   ## Literature Findings

   ### <Paper 1 Title>
   - **Authors**: ...
   - **Year**: ...
   - **URL**: ...
   - **Key findings**: ...
   - **Connection**: ...

   ### <Paper 2 Title>
   ...

   ## Synthesis
   <2-3 paragraphs connecting the literature to the seed's core argument,
    identifying gaps, contradictions, and novel angles>

   ## Open Questions
   <3-5 questions the literature raises for our work>

   ## Engineering Relevance
   <What dharma_swarm modules or R_V metric work could use these findings>
   ```

6. Print to stdout: annotation read, number of sources found, topic name.

Be precise with citations. If you cannot verify a URL, mark it [unverified].
Write REAL files to disk.""",
    },

    "synthesize": {
        "name": "synthesize",
        "model": "opus",
        "timeout": 900,
        "cwd": str(HOME),
        "prompt": """You are the Deep Reading Daemon's synthesis engine. Your task: combine a
deep-read annotation with its research grounding to produce a LODESTONE.

A lodestone is a semantically dense, self-contained document that bridges
contemplative insight, current science, engineering implications, and
swarm intelligence. It is the intellectual gold of the system.

PROTOCOL:

1. Read the most recent annotation from ~/.dharma/deep_reads/annotations/

2. Read the most recent research synthesis from ~/dharma_swarm/lodestones/grounding/
   (match by topic if possible, otherwise most recent)

3. Read the relevant dharma_swarm modules mentioned in the annotation's
   engineering_implications section (at least skim them)

4. Read the relevant pillar document(s) from ~/dharma_swarm/foundations/
   if the annotation references any pillar

5. Create a LODESTONE. Write to:
   ~/dharma_swarm/lodestones/seeds/<topic>_lodestone.md

   A lodestone MUST be:

   **Self-contained**: Readable without needing to open other files. All necessary
   context is included inline.

   **Cited**: Every factual claim traces to a source. Format: (Source: <filename>)
   or (Ref: <paper title, year>). No unsourced assertions.

   **Connected**: Explicit cross-references to:
   - dharma_swarm code modules by filename
   - Pillar documents by number
   - R_V paper sections if relevant
   - Other lodestones if they exist

   **Dense**: High meaning-per-line ratio. No filler. No throat-clearing.
   Every paragraph carries load.

   Format:
   ```markdown
   # Lodestone: <Title>

   **Lineage**: <seed file> -> <annotation> -> <research> -> this document
   **Date**: <ISO date>
   **Synthesizer**: deep-reading-daemon/synthesize

   ## Core Insight
   <1 paragraph: the central idea in its most compressed, precise form>

   ## Contemplative Ground
   <The spiritual/contemplative dimension. What does Dada Bhagwan, Aurobindo,
    or the tradition say about this? What experiential evidence exists?>
   (Source: <specific text or teaching>)

   ## Scientific Ground
   <Current peer-reviewed or preprint science supporting or relating to this.
    Cite specific papers from the research synthesis.>
   (Ref: <paper, year>)

   ## Formal Structure
   <Mathematical or logical formalism if applicable. Equations, definitions,
    category theory, information geometry — whatever the seed contains.>

   ## Engineering Bridge
   <How this translates to code. Which dharma_swarm modules implement aspects
    of this? What's missing? What should be built?>
   - `module.py`: <what it does relevant to this>
   - Gap: <what's not yet implemented>

   ## Swarm Implications
   <What this means for multi-agent coordination, evolution, governance.
    How does this insight change how agents should behave?>

   ## Cross-References
   - Pillar: <number and name>
   - Seeds: <related seeds>
   - Code: <modules>
   - Papers: <cited works>
   - Other lodestones: <if any>

   ## Open Threads
   <What questions remain? What should the next deep-read pursue?>
   ```

6. Print to stdout: lodestone title, word count, number of citations, file path.

This is the highest-value output of the daemon. Take the full timeout if needed.
Quality over speed. Write REAL files to disk.""",
    },
}

# Cycle order: deep-read feeds research feeds synthesis
FULL_CYCLE = ["deep-read", "research", "synthesize"]


# -- Subprocess Runner -----------------------------------------------------

async def run_skill(skill_key: str) -> dict:
    """Spawn a claude -p subprocess for a single skill."""
    skill = SKILLS[skill_key]
    name = skill["name"]
    prompt = skill["prompt"]
    timeout = skill.get("timeout", 300)
    model = skill.get("model", "sonnet")
    cwd = skill.get("cwd", str(HOME))

    log.info(f"{'--'*30}")
    log.info(f"  DEEP READING | {name}")
    log.info(f"  model={model} timeout={timeout}s cwd={Path(cwd).name}")
    log.info(f"{'--'*30}")

    start = datetime.now(timezone.utc)
    proc = None

    try:
        args = [
            CLAUDE_BIN, "-p", prompt,
            "--output-format", "text",
            "--permission-mode", "bypassPermissions",
        ]
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

        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )

        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
        output = stdout_bytes.decode(errors="replace")[:50_000] if stdout_bytes else ""
        stderr_out = stderr_bytes.decode(errors="replace")[:5_000] if stderr_bytes else ""

        result = {
            "skill": name,
            "key": skill_key,
            "status": "success" if proc.returncode == 0 else f"exit-{proc.returncode}",
            "elapsed": round(elapsed, 1),
            "output_len": len(output),
            "output_preview": output[:1200],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if stderr_out and proc.returncode != 0:
            result["stderr_preview"] = stderr_out[:500]

        icon = "OK" if proc.returncode == 0 else "FAIL"
        log.info(f"  [{icon}] {elapsed:.0f}s, {len(output)} chars output")

    except asyncio.TimeoutError:
        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
        result = {
            "skill": name,
            "key": skill_key,
            "status": "timeout",
            "elapsed": round(elapsed, 1),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        log.warning(f"  [TIMEOUT] {name} after {elapsed:.0f}s")
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        log.error(f"  [EXCEPTION] {name}: {e}")

    return result


# -- Cycle Runner ----------------------------------------------------------

async def run_cycle(skill_keys: list[str] | None = None) -> dict:
    """Run a full deep-reading cycle through specified skills in order."""
    if skill_keys is None:
        skill_keys = FULL_CYCLE

    cycle_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    cycle_start = datetime.now(timezone.utc)

    log.info(f"{'##'*30}")
    log.info(f"  DEEP READING DAEMON -- Cycle {cycle_id}")
    log.info(f"  Skills: {' -> '.join(skill_keys)}")
    log.info(f"  Started: {cycle_start.strftime('%H:%M:%S UTC')}")
    log.info(f"{'##'*30}")

    results = []
    for key in skill_keys:
        if key not in SKILLS:
            log.warning(f"  [SKIP] Unknown skill: {key}")
            continue

        # Check for .PAUSE file
        if PAUSE_FILE.exists():
            log.info("  [PAUSED] .PAUSE file detected, stopping cycle")
            break

        result = await run_skill(key)
        results.append(result)

        # If a skill fails, don't proceed to downstream skills that depend on its output
        if result["status"] not in ("success",):
            log.warning(f"  [HALT] {key} did not succeed ({result['status']}), "
                        f"skipping remaining skills")
            break

    cycle_end = datetime.now(timezone.utc)
    total = (cycle_end - cycle_start).total_seconds()

    report = {
        "cycle_id": cycle_id,
        "daemon": "deep-reading",
        "started": cycle_start.isoformat(),
        "ended": cycle_end.isoformat(),
        "total_seconds": round(total, 1),
        "skills_run": len(results),
        "successes": sum(1 for r in results if r["status"] == "success"),
        "results": results,
    }

    # Write reports
    report_path = CYCLE_REPORTS_DIR / f"cycle_{cycle_id}.json"
    report_path.write_text(json.dumps(report, indent=2))
    (CYCLE_REPORTS_DIR / "latest_cycle.json").write_text(json.dumps(report, indent=2))

    log.info(f"{'##'*30}")
    log.info(f"  CYCLE COMPLETE -- {total:.0f}s total")
    for r in results:
        icon = "+" if r["status"] == "success" else "-"
        log.info(f"  [{icon}] {r['skill']}: {r['status']} ({r.get('elapsed', '?')}s)")
    log.info(f"  Report: {report_path}")
    log.info(f"{'##'*30}")

    return report


# -- Daemon Loop -----------------------------------------------------------

async def daemon_loop(interval: int = CYCLE_INTERVAL) -> None:
    """Run cycles forever with sleep between them."""
    log.info(f"Deep Reading Daemon starting in loop mode (interval={interval}s)")

    while True:
        # Check quiet hours (UTC)
        hour = datetime.now(timezone.utc).hour
        if hour in QUIET_HOURS:
            log.info(f"  Quiet hours ({hour}:xx UTC), sleeping 1h...")
            await asyncio.sleep(3600)
            continue

        # Check .PAUSE file
        if PAUSE_FILE.exists():
            log.info("  .PAUSE file present, sleeping 60s...")
            await asyncio.sleep(60)
            continue

        try:
            await run_cycle()
        except Exception as e:
            log.error(f"  Cycle error: {e}", exc_info=True)

        log.info(f"  Next cycle in {interval}s ({interval / 3600:.1f}h)...")
        await asyncio.sleep(interval)


# -- Background (daemonize) -----------------------------------------------

def daemonize() -> None:
    """Fork to background. Writes PID to ~/.dharma/deep_reading_daemon.pid."""
    pid = os.fork()
    if pid > 0:
        # Parent: print PID and exit
        pid_file = HOME / ".dharma" / "deep_reading_daemon.pid"
        pid_file.write_text(str(pid))
        print(f"Deep Reading Daemon forked to background, PID={pid}")
        print(f"PID file: {pid_file}")
        print(f"Log: {LOG_FILE}")
        sys.exit(0)
    # Child: continue to daemon_loop
    os.setsid()


# -- CLI -------------------------------------------------------------------

async def main() -> None:
    """Parse CLI args and dispatch."""
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print(__doc__)
        sys.exit(0)

    # --background: fork before anything else
    if "--background" in args:
        daemonize()
        args = [a for a in args if a != "--background"]
        # After fork, child falls through to --daemon
        if "--daemon" not in args:
            args.append("--daemon")

    if "--daemon" in args:
        interval = CYCLE_INTERVAL
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
        else:
            print("--skill requires a skill name")
            print(f"Available: {', '.join(SKILLS.keys())}")
            sys.exit(1)

    elif "--once" in args:
        await run_cycle()

    else:
        # Default: one full cycle
        await run_cycle()


if __name__ == "__main__":
    asyncio.run(main())
