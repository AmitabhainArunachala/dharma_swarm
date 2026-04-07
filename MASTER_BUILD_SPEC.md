# DHARMA SWARM — Master Build Spec v1.0
## The Perception → Evolution → Memory → Metabolism Sprint

**Classification:** Master Engineering Specification  
**Date:** April 7, 2026  
**Authority:** 4-Dimension Oversight (Cybernetician, Engineer, Philosopher, Strategist)  
**Executor:** Claude Code (primary build) + Perplexity Computer (oversight)

---

## THE OBJECTIVE

Wire the five perception-action loops that transform DHARMA SWARM from an amnesiac task dispatcher into a self-perceiving, self-modifying, self-sustaining organism. Demonstrate this transformation through:
1. Iterative, tested implementation (30 steps)
2. A DevOps PhD code review
3. A 4-Dimension oversight re-evaluation
4. Three live fire tests with real LLM calls

**Definition of Done:** The system runs for 30 minutes, completes real tasks, modifies its own code based on what it learned, persists that knowledge for the next session, and the oversight committee sees something genuinely different from what it saw at the start.

---

## BASELINE STATE (measure this BEFORE touching anything)

Run these commands and record every number. These are your comparison targets.

```bash
git pull origin main && git log --oneline -3

# Baseline metrics
python3 -c "
from pathlib import Path
import json

state = Path.home() / '.dharma'
# Task board
try:
    import asyncio
    from dharma_swarm.task_board import TaskBoard
    board = TaskBoard(state / 'db' / 'tasks.db')
    asyncio.get_event_loop().run_until_complete(board.init_db())
    stats = asyncio.get_event_loop().run_until_complete(board.stats())
    print('Task board:', stats)
except: print('Task board: unavailable')

# Telos graph
telos = state / 'telos' / 'objectives.jsonl'
if telos.exists():
    entries = [json.loads(l) for l in telos.read_text().strip().split('\n') if l.strip()]
    progresses = [e.get('progress', 0) for e in entries]
    print(f'TelosGraph: {len(entries)} objectives, avg_progress={sum(progresses)/len(progresses):.3f}')
else:
    print('TelosGraph: not seeded')

# Evolution archive
archive = state / 'evolution' / 'archive.jsonl'
if archive.exists():
    entries = [json.loads(l) for l in archive.read_text().strip().split('\n') if l.strip()]
    real_diffs = sum(1 for e in entries if e.get('diff', '').strip())
    print(f'Evolution archive: {len(entries)} entries, {real_diffs} with real diffs')
else:
    print('Evolution archive: empty')

# Memory
marks = state / 'stigmergy' / 'marks.jsonl'
print(f'Stigmergy marks: {len(marks.read_text().strip().split(chr(10))) if marks.exists() else 0}')

# Recognition seed
seed = state / 'meta' / 'recognition_seed.md'
print(f'Recognition seed: {seed.stat().st_size}b' if seed.exists() else 'Recognition seed: missing')
"

dgc invariants
```

**Save this output.** Label it `BASELINE_STATE.txt`. You will compare to it after each phase.

---

## THE 30-STEP BUILD

### PHASE 0: STABILIZE (Steps 1-3)
*Goal: Confirm the baseline system works before adding anything.*

**Step 1 — Clean baseline test**
```bash
rm -f ~/.dharma/EMERGENCY_HOLD
export TINY_ROUTER_BACKEND=heuristic
timeout 300 dgc orchestrate-live 2>&1 | tee /tmp/step1_baseline.log
grep "dispatched=\|settled=" /tmp/step1_baseline.log | head -10
```
**Pass criteria:** At least 5 tasks dispatched, at least 3 settled.  
**If fail:** Stop. Fix the underlying boot issue before proceeding. Do NOT continue to Phase 1.

**Step 2 — Confirm imports are clean**
```bash
python3 -c "
import dharma_swarm.swarm
import dharma_swarm.orchestrate_live
import dharma_swarm.telos_graph
import dharma_swarm.evolution
import dharma_swarm.agent_runner
import dharma_swarm.web_search
print('All critical imports OK')
"
```
**Pass criteria:** No import errors.

