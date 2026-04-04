# 2026-04-02 Terminal / TUI Convergence Merge Path

## Summary

This repo currently has two overlapping operator surfaces:

- `terminal/`, the Bun + Ink shell
- `dharma_swarm/tui/`, the Python Textual engine

They are not redundant copies. They are different shells with partially overlapping responsibilities. The highest merge risk in an overnight convergence build is not visual polish; it is semantic drift between shell state, runtime truth, session lifecycle, model routing, and command execution.

The goal of this note is to define a clean merge path that keeps the blast radius bounded while a shared operator brain is converged.

## Blast Radius Map

### 1. Session lifecycle and persistence

High risk because both sides persist or reconstruct operator state, but they do it with different abstractions.

- Bun shell owns local UI state, previews, and shell persistence in `terminal/src/persistence.ts` and `terminal/src/state.ts`.
- Python engine owns deeper session tracking in `dharma_swarm/tui/engine/session_state.py` and runtime flow in `dharma_swarm/tui/engine/provider_runner.py`.
- The bridge layer in `dharma_swarm/terminal_bridge.py` is the current seam that can either unify or duplicate session semantics.

Collision symptom:
- one shell resumes a turn the other shell does not recognize
- state is persisted in two formats
- compaction / replay / turn counters diverge

### 2. Model routing and provider selection

High risk because both stacks can decide what model or provider to use, and model policy is core brain logic rather than cosmetic UI.

- Bun shell has local model selection and route presentation in `terminal/src/app.tsx` and related components.
- Python engine owns provider orchestration and routing behavior in `dharma_swarm/tui/engine/provider_runner.py`.

Collision symptom:
- UI shows one active model while the underlying provider runner uses another
- policy changes do not propagate across shells
- fallbacks or approvals are handled twice

### 3. Runtime truth and operator status

High risk because both shells render “current state,” but the canonical source of truth is still split across UI-specific snapshots.

- Bun shell renders repo/control/runtime summaries through `terminal/src/protocol.ts`, `terminal/src/components/ControlPane.tsx`, and `terminal/src/components/RepoPane.tsx`.
- Python side renders richer live views through `dharma_swarm/tui/screens/command_center.py` and `dharma_swarm/tui/widgets/stream_output.py`.

Collision symptom:
- divergent health/status labels
- conflicting “live” indicators
- runtime data duplicated in two incompatible presentation pipelines

### 4. Command execution and approvals

High risk because this is where unsafe behavior appears if policy or gating drifts.

- Python governance logic is concentrated in `dharma_swarm/tui/engine/governance.py`.
- Bun shell surfaces commands, actions, and interactive controls in `terminal/src/app.tsx` and the component layer.

Collision symptom:
- approvals appear in one shell but not the other
- blocked actions are rendered as available
- command execution rules fork by shell

### 5. Navigation, panes, and identity of surfaces

Moderate-to-high risk because the two shells use different interaction models and different tab/screen taxonomies.

- Bun shell is tabbed and componentized: `terminal/src/app.tsx`, `terminal/src/components/*`
- Python shell is screen/widget oriented: `dharma_swarm/tui/app.py`, `dharma_swarm/tui/screens/*`, `dharma_swarm/tui/widgets/*`

Collision symptom:
- same concept has different names and different navigation targets
- routes drift in meaning between shells
- panes get rebuilt independently instead of sharing contracts

## Recommended File Ownership Boundaries

These boundaries are designed to support parallel work without stepping on each other.

### Bun shell ownership

Own all shell-specific UI and interaction code under:

- `terminal/src/app.tsx`
- `terminal/src/state.ts`
- `terminal/src/types.ts`
- `terminal/src/protocol.ts`
- `terminal/src/persistence.ts`
- `terminal/src/bridge.ts`
- `terminal/src/components/*`
- `terminal/tests/*`

This layer can change layout, interaction patterns, and visual structure, but it should not redefine core runtime semantics independently of the shared brain.

### Python TUI ownership

