# Runtime Spine Audit And Trust Report

Date: 2026-03-28
Repo: `/Users/dhyana/dharma_swarm`
Branch: `checkpoint/dashboard-stabilization-2026-03-19`

## Fresh Verification Evidence

### Targeted provider/execution seam

Fresh command, run twice:

```bash
pytest -q tests/test_agent_runner.py tests/test_providers.py tests/test_providers_quality_track.py tests/test_dashboard_chat_router.py tests/test_intelligence_agents.py
```

Fresh results:

- pass 1: `102 passed in 71.19s`
- pass 2: `102 passed in 71.60s`

### Targeted scheduler/pulse/orchestrator seam

Fresh command, run twice:

```bash
pytest -q tests/test_cron_runner.py tests/test_launchd_job_runner.py tests/test_overnight_director.py tests/test_pulse.py tests/test_doctor.py tests/test_orchestrator.py tests/test_organism_boot.py
```

Fresh results:

- pass 1: `94 passed in 8.78s`
- pass 2: `94 passed in 9.48s`

### Focused runtime-path subset

Fresh command:

```bash
pytest -q tests/test_agent_runner.py tests/test_cron_runner.py tests/test_pulse.py tests/test_orchestrator.py tests/test_dashboard_chat_router.py tests/test_doctor.py
```

Fresh result:

- `103 passed in 74.48s`

### Live pulse status

Fresh command:

```bash
python3 -m dharma_swarm.pulse --status
```

Fresh result:

- pulse log exists and is readable
- current thread: `architectural`
- contributions recorded by thread
- historical failures show direct dependency on Claude login state:
  - `Error (rc=1): Not logged in · Please run /login`

### Integration probe

Fresh command:

```bash
python3 scripts/system_integration_probe.py
```

Fresh result:

- `19 pass / 0 fail / 1 degrade / 0 skip`
- health reported: `95%`
- degraded item:
  - `LivingState: unknown age`

Important runtime truth surfaced during probe:

- `ContextCompiler.compile_bundle` emitted an un-awaited coroutine warning
- stigmergy loader reported `skipped 15 corrupt marks`
- live free-model probes responded successfully for:
  - `Kimi-K2.5`
  - `GLM-5`
  - `NvidiaNIM`

## Most Evidenced Working Paths

These are the paths with the strongest current evidence of being both evolved and
logically coherent.

### 1. Provider / Execution Truth Path

Core files:

- `dharma_swarm/agent_runner.py`
- `dharma_swarm/providers.py`
- `dharma_swarm/runtime_provider.py`
- `dharma_swarm/provider_policy.py`
- `dharma_swarm/provider_smoke.py`
- `api/routers/chat.py`
- `dharma_swarm/contracts/intelligence_agents.py`

Why this path counts as evidenced:

- repeated green tests on the exact seam
- certified-lane identity exists
- live free-model probe success exists
- false-green local-worker path has already been corrected

What is still weak:

- OpenAI tool-loop robustness
- Claude Haiku tool-schema path
- dashboard/frontend baseline still not clean enough to act as a hard gate

### 2. Temporal Scheduler / Resume Path

Core files:

- `dharma_swarm/cron_runner.py`
- `dharma_swarm/launchd_job_runner.py`
- `dharma_swarm/overnight_director.py`
- `dharma_swarm/pulse.py`
- `dharma_swarm/doctor.py`

Why this path counts as evidenced:

- repeated green tests on the exact seam
- explicit `waiting_external` handling exists
- resume metadata is already being threaded through cron execution

What is still weak:

- canonical runtime pulse is not yet the same thing as the daemon wrapper
- status/probe truth still has degradations

### 3. Async Orchestration Core

Core file:

- `dharma_swarm/orchestrator.py`

Why this path counts as evidenced:

- targeted orchestrator tests pass repeatedly
- real routing, dispatch, and fan-out/fan-in semantics exist
- structurally, this is the strongest candidate for L3 coordination

What is still weak:

- it is not yet the canonical conductor for the full pulse lifecycle
- it still lives next to broader runtime sprawl rather than beneath a narrow pulse contract

### 4. Organism Runtime Surface

Core files:

- `dharma_swarm/organism.py`
- `dharma_swarm/model_routing.py`

Why this path counts as evidenced:

- organism boot and heartbeat tests pass
- integration probe reports `OrganismRuntime` as operational

What is still weak:

- current organism surface is broader and older than the new constitutional runtime target
- it should not be the first place new pulse semantics land

## Diagnosis

### 1. `pulse.py` is not yet the canonical runtime pulse

Current reality:

- it is a daemon/headless-Claude wrapper
- it mixes:
  - quiet-hours behavior
  - cron triggering
  - prompt construction
  - direct LLM execution
  - living-layer heartbeat
  - memory writes
  - thread rotation

Architecturally, that means current `pulse.py` is mostly:

