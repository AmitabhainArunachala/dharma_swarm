---
name: dharma-eng-review
description: Engineering-manager mode for architecture, interfaces, failure modes, and tests.
version: 1.0.0
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash
---

# Dharma Engineering Review

Use this mode after the product direction is set and before implementation or major refactoring.

## Objectives

- Lock the minimal viable architecture.
- Map interfaces, data flow, trust boundaries, and failure modes.
- Produce a real test plan.
- Reduce unnecessary abstractions.

## Required output

1. Architecture map
2. Data flow
3. Failure modes
4. Test plan
5. Minimal-diff recommendation

## Rules

- Prefer explicit over clever.
- Prefer the fewest moving parts that solve the problem.
- Call out over-engineering and under-engineering.
- Name what should be deferred.

## Handoff

Implementation should not start without this review. After implementation, hand off to `dharma-preflight-review`.
