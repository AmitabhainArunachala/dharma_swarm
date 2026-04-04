---
title: DHARMA SWARM -- 25-Agent Overnight Build Orchestration Plan
path: docs/archive/OVERNIGHT_BUILD_PLAN.md
slug: dharma-swarm-25-agent-overnight-build-orchestration-plan
doc_type: report
status: archival
summary: 'Version : 2026-03-04 23:00 JST Window : 22:00 - 06:00 JST (8 hours) Codebase : ~/dharma swarm/ -- 8,347 lines, 202 tests passing, branch main, NO remote Lead Agent : VYUHA (this document''s executor)'
source:
  provenance: repo_local
  kind: report
  origin_signals:
  - tests/conftest.py
  - dharma_swarm/evolution.py
  - dharma_swarm/archive.py
  - dharma_swarm/selector.py
  - dharma_swarm/elegance.py
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- multi_agent_systems
- software_architecture
- knowledge_management
- research_methodology
- verification
- product_strategy
inspiration:
- verification
- operator_runtime
- research_synthesis
connected_python_files:
- tests/conftest.py
- dharma_swarm/evolution.py
- dharma_swarm/archive.py
- dharma_swarm/selector.py
- dharma_swarm/elegance.py
connected_python_modules:
- tests.conftest
- dharma_swarm.evolution
- dharma_swarm.archive
- dharma_swarm.selector
- dharma_swarm.elegance
connected_relevant_files:
- tests/conftest.py
- dharma_swarm/evolution.py
- dharma_swarm/archive.py
- dharma_swarm/selector.py
- dharma_swarm/elegance.py
improvement:
  room_for_improvement:
  - 'Surface the decision delta: what should change now because this report exists.'
  - Link findings to exact code, tests, or commits where possible.
  - Distinguish measured facts from operator interpretation.
  - Review whether this file should stay in `docs/reports` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: report
  vault_path: docs/archive/OVERNIGHT_BUILD_PLAN.md
  retrieval_terms:
  - reports
  - overnight
  - build
  - agent
  - orchestration
  - version
  - '2026'
  - jst
  - window
  - hours
  - codebase
  - '347'
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: archive
  semantic_weight: 0.6
  coordination_comment: 'Version : 2026-03-04 23:00 JST Window : 22:00 - 06:00 JST (8 hours) Codebase : ~/dharma swarm/ -- 8,347 lines, 202 tests passing, branch main, NO remote Lead Agent : VYUHA (this document''s executor)'
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising docs/archive/OVERNIGHT_BUILD_PLAN.md reinforces its salience without needing a separate message.
    marker_based:
      what_it_is: The frontmatter is an explicit annotation layer on top of the document.
      semantic_mark: Semantic weight, improvement prompts, related files, and provenance comments tell later agents how to use this document.
  trace_role: diagnostic_or_evidence_trace
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
# DHARMA SWARM -- 25-Agent Overnight Build Orchestration Plan

