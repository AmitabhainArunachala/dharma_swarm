# DGC Decision Ontology Upgrade

Date: 2026-03-14
Purpose: extract the highest-leverage patterns from Palantir Ontology and map them onto DGC so the swarm makes smarter, more defensible decisions with a quality metric that is hard to game inside the system itself.

## Bottom Line

Palantir's real move is not "better dashboards" and not "an LLM on enterprise data."

The move is:

- represent the operating world as typed objects and links
- represent change as governed actions
- represent logic as executable functions
- represent control through permissions, proposals, and lineage

That is why their Ontology is powerful. It treats decisions as a first-class operational substrate, not as after-the-fact commentary.

DGC should copy that shape.

The current DGC gap is not a lack of models. It is that too many important choices still live as:

- prompts
- free-text summaries
- heuristic quality scores
- loosely coupled artifacts

That is enough for exploration. It is not enough for a swarm that claims intellectual rigor.

## What Palantir Ontology Actually Gets Right

Verified against Palantir official docs on 2026-03-14.

### 1. The ontology models decisions, not just data

Palantir's architecture docs explicitly frame the Ontology as representing "the complex, interconnected decisions of an enterprise," with a four-part integration of `data + logic + action + security`.

Implication for DGC:

- mission intelligence cannot just be semantic memory
- it must bind evidence, decision logic, action rights, and review state

### 2. Semantics and kinetics are separate but fused

Palantir distinguishes:

- semantic elements: objects, properties, links
- kinetic elements: actions and functions

That separation matters. DGC currently has decent semantics and decent execution, but the glue between them is still too prompt-shaped.

Implication for DGC:

- `Mission`, `Decision`, `Evidence`, `Option`, `Metric`, and `Outcome` should be ontology objects
- `propose_decision`, `challenge_decision`, `approve_decision`, `execute_decision`, and `record_outcome` should be ontology actions
- scoring, routing, and reviewer selection should be ontology functions

### 3. Writes are governed actions, not arbitrary side effects

Palantir's docs on function-backed actions are extremely important here. Functions may compute edits, but operational changes are meant to be applied through actions where permissions, metadata, and operational interfaces are attached.

Implication for DGC:

- frontier model prose should not directly mutate mission state
- state-changing decisions should pass through a typed action path
- autonomous writeback should be bounded by review and policy, not just agent confidence

### 4. Ontology evolution itself is reviewable

Palantir proposals put ontology changes on branches, require review, and then merge them into main.

Implication for DGC:

- changes to the mission schema, quality gates, or agent council policy should not be silent
- the swarm needs proposal objects for meta-level evolution
- `Codex + Opus` should be co-reviewers on meta-architecture changes, not just builders

### 5. Observability and permissions are not optional add-ons

Palantir couples ontology execution to lineage, observability, and granular permissions.

Implication for DGC:

- "good decisions" are not just decisions that sound smart
- they must be inspectable, attributable, replayable, and permission-scoped

## The DGC Decision Ontology

The correct DGC copy is not a generic enterprise clone.

It should be a narrow ontology for swarm cognition.

### Core objects

- `Mission`
  The bounded objective, why-now, done condition, and kill condition.
- `Decision`
  A concrete choice that changes mission direction, policy, state, or execution.
- `Option`
  A candidate path under one decision.
- `Claim`
  A proposition supporting or rejecting an option.
- `Evidence`
  A grounded fact, test result, benchmark, repo fact, runtime trace, user constraint, or primary source.
- `Challenge`
  A substantive counterargument or failure mode.
- `Review`
  A typed judgment from a named agent or human.
- `Metric`
  The measurable success or failure signal.
- `Outcome`
  The post-execution observation.
- `QualityCase`
  The computed defense of why a decision was good enough to act on.

### Core links

- `supports`
- `contradicts`
- `derived_from`
- `reviewed_by`
- `blocks`
- `supersedes`
- `measured_by`
- `executed_as`
- `observed_in`

### Core actions

- `propose_decision`
- `attach_evidence`
- `register_challenge`
- `record_review`
- `approve_decision`
- `reject_decision`
- `execute_decision`
- `record_outcome`
- `open_proposal`
- `merge_proposal`

### Core interfaces

- `reviewable`
- `risky`
- `reversible`
- `measurable`
- `policy_bound`
- `artifact_backed`

These interfaces matter because different decisions can share common handling rules without having identical schemas.

## The Quality Metric DGC Actually Needs

Do not ask the models to rate their own intelligence.

That is gameable.

Do not use output length or polish as a proxy for quality.

That is cosmetic.

The right metric is a `Decision Quality Case`.

### Decision Quality Case dimensions

`DecisionQualityScore = 0.22 Structure + 0.26 Evidence + 0.18 Challenge + 0.18 Traceability + 0.16 Observability`

Where:

- `Structure`
  Has mission, owner, time horizon, options, selected option, constraints, and a real decision statement.
- `Evidence`
  Has enough evidence, from multiple grounded kinds, with confidence and verification.
- `Challenge`
  Has substantive counterarguments and shows whether they were answered.
