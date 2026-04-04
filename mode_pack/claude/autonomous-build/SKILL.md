---
title: Dharma Autonomous Build
path: mode_pack/claude/autonomous-build/SKILL.md
slug: dharma-autonomous-build
doc_type: skill
status: active
summary: Use this mode for bounded overnight autonomous cleanup or build execution where the lane, stop conditions, and hot-path exclusions are already explicit.
source:
  provenance: repo_local
  kind: skill
  origin_signals:
  - mode_pack/contracts/mode_pack.v1.json
  - docs/plans/2026-04-02-cleanup-control-center.md
  - docs/plans/2026-04-03-autonomous-cleanup-overnight-control.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- operations
- software_architecture
- verification
- knowledge_management
inspiration:
- operator_runtime
- verification
connected_relevant_files:
- mode_pack/contracts/mode_pack.v1.json
- docs/plans/2026-04-02-cleanup-control-center.md
- docs/plans/2026-04-02-generated-artifact-control-center.md
- docs/plans/2026-04-03-tui-baseline-protection-note.md
- docs/plans/2026-04-03-autonomous-cleanup-overnight-control.md
- docs/plans/2026-04-03-autonomous-build-skill-issues-and-fixes.md
improvement:
  room_for_improvement:
  - Keep the overnight loop bounded by explicit lane rules and stop conditions.
  - Add stronger examples of acceptable versus unacceptable autonomous widening.
  - Link future runtime wrappers or tmux launchers once they exist for this mode.
  next_review_at: '2026-04-05T12:00:00+09:00'
pkm:
  note_class: skill
  vault_path: mode_pack/claude/autonomous-build/SKILL.md
  retrieval_terms:
  - mode
  - pack
  - claude
  - autonomous
  - build
  - overnight
  - cleanup
  evergreen_potential: medium
stigmergy:
  meaning: This file provides a repo-local Claude mode for long-running autonomous execution that is still governed by lane boundaries and explicit stop conditions.
  state: active
  semantic_weight: 0.72
  coordination_comment: Use this mode when the work is already decomposed into a safe lane and the agent needs to keep iterating without reopening scope each cycle.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-03T20:45:00+09:00'
  curated_by_model: Codex (GPT-5)
  future_model_handoffs:
  - GPT-5 Codex
  - Claude
  - Gemini
  - Local evaluator
  schema_version: pkm-phd-stigmergy-v1
name: dharma-autonomous-build
description: Overnight autonomous execution mode for bounded cleanup or build lanes with strict scope and stop rules.
version: 1.0.0
allowed-tools:
- Read
- Grep
- Glob
- Bash
- Edit
- Write
---
# Dharma Autonomous Build

Use this mode only when the lane is already explicit, the hot paths are protected, and the stop conditions are written down.

## Objectives

- keep executing bounded cleanup or build work without reopening scope every cycle
- preserve lane integrity and avoid hot-path interference
- leave a truthful control trail after each tranche
- stop on ambiguity rather than silently widening into adjacent domains

## Required output

1. current lane
2. tranche completed
3. files changed
4. validation performed
5. residual risks
6. next bounded seam

## Rules

- do not widen from non-TUI cleanup into TUI or dashboard hot paths
- do not confuse “file exists” with “tracked and merge-safe”
- update YAML/frontmatter when touched prose would otherwise drift out of schema discipline
- write or update the active control docs as the lane evolves
- stop on unresolved ownership, path-coupling, or authority ambiguity and record it explicitly

## Handoff

Use [2026-04-03-autonomous-cleanup-overnight-control.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-autonomous-cleanup-overnight-control.md) as the lane owner.
Record any mode/runtime problems in [2026-04-03-autonomous-build-skill-issues-and-fixes.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-autonomous-build-skill-issues-and-fixes.md).
