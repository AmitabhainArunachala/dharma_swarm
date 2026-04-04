---
title: Autonomous Build Skill Issues And Fixes
path: docs/plans/2026-04-03-autonomous-build-skill-issues-and-fixes.md
slug: autonomous-build-skill-issues-and-fixes
doc_type: plan
status: active
summary: Live issue log for the repo-local autonomous-build mode, recording what was missing, what was fixed, and what still requires an external runtime owner.
source:
  provenance: repo_local
  kind: cleanup_plan
  origin_signals:
  - mode_pack/claude/autonomous-build/SKILL.md
  - mode_pack/contracts/mode_pack.v1.json
  - docs/plans/2026-04-03-autonomous-cleanup-overnight-control.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- operations
- knowledge_management
- documentation
- verification
inspiration:
- operator_runtime
- canonical_truth
connected_relevant_files:
- mode_pack/claude/autonomous-build/SKILL.md
- mode_pack/contracts/mode_pack.v1.json
- mode_pack/README.md
- docs/plans/2026-04-03-autonomous-cleanup-overnight-control.md
- docs/plans/2026-04-02-cleanup-control-center.md
improvement:
  room_for_improvement:
  - Keep this log concrete and issue-shaped rather than turning it into general philosophy.
  - Convert resolved issues into stable contract updates where possible.
  - Add runtime launcher notes only when they are actually implemented and tested.
  next_review_at: '2026-04-04T12:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/2026-04-03-autonomous-build-skill-issues-and-fixes.md
  retrieval_terms:
  - autonomous
  - build
  - issues
  - fixes
  - overnight
  - cleanup
  evergreen_potential: medium
stigmergy:
  meaning: This file preserves the real friction around the autonomous-build mode so future overnight runs can improve the mechanism instead of rediscovering the same problems.
  state: active
  semantic_weight: 0.8
  coordination_comment: Update this note whenever the autonomous-build lane hits a mode or runtime problem that affects overnight execution quality.
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
---
# Autonomous Build Skill Issues And Fixes

## Purpose

This is the live issue log for the repo-local `dharma-autonomous-build` mode.

It records:

- what was missing
- what has already been fixed
- what still requires a human-owned runtime or launcher

## Current Issues

### 1. Missing canonical autonomous-build mode

Status: fixed

Problem:

- the mode pack had no canonical `autonomous-build` skill or slug
- overnight cleanup relied on lore, old conclave notes, or ad hoc sessions

Fix:

- added [mode_pack/claude/autonomous-build/SKILL.md](/Users/dhyana/dharma_swarm/mode_pack/claude/autonomous-build/SKILL.md)
- added a matching mode entry to `mode_pack/contracts/mode_pack.v1.json`

### 2. Missing overnight lane owner for non-TUI cleanup

Status: fixed

Problem:

- there was no single current control file for an overnight non-TUI hygiene run
- active doctrine existed, but it was spread across many cleanup notes

Fix:

- added [autonomous-cleanup-overnight-control.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-autonomous-cleanup-overnight-control.md)

### 3. No external runtime owner from this session alone

Status: partially fixed

Problem:

- a repo-local skill file does not by itself create a running overnight process
- this session can author the control surface, but it cannot truthfully claim infinite autonomous execution is now running unless a human or external supervisor launches it

Fix:

- added `scripts/start_autonomous_cleanup_tmux.sh`
- added `scripts/status_autonomous_cleanup_tmux.sh`
- added `scripts/stop_autonomous_cleanup_tmux.sh`

Current posture:

- the mode and lane are now defined
- the launcher exists and targets the bounded cleanup lane honestly
- a human or supervisor still has to invoke it and own the long-running process

### 4. Risk of lane drift during long unattended runs

Status: partially fixed

Problem:

- unattended cleanup can widen from docs authority into runtime churn if the lane contract is weak

Fix:

- the new skill and overnight control file explicitly ban TUI, dashboard, and unrelated runtime widening
- the cleanup control center remains the primary truth surface

### 5. Claude runtime may fail immediately for account/budget reasons

Status: open

Problem:

- the launcher can start the tmux session correctly while the underlying Claude run still exits immediately
- the first live launch in this repo failed with `Credit balance is too low`

Current posture:

- launcher wiring is now real and verified
- runtime health still depends on a valid Claude account/token/budget outside the repo itself
- this is an external execution prerequisite, not a repo-structure bug

## Operating Rule

Any time the autonomous-build lane fails because of:

- unclear scope
- missing launcher wiring
- stale control docs
- ambiguity between doctrine and implementation

record it here first, then fix the mechanism if the fix is low-blast-radius.