**Step 3 — Run unit test suite, record failures**
```bash
TINY_ROUTER_BACKEND=heuristic python -m pytest tests/ -q --tb=line 2>&1 | tail -10
```
**Record:** exact number of passing/failing tests. This is your regression baseline.

---

### PHASE 1: PERCEPTION LOOP (Steps 4-9)
*Wire task completions to TelosGraph progress. Give the system eyes on itself.*

**Step 4 — Read the exact code paths**

Before writing a single line, read these files:
```bash
# Where signal is emitted
grep -n "SIGNAL_LIFECYCLE_COMPLETED" dharma_swarm/orchestrator.py | head -5

# TelosGraph update_objective signature  
grep -n "async def update_objective" dharma_swarm/telos_graph.py
sed -n '282,305p' dharma_swarm/telos_graph.py

# What objectives map to what task types
grep -n "domain\|viveka\|darwin\|kalyan\|revenue\|research" dharma_swarm/telos_substrate.py | head -10
```

**Step 5 — Create the task→telos mapping**

Create `dharma_swarm/telos_tracker.py`:
```python
"""Task completion → TelosGraph progress mapper.

When a task completes, identify which telos objective it contributes to
and increment that objective's progress. This closes the perception loop:
the system now knows what it has accomplished.
"""

# Domain keywords → telos objective name fragments
TASK_DOMAIN_MAP = {
    "web_search": ("viveka", 0.02),
    "research": ("viveka", 0.02),
    "arxiv": ("viveka", 0.03),
    "mechanistic": ("viveka", 0.03),
    "r_v": ("VIVEKA R_V", 0.05),
    "trading": ("Wire Ginko", 0.03),
    "ginko": ("Wire Ginko", 0.05),
    "market": ("Wire Ginko", 0.02),
    "competitive": ("Differentiate from Isara", 0.03),
    "isara": ("Differentiate from Isara", 0.05),
    "evolution": ("Surpass Sakana DGM", 0.02),
    "darwin": ("Surpass Sakana DGM", 0.03),
    "24.hour": ("Achieve 24-hour", 0.05),
    "deploy": ("Achieve 24-hour", 0.02),
    "autonomous": ("Achieve 24-hour", 0.02),
}

async def record_task_completion(
    task_title: str,
    task_description: str,
    result: str,
    state_dir: Path,
) -> None:
    """Called on task completion. Updates TelosGraph progress."""
    try:
        from dharma_swarm.telos_graph import TelosGraph
        telos = TelosGraph(telos_dir=state_dir / "telos")
        await telos.load()
        
        text = (task_title + " " + task_description).lower()
        matched = {}
        for keyword, (domain_fragment, increment) in TASK_DOMAIN_MAP.items():
            if keyword in text:
                matched[domain_fragment] = matched.get(domain_fragment, 0) + increment
        
        for fragment, total_increment in matched.items():
            objs = await telos.search_objectives(fragment)
            for obj in objs[:1]:  # top match only
                new_progress = min(1.0, obj.progress + total_increment)
                await telos.update_objective(obj.id, progress=new_progress)
        
        await telos.save()
    except Exception as e:
        logger.debug("TelosGraph progress update failed (non-fatal): %s", e)
```

**Step 6 — Wire `record_task_completion` into orchestrator**

Find the task completion handler in `orchestrator.py` (the same place `SIGNAL_LIFECYCLE_COMPLETED` fires). Add the call:
```python
# After emitting SIGNAL_LIFECYCLE_COMPLETED:
try:
    from dharma_swarm.telos_tracker import record_task_completion
    asyncio.create_task(
        record_task_completion(task.title, task.description, result or "", self._state_dir)
    )
except Exception:
    pass  # Never block task completion
```

**Step 7 — Unit test the tracker**

Write `tests/test_telos_tracker.py`:
```python
# Test that: keyword matching works, progress increments correctly,
# out-of-bounds (>1.0) is clamped, unknown tasks don't crash
```
Run: `pytest tests/test_telos_tracker.py -v`  
**Pass criteria:** All tests green.

