---
title: DHARMA SWARM 1000x Masterplan
path: docs/archive/DHARMA_SWARM_1000X_MASTERPLAN_2026-03-16.md
slug: dharma-swarm-1000x-masterplan
doc_type: documentation
status: active
summary: 'Date: 2026-03-16'
source:
  provenance: repo_local
  kind: documentation
  origin_signals:
  - dharma_swarm/swarm.py
  - dharma_swarm/orchestrator.py
  - dharma_swarm/engine/knowledge_store.py
  - pyproject.toml
  - dharma_swarm/dgc_cli.py
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- multi_agent_systems
- software_architecture
- knowledge_management
- research_methodology
- verification
- frontend_engineering
inspiration:
- verification
- operator_runtime
- product_surface
- research_synthesis
connected_python_files:
- dharma_swarm/swarm.py
- dharma_swarm/orchestrator.py
- dharma_swarm/engine/knowledge_store.py
- dharma_swarm/dgc_cli.py
- dharma_swarm/thinkodynamic_director.py
connected_python_modules:
- dharma_swarm.swarm
- dharma_swarm.orchestrator
- dharma_swarm.engine.knowledge_store
- dharma_swarm.dgc_cli
- dharma_swarm.thinkodynamic_director
connected_relevant_files:
- dharma_swarm/swarm.py
- dharma_swarm/orchestrator.py
- dharma_swarm/engine/knowledge_store.py
- pyproject.toml
- dharma_swarm/dgc_cli.py
improvement:
  room_for_improvement:
  - Strengthen cross-links to adjacent docs and implementing modules.
  - Separate durable knowledge from transient session context.
  - Add a tighter summary for first-pass retrieval.
  - Review whether this file should stay in `docs` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: documentation
  vault_path: docs/archive/DHARMA_SWARM_1000X_MASTERPLAN_2026-03-16.md
  retrieval_terms:
  - 1000x
  - masterplan
  - '2026'
  - date
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: working
  semantic_weight: 0.6
  coordination_comment: 'Date: 2026-03-16'
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising docs/archive/DHARMA_SWARM_1000X_MASTERPLAN_2026-03-16.md reinforces its salience without needing a separate message.
    marker_based:
      what_it_is: The frontmatter is an explicit annotation layer on top of the document.
      semantic_mark: Semantic weight, improvement prompts, related files, and provenance comments tell later agents how to use this document.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-01T00:43:19+09:00'
  curated_by_model: Codex (GPT-5)
  source_model_in_file: 
  future_model_handoffs:
  - GPT-5 Codex
  - Claude
  - Gemini
  - Local evaluator
  schema_version: pkm-phd-stigmergy-v1
---
# DHARMA SWARM 1000x Masterplan

Date: 2026-03-16

This is an additive plan for turning `dharma_swarm` into a faster, more elegant,
more operationally trustworthy system without deleting existing work.

## Current Shape

The repo already has meaningful mass:

- Roughly 250+ Python modules under `dharma_swarm/`
- 228 Python test files and about 4000 collected tests
- A separate Next.js dashboard under `dashboard/`
- One GitHub Actions workflow that only runs pytest
- A very large operational script surface under `scripts/`

The system is not empty. It already has:

- A real orchestrator path in `dharma_swarm/swarm.py` and `dharma_swarm/orchestrator.py`
- A clean local-vs-Qdrant retrieval seam in `dharma_swarm/engine/knowledge_store.py`
- A large test estate, which is a major asset
- Multiple runtime surfaces: CLI, API, TUI, dashboard, cron, launchd, tmux
- Conceptual coverage for memory, evolution, telemetry, routing, gates, and ecosystem awareness

That means the 1000x move is not "add more ideas". It is:

1. Select a small canonical core
2. Push everything else behind explicit seams
3. Make operations measurable and reproducible
4. Move the hottest loops into faster runtimes only where it pays

## What Works

These are real strengths, not aspirations:

- Test coverage breadth is unusually high for a repo this exploratory.
- The package has strong concept coverage across orchestration, memory, evaluation, routing, and telemetry.
- `engine/knowledge_store.py` is the right pattern: lightweight default, optional heavy backend.
- `swarm.py` and `orchestrator.py` already look like real control-plane candidates.
- The dashboard is separated from the Python package instead of being mixed into it.
- Optional dependency groups in `pyproject.toml` already hint at a layered architecture.

## What Is Blocking 1000x

### 1. Complexity is concentrated in a few god files

Measured hotspots:

