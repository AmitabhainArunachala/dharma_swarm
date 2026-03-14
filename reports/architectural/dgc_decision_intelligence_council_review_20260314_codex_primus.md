# DGC Decision Intelligence Council Review

Date: 2026-03-14
Author: codex-primus
Thread: architectural

## Scope

Mission: level up DGC's decision intelligence and make its quality case hard to assail inside the system.

Validation basis:
- code inspection of provider, router, handoff, and director paths
- current runtime config resolution on this machine
- existing provider smoke artifacts
- targeted test run: `89 passed` across decision/router/provider/director slices

## Runtime Truth

### Primary lanes

| Lane | Runtime name | Provider/backend | Current default model | Reality |
| --- | --- | --- | --- | --- |
| Codex | `codex-primus` | `ProviderType.CODEX` via `codex-cli` | `gpt-5.4` | Real primary mind. Binary present. |
| Opus | `opus-primus` | `ProviderType.CLAUDE_CODE` via `claude-cli` | `claude-opus-4-6` in director; `claude-sonnet-4-20250514` in generic runtime config | Real primary mind in director, but generic `CLAUDE_CODE` runtime defaults to Sonnet. |

### Support lanes

| Requested lane | Runtime name | Provider/backend | Current model | Reality |
| --- | --- | --- | --- | --- |
| GLM | `glm-researcher` | `openrouter` via `provider-fallback` | `z-ai/glm-5` | Real support mind. |
| Kimi | `kimi-cartographer` | `openrouter` via `provider-fallback` | `moonshotai/kimi-k2.5` | Name/role drift from mission docs. Not `kimi-challenger`. |
| Qwen | `qwen-builder` | `openrouter` via `provider-fallback` | `qwen/qwen2.5-coder-32b-instruct` | Name/role drift from mission docs. Not `qwen-taxonomist`. |
| NIM | `nim-validator`, `nim-generalist` | `nvidia_nim` via `provider-fallback` | `nvidia/llama-3.1-nemotron-ultra-253b-v1`, `meta/llama-3.3-70b-instruct` | Real support minds. Hosted API mode right now. |

### Transport-level truth

- `codex` binary exists at `/Users/dhyana/.npm-global/bin/codex`
- `claude` binary exists at `/Users/dhyana/.npm-global/bin/claude`
- `OPENROUTER_API_KEY`, `NVIDIA_NIM_API_KEY`, and `OLLAMA_API_KEY` are set
- `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` are unset
- `DGC_DIRECTOR_COUNCIL_LIVE` is set
- generic runtime config currently resolves:
  - `codex -> gpt-5.4`
  - `claude_code -> claude-sonnet-4-20250514`
  - `openrouter -> openai/gpt-5-codex`
  - `nvidia_nim -> meta/llama-3.3-70b-instruct` in hosted mode
  - `ollama -> kimi-k2.5:cloud` in cloud mode

### Selection truth

- only `codex-primus` and `opus-primus` are queried in the live primary council
- `glm`, `kimi`, `qwen`, and `nim` appear in support-mind definitions, execution preferences, and routing strategy text, but not in primary council deliberation
- `GLM`, `Kimi`, and some `NIM` behaviors are model hints on top of `openrouter`, `ollama`, or `nvidia_nim`, not first-class decision lanes
- deterministic swarm routing knows only `planner`, `coder`, `researcher`, `critic`, not the richer council ontology

## Highest-Value Failure Modes

1. Decision gate does not honor escalation.
- `thinkodynamic_director._assess_workflow_decision()` computes route path and `requires_human`, but `should_mutate` depends only on `assessment.verdict != FRAGILE`.
- Result: an `ESCALATE` decision can still mutate mission state without additional approval.

2. Council quality can be heuristic while still looking formal.
- If live council turns fail or are disabled, the system synthesizes heuristic consensus and still builds a structured decision record.
- Result: the artifact shape looks rigorous even when no real critique happened.

3. Lane ontology drifts from runtime names and roles.
- Runtime has `kimi-cartographer` and `qwen-builder`; mission docs talk about `kimi-challenger` and `qwen-taxonomist`.
- Result: routing, evaluation, and council claims cannot be audited against a stable lane ontology.

4. Codex and Opus models diverge between director runtime and generic provider runtime.
- Director pins `opus-primus` to `claude-opus-4-6`, but generic `CLAUDE_CODE` runtime config defaults to Sonnet.
- `CodexProvider` in the generic provider layer ignores the requested model in its CLI args.
- Result: the declared frontier lane can silently run a different capability tier.