**Step 8 — Integration test: does progress actually update?**
```python
# Boot SwarmManager with mock provider
# Complete one task with title "research mechanistic interpretability"
# Check TelosGraph: VIVEKA R_V objective progress should be > 0
```

**Step 9 — Live verification**
```bash
rm -f ~/.dharma/EMERGENCY_HOLD
timeout 300 dgc orchestrate-live 2>&1 | tee /tmp/step9_perception.log

# After run, check if TelosGraph updated
python3 -c "
import asyncio, json
from pathlib import Path
from dharma_swarm.telos_graph import TelosGraph
async def check():
    tg = TelosGraph()
    await tg.load()
    objs = await tg.get_all_objectives()
    moved = [o for o in objs if o.progress > 0]
    print(f'Objectives with progress > 0: {len(moved)}/{len(objs)}')
    for o in sorted(moved, key=lambda x: -x.progress)[:5]:
        print(f'  {o.name[:60]}: {o.progress:.3f}')
asyncio.run(check())
"
```
**Pass criteria:** At least 3 objectives show progress > 0.  
**If fail:** Debug the wire. Do not proceed to Phase 2.

---

### PHASE 2: SELF-MODIFICATION (Steps 10-16)
*Wire DarwinEngine real diffs. Give the system hands.*

**Step 10 — Read DarwinEngine code precisely**
```bash
# Find the stubbed call
grep -n "diff.*=.*\"\"\|diff.*empty\|generate_diff\|_generate_code_diff\|second.*llm" dharma_swarm/evolution.py | head -10

# Find auto_evolve vs evolve
grep -n "def auto_evolve\|def evolve\|def run_cycle\|_maybe_auto_evolve" dharma_swarm/evolution.py | head -10

# Read the generate_proposal method
grep -n "def generate_proposal\|async def generate_proposal" dharma_swarm/evolution.py
```

Read every line of `generate_proposal()` and `run_cycle()`. Understand what's stubbed before writing any code.

**Step 11 — Implement the diff generation call**

In `evolution.py`, within `run_cycle()` or `generate_proposal()`, add the second LLM call:
```python
async def _generate_real_diff(
    self,
    component: str,
    description: str,
    improvement_direction: str,
) -> str:
    """Generate an actual code diff via LLM. This is what was stubbed."""
    prompt = f"""You are a Python expert. Generate a minimal, targeted diff for this improvement:

Component: {component}
Current behavior issue: {description}
Improvement direction: {improvement_direction}

Rules:
- Output ONLY the diff in unified diff format (--- /++ lines)
- Touch the minimum number of lines necessary
- The change must be reversible (no destructive operations)
- Add a docstring comment explaining why this change improves fitness
- If no safe change is possible, output: SKIP

Diff:"""
    
    try:
        result = await self._provider.complete(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.3,  # Low temp for code generation
        )
        diff = result.content.strip()
        if diff.startswith("SKIP") or not diff.startswith("---"):
            return ""
        return diff
    except Exception as e:
        logger.warning("Diff generation failed: %s", e)
        return ""
```

**Step 12 — Wire `_generate_real_diff` into the proposal pipeline**

Find where `proposal.diff = ""` is set. Replace with:
```python
proposal.diff = await self._generate_real_diff(
    component=proposal.component,
    description=proposal.description,
    improvement_direction=proposal.improvement_direction,
)
```

**Step 13 — Test diff generation in isolation**
```python
# Create a DarwinEngine with a mock provider
# Call _generate_real_diff with a test component
# Assert: result is either empty string or valid unified diff format
# Assert: provider was called exactly once
```

**Step 14 — Test the full evolution cycle with real diff**
```python
# Run engine.run_cycle() with a mock provider that returns a realistic diff
# Assert: archive entry has non-empty diff
# Assert: if diff is valid and tests pass, proposal is promoted
# Assert: if diff breaks tests, rollback is called and proposal is archived as failed
```

**Step 15 — Safety gate test: bad diff must roll back**
```python
# Inject a diff that deliberately breaks a test
# Assert: the rollback fires, original file is restored
# Assert: test suite passes after rollback
# This is critical: the system must not be able to corrupt itself
```

