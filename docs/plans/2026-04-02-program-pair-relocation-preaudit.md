---
title: Program Pair Relocation Preaudit
path: docs/plans/2026-04-02-program-pair-relocation-preaudit.md
slug: program-pair-relocation-preaudit
doc_type: plan
status: active
summary: Records the real blocker and best current landing path for relocating program.md and program_ecosystem.md out of repo root.
source:
  provenance: repo_local
  kind: cleanup_plan
  origin_signals:
    - program.md
    - program_ecosystem.md
    - dharma_swarm/long_context_sidecar_eval.py
    - tests/test_long_context_sidecar_eval.py
    - docs/plans/2026-04-02-root-operational-notes-policy.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
  - repository_hygiene
  - operations
  - software_architecture
  - verification
inspiration:
  - canonical_truth
  - operator_runtime
connected_relevant_files:
  - program.md
  - program_ecosystem.md
  - dharma_swarm/long_context_sidecar_eval.py
  - tests/test_long_context_sidecar_eval.py
  - docs/plans/2026-04-02-root-operational-notes-policy.md
  - docs/plans/2026-04-02-root-next-tranche-plan.md
improvement:
  room_for_improvement:
    - Count and repair any remaining live backlinks before the paired move is attempted.
    - Decide whether a future docs/runbooks subtree is warranted after more operator-note classification is complete.
    - Convert the later move into one bounded code-and-doc tranche instead of a prose-only cleanup pass.
  next_review_at: '2026-04-03T12:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/2026-04-02-program-pair-relocation-preaudit.md
  retrieval_terms:
    - program
    - program ecosystem
    - relocation
    - preaudit
    - root
  evergreen_potential: medium
stigmergy:
  meaning: This file turns the program pair from a vague future cleanup idea into a concrete later tranche with known blockers.
  state: active
  semantic_weight: 0.8
  coordination_comment: Use this before relocating program.md and program_ecosystem.md.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-02T22:25:00+09:00'
  curated_by_model: Codex (GPT-5)
  schema_version: pkm-phd-stigmergy-v1
---
# Program Pair Relocation Preaudit

## Scope

This file covers only:

- `program.md`
- `program_ecosystem.md`

The goal is to decide whether they can leave repo root yet, and if not, what exactly blocks the move.

## What They Are

These are not root bootstrap docs in the same sense as `README.md` or `CLAUDE.md`.

They are:

- operational runbooks
- autonomy / autoresearch instructions
- procedural notes

They belong together semantically and should move together whenever the relocation happens.

## Best Current Destination

The best current landing path is still:

- `docs/plans/program.md`
- `docs/plans/program_ecosystem.md`

Why:

- both files read as bounded runbooks rather than canon
- `docs/plans/` already exists and is not surprising
- `docs/missions/` is too campaign-shaped and date-shaped for these reusable operator runbooks
- creating a new subtree just for this pair is premature right now

## Why They Should Not Move Yet

This is not only a docs problem.

There is still explicit code/test coupling to `program.md` at repo root:

- `dharma_swarm/long_context_sidecar_eval.py` reads `repo_root / "program.md"`
- `tests/test_long_context_sidecar_eval.py` writes and expects `program.md` at repo root

That makes the relocation a later code-aware tranche, not a prose-only cleanup pass.

## Safe Later Move

When the move is taken, it should be one bounded tranche that does all of this together:

1. move `program.md`
2. move `program_ecosystem.md`
3. repair the `long_context_sidecar_eval.py` path assumption
4. repair the corresponding test fixture
5. update any remaining live doc backlinks

## Current Decision

- keep both files at root for now
- do not move one without the other
- do not move them in a docs-only pass
- revisit only when a code-aware tranche is acceptable
