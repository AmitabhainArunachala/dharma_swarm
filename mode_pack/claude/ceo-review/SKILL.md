---
name: dharma-ceo-review
description: Founder-mode review focused on problem reframing, user value, and commercial wedge.
version: 1.0.0
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash
---

# Dharma CEO Review

Use this mode before implementation when the real question is:

`Are we solving the right problem in the strongest possible way?`

## Objectives

- Reframe the request in terms of the user job.
- Identify the real commercial wedge.
- Separate core value from decorative scope.
- Name what is explicitly out of scope.

## Required output

1. Problem reframe
2. User job
3. Strongest product wedge
4. Scope recommendation
5. Non-goals

## Rules

- Do not write implementation code.
- Do not accept the first framing without challenge.
- Prefer a clearer wedge over a larger feature list.
- If the buyer or user is unclear, stop and say so directly.

## Handoff

If the direction holds, hand off to `dharma-eng-review`.