Own all provider/runtime/governance core and the richer Python UI under:

- `dharma_swarm/tui/app.py`
- `dharma_swarm/tui/engine/*`
- `dharma_swarm/tui/screens/*`
- `dharma_swarm/tui/widgets/*`

This layer can continue to hold core orchestration logic while the Bun shell converges, but it should not become a second source of truth for UI-facing contracts that the shared brain needs.

### Shared seam ownership

Treat these as bridge or contract stabilization zones:

- `dharma_swarm/terminal_bridge.py`
- any new shared schema / contract module
- any API or event definition used by both shells

These files should move toward transport + contract fidelity only. They should not accumulate shell-local behavior.

### Docs ownership

The following should remain the place for merge notes, risk tracking, and convergence planning:

- `docs/plans/*`
- `docs/reports/*`

## Staged Merge / Integration Checklist

### Stage 0: Freeze the contract surface

Before moving logic, identify the canonical contracts that both shells must share:

- session snapshot shape
- event envelope shape
- provider/model routing decision shape
- runtime truth snapshot shape
- command/approval decision shape

Rule:
- if a field is needed by both shells, define it once
- if a field is shell-only, keep it shell-local

### Stage 1: Reduce the bridge to transport

Goal:
- the bridge should move data, not invent policy

Actions:
- keep `dharma_swarm/terminal_bridge.py` focused on protocol translation and transport
- remove shell-specific decisioning from the bridge where possible
- ensure Bun and Python consume the same contract shapes

### Stage 2: Converge session state

Goal:
- one session model, one persistence story, one replay story

Actions:
- choose the canonical session owner
- align turn counters, summaries, and compaction semantics
- make resume/fork behavior explicit and deterministic

### Stage 3: Converge runtime truth

Goal:
- the two shells may render differently, but they must agree on facts

Actions:
- define one source of truth for repo/worktree/runtime status
- align health/degraded/blocked labels
- make preview rendering consume the same snapshot contract

### Stage 4: Align command and permission semantics

Goal:
- a blocked action must be blocked everywhere

Actions:
- centralize approval/gating rules
- ensure dangerous mutations are not reclassified differently by shell
- surface the same reason string or policy code in both surfaces

### Stage 5: Introduce shared entity and drilldown contracts

Goal:
- both shells should be able to inspect the same objects, but present them differently

Actions:
- define shared entity IDs and relation labels
- map runtime objects into a canonical entity model
- keep navigation semantics shell-specific, but identity shared

### Stage 6: Let the shells diverge intentionally

Goal:
- the brain is shared, the experience is different

Actions:
- Bun shell becomes the fast cockpit
- Python UI remains a richer or transitional operator surface if needed
- do not duplicate the same feature twice unless one implementation is clearly temporary

## Branch / Worktree Hygiene Warnings

1. The repo is already dirty. Avoid broad mechanical refactors that touch unrelated files.

2. There is a concurrent detached worktree on the same commit line. Assume another agent may change nearby files without warning.

3. Do not move implementation files between `terminal/` and `dharma_swarm/tui/` without a contract migration step. That is the easiest way to create invisible drift.

4. Do not rely on local shell state as proof of canonical behavior. Verify against the bridge and the runtime store.

5. Keep a single authoritative merge-path note and update it rather than creating competing versions.

6. If a file is both shell-facing and core-facing, treat it as a blast-radius hotspot and isolate changes carefully.

## Merge Safety Rules

- Prefer additive contract work before behavioral rewrites.
- Prefer transport simplification before UI unification.
- Prefer one canonical state model before replatforming surfaces.
- Prefer explicit partial support over silent fallback.
- Prefer small merges with clear ownership over a broad “all at once” convergence pass.

## Recommended Next Checks

If you are continuing the overnight build, the first follow-up review should verify:

- which session fields are truly canonical
- which provider decisions are shell-local
- whether the bridge is still making policy decisions
- whether runtime truth is duplicated in both shells
- whether any command gating differs between shells

