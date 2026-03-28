# Living Layers Architecture

**Source files:**
- `~/dharma_swarm/dharma_swarm/stigmergy.py` (220 lines)
- `~/dharma_swarm/dharma_swarm/shakti.py` (201 lines)
- `~/dharma_swarm/dharma_swarm/subconscious.py` (191 lines)
- `~/dharma_swarm/dharma_swarm/orchestrate_live.py` (356 lines, line 219-263 for living layers loop)

---

The Godel Claw has two halves:

- **Gnani** (observer): Dharma Kernel, Corpus, Gates, Policy Compiler --
  immutable, constraining. These are the 10 axioms that never change, the gates
  that block harm, the compiler that fuses principles into enforceable policy.
  They are the skeleton.

- **Prakruti** (dynamic): Stigmergic lattice, Shakti perception, subconscious
  association -- creative, alive. These are the layers that accumulate
  intelligence through use, find lateral connections through dreaming, and
  perceive emergent patterns through the four energies. They are the flesh.

Neither half works alone. Gnani without Prakruti is a rigid rulebook. Prakruti
without Gnani is undirected chaos. Together they form a system that constrains
itself while remaining capable of surprise.

---

## 1. Stigmergy -- The Lattice

**Source:** `~/dharma_swarm/dharma_swarm/stigmergy.py` (220 lines)

Stigmergy is how ant colonies build complex structures without blueprints: each
ant leaves a pheromone trace, and subsequent ants respond to the accumulated
traces rather than to any central plan. The intelligence lives in the
environment, not in any individual.

### The Mark Model

Every agent interaction leaves a `StigmergicMark`:

```
StigmergicMark
  id:           UUID
  timestamp:    UTC datetime
  agent:        who left the mark (e.g., "cartographer", "surgeon", "subconscious")
  file_path:    what file was touched
  action:       "read" | "write" | "scan" | "connect" | "dream"
  observation:  what was noticed (max 200 chars)
  salience:     0.0 - 1.0 (how important this observation is)
  connections:  list of related file paths
```

Marks are appended to `~/.dharma/stigmergy/marks.jsonl` -- append-only,
non-blocking via `aiofiles`. The five allowed actions are defined as a `Literal`
type at line 27. The `"dream"` action is exclusively used by the subconscious
layer when dream marks re-enter the lattice.

### Reading the Lattice

The `StigmergyStore` class (line 50) provides five async read methods:

- **`read_marks(file_path, limit)`** (line 89): Recent marks for a specific
  file, newest first, capped at `limit`. The basic query: "what has been
  observed about this file?"

- **`hot_paths(window_hours, min_marks)`** (line 104): Files with heavy recent
  activity within the last `window_hours` (default 24), requiring at least
  `min_marks` touches (default 3). Returns `list[tuple[str, int]]` sorted by
  count descending. These are the files where attention is concentrating.

- **`high_salience(threshold, limit)`** (line 125): Marks with salience >=
  `threshold` (default 0.7), sorted by salience descending, capped at `limit`
  (default 10). These are the observations that agents flagged as important.

- **`connections_for(file_path)`** (line 136): Unique connections from all marks
  on a given file, returned as a sorted list. This reveals the web of
  relationships that agents have discovered between files.

- **`density()`** (line 184): Synchronous count of marks in the hot file. Opens
  the file directly with `open()`, not `aiofiles`, for fast non-async checks.
  Used by the subconscious layer to decide when to wake.

### Decay

`decay(max_age_hours)` at line 147 moves marks older than `max_age_hours`
(default 168 = 7 days) from the hot file to `~/.dharma/stigmergy/archive.jsonl`.
The implementation reads all marks, partitions by age, appends old marks to the
archive, and rewrites the hot file with only the kept marks. Returns the count
of archived marks.

The archive is never deleted -- it is the colony's long-term memory.

### Module-Level Convenience

