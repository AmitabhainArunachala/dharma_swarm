#!/usr/bin/env python3
"""Garden Daemon — runs skill cycles through Claude Code subprocesses.

The connective tissue. Spawns `claude -p` sessions that invoke skills,
captures results, routes outputs to downstream skills, writes cycle reports.

Hybrid Sensor Pattern: ecosystem-pulse runs unconditionally as a lightweight
sensor; expensive skills (archaeology, hum, research-status) only spawn when
trigger conditions are met. Cost ledger tracks spend and enforces daily caps.

Usage:
    python garden_daemon.py                  # Run one cycle (hybrid sensor)
    python garden_daemon.py --force          # Force ALL skills regardless of triggers
    python garden_daemon.py --skill hum      # Run a single skill
    python garden_daemon.py --daemon         # Loop forever (for launchd)
"""

import asyncio
import fcntl
import json
import math
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# ── Paths ──────────────────────────────────────────────────────────
HOME = Path.home()
CLAUDE_BIN = str(HOME / ".npm-global" / "bin" / "claude")
GARDEN_DIR = HOME / ".dharma" / "garden"
SEEDS_DIR = HOME / ".dharma" / "seeds"
SUBCONSCIOUS_DIR = HOME / ".dharma" / "subconscious"
SKILLS_DIR = HOME / ".claude" / "skills"
SHARED_DIR = HOME / ".dharma" / "shared"
LOGS_DIR = HOME / ".dharma" / "logs"
COSTS_DIR = HOME / ".dharma" / "costs"
HEARTBEAT_DIR = GARDEN_DIR  # heartbeat files live alongside cycle reports

