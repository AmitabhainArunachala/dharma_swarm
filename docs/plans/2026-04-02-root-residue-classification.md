---
title: Root Residue Classification
path: docs/plans/2026-04-02-root-residue-classification.md
slug: root-residue-classification
doc_type: plan
status: active
summary: Classifies current repo-root residue into true entrypoints, root-coupled operational notes, future move candidates, and in-flight historical drains so root cleanup can proceed without guesswork.
source:
  provenance: repo_local
  kind: cleanup_plan
  origin_signals:
  - git status --short
  - README.md
  - CLAUDE.md
  - docs/architecture/GENOME_WIRING.md
  - LIVING_LAYERS.md
  - PRODUCT_SURFACE.md
  - docs/architecture/SWARMLENS_MASTER_SPEC.md
  - program.md
  - program_ecosystem.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- knowledge_management
- software_architecture
- documentation
- operations
- verification
inspiration:
- repo_topology
- canonical_truth
connected_relevant_files:
- docs/plans/2026-04-02-cleanup-control-center.md
- README.md
- CLAUDE.md
- docs/architecture/GENOME_WIRING.md
- LIVING_LAYERS.md
- PRODUCT_SURFACE.md
- docs/architecture/SWARMLENS_MASTER_SPEC.md
- program.md
- program_ecosystem.md
- docs/plans/2026-04-02-repo-dirt-taxonomy-and-run-plan.md
- docs/plans/2026-04-02-root-helper-artifact-policy.md
- docs/plans/2026-04-02-root-operational-notes-policy.md
- docs/plans/2026-04-02-program-pair-relocation-preaudit.md
- docs/plans/2026-04-02-root-next-tranche-plan.md
- docs/plans/2026-04-02-living-layers-preaudit.md
- docs/README.md
improvement:
  room_for_improvement:
  - Revisit the root-coupled operator notes after the substrate-layer pass clarifies doctrine versus architecture.
  - Convert the future-move set into one bounded relocation tranche instead of piecemeal drains.
  - Classify non-markdown root residue such as helper artifacts and scratch outputs separately from prose.
  next_review_at: '2026-04-03T12:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/2026-04-02-root-residue-classification.md
  retrieval_terms:
  - root
  - residue
  - classification
  - cleanup
  - repo
  - entrypoints
  evergreen_potential: medium
stigmergy:
  meaning: This plan turns the remaining repo-root prose into explicit classes so future cleanup stops treating root residue as one undifferentiated mess.
  state: active
  semantic_weight: 0.84
  coordination_comment: Use this file before moving or deleting any additional root-level prose.
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
# Root Residue Classification

## Scope

This pass classifies current repo-root prose and root-drain residue. It does not move additional files yet.

The goal is to decide what truly belongs at root, what remains there only because of workflow coupling, and what is already in a safe drain path.

## Root Classes

### 1. True Root Entrypoints

These files still make sense at repo root because they act as immediate operator or contributor entry surfaces.

- `README.md`
- `CLAUDE.md`

Why:

- they are repo entrypoints, not subtree-local doctrine
- they are expected at root by both humans and tooling
- moving them would not reduce confusion enough to justify the churn

### 2. Root-Coupled Operational Notes

These files are not ideal permanent root canon, but they still read like operator-facing or workflow-coupled notes whose current location may still be doing real work.

- `program.md`
- `program_ecosystem.md`
- `PRODUCT_SURFACE.md`

Why:

- they are still used like quick-start or operator-orientation notes
- they point directly into live runtime or ecosystem surfaces
- moving them now would require a stronger decision about whether they belong under `docs/`, `docs/architecture/`, or a future operator-doc subtree
- `PRODUCT_SURFACE.md` is a special case: it is still acting as a compact product-canon statement, so root retention is defensible until a deliberate canon migration happens

Action:

- keep `PRODUCT_SURFACE.md` at root for now
- treat `program.md` and `program_ecosystem.md` as the smallest safe relocation tranche candidates, but do not move them yet until a landing zone and backlink plan are in place
- the best current landing zone for the pair is `docs/plans/`, not `docs/missions/`, because they act like reusable operator runbooks rather than dated mission packets
- revisit through `docs/plans/2026-04-02-root-operational-notes-policy.md`
- use `docs/plans/2026-04-02-program-pair-relocation-preaudit.md` when the later code-aware move is being prepared

