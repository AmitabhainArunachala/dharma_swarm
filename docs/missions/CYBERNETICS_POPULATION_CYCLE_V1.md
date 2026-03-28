# Cybernetics Population Cycle V1

**Status**: Ready to seed after first live lever
**Date**: 2026-03-27
**Purpose**: Populate the cybernetics stratum in a way that changes runtime behavior, not just the reading archive.

## Why This Cycle Exists

The cybernetics directive is now a live execution lane. The next failure mode is obvious:
- the seats run, but the intellectual genome stays thin
- readings accumulate, but governance variety does not materially increase
- the system talks about Beer and Ashby without pushing their force into code, routing, or audit

This cycle exists to prevent that failure. It turns cybernetics reading into:
- corpus claims
- citation edges
- contradiction records
- one bounded governance diff

## Governing Principles

1. **Depth over breadth**
One tradition through all layers before adding another. Cybernetics first.

2. **Stratified extraction, not summaries**
Every source yields:
- thesis kernel
- load-bearing passages
- structural DAG
- loss manifest

3. **Transmission vector is the code diff**
If the reading does not alter code, routing, or gate logic, it remains decorative.

4. **Contradictions are first-class**
Conflicts between Ashby, Beer, Hofstadter, and contemplative frames are not noise. They are tracked and tested.

5. **Metabolism beats intake**
The point is not to read more. The point is to increase governance variety and reduce hot-path disconnection.

## Primary Sources For This Cycle

1. W. Ross Ashby, *An Introduction to Cybernetics* (1956)
2. Roger Conant and W. Ross Ashby, *Every Good Regulator of a System Must Be a Model of that System* (1970)
3. Stafford Beer, core VSM/governance material already reflected in [07_VSM_GOVERNANCE.md](/Users/dhyana/dharma_swarm/docs/telos-engine/07_VSM_GOVERNANCE.md)

## Existing Assets To Reuse

- [semantic_population_plan.md](/Users/dhyana/.claude/projects/-Users-dhyana/memory/semantic_population_plan.md)
- [feedback_deep_reading_pipeline.md](/Users/dhyana/.claude/projects/-Users-dhyana/memory/feedback_deep_reading_pipeline.md)
- [RECURSIVE_READING_PROTOCOL.md](/Users/dhyana/dharma_swarm/docs/RECURSIVE_READING_PROTOCOL.md)
- [seed_ashby_citations.py](/Users/dhyana/dharma_swarm/scripts/seed_ashby_citations.py)
- [ingest_ashby_claims.py](/Users/dhyana/dharma_swarm/scripts/ingest_ashby_claims.py)
- [seed_contradictions.py](/Users/dhyana/dharma_swarm/scripts/seed_contradictions.py)
- [policy_compiler.py](/Users/dhyana/dharma_swarm/dharma_swarm/policy_compiler.py)
- [structured_predicate.py](/Users/dhyana/dharma_swarm/dharma_swarm/structured_predicate.py)

## Required Outputs

1. **Canon packet**
One durable note that maps which Ashby/Beer/Conant passages matter for:
- PolicyCompiler
- telos gates
- orchestrator routing
- witness/audit
- stigma and corpus loops

2. **Stratified extraction packet**
At minimum:
- thesis kernel
- 12+ load-bearing passages
- structural DAG
- loss manifest

3. **Live substrate ingestion**
Run or extend:
- claim ingestion into DharmaCorpus
- citation seeding
- contradiction seeding

4. **One bounded governance delta**
Choose exactly one of:
- `policy_compiler.py`
- `provider_policy.py`
- `orchestrator.py`
- `telos_gates.py`

The delta must be justified by the reading packet, not by convenience.

5. **Audit note**
State whether the cycle increased governance variety or merely produced better prose.

## The Bounded Loop

1. Build canon map.
2. Extract stratified reading packet.
3. Ingest claims, citations, contradictions.
4. Force one code diff into the hot path.
5. Audit and decide whether to continue with Beer depth or pivot to semantic governance unification.

## Non-Goals

- Adding another tradition before cybernetics is metabolized
- Producing a literature review with no runtime effect
- Expanding the ontology surface without increasing behavioral regulation
- Treating seat activity as success if the code diff never lands

## Acceptance Criteria

A cycle counts as successful only if all of the following are true:

1. At least one new durable reading artifact exists in `~/.dharma/shared/` or `~/.dharma/reading_program/`.
2. DharmaCorpus, citations, or contradictions increased measurably.
3. A concrete governance-path file changed or a clearly justified diff proposal was produced.
4. An audit note states what changed in runtime behavior or why the cycle failed.

## Launch

When the current live lever and its audit complete, seed this cycle with:

```bash
python3 scripts/seed_cybernetics_population_cycle.py
```
