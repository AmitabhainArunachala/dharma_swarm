# Living Layers Architecture

The Godel Claw has two halves:

- **Gnani** (observer): Dharma Kernel, Constitution, Gates, Policy Compiler --
  immutable, constraining. These are the 10 axioms that never change, the gates
  that block harm, the compiler that fuses principles into enforceable policy.
  They are the skeleton.

- **Prakruti** (dynamic): Shakti perception, stigmergic lattice, subconscious
  association -- creative, alive. These are the layers that accumulate
  intelligence through use, find lateral connections through dreaming, and
  perceive emergent patterns through the four energies. They are the flesh.

Neither half works alone. Gnani without Prakruti is a rigid rulebook. Prakruti
without Gnani is undirected chaos. Together they form a system that constrains
itself while remaining capable of surprise.


## The Stigmergic Lattice

**Source**: `~/dharma_swarm/dharma_swarm/stigmergy.py` (221 lines)

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
non-blocking via `aiofiles`.

### Reading the Lattice

The `StigmergyStore` provides five read methods:

- **`read_marks(file_path, limit)`**: Recent marks for a specific file, newest
  first. The basic query: "what has been observed about this file?"

- **`hot_paths(window_hours, min_marks)`**: Files with heavy recent activity,
  sorted by touch count. Default window: 24 hours, minimum 3 marks. These are
  the files where attention is concentrating.

- **`high_salience(threshold, limit)`**: Marks with salience above a threshold
  (default 0.7), sorted by salience descending. These are the observations
  that agents flagged as important.

- **`connections_for(file_path)`**: Unique connections from all marks on a
  given file. This reveals the web of relationships that agents have discovered
  between files.

- **`density()`**: Synchronous count of marks in the hot file. Used by the
  subconscious layer to decide when to wake up.

### Decay

Marks older than 168 hours (7 days) are moved from the hot file to an archive
file by `decay()`. This keeps the hot file lean while preserving history. The
archive is never deleted -- it is the colony's long-term memory.

### The Key Insight

Every agent touch leaves a trace. The intelligence accumulates in the lattice,
not in any single agent. An agent that reads a file and notices a pattern
leaves a mark. The next agent that touches the same file sees not just the file
but also what previous agents noticed. Over time, the lattice develops a
topology that reflects the actual structure of the system -- not the designed
structure, but the emergent one.


## Shakti Perception

**Source**: `~/dharma_swarm/dharma_swarm/shakti.py` (201 lines)

The four Shaktis are creative energies from Sri Aurobindo's integral
philosophy, mapped here to four modes of computational perception. Every
observation the system makes is classified through this lens.

### The Four Energies

| Energy | Domain | Question | Keywords |
|--------|--------|----------|----------|
| **Maheshwari** | Vision | Does this serve the larger pattern? What wants to emerge? | vision, pattern, architecture, design, direction, strategy, purpose, telos, emergence, possibility |
| **Mahakali** | Force | Is this the moment to act? What is the force criterion? | force, action, execute, deploy, speed, urgency, breakthrough, destroy, clear, decisive |
| **Mahalakshmi** | Beauty | Is this elegant? Does it create harmony or add noise? | harmony, balance, beauty, elegant, integrate, flow, rhythm, proportion, grace, coherence |
| **Mahasaraswati** | Precision | Is this technically correct? Every detail right? | precision, detail, exact, correct, careful, thorough, meticulous, accurate, validate, verify |

Classification is keyword-based: the observation text is lowercased and
scanned for keyword matches. The energy with the most hits wins. When no
keywords match, the default is Mahasaraswati (precision as the conservative
fallback -- when in doubt, be careful).

### The Perception Loop

`ShaktiLoop` is wired to a `StigmergyStore` and operates in three steps:

1. **Scan**: Query the lattice for hot paths and high-salience marks.

2. **Classify**: For each finding, determine the dominant Shakti energy and
   the impact level:
   - Hot path with > 10 touches -> **system** level (salience = count/20, capped at 1.0)
   - Hot path with > 5 touches -> **module** level
   - Everything else -> **local** level

3. **Respond**: Based on impact level:
   - **Local**: `propose_local()` returns a proposal dict that can be
     auto-approved and executed without escalation
   - **Module** or **System**: `escalate()` returns an escalation dict
     routed to the Darwin Engine or human oversight

### The SHAKTI_HOOK

The following text is defined in `shakti.py` for injection into every agent's
system prompt:

```
SHAKTI PERCEPTION: Before completing your task, spend 30 seconds scanning:
- What pattern did you notice that wasn't in your task description?
- What connection exists between what you just did and something else in the system?
- What wants to emerge that nobody asked for?
Leave a stigmergic mark with your observation. If salience > 0.7, propose it.
```

**Current status**: The hook text is defined but not yet automatically injected
into agent system prompts at spawn time. This is a v2 wiring task. Agents can
still be given the hook manually.


## The Subconscious / HUM

**Source**: `~/dharma_swarm/dharma_swarm/subconscious.py` (191 lines)

The subconscious is the colony's equivalent of sleeping on a problem. When
enough marks have accumulated (density threshold: 50 new marks since last
wake), the subconscious wakes and dreams: randomly sampling marks and
computing lateral associations that no focused agent would produce.

