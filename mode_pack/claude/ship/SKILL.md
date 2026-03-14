---
name: dharma-ship
description: Release mode for a ready branch with tests, versioning, changelog, and PR discipline.
version: 1.0.0
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash
  - Edit
  - Write
---

# Dharma Ship

Use this mode only for a branch that is already ready to land.

## Objectives

- Sync with main
- Run tests
- Apply version/changelog discipline
- Push and open the PR or release artifact

## Required output

1. Test results
2. Release notes
3. Version update
4. PR or release status

## Rules

- Do not use this mode to decide what to build.
- Stop on failed tests or unresolved critical blockers.
- Prefer non-interactive automation once the branch is truly ready.

## Handoff

After ship, hand off to `dharma-qa` for release verification and `dharma-retro` after completion.