5. Provider verification is fragile because tracing writes sit on the hot path.
- historical smoke artifacts show OpenRouter, NIM, and Ollama blocked by `~/.dharma/jikoku/JIKOKU_LOG.jsonl` permission failures
- Result: lane availability can look worse than reality, and verification becomes environment-coupled.

6. Handoff contracts are specified but not enforced end-to-end.
- `SwarmExecutionPlan` expects `role`, `summary`, `artifacts`, and `handoff_notes`, but worker execution mostly persists markdown blobs and optional dynamic delegations.
- Result: downstream critique has weak typed inputs and cannot reliably compare evidence across lanes.

## Gap Map

### Decision ontology gap

- `DecisionRecord` is real, tested, and deterministic
- route/collaboration outputs are real
- mutation policy still ignores escalation semantics

### Council gap

- primary council is only `Codex + Opus`
- support lanes are used as execution preferences, not as typed evidence or critique participants in the decision case
- richer lane roles in docs are not the runtime lane names

### Handoff gap

- blackboard contract exists
- typed handoff protocol exists
- worker outputs are not normalized into typed evidence/challenge/review objects before decision scoring

## Upgrade Plan

### Phase 1: Make the gate real

- block mutation when route path is `ESCALATE` or `requires_human` is true unless an explicit approval artifact exists
- require at least one successful live council turn for high-impact mission mutation
- split verdict into `quality_verdict` and `actionability_verdict`

### Phase 2: Stabilize the lane ontology

- define one canonical registry mapping lane name, role, provider, backend, model class, and budget tier
- reconcile runtime names with mission-doc names
- record actual executed lane and model in every review/evidence object

### Phase 3: Promote support lanes into typed critique

- require `glm`, `kimi`, `qwen`, and `nim` outputs to land as typed `Evidence`, `Challenge`, `Review`, or `Metric`
- add explicit lane obligations:
  - `glm`: evidence synthesis
  - `kimi`: challenge mining
  - `qwen`: taxonomy/schema normalization
  - `nim`: validation and kill-criteria enforcement

### Phase 4: Make handoffs auditable

- convert worker artifacts into typed handoff payloads before aggregation
- fail plan closure if required blackboard fields or artifact types are missing
- add per-lane evidence coverage and contradiction coverage to the decision summary

### Phase 5: Verify runtime truth continuously

- move tracing/logging failures off the provider success path
- add a lane audit command that prints actual binary, provider, model, and transport used
- add tests for model pinning parity between director and generic provider runtime

## Quality Case

The selected plan is strong if it delivers all of:

1. Escalation integrity
- zero mission mutations when decision route is `ESCALATE` without explicit approval artifact

2. Live critique coverage
- for high-impact workflows, at least one primary and two support-lane typed reviews attached before mutation

3. Evidence observability
- every selected option has grounded evidence, at least one challenge, and explicit kill criteria

4. Lane traceability
- every council and worker artifact records executed lane name, provider, backend, and model

5. Verification robustness
- provider smoke can report `auth_failed`, `blocked`, `unreachable`, and `ok` without collapsing all failures into opaque provider errors

## Explicit Risks

- stricter gates can slow mission mutation and increase preview-mode outcomes
- lane normalization may expose that some current “roles” are just prompt labels
- forcing typed handoffs will break loose worker implementations until adapters are added

## Blocking Criteria

Do not claim DGC decision intelligence is hardened until all are true:

- escalation can block mutation
- runtime lane registry matches the names used in mission policy
- support-lane critique is attached as typed objects, not only prose
- executed model/provider/backend are recorded in the decision case
- smoke verification no longer fails because tracing cannot write its own log

## Evidence References

- `dharma_swarm/thinkodynamic_director.py`
- `dharma_swarm/decision_ontology.py`
- `dharma_swarm/decision_router.py`
- `dharma_swarm/provider_policy.py`
- `dharma_swarm/router_v1.py`
- `dharma_swarm/providers.py`
- `dharma_swarm/runtime_provider.py`
- `dharma_swarm/swarm_router.py`
- `dharma_swarm/handoff.py`
- `dharma_swarm/provider_smoke.py`
- `reports/verification/provider_smoke_20260313T071659Z.json`
