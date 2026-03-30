# Runtime Convergence Hardening Design

**Date:** 2026-03-30

**Scope:** Stabilize the live `dharma_swarm` operator/runtime loop without changing the product thesis or adding major new subsystems. Continue the recent repository theme of wiring, feedback-loop closure, maintenance, and verification.

## Why This Exists

`dharma_swarm` is not failing because it lacks ambition. It is failing to fully hum because too many critical surfaces still depend on ambient local knowledge:

- runtime and repo roots are often assumed to be `~/dharma_swarm` and `~/.dharma`
- health is assembled in more than one place
- verification is spread across ad hoc commands instead of one canonical lane
- the CLI has a modular path and a monolithic path at the same time
- the repo still contains enough generated and machine-local material to increase cognitive and operational drag

The right move is not a redesign. The right move is convergence.

## What The Last 72 Hours Actually Say

Direct review of the repository history from 2026-03-27 through 2026-03-29 shows a clear pattern:

- the dominant recent intent is `feat(wire)`, not `feat(platform)` or `feat(rewrite)`
- the work clustered around feedback-loop closure, temporal continuity, ingestion wiring, runtime maintenance, health reporting, and search/runtime efficiency
- fixes immediately followed wiring when seams broke
- tests were added beside the higher-risk hardening changes
- the repo already started converging toward canonical paths, for example with API key centralization and the modular `dgc` package

Recent commits worth carrying forward as theme markers:

- `refactor: centralize all LLM API key resolution through api_keys.py`
- `fix(providers): resolve api_keys import error blocking DGC CLI`
- `feat(wire): B6-B10` for semantic ingestion bootstrap and contradiction surfacing
- `feat(wire): C11-C16` for mutation pressure, overnight adaptation, trace injection, and confidence decay
- `feat(wire): R1` for FTS5 candidate selection
- `feat(wire): R3` for launchd + `/health`
- `feat(wire): R4` for maintenance loop wiring

That is the line to continue.

## Design Goal

Weave three strands into one convergence program:

1. Runtime humming
2. Verification as a control loop
3. Structural simplification only where it improves the first two

This program should make the live system more reliable, easier to reason about, and cheaper to iterate on without broad architectural invention.

## Non-Goal

This design does **not** authorize:

- a new operator architecture
- a new public API surface unless it replaces or hardens an existing one
- a broad CLI rewrite
- a new agent framework
- movement of large conceptual/spec material purely for aesthetic cleanliness

## Core Rule

**Do not add a new subsystem when canonicalizing an existing subsystem will solve the problem.**

This is the anti-overengineering guardrail for the whole hardening lane.

## Recommendation

Choose a hybrid convergence strategy:

- stabilize the current architecture first
- pay down only the structural debt that directly blocks stability, verification, or operability
- defer broad refactors that do not produce immediate runtime or iteration benefits

This is the highest-ROI way to keep the current theme going.

## Program Shape

The hardening program has three linked spines.

### 1. Canonical Runtime Spine

Goal:

- one resolved runtime context
- one canonical state root
- one canonical repo root
- one canonical operator-health contract

Concretely:

- centralize root/path/env resolution
- remove direct `Path.home() / "dharma_swarm"` assumptions from hot runtime surfaces
- remove duplicate runtime payload assembly
- keep `dgc`, operator startup, API routes, and dashboard health reading from the same source

### 2. Canonical Verification Spine

Goal:

- one command that says whether the system is humming

Concretely:

- compile Python surfaces
- run the narrow operator/API/runtime contract suites
- run dashboard lint and build
- run the assurance gate
- run one CLI smoke command
- run one runtime supervision smoke serialization check
- optionally report repo-boundary drift

This should become the local and CI definition of "healthy enough to keep iterating."

### 3. Canonical Repo Spine

Goal:

- reduce ambient repo noise so the runtime and verification loops stay legible

Concretely:

