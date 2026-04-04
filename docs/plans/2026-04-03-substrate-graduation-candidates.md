---
title: Substrate Graduation Candidates
path: docs/plans/2026-04-03-substrate-graduation-candidates.md
slug: substrate-graduation-candidates
doc_type: plan
status: active
summary: Separates likely stay-put substrate files from possible graduation candidates in foundations and lodestones, while explicitly confirming mode_pack as an operational contract surface rather than a prose-cleanup target.
source:
  provenance: repo_local
  kind: cleanup_plan
  origin_signals:
  - docs/plans/2026-04-03-substrate-directory-cartography.md
  - foundations/INDEX.md
  - lodestones/README.md
  - mode_pack/README.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- knowledge_management
- documentation
- software_architecture
- operations
- verification
inspiration:
- repo_topology
- canonical_truth
connected_relevant_files:
- docs/plans/2026-04-03-substrate-directory-cartography.md
- docs/plans/2026-04-02-substrate-layer-policy.md
- foundations/SAMAYA_PROTOCOL.md
- foundations/THINKODYNAMIC_BRIDGE.md
- foundations/EMPIRICAL_CLAIMS_REGISTRY.md
- lodestones/CONSCIOUS_INFRASTRUCTURE.md
- lodestones/bridges/telos_as_syntropic_attractor.md
- lodestones/grounding/agentic_ai_landscape_2026.md
- mode_pack/README.md
improvement:
  room_for_improvement:
  - Add file-by-file justifications only when a specific graduation move is approved.
  - Revisit candidates if they become more tightly cited by architecture or specs.
  - Keep this note as a candidate map, not a silent move authorization.
  next_review_at: '2026-04-04T12:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/2026-04-03-substrate-graduation-candidates.md
  retrieval_terms:
  - substrate
  - graduation
  - candidates
  - foundations
  - lodestones
  - mode_pack
  evergreen_potential: high
stigmergy:
  meaning: This file turns the substrate cartography into a concrete keep-versus-graduate candidate map without triggering premature moves.
  state: active
  semantic_weight: 0.85
  coordination_comment: Use this note before proposing any file-level move out of foundations or lodestones.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-03T02:12:00+09:00'
  curated_by_model: Codex (GPT-5)
  future_model_handoffs:
  - GPT-5 Codex
  - Claude
  - Gemini
  - Local evaluator
  schema_version: pkm-phd-stigmergy-v1
---
# Substrate Graduation Candidates

## Purpose

This note identifies:

- substrate files that should clearly stay where they are
- substrate files that may eventually graduate outward
- the current non-negotiable status of `mode_pack/`

This is a candidate map, not a move order.

## `foundations/`

### Likely stay-put canonical substrate

These look correctly placed as conceptual canon:

- `PILLAR_01_LEVIN.md` through `PILLAR_11_BEER.md`
- `FOUNDATIONS_SYNTHESIS.md`
- `META_SYNTHESIS.md`
- `SYNTHESIS_DEACON_FRISTON.md`
- `GLOSSARY.md`
- `EMPIRICAL_CLAIMS_REGISTRY.md`

Reason:

- they behave like deep conceptual substrate or canon-index material, not like live product doctrine

### Possible graduation candidates

- `SAMAYA_PROTOCOL.md`
  - candidate direction: `docs/architecture/` or `specs/` only if it becomes operational doctrine rather than contemplative-computational substrate
- `THINKODYNAMIC_BRIDGE.md`
  - candidate direction: `docs/architecture/` if it hardens into active architecture doctrine
- `ECONOMIC_VISION.md`
  - candidate direction: `docs/research/` or a strategy/report surface if it becomes more evidence-led than substrate-led

Current posture:

- keep all of these in `foundations/` for now
- mark them as graduation-watch candidates, not move-now candidates

## `lodestones/`

### Likely stay-put orienting substrate

These look correctly placed as directional or generative material:

- `seeds/**`
- `reframes/**`
- `bridges/telos_as_syntropic_attractor.md`
- `CONSCIOUS_INFRASTRUCTURE.md`

Reason:

- they read as attractors, bridges, or conceptual reframes rather than settled canon or normative implementation truth

### Possible graduation candidates

- `grounding/agentic_ai_landscape_2026.md`
  - candidate direction: `docs/research/` if it becomes more like a maintained evidence brief than lodestone grounding
- `pillars_expanded/**`
  - candidate direction: `foundations/` only if specific files become clearly canonical rather than expanded interpretive companions

Current posture:

- keep in `lodestones/` for now
- watch `grounding/` and `pillars_expanded/` for authority drift

## `mode_pack/`

### Explicit stay-put status

`mode_pack/` should stay where it is.

Reason:

- it is an operational contract/workflow surface
- it includes machine-readable contract material
- it is not substrate prose and should not be treated as a docs-cleanup casualty

Current posture:

- no graduation review needed
- no relocation pressure
- preserve as operational contract layer

## Current Best Read

The substrate layer is not mainly blocked on movement.

It is blocked on authority labeling:

1. which files are clearly deep substrate
2. which files are orienting and should remain interpretive
3. which files might later harden into architecture, research, or spec truth
4. which directories are operational rather than prose

## Recommended Next Move

The next safe substrate tranche is:

1. add local indexing or labels for the likely stay-put classes
2. add a small watchlist for the graduation candidates
3. do not move files yet unless one candidate has become obviously live doctrine

## Control Entry Points

- [substrate-directory-cartography.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-substrate-directory-cartography.md)
- [substrate-layer-policy.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-substrate-layer-policy.md)
