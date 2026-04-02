---
title: Reports Cartography And Cleanup Plan
path: docs/plans/2026-04-02-reports-cartography-and-cleanup-plan.md
slug: reports-cartography-and-cleanup-plan
doc_type: plan
status: active
summary: "Date: 2026-04-02 Purpose: classify the reports layer into historical, generated, and active-reference surfaces and choose the next cleanup seam."
source:
  provenance: repo_local
  kind: plan
  origin_signals:
  - docs/GENERATED_ARTIFACT_BOUNDARY_MATRIX_2026-04-02.md
  - reports/repo_xray_2026-03-31.md
  - docs/plans/2026-04-02-non-tui-repo-hygiene-map.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- knowledge_management
- operations
- documentation
- verification
inspiration:
- repo_topology
- canonical_truth
connected_relevant_files:
- docs/plans/2026-04-02-cleanup-control-center.md
- docs/plans/2026-04-02-generated-artifact-control-center.md
- docs/plans/2026-04-02-retained-generated-packet-families-preaudit.md
- docs/GENERATED_ARTIFACT_BOUNDARY_MATRIX_2026-04-02.md
- reports/generated/README.md
- reports/historical/GODEL_CLAW_V1_REPORT.md
- reports/repo_xray_2026-03-31.md
improvement:
  room_for_improvement:
  - Keep this note focused on report topology rather than turning it into a full generated-state ontology.
  - Add packet-family policy only when those families are ready for a dedicated pass.
  next_review_at: '2026-04-03T12:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/2026-04-02-reports-cartography-and-cleanup-plan.md
  retrieval_terms:
  - reports
  - cartography
  - cleanup
  - generated
  - historical
  - packets
  - control center
  evergreen_potential: high
stigmergy:
  meaning: This file maps the reports layer into generated, historical, packetized, and active-reference surfaces for later cleanup sequencing.
  state: active
  semantic_weight: 0.82
  coordination_comment: Use this file when choosing the next bounded reports cleanup seam.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-02T23:59:00+09:00'
  curated_by_model: Codex (GPT-5)
  future_model_handoffs:
  - GPT-5 Codex
  - Claude
  - Gemini
  - Local evaluator
  schema_version: pkm-phd-stigmergy-v1
---
# Reports Cartography And Cleanup Plan

Date: 2026-04-02
Scope: `reports/`

## Thesis

`reports/` is not one thing.

It currently mixes:

- durable historical authored reports
- generated run artifacts
- verification outputs
- audit packets
- a few still-useful active reference reports

That is one of the biggest remaining sources of repo noise.

The right move is not “clean reports.”
It is to separate report classes so evidence stops competing with doctrine.

## Current Topology

Top dirty buckets inside `reports/`:

- `reports/psmv_hyperfiles_20260313`
- `reports/dual_engine_swarm_20260313_run`
- `reports/architectural`
- `reports/dgc_self_proving_packet_20260313`
- `reports/verification`
- `reports/historical`

This confirms that most `reports/` noise is concentrated in generated or packetized report families, not in the small set of genuinely durable historical notes.

## Classification

### 1. Historical Keep

These should remain readable in git and should not be treated as clutter.

Primary family:

- `reports/historical/`

Examples:

- `reports/historical/FULL_REPO_AUDIT_2026-03-28.md`
- `reports/historical/GODEL_CLAW_V1_REPORT.md`
- `reports/historical/CONSTITUTIONAL_XRAY_REPORT.md`

Meaning:

- historical authored evidence
- acceptable to keep in git
- should not compete with live doctrine

### 2. Generated / Quarantine Candidates

These are the biggest report-noise families.

Primary families:

- `reports/dual_engine_swarm_20260313_run/`
- `reports/psmv_hyperfiles_20260313/`
- `reports/nightwatch/`
- parts of `reports/verification/`

Why:

- strong machine-output characteristics
- packetized or log-like structure
- high audit value in some cases, but low doctrine value

Recommended posture:

- classify under a stronger generated-state boundary
- consider future `reports/generated/` or external retention strategy

### 3. Active Reference Reports

These are reports, but they still have meaningful operator/reference value.

Examples:

- `reports/repo_xray_2026-03-31.md`
- `reports/dharma_current_state_deep_dive_2026-03-19.md`
- `reports/ecosystem_absorption_master_index_2026-03-19.md`
- `reports/ecosystem_forensics_audit_2026-03-19.md`

Meaning:

- still worth citing during cleanup or architecture decisions
- should remain visible, but should be explicitly treated as evidence, not canon

### 4. Packet Families

These are neither simple historical notes nor pure logs.

Primary families:

- `reports/dgc_self_proving_packet_20260313/`
- `reports/xray_revenue_packet_20260313/`
- `reports/gaia_eco_pilot_20260327/`

Meaning:

- campaign or packet bundles
- mixed authored/generated content
- should likely remain grouped, but should not sit conceptually beside canon

Recommended posture:

- keep as packet families for now
- do not attempt piecemeal cleanup until packet policy is explicit

### 5. Verification Families

Primary family:

- `reports/verification/`

Meaning:

- partly generated
- partly authored manifests
- high value for evidence
- weak fit as current doctrine

Recommended posture:

- do not flatten or purge
- later split into:
  - authored verification manifests
  - generated probe outputs

## Best Next Seam

The strongest next seam is not moving everything in `reports/`.

It is:

### Seam A: Classify and isolate the obviously generated report families

Best candidates:

- `reports/nightwatch/`
- `reports/dual_engine_swarm_20260313_run/`
- `reports/psmv_hyperfiles_20260313/`

Why:

- they are structurally the clearest generated/noise families
- they dominate the dirty report topology
- separating them lowers noise faster than touching historical reports

Current status:

- `reports/nightwatch/` has now been rehomed under `reports/generated/nightwatch/` as the first concrete generated-report quarantine move
- `reports/dual_engine_swarm_20260313_run/` is not yet a safe relocation seam because code, tests, and packet docs still point at its current paths
- `reports/psmv_hyperfiles_20260313/` is also not yet a safe relocation seam because code, tests, and mission docs still point at it

### Seam B: Keep historical reports stable

Do not churn:

- `reports/historical/`

Why:

- it is already a good destination
- it is not the main problem now

## Recommended Order

1. Add an explicit `reports/generated/` policy in docs before moving more report families.
2. Classify `reports/nightwatch/` as generated-only and lowest-risk quarantine material.
3. Classify `reports/dual_engine_swarm_20260313_run/` and `reports/psmv_hyperfiles_20260313/` as retained generated packet families and explicitly defer relocation.
4. Defer packet-family surgery (`dgc_self_proving_packet`, `xray_revenue_packet`, `gaia_eco_pilot`) until packet policy is clear.
5. Leave `reports/historical/` alone.

## Cleanest Immediate Move

The cleanest immediate next report-layer artifact after `nightwatch/` is not a file move.

It is a stronger report ontology note that says:

- what counts as historical
- what counts as generated
- what counts as packetized
- what counts as active reference evidence

And, specifically:

- which generated packet families are still path-coupled and must stay put for now

That gives later cleanup tranches a stable frame.

Current control entrypoint:

- [2026-04-02-generated-artifact-control-center.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-generated-artifact-control-center.md)
- [2026-04-02-retained-generated-packet-families-preaudit.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-retained-generated-packet-families-preaudit.md)

## Stop Point

Do not start moving large report families blindly.

The right stop point for this stage is:

- one clear report cartography map
- one explicit generated-vs-historical-vs-packet posture
- one next bounded seam chosen from the generated families