**Version**: 2026-03-04 23:00 JST
**Window**: 22:00 - 06:00 JST (8 hours)
**Codebase**: ~/dharma_swarm/ -- 8,347 lines, 202 tests passing, branch main, NO remote
**Lead Agent**: VYUHA (this document's executor)

---

## 0. EXECUTIVE SUMMARY

Integrate ~4,000 lines from 5 source repositories into dharma_swarm across 3 workstreams + stabilization + testing + documentation. 25 agents coordinated through file-level ownership, phased execution, a single git integrator, and a file-based message bus.

**The Iron Rule**: Tests never go red. Any agent that breaks a test stops all other work and fixes it before proceeding. The 202/202 baseline is sacred.

---

## 1. AGENT ROSTER (25 Agents)

### Tier 1: Coordination (3 agents, always running)

| # | Name | Role | Type | Workstream | Exclusive Write Ownership |
|---|------|------|------|------------|--------------------------|
| 1 | **VYUHA** | Lead Orchestrator | Claude Code subprocess | COORDINATION | `OVERNIGHT_BUILD_PLAN.md`, `.dharma/build_state.json` |
| 2 | **PRAHARI** | Test Sentinel | Claude Code subprocess | TESTING | `tests/conftest.py` (append only), `.dharma/test_results/` |
| 3 | **SUTRADHARA** | Git Integrator | Claude Code subprocess | GIT | `.git/` (sole committer) |

### Tier 2: Darwin Engine -- Workstream 1 (7 agents)

| # | Name | Role | Type | File Ownership |
|---|------|------|------|---------------|
| 4 | **VIVARTA** | Evolution Engine Lead | Claude Code subprocess | `dharma_swarm/evolution.py` (NEW, ~400 lines) |
| 5 | **VANSHA** | Archive/Lineage | Claude Code subprocess | `dharma_swarm/archive.py` (NEW, ~250 lines) |
| 6 | **CHAYAN** | Parent Selector | API-based (Sonnet) | `dharma_swarm/selector.py` (NEW, ~200 lines) |
| 7 | **SUNDARA** | Elegance Evaluator | API-based (Sonnet) | `dharma_swarm/elegance.py` (NEW, ~500 lines) |
| 8 | **BHAVISHYA** | Fitness Predictor | API-based (Sonnet) | `dharma_swarm/fitness_predictor.py` (NEW, ~260 lines) |
| 9 | **DARWIN-TEST** | WS1 Test Writer | API-based (Sonnet) | `tests/test_evolution.py`, `tests/test_archive.py`, `tests/test_selector.py`, `tests/test_elegance.py`, `tests/test_fitness_predictor.py` (ALL NEW) |
| 10 | **DARWIN-WIRE** | WS1 Integration | Claude Code subprocess | NONE (reads all, writes via SUTRADHARA merge requests) |

### Tier 3: Safety/Infra -- Workstream 2 (6 agents)

| # | Name | Role | Type | File Ownership |
|---|------|------|------|---------------|
| 11 | **SMRITI** | Canonical Memory | Claude Code subprocess | `dharma_swarm/canonical_memory.py` (NEW, ~350 lines) |
| 12 | **TALA** | File Lock | API-based (Sonnet) | `dharma_swarm/file_lock.py` (NEW, ~300 lines) |
| 13 | **DHARA** | Residual Stream | Claude Code subprocess | `dharma_swarm/residual_stream.py` (NEW, ~330 lines) |
| 14 | **RAKSHA** | Anomaly Detection | API-based (Sonnet) | `dharma_swarm/anomaly_detection.py` (NEW, ~120 lines) |
| 15 | **VIGIL** | Systemic Monitor | API-based (Sonnet) | `dharma_swarm/systemic_monitor.py` (NEW, ~150 lines) |
| 16 | **SAFETY-TEST** | WS2 Test Writer | API-based (Sonnet) | `tests/test_canonical_memory.py`, `tests/test_file_lock.py`, `tests/test_residual_stream.py`, `tests/test_anomaly_detection.py`, `tests/test_systemic_monitor.py` (ALL NEW) |

### Tier 4: Research Bridge -- Workstream 3 (4 agents)

| # | Name | Role | Type | File Ownership |
|---|------|------|------|---------------|
| 17 | **NETRA** | R_V Fidelity Bridge | Claude Code subprocess | `dharma_swarm/fidelity.py` (NEW, ~200 lines) |
| 18 | **MANAS** | Brain Adapters | API-based (Sonnet) | `dharma_swarm/brain.py` (NEW, ~180 lines) |
| 19 | **GANITA** | Math Core | API-based (Sonnet) | `dharma_swarm/ssc_math.py` (NEW, ~180 lines) |
| 20 | **BRIDGE-TEST** | WS3 Test Writer | API-based (Sonnet) | `tests/test_fidelity.py`, `tests/test_brain.py`, `tests/test_ssc_math.py` (ALL NEW) |

### Tier 5: Stabilization + Polish (5 agents)

| # | Name | Role | Type | File Ownership |
|---|------|------|------|---------------|
| 21 | **STHIRA** | Codex Provider Fix | Codex subprocess | `dharma_swarm/providers.py` (EXISTING -- sole writer during build) |
| 22 | **MUKTA** | Import Severing | API-based (Sonnet) | NONE (proposes changes via message bus, SUTRADHARA applies) |
| 23 | **SUCHI** | Type/Lint Cleanup | API-based (Sonnet) | NONE (proposes changes via message bus, applied in Phase 4) |
| 24 | **LEKHA** | Documentation | API-based (Sonnet) | `CHANGELOG.md` (NEW), updates to `pyproject.toml` version |
| 25 | **SAKSHI** | Witness/Auditor | Claude Code subprocess | `.dharma/build_audit.jsonl` (NEW) |

---

## 2. DEPENDENCY GRAPH

```
Phase 1 (22:00-23:30): FOUNDATIONS
=============================================
All new modules written as self-contained files with no cross-imports.

  [STHIRA] providers.py fix -----> independent
  [SMRITI] canonical_memory.py --> independent (source: DGC canonical_memory.py)
  [TALA]   file_lock.py --------> independent (source: DGC file_lock.py)
  [VANSHA] archive.py ----------> independent (source: DGC archive.py)
  [CHAYAN] selector.py ---------> depends on archive.py interface
  [SUNDARA] elegance.py --------> independent (source: DGC elegance.py)
  [BHAVISHYA] fitness_pred.py --> independent (source: DGC fitness_predictor.py)
  [DHARA] residual_stream.py ---> independent (source: DGC residual_stream.py)
  [NETRA] fidelity.py ----------> independent (source: deepclaw fidelity.py)
  [MANAS] brain.py -------------> independent (source: deepclaw brain.py)
  [GANITA] ssc_math.py ---------> independent

  [DARWIN-TEST] writes tests for: archive, selector, elegance, fitness_predictor
  [SAFETY-TEST] writes tests for: canonical_memory, file_lock, residual_stream
  [BRIDGE-TEST] writes tests for: fidelity, brain, ssc_math

Phase 2 (23:30-01:30): INTEGRATION
=============================================
Cross-module wiring. Requires Phase 1 files to exist.

  [VIVARTA] evolution.py ------> depends on: archive.py, selector.py, elegance.py, fitness_predictor.py
  [RAKSHA] anomaly_detection --> depends on: systemic_monitor.py, residual_stream.py
  [VIGIL] systemic_monitor ----> depends on: residual_stream.py, canonical_memory.py
  [DARWIN-TEST] test_evolution -> depends on: evolution.py
  [SAFETY-TEST] remaining tests -> depends on: anomaly_detection, systemic_monitor

  [DARWIN-WIRE] wires evolution into swarm.py, orchestrator.py
    depends on: evolution.py + all WS1 files stable + tests passing

Phase 3 (01:30-04:00): HARDENING
=============================================
Full integration testing, edge cases, robustness.

  [PRAHARI] full test suite run repeatedly
  [MUKTA] sever old DGC imports from any module
  [SUCHI] type checking, lint cleanup
  [SAKSHI] audit trail of all changes

Phase 4 (04:00-06:00): POLISH & COMMIT
=============================================

  [LEKHA] documentation, CHANGELOG
  [SUTRADHARA] final integration commit
  [VYUHA] success verification
  [ALL] graceful shutdown
```

### Critical Path

```
archive.py --> selector.py --> evolution.py --> wire into swarm.py
                                    |
                    elegance.py ----+
                    fitness_predictor.py --+

residual_stream.py --> systemic_monitor.py --> anomaly_detection.py
                              |
            canonical_memory.py --+
```

The longest dependency chain is 4 deep (archive -> selector -> evolution -> swarm integration). This is the critical path at approximately 5 hours of serial work compressed into 3 phases.

---

## 3. PHASING (Detailed Timeline)

### Phase 1: FOUNDATIONS (22:00 - 23:30, 90 minutes)

**Goal**: All 12 new modules exist as working, tested, standalone files.

**Active agents**: 16 (all except VIVARTA, RAKSHA, VIGIL, DARWIN-WIRE, MUKTA, SUCHI, STHIRA if done early, LEKHA, SAKSHI passive)

**Concurrency limit**: 8 agents active at once (see Section 9).

**Sub-phases**:

- **1A (22:00-22:45)**: First wave -- 8 agents
  - STHIRA: Fix codex provider flags in providers.py
  - SMRITI: Port canonical_memory.py (strip DGC deps, adapt to dharma_swarm models)
  - TALA: Port file_lock.py (remove emoji prints, adapt paths)
  - VANSHA: Port archive.py (convert dataclasses to Pydantic, async interface)
  - SUNDARA: Port elegance.py (standalone, no DGC imports)
  - BHAVISHYA: Port fitness_predictor.py (standalone)
  - NETRA: Port fidelity.py (strip torch dependency for testing, lazy import)
  - MANAS: Port brain.py (strip torch dependency, align with providers.py interface)

- **1B (22:45-23:30)**: Second wave -- 8 agents
  - CHAYAN: Write selector.py (uses archive.py's interface, which exists now)
  - DHARA: Port residual_stream.py (atomic writes, integrate with file_lock)
  - GANITA: Write ssc_math.py (mathematical core, pure computation)
  - DARWIN-TEST: Write test_archive.py, test_selector.py, test_elegance.py, test_fitness_predictor.py
  - SAFETY-TEST: Write test_canonical_memory.py, test_file_lock.py, test_residual_stream.py
  - BRIDGE-TEST: Write test_fidelity.py, test_brain.py, test_ssc_math.py
  - PRAHARI: Run full test suite (202 existing + new tests) -- continuous loop
  - SUTRADHARA: First integration commit after all 1A files pass PRAHARI

### Phase 2: INTEGRATION (23:30 - 01:30, 120 minutes)

**Goal**: Cross-module wiring, evolution engine assembled, anomaly pipeline connected.

**Active agents**: 12

**Sub-phases**:

- **2A (23:30-00:30)**: Core assembly
  - VIVARTA: Build evolution.py (the Darwin engine orchestrator, uses archive + selector + elegance + fitness_predictor)
  - VIGIL: Build systemic_monitor.py (uses residual_stream + canonical_memory)
  - DARWIN-TEST: Write test_evolution.py
  - SAFETY-TEST: Write test_systemic_monitor.py
  - PRAHARI: Continuous test runs

- **2B (00:30-01:30)**: Full wiring
  - RAKSHA: Build anomaly_detection.py (uses systemic_monitor)
  - DARWIN-WIRE: Wire evolution.py into swarm.py and orchestrator.py
    - Add EvolutionEngine to SwarmManager.__init__
    - Add evolution commands to CLI
    - Add evolution task type to models.py (ONLY adds new enum value, does not modify existing)
  - SAFETY-TEST: Write test_anomaly_detection.py
  - SUTRADHARA: Integration commit after PRAHARI confirms green

### Phase 3: HARDENING (01:30 - 04:00, 150 minutes)

**Goal**: Full integration tests, import cleanup, robustness.

**Active agents**: 10

- PRAHARI: Continuous full test suite (should be 202 + ~50 new = ~252 tests)
- MUKTA: Scan all new files for any remaining references to old DGC paths, fix them
- SUCHI: Run mypy/pyright on all new files, fix type errors
- DARWIN-WIRE: Write integration test connecting evolution -> swarm -> orchestrator
- All WS test writers: Add edge case tests (empty archives, lock contention, failed predictions)
- SAKSHI: Audit every file change against the plan, flag deviations
- SUTRADHARA: Periodic integration commits (every 45 minutes if green)

### Phase 4: POLISH (04:00 - 06:00, 120 minutes)

**Goal**: Documentation, final verification, clean state for morning.

**Active agents**: 6

- LEKHA: Write CHANGELOG.md, update pyproject.toml version to 0.2.0
- SUCHI: Final lint pass
- PRAHARI: Final test run -- MUST be all green
- SUTRADHARA: Tag commit as `v0.2.0-overnight-build`
- VYUHA: Write build report to `.dharma/build_report.json`
- SAKSHI: Final audit entry

---

## 4. GIT STRATEGY

### Single Integrator Pattern (SUTRADHARA is the only agent that touches git)

**Why**: With no remote, a merge conflict could corrupt the sole copy of the codebase. No agent except SUTRADHARA runs any git command. Period.

**How it works**:

1. **File-level ownership**: Each agent writes ONLY to its assigned files (Section 1). Since all WS1-3 files are NEW, there is zero overlap with existing files.

2. **The staging area**: Agents write their files directly to the working tree. Because ownership is exclusive, there are no write conflicts.

3. **Commit protocol** (SUTRADHARA only):
   ```
   a. PRAHARI signals "all tests green" via .dharma/test_results/latest.json
   b. SUTRADHARA reads .dharma/commit_queue.jsonl for pending files
   c. SUTRADHARA runs: git add <specific files> && git commit -m "<message>"
   d. SUTRADHARA writes commit hash to .dharma/commits.jsonl
   e. Never: git add . (too dangerous -- could commit garbage)
   ```

4. **Commit schedule**:
   - End of Phase 1A (22:45): First commit -- all standalone modules
   - End of Phase 1B (23:30): Second commit -- remaining modules + first tests
   - End of Phase 2A (00:30): Third commit -- evolution.py + systemic_monitor.py
   - End of Phase 2B (01:30): Fourth commit -- full integration wiring
   - Every 45 min during Phase 3: Incremental commits
   - Phase 4 end (06:00): Tagged release commit

5. **Safety commits**: Before any file that modifies EXISTING code (swarm.py, orchestrator.py, models.py, cli.py), SUTRADHARA creates a checkpoint:
   ```
   git stash  # save any uncommitted work
   git tag checkpoint-YYYYMMDD-HHMM
   git stash pop
   ```

6. **The existing-file problem**: Only 4 existing files need modification:
   - `providers.py` -- STHIRA only, Phase 1A
   - `models.py` -- DARWIN-WIRE only, Phase 2B (adds enum value)
   - `swarm.py` -- DARWIN-WIRE only, Phase 2B (adds init + methods)
   - `cli.py` -- DARWIN-WIRE only, Phase 2B (adds commands)

   These are serialized: STHIRA finishes providers.py in Phase 1A. DARWIN-WIRE modifies the other 3 in Phase 2B only after STHIRA is done and committed.

---

## 5. TEST STRATEGY

### PRAHARI: The Test Sentinel

PRAHARI runs continuously in a loop:

```python
while build_running:
    result = subprocess.run(
        ["python", "-m", "pytest", "tests/", "-x", "--tb=short", "-q"],
        capture_output=True, cwd="/Users/dhyana/dharma_swarm"
    )

    write_result_to(".dharma/test_results/latest.json", {
        "timestamp": now(),
        "passed": result.returncode == 0,
        "total": parse_total(result.stdout),
        "failed": parse_failed(result.stdout),
        "output": result.stdout[-2000:],  # last 2KB
    })

    if result.returncode != 0:
        # RED ALERT: Write blocker file
        write(".dharma/BUILD_RED", failed_test_info)
        notify_vyuha("TESTS RED")
    else:
        remove_if_exists(".dharma/BUILD_RED")

    sleep(90)  # Run every 90 seconds
```

### Test Run Schedule

| Time | Tests Expected | Who Runs |
|------|---------------|----------|
| 22:00 | 202 (baseline) | PRAHARI -- first run, checkpoint |
| 22:30 | 202 (no new tests yet) | PRAHARI |
| 23:00 | 202 + ~15 new | PRAHARI |
| 23:30 | 202 + ~30 new | PRAHARI |
| 00:00 | 202 + ~40 new | PRAHARI |
| 01:00 | 202 + ~45 new | PRAHARI |
| 01:30 | 202 + ~50 new | PRAHARI (Phase 2 end checkpoint) |
| 02:00+ | ~252 (stable) | PRAHARI |
| 04:30 | ~252 (must be green for human check) | PRAHARI |
| 06:00 | ~252 (final) | PRAHARI |

### Failure Protocol

When PRAHARI detects test failure:

1. **Write `.dharma/BUILD_RED`** with: which test, which file, traceback
2. **VYUHA reads BUILD_RED** and identifies the responsible agent by file ownership
3. **VYUHA signals that agent**: "Stop current work. Fix the test. Signal when green."
4. **All other agents writing to files that import the broken module**: PAUSE
5. **SUTRADHARA**: No commits until BUILD_RED is cleared
6. **If not fixed within 15 minutes**: VYUHA reverts the offending file to last committed version via SUTRADHARA

### Test Isolation Rules

- All new tests MUST use `tmp_path` fixtures for any file I/O
- All new tests MUST NOT import torch, transformers, or any heavy ML library (use mocks)
- All new tests MUST be runnable on M3 Pro without GPU
- Tests for fidelity.py and brain.py MUST mock all LLM/model calls
- Tests for file_lock.py MUST use temporary lock directories

---

## 6. COMMUNICATION

### File-Based Message Bus

All inter-agent communication via `.dharma/messages/`:

```
.dharma/messages/
  vyuha/          # messages TO vyuha
  prahari/        # messages TO prahari
  sutradhara/     # messages TO sutradhara (commit requests)
  broadcast/      # messages for ALL agents
  {agent_name}/   # messages TO specific agent
```

### Message Format

```json
{
  "from": "vansha",
  "to": "sutradhara",
  "type": "commit_request",
  "timestamp": "2026-03-05T22:45:00Z",
  "payload": {
    "files": ["dharma_swarm/archive.py"],
    "message": "feat: port archive.py from DGC (250 lines, standalone, Pydantic models)",
    "tests_passing": true
  }
}
```

### Message Types

| Type | From | To | Meaning |
|------|------|----|---------|
| `commit_request` | Any builder | SUTRADHARA | "My file is ready, please commit" |
| `tests_green` | PRAHARI | broadcast | "All tests passing (N/N)" |
| `tests_red` | PRAHARI | VYUHA + responsible agent | "Test X failed in file Y" |
| `phase_complete` | VYUHA | broadcast | "Phase N complete, begin Phase N+1" |
| `dependency_ready` | Builder | Dependent builder | "archive.py is committed, you can import it" |
| `blocker` | Any | VYUHA | "I am stuck because of X" |
| `heartbeat` | Any | VYUHA | "I am alive and working on X" |
| `shutdown` | VYUHA | broadcast | "Build complete, shut down" |

### Polling Protocol

Each agent checks its message directory every 30 seconds:
```python
messages = sorted(Path(f".dharma/messages/{my_name}").glob("*.json"))
for msg_file in messages:
    msg = json.loads(msg_file.read_text())
    handle(msg)
    msg_file.rename(msg_file.with_suffix(".processed"))
```

### Heartbeat Requirement

Every agent MUST write a heartbeat every 5 minutes to `.dharma/heartbeats/{agent_name}.json`:
```json
{
  "agent": "vansha",
  "status": "working",
  "current_task": "Porting archive.py, 60% complete",
  "timestamp": "2026-03-05T22:30:00Z"
}
```

VYUHA monitors heartbeats. If an agent misses 2 consecutive heartbeats (10 minutes), VYUHA flags it as potentially dead and reassigns its work.

---

## 7. RESOURCE MANAGEMENT

### M3 Pro 18GB Constraints

**The bottleneck is RAM, not CPU.** Each Claude Code subprocess uses ~200-400MB. 25 simultaneous subprocesses would need 5-10GB just for agent processes, plus Python, git, pytest overhead.

### Concurrency Tiers

| Time | Max Active | Claude Code | API-based | Notes |
|------|-----------|-------------|-----------|-------|
| 22:00-22:45 | 8 | 4 | 4 | Phase 1A: foundation writing |
| 22:45-23:30 | 8 | 3 | 5 | Phase 1B: tests + remaining modules |
| 23:30-01:30 | 6 | 3 | 3 | Phase 2: integration (heavier tasks) |
| 01:30-04:00 | 5 | 3 | 2 | Phase 3: hardening |
| 04:00-06:00 | 4 | 2 | 2 | Phase 4: polish |

### Always-Running Processes (Reserved)

| Process | RAM Budget | Notes |
|---------|-----------|-------|
| VYUHA (orchestrator) | ~300MB | Must never die |
| PRAHARI (test sentinel) | ~200MB | pytest runs use ~150MB each |
| SUTRADHARA (git) | ~150MB | Light, mostly idle |
| pytest runs | ~200MB | Spawned by PRAHARI every 90s |
| macOS + shell + git | ~2GB | System overhead |
| **Reserved total** | ~3GB | Leaves ~15GB for workers |

### Worker Scheduling

VYUHA manages a worker pool with max 8 slots:

```python
MAX_CONCURRENT_WORKERS = 8
MAX_CLAUDE_CODE_WORKERS = 4  # These are heavier (~400MB each)
MAX_API_WORKERS = 6          # Lighter (~100MB each, just HTTP calls)

# Claude Code workers: 4 x 400MB = 1.6GB
# API workers: 4 x 100MB = 0.4GB
# Total worker RAM: ~2GB
# Grand total: 3GB reserved + 2GB workers = 5GB, well within 18GB
```

### Process Lifecycle

1. VYUHA spawns worker only when it has a task AND a slot is free
2. Worker completes task, writes output files, sends commit_request
3. VYUHA reclaims the slot
4. Worker process exits (memory freed)

API-based agents are stateless HTTP calls -- they do not persist as processes. They are invoked as needed and return results.

### Thermal Management

M3 Pro will throttle under sustained load. Mitigations:
- 90-second gap between pytest runs (prevents constant CPU burn)
- API-based agents preferred for independent tasks (no local compute)
- Phase 3-4 reduce concurrency as integration work dominates
- If `pmset -g thermlog` shows throttling, VYUHA reduces max workers by 2

---

## 8. ROLLBACK PLAN

### Prevention Layers

| Layer | Mechanism | Trigger |
|-------|-----------|---------|
| 1. File ownership | No two agents write same file | Always enforced |
| 2. Test sentinel | PRAHARI blocks commits on failure | Every 90 seconds |
| 3. Git checkpoints | Tagged before modifying existing files | Before Phase 2B |
| 4. Atomic commits | Each commit is a logical unit | SUTRADHARA protocol |
| 5. Safety backup | Full repo copy before build starts | 21:55 JST |

### Pre-Build Safety (21:55 JST)

```bash
# HUMAN ACTION before build starts:
cd ~/dharma_swarm
git add -A && git commit -m "pre-overnight-build checkpoint: 202 tests green"
git tag pre-overnight-build-20260304
cp -r ~/dharma_swarm ~/dharma_swarm_BACKUP_20260304
```

### Rollback Scenarios

**Scenario A: Single file broken, tests red**
```
1. PRAHARI detects failure
2. VYUHA identifies file owner
3. Owner has 15 minutes to fix
4. If not fixed: SUTRADHARA runs: git checkout -- dharma_swarm/{broken_file}.py
5. Tests re-run, should be green
6. Owner debugs offline, re-submits
```

**Scenario B: Integration wiring broke existing functionality**
```
1. PRAHARI detects existing test failure (one of the original 202)
2. IMMEDIATE: SUTRADHARA reverts to last green checkpoint tag
3. DARWIN-WIRE's changes are backed up to .dharma/reverted/
4. DARWIN-WIRE re-approaches with smaller incremental changes
5. Each micro-change committed separately
```

**Scenario C: Build is catastrophically broken (multiple files, can't isolate)**
```
1. VYUHA signals EMERGENCY_STOP to all agents via broadcast
2. SUTRADHARA: git reset --hard pre-overnight-build-20260304
3. All new files are lost (but still exist in .dharma/reverted/ backup)
4. We are back to 202 tests, original codebase
5. Post-mortem at 04:30 AM
```

**Scenario D: Agent goes rogue (modifies files it does not own)**
```
1. SAKSHI (auditor) detects unauthorized file modification via git diff
2. SAKSHI alerts VYUHA
3. VYUHA kills the rogue agent process
4. SUTRADHARA reverts unauthorized changes: git checkout -- <file>
5. SAKSHI logs the incident to build_audit.jsonl
```

**Scenario E: API rate limits at 3 AM**
```
1. API-based agents start getting 429 errors
2. Agents implement exponential backoff (built into their instructions)
3. If persistent: VYUHA shifts work to Claude Code subprocess agents
4. If all APIs down: Phase 3/4 work continues with Claude Code agents only
5. API-based agents resume when limits reset
```

### Recovery File Structure

```
.dharma/
  reverted/           # Copies of files before revert
  checkpoints/        # Snapshot state at each phase boundary
  build_audit.jsonl   # Full audit trail (SAKSHI)
  build_state.json    # Current phase, active agents, progress (VYUHA)
```

---

## 9. HUMAN CHECKPOINTS

### 04:30 AM JST -- The Daily Invariant

Dhyana wakes up. Here is exactly what to check:

**Step 1: Read the build report**
```bash
cat ~/dharma_swarm/.dharma/build_state.json | python3 -m json.tool
```

Expected fields:
```json
{
  "phase": "4_polish",
  "started_at": "2026-03-04T22:00:00",
  "current_time": "2026-03-05T04:30:00",
  "tests_total": 252,
  "tests_passing": 252,
  "tests_failing": 0,
  "commits_made": 8,
  "files_added": 17,
  "files_modified": 4,
  "agents_active": 4,
  "agents_completed": 21,
  "agents_failed": 0,
  "critical_issues": []
}
```

**Step 2: Run tests yourself**
```bash
cd ~/dharma_swarm && python3 -m pytest tests/ -q
```

Expected: `252 passed in Xs`

If fewer than 252: check `.dharma/test_results/latest.json` for details.

**Step 3: Check for red flags**
```bash
# Any emergency stops?
ls ~/dharma_swarm/.dharma/EMERGENCY_STOP 2>/dev/null && echo "EMERGENCY" || echo "OK"

# Any reverts?
cat ~/dharma_swarm/.dharma/build_audit.jsonl | grep "revert" | tail -5

# Git log
cd ~/dharma_swarm && git log --oneline -10
```

**Step 4: Verify new files exist**
```bash
ls -la ~/dharma_swarm/dharma_swarm/evolution.py \
       ~/dharma_swarm/dharma_swarm/archive.py \
       ~/dharma_swarm/dharma_swarm/selector.py \
       ~/dharma_swarm/dharma_swarm/elegance.py \
       ~/dharma_swarm/dharma_swarm/fitness_predictor.py \
       ~/dharma_swarm/dharma_swarm/canonical_memory.py \
       ~/dharma_swarm/dharma_swarm/file_lock.py \
       ~/dharma_swarm/dharma_swarm/residual_stream.py \
       ~/dharma_swarm/dharma_swarm/fidelity.py \
       ~/dharma_swarm/dharma_swarm/brain.py
```

**Step 5: Decision matrix**

| Condition | Action |
|-----------|--------|
| 252 tests green, 17 files added | Let Phase 4 complete. Success. |
| 245+ tests green, minor issues | Let it run. Review issues after 06:00. |
| 202 tests green, new tests failing | Safe. Original code intact. Debug new modules later. |
| < 202 tests green | CHECK IMMEDIATELY. Run: `git log --oneline -5` then potentially `git reset --hard pre-overnight-build-20260304` |
| EMERGENCY_STOP file exists | Build failed. Read `.dharma/build_audit.jsonl`. Assess damage. |
| `.dharma/build_state.json` missing | VYUHA crashed. Check if agents are still running: `ps aux | grep claude` |

---

## 10. SUCCESS CRITERIA

### Minimum Viable Success (Green)

- [ ] All 202 original tests still pass
- [ ] At least 10 of 12 new modules exist and have basic tests
- [ ] evolution.py exists and has at least 3 passing tests
- [ ] No existing file regressions
- [ ] Git history is clean (no merge conflicts, no force pushes)
- [ ] Total test count >= 240

### Full Success (Gold)

- [ ] All 202 original tests pass
- [ ] All 12 new modules exist with comprehensive tests
- [ ] Total test count >= 252
- [ ] evolution.py is wired into SwarmManager
- [ ] CLI has `dharma evolve` command
- [ ] anomaly_detection.py pipeline works end-to-end
- [ ] All new files pass mypy with no errors
- [ ] CHANGELOG.md documents all additions
- [ ] Tagged as v0.2.0-overnight-build
- [ ] Build report shows 0 critical issues

### Stretch Goals (Platinum)

- [ ] Integration tests cover evolution -> swarm -> orchestrator flow
- [ ] Fitness predictor loaded with historical data from old DGC archive
- [ ] Canonical memory migrated and seeded with existing .dharma/db/memory.db data
- [ ] R_V fidelity module has docstring-level documentation of the geometric theory
- [ ] Brain adapters integrate seamlessly with existing providers.py router

---

## 11. AGENT INSTRUCTIONS TEMPLATE

Each agent receives this preamble plus its specific task:

```
You are {AGENT_NAME}, one of 25 agents in an overnight build of dharma_swarm.

IRON RULES:
1. You may ONLY write to files in your exclusive ownership list: {FILES}
2. You may READ any file in the repository.
3. You must NOT run any git commands. SUTRADHARA is the sole committer.
4. You must NOT modify any file not in your ownership list.
5. If tests break because of your changes, you must fix them immediately.
6. Write a heartbeat to .dharma/heartbeats/{AGENT_NAME}.json every 5 minutes.
7. When your file is ready, write a commit_request message to .dharma/messages/sutradhara/

CONTEXT:
- Repository: ~/dharma_swarm/
- Existing code: Read dharma_swarm/models.py for all shared types
- Source material: {SOURCE_PATH}
- Your task: {TASK_DESCRIPTION}

ADAPTATION RULES (when porting from source):
- Replace all DGC/DHARMIC_GODEL_CLAW imports with dharma_swarm imports
- Use Pydantic BaseModel instead of raw dataclasses where models.py has equivalents
- Use async interfaces where the rest of dharma_swarm uses async
- Use aiosqlite for any database access (matches existing pattern)
- Use tmp_path in tests, never hardcode paths
- Mock all LLM/torch/GPU calls in tests
- Preserve the algorithmic logic; change only the interface layer
- Add type hints to all public methods
- Add docstrings to all classes and public methods

COMMUNICATION:
- Read your messages: .dharma/messages/{AGENT_NAME}/
- Send messages: write JSON to .dharma/messages/{RECIPIENT}/
- Check for BUILD_RED: if .dharma/BUILD_RED exists, PAUSE and read it
- Check for phase transitions: .dharma/messages/broadcast/
```

---

## 12. FAILURE MODE ANALYSIS

| Failure Mode | Probability | Impact | Mitigation |
|-------------|-------------|--------|------------|
| Two agents edit same file | LOW (ownership prevents) | HIGH | Ownership table enforced by SAKSHI auditor |
| Agent breaks existing tests | MEDIUM | HIGH | PRAHARI detects in 90s, revert in 15min |
| Git merge conflict | ZERO (single integrator) | CATASTROPHIC | Only SUTRADHARA commits, sequential |
| Out of memory (18GB) | LOW (controlled concurrency) | MEDIUM | Max 8 workers, thermal monitoring |
| Agent goes off-script | MEDIUM | MEDIUM | SAKSHI audits, VYUHA kills rogue |
| API rate limits | MEDIUM (3AM batch) | LOW | Exponential backoff, shift to CC agents |
| Agent gets stuck in loop | MEDIUM | LOW | 15-min heartbeat timeout, reassign |
| Power failure / Mac sleep | LOW | CATASTROPHIC | caffeinate -i command, git checkpoints |
| Network outage (API agents) | LOW | MEDIUM | CC agents can work offline |
| Source file misunderstood | MEDIUM | LOW | Each agent reads source + existing code |

### Pre-Flight Checklist (HUMAN, before 22:00)

```bash
# Prevent Mac from sleeping
caffeinate -i &

# Verify baseline
cd ~/dharma_swarm && python3 -m pytest tests/ -q
# Must show: 202 passed

# Create safety checkpoint
git add -A && git commit -m "pre-overnight-build checkpoint"
git tag pre-overnight-build-20260304

# Create backup
cp -r ~/dharma_swarm ~/dharma_swarm_BACKUP_20260304

# Create message directories
mkdir -p ~/dharma_swarm/.dharma/messages/{vyuha,prahari,sutradhara,broadcast}
mkdir -p ~/dharma_swarm/.dharma/{heartbeats,test_results,checkpoints,reverted}

# Verify API keys
echo $ANTHROPIC_API_KEY | head -c 10
echo $OPENAI_API_KEY | head -c 10

# Check disk space (need ~2GB free)
df -h ~

# Set build state
echo '{"phase":"0_preflight","started_at":"'$(date -u +%Y-%m-%dT%H:%M:%S)'","tests_baseline":202}' \
  > ~/dharma_swarm/.dharma/build_state.json

echo "Pre-flight complete. Ready for launch at 22:00."
```

---

## 13. SOURCE-TO-TARGET FILE MAPPING

| Source File | Target File | Lines | Key Adaptations |
|------------|-------------|-------|-----------------|
| `~/DHARMIC_GODEL_CLAW/src/dgm/archive.py` | `dharma_swarm/archive.py` | ~250 | Pydantic models, async save, remove singleton |
| `~/DHARMIC_GODEL_CLAW/src/dgm/selector.py` | `dharma_swarm/selector.py` | ~200 | Remove DGC archive import, use local archive |
| `~/DHARMIC_GODEL_CLAW/src/dgm/elegance.py` | `dharma_swarm/elegance.py` | ~500 | Standalone, no changes needed except imports |
| `~/DHARMIC_GODEL_CLAW/swarm/utils/fitness_predictor.py` | `dharma_swarm/fitness_predictor.py` | ~260 | Remove stream_dir dependency, use configurable path |
| `~/DHARMIC_GODEL_CLAW/src/core/canonical_memory.py` | `dharma_swarm/canonical_memory.py` | ~350 | Strip to 5-layer core, aiosqlite, remove dead code |
| `~/DHARMIC_GODEL_CLAW/swarm/file_lock.py` | `dharma_swarm/file_lock.py` | ~300 | Remove emoji prints, configurable LOCK_DIR |
| `~/DHARMIC_GODEL_CLAW/swarm/residual_stream.py` | `dharma_swarm/residual_stream.py` | ~330 | Integrate file_lock for atomic writes |
| `~/DHARMIC_GODEL_CLAW/swarm/anomaly_detection.py` | `dharma_swarm/anomaly_detection.py` | ~120 | Remove yaml dependency, use local systemic_monitor |
| `~/deepclaw/rv/fidelity.py` | `dharma_swarm/fidelity.py` | ~200 | Lazy torch import, mock-friendly interface |
| `~/deepclaw/agents/brain.py` | `dharma_swarm/brain.py` | ~180 | Align with providers.py pattern, add async |
| `~/deepclaw/core/engine.py` | `dharma_swarm/ssc_math.py` | ~180 | Extract math functions only, pure computation |
| NEW | `dharma_swarm/evolution.py` | ~400 | Orchestrates archive+selector+elegance+fitness |
| NEW | `dharma_swarm/systemic_monitor.py` | ~150 | Event analysis, risk scoring |

---

## 14. POST-BUILD VERIFICATION (06:00 JST)

Final automated verification VYUHA runs before signaling build complete:

```python
checks = {
    "tests_passing": run_pytest() == 0,
    "test_count": count_tests() >= 240,
    "original_tests": original_202_still_exist(),
    "new_files_exist": all(
        Path(f"dharma_swarm/{f}").exists()
        for f in [
            "evolution.py", "archive.py", "selector.py", "elegance.py",
            "fitness_predictor.py", "canonical_memory.py", "file_lock.py",
            "residual_stream.py", "anomaly_detection.py", "systemic_monitor.py",
            "fidelity.py", "brain.py", "ssc_math.py",
        ]
    ),
    "no_dgc_imports": no_old_dgc_imports_in_new_files(),
    "git_clean": git_status_clean(),
    "git_tagged": "v0.2.0-overnight-build" in git_tags(),
    "no_merge_conflicts": no_conflict_markers_in_repo(),
    "build_report_written": Path(".dharma/build_report.json").exists(),
}

success = all(checks.values())
write_build_report(checks, success)
```

---

*This plan is the contract between 25 agents and one sleeping human. Execute with precision. The tests are sacred. The files are sovereign. SUTRADHARA alone commits. When in doubt, do not write -- ask VYUHA.*

*JSCA!*