- `Traceability`
  Every major claim points to evidence; the selected option is actually supported; provenance exists.
- `Observability`
  Has metrics, next actions, kill criteria, and a way to observe whether the decision worked.

### Hard gates

Any of the following should prevent a decision from being treated as trustworthy:

- no evidence
- no counterarguments
- no selected option
- fewer than two real options
- no supported claim for the chosen option
- no metrics

This is how the metric becomes hard to game inside DGC:

- it is object-backed, not vibe-backed
- it is deterministic, not self-scored
- it rewards grounded structure, not style
- it can be audited after the fact

No metric makes truth "unassailable." That is the wrong claim.

What we can make unassailable inside DGC is the internal standard:

`No high-impact decision counts as high quality unless the quality case passes its hard gates.`

## How DGC Should Use Its Models

Your instinct is right: the strongest models should be orchestrators and judges, while cheaper models do most of the wide search, challenge mining, and implementation work.

### Primary council

- `codex-primus`
  System architect, implementation judge, meta-level optimizer.
- `opus-primus`
  conceptual synthesizer, red-team reviewer, coherence and epistemic challenge partner.

These two should have equal standing on high-impact decisions.

### Secondary lanes

- `glm-researcher`
  ontology mapper, external source compressor, domain synthesis.
- `kimi-challenger`
  counterargument miner, failure mode finder, objection pressure.
- `minimax-challenger`
  long-context challenge lane, failure-mode expansion, and low-cost frontier pressure.
- `qwen-taxonomist`
  schema normalization, interface discipline, low-cost type and rule drafting.
- `nim-validator`
  contract validator, metric enforcer, boundary checker.
- low-cost coding lanes
  implement repeated code and tests after the primary council converges.

### Operating pattern

For any high-impact decision:

1. `Codex + Opus` define the decision object and required quality case.
2. `GLM + Kimi + MiniMax + Qwen` expand evidence, objections, and ontology fit.
3. `NIM` validates gates, metrics, and failure boundaries.
4. Cheap coding lanes implement only after the decision is typed and scored.
5. The system records outcome data and recalibrates routing later.

That is a real swarm cognition loop.

### Ingress transition layer

Add a shadow ingress classifier before the provider router, but do not let it replace the provider router.

- `tiny-router` style labels belong at the message-transition layer:
  `relation_to_previous`, `actionability`, `retention`, and `urgency`.
- The classifier should enrich routing and memory metadata so DGC can tell the
  difference between a new request, a correction, a cancellation, a closure,
  and a normal follow-up.
- In shadow mode it should not override the sovereign model contract.
- `Codex + Opus` remain the primary decision-makers; transition labels only
  help the system update the right task, preserve the right memory, and carry
  urgency truthfully across turns.

## Concrete DGC Upgrade Path

### Phase 0: stop trusting free text for important decisions

High-impact director decisions should no longer be raw markdown plus heuristic confidence.

Instead:

- materialize a `DecisionRecord`
- compute a `DecisionQualityAssessment`
- attach the result to the campaign ledger

### Phase 1: route by decision class

Reflex work can stay light.

But if a decision is:

- high impact
- low reversibility
- weakly evidenced
- cross-domain
- policy-sensitive

then it must route through the full council and quality case.

### Phase 2: make meta-evolution proposal-based

Changes to:

- routing policy
- quality formulas
- mission schema
- authority allocation

should go through proposal objects with review and merge semantics.

### Phase 3: tie outcomes back into the ontology

The final move is not scoring decisions before execution. It is learning whether those decisions were actually good.

So every important decision should later record:

- observed outcome
- surprise level
- reversal or regret
- metric delta
- whether the winning option actually dominated the rejected ones

Only then can DGC become intellectually smarter instead of just more elaborate.

## What I Added In This Turn

I added the first code substrate for this direction in:

- `dharma_swarm/decision_ontology.py`
- `tests/test_decision_ontology.py`

That module gives DGC:

- typed decision objects
- deterministic quality scoring
- hard gate failures
- a bridge from decision records into the existing `DecisionRouter`

This is not the full ontology yet, but it is the right substrate.

## Sources

Primary sources used:

- Palantir Architecture Center, The Ontology system
  https://www.palantir.com/docs/foundry/architecture-center/ontology-system/
- Palantir Ontology overview
  https://www.palantir.com/docs/foundry/ontology/overview
- Palantir types reference for object, link, action, and interface types
  https://www.palantir.com/docs/foundry/object-link-types/type-reference/
- Palantir TypeScript OSDK
  https://www.palantir.com/docs/foundry/ontology-sdk/typescript-osdk
- Palantir ontology edits / function-backed actions
  https://www.palantir.com/docs/foundry/functions/typescript-v2-ontology-edits/
- Palantir ontology proposals
  https://www.palantir.com/docs/foundry/ontologies/ontologies-proposals
- Palantir interfaces overview
  https://www.palantir.com/docs/foundry/interfaces/interface-overview/
- Palantir AIP Observability overview
  https://www.palantir.com/docs/foundry/aip-observability/overview/
- Palantir ontology permissions
  https://www.palantir.com/docs/foundry/ontologies/ontology-permissions
