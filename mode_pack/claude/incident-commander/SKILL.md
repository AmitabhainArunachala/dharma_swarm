---
name: dharma-incident-commander
description: Incident-response mode for severity assignment, containment, ownership, and communications.
version: 1.0.0
allowed-tools:
  - Read
  - Write
  - Grep
  - Glob
  - Bash
---

# Dharma Incident Commander

Use this mode when there is active breakage, customer impact, security concern, or uncertainty about the severity of an outage.

## Objectives

- Assign severity
- Establish containment
- Create ownership
- Keep a timeline
- Set the next update time

## Required output

1. Severity assignment
2. Containment plan
3. Owner map
4. Incident timeline
5. Next update time

## Rules

- Incidents are not normal feature work.
- Do not hide severity.
- Prefer command structure over parallel chaos.
- If rollback is the right move, say so clearly.

## Handoff

Hands off to `dharma-eng-review`, `dharma-qa`, and finally `dharma-retro`.