### The Dream Mechanism

`SubconsciousStream.dream(sample_size)` operates as follows:

1. Read recent marks from stigmergy (3x the sample size, to have a pool)
2. Randomly sample `sample_size` marks from the pool
3. For each adjacent pair in the sample, compute Jaccard similarity on their
   observation text (word-level overlap)
4. Classify the resonance type:
   - **`structural_echo`**: both marks reference the same file_path
   - **`temporal_coincidence`**: marks are within 1 hour of each other
   - **`pattern_similarity`**: Jaccard similarity > 0.3
   - **`unknown`**: none of the above
5. Persist each association to `~/.dharma/subconscious/hum.jsonl`
6. Leave a dream mark back on the stigmergic lattice:
   - agent: `"subconscious"`
   - file_path: `"source_a<->source_b"` (the connection itself)
   - action: `"dream"`
   - salience: set to the Jaccard strength

### The Wake Threshold

`should_wake()` returns True when the stigmergy density has increased by at
least 50 marks since the last dream cycle. This prevents the subconscious from
running on every tick -- it only wakes when there is enough new material to
dream about.

**Current status**: Nothing in the daemon heartbeat calls `should_wake()`.
Dreams only fire when explicitly invoked via `dgc hum` or `/hum` in the TUI.
Wiring this into the daemon's tick loop is a v2 task.

### Resonance Scoring

The `_find_resonance()` method uses Jaccard similarity:

```
words_a = set(text_a.lower().split())
words_b = set(text_b.lower().split())
similarity = len(words_a & words_b) / len(words_a | words_b)
```

This is deliberately simple -- no LLM, no embeddings, no semantic analysis.
The point is to find lateral connections cheaply. A Jaccard score of 0.3 means
roughly a third of the combined vocabulary overlaps, which is enough to flag
a potential structural relationship worth investigating.

### Reading Dreams

- `get_recent_dreams(limit)`: returns newest associations first
- `strongest_resonances(threshold)`: returns associations with strength above
  threshold, sorted by strength descending


## How They Interact

```
Agents work on tasks
    |
    v
Leave stigmergic marks (observation, salience, connections)
    |
    v
Shakti perceives hot paths + high salience marks
    |
    v
Local proposals auto-approve, system proposals escalate to Darwin Engine
    |
    v
When stigmergy density crosses threshold (50 marks) -> Subconscious wakes
    |
    v
Dreams sample random marks -> find lateral associations via Jaccard
    |
    v
Dream marks re-enter lattice with action="dream" and salience=strength
    |
    v
Next Shakti scan picks up dream marks alongside regular marks
    |
    v
Cycle continues...
```

The feedback loop is the essential property. Dreams are not discarded -- they
become stigmergic marks that can trigger further perception, which can trigger
further dreams. A strong enough resonance (high Jaccard, high salience) will
surface through the Shakti perception loop as a system-level observation and
get escalated to the Darwin Engine for evaluation.

The colony does not need a central planner to discover cross-cutting concerns.
The lattice discovers them through accumulation, and the subconscious surfaces
them through random sampling. This is Aunt Hillary: intelligence emerging from
the interactions of simple agents following local rules.


## Fractal Autonomy Model

The three impact levels create a fractal structure where each layer has
appropriate autonomy:

- **Local actions** (impact_level="local"): Self-approve. Low risk, high speed.
  An agent notices a pattern in the file it is working on and leaves a mark.
  No escalation needed.

- **Module actions** (impact_level="module"): Propose to Darwin Engine. Medium
  risk. A Shakti perception identifies a connection between multiple files that
  suggests a refactoring. The proposal goes through gate-check and fitness
  evaluation before execution.

- **System actions** (impact_level="system"): Escalate to human or committee.
  High risk. A perception identifies a pattern that spans the entire codebase
  or contradicts existing policy. Human oversight is required before action.

The thresholds are simple: > 10 touches on a hot path = system, > 5 = module,
everything else = local. These can be tuned, but the principle holds: the more
a pattern involves, the more oversight it requires. Downward causation only --
higher layers constrain lower, never the reverse.


## What Is Not Yet Wired

Being honest about the gaps:

1. **SHAKTI_HOOK is not injected into agent system prompts**. The text exists
   in `shakti.py` but `startup_crew.py` does not include it. Agents do not
   currently perceive through the Shakti lens unless manually instructed.

2. **SubconsciousStream is not called from the daemon heartbeat**. The
   `should_wake()` / `dream()` cycle only fires on explicit CLI/TUI invocation.
   The subconscious is dormant unless you poke it.

3. **Stigmergy marks are not automatically left by agent tasks**. The
   `leave_stigmergic_mark()` convenience function exists, but `agent_runner.py`
   does not call it after task completion. Marks must be left manually or
   through future middleware.

4. **ShaktiLoop.perceive() is not called in any loop**. The perception
   infrastructure exists but nothing periodically runs it. It works when called
   from the TUI (`/stigmergy`) or CLI (`dgc stigmergy`), but there is no
   autonomous scanning.

These are not design failures -- the architecture is sound and the components
are tested. They are wiring gaps between independently functional modules that
will be connected in v2. The living layers exist; they are just not yet
breathing on their own.
