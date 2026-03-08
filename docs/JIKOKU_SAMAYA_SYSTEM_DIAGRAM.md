# JIKOKU SAMAYA — System Architecture Diagrams

**Version**: 1.0
**Date**: 2026-03-08

---

## 1. High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DHARMA SWARM SYSTEM                                │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    JIKOKU SAMAYA Instrumentation                     │   │
│  │                         (Deep OS Integration)                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                     │                                         │
│                                     ▼                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │   Provider   │  │    Swarm     │  │  Evolution   │  │    Agent     │   │
│  │ Interceptors │  │ Interceptors │  │ Interceptors │  │ Interceptors │   │
│  │              │  │              │  │              │  │              │   │
│  │ • Anthropic  │  │ • spawn()    │  │ • propose()  │  │ • execute()  │   │
│  │ • OpenAI     │  │ • task()     │  │ • gate()     │  │ • task loop  │   │
│  │ • OpenRouter │  │ • dispatch() │  │ • evaluate() │  │              │   │
│  │ • NVIDIA     │  │              │  │ • archive()  │  │              │   │
│  │ • ClaudeCode │  │              │  │              │  │              │   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘   │
│         │                 │                 │                 │             │
│         └─────────────────┴─────────────────┴─────────────────┘             │
│                                     │                                         │
│                                     ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      Span Creation & Management                      │   │
│  │                                                                       │   │
│  │  • jikoku_auto_span() context manager                               │   │
│  │  • @jikoku_traced_provider decorator                                │   │
│  │  • Nested span tracking (parent-child)                              │   │
│  │  • Async context propagation                                        │   │
│  │  • Metadata aggregation (tokens, cost, model)                       │   │
│  └───────────────────────────────┬─────────────────────────────────────┘   │
│                                     │                                         │
│                                     ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                       JikokuTracer Core                              │   │
│  │                                                                       │   │
│  │  • Span ID generation                                                │   │
│  │  • Timestamp capture (ISO 8601 UTC)                                 │   │
│  │  • Duration calculation                                              │   │
│  │  • Active span tracking                                              │   │
│  └───────────────────────────────┬─────────────────────────────────────┘   │
│                                     │                                         │
│                                     ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     Storage (JIKOKU_LOG.jsonl)                       │   │
│  │                                                                       │   │
│  │  • Append-only JSONL (atomic writes)                                │   │
│  │  • ~/.dharma/jikoku/JIKOKU_LOG.jsonl                                │   │
│  │  • One span per line                                                 │   │
│  │  • Rotation: 30-day retention                                        │   │
│  └───────────────────────────────┬─────────────────────────────────────┘   │
│                                     │                                         │
│                                     ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                       Kaizen Engine                                  │   │
│  │                                                                       │   │
│  │  Triggers:                                                           │   │
│  │    • Every 7 sessions (protocol)                                     │   │
│  │    • Every 100 spans                                                 │   │
│  │    • Manual: `dgc kaizen`                                            │   │
│  │    • Scheduled: cron job                                             │   │
│  │                                                                       │   │
│  │  Analysis:                                                           │   │
│  │    • Utilization % (compute / wall clock)                           │   │
│  │    • Pramāda % (idle / wall clock)                                  │   │
│  │    • Category breakdown                                              │   │
│  │    • Top 10 optimization targets                                    │   │
│  │    • Observer effect measurement                                     │   │
│  └───────────────────────────────┬─────────────────────────────────────┘   │
│                                     │                                         │
│                                     ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                   Darwin Evolution Engine                            │   │
│  │                                                                       │   │
│  │  • optimize_span_target()                                            │   │
│  │  • Create optimization proposals                                     │   │
│  │  • Gate check proposals (telos gates)                               │   │
│  │  • Evaluate fitness                                                  │   │
│  │  • Archive results                                                   │   │
│  └───────────────────────────────┬─────────────────────────────────────┘   │
│                                     │                                         │
│                                     ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     Self-Optimization Loop                           │   │
│  │                                                                       │   │
│  │  Kaizen → Proposals → Implementation → Measurement → Kaizen         │   │
│  │    ▲                                                            │     │   │
│  │    └────────────────────────────────────────────────────────────┘     │   │
│  │                                                                       │   │
│  │  TARGET: 5% → 50% utilization = 10x efficiency gain                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Span Lifecycle Flowchart