- keep machine state out of the tracked source tree
- tighten generated-artifact policy
- keep docs/plans/reports useful without turning them into a second runtime
- continue decomposing the highest-friction control-plane monoliths only where it improves operability

## Phases

### Phase A: Humming Baseline

Deliverables:

- canonical runtime root resolution with explicit env overrides
- a single verification driver for local and CI use
- green dashboard lint/build
- green operator/API contract lane
- JSON-serializable runtime supervision payload
- one health contract shared across `/health`, `/api/health`, and operator reporting

Exit criteria:

- the front door is green
- the verification lane is trustworthy
- the operator surfaces agree on state and health

### Phase B: Friction Removal

Deliverables:

- repo-boundary checks folded into verification
- relocation or ignoring of non-source runtime/generated material where practical
- reduced cognitive load in static inventory and navigation
- explicit documentation of what belongs in source vs `~/.dharma`

Exit criteria:

- repo-local noise no longer obscures the runtime or verification story
- generated artifacts do not silently masquerade as source

### Phase C: Structural Completion

Deliverables:

- continue the `dgc` modular split only for the runtime/ops surfaces that matter most to humming
- remove duplicate health/payload assembly paths
- either implement or hide incomplete public surfaces such as placeholder GraphQL queries

Exit criteria:

- the highest-friction monoliths are smaller where it matters
- incomplete public surfaces no longer create false confidence

## Verification Loop

The control system for this program is:

`wire -> verify -> prune -> repeat`

### Loop Steps

1. Capture the current baseline.
2. Pick the narrowest seam that increases humming.
3. Make one canonical fix.
4. Run the smallest targeted verification that can prove the seam improved.
5. Run the canonical humming verification lane.
6. Record the delta and any remaining blockers.
7. Prune drift, duplication, or dead paths uncovered by that change.
8. Choose the next seam.

### What Counts As "Humming"

Minimum baseline:

- Python compile passes for active runtime/API/tests surfaces
- dashboard lint passes
- dashboard build passes
- assurance gate passes
- operator/API contract tests pass
- `python3 -m dharma_swarm.dgc status` exits cleanly
- runtime supervision output is structurally stable enough to inspect and serialize

Stretch baseline:

- the same verification lane is used locally and in CI
- runtime and dashboard health tell the same story
- path/root assumptions are injectable instead of ambient

## Design Principles

1. Preserve the front doors.
   Keep `dgc`, `run_operator.sh`, FastAPI, and the dashboard as the stable public operator surfaces.

2. Prefer canonicalization over invention.
   The fastest path to humming is usually to unify two existing seams, not create a third.

3. Treat verification as a product surface.
   If the verification story is ambiguous, the runtime will eventually become ambiguous too.

4. Remove ambient assumptions from hot paths.
   The most expensive bugs in this repo are often hidden in path, state, and launch assumptions.

5. Use structural refactors only when they pay an operational dividend.
   A refactor that only looks cleaner is not enough.

6. Keep the tranche small enough to review.
   The recent 92-file working batch is too wide to be a healthy steady-state hardening loop.

## Immediate Targets

The first hardening tranche should focus on:

- the canonical verify lane
- immediate front-door failures
- runtime path centralization
- health payload unification
- repo-boundary checks that fit naturally into verification
- narrow continuation of `dgc` ops/runtime decomposition

It should **not** begin with a broad rewrite.

## Deferred Until Later

- broad migration of every `~/dharma_swarm` reference in one pass
- moving or rewriting deep documentation/spec archives without operational benefit
- new dashboard product surfaces unrelated to runtime trust
- expanding GraphQL beyond a minimal honest surface

## Success Statement

This design succeeds if the repo feels less magical and more mechanical:

- the system starts the same way
- reports health the same way
- verifies the same way
- stores runtime state in the same places
- and can be hardened in narrow, reviewable increments without expanding its conceptual footprint

That is what "humming" means here.