`leave_stigmergic_mark()` at line 201 is a module-level async function that
creates a `StigmergicMark` and persists it via a default `StigmergyStore`.
This is the simplest way for any code to leave a trace:

```python
from dharma_swarm.stigmergy import leave_stigmergic_mark

await leave_stigmergic_mark(
    agent="cartographer",
    file_path="dharma_swarm/evolution.py",
    observation="Safety floor invariant at line 1241",
    salience=0.8,
    connections=["dharma_swarm/canary.py"],
    action="scan",
)
```

---

## 2. Shakti -- Creative Perception

**Source:** `~/dharma_swarm/dharma_swarm/shakti.py` (201 lines)

The four Shaktis are creative energies from Sri Aurobindo's integral philosophy,
mapped here to four modes of computational perception. Every observation the
system makes is classified through this lens.

### The Four Energies

| Energy | Domain | Question | Keywords (line 40-57) |
|--------|--------|----------|-----------------------|
| **Maheshwari** | Vision, architecture | Does this serve the larger pattern? What wants to emerge? | vision, pattern, architecture, design, direction, strategy, purpose, telos, emergence, possibility |
| **Mahakali** | Force, decisive action | Is this the moment to act? What is the force criterion? | force, action, execute, deploy, speed, urgency, breakthrough, destroy, clear, decisive |
| **Mahalakshmi** | Harmony, beauty | Is this elegant? Does it create harmony or add noise? | harmony, balance, beauty, elegant, integrate, flow, rhythm, proportion, grace, coherence |
| **Mahasaraswati** | Precision, detail | Is this technically correct? Every detail right? | precision, detail, exact, correct, careful, thorough, meticulous, accurate, validate, verify |

`classify_energy()` at line 83 lowercases the observation, splits into words,
and counts keyword intersections with each energy's frozen set. The energy with
the most hits wins. When no keywords match, the default is **Mahasaraswati**
(precision as the conservative fallback -- when in doubt, be careful).

### The Perception Loop

`ShaktiLoop` (line 110) is wired to a `StigmergyStore` and operates in three
steps:

**Step 1 -- Scan** (line 129, `perceive()`): Query the lattice for hot paths
(last 24 hours) and high-salience marks (threshold 0.7).

**Step 2 -- Classify**: For each finding, determine the dominant Shakti energy
and the impact level based on activity intensity:

| Touch Count | Impact Level | Salience Formula |
|-------------|-------------|------------------|
| > 10 | `"system"` | `min(count / 20, 1.0)` |
| > 5 | `"module"` | `min(count / 20, 1.0)` |
| <= 5 | `"local"` | `min(count / 20, 1.0)` |

High-salience marks from the lattice are always classified as `"module"` impact.

**Step 3 -- Respond**: Based on impact level:

- **Local** (`propose_local()` at line 169): Returns a proposal dict with
  `type="local"`, perception_id, proposal text, and energy. Local proposals
  can be auto-approved and executed without escalation. Returns `None` if
  perception is not local impact.

- **Module or System** (`escalate()` at line 180): Returns an escalation dict
  with `type="escalation"`, perception_id, impact level, observation, proposal,
  and energy. Routed to the Darwin Engine or human oversight.

### The SHAKTI_HOOK

Defined at line 196 for injection into agent system prompts:

```
SHAKTI PERCEPTION: Before completing your task, spend 30 seconds scanning:
- What pattern did you notice that wasn't in your task description?
- What connection exists between what you just did and something else in the system?
- What wants to emerge that nobody asked for?
Leave a stigmergic mark with your observation. If salience > 0.7, propose it.
```

**Current status:** The hook text is defined but not yet automatically injected
into agent system prompts by `startup_crew.py`. Agents can be given the hook
manually, or dedicated Shakti-scanning agents can be spawned with it.

---

## 3. Subconscious / HUM -- The Dream Layer

**Source:** `~/dharma_swarm/dharma_swarm/subconscious.py` (191 lines)

