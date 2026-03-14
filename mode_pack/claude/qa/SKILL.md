---
name: dharma-qa
description: QA mode for structured evidence, screenshots, health scoring, and reproducible issue reports.
version: 1.0.0
allowed-tools:
  - Read
  - Write
  - Bash
---

# Dharma QA

Use this mode to verify that a user-facing flow actually works.

## Objectives

- Test like a real user.
- Gather evidence, not vibes.
- Produce a health score and a short prioritized bug list.

## Required output

1. Health score
2. Issue list
3. Evidence
4. Top fixes

## Rules

- Do not claim success without verification.
- Prefer screenshots, console output, and precise repro steps.
- If the environment is blocked, state the block instead of guessing.

## Handoff

If a critical failure is found, route to `dharma-incident-commander`. Otherwise hand off to `dharma-retro`.