for d in [GARDEN_DIR, SEEDS_DIR, SUBCONSCIOUS_DIR, SHARED_DIR, LOGS_DIR, COSTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Cost Constants ────────────────────────────────────────────────
MODEL_COST_USD: dict[str, float] = {
    "haiku": 0.01,
    "sonnet": 0.06,
    "opus": 0.30,
}
DAILY_COST_WARN_USD = 5.0   # Above this: downgrade models to haiku
DAILY_COST_HALT_USD = 10.0  # Above this: only ecosystem-pulse runs
COST_LEDGER_PATH = COSTS_DIR / "daily_ledger.jsonl"

# ── Essential skills (never skipped by cost cap) ──────────────────
ESSENTIAL_SKILLS = {"ecosystem-pulse"}

# ── Skill Definitions ─────────────────────────────────────────────
# Each skill: name, prompt (what to tell claude -p), timeout, model, cwd

SKILLS: dict[str, dict[str, Any]] = {
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

    "curiosity-scan": {
        "name": "curiosity-scan",
        "model": "haiku",
        "timeout": 120,
        "cwd": str(HOME),
        "prompt": "Run curiosity scan: profile top 3 exploration targets from CuriosityEngine, read each file, leave enriched stigmergy marks, update FileProfiles.",
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
    "agora-pulse": {
        "name": "agora-pulse",
        "model": "haiku",
        "timeout": 120,
        "cwd": str(HOME),
        "prompt": """Check SAB Dharmic Agora health and report status.

Execute:
1. curl -sk --max-time 10 https://157.245.193.15/sab-health — parse JSON for status, version, gate_count, sparks
2. curl -sk --max-time 10 https://157.245.193.15/api/node/status — get totals (sparks, canon, compost, pending)

Write results to ~/.dharma/shared/agora_pulse.md in format:
SAB AGORA YYYY-MM-DD STATUS — summary with metrics

Where STATUS is GREEN (healthy + responding), AMBER (degraded), or RED (unreachable).
Include: version, gate count, spark count, canon count, response time.
Be extremely brief — one line plus metrics.""",
    },
}

# ── Cycle Definitions ─────────────────────────────────────────────
# Order matters: earlier skills feed later ones

FULL_CYCLE = ["ecosystem-pulse", "archaeology", "hum", "research-status", "agora-pulse"]
QUICK_CYCLE = ["ecosystem-pulse", "research-status", "agora-pulse"]

# Skills that are triggered (not the sensor)
TRIGGERED_SKILLS = ["archaeology", "hum", "research-status", "curiosity-scan"]


def _atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Persist text via replace to avoid torn state files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding=encoding,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
            tmp_name = handle.name
        Path(tmp_name).replace(path)
    finally:
        if tmp_name:
            Path(tmp_name).unlink(missing_ok=True)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write_text(path, json.dumps(payload, indent=2) + "\n")


def _append_locked_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Append text under an advisory lock and fsync before release."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding=encoding) as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


# ── Cost Ledger ──────────────────────────────────────────────────

def _parse_cost_amount(value: Any) -> float | None:
    """Coerce append-only ledger amounts without letting bad rows break cycles."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        amount = float(value)
        return amount if math.isfinite(amount) else None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            amount = float(stripped)
        except ValueError:
            return None
        return amount if math.isfinite(amount) else None
    return None

def _read_daily_total(date_str: str | None = None) -> float:
    """Sum estimated_cost_usd from the ledger for the given date (default today)."""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    total = 0.0
    if not COST_LEDGER_PATH.exists():
        return total
    try:
        for line in COST_LEDGER_PATH.read_text().strip().splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if entry.get("date") == date_str:
                    amount = _parse_cost_amount(entry.get("estimated_cost_usd"))
                    if amount is not None:
                        total += amount
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    return total


def _append_cost_entry(
    skill_key: str,
    model: str,
    elapsed: float,
    status: str,
    *,
    recorded_at: datetime | None = None,
) -> None:
    """Append a cost entry to the daily ledger using the invocation timestamp."""
    cost = MODEL_COST_USD.get(model, 0.03)  # default to a conservative estimate
    entry_time = recorded_at or datetime.now()
    entry = {
        "timestamp": entry_time.isoformat(),
        "date": entry_time.strftime("%Y-%m-%d"),
        "session_id": "garden_daemon",
        "tool": "garden_skill",
        "category": "garden",
        "estimated_cost_usd": cost,
        "agent_description": f"{skill_key} ({status}, {elapsed:.0f}s)",
        "model": model,
    }
    try:
        _append_locked_text(
            COST_LEDGER_PATH,
            json.dumps(entry, ensure_ascii=True) + "\n",
        )
    except OSError as e:
        print(f"  [WARN] Could not write cost ledger: {e}")


def _effective_model(skill_key: str, configured_model: str) -> str:
    """Downgrade model if daily spend exceeds warning threshold."""
    if skill_key in ESSENTIAL_SKILLS:
        return configured_model
    daily_total = _read_daily_total()
    if daily_total >= DAILY_COST_WARN_USD and configured_model != "haiku":
        print(f"  [COST] Daily total ${daily_total:.2f} >= ${DAILY_COST_WARN_USD:.2f}"
              f" — downgrading {skill_key} from {configured_model} to haiku")
        return "haiku"
    return configured_model


def _should_skip_for_cost(skill_key: str) -> bool:
    """Return True if the skill should be skipped due to cost cap."""
    if skill_key in ESSENTIAL_SKILLS:
        return False
    daily_total = _read_daily_total()
    if daily_total >= DAILY_COST_HALT_USD:
        print(f"  [COST] Daily total ${daily_total:.2f} >= ${DAILY_COST_HALT_USD:.2f}"
              f" — skipping non-essential skill {skill_key}")
        return True
    return False


# ── Trigger Detection (Hybrid Sensor) ────────────────────────────

def _file_age_hours(path: Path) -> float | None:
    """Return age of a file in hours, or None if it doesn't exist."""
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    return (time.time() - mtime) / 3600.0


def _no_cycle_in_24h() -> bool:
    """Return True if latest_cycle.json is missing or older than 24h."""
    latest = GARDEN_DIR / "latest_cycle.json"
    age = _file_age_hours(latest)
    return age is None or age > 24.0


def _sensor_succeeded(pulse_result: Any) -> bool:
    """Return whether the ecosystem pulse produced a usable success signal."""
    return isinstance(pulse_result, dict) and pulse_result.get("status") == "success"


def check_triggers(pulse_result: dict) -> list[str]:  # noqa: ARG001
    """Examine filesystem state and return which triggered skills should run.

    Called after ecosystem-pulse completes. Checks file ages and existence
    to determine which expensive skills need to fire this cycle.

    Args:
        pulse_result: The result dict from running ecosystem-pulse (used for
            logging context but triggers are filesystem-based, not output-parsed).

    Returns:
        List of skill keys that should run (subset of TRIGGERED_SKILLS).
    """
    if not _sensor_succeeded(pulse_result):
        status = "unknown"
        if isinstance(pulse_result, dict):
            status = str(pulse_result.get("status") or "unknown")
        print(f"\n  SENSOR FAILED ({status}) -- skipping triggered skills")
        return []

    triggered: list[str] = []
    reasons: dict[str, str] = {}

    # ── archaeology triggers ──────────────────────────────────────
    seeds_json = SEEDS_DIR / "seeds.json"
    seeds_age = _file_age_hours(seeds_json)
    if seeds_age is None:
        triggered.append("archaeology")
        reasons["archaeology"] = "seeds.json does not exist"
    elif seeds_age > 24.0:
        triggered.append("archaeology")
        reasons["archaeology"] = f"seeds.json is {seeds_age:.1f}h old (>24h)"

    # ── hum triggers ──────────────────────────────────────────────
    seeds_fresh = seeds_age is not None and seeds_age < 6.0
    dreams_jsonl = SUBCONSCIOUS_DIR / "dream_associations.jsonl"
    dreams_age = _file_age_hours(dreams_jsonl)
    if seeds_fresh:
        triggered.append("hum")
        reasons["hum"] = f"fresh seeds ({seeds_age:.1f}h old, <6h)"
    elif dreams_age is None or dreams_age > 24.0:
        triggered.append("hum")
        age_str = "does not exist" if dreams_age is None else f"{dreams_age:.1f}h old (>24h)"
        reasons["hum"] = f"dream_associations.jsonl {age_str}"

    # Additional hum triggers: curiosity + mark activity
    if "hum" not in triggered:
        # Trigger if many new marks appeared
        marks_file = Path.home() / ".dharma" / "stigmergy" / "marks.jsonl"
        if marks_file.exists():
            mark_count = sum(1 for _ in open(marks_file))
            # Check if >10 marks are recent (rough heuristic: file modified recently)
            mtime = datetime.fromtimestamp(marks_file.stat().st_mtime)
            hours_since_mod = (datetime.now() - mtime).total_seconds() / 3600
            if hours_since_mod < 2 and mark_count > 50:
                triggered.append("hum")
                reasons["hum"] = f"high mark activity ({mark_count} marks, file modified {hours_since_mod:.1f}h ago)"

    # ── research-status triggers ──────────────────────────────────
    research_md = GARDEN_DIR / "research_status.md"
    research_age = _file_age_hours(research_md)
    if research_age is None or research_age > 12.0:
        triggered.append("research-status")
        age_str = "does not exist" if research_age is None else f"{research_age:.1f}h old (>12h)"
        reasons["research-status"] = f"research_status.md {age_str}"

    # ── curiosity triggers ────────────────────────────────────────
    try:
        from dharma_swarm.curiosity import CuriosityEngine
        engine = CuriosityEngine()
        targets = engine.explore(top_n=3)
        high_curiosity = [t for t in targets if t.curiosity_score > 0.6]
        if high_curiosity:
            triggered.append("curiosity-scan")
            reasons["curiosity-scan"] = f"{len(high_curiosity)} targets above 0.6 threshold"
    except Exception:
        pass  # Curiosity engine not yet initialized

    # ── Log trigger decisions ─────────────────────────────────────
    if triggered:
        print(f"\n  TRIGGERS ({len(triggered)}/{len(TRIGGERED_SKILLS)}):")
        for skill_key in triggered:
            print(f"    [{skill_key}] {reasons[skill_key]}")
    else:
        print(f"\n  No triggers -- system stable")

    return triggered


# ── Heartbeat Protocol ───────────────────────────────────────────

def _heartbeat_path(skill_key: str) -> Path:
    """Return the heartbeat file path for a skill."""
    return HEARTBEAT_DIR / f"heartbeat_{skill_key}.json"


def _write_heartbeat(skill_key: str, status: str, started: datetime,
                     pid: int | None = None, ended: datetime | None = None) -> None:
    """Write or update a per-skill heartbeat file."""
    data: dict[str, Any] = {
        "skill": skill_key,
        "status": status,
        "started": started.isoformat(),
    }
    if pid is not None:
        data["pid"] = pid
    if ended is not None:
        data["ended"] = ended.isoformat()
        data["elapsed"] = round((ended - started).total_seconds(), 1)
    try:
        _write_json(_heartbeat_path(skill_key), data)
    except OSError as e:
        print(f"  [WARN] Could not write heartbeat for {skill_key}: {e}")


def _check_stale_heartbeat(skill_key: str) -> None:
    """Check if a previous run left a stale 'running' heartbeat (>90s old)."""
    hb_path = _heartbeat_path(skill_key)
    if not hb_path.exists():
        return
    try:
        data = json.loads(hb_path.read_text())
        if data.get("status") == "running":
            started_str = data.get("started", "")
            if started_str:
                started = datetime.fromisoformat(started_str)
                age = (datetime.now() - started).total_seconds()
                if age > 90:
                    print(f"  [WARN] Stale heartbeat detected for {skill_key}"
                          f" — started {age:.0f}s ago, proceeding anyway")
    except (json.JSONDecodeError, OSError, ValueError):
        pass


# ── Subprocess Runner ─────────────────────────────────────────────

async def run_skill(skill_key: str, model_override: str | None = None) -> dict:
    """Spawn a claude -p subprocess for a single skill.

    Args:
        skill_key: Key into the SKILLS dict.
        model_override: If set, override the skill's configured model
            (used by cost cap downgrade).

    Returns:
        Result dict with skill name, status, timing, and output preview.
    """
    skill = SKILLS[skill_key]
    name = skill["name"]
    prompt = skill["prompt"]
    timeout = skill.get("timeout", 300)
    configured_model = skill.get("model", "sonnet")
    model = model_override or _effective_model(skill_key, configured_model)
    cwd = skill.get("cwd", str(HOME))

    # 3c: Check cost cap before spawning
    if _should_skip_for_cost(skill_key):
        return {
            "skill": name,
            "key": skill_key,
            "status": "skipped-cost-cap",
            "timestamp": datetime.now().isoformat(),
        }

    # 3b: Check for stale heartbeat from a previous hung run
    _check_stale_heartbeat(skill_key)

    print(f"\n{'─'*60}")
    print(f"  GARDEN | {name}")
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

        # 3b: Write "running" heartbeat with PID
        _write_heartbeat(skill_key, "running", start, pid=proc.pid)

        stdout_bytes, _ = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )

        elapsed = (datetime.now() - start).total_seconds()
        output = stdout_bytes.decode(errors="replace")[:50_000] if stdout_bytes else ""

        status = "success" if proc.returncode == 0 else f"exit-{proc.returncode}"
        result = {
            "skill": name,
            "key": skill_key,
            "status": status,
            "elapsed": round(elapsed, 1),
            "output_len": len(output),
            "output_preview": output[:800],
            "timestamp": datetime.now().isoformat(),
            "model": model,
        }

        # 3b: Update heartbeat to completed/failed
        hb_status = "completed" if proc.returncode == 0 else "failed"
        _write_heartbeat(skill_key, hb_status, start, pid=proc.pid,
                         ended=datetime.now())

        # 3c: Record cost
        _append_cost_entry(skill_key, model, elapsed, status, recorded_at=start)

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
            "model": model,
        }
        # 3b: Update heartbeat to timeout
        _write_heartbeat(skill_key, "timeout", start,
                         pid=proc.pid if proc else None, ended=datetime.now())
        # 3c: Still record cost (the LLM ran, tokens were spent)
        _append_cost_entry(skill_key, model, elapsed, "timeout", recorded_at=start)

        print(f"  [TIMEOUT] after {elapsed:.0f}s")
        try:
            if proc is not None:
                proc.terminate()
                await proc.wait()
        except Exception:
            pass

    except Exception as e:
        result = {
            "skill": name,
            "key": skill_key,
            "status": "exception",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
            "model": model,
        }
        # 3b: Update heartbeat to failed
        _write_heartbeat(skill_key, "failed", start, ended=datetime.now())

        print(f"  [EXCEPTION] {e}")

    return result