- `dharma_swarm/dgc_cli.py`: about 5800 lines
- `dharma_swarm/thinkodynamic_director.py`: about 4700 lines
- `dharma_swarm/evolution.py`: about 2600 lines
- `dharma_swarm/tui/app.py`: about 2500 lines
- `dharma_swarm/runtime_state.py`: about 1800 lines
- `dharma_swarm/swarm.py`: about 1600 lines
- `dharma_swarm/providers.py`: about 1600 lines

These files are not just large. They are also some of the most connected parts of the system.
That is where elegance and speed are being lost.

### 2. Coupling is too high around the wrong modules

Static import analysis shows:

- `dharma_swarm.models` is the most imported local module by far
- `dharma_swarm.dgc_cli` is the biggest outbound importer
- `dharma_swarm.swarm`, `evolution`, `agent_runner`, and `providers` are also highly connected

This means there is no small stable kernel yet. Too many things know too much.

### 3. Ops is real, but fragmented

The repo has multiple operational entrypoints:

- CLI commands
- cron runner
- cron daemon
- launchd job runner
- tmux startup/status scripts
- dashboard
- API and TUI surfaces

That is useful raw capability, but the control plane is not singular enough.
There should be one canonical way to start, stop, inspect, and verify the system.

### 4. CI is too thin for the size of the system

Right now CI only runs pytest.

Missing from the canonical workflow:

- `compileall`
- linting
- type checks
- dashboard build
- smoke tests for CLI and runtime surfaces
- artifact generation for x-ray and benchmark reports

### 5. Baseline reliability is not green

The branch is not currently passing tests.

The first observed failing test is:

- `tests/test_adaptive_autonomy.py::TestAutonomyDecisions::test_aggressive_approves_most`

A 1000x system cannot be "conceptually complete but branch-red". Green baseline is mandatory.

## The 1000x Target Architecture

The right shape is a four-layer system.

### Layer 0: Kernel

Small, stable, typed, boring.

Owns:

- task and event contracts
- state transitions
- scheduling contracts
- agent lifecycle contracts
- append-only runtime facts

Canonical modules should eventually live under something like:

- `dharma_swarm/kernel/`
- `dharma_swarm/contracts/`
- `dharma_swarm/control_plane/`

This layer should be the hardest to change and the easiest to test.

### Layer 1: Fast Path

This is where performance-critical services live.

Owns:

- event ingestion and log compaction
- retrieval indexing
- vector or lexical search acceleration
- scheduling queues
- high-volume telemetry aggregation

This layer is where Rust is justified first.

### Layer 2: Intelligence

Python remains the right default here.

Owns:

- provider routing
- prompt assembly
- evaluation heuristics
- meta-evolution logic
- context composition
- policy experiments

This layer changes quickly and should not be frozen too early.

### Layer 3: Surfaces

User and operator interfaces.

Owns:

- Typer CLI
- TUI
- FastAPI/API surface
- dashboard
- launchd/cron/tmux wrappers

These surfaces should be thin adapters over the kernel and intelligence layers.

## Where Rust Should Go

Rust is useful here, but only for specific pain points.

### Rust Tier 1: Do This First

1. Event log and trace spine

Candidates:

- runtime event store
- session ledger
- trace store
- append-only witness or merkle log

Why Rust:

- deterministic IO
- strong concurrency
- safe append-only storage
- low-latency streaming to dashboard or CLI

2. Retrieval and indexing engine

Candidates:

- context search
- semantic digester preprocessing
- chunking and token indexing
- hybrid retrieval scoring

Why Rust:

- faster local indexing
- much better memory behavior on large corpora
- clean FFI/service boundary for Python

3. Scheduler or dispatch queue

Candidates:

- orchestration queue
- DAG executor internals
- high-throughput task claiming and leasing

Why Rust:

- removes Python contention from the control loop
- gives you a reliable daemon-grade core

### Rust Tier 2: Maybe Later

- telemetry rollups
- route scoring
- file scanning and workspace graphing

### Do Not Move to Rust Yet

- provider policy
- prompt engineering
- evaluation heuristics
- research loops
- experimental meta-agents

Those are still changing too fast. Python is the right medium there.

## Where Go May Be Better Than Rust

Use Go, not Rust, if the problem is primarily operational rather than computational.

Good Go candidates:

- one binary for daemon supervision
- process manager for cron, launchd, tmux, and gateway unification
- lightweight control API service

If the goal is "reliable small ops binary", Go can be the faster win.
If the goal is "fast safe core engine", Rust is the better choice.

## What Should Be Sharpened First

### 1. Split the god files without deleting them

Do not delete legacy entrypoints. Replace them with facades.