- L3 execution wrapper
- plus daemon glue
- plus incidental L4/L5 concerns

It is not yet the explicit:

`sense -> interpret -> constrain -> propose -> execute -> trace -> evaluate -> archive -> adapt`

runtime.

### 2. `orchestrator.py` is the right L3 anchor

Current reality:

- async routing core exists
- dispatch and coordination semantics exist
- it already behaves like a coordination engine, not a shell wrapper

Architecturally, `orchestrator.py` is the strongest candidate to become the
execution conductor beneath a canonical pulse.

### 3. The invariant and prediction surfaces do not exist yet

Missing:

- `dharma_swarm/invariants.py`
- `dharma_swarm/self_prediction.py`
- `tests/test_layer_separation.py`

That is the clearest sign that the constitutional runtime is not yet fully
computable. The project has telemetry, gates, and graph structure, but not yet:

- explicit invariant snapshots
- explicit predictive self-model snapshots
- explicit layer-boundary enforcement tests

### 4. Existing nearby modules are partial ingredients, not the missing surfaces

- `telemetry_plane.py` is a retrospective substrate, not a predictive self-model
- `catalytic_graph.py` exposes SCC/autocatalytic analysis, not runtime invariants
- `pulse.py` has living-layer heartbeat wiring, but not a bounded constitutional cycle

## Architectural Decision

Make `pulse.py` canonical by turning it into a bounded phase runner over a small
set of explicit pure/small functions, while making `orchestrator.py` the L3
execution engine underneath it.

The target architecture:

- `L0` Constitution
  - `invariants.py`
  - telos / hard limits / mutation rights / freeze state
- `L1` Signals / Trace / Archive
  - existing runtime state, telemetry, trace/artifact writes
- `L2` Interpretation / Prediction
  - `self_prediction.py`
  - signal interpretation and next-cycle expectation
- `L3` Coordination / Execution
  - `orchestrator.py`
  - bounded 3-agent execution plan
- `L4` Evaluation / Adaptation
  - result scoring, archive, adaptation decision
- `L5` Product Surface
  - API/dashboard/operator views only

`pulse.py` should become the orchestrated runtime loop, not the place where the
system directly shells into Claude as its primary identity.

## Exact Files To Modify

Primary:

- `dharma_swarm/pulse.py`
- `dharma_swarm/orchestrator.py`
- `dharma_swarm/telemetry_plane.py`
- `dharma_swarm/runtime_artifacts.py`

Create:

- `dharma_swarm/invariants.py`
- `dharma_swarm/self_prediction.py`
- `tests/test_layer_separation.py`
- `tests/test_invariants.py`
- `tests/test_self_prediction.py`

Modify tests:

- `tests/test_pulse.py`
- `tests/test_orchestrator.py`
- `tests/test_doctor.py`

Optional nearby adapters only if needed:

- `dharma_swarm/doctor.py`
- `dharma_swarm/runtime_provider.py`

## Proposed Interfaces / Types / Function Signatures

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


PulseVerdict = Literal["proceed", "degrade", "block"]


@dataclass(slots=True)
class SignalSnapshot:
    run_id: str
    captured_at: str
    thread: str
    task_count: int
    idle_agent_count: int
    queue_depth: int
    stigmergy_density: int
    living_state_age_sec: int | None
    provider_health: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class InvariantCheck:
    name: str
    passed: bool
    severity: Literal["low", "medium", "high", "critical"]
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class InvariantSnapshot:
    verdict: PulseVerdict
    checks: list[InvariantCheck]
    issue_count: int
    recorded_at: str


@dataclass(slots=True)
class PredictionSnapshot:
    expected_verdict: PulseVerdict
    expected_runtime_ms: int
    expected_agent_count: int
    expected_risks: list[str]
    confidence: float
    model_version: str = "rule_based_v1"


@dataclass(slots=True)
class ExecutionPlan:
    run_id: str
    max_agents: int
    timeout_seconds: float
    tasks: list[dict[str, Any]]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExecutionResult:
    completed_tasks: int
    failed_tasks: int
    duration_ms: int
    outputs: list[dict[str, Any]]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ArchiveRecord:
    run_id: str
    stored_at: str
    paths: dict[str, str]
    summary: dict[str, Any]


@dataclass(slots=True)
class AdaptationDecision:
    action: Literal["keep", "tune", "pause", "escalate"]
    reason: str
    changes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PulseResult:
    run_id: str
    signal_snapshot: SignalSnapshot
    invariant_snapshot: InvariantSnapshot
    prediction_snapshot: PredictionSnapshot
    execution_result: ExecutionResult
    archive_record: ArchiveRecord
    adaptation_decision: AdaptationDecision