```
┌─────────────────────────────────────────────────────────────────────┐
│                     OPERATION BEGINS                                 │
│              (spawn_agent, LLM call, gate check, etc.)              │
└────────────────────────────────┬────────────────────────────────────┘
                                  │
                                  ▼
                        ┌──────────────────┐
                        │ Instrumentation  │
                        │    Enabled?      │
                        │ (JIKOKU_ENABLED) │
                        └────────┬─────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    │ NO                        │ YES
                    ▼                           ▼
          ┌──────────────────┐      ┌──────────────────┐
          │   Execute        │      │  Sample Check    │
          │   Operation      │      │ (SAMPLE_RATE)    │
          │   (no span)      │      └────────┬─────────┘
          └──────────────────┘               │
                    │              ┌──────────┼──────────┐
                    │              │ SKIP               │ CREATE
                    │              ▼                    ▼
                    │    ┌──────────────────┐ ┌──────────────────┐
                    │    │   Execute        │ │ jikoku_auto_span │
                    │    │   Operation      │ │    (enter)       │
                    │    │   (no span)      │ └────────┬─────────┘
                    │    └──────────────────┘          │
                    │              │                   ▼
                    │              │         ┌──────────────────┐
                    │              │         │ Generate span_id │
                    │              │         │ Record ts_start  │
                    │              │         │ Category + intent│
                    │              │         └────────┬─────────┘
                    │              │                   │
                    │              │                   ▼
                    │              │         ┌──────────────────┐
                    │              │         │    OPERATION     │
                    │              │         │    EXECUTES      │
                    │              │         └────────┬─────────┘
                    │              │                   │
                    │              │                   ▼
                    │              │         ┌──────────────────┐
                    │              │         │ jikoku_auto_span │
                    │              │         │     (exit)       │
                    │              │         └────────┬─────────┘
                    │              │                   │
                    │              │                   ▼
                    │              │         ┌──────────────────┐
                    │              │         │ Record ts_end    │
                    │              │         │ Calculate Δt     │
                    │              │         │ Merge metadata   │
                    │              │         └────────┬─────────┘
                    │              │                   │
                    │              │                   ▼
                    │              │         ┌──────────────────┐
                    │              │         │ Append to JSONL  │
                    │              │         │  (atomic write)  │
                    │              │         └────────┬─────────┘
                    │              │                   │
                    └──────────────┴───────────────────┘
                                  │
                                  ▼
                        ┌──────────────────┐
                        │    OPERATION     │
                        │    COMPLETE      │
                        └──────────────────┘
```

---

## 3. Kaizen Loop Dataflow

