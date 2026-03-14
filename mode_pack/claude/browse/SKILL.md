---
name: dharma-browse
description: Browser-operation mode for fast navigation, verification, and screenshot capture.
version: 1.0.0
allowed-tools:
  - Read
  - Bash
---

# Dharma Browse

Use this mode when browser automation is the right tool.

## Objectives

- Navigate pages quickly
- Capture state cleanly
- Reuse the existing browser stack instead of inventing a new one

## Required output

1. Navigation result
2. State snapshot

## Rules

- Prefer the repo's existing browser workflow or `gstack browse` if installed and working.
- Do not use browser automation when file inspection or API inspection is enough.
- Preserve evidence with screenshots or snapshots when the result matters.

## Handoff

Usually hands off to `dharma-qa` or `dharma-incident-commander`.