### 3. Future Move Candidates

These root files look semantically real, but not obviously root-worthy.

- `docs/architecture/GENOME_WIRING.md`
- `LIVING_LAYERS.md`
- `docs/architecture/SWARMLENS_MASTER_SPEC.md`

Why:

- they read more like architecture, conceptual substrate, or subsystem spec material than root entrypoints
- their current root presence gives them more authority than they likely deserve
- they need destination discipline before moving:
  - `docs/architecture/GENOME_WIRING.md`: architecture note no longer competing with root bootstrap
  - `LIVING_LAYERS.md`: likely substrate/research classification, not root canon
  - `docs/architecture/SWARMLENS_MASTER_SPEC.md`: now tracked outside root, but still needs a later judgment about architecture-local vs normative spec status

Action:

- do not move opportunistically
- take them as a bounded future tranche after the substrate-layer classification pass

### 4. In-Flight Historical Drains

These root files are already being drained into better homes. Their root-level presence in `git status` is expected cleanup churn, not fresh ambiguity.

Historical reports draining toward `reports/historical/`:

- `CONSTITUTIONAL_HARDENING_SPRINT_REPORT.md`
- `CONSTITUTIONAL_XRAY_REPORT.md`
- `DUAL_SPRINT_COMPLETION_REPORT.md`
- `FULL_REPO_AUDIT_2026-03-28.md`
- `PHASE2_COMPLETION_REPORT.md`
- `PHASE3_COMPLETION_REPORT.md`
- `WAVE2_ACCEPTANCE_CHECKLIST.md`
- `xray_report.md`

Architecture or navigation docs draining toward `docs/architecture/`:

- `INTEGRATION_MAP.md`
- `MODEL_ROUTING_CANON.md`
- `NAVIGATION.md`
- `VERIFICATION_LANE.md`

Prompt artifacts draining toward `docs/prompts/`:

- `MEGA_PROMPT_STRANGE_LOOP.md`
- `MEGA_PROMPT_v2.md`
- `MEGA_PROMPT_v3.md`
- `MEGA_PROMPT_v4.md`
- `ORTHOGONAL_UPGRADE_PROMPT.md`
- `PALANTIR_UPGRADE_PROMPT.md`
- `STRANGE_LOOP_COMPLETE_PROMPT.md`
- `STRANGE_LOOP_COMPLETE_PROMPT_v2.md`
- `STRATEGIC_PROMPT.md`

Why:

- these are already part of known cleanup tranches
- the remaining work is validation and tracking discipline, not fresh reclassification

## Non-Markdown Root Residue Worth Separate Attention

These are not part of the prose-root decision, but they still contribute to “why is root so noisy?” confusion:

- `CODEBASE_STRUCTURE_ANALYSIS.txt`
- `uv.lock`
- `synthesizer_memory.json`

Interpretation:

- `CODEBASE_STRUCTURE_ANALYSIS.txt` looks like a generated analysis artifact and should not become accidental canon
- `uv.lock` looks like an operational dependency lockfile and should be judged as package-management state rather than prose clutter
- `synthesizer_memory.json` looks like runtime/helper state rather than canonical root doctrine
- these should be classified in a later helper-artifact pass, not mixed into prose cleanup

## Decision Rule For The Next Root Pass

If a root file is:

- an actual repo entrypoint, keep it
- operator-coupled but not yet clearly placeable, defer it
- semantically strong but over-authoritative at root, queue it for a bounded move tranche
- already in an active drain path, do not reopen classification; just finish the existing move cleanly

## Recommended Next Move

Do not run a generic root cleanup.

The strongest next root-adjacent move is:

1. accept that the `specs/` prompt-and-closeout tranche is complete
2. accept that substrate classification for `foundations/`, `lodestones/`, and `mode_pack/` is now in place
3. focus the next bounded root move on:
   - `LIVING_LAYERS.md`
   - `program.md`
   - `program_ecosystem.md`

That sequence avoids turning root cleanup into a grab bag.

Substrate policy reference:

- `docs/plans/2026-04-02-substrate-layer-policy.md`

Future move preaudit:

- `docs/plans/2026-04-02-root-future-move-preaudit.md`
- `docs/plans/2026-04-02-living-layers-preaudit.md`

Current-state reconciliation:

- `docs/plans/2026-04-02-root-state-reconciliation.md`