```
┌─────────────────────────────────────────────────────────────────────┐
│                   JIKOKU_LOG.jsonl (Append-Only)                    │
│                                                                      │
│  • Every operation creates a span                                   │
│  • Metadata: category, duration, tokens, cost, etc.                │
│  • Example: 100 spans per session                                  │
└────────────────────────────────┬────────────────────────────────────┘
                                  │
                                  ▼
                        ┌──────────────────┐
                        │  Kaizen Trigger  │
                        │                  │
                        │ • 7 sessions     │
                        │ • 100 spans      │
                        │ • Manual         │
                        │ • Cron           │
                        └────────┬─────────┘
                                  │
                                  ▼
                    ┌──────────────────────────┐
                    │    Load Last N Sessions   │
                    │                          │
                    │ • Parse JSONL             │
                    │ • Filter by session_id    │
                    │ • Total: ~700 spans       │
                    └────────┬─────────────────┘
                              │
                              ▼
              ┌───────────────────────────────────┐
              │        Aggregate Metrics          │
              │                                   │
              │ • Total compute time (Σ duration) │
              │ • Wall clock (max - min ts)       │
              │ • Utilization = compute / wall    │
              │ • Pramāda = 1 - utilization       │
              │ • Category breakdown              │
              │ • Observer overhead               │
              └────────┬──────────────────────────┘
                        │
                        ▼
              ┌───────────────────────────────────┐
              │     Identify Top 10 Slowest        │
              │                                   │
              │ • Sort spans by duration DESC     │
              │ • Take top 10                     │
              │ • These are optimization targets  │
              └────────┬──────────────────────────┘
                        │
                        ▼
              ┌───────────────────────────────────┐
              │      Generate Kaizen Goals        │
              │                                   │
              │ IF utilization < 50%:             │
              │   → "INCREASE UTILIZATION"        │
              │                                   │
              │ FOR each top category:            │
              │   → "OPTIMIZE {category}"         │
              │                                   │
              │ FOR each top 3 slowest spans:     │
              │   → "Reduce {intent} by 30%"      │
              └────────┬──────────────────────────┘
                        │
                        ▼
              ┌───────────────────────────────────┐
              │    Kaizen Report (dict)           │
              │                                   │
              │ {                                 │
              │   "utilization_pct": 12.3,        │
              │   "idle_pct": 87.7,               │
              │   "optimization_targets": [       │
              │     {                             │
              │       "span_id": "...",           │
              │       "category": "api_call",     │
              │       "intent": "LLM to Claude",  │
              │       "duration_sec": 3.2         │
              │     }, ...                        │
              │   ],                              │
              │   "kaizen_goals": [...]           │
              │ }                                 │
              └────────┬──────────────────────────┘
                        │
                        ├──────────────────┬──────────────────┐
                        │                  │                  │
                        ▼                  ▼                  ▼
          ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
          │  Log to Dashboard│ │ Create Evolution │ │  Human Review    │
          │                  │ │   Proposals      │ │  (optional)      │
          │ • TUI display    │ │                  │ │                  │
          │ • ~/.dharma/     │ │ FOR top 3:       │ │ • .FOCUS file    │
          │   kaizen/        │ │   optimize_span_ │ │ • Manual tuning  │
          │   report.json    │ │   target()       │ │                  │
          └──────────────────┘ └────────┬─────────┘ └──────────────────┘
                                          │
                                          ▼
                              ┌──────────────────────────┐
                              │   DarwinEngine           │
                              │                          │
                              │ • Proposal created       │
                              │ • Gate check             │
                              │ • Implementation         │
                              │ • Test                   │
                              │ • Fitness evaluation     │
                              │ • Archive                │
                              └────────┬─────────────────┘
                                        │
                                        ▼
                              ┌──────────────────────────┐
                              │   Applied to Codebase    │
                              │                          │
                              │ • Faster operation       │
                              │ • Next kaizen measures   │
                              │   improvement            │
                              └────────┬─────────────────┘
                                        │
                                        ▼
                              ┌──────────────────────────┐
                              │   Utilization Improves   │
                              │                          │
                              │  12.3% → 15.8% → 20.1%  │
                              │         ⬇                │
                              │    Path to 50%           │
                              │    (10x efficiency)      │
                              └──────────────────────────┘
```

---

## 4. Integration Point Map