# ── Cycle Runner ──────────────────────────────────────────────────

async def run_cycle(skill_keys: list[str] | None = None,
                    force: bool = False) -> dict:
    """Run a garden cycle. Hybrid sensor pattern by default.

    When skill_keys is None (full cycle mode):
      1. Always run ecosystem-pulse first (sensor).
      2. Call check_triggers() to determine which expensive skills to run.
      3. Only spawn triggered skills (unless force=True).

    When skill_keys is explicitly provided (e.g. QUICK_CYCLE or --skill):
      Runs exactly those skills in order (no trigger gating).

    Args:
        skill_keys: Explicit list of skills to run, or None for hybrid sensor mode.
        force: If True, run all skills regardless of triggers.

    Returns:
        Cycle report dict.
    """
    hybrid_mode = skill_keys is None
    if hybrid_mode:
        # Start with sensor only; triggered skills determined after sensor runs
        skill_keys = list(FULL_CYCLE)  # copy for reference

    cycle_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    cycle_start = datetime.now()

    # Check force_all condition: no cycle in 24h
    force_reason = ""
    if hybrid_mode and not force and _no_cycle_in_24h():
        force = True
        force_reason = "no cycle completed in 24h"

    mode_label = "HYBRID SENSOR" if hybrid_mode else "EXPLICIT"
    if force:
        mode_label = f"FORCED ({force_reason})" if force_reason else "FORCED"

    print(f"\n{'#'*60}")
    print(f"  GARDEN DAEMON -- Cycle {cycle_id}")
    print(f"  Mode: {mode_label}")
    if hybrid_mode:
        print(f"  Sensor: ecosystem-pulse (always)")
        print(f"  Candidates: {' | '.join(TRIGGERED_SKILLS)}")
    else:
        assert skill_keys is not None
        print(f"  Skills: {' -> '.join(skill_keys)}")
    print(f"  Daily cost so far: ${_read_daily_total():.2f}")
    print(f"  Started: {cycle_start.strftime('%H:%M:%S')}")
    print(f"{'#'*60}")

    results: list[dict] = []

    if hybrid_mode:
        # ── Phase 1: Run the sensor unconditionally ───────────────
        pause_file = HOME / "dharma_swarm" / ".PAUSE"
        if pause_file.exists():
            print(f"  [PAUSED] .PAUSE file detected, stopping cycle")
        elif "ecosystem-pulse" in SKILLS:
            pulse_result = await run_skill("ecosystem-pulse")
            results.append(pulse_result)

            # ── Phase 2: Determine which follow-up skills to run ──
            if force:
                triggered = list(TRIGGERED_SKILLS)
                print(f"\n  FORCE MODE: running all {len(triggered)} triggered skills")
            else:
                triggered = check_triggers(pulse_result)

            # ── Phase 3: Run triggered skills in order ────────────
            for key in FULL_CYCLE:
                if key == "ecosystem-pulse":
                    continue  # already ran
                if key not in triggered:
                    continue
                if key not in SKILLS:
                    print(f"  [SKIP] Unknown skill: {key}")
                    continue

                # Check for .PAUSE file between skills
                if pause_file.exists():
                    print(f"  [PAUSED] .PAUSE file detected, stopping cycle")
                    break

                result = await run_skill(key)
                results.append(result)
    else:
        # Explicit skill list mode (--quick or custom)
        assert skill_keys is not None
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

    # Count statuses
    successes = sum(1 for r in results if r.get("status") == "success")
    skipped = sum(1 for r in results if r.get("status", "").startswith("skipped"))

    report: dict[str, Any] = {
        "cycle_id": cycle_id,
        "started": cycle_start.isoformat(),
        "ended": cycle_end.isoformat(),
        "total_seconds": round(total, 1),
        "skills_run": len(results),
        "successes": successes,
        "skipped": skipped,
        "mode": mode_label,
        "daily_cost_usd": round(_read_daily_total(), 4),
        "results": results,
    }

    # Write reports
    report_path = GARDEN_DIR / f"cycle_{cycle_id}.json"
    _write_json(report_path, report)
    _write_json(GARDEN_DIR / "latest_cycle.json", report)

    # Write heartbeat (for supervisor / accountability check)
    heartbeat = {
        "cycle_id": cycle_id,
        "timestamp": cycle_end.isoformat(),
        "status": "completed",
        "successes": successes,
        "total_skills": len(results),
        "elapsed_seconds": round(total, 1),
    }
    heartbeat_path = SHARED_DIR / "garden_heartbeat.json"
    _write_json(heartbeat_path, heartbeat)

    print(f"\n{'#'*60}")
    print(f"  CYCLE COMPLETE -- {total:.0f}s total | ${_read_daily_total():.2f} today")
    for r in results:
        status = r.get("status", "?")
        if status == "success":
            icon = "+"
        elif status.startswith("skipped"):
            icon = "~"
        else:
            icon = "-"
        elapsed_str = f"{r.get('elapsed', '?')}s" if 'elapsed' in r else status
        print(f"  [{icon}] {r['skill']}: {status} ({elapsed_str})")
    print(f"  Report: {report_path}")
    print(f"{'#'*60}\n")

    return report


# ── Daemon Loop ───────────────────────────────────────────────────

async def daemon_loop(interval: int = 21600, force: bool = False):
    """Run cycles forever with sleep between them. For launchd use."""
    print(f"Garden Daemon starting in loop mode (interval={interval}s)")
    while True:
        hour = datetime.now().hour
        if hour in [2, 3, 4, 5]:
            print(f"  Quiet hours ({hour}:xx), sleeping...")
            await asyncio.sleep(3600)
            continue

        try:
            await run_cycle(force=force)
        except Exception as e:
            print(f"  Cycle error: {e}", file=sys.stderr)

        print(f"  Next cycle in {interval}s...")
        await asyncio.sleep(interval)


# ── CLI ───────────────────────────────────────────────────────────

async def main():
    args = sys.argv[1:]
    force = "--force" in args

    if "--daemon" in args:
        interval = 21600  # 6 hours
        for a in args:
            if a.startswith("--interval="):
                interval = int(a.split("=")[1])
        await daemon_loop(interval, force=force)

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
        # Default: hybrid sensor cycle (force if --force passed)
        await run_cycle(force=force)


if __name__ == "__main__":
    asyncio.run(main())
