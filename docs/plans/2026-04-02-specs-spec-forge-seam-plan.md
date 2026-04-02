---
title: Specs vs Spec-Forge Seam Plan
path: docs/plans/2026-04-02-specs-spec-forge-seam-plan.md
slug: specs-vs-spec-forge-seam-plan
doc_type: plan
status: active
summary: Defines the next bounded cleanup seam between normative specs, forge-stage specs, and non-spec material currently mixed into specs/.
source:
  provenance: repo_local
  kind: cleanup_plan
  origin_signals:
    - specs/README.md
    - spec-forge/README.md
    - docs/prompts/PARALLEL_BUILD_AGENT_PROMPTS_2026-03-19.md
    - docs/prompts/SOVEREIGN_BUILD_PHASE_MASTER_PROMPT_2026-03-19.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
  - knowledge_management
  - software_architecture
  - verification
  - operations
inspiration:
  - repo_hygiene
  - canonical_truth
connected_relevant_files:
  - specs/README.md
  - spec-forge/README.md
  - docs/prompts/PARALLEL_BUILD_AGENT_PROMPTS_2026-03-19.md
  - docs/prompts/SOVEREIGN_BUILD_PHASE_MASTER_PROMPT_2026-03-19.md
  - docs/archive/VERIFICATION_COMPLETE.md
  - docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md
improvement:
  room_for_improvement:
    - Turn this seam plan into a single executed tranche with updated indices.
    - Mark superseded specs explicitly inside specs/.
    - Classify research material under specs/ more sharply after the prompt tranche is removed.
  next_review_at: '2026-04-03T12:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/2026-04-02-specs-spec-forge-seam-plan.md
  retrieval_terms:
    - specs
    - spec-forge
    - cleanup
    - canonical
    - forge
  evergreen_potential: medium
stigmergy:
  meaning: This file defines the next clean boundary between normative specifications and forge-stage or prompt-heavy material.
  state: active
  semantic_weight: 0.84
  coordination_comment: Use this file to choose one bounded specs cleanup tranche without widening into broad repo churn.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-02T23:59:00+09:00'
  curated_by_model: Codex (GPT-5)
  schema_version: pkm-phd-stigmergy-v1
---
# Specs vs Spec-Forge Seam Plan

## Current Reality

The split between `specs/` and `spec-forge/` is conceptually strong and now documented in both index files:

- [`specs/README.md`](/Users/dhyana/dharma_swarm/specs/README.md) says `specs/` is the normative, formal, protocol, and verification layer.
- [`spec-forge/README.md`](/Users/dhyana/dharma_swarm/spec-forge/README.md) says `spec-forge/` is the incubation lane for emerging specifications.

The main problem is no longer directory meaning. The problem is mixed occupancy inside `specs/`.

## What Is Clearly In Bounds For `specs/`

These are good fits for `specs/`:

- formal artifacts such as `TaskBoardCoordination.tla` and `TaskBoardCoordination.cfg`
- bounded subsystem specs such as `KERNEL_CORE_SPEC.md`
- durable protocol and ontology specs such as `ONTOLOGY_PHASE2_SQLITE_UNIFICATION_SPEC_2026-03-19.md`
- stable schema and contract material such as `Dharma_Corpus_Schema.md`

## What Is Clearly Mixed Or Weakly Placed

These files did not read like enduring normative specs:

- `docs/prompts/PARALLEL_BUILD_AGENT_PROMPTS_2026-03-19.md`
- `docs/prompts/SOVEREIGN_BUILD_PHASE_MASTER_PROMPT_2026-03-19.md`
- `docs/archive/VERIFICATION_COMPLETE.md`

They are prompt-heavy, wave-specific, or completion-report style material.

## Ambiguous But Not First-Move Targets

These should not be moved in the first tranche without deeper coupling review:

- `specs/DGC_TERMINAL_ARCHITECTURE.md`
- `specs/DGC_TERMINAL_ARCHITECTURE_v1.1.md`
- `specs/SOVEREIGN_BUILD_PHASE_MASTER_SPEC_2026-03-19.md`
- `specs/STIGMERGY_11_LAYER_SPEC_2026-03-23.md`
- `specs/research/`
- `specs/research_living_layers/`

Reasons:

- some still function as active architectural reference
- some may belong in `docs/architecture/` rather than `spec-forge/`
- some are research substrate, which is a separate classification question

## Executed Tranche

The strongest bounded move was a prompt-and-completion tranche out of `specs/`, and that move is now staged.

### Moved Files

- `docs/prompts/PARALLEL_BUILD_AGENT_PROMPTS_2026-03-19.md`
- `docs/prompts/SOVEREIGN_BUILD_PHASE_MASTER_PROMPT_2026-03-19.md`
- `docs/archive/VERIFICATION_COMPLETE.md`

### Destinations

- prompt-heavy files moved to `docs/prompts/` because they remain useful as reusable prompt artifacts
- completion or wave-closeout material moved to `docs/archive/` because it reads as historical verification residue rather than current normative spec truth

## Working Rule

Do not move architectural specs and prompt packets in the same tranche.

The first tranche should only remove the obviously non-normative files from `specs/`.

## Validation Standard

Any implementation pass on this seam should:

1. update `specs/README.md`
2. update any direct live references to the moved files
3. preserve frontmatter integrity
4. keep the tranche Git-real and merge-safe
5. avoid touching `spec-forge/` family structure unless a move explicitly targets it

## Why This Is The Right Next Step

This move improves the repo in three ways at once:

- it makes `specs/` more truthful
- it reduces top-level ambiguity between specs and prompts
- it avoids the harder coupling questions around architecture and research material until the easy win is complete
