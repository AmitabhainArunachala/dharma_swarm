---
title: Verification Probe Citation Census
path: docs/plans/2026-04-03-verification-probe-citation-census.md
slug: verification-probe-citation-census
doc_type: plan
status: active
summary: Records which verification probe artifacts remain live-cited and which uncited traces were relocated into reports/generated/verification/ during the first generated-only move tranche.
source:
  provenance: repo_local
  kind: cleanup_plan
  origin_signals:
  - docs/plans/2026-04-03-verification-family-retention-policy.md
  - reports/verification/dgc_full_power_probe_20260313T015447Z.md
  - reports/verification/provider_smoke_20260313T071659Z.json
  - rg repo-wide citation scan on 2026-04-03
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- verification
- knowledge_management
- operations
- documentation
inspiration:
- verification
- canonical_truth
connected_relevant_files:
- docs/plans/2026-04-03-uncited-verification-probe-relocation-preplan.md
- docs/plans/2026-04-03-verification-family-retention-policy.md
- docs/plans/2026-04-03-verification-family-classification-preaudit.md
- reports/verification/dgc_full_power_probe_20260313T015447Z.md
- reports/verification/provider_smoke_20260313T071659Z.json
- reports/dgc_self_proving_packet_20260313/working_system_spec.md
- reports/dgc_self_proving_packet_20260313/proof_packet.md
- reports/dgc_self_proving_packet_20260313/director_summary.md
- reports/architectural/dgc_decision_intelligence_council_review_20260314_codex_primus.md
improvement:
  room_for_improvement:
  - Re-run this census before any actual relocation tranche because citations may change.
  - Separate cleanup-doc self-references from genuinely live product or evidence references if needed.
  - Add paired md/json linkage rules if probe families are partially relocated.
  next_review_at: '2026-04-04T12:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/2026-04-03-verification-probe-citation-census.md
  retrieval_terms:
  - verification
  - probe
  - citation
  - census
  - cited
  - uncited
  evergreen_potential: medium
stigmergy:
  meaning: This file turns the verification retention policy into a concrete first-move candidate list by separating cited probe artifacts from uncited ones.
  state: active
  semantic_weight: 0.84
  coordination_comment: Use this note before moving any verification probe traces into a generated subtree.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-03T01:23:00+09:00'
  curated_by_model: Codex (GPT-5)
  future_model_handoffs:
  - GPT-5 Codex
  - Claude
  - Gemini
  - Local evaluator
  schema_version: pkm-phd-stigmergy-v1
---
# Verification Probe Citation Census

## Purpose

This census distinguishes verification probe artifacts that remain cited live from those that were uncited enough to relocate into `reports/generated/verification/`.

That distinction was the minimum requirement for the first generated-only relocation tranche and remains the basis for future moves.

## Census Scope

Probe-like targets checked:

- `dgc_full_power_probe_20260312T131318Z.{md,json}`
- `dgc_full_power_probe_20260312T135427Z.{md,json}`
- `dgc_full_power_probe_20260313T015447Z.{md,json}`
- `dgc_full_power_probe_20260324T153444Z.{md,json}`
- `provider_smoke_20260313T071659Z.json`
- `eval_probe_task_20260325T141025Z.md`

Scan method:

- repo-wide `rg` outside `reports/verification/`
- cleanup-doc self-references are noted separately from live evidence references

## Live-Cited Probe Artifacts

### Path-stable for now

- `dgc_full_power_probe_20260313T015447Z.md`
  - cited in:
    - [working_system_spec.md](/Users/dhyana/dharma_swarm/reports/dgc_self_proving_packet_20260313/working_system_spec.md)
    - [proof_packet.md](/Users/dhyana/dharma_swarm/reports/dgc_self_proving_packet_20260313/proof_packet.md)
    - [director_summary.md](/Users/dhyana/dharma_swarm/reports/dgc_self_proving_packet_20260313/director_summary.md)
  - current posture:
    - keep path-stable

- `provider_smoke_20260313T071659Z.json`
  - cited in:
    - [proof_packet.md](/Users/dhyana/dharma_swarm/reports/dgc_self_proving_packet_20260313/proof_packet.md)
    - [dgc_decision_intelligence_council_review_20260314_codex_primus.md](/Users/dhyana/dharma_swarm/reports/architectural/dgc_decision_intelligence_council_review_20260314_codex_primus.md)
  - current posture:
    - keep path-stable

## Relocated Uncited Probe Artifacts

The following artifacts were moved into `reports/generated/verification/`:

- `reports/generated/verification/dgc_full_power_probe_20260312T131318Z.md`
- `reports/generated/verification/dgc_full_power_probe_20260312T131318Z.json`
- `reports/generated/verification/dgc_full_power_probe_20260312T135427Z.md`
- `reports/generated/verification/dgc_full_power_probe_20260312T135427Z.json`
- `reports/generated/verification/dgc_full_power_probe_20260313T015447Z.json`
- `reports/generated/verification/dgc_full_power_probe_20260324T153444Z.md`
- `reports/generated/verification/dgc_full_power_probe_20260324T153444Z.json`
- `reports/generated/verification/eval_probe_task_20260325T141025Z.md`

Current posture:

- these now live in the generated verification subtree
- recheck citations before any further move or pruning

## Cleanup-Doc Self-References

Some probe filenames now appear in cleanup doctrine because of this census and the verification policy/preaudit notes.

Those mentions do not make a file operationally path-stable by themselves.

## Executed First-Move Set

The first generated-only move tranche relocated:

- uncited `dgc_full_power_probe_*` outputs other than the `20260313T015447Z` markdown evidence file
- `eval_probe_task_20260325T141025Z.md`

Do not include:

- `dgc_full_power_probe_20260313T015447Z.md`
- `provider_smoke_20260313T071659Z.json`

until their live evidence citations are handled in the same tranche.

Executed from preplan:

- [2026-04-03-uncited-verification-probe-relocation-preplan.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-uncited-verification-probe-relocation-preplan.md)

## Control Entry Points

- [verification-family-retention-policy.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-verification-family-retention-policy.md)
- [verification-family-classification-preaudit.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-verification-family-classification-preaudit.md)