The subconscious is the colony's equivalent of sleeping on a problem. When
enough marks have accumulated, the subconscious wakes and dreams: randomly
sampling marks and computing lateral associations that no focused agent would
produce.

### The Dream Mechanism

`SubconsciousStream.dream(sample_size)` at line 69:

1. **Read**: Fetch recent marks from stigmergy (3x sample_size, to have a pool).
2. **Sample**: Randomly select `sample_size` marks using `random.sample()`.
3. **Associate**: For each adjacent pair (i, i+1) in the sample, compute
   Jaccard similarity on observation text and classify the resonance type:

   | Resonance Type | Condition |
   |----------------|-----------|
   | `structural_echo` | Both marks reference the same `file_path` |
   | `temporal_coincidence` | Marks are within 3600 seconds (1 hour) |
   | `pattern_similarity` | Jaccard similarity > 0.3 |
   | `unknown` | None of the above |

4. **Persist**: Write each `SubconsciousAssociation` to
   `~/.dharma/subconscious/hum.jsonl`.
5. **Re-enter**: Leave a dream mark back on the stigmergic lattice for each
   association:

   ```python
   StigmergicMark(
       agent="subconscious",
       file_path=f"{source_a}<->{source_b}",  # the connection itself
       action="dream",
       observation=description[:200],
       salience=strength,  # Jaccard score becomes salience
   )
   ```

### The Wake Threshold

`should_wake()` at line 130 returns True when the stigmergy density has
increased by at least `_wake_threshold` (default 50) marks since the last dream
cycle. The `_last_density` is updated at the end of each `dream()` call
(line 125).

This prevents the subconscious from running on every tick. It only wakes when
there is enough new material to dream about.

### Resonance Scoring

`_find_resonance()` at line 176 uses Jaccard similarity:

```python
words_a = set(text_a.lower().split())
words_b = set(text_b.lower().split())
similarity = len(words_a & words_b) / len(words_a | words_b)
```

Deliberately simple -- no LLM, no embeddings, no semantic analysis. The point
is to find lateral connections cheaply. A Jaccard score of 0.3 means roughly a
third of the combined vocabulary overlaps, which is enough to flag a potential
structural relationship worth investigating.

### Reading Dreams

- `get_recent_dreams(limit)` at line 137: Returns newest associations first.
- `strongest_resonances(threshold)` at line 155: Returns associations with
  strength >= threshold, sorted by strength descending.

---

## 4. How They Interact

```
Agents work on tasks
    |
    v
Leave stigmergic marks (observation, salience, connections)
    |
    +---> marks.jsonl accumulates
    |
    v
[Every 180s -- orchestrate_live.py line 219]
    |
    +---> Stigmergy decay: if density > 100, evaporate marks older than 7 days
    |
    +---> Subconscious check: if density increased by >= 50 since last dream
    |         |
    |         +---> dream(): sample random marks, compute Jaccard associations
    |         |
    |         +---> Dream marks re-enter lattice with action="dream"
    |
    +---> Shakti perception: scan hot paths + high-salience marks
              |
              +---> Classify each into Shakti energy (vision/force/beauty/precision)
              |
              +---> Determine impact level (local/module/system)
              |
              +---> High-salience perceptions logged to orchestrator summary
              |
              v
         [Next tick picks up dream marks alongside regular marks]
              |
              v
         Cycle continues...
```

The feedback loop is the essential property. Dreams are not discarded -- they
become stigmergic marks (with `action="dream"` and `salience` set to the
Jaccard strength). On the next living-layers tick, Shakti perception scans the
lattice and encounters both regular agent marks AND dream marks. A strong dream
(high Jaccard similarity, high salience) will surface as a hot path or
high-salience observation and potentially get escalated.

The colony does not need a central planner to discover cross-cutting concerns.
The lattice discovers them through accumulation, and the subconscious surfaces
them through random sampling. This is the Aunt Hillary principle: intelligence
emerging from the interactions of simple agents following local rules.