```
┌─────────────────────────────────────────────────────────────────────┐
│                          DHARMA SWARM                                │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │ providers.py                                               │   │
│  │                                                            │   │
│  │  class AnthropicProvider:                                 │   │
│  │      @jikoku_traced_provider  ◄────────┐                  │   │
│  │      async def complete():             │                  │   │
│  │          # LLM API call                │                  │   │
│  │                                        │                  │   │
│  │  class OpenAIProvider:                 │                  │   │
│  │      @jikoku_traced_provider  ◄────────┤                  │   │
│  │      async def complete():             │                  │   │
│  │                                        │                  │   │
│  │  class OpenRouterProvider:             │ INSTRUMENTATION  │   │
│  │      @jikoku_traced_provider  ◄────────┤     POINT        │   │
│  │      async def complete():             │                  │   │
│  │                                        │                  │   │
│  │  class NVIDIANIMProvider:              │  Captures:       │   │
│  │      @jikoku_traced_provider  ◄────────┤  • Duration      │   │
│  │      async def complete():             │  • Tokens        │   │
│  │                                        │  • Cost          │   │
│  │  class ClaudeCodeProvider:             │  • Model         │   │
│  │      @jikoku_traced_provider  ◄────────┘                  │   │
│  │      async def complete():                                │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │ swarm.py                                                   │   │
│  │                                                            │   │
│  │  async def spawn_agent():                                 │   │
│  │      with jikoku_auto_span(  ◄───────┐                    │   │
│  │          "execute.agent_spawn",      │                    │   │
│  │          f"Spawn {name}"              │                    │   │
│  │      ):                               │                    │   │
│  │          # ... spawn logic ...        │ INSTRUMENTATION    │   │
│  │                                       │     POINT          │   │
│  │  async def create_task():             │                    │   │
│  │      with jikoku_auto_span(  ◄───────┤  Captures:         │   │
│  │          "execute.task_create",       │  • Duration        │   │
│  │          f"Create {title}"            │  • Agent/Role      │   │
│  │      ):                               │  • Task ID         │   │
│  │          # ... task logic ...         │  • Priority        │   │
│  │                                       │                    │   │
│  │  async def dispatch_next():           │                    │   │
│  │      with jikoku_auto_span(  ◄───────┘                    │   │
│  │          "execute.orchestration_tick",                     │   │
│  │          "Orchestration tick"                              │   │
│  │      ):                                                    │   │
│  │          # ... dispatch logic ...                          │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │ evolution.py                                               │   │
│  │                                                            │   │
│  │  async def propose():                                     │   │
│  │      with jikoku_auto_span(  ◄───────┐                    │   │
│  │          "execute.evolution_propose", │                    │   │
│  │          f"Propose {component}"       │                    │   │
│  │      ):                               │                    │   │
│  │          # ... propose logic ...      │ INSTRUMENTATION    │   │
│  │                                       │     POINT          │   │
│  │  async def gate_check():              │                    │   │
│  │      with jikoku_auto_span(  ◄───────┤  Captures:         │   │
│  │          "execute.evolution_gate",    │  • Duration        │   │
│  │          f"Gate {proposal.id}"        │  • Proposal ID     │   │
│  │      ):                               │  • Decision        │   │
│  │          # ... gate logic ...         │  • Fitness         │   │
│  │                                       │  • Component       │   │
│  │  async def evaluate():                │                    │   │
│  │      with jikoku_auto_span(  ◄───────┤                    │   │
│  │          "execute.evolution_evaluate",│                    │   │
│  │          f"Evaluate {proposal.id}"    │                    │   │
│  │      ):                               │                    │   │
│  │          # ... evaluate logic ...     │                    │   │
│  │                                       │                    │   │
│  │  async def archive_result():          │                    │   │
│  │      with jikoku_auto_span(  ◄───────┘                    │   │
│  │          "file_op",                                        │   │
│  │          f"Archive {proposal.id}"                          │   │
│  │      ):                                                    │   │
│  │          # ... archive logic ...                           │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │ agent_runner.py                                            │   │
│  │                                                            │   │
│  │  async def _execute_task():                               │   │
│  │      with jikoku_auto_span(  ◄───────┐                    │   │
│  │          "execute.agent_task",        │ INSTRUMENTATION    │   │
│  │          f"Execute {task.title}"      │     POINT          │   │
│  │      ):                               │                    │   │
│  │          # ... execution logic ...    │  Captures:         │   │
│  │                                       │  • Duration        │   │
│  │                                       │  • Agent ID        │   │
│  │                                       │  • Task ID         │   │
│  │                                       │  • Success/Fail    │   │
│  │                                       │  • Result length   │   │
│  └───────────────────────────────────────┴──────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 5. Performance Control Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PERFORMANCE CONTROL LAYERS                        │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ Layer 1: Global Enable/Disable                                      │
│                                                                      │
│  Environment Variable:                                              │
│    JIKOKU_ENABLED=1  →  Instrumentation ON                         │
│    JIKOKU_ENABLED=0  →  Instrumentation OFF (zero overhead)        │
│                                                                      │
│  Runtime Toggle:                                                    │
│    enable_instrumentation(True/False)                               │
│                                                                      │
│  Overhead when disabled: ~1 conditional check (< 1 nanosecond)     │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 2: Adaptive Sampling                                          │
│                                                                      │
│  Environment Variable:                                              │
│    JIKOKU_SAMPLE_RATE=1.0  →  100% of spans (full instrumentation) │
│    JIKOKU_SAMPLE_RATE=0.1  →  10% of spans (lower overhead)        │
│    JIKOKU_SAMPLE_RATE=0.01 →  1% of spans (minimal overhead)       │
│                                                                      │
│  Sampling Decision:                                                 │
│    if random.random() > SAMPLE_RATE:                                │
│        skip span creation                                           │
│                                                                      │
│  Trade-off: Lower sample rate = less complete data but less        │
│             overhead. Still useful for trends.                      │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 3: Async-Native Implementation                                │
│                                                                      │
│  All span operations are async-compatible:                          │
│    • No blocking I/O during span creation                           │
│    • JSONL writes are atomic (single write() call)                 │
│    • Context managers use async context vars                        │
│    • No GIL contention                                              │
│                                                                      │
│  Observer effect minimized:                                         │
│    • Span metadata prepared before await                            │
│    • Write happens outside critical path                            │
│    • No synchronous file operations                                 │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 4: Observer Effect Measurement                                │
│                                                                      │
│  Kaizen report includes JIKOKU's own overhead:                      │
│                                                                      │
│    jikoku_overhead_sec = Σ duration of jikoku_* spans              │
│    jikoku_overhead_pct = overhead / total_compute * 100            │
│                                                                      │
│  Target: < 1% overhead                                              │
│                                                                      │
│  If overhead > 1%:                                                  │
│    • Increase SAMPLE_RATE (measure less frequently)                │
│    • Reduce metadata captured                                       │
│    • Use coarser granularity                                        │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 5: Emergency Circuit Breaker                                  │
│                                                                      │
│  If JIKOKU overhead > 5%:                                           │
│    • Auto-disable instrumentation                                   │
│    • Log warning                                                    │
│    • Create alert for human review                                  │
│                                                                      │
│  Safety guarantee:                                                  │
│    JIKOKU will never degrade system performance beyond threshold   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 6. Evolution Integration Flowchart

```
┌─────────────────────────────────────────────────────────────────────┐
│                  KAIZEN REPORT GENERATED                             │
│                                                                      │
│  • Utilization: 12.3%                                               │
│  • Pramāda: 87.7%                                                   │
│  • Top 3 optimization targets:                                      │
│    1. api_call - "LLM to Claude" - 3.2s                            │
│    2. execute.evolution_gate - "Gate check" - 1.8s                 │
│    3. file_op - "Archive proposal" - 0.9s                          │
└────────────────────────────────┬────────────────────────────────────┘
                                  │
                                  ▼
                    ┌──────────────────────────┐
                    │   FOR each target in      │
                    │   top 3:                  │
                    └────────┬─────────────────┘
                              │
                              ▼
              ┌───────────────────────────────────┐
              │  optimize_span_target()           │
              │                                   │
              │  Input: {                         │
              │    "span_id": "...",              │
              │    "category": "api_call",        │
              │    "intent": "LLM to Claude",     │
              │    "duration_sec": 3.2            │
              │  }                                │
              │                                   │
              │  Output: Proposal                 │
              └────────┬──────────────────────────┘
                        │
                        ▼
              ┌───────────────────────────────────┐
              │     DarwinEngine.propose()        │
              │                                   │
              │  component: "providers.py"        │
              │  change_type: "optimization"      │
              │  description: "Reduce LLM call    │
              │    latency by 30%"                │
              │  think_notes: "Kaizen identified  │
              │    this as top slowest span..."   │
              └────────┬──────────────────────────┘
                        │
                        ▼
              ┌───────────────────────────────────┐
              │     DarwinEngine.gate_check()     │
              │                                   │
              │  • AHIMSA: no harm?               │
              │  • SATYA: truthful?               │
              │  • WITNESS: thought through?      │
              │  • ...                            │
              │                                   │
              │  Decision: ALLOW                  │
              └────────┬──────────────────────────┘
                        │
                        ▼
              ┌───────────────────────────────────┐
              │       Implementation              │
              │                                   │
              │  Options:                         │
              │  1. Caching (memoize responses)   │
              │  2. Parallelization (batch calls) │
              │  3. Model swap (faster model)     │
              │  4. Request optimization (fewer   │
              │     tokens)                       │
              └────────┬──────────────────────────┘
                        │
                        ▼
              ┌───────────────────────────────────┐
              │     DarwinEngine.evaluate()       │
              │                                   │
              │  • Run tests (correctness)        │
              │  • Measure new span duration      │
              │  • Calculate fitness              │
              │                                   │
              │  Before: 3.2s                     │
              │  After:  2.1s                     │
              │  Speedup: 34% (target: 30%)       │
              │                                   │
              │  Fitness: 0.78 (> 0.6 threshold)  │
              └────────┬──────────────────────────┘
                        │
                        ▼
              ┌───────────────────────────────────┐
              │    DarwinEngine.archive_result()  │
              │                                   │
              │  • Store in evolution archive     │
              │  • Mark as "applied"              │
              │  • Update predictor               │
              └────────┬──────────────────────────┘
                        │
                        ▼
              ┌───────────────────────────────────┐
              │    Next Kaizen Report Measures    │
              │         Improvement               │
              │                                   │
              │  Utilization: 12.3% → 14.1%       │
              │  (Faster operations = higher      │
              │   utilization for same wall time) │
              └───────────────────────────────────┘
```

---

**JSCA!**

*End of JIKOKU SAMAYA System Architecture Diagrams v1.0*