**Step 16 — Live verification**
```bash
# Run free-grind for 20 minutes (this is where DarwinEngine runs)
timeout 1200 dgc orchestrate-live 2>&1 | tee /tmp/step16_evolution.log

# Check if any real diffs appeared
python3 -c "
import json
from pathlib import Path
archive = Path.home() / '.dharma' / 'evolution' / 'archive.jsonl'
if archive.exists():
    entries = [json.loads(l) for l in archive.read_text().strip().split('\n') if l.strip()]
    real = [e for e in entries if e.get('diff','').strip() and not e['diff'].startswith('SKIP')]
    print(f'Real diffs: {len(real)}/{len(entries)}')
    for e in real[:3]:
        print(f'  {e.get(\"component\",\"?\")}:')
        print(f'  {e[\"diff\"][:100]}...')
"
```
**Pass criteria:** At least 1 real diff in the evolution archive.  
**If fail:** Debug the LLM call. Check provider is available. Check prompt is reaching the model.

---

### PHASE 3: COMPOSABILITY (Steps 17-20)
*Fix cross-task file coordination. Give the system a shared workspace.*

**Step 17 — Read the existing share_to_swarm mechanism**
```bash
grep -n "share_to_swarm\|shared_path\|shared_dir\|SharedMemory" dharma_swarm/agent_memory_manager.py | head -10
grep -n "def share_to_swarm" dharma_swarm/agent_memory_manager.py
```

Read the full method. Understand what it does and why it's never called.

**Step 18 — Wire share_to_swarm into task completion**

In `agent_runner.py`, in the task completion path (where shared notes are written):
```python
# After writing to agent notes:
try:
    if self._memory_manager and result:
        await self._memory_manager.share_to_swarm(
            content=result,
            task_title=task.title,
            task_id=task.id,
            agent_name=self.name,
        )
except Exception as e:
    logger.debug("share_to_swarm failed (non-fatal): %s", e)
```

**Step 19 — Update task description builder to include shared output path**

In the section of code that builds task context for agents, add:
```python
# Tell agents where to write shared outputs
shared_instruction = (
    f"\n\nIMPORTANT: Write your primary output to BOTH:\n"
    f"1. Your agent notes (standard behavior)\n"
    f"2. A shared file: ~/.dharma/shared/{task_id[:8]}_{slugify(task_title)}.md\n"
    f"The second path is how other agents find your work."
)
```

**Step 20 — Test cross-task coordination**
```python
# Create two tasks: Task A writes to shared path, Task B reads it
# Run Task A first (complete)
# Run Task B and assert it can find Task A's output
# This is the coordination chain test
```
**Pass criteria:** Task B successfully reads Task A's output and incorporates it.

---

### PHASE 4: MEMORY (Steps 21-24)
*Deploy LanceDB. Give the system a past.*

**Step 21 — Deploy LanceDB adapter**

Read `memory_palace.py` to find the LanceDB integration point. The spec says it falls back to `tempfile.mkdtemp()` — find that and replace with a real LanceDB deployment:
```python
# In memory_palace.py, where the tempfile fallback lives:
try:
    import lancedb
    db = lancedb.connect(str(self._state_dir / "lancedb"))
    self._db = db
    logger.info("LanceDB connected at %s", self._state_dir / "lancedb")
except ImportError:
    logger.warning("lancedb not installed — pip install lancedb")
    raise
except Exception as e:
    logger.warning("LanceDB failed: %s — falling back to in-memory", e)
    self._db = None  # Graceful degradation
```

**Step 22 — Index existing agent notes into LanceDB**

One-time migration: index all content in `~/.dharma/shared/` into LanceDB so the system has immediate memory of previous sessions' work.
```bash
python3 -c "
import asyncio
from dharma_swarm.memory_palace import MemoryPalace
from pathlib import Path

async def migrate():
    palace = MemoryPalace()
    shared = Path.home() / '.dharma' / 'shared'
    count = 0
    for f in shared.glob('*.md'):
        content = f.read_text()
        if content.strip():
            await palace.index(content, source=str(f), domain='swarm_output')
            count += 1
    print(f'Indexed {count} files into LanceDB')
asyncio.run(migrate())
"
```