---

## 5. Integration with the Orchestrator

`orchestrate_live.py` runs 5 concurrent async loops. The living layers loop is
at line 219:

```python
async def run_living_layers(shutdown_event: asyncio.Event) -> None:
    """Living layers -- stigmergy decay, shakti perception, subconscious dreams."""
    await asyncio.sleep(45)  # Let other systems init first

    while not shutdown_event.is_set():
        store = StigmergyStore()
        density = store.density()

        # 1. Stigmergy decay (only when hot file is large)
        if density > 100:
            decayed = await store.decay(max_age_hours=168)

        # 2. Subconscious dreams (trigger on density threshold)
        stream = SubconsciousStream(stigmergy=store)
        if await stream.should_wake():
            associations = await stream.dream()

        # 3. Shakti perception
        loop = ShaktiLoop(stigmergy=store)
        perceptions = await loop.perceive(
            current_context="orchestrator living-layer tick",
            agent_role="orchestrator",
        )

        await asyncio.sleep(LIVING_INTERVAL)  # 180 seconds
```

The interval defaults to 180 seconds, configurable via the `DGC_LIVING_INTERVAL`
environment variable (line 41). The initial 45-second delay lets other systems
(swarm, memory, task board) initialize first.

This loop is started alongside the other 4 loops at line 328:

```python
asyncio.create_task(run_living_layers(shutdown_event), name="living")
```

---

## 6. Fractal Autonomy Model

The three impact levels create a fractal structure where each layer has
appropriate autonomy:

| Level | Threshold | Autonomy | Example |
|-------|-----------|----------|---------|
| **Local** | <= 5 touches | Self-approve. Low risk, high speed. | An agent notices a pattern in the file it is working on and leaves a mark. No escalation needed. |
| **Module** | > 5 touches, or high-salience mark | Propose to Darwin Engine. Medium risk. | A Shakti perception identifies a connection between multiple files suggesting a refactoring. Goes through gate-check and fitness eval. |
| **System** | > 10 touches | Escalate to human or committee. High risk. | A perception identifies a pattern spanning the entire codebase or contradicting existing policy. Human oversight required. |

The principle: the more a pattern involves, the more oversight it requires.
This is downward causation in action -- higher layers (Dharma) constrain lower
layers (living), and the constraint intensity scales with impact scope.

---

## 7. Wiring Status (Updated 2026-03-27)

Honest assessment of remaining gaps:

1. ✅ **SHAKTI_HOOK is now injected into ALL agent system prompts.** As of 2026-03-27,
   `agent_runner.py` line 1282-1287 injects `SHAKTI_HOOK` for all providers, not just
   CLAUDE_CODE. Agents now perceive through the Shakti lens automatically.

2. ✅ **Stigmergy marks ARE automatically left by agent tasks.** `agent_runner.py`
   line 2407 calls `_leave_task_mark()` (defined at line 1670) on every task completion.
   Marks include agent, file_path, action, observation, salience, and connections.
   This was ALREADY wired, but the documentation was outdated.

3. ❌ **Shakti escalations are not routed to the Darwin Engine.** `ShaktiLoop`
   can produce escalation dicts, and these are logged in the orchestrator
   summary, but there is no automatic path from a Shakti escalation to a
   Darwin Engine `Proposal`. This routing logic is still a v2 task.

4. ❌ **Dream marks are not weighted differently from agent marks.** The lattice
   treats `action="dream"` marks identically to `action="write"` marks when
   computing hot paths. A future refinement could weight dream marks differently
   in the hot path and salience calculations.

**Current status:** 2/4 wired (50%), 2/4 remaining. The living layers loop in
`orchestrate_live.py` connects stigmergy, shakti, and subconscious at the 180-second
interval level. The remaining work is: Shakti → Darwin routing and dream mark weighting.

---

*All line numbers reference the current source as of 2026-03-13 in
`~/dharma_swarm/dharma_swarm/`.*
