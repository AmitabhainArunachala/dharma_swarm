# DGC Unified Operator Shell Design

**Date:** 2026-03-26

**Goal:** make `dgc` feel like one clean, transcript-first, intent-first operator shell while keeping the `dharma_swarm` engine substantially unchanged.

## Scope

This design is for the terminal operator surface only.

It intentionally does **not** redesign:

- `dharma_swarm/swarm.py`
- `dharma_swarm/orchestrator.py`
- `dharma_swarm/agent_runner.py`
- `dharma_swarm/providers.py`
- the web/dashboard product surface

The purpose of this slice is to unify the shell above the engine, not to rewrite the engine.

## Current State

The repo currently exposes multiple overlapping terminal strands:

1. `dgc` via `dharma_swarm/dgc_cli.py`
2. `dharma-swarm` via `dharma_swarm/cli.py`
3. the newer Textual client in `dharma_swarm/tui/`
4. the legacy Textual client in `dharma_swarm/tui_legacy.py`
5. native Claude passthrough via `dgc chat`

This creates three kinds of drift:

- command drift: batch CLI and TUI commands are not defined in one place
- interaction drift: plain language, slash commands, and native external clients are separate user experiences
- capability drift: local skills, agents, and command packs are not represented as one coherent registry

## Product Direction

`dgc` should become one operator shell with two faces:

- **Interactive face:** transcript-first inline shell, optimized for normal terminal use
- **Batch face:** clean one-shot command execution for scripting, copy/paste, and inspection

The shell should be:

- transcript-first
- copy-first
- intent-first
- mode-aware
- capability-aware
- transparent about what it is doing

The shell should **not** be:

- dashboard-first
- alternate-screen dependent
- command-memory heavy
- a second runtime parallel to the engine

## Core Principles

### 1. One Public Front Door

The public brand is `dgc`.

`dharma-swarm` can remain as compatibility or internal tooling, but the user-facing operator identity should converge on `dgc`.

### 2. Transcript First

The main experience should feel like Claude Code or Codex:

- persistent readable transcript
- multiline input
- stable scrollback
- clean tool event summaries
- easy selection and copy

Dashboard views should exist, but as secondary overlays or inspector screens.

### 3. Copy-Paste Is A First-Class Requirement

No important information should exist only in widgets, color, or dense panels.

Every meaningful output must have a clean plain-text form. Rich presentation is an enhancement layer, not the only representation.

### 4. Intent Before Commands

Users should be able to say:

- "show me what's broken"
- "plan this first"
- "open the most useful view"
- "help me debug the live runtime"

Commands remain available for precision and scripting, but natural language becomes the primary interface.

### 5. Transparency Over Magic

If the shell auto-selects a mode, command path, or view, it should say so explicitly.

Example:

- `Interpreting this as: health inspection`
- `Switching to Plan mode`
- `Opening Command Center: runtime + anomalies`

## Target Architecture

The terminal surface should converge on five pieces.

### 1. Shell Core

Owns:

- intent parsing
- command registry
- mode resolution
- shell actions
- capability selection
- presentation contracts

This is the canonical operator interaction layer.

### 2. Clients

Two clients sit on top of the shell core:

- interactive transcript client
- batch CLI client

They should share command vocabulary and output contracts.

### 3. Engine Bridges

Thin adapters connect the shell to the existing runtime:

- runtime status and health
- swarm/task operations
- provider execution
- session and history
- inspector/dashboard actions

These bridges should wrap existing engine functionality rather than replace it.

### 4. Capability Registry

The shell should not directly ingest raw skill text into every prompt.

Instead it should maintain a normalized registry of capabilities from:

- Codex skills
- Claude skills
- Claude agents
- Claude commands
- Agni workspace skills
- OpenClaw/shared skill sources
- later: trusted external repositories and field discovery

The canonical unit is a **capability with provenance**, not a raw skill file.

### 5. Presentation Layer

Same shell output, different renderers:

- transcript renderer for interactive mode
- plain text renderer for batch mode

Rich rendering should always degrade cleanly to copyable text.

## Interaction Model

### Default Mode

`dgc` with no arguments should open the interactive transcript shell.

This shell should default to inline behavior where terminal support is good, preserving normal terminal selection and scrollback.

### Batch Mode

`dgc <command>` should run one-shot operations through the same shell vocabulary and render clean plain-text output.

### Natural Language

Plain text should be interpreted as user intent first.

Possible outcomes:

- conversational request
- command resolution
- mode switch suggestion
- inspector view selection
- plan-first action

### Slash Commands

Slash commands remain for precision:

- `/status`
- `/health`
- `/runtime`
- `/dashboard`
- `/plan`

They should route through the same shared registry as batch CLI commands.

## Modes

User-facing modes should be conceptually simple:

- **Chat:** normal transcript mode
- **Plan:** read/scope before mutation
- **Auto:** autonomous execution lane
- **Ops:** inspection/intervention lane

The current internal markers can remain, but the user-facing shell should present clearer semantics.

## Command Model

The shell should expose one command vocabulary in two forms:

- batch: `dgc status`
- interactive: `/status`

Families should converge around:

- `system`: status, health, runtime, doctor, logs
- `work`: swarm, task, ledger, session, artifact
- `intelligence`: model, provider, routing, plan
- `views`: dashboard, agents, lineage, ontology

No important capability should exist only in one surface.

## Output Model

### Required Properties

The output model should optimize for:

- direct terminal selection
- stable transcript reading
- compact default summaries
- explicit expansion for detail
- plain-text copyability

### Rules

- tool activity defaults to short summaries, not giant raw dumps
- long outputs can be folded in UI but copy as full text
- tables need a compact text representation by default
- the shell should always be usable without color

## Capability Registry Design

The first implementation slice should support a local capability census.

Each capability record should carry:

- `capability_id`
- `name`
- `kind`
- `source_system`
- `source_path`
- `summary`
- `intent_triggers`
- `trust_tier`
- `recency`
- `promotion_status`
- `merged_into`

This lets the shell retrieve the right capability pack without stuffing every raw file into the live interaction loop.

## Future Intake: Skill Seeker

The design should leave room for a follow-on subsystem:

- **Local Seeker:** scans local repos and configs
- **Repo Watcher:** watches trusted GitHub repos in quarantine
- **Field Seeker:** watches curated web/social sources for emerging patterns
- **Integration Judge:** ranks, deduplicates, and proposes promotions

This should feed the capability registry through promotion gates, not merge raw material directly into the shell core.

## Migration Direction

The terminal convergence path is:

1. create a shared operator shell layer
2. extract a shared command registry
3. route TUI and batch CLI through that registry
4. preserve transcript-first behavior as the default interaction model
5. add local capability indexing
6. demote legacy TUI to compatibility-only
7. keep external repo/social intake as a future extension

## Error Handling

The shell should fail clearly and reversibly:

- unknown intent falls back to conversation with a suggestion
- ambiguous intent yields a visible interpretation prompt or suggestion
- high-risk operations must remain explicit
- unavailable capabilities should fail with source and reason
- mode switches should always be visible to the user

## Testing

The shell convergence slice should be covered with:

- command registry unit tests
- intent routing unit tests
- capability indexing unit tests
- CLI dispatch regression tests
- interactive Textual transcript tests
- copy/paste and scrollback behavior tests

The most important invariant is simple:

`dgc` should feel like one product surface, even though it offers both interactive and batch use.
