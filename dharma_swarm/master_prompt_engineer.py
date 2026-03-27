"""Master Prompt Engineer -- 3-Layer Meta-Prompt for System Evolution.

Generates evolved prompts based on current system state, gaps, and telos.
The output prompt is fed back into the system for next evolution cycle.

Three layers:
  GRANULAR  -- Specific file paths, line numbers, exact fixes
  META      -- Pattern recognition across cycles, trajectory analysis
  QUALITY   -- Anti-myopia checks, diversity enforcement, loop detection
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

# COLM 2026 deadlines
_COLM_ABSTRACT_DATE = date(2026, 3, 26)
_COLM_PAPER_DATE = date(2026, 3, 31)


def _days_to_colm() -> tuple[int, int]:
    """Return (days_to_abstract, days_to_paper) from today."""
    today = date.today()
    return (
        max(0, (_COLM_ABSTRACT_DATE - today).days),
        max(0, (_COLM_PAPER_DATE - today).days),
    )

_STATE_DIR = Path.home() / ".dharma"
_SHARED_DIR = _STATE_DIR / "shared"
_HISTORY_FILE = _STATE_DIR / "prompt_evolution_history.jsonl"


# ---------------------------------------------------------------------------
# Layer definitions
# ---------------------------------------------------------------------------

_GRANULAR_LAYER = """## LAYER 1: GRANULAR (Builder)

You have direct access to the current system state. Generate the most
concrete, actionable items possible.

**Morning brief** (what was flagged this morning):
{morning_brief}

**Dream seeds** (subconscious cross-domain resonances, high-salience first):
{dream_seeds}