**Step 23 — Wire SleepTimeAgent to use LanceDB**

After each task completion, SleepTimeAgent should extract propositions and index them:
```python
# In the task completion path, after share_to_swarm:
try:
    from dharma_swarm.sleep_time_agent import SleepTimeAgent
    sta = SleepTimeAgent()
    await sta.consolidate_knowledge(
        content=result,
        task_title=task.title,
        source="task_completion",
    )
except Exception as e:
    logger.debug("SleepTimeAgent consolidation failed (non-fatal): %s", e)
```

**Step 24 — Verify cross-session persistence**
```bash
# Run 1: Do research task, write to shared notes, check LanceDB
timeout 120 python3 -c "
# Boot swarm, do one task, check LanceDB has entries
"

# RESTART the swarm (this is the key test)
# Run 2: Query LanceDB for knowledge from Run 1
timeout 120 python3 -c "
# Boot swarm, query LanceDB for 'what do we know about Isara?'
# Assert: results come back from the PREVIOUS session
"
```
**Pass criteria:** LanceDB returns relevant content from a previous session.  
**If fail:** The persistence mechanism is broken. Do not proceed to Phase 5.

---

### PHASE 5: METABOLISM (Steps 25-27)
*Wire Ginko. Give the system a reason to survive.*

**Step 25 — Create the Ginko bridge tool**

In `web_search.py` or a new `ginko_bridge.py`:
```python
async def ginko_get_signals() -> dict:
    """Get current Ginko market regime signals."""
    try:
        import subprocess
        result = subprocess.run(
            ["python3", "-m", "ginko.signals", "--format", "json"],
            cwd=Path.home() / "ginko-trading",
            capture_output=True, timeout=30
        )
        return json.loads(result.stdout)
    except Exception as e:
        return {"error": str(e), "regime": "unknown"}

async def ginko_get_regime() -> str:
    """Get current market regime from Ginko."""
    signals = await ginko_get_signals()
    return signals.get("regime", "unknown")
```

Add `ginko_signals` and `ginko_regime` to autonomous_agent tool definitions.

**Step 26 — Wire Ginko PnL to EconomicSpine**

Add a cron job or loop that reads Ginko paper trading results and reports to EconomicSpine:
```python
# Every 30 minutes, read Ginko PnL from paper trading results
# Report to EconomicSpine as revenue event
# This gives the swarm a metabolic signal: is the system paying its way?
```

**Step 27 — Test Ginko bridge**
```bash
# Create a task: "Get current market regime and decide if now is a good time to trade BTC"
# Assert: agent calls ginko_regime tool
# Assert: agent receives valid regime data
# Assert: agent produces a recommendation based on real data
```

---

### PHASE 6: VERIFICATION GAUNTLET (Steps 28-30)

**Step 28 — DevOps PhD Review**

After completing all code changes, run this full review prompt through a fresh Claude Code session with the entire changed codebase:

```
You are a DevOps PhD and principal engineer with deep expertise in distributed systems,
async Python, and agentic AI architectures. You have been handed a codebase that just 
had 5 major subsystems wired in parallel. Your job is forensic.

Read these changed files:
- dharma_swarm/telos_tracker.py (new)
- dharma_swarm/evolution.py (modified: diff generation)
- dharma_swarm/orchestrator.py (modified: perception loop + share wire)
- dharma_swarm/agent_runner.py (modified: share_to_swarm, SleepTimeAgent)
- dharma_swarm/memory_palace.py (modified: LanceDB deployment)
- dharma_swarm/web_search.py (modified: Ginko bridge)

For EACH file check:
1. Async correctness — are all async calls awaited? Are there any blocking calls in async contexts?
2. Error handling — does every new try/except catch the right exceptions? Are there silent failures that will mask real bugs?
3. Interface contracts — does every new caller pass the correct arguments to every callee? 
4. Regression risk — does any change modify a code path that existing tests cover? If so, will those tests now fail?
5. Resource leaks — are database connections, file handles, and asyncio tasks properly cleaned up?
6. Idempotency — can everything be safely re-run? Can the system restart without corrupting state?

Run: pytest tests/ -q --tb=short
Fix every failing test before reporting.

Report: list of issues found (severity: BLOCKER / HIGH / MEDIUM / LOW), fixes applied, final test count.
```