```

Proposed module functions:

```python
def collect_signals(...) -> SignalSnapshot: ...
def evaluate_invariants(signals: SignalSnapshot) -> InvariantSnapshot: ...
def predict_pulse_outcome(
    signals: SignalSnapshot,
    invariants: InvariantSnapshot,
) -> PredictionSnapshot: ...
def build_execution_plan(
    signals: SignalSnapshot,
    invariants: InvariantSnapshot,
    prediction: PredictionSnapshot,
    *,
    max_agents: int = 3,
    timeout_seconds: float = 60.0,
) -> ExecutionPlan: ...
async def execute_plan(
    plan: ExecutionPlan,
    orchestrator: Orchestrator,
) -> ExecutionResult: ...
def archive_pulse_result(result: PulseResult) -> ArchiveRecord: ...
def decide_adaptation(result: PulseResult) -> AdaptationDecision: ...
async def run_pulse_cycle(...) -> PulseResult: ...
```

## Refactor Sequence

### Phase 1: Add the missing surfaces without moving behavior

1. Create `invariants.py` with pure dataclasses and invariant evaluators.
2. Create `self_prediction.py` with a simple rule-based predictor.
3. Add `tests/test_invariants.py`, `tests/test_self_prediction.py`, and `tests/test_layer_separation.py`.

Do not touch the direct headless-Claude execution path yet.

### Phase 2: Turn `pulse.py` into a phase runner

1. Extract:
   - signal collection
   - invariant evaluation
   - prediction
   - plan building
   - archive/adaptation
2. Keep existing CLI flags and daemon entrypoints intact.
3. Make the old direct execution path one execution adapter, not the identity of the pulse.

### Phase 3: Make `orchestrator.py` the L3 executor

1. Add a narrow execution-plan entrypoint in `orchestrator.py`.
2. Limit the pulse to `max_agents=3`.
3. Enforce `timeout_seconds <= 60`.

### Phase 4: Record structured pulse artifacts

Persist on every pulse:

- trace record
- invariant snapshot
- prediction snapshot
- execution result
- archive record
- adaptation decision

### Phase 5: Add layer-boundary enforcement

`tests/test_layer_separation.py` should enforce:

- `L5` modules do not import `L0`/`L3` internals directly except through narrow adapters
- `pulse.py` does not import dashboard/UI code
- invariants/prediction surfaces stay pure and deterministic

## Risks Introduced

### 1. Pulse regression risk

Refactoring `pulse.py` can easily break:

- daemon behavior
- quiet-hours flow
- cron bridge behavior
- current artifact writes

### 2. False abstraction risk

If `invariants.py` or `self_prediction.py` become vague wrappers, they add
conceptual sprawl instead of reducing it.

### 3. Branch-governance risk

This refactor should not proceed in the already overloaded integration branch
without strict stop/finish/split discipline.

### 4. Test illusion risk

New tests must remain:

- deterministic
- mostly pure
- not dependent on live LLM calls

or they will increase noise instead of trust.

## Verification Plan

### Existing proof commands to keep

```bash
pytest -q tests/test_agent_runner.py tests/test_providers.py tests/test_providers_quality_track.py tests/test_dashboard_chat_router.py tests/test_intelligence_agents.py
pytest -q tests/test_cron_runner.py tests/test_launchd_job_runner.py tests/test_overnight_director.py tests/test_pulse.py tests/test_doctor.py tests/test_orchestrator.py tests/test_organism_boot.py
pytest -q tests/test_agent_runner.py tests/test_cron_runner.py tests/test_pulse.py tests/test_orchestrator.py tests/test_dashboard_chat_router.py tests/test_doctor.py
python3 -m dharma_swarm.pulse --status
python3 scripts/system_integration_probe.py
```

### New proof commands to add

```bash
pytest -q tests/test_invariants.py tests/test_self_prediction.py tests/test_layer_separation.py
pytest -q tests/test_pulse.py tests/test_orchestrator.py tests/test_doctor.py
```

### Acceptance target

Under 60 seconds, a canonical pulse should produce:

- trace
- invariant snapshot
- prediction snapshot
- execution result
- archive record
- adaptation decision

with no live test requiring a frontier-model login.

## What Not To Do

- Do not make `pulse.py` a bigger daemon wrapper.
- Do not put invariants inside `api/main.py`, `chat.py`, or dashboard files.
- Do not introduce more overlapping runtime loops.
- Do not make `self_prediction.py` a vague LLM-only oracle.
- Do not let `orchestrator.py` absorb product-surface concerns.
- Do not add new commands if existing `pulse` and `doctor` entrypoints can carry the surface.
- Do not ship the constitutional runtime without layer-separation tests.

## Blunt Conclusion

The most evidenced working runtime paths today are:

1. provider/execution truthfulness
2. temporal scheduler/resume truthfulness
3. async orchestration dispatch

The canonical constitutional pulse does not exist yet.

But the substrate to build it is real:

- `orchestrator.py` can be the L3 executor
- `pulse.py` can be narrowed into the canonical phase runner
- invariants/prediction/layer-separation are the exact missing pieces

That is the highest-leverage logical path forward.