**Sprint handoff** (what yesterday's sprint left incomplete):
{sprint_handoff}

**Witness observations** (what happened today so far):
{witness_recent}

**Test results from this cycle**:
{test_summary}

**Files reviewed this cycle** (with signals):
{file_signals}

**TODO items from previous cycle**:
{prev_todo}

For each item you propose:
- Name the EXACT file path
- Identify the specific function/class/line range
- State the concrete fix or addition
- Define a measurable success criterion (e.g., "test_X passes", "coverage +3%")
- Estimate time: <30min, 1-2h, half-day
"""

_META_LAYER = """## LAYER 2: META (Vision)

Look across the last {history_depth} evolution cycles. Detect patterns.

**Cycle history** (last {history_depth} cycles):
{cycle_history}

**Trajectory analysis**:
- Which areas are improving? Which are stagnant?
- Are we approaching any deadlines (COLM: {colm_days} days)?
- What threads have been neglected for >3 cycles?
- Are the GRANULAR items serving the META goals, or drifting?

Produce:
1. A 1-sentence trajectory summary ("We are moving toward X, away from Y")
2. The single most important thing to do next (not a list -- ONE thing)
3. Any thread that needs rotation (has been starved)
"""

_QUALITY_LAYER = """## LAYER 3: QUALITY CONTROL (Anti-Myopia)

Guard against degenerate evolution. Check for:

**Loop detection**:
{loop_analysis}

**Diversity check**:
- Are we touching >3 different modules per cycle, or fixating on 1-2?
- Are test counts going up, down, or flat?
- Are we creating new files (sprawl) or editing existing (focus)?

**Staleness check**:
- Has any TODO item appeared in >2 consecutive cycles unchanged? FLAG IT.
- Are we solving the same bug repeatedly? (regression signal)
- Is the system actually running, or are we just editing configs?

**Anti-theater check**:
- Are changes producing measurable output (test results, metrics)?
- Or are we just reorganizing documentation?

Produce:
1. VERDICT: HEALTHY / DRIFTING / STUCK / LOOPING
2. If not HEALTHY: the specific corrective action (one sentence)
3. Diversity score: how many distinct modules were touched (target: 4+)
"""

MASTER_PROMPT_TEMPLATE = """You are the Master Prompt Engineer for dharma_swarm.

**Your telos**: Generate an evolved prompt that will guide the next autonomous
evolution cycle. The prompt must be concrete, honest, and serve Jagat Kalyan.

{granular_layer}

---

{meta_layer}

---

{quality_layer}

---

## SYNTHESIS

Integrate all three layers into a single evolved prompt (800-1500 words).
The prompt should:
- Lead with the ONE most important action from META
- Include 3-5 GRANULAR items that serve that action
- Respect QUALITY CONTROL constraints (no loops, no theater, no sprawl)
- Follow v7 rules: no theater, no sprawl, no amnesia, no forcing, witness all, silence is valid

**Output**: A comprehensive prompt an autonomous agent can execute.
Begin with "EVOLVED PROMPT:" on its own line.
"""


# ---------------------------------------------------------------------------
# Cycle history tracking
# ---------------------------------------------------------------------------


def _load_cycle_history(max_entries: int = 10) -> list[dict[str, Any]]:
    """Load recent cycle history from the evolution history file."""
    if not _HISTORY_FILE.exists():
        return []

    entries: list[dict[str, Any]] = []
    try:
        with open(_HISTORY_FILE) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []

    return entries[-max_entries:]


def _load_allout_cycle_history(max_entries: int = 10) -> list[dict[str, Any]]:
    """Load recent allout cycle history from ~/.dharma/shared/allout_todo_cycle_*.md.

    This is the REAL cycle history (119+ entries today) vs the JSONL file
    which only has 8 entries with a cycle=1 counter bug.
    """
    shared = _SHARED_DIR
    if not shared.exists():
        return []

    cycle_files = sorted(shared.glob("allout_todo_cycle_*.md"))[-max_entries:]
    entries: list[dict[str, Any]] = []
    for fpath in cycle_files:
        try:
            text = fpath.read_text()
            # Extract cycle number from filename
            num_str = fpath.stem.split("_")[-1]
            cycle_num = int(num_str) if num_str.isdigit() else 0
            # Extract steps (lines starting with a digit and dot)
            steps = [
                ln.lstrip("0123456789. ").strip()
                for ln in text.splitlines()
                if ln.strip() and ln.strip()[0].isdigit() and ". " in ln
            ]
            # Extract timestamp if present
            ts_line = next((ln for ln in text.splitlines() if "Generated" in ln), "")
            entries.append({
                "cycle": cycle_num,
                "timestamp": ts_line.replace("- Generated (UTC):", "").strip(),
                "todo_steps": steps,
                "tests_passed": "?",
                "quality_verdict": "unknown",
                "source": "allout",
            })
        except (OSError, ValueError):
            continue

    return entries


def _save_cycle_entry(entry: dict[str, Any]) -> None:
    """Append a cycle entry to the evolution history."""
    _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_HISTORY_FILE, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def _read_ledger_failure_signatures(max_sessions: int = 5, max_per_session: int = 10) -> list[str]:
    """Read failure signatures from recent orchestrator ledger sessions."""
    ledger_base = _STATE_DIR / "ledgers"
    if not ledger_base.exists():
        return []
    sessions = sorted(
        (p for p in ledger_base.iterdir() if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:max_sessions]
    sigs: list[str] = []
    for sess in sessions:
        pf = sess / "progress_ledger.jsonl"
        if not pf.exists():
            continue
        try:
            for line in pf.read_text().splitlines():
                if not line.strip():
                    continue
                entry = json.loads(line)
                if entry.get("event") in ("task_failed", "task_blocked"):
                    sig = entry.get("failure_signature", "")
                    if sig:
                        sigs.append(sig)
            if len(sigs) >= max_per_session * max_sessions:
                break
        except (OSError, json.JSONDecodeError):
            continue
    return sigs


def _detect_loops(history: list[dict[str, Any]]) -> str:
    """Detect repeated patterns in cycle history and ledger failure signatures."""
    lines: list[str] = []

    # 1. Check for repeated TODO items across allout cycles
    if len(history) >= 2:
        todo_counts: dict[str, int] = {}
        for entry in history:
            for step in entry.get("todo_steps", []):
                normalized = step.strip().lower()[:80]
                todo_counts[normalized] = todo_counts.get(normalized, 0) + 1
        repeated = {k: v for k, v in todo_counts.items() if v >= 2}
        if repeated:
            lines.append("REPEATED TODO items (appeared in 2+ cycles):")
            for item, count in sorted(repeated.items(), key=lambda x: -x[1])[:5]:
                lines.append(f"  [{count}x] {item}")
        else:
            lines.append("No repeated TODO items detected. Evolution appears non-degenerate.")
    else:
        lines.append("Insufficient allout history (need 2+ cycles).")

    # 2. Check ledger failure signatures for repeated errors
    sigs = _read_ledger_failure_signatures()
    if sigs:
        sig_counts: dict[str, int] = {}
        for s in sigs:
            sig_counts[s] = sig_counts.get(s, 0) + 1
        repeated_sigs = {k: v for k, v in sig_counts.items() if v >= 2}
        if repeated_sigs:
            lines.append("\nREPEATED orchestrator failures (from ledgers):")
            for sig, count in sorted(repeated_sigs.items(), key=lambda x: -x[1])[:3]:
                lines.append(f"  [{count}x] {sig[:80]}")
        else:
            lines.append(f"\nLedger: {len(sigs)} failure signatures, none repeated.")

    return "\n".join(lines) if lines else "No loop signals detected."


def _format_cycle_history(history: list[dict[str, Any]]) -> str:
    """Format cycle history for the META layer prompt."""
    if not history:
        return "No previous cycles recorded."

    lines = []
    for entry in history:
        ts = entry.get("timestamp", "unknown")
        cycle = entry.get("cycle", "?")
        test_pass = entry.get("tests_passed", "?")
        test_fail = entry.get("tests_failed", "?")
        steps = entry.get("todo_steps", [])
        verdict = entry.get("quality_verdict", "unknown")

        lines.append(f"Cycle {cycle} ({ts}): tests={test_pass}p/{test_fail}f, "
                      f"verdict={verdict}, steps={len(steps)}")
        for s in steps[:3]:
            lines.append(f"  - {s[:100]}")
        if len(steps) > 3:
            lines.append(f"  ... and {len(steps) - 3} more")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# State gathering (reads real system state, not hardcoded)
# ---------------------------------------------------------------------------


def _read_dream_seeds(n: int = 5) -> str:
    """Read the N most recent dream associations as compact seeds."""
    path = _STATE_DIR / "subconscious" / "dream_associations.jsonl"
    if not path.exists():
        return ""
    seeds = []
    try:
        lines = [l for l in path.read_text().splitlines() if l.strip()]
        for line in lines[-n:]:
            entry = json.loads(line)
            salience = entry.get("salience", 0)
            rtype = entry.get("resonance_type", "?")
            desc = entry.get("description", "")[:120]
            seeds.append(f"  [{salience:.2f}] {rtype}: {desc}")
    except (OSError, json.JSONDecodeError):
        pass
    return "\n".join(seeds)


def _read_morning_brief() -> str:
    """Read the most recent morning brief."""
    candidates = [
        Path.home() / "dgc-core" / "daemon" / "morning_brief.md",
        _SHARED_DIR / "morning_brief.md",
    ]
    for p in candidates:
        if p.exists():
            try:
                content = p.read_text()
                return content[:1500] + ("\n... [truncated]" if len(content) > 1500 else "")
            except OSError:
                pass
    return ""


def _read_sprint_handoff() -> str:
    """Read the most recent sprint handoff file."""
    if not _SHARED_DIR.exists():
        return ""
    handoffs = sorted(_SHARED_DIR.glob("sprint_handoff_*.md"),
                      key=lambda f: f.stat().st_mtime, reverse=True)
    if not handoffs:
        return ""
    try:
        content = handoffs[0].read_text()
        return content[:1200] + ("\n... [truncated]" if len(content) > 1200 else "")
    except OSError:
        return ""


def _read_witness_recent(n: int = 5) -> str:
    """Read the N most recent witness observations from today's log."""
    witness_dir = _STATE_DIR / "witness"
    if not witness_dir.exists():
        return ""
    logs = sorted(witness_dir.glob("witness_*.jsonl"),
                  key=lambda f: f.stat().st_mtime, reverse=True)
    if not logs:
        return ""
    lines_out = []
    try:
        lines = [l for l in logs[0].read_text().splitlines() if l.strip()]
        for line in lines[-n:]:
            entry = json.loads(line)
            action = entry.get("action", "")[:80]
            reflection = entry.get("reflection", "")[:80]
            lines_out.append(f"  [{entry.get('phase','?')}] {action} → {reflection}")
    except (OSError, json.JSONDecodeError):
        pass
    return "\n".join(lines_out)


def gather_system_state() -> dict[str, Any]:
    """Gather current system state from the filesystem."""
    home = Path.home()
    ds = home / "dharma_swarm"

    # Count tests
    test_count = 0
    test_dir = ds / "tests"
    if test_dir.exists():
        test_count = sum(1 for _ in test_dir.rglob("test_*.py"))

    # Count modules
    mod_dir = ds / "dharma_swarm"
    mod_count = sum(1 for _ in mod_dir.glob("*.py")) if mod_dir.exists() else 0

    # Check API keys (existence only, not values)
    api_status = {}
    from dharma_swarm.api_keys import PROVIDER_ENV_KEYS, provider_available
    for key_name in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        val = os.getenv(key_name, "")
        if val:
            api_status[key_name] = f"set ({len(val)} chars)"
        else:
            api_status[key_name] = "not set"

    # Check infrastructure files
    infra = {}
    check_files = {
        "pulse_log": _STATE_DIR / "pulse.log",
        "dream_associations": _STATE_DIR / "subconscious" / "dream_associations.jsonl",
        "latest_journal": _STATE_DIR / "subconscious" / "journal" / "LATEST_JOURNAL.md",
        "memory_db": _STATE_DIR / "db" / "memory.db",
        "stigmergy_marks": _STATE_DIR / "stigmergy" / "marks.jsonl",
    }
    for name, path in check_files.items():
        if path.exists():
            try:
                size = path.stat().st_size
                infra[name] = f"exists ({size:,} bytes)"
            except OSError:
                infra[name] = "exists (size unknown)"
        else:
            infra[name] = "missing"

    # Live signals — actual content, not just file existence
    live_signals = {
        "morning_brief": _read_morning_brief() or "(no morning brief yet)",
        "dream_seeds": _read_dream_seeds() or "(no dream associations)",
        "sprint_handoff": _read_sprint_handoff() or "(no handoff from yesterday)",
        "witness_recent": _read_witness_recent() or "(no witness observations today)",
    }

    return {
        "test_files": test_count,
        "modules": mod_count,
        "api_keys": api_status,
        "infrastructure": infra,
        "live_signals": live_signals,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Core generation
# ---------------------------------------------------------------------------


async def generate_evolved_prompt(
    system_state: dict[str, Any] | None = None,
    recent_findings: dict[str, Any] | None = None,
    priority_actions: list[str] | None = None,
    quality_gap: str = "",
    *,
    test_summary: str = "",
    file_signals: str = "",
    prev_todo: str = "",
    cycle_number: int = 0,
    colm_days: int | None = None,
    history_depth: int = 5,
    llm_timeout_sec: float = 12.0,
) -> str:
    """Generate evolved prompt using OpenRouter with the 3-layer system.

    Can be called with the old-style positional args (backward compatible)
    or with the new keyword args for full 3-layer integration.

    Args:
        system_state: System state dict (optional, auto-gathered if None).
        recent_findings: Findings dict (optional).
        priority_actions: Priority action list (optional).
        quality_gap: Quality gap description (optional, for backward compat).
        test_summary: Test results from this cycle.
        file_signals: Files reviewed with signals.
        prev_todo: Previous cycle TODO items.
        cycle_number: Current cycle number.
        colm_days: Days until COLM deadline.
        history_depth: How many past cycles to analyze.
        llm_timeout_sec: Timeout for the OpenRouter call before callers may fall back.

    Returns:
        The generated evolved prompt text.
    """
    import httpx

    from dharma_swarm.api_keys import get_llm_key
    openrouter_key = get_llm_key("openrouter")
    if not openrouter_key:
        raise RuntimeError("No LLM API key configured (need OPENROUTER_API_KEY or similar)")

    # Auto-calculate COLM days if not provided
    if colm_days is None:
        colm_days, _ = _days_to_colm()

    # Auto-gather state if not provided
    if system_state is None:
        system_state = gather_system_state()

    # Load cycle history — prefer allout cycles (real history) over JSONL
    allout_history = _load_allout_cycle_history(history_depth)
    history = allout_history if allout_history else _load_cycle_history(history_depth)

    # Extract live signals from system_state (populated by gather_system_state)
    live = system_state.get("live_signals", {})

    # Build GRANULAR layer
    granular = _GRANULAR_LAYER.format(
        morning_brief=live.get("morning_brief", "(no morning brief)"),
        dream_seeds=live.get("dream_seeds", "(no dream seeds)"),
        sprint_handoff=live.get("sprint_handoff", "(no handoff)"),
        witness_recent=live.get("witness_recent", "(no witness observations)"),
        test_summary=test_summary or json.dumps(
            {k: v for k, v in system_state.items() if k != "live_signals"}, indent=2
        ),
        file_signals=file_signals or "No file signals available this cycle.",
        prev_todo=prev_todo or "No previous TODO available.",
    )

    # Build META layer
    meta = _META_LAYER.format(
        history_depth=history_depth,
        cycle_history=_format_cycle_history(history),
        colm_days=colm_days,
    )

    # Build QUALITY layer
    quality = _QUALITY_LAYER.format(
        loop_analysis=_detect_loops(history),
    )

    # Assemble the full prompt
    prompt_text = MASTER_PROMPT_TEMPLATE.format(
        granular_layer=granular,
        meta_layer=meta,
        quality_layer=quality,
    )

    # Append legacy fields if provided (backward compat)
    if recent_findings or priority_actions or quality_gap:
        extras = []
        if recent_findings:
            extras.append(f"**Recent findings**: {json.dumps(recent_findings, indent=2)}")
        if priority_actions:
            extras.append("**Priority actions**:\n" + "\n".join(
                f"{i + 1}. {a}" for i, a in enumerate(priority_actions)
            ))
        if quality_gap:
            extras.append(f"**Quality gap**:\n{quality_gap}")
        prompt_text += "\n\n## ADDITIONAL CONTEXT\n\n" + "\n\n".join(extras)

    # Use Sonnet for meta-level prompt engineering (cheaper than Opus, fast)
    async with httpx.AsyncClient(timeout=httpx.Timeout(llm_timeout_sec)) as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json={
                "model": "anthropic/claude-3.5-sonnet",
                "messages": [{"role": "user", "content": prompt_text}],
                "temperature": 0.7,
                "max_tokens": 4000,
            },
            headers={
                "Authorization": f"Bearer {openrouter_key}",
                "HTTP-Referer": "https://github.com/dharma-swarm",
                "X-Title": "Dharma Swarm Master Prompt Engineer",
            },
        )

        if resp.status_code != 200:
            raise RuntimeError(f"OpenRouter error {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError("OpenRouter returned empty choices")
        evolved_prompt = choices[0].get("message", {}).get("content", "")

    if not evolved_prompt.strip():
        raise RuntimeError("OpenRouter returned empty prompt content")

    return evolved_prompt


def generate_local_prompt(
    test_summary: str = "",
    file_signals: str = "",
    prev_todo: str = "",
    cycle_number: int = 0,
    colm_days: int = 20,
    history_depth: int = 5,
) -> str:
    """Generate a prompt locally without LLM call (for offline/testing).

    Uses cycle history and signals to build a deterministic prompt
    without requiring an API key. Useful as a fallback when OpenRouter
    is unavailable.

    Args:
        test_summary: Test results from this cycle.
        file_signals: Files reviewed with signals.
        prev_todo: Previous cycle TODO items.
        cycle_number: Current cycle number.
        colm_days: Days until COLM deadline.
        history_depth: How many past cycles to analyze.

    Returns:
        A locally assembled prompt (no LLM call).
    """
    history = _load_cycle_history(history_depth)
    loop_analysis = _detect_loops(history)
    trajectory = _format_cycle_history(history)

    # Determine quality verdict from history
    verdict = "HEALTHY"
    if "REPEATED TODO" in loop_analysis:
        verdict = "LOOPING"
    elif len(history) > 3 and all(
        h.get("tests_failed", 0) == 0 for h in history[-3:]
    ):
        verdict = "HEALTHY"

    sections = [
        f"# Evolved Prompt -- Cycle {cycle_number}",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"COLM deadline: {colm_days} days",
        f"Quality verdict: {verdict}",
        "",
        "## GRANULAR (this cycle)",
        test_summary or "No test data.",
        "",
        file_signals or "No file signals.",
        "",
        "## META (trajectory)",
        trajectory or "No history yet.",
        "",
        "## QUALITY CONTROL",
        loop_analysis,
        "",
        "## PREVIOUS TODO",
        prev_todo or "None.",
    ]

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Allout integration helpers
# ---------------------------------------------------------------------------


def record_cycle(
    cycle_number: int,
    todo_steps: list[str],
    test_results: dict[str, Any] | None = None,
    files_reviewed: list[str] | None = None,
    quality_verdict: str = "unknown",
) -> None:
    """Record a cycle's results for history tracking.

    Called by thinkodynamic_director after each cycle to build the history
    that feeds the META and QUALITY layers.

    Args:
        cycle_number: The cycle number.
        todo_steps: TODO items generated this cycle.
        test_results: Test pass/fail counts.
        files_reviewed: Files that were reviewed.
        quality_verdict: HEALTHY/DRIFTING/STUCK/LOOPING.
    """
    entry = {
        "cycle": cycle_number,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "todo_steps": todo_steps,
        "tests_passed": (test_results or {}).get("passed", 0),
        "tests_failed": (test_results or {}).get("failed", 0),
        "files_reviewed": files_reviewed or [],
        "quality_verdict": quality_verdict,
    }
    _save_cycle_entry(entry)


def should_evolve_prompt(cycle_number: int, every_n: int = 3) -> bool:
    """Check if this cycle should trigger prompt evolution.

    Args:
        cycle_number: Current cycle number (1-based).
        every_n: Generate evolved prompt every N cycles.

    Returns:
        True if this cycle should generate an evolved prompt.
    """
    return cycle_number > 0 and (cycle_number % every_n) == 0


def assess_quality(
    history: list[dict[str, Any]] | None = None,
    max_depth: int = 5,
) -> str:
    """Assess quality from recent history. Returns verdict string.

    Args:
        history: Cycle history (loaded from file if None).
        max_depth: How many recent cycles to consider.

    Returns:
        One of: HEALTHY, DRIFTING, STUCK, LOOPING.
    """
    if history is None:
        history = _load_cycle_history(max_depth)

    if len(history) < 2:
        return "HEALTHY"  # Not enough data to judge

    # Check for looping (repeated TODOs)
    loop_analysis = _detect_loops(history[-max_depth:])
    if "REPEATED TODO" in loop_analysis:
        return "LOOPING"

    # Check for stuck (no test improvement over 3+ cycles)
    recent = history[-3:]
    if len(recent) >= 3:
        test_counts = [h.get("tests_passed", 0) for h in recent]
        if all(t == test_counts[0] for t in test_counts) and test_counts[0] > 0:
            return "STUCK"

    # Check for drift (no files reviewed)
    if len(recent) >= 2:
        empty_reviews = sum(
            1 for h in recent if not h.get("files_reviewed")
        )
        if empty_reviews >= 2:
            return "DRIFTING"

    return "HEALTHY"


# ---------------------------------------------------------------------------
# Public API (backward compatible)
# ---------------------------------------------------------------------------


async def run_master_prompt_engineer(
    *,
    test_summary: str = "",
    file_signals: str = "",
    prev_todo: str = "",
    cycle_number: int = 0,
) -> str:
    """Run the master prompt engineer with current system state.

    Args:
        test_summary: Test results from the current cycle.
        file_signals: File review signals.
        prev_todo: Previous cycle TODO steps.
        cycle_number: Current cycle number.

    Returns:
        The evolved prompt text.
    """
    system_state = gather_system_state()

    evolved_prompt = await generate_evolved_prompt(
        system_state=system_state,
        test_summary=test_summary,
        file_signals=file_signals,
        prev_todo=prev_todo,
        cycle_number=cycle_number,
    )

    # Write to file
    output_file = _SHARED_DIR / "EVOLVED_PROMPT.md"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        ts = datetime.now(timezone.utc).isoformat()
        f.write(f"# EVOLVED PROMPT -- Cycle {cycle_number}\n\n")
        f.write(f"**Generated**: {ts}\n\n")
        f.write(evolved_prompt)

    print(f"[master-prompt] Evolved prompt written to: {output_file}")
    print(f"[master-prompt] Length: {len(evolved_prompt)} chars")

    return evolved_prompt


if __name__ == "__main__":
    asyncio.run(run_master_prompt_engineer())
