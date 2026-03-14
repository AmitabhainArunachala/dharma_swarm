# DGC Decision Ontology Swarm

Date: 2026-03-14
Purpose: use the full DGC council shape to turn Palantir Ontology's strongest design patterns into a real DGC decision substrate with harder internal standards for intelligence and quality
Primary reference: `docs/reports/DGC_DECISION_ONTOLOGY_UPGRADE_2026-03-14.md`

## Mission Thesis

The swarm should not be asked to "think harder."

It should be asked to make high-impact decisions legible, challengeable, measurable, and replayable.

This mission is complete only when DGC has:

- a typed decision ontology
- a deterministic quality case
- a council workflow that uses the strongest models where judgment matters most
- a clear path to route mission-critical choices through that substrate

## Required Outputs

1. `decision_ontology.py`
   Typed decision objects, evidence, challenges, reviews, metrics, and quality scoring.
2. `test_decision_ontology.py`
   Deterministic tests for hard gates and router bridging.
3. `decision_ontology_report.md`
   Strategic rationale, copied patterns, and integration plan.
4. `decision_quality_integration.md`
   Exact touch points in director, campaign ledger, and mission routing.
5. `proposal_flow_spec.md`
   How meta-level evolution becomes branch/proposal/review/merge.

## Hard Rules

- no claim that "smartness" can be measured by eloquence
- no high-quality label without evidence, objections, and metrics
- no automatic state-changing writes from frontier model prose alone
- no schema evolution without named reviewers
- no metric that depends on the model praising itself

## Swarm Shape

Minimum viable swarm: `6 agents`

Full ontology swarm: `8-10 agents`

## Roles

1. `codex-primus`
   Co-orchestrator, code-path owner, implementation judge.
2. `opus-primus`
   Co-orchestrator, conceptual synthesizer, epistemic red-team.
3. `glm-researcher`
   Maps Palantir ontology primitives and extracts the transferable architecture.
4. `kimi-challenger`
   Mines counterarguments, failure modes, and spec loopholes.
5. `qwen-taxonomist`
   Normalizes object, link, action, and interface definitions.
6. `nim-validator`
   Tests gates, measurement integrity, and contract boundaries.
7. `builder-lane`
   Implements low-cost code and tests after council convergence.
8. `observer-lane`
   Designs outcome tracking and retrospective calibration.

## Work Waves

### Wave 1: Ontology extraction

- `glm-researcher`
- `opus-primus`
- `qwen-taxonomist`

Deliverables:

- copied Palantir design primitives
- DGC-native object model
- interface and action taxonomy

### Wave 2: Quality-case design

- `codex-primus`
- `kimi-challenger`
- `nim-validator`

Deliverables:

- deterministic score dimensions
- hard fail conditions
- warning conditions
- anti-gaming rationale

### Wave 3: Implementation

- `codex-primus`
- `builder-lane`
- `nim-validator`

Deliverables:

- decision ontology module
- tests
- router bridge

### Wave 4: Meta-governance

- `opus-primus`
- `codex-primus`
- `observer-lane`

Deliverables:

- proposal workflow
- review semantics
- outcome feedback loop

## Scoring Standard

Use this formula:

`DecisionQualityScore = 0.22 Structure + 0.26 Evidence + 0.18 Challenge + 0.18 Traceability + 0.16 Observability`

Hard fail if any of these are missing:

- evidence
- counterarguments
- selected option
- at least two options
- supported claim for the selected option
- metrics

## Stop Conditions

Stop and escalate if:

- the quality metric can be inflated by prose with no new evidence
- the selected option can pass without claim-to-evidence support
- the system still allows silent meta-level rule changes
- the council cannot explain why a decision passed in one screen of structured output

## Definition Of Success

The mission succeeds when DGC can take one important decision and show, in a compact typed record:

- what was being decided
- which options existed
- what evidence grounded them
- what objections were raised
- who reviewed the choice
- how quality was computed
- how the result will later be judged in the world
