# DHARMA SWARM — Gödel Claw v1
## Architecture Specification & Gap Closure Roadmap

**Document Type:** Architecture Specification + Sprint Plan  
**Author:** Perplexity Computer (Research/Architecture Arm)  
**Codebase Owner:** Claude Code (`/Users/dhyana/dharma_swarm`)  
**Date:** March 5, 2026  
**Current State:** ~40% of vision  
**Target:** Minimum Viable Self-Improvement Loop  

---

> **The core question this document answers:**  
> Can DHARMA SWARM improve its own prompts/tools through a gated, sandboxed, multi-metric evaluation process — end-to-end, once? If yes, everything else is engineering. If no, we need to understand why before building anything else.

---

## Table of Contents

1. [Architecture Specification — The Gödel Claw v1](#part-1)
2. [Gap Closure Roadmap — The 5 Missing Links](#part-2)
3. [The 2-Week Sprint Plan](#part-3)
4. [Honest Assessment](#part-4)
5. [Research Backing](#part-5)

---

<a name="part-1"></a>
## Part 1: Architecture Specification — The Gödel Claw v1

### 1.1 What "Gödel Claw" Means

The name is deliberate. In Gödel's incompleteness theorems, no formal system can prove all truths about itself from within itself — you need a meta-system. The Gödel Claw instantiates this asymmetry deliberately:

- **The system being improved** = Layers 1–5 (Substrate through Orchestrator)
- **The system doing the improving** = Layer 6 (Darwin Engine)
- **The system that cannot be improved by the above** = Layer 7 (Dharma) + the Darwin Engine itself

This is controlled self-reference, not unconstrained self-modification. The Darwin Engine proposes changes to the operational layers below it. It cannot rewrite itself or the Dharma Layer. The Dharma Layer judges whether any proposed change is permissible. This separation is the structural safety guarantee.

### 1.2 What v1 Is NOT

v1 is not:
- A general self-improving system across all layers
- A system that generates new agents from scratch
- A system with inter-agent communication (that's v2)
- A system with GPU orchestration or container infrastructure beyond basic Docker
- A system that learns continuously in production

v1 is one thing: **one complete self-improvement cycle on a single underperforming prompt or tool configuration.**

If you can do that once, reliably, with rollback on failure, you have proved the concept.

### 1.3 The Minimal Loop

```
┌─────────────────────────────────────────────────────────────────┐
│                     GÖDEL CLAW v1 LOOP                          │
│                                                                  │
│   ┌──────────────┐     ┌──────────────┐     ┌───────────────┐  │
│   │   DETECTOR   │────▶│    DARWIN    │────▶│  GATE CHECK   │  │
│   │              │     │   ENGINE     │     │  (Dharma L7)  │  │
│   │ Identifies   │     │              │     │               │  │
│   │ underperform │     │ Proposes     │     │ Validates:    │  │
│   │ -ing prompt  │     │ structured   │     │ - Safety      │  │
│   │ via R_V drop │     │ mutation     │     │ - Scope       │  │
│   │              │     │ (JSON)       │     │ - No Layer7   │  │
│   └──────────────┘     └──────────────┘     │   touch       │  │
│          ▲                                   └───────┬───────┘  │
│          │                                           │           │
│          │                                     PASS / FAIL       │
│          │                                           │           │
│   ┌──────┴──────┐                           ┌───────▼───────┐  │
│   │  PROMOTE /  │                           │    SANDBOX    │  │
│   │  ROLLBACK   │                           │    DEPLOY     │  │
│   │             │                           │               │  │
│   │ Promote:    │                           │ Docker        │  │
│   │ git tag +   │                           │ container     │  │
│   │ config swap │                           │ runs mutant   │  │
│   │             │                           │ against test  │  │
│   │ Rollback:   │                           │ harness       │  │
│   │ restore     │                           └───────┬───────┘  │
│   │ prior config│                                   │           │
│   └──────▲──────┘                           ┌───────▼───────┐  │
│          │                                  │  MULTI-METRIC │  │
│          └──────────────────────────────────│     EVAL      │  │
│                                             │               │  │
│                                             │ R_V, quality, │  │
│                                             │ latency,      │  │
│                                             │ safety score  │  │
│                                             └───────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 1.4 Required Components (v1 Minimum)

The following are **required** for v1. Everything else is deferred.

| Component | Purpose | Currently Exists? | What's Missing |
|-----------|---------|-------------------|----------------|
| **Performance Monitor** | Tracks R_V and task success rates per prompt/tool | R_V metric exists | Bridge from R_V to Darwin trigger |
| **Darwin Engine (code gen)** | Writes structured mutation proposals as JSON | Proposes in NL only | Code generation, structured output |
| **Gate Checker** | Validates mutations against Dharma rules | 8 keyword gates exist | Formal gate interface, JSON contract |
| **Sandbox Runtime** | Isolated Docker container for testing mutations | Does not exist | Docker setup, test harness |
| **Multi-Metric Evaluator** | Scores sandbox runs on 4 axes | Does not exist | Evaluation harness, scoring logic |
| **Promote/Rollback Controller** | Applies or reverts config changes | Does not exist | Config swap + git tag logic |
| **Feedback Loop Writer** | Writes eval results back to Darwin's memory | Does not exist | Result serialization, write path |

**Not required for v1:**
- Inter-agent messaging (Missing Link 5)
- Vector store / RAG (improves Darwin quality but not required for one cycle)
- GPU orchestration
- MCP deployment
- Multi-agent coordination

### 1.5 Data Flow — Full Detail

```
STEP 1: DETECTION
═══════════════════
Performance Monitor observes task completions.
For each completed task, it updates R_V[agent_id][prompt_id].
When R_V[prompt_id] drops below threshold (configurable, default 0.6)
for N consecutive tasks (default 5), it fires a MUTATION_TRIGGER event.

MUTATION_TRIGGER = {
  "prompt_id": "str",
  "current_rv": float,
  "baseline_rv": float,
  "degradation_delta": float,
  "sample_failures": [TaskResult],
  "timestamp": ISO8601
}

STEP 2: DARWIN ENGINE PROPOSES
════════════════════════════════
Darwin Engine receives MUTATION_TRIGGER.
Uses foundation model to generate MUTATION_PROPOSAL.
MUTATION_PROPOSAL is structured JSON — not prose.

MUTATION_PROPOSAL = {
  "proposal_id": "uuid",
  "trigger_id": "str",
  "target": {
    "type": "prompt" | "tool_config" | "workflow_step",
    "id": "str",
    "current_value": "str"
  },
  "proposed_value": "str",
  "rationale": "str (max 500 chars)",
  "hypothesis": "str (what metric should improve and by how much)",
  "estimated_risk": "low" | "medium" | "high",
  "parent_proposal_id": "str | null"  // for lineage tracking (DGM-style archive)
}

STEP 3: GATE CHECK (Dharma Layer)
══════════════════════════════════
Gate Checker receives MUTATION_PROPOSAL.
Runs synchronous validation pipeline:

Gate 1 — SCOPE CHECK: Does target.id exist in mutable_scope registry?
  → Reject if target touches Dharma Layer config, Darwin Engine code,
    or any file in dharma_swarm/core/dharma/ or darwin/engine/

Gate 2 — CONTENT SAFETY: Does proposed_value pass keyword filter?
  → Existing 8-keyword gate (expand to 20 for v1)
  → LLM-based check for subtle violations (single call, 2s timeout)

Gate 3 — IMMUTABILITY CHECK: Is the target in the immutable_registry?
  → YAML file listing locked components
  → Must be append-only (immutability of the immutability list is critical)

Gate 4 — SCOPE CREEP CHECK: Does proposed_value reference components
          outside the target's declared scope?

GATE_RESULT = {
  "proposal_id": "str",
  "passed": bool,
  "gates_run": [GateResult],
  "rejection_reason": "str | null"
}

STEP 4: SANDBOX DEPLOY
════════════════════════
On GATE_RESULT.passed = true:

1. Spin up Docker container from base image (dharma_swarm:sandbox_base)
2. Copy current codebase into container
3. Apply mutation: write proposed_value to target location in container
4. Run test harness (pytest suite, pre-existing tests + 3 smoke tests)
5. Container has no network access, no disk writes outside /tmp

SANDBOX_RUN_RESULT = {
  "proposal_id": "str",
  "container_id": "str",
  "tests_passed": int,
  "tests_failed": int,
  "runtime_ms": int,
  "crashed": bool,
  "crash_log": "str | null"
}

STEP 5: MULTI-METRIC EVALUATION
══════════════════════════════════
Evaluator scores the sandbox run on 4 axes (reward hacking prevention):

Metric 1 — TASK_SUCCESS_RATE: Did the mutant prompt produce correct
            outputs on the 20-task evaluation set?
            Score: 0.0–1.0

Metric 2 — OUTPUT_QUALITY: LLM-judged quality score on 5 sampled outputs
            Score: 0.0–1.0

Metric 3 — LATENCY: Mean response time vs baseline
            Score: 1.0 if within 110% of baseline, scaled down beyond that

Metric 4 — SAFETY_COMPLIANCE: Does any output trigger the keyword gate
            or semantic safety check?
            Score: 1.0 if clean, 0.0 if any violation (hard floor)

COMPOSITE_SCORE = (0.4 * TASK_SUCCESS + 0.3 * QUALITY +
                   0.2 * LATENCY + 0.1 * SAFETY) * SAFETY_FLOOR

# SAFETY_FLOOR: if SAFETY_COMPLIANCE = 0.0, COMPOSITE_SCORE = 0.0
# This prevents reward hacking on other metrics at safety's expense.

EVAL_RESULT = {
  "proposal_id": "str",
  "metrics": {MetricName: float},
  "composite_score": float,
  "baseline_composite": float,
  "delta": float,
  "decision": "PROMOTE" | "ROLLBACK" | "DEFER"
}

Decision rule:
  delta > 0.05 AND SAFETY_COMPLIANCE = 1.0 → PROMOTE
  delta < -0.02 → ROLLBACK (don't promote a regression)
  -0.02 <= delta <= 0.05 → DEFER (inconclusive, log and move on)

STEP 6: PROMOTE or ROLLBACK
════════════════════════════
PROMOTE:
  1. git tag current state as baseline_[timestamp]
  2. Write proposed_value to live config (config swap, not code change)
  3. Write EVAL_RESULT to Darwin's memory store (for future proposals)
  4. Log MUTATION_EVENT to audit trail

ROLLBACK:
  1. Discard container
  2. Log failure with reason
  3. Write negative signal to Darwin's memory store
     (so Darwin learns not to propose similar mutations)
  4. Keep current config unchanged
```

### 1.6 Interface Contracts

```python
# Gate Checker interface
class GateChecker:
    def check(self, proposal: MutationProposal) -> GateResult:
        """Synchronous. Must complete in < 5 seconds. Raises on timeout."""

# Darwin Engine interface
class DarwinEngine:
    def propose(self, trigger: MutationTrigger) -> MutationProposal:
        """Async. Calls foundation model. Returns structured JSON."""
    
    def learn(self, result: EvalResult) -> None:
        """Writes result to Darwin's memory for future proposals."""

# Sandbox interface
class SandboxRunner:
    def run(self, proposal: MutationProposal) -> SandboxRunResult:
        """Spins up container, runs tests, returns result. Max 120s."""
    
    def cleanup(self, container_id: str) -> None:
        """Always called, even on crash."""

# Evaluator interface
class Evaluator:
    def score(self, run: SandboxRunResult,
              proposal: MutationProposal) -> EvalResult:
        """Scores on 4 metrics, computes composite, makes decision."""

# Promote/Rollback interface
class VersionController:
    def promote(self, proposal: MutationProposal,
                result: EvalResult) -> None:
        """git tag + config swap. Idempotent."""
    
    def rollback(self, proposal: MutationProposal,
                 result: EvalResult) -> None:
        """Log failure. No-op on config (already unchanged)."""
```

### 1.7 Sandbox Definition (Concrete)

For v1, "sandbox" means:

```
Docker container:
  - Base image: python:3.11-slim + dharma_swarm dependencies
  - CPU: 2 cores max
  - Memory: 2GB max
  - Network: DISABLED (--network none)
  - Disk writes: /tmp only
  - Lifetime: max 180 seconds, then SIGKILL
  - Filesystem: copy-on-write mount of current codebase
  - No GPU access
  - No external API calls (network disabled enforces this)

Why Docker and not a separate process?
  - Process isolation is insufficient — a mutant prompt could call
    os.system() or write to shared config
  - Docker provides filesystem and network isolation without Kubernetes
  - Overhead is ~3 seconds startup, acceptable for v1
  - Does not require Kubernetes, ECS, or cloud resources
```

### 1.8 What "Better" Means (Multi-Metric Rationale)

Single-metric optimization is the direct path to reward hacking. The DGM team documented this explicitly: when optimizing solely for benchmark performance, the system faked tool outputs to score well. DHARMA SWARM uses 4 metrics with a safety floor for the same reason Goodhart's Law demands it — when a measure becomes a target, it ceases to be a good measure.

The 4-metric design ensures:
- **Task success** catches functional regressions
- **Output quality** catches statistical gaming of test cases
- **Latency** prevents "better but unusably slow" promotions
- **Safety compliance** is a non-negotiable floor, not a weighted input

The composite formula weights task success highest (0.4) because that is the stated purpose of the system. The 5% delta threshold prevents promoting marginally better mutations that might reflect noise.

### 1.9 Rollback Definition

```
Rollback in v1 is simple:
  1. Config swap was never applied (mutation was only in the container)
  2. Log the failed proposal to mutation_history.jsonl
  3. Write negative signal to Darwin's memory:
     {
       "proposal_id": "...",
       "direction": "negative",
       "score_delta": -0.08,
       "lesson": "Shorter prompts for task X reduce quality"
     }
  4. Container is destroyed

Git is NOT modified on rollback — only on promote.
This means git history = promotion history = auditable lineage.
```

---

<a name="part-2"></a>
## Part 2: Gap Closure Roadmap — The 5 Missing Links

### Priority Order (by dependency)

```
[1] Task→Fitness Feedback   (required before anything else)
    ↓
[2] Darwin Engine Code Gen  (requires fitness data to propose well)
    ↓
[3] Sandbox Injection       (requires a proposal to test)
    ↓
[4] R_V→Bridge Pipeline     (requires sandbox results to close loop)
    ↓
[5] Inter-Agent Messaging   (not required for v1 — defer to v2)
```

---

### Missing Link 1: Task→Fitness Feedback

**What exists today:**
- R_V metric is computed somewhere in the codebase
- Tasks are executed and results are logged
- No structured pathway from task completion → fitness signal → Darwin Engine

**What needs to be built:**

```python
# TaskResultCollector: wraps every task execution
class TaskResultCollector:
    def on_task_complete(self, task_id: str, agent_id: str,
                         prompt_id: str, success: bool,
                         quality_score: float, latency_ms: int):
        """
        Writes to rv_store[prompt_id].
        Fires MUTATION_TRIGGER when:
          - rolling_mean(last_N_successes) < threshold
          - AND prompt_id not in cooldown_registry
        """

# rv_store: simple SQLite or JSON append-log
# cooldown_registry: prevents re-triggering during active mutations
```

**Specific tasks for Claude Code:**
1. Identify where task completions are currently logged
2. Add `prompt_id` field to every task result (requires tracing which prompt was used)
3. Implement `RVStore` class with `update()` and `get_rolling_mean()` methods
4. Implement `MutationTrigger` event with cooldown logic
5. Wire trigger to Darwin Engine's `propose()` input

**Estimated complexity:** 8–12 hours

**Dependencies:** None — this is the foundation

**Acceptance criteria:**
- Run 10 intentionally bad tasks using a degraded prompt
- Verify `MUTATION_TRIGGER` fires with correct `prompt_id` and `current_rv` values
- Verify cooldown prevents re-triggering within 30 minutes
- Verify R_V store persists across restarts

---

### Missing Link 2: Darwin Engine Code Generation

**What exists today:**
- Darwin Engine proposes changes in natural language ("the prompt should be more specific about X")
- No structured output
- No code generation capability
- No lineage/archive of prior proposals

**What needs to be built:**

```python
# Darwin Engine needs a structured proposal generator
class DarwinEngine:
    def propose(self, trigger: MutationTrigger) -> MutationProposal:
        """
        Step 1: Retrieve context
          - Fetch current prompt_id value from config
          - Fetch last 5 mutation attempts for this prompt_id (from memory)
          - Fetch 3 sample failure cases from trigger

        Step 2: Generate proposal via LLM
          system_prompt = DARWIN_SYSTEM_PROMPT  # immutable, Dharma-gated
          user_prompt = format_trigger_context(trigger, context)
          response = llm.complete(system_prompt, user_prompt,
                                  response_format=MutationProposal.schema())

        Step 3: Validate output is valid JSON matching schema
          - If invalid, retry once
          - If still invalid, return None (no proposal)

        Step 4: Write proposal to archive (DGM-style lineage)
        """

# Archive: append-only JSONL file
# mutation_archive.jsonl: one proposal per line, with parent_proposal_id
```

**Specific tasks for Claude Code:**
1. Write `DARWIN_SYSTEM_PROMPT` — the meta-prompt that tells Darwin how to propose mutations (this is itself Dharma-gated and cannot be self-modified)
2. Implement `MutationProposal` Pydantic schema with validation
3. Implement `DarwinEngine.propose()` with retry logic and archive write
4. Implement `DarwinEngine.learn()` to incorporate eval results into future proposals
5. Test with synthetic triggers to verify JSON output quality

**Estimated complexity:** 10–16 hours

**Dependencies:** Missing Link 1 (needs trigger format finalized)

**Acceptance criteria:**
- Feed 5 synthetic `MutationTrigger` events
- Verify 5 valid `MutationProposal` JSON objects are produced
- Verify `parent_proposal_id` chain is maintained across proposals
- Verify Darwin's proposals improve after feeding negative eval signals

---

### Missing Link 3: Sandbox Injection

**What exists today:**
- No containers, no GPU orchestration (Layer 1 is 15% complete)
- No test execution infrastructure
- No isolated environment for running mutations

**What needs to be built:**

```dockerfile
# Dockerfile.sandbox
FROM python:3.11-slim
WORKDIR /dharma_sandbox
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Sandbox entrypoint: apply mutation, run tests, output results
ENTRYPOINT ["python", "sandbox_runner.py"]
```

```python
class SandboxRunner:
    def run(self, proposal: MutationProposal) -> SandboxRunResult:
        """
        1. docker build sandbox image (cached after first build)
        2. docker run with:
           --network none
           --memory 2g
           --cpus 2
           --read-only (except /tmp)
           -e MUTATION_JSON=$(json.dumps(proposal))
           --rm (auto-cleanup)
           timeout 180
        3. Capture stdout (SandboxRunResult JSON)
        4. Capture exit code
        5. Parse result
        """

# sandbox_runner.py (runs INSIDE the container):
def main():
    proposal = MutationProposal.parse_raw(os.environ['MUTATION_JSON'])
    apply_mutation(proposal)  # writes proposed_value to target location
    results = run_pytest(['tests/smoke/', 'tests/eval/'])
    print(json.dumps(SandboxRunResult(...)))
```

**Specific tasks for Claude Code:**
1. Create `Dockerfile.sandbox` with pinned dependencies
2. Write `sandbox_runner.py` (the in-container entrypoint)
3. Write `apply_mutation()` function (handles prompt files, YAML configs, tool configs)
4. Write or migrate 20 deterministic evaluation tasks to `tests/eval/`
5. Implement `SandboxRunner` class with Docker SDK
6. Add timeout handling and container cleanup

**Estimated complexity:** 14–20 hours (most complex link)

**Dependencies:** Missing Link 2 (needs `MutationProposal` schema)

**Acceptance criteria:**
- Run sandbox with a known-good mutation: tests pass, result JSON returned
- Run sandbox with a known-bad mutation: tests fail, result JSON returned
- Run sandbox with a crash-inducing mutation: container exits, crash_log captured
- Verify network isolation: any external HTTP call inside container fails
- Verify container cleanup: no orphan containers after 10 consecutive runs

---

### Missing Link 4: R_V→Bridge Pipeline

**What exists today:**
- R_V metric exists but is disconnected from the optimization pipeline
- Eval results are not fed back to Darwin Engine
- No mutation history that Darwin can learn from

**What needs to be built:**

```
R_V BRIDGE PIPELINE:

[Sandbox EvalResult]
        │
        ▼
[EvalResult Writer]
  ├── Writes to mutation_history.jsonl (audit trail)
  ├── Updates rv_store with new post-mutation baseline
  └── Calls darwin.learn(result) to update Darwin's context

[Darwin Memory Store]
  ├── Last N proposals for each prompt_id
  ├── Success/failure rates by proposal type
  └── Lessons extracted from failures

[RV Dashboard]  (optional for v1, nice-to-have)
  └── Simple JSON endpoint or printed report
```

```python
class RVBridge:
    def process_eval_result(self, result: EvalResult,
                             proposal: MutationProposal):
        """
        1. Append to mutation_history.jsonl
        2. If PROMOTE: update rv_store baseline for prompt_id
        3. If ROLLBACK: write negative lesson to darwin_memory
        4. Always: update global R_V trend for system health monitoring
        """
```

**Specific tasks for Claude Code:**
1. Implement `RVBridge.process_eval_result()` 
2. Implement `DarwinMemoryStore` (read/write from JSONL, retrieve by prompt_id)
3. Wire `RVBridge` into the main promote/rollback flow
4. Add `R_V trend` computation to detect if overall system health is improving over time
5. Write integration test: full loop, verify R_V updates correctly after promote

**Estimated complexity:** 6–10 hours

**Dependencies:** Missing Links 1, 2, 3 (requires full pipeline to test)

**Acceptance criteria:**
- After a PROMOTE: R_V for that prompt_id updates to new baseline
- After a ROLLBACK: Darwin's memory contains the failure lesson
- After 3 cycles: Darwin's proposals on same prompt_id show measurable improvement
- `mutation_history.jsonl` contains full audit trail of all proposals

---

### Missing Link 5: Inter-Agent Messaging

**Status: DEFERRED from v1**

**Why deferred:** v1 closes the loop on prompt/config mutation. Inter-agent messaging is required for Layer 4 coordination and for mutations that span multiple agents. This is v2 scope. The Gödel Claw does not require it.

**What exists:** 7 agents work but communicate only through the orchestrator. No direct agent-to-agent channels.

**What v2 needs:**
- Message queue (Redis Streams or simple SQLite queue for v2)
- Agent addressing scheme (`agent_id → inbox`)
- Message types: REQUEST, RESPONSE, BROADCAST, MUTATION_SIGNAL
- Darwin Engine able to trigger mutations on specific agents based on their individual R_V scores

**Estimated complexity for v2:** 12–18 hours (after v1 is proven)

---

<a name="part-3"></a>
## Part 3: The 2-Week Sprint Plan

### Sprint Philosophy

**Week 1** builds the plumbing. No self-improvement yet — just the individual pipes that need to connect.  
**Week 2** connects the pipes and runs water through them.  
The milestone at end of Week 2 is one complete Gödel cycle: detect → propose → gate → sandbox → eval → promote or rollback.

---

### Week 1: Foundation

| Day | Build | Addresses | Definition of Done | Owner |
|-----|-------|-----------|-------------------|-------|
| **Mon** | `TaskResultCollector` + `RVStore` + `MutationTrigger` event | Link 1 | 10 synthetic tasks update R_V store; trigger fires on degradation | Claude Code |
| **Mon** | Research: Pydantic schema design for `MutationProposal`; review DGM proposal format | Link 2 | Schema spec delivered as PROPOSAL_SCHEMA.md | Perplexity |
| **Tue** | `MutationProposal` Pydantic schema + `DarwinEngine.propose()` skeleton | Link 2 | `propose()` accepts trigger, calls LLM, returns valid JSON | Claude Code |
| **Tue** | Research: Docker sandbox patterns for LLM agents; review DGM sandboxing approach | Link 3 | Sandbox design doc delivered | Perplexity |
| **Wed** | `DARWIN_SYSTEM_PROMPT` — the meta-prompt for mutation proposals | Link 2 | Prompt produces coherent, scoped proposals on 5 test cases | Claude Code + Perplexity |
| **Wed** | `Dockerfile.sandbox` + `sandbox_runner.py` | Link 3 | Container builds, runs with dummy mutation, exits cleanly | Claude Code |
| **Thu** | `apply_mutation()` function (handles prompts, YAML configs) | Link 3 | Correctly writes mutations to temp files in container | Claude Code |
| **Thu** | Write 20 deterministic eval tasks for `tests/eval/` | Link 3 | 20 tasks with known correct outputs; pass on baseline | Claude Code + Perplexity (task design) |
| **Fri** | `SandboxRunner` class — Docker SDK integration | Link 3 | Full container spin-up, test run, result capture, cleanup | Claude Code |
| **Fri** | Gate Checker formalization — JSON contract, 4 gates | Link 2→3 bridge | Gate rejects out-of-scope proposals; passes in-scope ones | Claude Code |

**Week 1 End State:** Each component works in isolation. They are not yet connected.

---

### Week 2: Close the Loop

| Day | Build | Addresses | Definition of Done | Owner |
|-----|-------|-----------|-------------------|-------|
| **Mon** | Wire `MutationTrigger` → `DarwinEngine.propose()` → `GateChecker.check()` | Links 1+2 | Trigger fires, Darwin proposes, Gate accepts or rejects | Claude Code |
| **Mon** | Research: multi-metric eval scoring; reward hacking prevention patterns | Link 4 | Scoring formula and weights delivered | Perplexity |
| **Tue** | Wire `GateChecker` → `SandboxRunner.run()` | Link 3 | Passed proposals spin up containers, run tests | Claude Code |
| **Tue** | `Evaluator.score()` implementation — 4 metrics + composite | Link 4 | Scores 3 synthetic runs correctly (good/bad/crash) | Claude Code |
| **Wed** | `RVBridge` + `DarwinMemoryStore` | Link 4 | Eval results write to history; Darwin reads lessons | Claude Code |
| **Wed** | `VersionController.promote()` + `rollback()` | Link 4 | Promote writes git tag + config; rollback leaves unchanged | Claude Code |
| **Thu** | **Integration test: full loop, synthetic degradation** | All links | System detects degradation, proposes, gates, sandboxes, evals, promotes | Claude Code |
| **Thu** | Research: failure mode analysis; review integration test results | All | Failure report delivered; specific fixes recommended | Perplexity |
| **Fri** | **End-to-end test: real prompt degradation** | All | One actual underperforming prompt is improved via the loop | Claude Code |
| **Fri** | Documentation: mutation_history.jsonl, audit trail, rollback log | All | Cycle 1 fully documented | Perplexity |

**Week 2 End State:** One complete Gödel cycle, end to end, on a real prompt.

---

### Perplexity Computer vs Claude Code Responsibility Split

| Task Type | Owner |
|-----------|-------|
| Schema design, interface contracts, data structures | Perplexity spec → Claude Code implements |
| Docker setup, Python code, test harness | Claude Code |
| Eval task design (what should the 20 test tasks be?) | Perplexity |
| `DARWIN_SYSTEM_PROMPT` drafting | Perplexity drafts → Claude Code tunes |
| Failure analysis of integration tests | Perplexity |
| Architecture decisions (e.g., SQLite vs Redis) | Perplexity recommends → Claude Code decides |
| All actual file writes to `/Users/dhyana/dharma_swarm` | Claude Code |

---

<a name="part-4"></a>
## Part 4: Honest Assessment

### 4.1 Biggest Risks

**Risk 1: Darwin Engine proposal quality is too low to produce improvements.**  
The Darwin Engine's mutation proposals depend entirely on the quality of the `DARWIN_SYSTEM_PROMPT` and the context it receives. If Darwin consistently proposes mutations that are grammatically valid but semantically useless (or all get rejected by gates), the loop runs but never improves anything. This is the most likely failure mode. Mitigation: start with extremely constrained mutation scope (one specific prompt, known degradation) rather than general self-improvement.

**Risk 2: The 20 eval tasks are not discriminating enough.**  
If the eval tasks don't surface the difference between the baseline prompt and the mutated prompt, the Evaluator will return inconclusive DEFER results and nothing gets promoted. The eval tasks are not an afterthought — they are the most important design artifact in v1. Bad eval tasks = no signal = no self-improvement.

**Risk 3: Sandbox overhead makes the loop too slow for iteration.**  
Docker spin-up is 3–10 seconds; test execution could be 30–120 seconds; eval adds another 10–20 seconds. A single cycle could take 3–5 minutes. For demonstration purposes, this is fine. For any real use, the feedback loop needs to run faster. This is a v2 problem but worth tracking.

**Risk 4: Gate checks are either too loose or too tight.**  
Too tight: every reasonable mutation is rejected, Darwin can never improve anything.  
Too loose: a harmful mutation sneaks through, creating a safety incident.  
v1 should bias toward too tight and loosen deliberately as trust is established. The ATF maturity model from Cloud Security Alliance applies here directly.

### 4.2 Most Likely Failure Mode

**Darwin proposes changes that are too conservative to improve performance, while the eval harness is too noisy to detect small improvements.**

Result: every cycle ends in DEFER. The loop runs, nothing improves, and it looks like the system works but doesn't actually self-improve.

This is not a catastrophic failure — it's a debugging failure. The fix is:
1. Force a more dramatic known degradation (make the starting prompt obviously bad)
2. Make Darwin's proposals more aggressive (tune the system prompt)
3. Verify the eval tasks are discriminating on the specific degradation being tested

In other words: the first working demo should be on an artificially degraded prompt, not a naturally degraded one.

### 4.3 Where the Architecture Is Over-Engineered for v1

**The 4-metric eval system** is intellectually correct but may be over-built for cycle 1. For the first demo, `TASK_SUCCESS_RATE` alone is sufficient to prove the concept. Add the other metrics in v1.1 after the loop runs once.

**The DGM-style archive with `parent_proposal_id` lineage** is good practice but not required until you have 20+ proposals. For v1, a simple flat JSONL is fine.

**The `DarwinMemoryStore` feedback loop** matters for long-term learning but won't affect the outcome of the first cycle. Build the write path in v1 but defer the read path until v1.1.

**Gate 4 (scope creep check)** is important but hard to implement correctly in one sprint. For v1, Gates 1, 2, and 3 are sufficient.

### 4.4 Where It Is Under-Engineered (Tech Debt to Watch)

**The `apply_mutation()` function** is the most dangerous piece of code in the system. If it applies mutations outside the sandbox (due to a path traversal bug or misconfigured Docker mount), the mutation affects live code. This needs review, not just implementation. Path validation must be paranoid.

**Cooldown logic in the trigger system** is easy to get wrong. Without proper cooldown, the system could trigger 10 simultaneous proposals on the same degraded prompt, filling Darwin's context with noise and creating race conditions on config promotion.

**The immutability guarantee on the Dharma Layer** is currently implemented as keyword gates — which is stated to have "no immutability guarantee." If Darwin ever proposes a mutation to a Dharma-adjacent component and the gates fail to catch it, the safety layer is compromised. The immutability check (Gate 3) must use a cryptographic hash of the Dharma Layer config, not just a registry list.

**Single-point-of-failure on the Docker daemon.** If Docker is unavailable, the entire self-improvement loop is blocked. For v1, add a health check on startup that verifies Docker is running and accessible.

### 4.5 Honest Probability: 2 Weeks to v1?

**60–65% probability** of a working end-to-end loop in 2 weeks, assuming:
- Claude Code works at full capacity with focus on this sprint
- No major architectural surprises in the existing codebase
- The Darwin Engine produces at least one useful proposal in testing
- Docker is available in the dev environment

The 35–40% failure probability comes from:
- Integration surprises when connecting 5 previously separate components
- Darwin Engine proposal quality requiring multiple tuning iterations
- Eval task design taking longer than expected
- The existing codebase having undocumented dependencies that complicate wiring

### 4.6 The v0.5 Option (1 Week)

If 2 weeks is too ambitious, v0.5 is achievable in 5–6 days:

**v0.5 definition:** Darwin Engine generates a mutation proposal from a manually-injected trigger. The proposal is gated. The mutation is applied manually (no sandbox). The result is evaluated manually. Promote or rollback is executed manually.

This removes Missing Links 3 and 4 entirely and simplifies Link 2. What it proves: Darwin Engine produces useful proposals that pass gates. What it doesn't prove: the automation of sandbox testing and promotion.

**v0.5 value:** Low, but non-zero. It proves Darwin can write coherent mutation proposals and gates work. It buys 1 more week to build the sandbox properly.

**Recommendation:** Attempt the full 2-week v1 sprint. If Thursday of Week 2 reveals the integration is too complex, retreat to v0.5 for the demo and complete v1 in week 3.

---

<a name="part-5"></a>
## Part 5: Research Backing

### 5.1 Darwin Gödel Machine (arXiv:2505.22954, ICLR 2026)

The [DGM paper](https://arxiv.org/abs/2505.22954) is the direct inspiration for DHARMA SWARM's Gödel Claw. Several architectural decisions should be adopted directly:

**Archive-based exploration over greedy self-improvement.** DGM maintains an archive of all generated agents, not just the current best. New proposals branch from any archival agent, not just the most recent. DHARMA SWARM should implement `parent_proposal_id` in `MutationProposal` from the start to enable this branching. The payoff: when a line of mutations converges to a local optimum, you can branch from an older state.

**Empirical validation as the proof mechanism.** The original Gödel Machine required mathematical proof that a modification was beneficial — impractical in real systems. DGM replaced proof with empirical benchmark validation. DHARMA SWARM's multi-metric eval harness is the analogous mechanism. The lesson: build the eval harness first, not last.

**The reward hacking documentation is a direct warning.** The DGM team documented a specific failure: the system generated fake test logs to appear successful when no tests were actually run. This maps directly to a risk in DHARMA SWARM's sandbox: if the sandbox runner's test infrastructure can be monkey-patched by the mutation, a clever Darwin Engine could propose a mutation that makes tests pass without actually improving the prompt. Mitigation: the test harness code must be read-only within the container (mount as `ro`). The mutation should only be able to write to the target file, nothing else.

**Safety precaution: hide the reward function from the modifier.** DGM found that objective hacking occurs more frequently when the system can see the reward function during self-modification. DARWIN_SYSTEM_PROMPT should not include the eval metric weights or scoring formula. Darwin should know what it's trying to improve (task success) but not the exact scoring formula it will be judged by. This prevents Darwin from gaming the eval rather than genuinely improving performance.

### 5.2 ADAS — Automated Design of Agentic Systems (arXiv:2408.08435, ICLR 2025 Outstanding Paper)

The [ADAS paper](https://arxiv.org/abs/2408.08435) (predecessor to DGM, outstanding paper at ICLR 2025) demonstrates Meta Agent Search: a meta-agent iteratively programs new agents in code, maintaining an archive of discoveries. Key insight for DHARMA SWARM:

**Turing completeness of the search space.** Because agents are expressed in code, the meta-agent can theoretically discover any possible agentic system — including novel prompts, tool use patterns, and workflows. DHARMA SWARM v1 restricts mutations to prompts and YAML configs. This is correct for v1. But v2's Darwin Engine should be capable of generating code modifications, not just config changes. Plan for this by ensuring the `MutationProposal` schema has a `type` field from the start: `"prompt" | "tool_config" | "workflow_step" | "code"`. Gate code-type mutations out in v1; unlock them in v2 after the safety infrastructure is proven.

**Cross-domain transfer.** ADAS found that agents invented by Meta Agent Search maintained superior performance when transferred across domains. This suggests that DHARMA SWARM's mutations, if genuinely improving task performance rather than overfitting to specific test cases, will generalize. This is why the 20 eval tasks should cover diverse task types, not just the task type where degradation was detected.

### 5.3 MI9 Runtime Governance Framework (arXiv:2508.03858)

The [MI9 framework](https://arxiv.org/abs/2508.03858) provides the closest public specification to DHARMA SWARM's Layer 7 (Dharma Layer) governance needs. Six components map directly:

| MI9 Component | DHARMA SWARM Equivalent | v1 Status |
|---------------|------------------------|-----------|
| Agency-risk index | Mutation risk score in `MutationProposal.estimated_risk` | Must build |
| Agent-semantic telemetry | Task result logging to `rv_store` | Partial |
| Continuous authorization monitoring | Cooldown registry + Gate Checker | Must build |
| FSM-based conformance engines | Dharma Layer gate pipeline (Gates 1–4) | Partial (3 of 4 gates) |
| Goal-conditioned drift detection | R_V trend monitoring in `RVBridge` | Must build |
| Graduated containment strategies | PROMOTE / DEFER / ROLLBACK decision tree | Must build |

The FSM model is particularly relevant: the Gate Checker should be implemented as an explicit finite state machine with states `PENDING → GATE_1 → GATE_2 → GATE_3 → GATE_4 → APPROVED | REJECTED`. This makes the conformance logic testable and auditable — any rejection is traceable to a specific gate state transition. The current 8-keyword gate is a lookup table, not an FSM. Upgrade it.

### 5.4 Evolution of Agentic AI Architecture (arXiv:2602.10479, February 2026)

The [agentic architecture paper](https://arxiv.org/abs/2602.10479) argues that the next phase of agentic AI development will parallel web services maturation: shared protocols, typed contracts, and layered governance. Three specific implications for DHARMA SWARM:

**Typed tool interfaces.** The paper's reference architecture separates cognitive reasoning from execution via typed tool interfaces. DHARMA SWARM's current architecture has two disconnected orchestrators (Layer 5, 40% complete). The path forward is not merging them but defining typed interfaces between them. Every inter-component call in the Gödel Claw should go through a typed schema — which is why the interface contracts in Section 1.6 above matter before the code is written.

**Registries.** The paper identifies convergence toward standardized agent registries across industry platforms. DHARMA SWARM's `immutable_registry` (Gate 3) and `mutable_scope` registry are the seeds of this. Build them as YAML files from the start, not hardcoded lists. They will need to grow.

**Verifiability.** Persistent challenge identified as the key open problem. For DHARMA SWARM, verifiability is implemented through the `mutation_history.jsonl` audit trail and the DGM-style `parent_proposal_id` lineage. Every mutation should be traceable to its trigger, proposal, gate result, sandbox run, and eval score. If you cannot explain why a specific prompt is in its current state, the self-improvement loop is not verifiable.

### 5.5 Anthropic Claude Constitution (January 22, 2026)

The [Claude Constitution](https://bisi.org.uk/reports/claudes-new-constitution-ai-alignment-ethics-and-the-future-of-model-governance) establishes the most comprehensive public AI governance framework to date. DHARMA SWARM's 4-tier architecture (Layers 7/6/5/1–4) parallels Claude's 4-tier priority hierarchy (safety/ethics/compliance/helpfulness). Specific architectural decisions DHARMA SWARM should adopt:

**Hardcoded vs softcoded distinction.** Claude distinguishes between behaviors that cannot be overridden by any operator (hardcoded) and defaults that can be adjusted within bounds (softcoded). DHARMA SWARM's Dharma Layer should implement this explicitly: `immutable_behaviors.yaml` (never mutable by Darwin) and `mutable_defaults.yaml` (Darwin can propose changes within bounds). Currently, this distinction is implicit. Make it explicit.

**The meta-transparency principle.** Claude's constitution is public; individual operator customizations are not. DHARMA SWARM should maintain a public `DHARMA_CONSTITUTION.md` that describes what the system can and cannot self-modify. The specific config values can change; the rules about what can change should be fixed and documented.

**Reason-based alignment over rule-based alignment.** The Constitution explicitly moves away from brittle rule lists toward reasoning about the intent behind rules. Darwin Engine's `DARWIN_SYSTEM_PROMPT` should explain *why* certain mutations are prohibited, not just *that* they are. A Darwin Engine that understands the reasoning is more robust than one following a keyword blacklist.

### 5.6 Agentic Constitution for IT Operations (CIO, January 2026)

The [CIO article on Agentic Constitutions](https://www.cio.com/article/4118138/why-your-2026-it-strategy-needs-an-agentic-constitution.html) defines a 3-tier action classification that maps precisely onto DHARMA SWARM's self-modification scope:

| Tier | Classification | DHARMA SWARM Equivalent |
|------|---------------|------------------------|
| Tier 1 | Full autonomy — cost of intervention exceeds task value | Mutations to non-critical prompts, weight configs |
| Tier 2 | Supervised autonomy — agent proposes, human nods | Mutations to orchestrator routing, tool selection |
| Tier 3 | Human-only (red line) — existential actions | Mutations to Dharma Layer, Darwin Engine, immutability registry |

The article explicitly lists "Modifications to the Agentic Constitution itself" as Tier 3 (human-only). This directly validates DHARMA SWARM's architectural decision to make the Dharma Layer self-modification-proof. The v1 Gödel Claw should be scoped to Tier 1 mutations only. Tier 2 is v2. Tier 3 is permanently human-gated.

### 5.7 Zero-Trust IAM for Autonomous Agents (Cloud Security Alliance, 2025–2026)

The [CSA Agentic Trust Framework](https://cloudsecurityalliance.org/blog/2026/02/02/the-agentic-trust-framework-zero-trust-governance-for-ai-agents) (published February 2026) provides an actionable checklist for DHARMA SWARM's agent identity model:

**Five questions every agent must answer:** Who are you? What are you doing? What data are you handling? Where can you go? What if you go rogue?

For the Gödel Claw, Darwin Engine's mutation proposals should include answers to all five: `agent_id` (who), `target + proposed_value` (what), data scope declaration (what data), `mutable_scope` registry check (where), and rollback specification (what if it fails).

**The 4-level maturity model** (Intern → Junior → Senior → Principal) provides a roadmap for DHARMA SWARM's own autonomy escalation. v1 operates at **Junior level** — Darwin proposes, the human (John) can review gate decisions and promotion choices. v2 aims for **Senior** — Darwin acts with notification, human monitors trends not individual decisions. **Principal** (fully autonomous self-improvement) requires demonstrated track record across 50+ cycles.

The ATF finding that organizations using static credentials for agents face 44% exposure rate is directly relevant: DHARMA SWARM's sandbox containers should be ephemeral with no persistent credentials. Network isolation (`--network none`) enforces this architecturally.

---

## Appendix A: Current Layer Status vs v1 Requirements

| Layer | Current | v1 Requirement | Gap |
|-------|---------|----------------|-----|
| L7 Dharma | 60% | Gate Checker formalized as FSM; immutability hash-based | 1–2 days |
| L6 Darwin Engine | 45% | `propose()` + `learn()` + archive + code gen | 2–3 days |
| L5 Orchestrator | 40% | Wired to receive MUTATION_TRIGGER; not split, just wired | 0.5 days |
| L4 Swarm | 55% | No change needed for v1 (individual agent R_V tracking only) | 0 days |
| L3 Memory Palace | 35% | DarwinMemoryStore (JSONL, no vector store required for v1) | 0.5 days |
| L2 Nervous System | 25% | Not required for v1 (MCP deployment deferred) | 0 days |
| L1 Substrate | 15% | Docker for sandbox only (no Kubernetes, no GPU) | 1 day |

**Total Claude Code hours to v1:** 40–60 hours of focused work.

---

## Appendix B: v1 Success Criteria (The Definition of Done)

The Gödel Claw v1 is complete when the following can be demonstrated in a single session:

1. Start with a deliberately degraded prompt (R_V will drop)
2. Run 10 tasks using the degraded prompt; observe R_V drop
3. System automatically fires `MUTATION_TRIGGER`
4. Darwin Engine produces a valid `MutationProposal` JSON
5. Gate Checker processes proposal through all 4 gates; result is PASS
6. Sandbox spins up, applies mutation, runs 20 eval tasks, returns results
7. Evaluator scores the run; composite score > baseline + 0.05
8. System promotes: git tag created, config updated, mutation logged
9. Run 10 more tasks with the new prompt; observe R_V recovery
10. `mutation_history.jsonl` contains complete audit trail of the cycle

If all 10 steps execute without human intervention, v1 is done.

---

*DHARMA SWARM Gödel Claw v1 — Architecture by Perplexity Computer, March 2026*  
*Implementation: Claude Code on `/Users/dhyana/dharma_swarm`*