**Pass criteria:** Zero BLOCKERs. All HIGHs addressed. Tests >= baseline count from Step 3.

**Step 29 — 4-Dimension Oversight Committee Re-evaluation**

Run the same 4 subagents from the first synthesis (Cybernetician, Engineer, Philosopher, Strategist), but now with the changed codebase. Each agent should:
1. Re-read the changed files
2. Re-check the live run metrics
3. Answer: "What is different? What is still broken? What is the highest next priority?"

**Synthesize their findings.** If they identify regressions or new gaps, go back to the relevant phase and fix before running live tests.

**Step 30 — Three Live Fire Tests**

**Live Fire 1 (10 minutes):** Clean boot with no prior state.
```bash
rm -f ~/.dharma/EMERGENCY_HOLD
rm -f ~/.dharma/meta/recognition_seed.md  # Force re-generation
timeout 600 dgc orchestrate-live 2>&1 | tee /tmp/livefire1.log
```
Measure: tasks dispatched, tasks settled, web searches fired, TelosGraph progress moved, evolution diffs generated.

**Live Fire 2 (30 minutes):** Continuation test — session memory.
```bash
# Do NOT clear state — boot from where Live Fire 1 left off
timeout 1800 dgc orchestrate-live 2>&1 | tee /tmp/livefire2.log
```
Measure: did LanceDB queries return content from Live Fire 1? Did agents reference previous research? Did DarwinEngine improve on previous proposals?

**Live Fire 3 (30 minutes):** State of AI research task (the real benchmark).
```bash
# Seed the 5 mission tasks from the State of AI prompt
# Run for 30 minutes
# Check: does STATE_OF_AI_APRIL_2026.md exist and have >3000 words?
# Compare quality to the PDF I produced manually
```
**Pass criteria:** The report exists, has real content (actual company names, funding figures, architectural details), and the synthesis task found and read the research tasks' outputs (meaning the coordination chain closed).

---

## COMPLETION CRITERIA

The build is DONE when ALL of the following are true:

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Task settlement | settled > 0 in logs | grep "settled=" livefire3.log |
| TelosGraph progress | ≥ 5 objectives > 0 | dgc telos (or python check) |
| Real evolution diffs | ≥ 1 non-empty diff | check evolution/archive.jsonl |
| Cross-session memory | LanceDB query returns previous content | python query test |
| Coordination chain | STATE_OF_AI report > 3000 words | wc -w |
| Web search | ≥ 20 searches in Live Fire 3 | grep "web_search via" |
| No regressions | Test count ≥ baseline | pytest count |
| DevOps sign-off | Zero BLOCKERs | DevOps review step 28 |
| Oversight consensus | All 4 dimensions see genuine improvement | Step 29 synthesis |

---

## ABORT CONDITIONS

Stop and reassess (do not push) if:
- Any Phase verification step fails 2x after attempted fix
- A change causes test count to drop by >10%
- Live fire produces EMERGENCY_HOLD within first 5 minutes
- DevOps review finds a BLOCKER that touches safety-critical code (telos_gates, dharma_kernel, gnani)

---

## NOTES FOR EXECUTOR (Claude Code)

1. **Read before writing.** Every step says which files to read first. Do not skip this.
2. **One phase at a time.** Do not start Phase 2 until Phase 1's live verification passes.
3. **Commit after each phase.** Format: `fix(phase-N): description`. This creates checkpoints.
4. **Never push a failing test.** If a test breaks, fix it before moving to the next step.
5. **The try/except pattern is intentional.** New wires should be non-fatal. The system must degrade gracefully, not crash.
6. **Update INTERFACE_MISMATCH_MAP.md** when you resolve a known mismatch.
7. **The 4D committee sees the git log.** Every commit message will be reviewed. Write them clearly.
