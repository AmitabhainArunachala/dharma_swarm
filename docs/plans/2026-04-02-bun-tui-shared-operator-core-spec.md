# Bun TUI Shared Operator Core Spec

## Context

The repo currently has:

- a Bun + Ink terminal shell in `terminal/`
- a deeper Python Textual TUI engine in `dharma_swarm/tui/`
- a Python `terminal_bridge.py` acting as the transitional semantic center for the Bun shell

This split is useful for proving concepts, but it is not the long-run architecture.

## Decision

The Bun TUI becomes the canonical operator shell.

The Python TUI engine is not the long-run shell. Its durable value is its runtime logic:

- provider adapters
- canonical event streaming
- governance and permission filtering
- session state + store
- command-center runtime truth integration

That logic must converge into a shell-neutral shared operator core.

## Immediate Convergence Target

Create a shell-neutral package:

- `dharma_swarm/operator_core/`

The first step is not moving all logic at once. The first step is freezing the canonical contracts that all future work must obey.

### Canonical contracts added

- `CanonicalSession`
- `CanonicalEventEnvelope`
- `CanonicalPermissionDecision`
- `CanonicalRoutingDecision`
- `CanonicalRuntimeSnapshot`
- `CanonicalEntity`
- `CanonicalRelation`
- `CanonicalWorkflowState`

These are defined in:

- `dharma_swarm/operator_core/contracts.py`

## Ownership Model

### Shared core owns

- session truth
- event truth
- routing truth
- permission truth
- workflow truth
- runtime truth
- entity truth

### Bun shell owns

- layout
- panes
- transcript choreography
- keyboarding
- command palette
- operator ergonomics

### Dashboard owns

- visual topology
- graph-heavy drilldowns
- map-room style interaction

Neither shell owns domain semantics.

## Migration rule

No new domain logic should be introduced into:

- `terminal/src/*`
- `dashboard/src/*`

unless it is explicitly shell-local presentation logic.

If the logic would need to be duplicated in the dashboard later, it belongs in `operator_core`.

## Transitional truth

`terminal_bridge.py` remains transitional.

For now it still assembles runtime summaries and shell-facing snapshot payloads.
During convergence, its role should shrink from semantic authority to transport/adaptation layer.

## Next implementation slices

1. Map existing Python TUI canonical events into `CanonicalEventEnvelope`.
2. Map current session store metadata into `CanonicalSession`.
3. Map runtime snapshot assembly from `terminal_bridge.py` into `CanonicalRuntimeSnapshot`.
4. Teach the Bun shell to consume the shared contracts rather than ad hoc preview strings wherever possible.
5. Keep protocol text rendering as a compatibility layer during migration.

## Non-negotiable constraint

Do not create:

- Bun-only session semantics
- dashboard-only entity semantics
- another bridge-shaped brain

The architecture only compounds if both shells continue to converge on one operator core.
