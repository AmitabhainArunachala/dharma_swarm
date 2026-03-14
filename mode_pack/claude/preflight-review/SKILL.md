---
name: dharma-preflight-review
description: Pre-landing review mode for structural bugs, trust boundaries, and ship blockers.
version: 1.0.0
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash
---

# Dharma Preflight Review

Use this mode when the code or plan is nearly ready and you need to know what can still hurt you in production.

## Objectives

- Find critical risks before merge or release.
- Focus on structural bugs, silent failures, trust boundaries, and missing tests.
- Produce a findings-first output ordered by severity.

## Required output

1. Findings by severity
2. Trust-boundary notes
3. Test gaps
4. Ship blockers

## Rules

- Findings first, summary second.
- Do not waste time on style-only feedback.
- If there are no findings, say that explicitly.
- If a critical blocker exists, do not act as if the branch is ready.

## Handoff

If clear, hand off to `dharma-ship` or `dharma-qa`.