For `dgc_cli.py`:

- keep the file as the public shell
- move commands into `dharma_swarm/cli_commands/`
- group by domain: `ops`, `memory`, `kernel`, `swarm`, `evolution`, `dashboard`

For `thinkodynamic_director.py`:

- split policy selection
- split scoring heuristics
- split execution policies
- split prompt text and templates
- split metrics and reporting

For `swarm.py`:

- move initialization wiring to a builder module
- move subsystem registry to a separate runtime container
- keep `SwarmManager` as thin coordinator, not giant constructor

### 2. Create a canonical control plane

There should be one explicit control surface for:

- start
- stop
- status
- doctor
- inspect
- benchmark
- xray

Everything else should be adapters to that.

### 3. Separate "core", "experimental", and "ops"

Right now those concerns are intermixed.

The repo needs an explicit map:

- `dharma_swarm/core/` or `kernel/`
- `dharma_swarm/experimental/` or `labs/`
- `dharma_swarm/ops/`
- `dharma_swarm/surfaces/`

No deletions are needed. Start with canonical aliases and migration docs.

### 4. Standardize runtime contracts

Every cross-layer boundary should use explicit typed payloads:

- event envelopes
- task claims
- agent status snapshots
- benchmark outputs
- dashboard API payloads

The repo already has pieces of this. It needs one contract registry.

## What Connections Need Tightening

### CLI -> Kernel

The CLI should delegate to small application services, not import half the system directly.

### Swarm -> Provider Layer

Provider routing should be injected by interface, not discovered ad hoc inside big coordinators.

### Runtime -> Dashboard

The dashboard should be fed from structured event and metrics streams, not inferred from scattered state files.

### Scripts -> Productized Ops

Most of `scripts/` are valuable prototypes.
The right move is not deletion.
The right move is to:

- classify scripts as `canonical`, `prototype`, or `deprecated-wrapper`
- keep canonical ones reachable through `make` or `dgc ops ...`
- keep prototypes in place but stop pretending they are the control plane

### Tests -> Architectural Seams

The test suite is broad, but the architectural seams are not yet obvious enough.
Tests should increasingly align to:

- kernel tests
- control-plane tests
- provider tests
- surface tests
- benchmark tests

## What Is Missing

### Missing Operational Pieces

- A local task runner surface at repo root
- A repeatable static architecture inventory
- CI steps beyond pytest
- benchmark baselines for context build, dispatch, retrieval, and CLI startup
- one authoritative environment and config story

### Missing Architecture Pieces

- canonical subsystem registry
- module ownership map
- explicit compatibility layer for legacy entrypoints
- architecture decision records for the kernel, retrieval, and ops control plane

### Missing Performance Pieces

- startup latency budget
- dispatch latency budget
- retrieval latency budget
- dashboard data freshness budget
- trace/event throughput budget

### Missing Reliability Pieces

- green branch discipline
- smoke tests for ops entrypoints
- dashboard build in CI
- compile step in CI

## Recommended Next Sequence

### Phase 1: Stabilize

1. Make baseline green.
2. Add compile and x-ray to the local workflow.
3. Add dashboard build to CI.
4. Freeze a canonical control-plane surface.

### Phase 2: Decouple

1. Split `dgc_cli.py` into domain command modules.
2. Split `thinkodynamic_director.py` by policy, scoring, and prompts.
3. Refactor `swarm.py` initialization into a builder/container layer.
4. Introduce a contracts package for runtime payloads.

### Phase 3: Accelerate

1. Move event log and trace spine behind a service boundary.
2. Build or adopt a Rust retrieval/indexing service.
3. Benchmark context search, retrieval, and dispatch end-to-end.
4. Stream metrics directly to the dashboard.

### Phase 4: Productize

1. One operator command surface.
2. One daemon lifecycle story.
3. One architecture index.
4. One performance report generated on demand.

## Immediate Wins Landed in This Pass

This pass adds additive repo-level tooling:

- `scripts/repo_xray.py`: static inventory for complexity and coupling
- `Makefile`: root-level entrypoints for x-ray, compile, smoke tests, and dashboard build

That is not the whole 1000x system. It is the beginning of one.

## Bottom Line

`dharma_swarm` already has enough substance to become a serious system.
What it lacks is not imagination.

It lacks:

- a smaller kernel
- a clearer control plane
- stronger operational discipline
- faster infrastructure for the hottest loops

The highest-leverage move is:

make the core smaller, make ops singular, keep Python for intelligence, and use Rust only where the machine is actually doing heavy repetitive work.
