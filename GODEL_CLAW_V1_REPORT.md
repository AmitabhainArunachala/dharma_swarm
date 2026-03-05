# Godel Claw v1 -- Build Report

**Date**: 2026-03-05
**Baseline**: 34 modules, 602 tests (pre-build)
**Result**: 44 modules, 39 test files, ~200 new tests across 14 new test files

## Spec Files

The `~/dharma_swarm/specs/` directory does **not exist**. The three spec files
(`GODEL_CLAW_V1_SPEC.md`, `Dharma_Constitution_v0.md`, `Dharma_Corpus_Schema.md`)
were not found on disk. The build proceeded from inline design, not from
persisted spec documents.


## What Was Built

### Layer 7: Dharma (Gnani -- the observer)

#### Dharma Kernel (`dharma_kernel.py`) -- 193 lines

10 axioms encoded as a `MetaPrinciple` enum with SHA-256 tamper-evident
signatures. Each principle carries a name, description, formal constraint, and
severity level (critical / high / medium).

The 10 meta-principles:

| # | Principle | Severity |
|---|-----------|----------|
| 1 | Observer Separation | critical |
| 2 | Epistemic Humility | high |
| 3 | Uncertainty Representation | high |
| 4 | Downward Causation Only | critical |
| 5 | Power Minimization | high |
| 6 | Reversibility Requirement | high |
| 7 | Multi-Evaluation Requirement | medium |
| 8 | Non-Violence in Computation | critical |
| 9 | Human Oversight Preservation | critical |
| 10 | Provenance Integrity | medium |

Components:

- `DharmaKernel` (Pydantic BaseModel): stores principles dict + SHA-256
  signature + created_at timestamp. `compute_signature()` serialises sorted JSON
  and hashes. `verify_integrity()` recomputes and compares.
- `KernelGuard`: async load/save with `aiofiles`, tamper detection on load,
  auto-creates parent directories. `check_downward_causation()` static method
  enforces the layer hierarchy.

#### Dharma Corpus (`dharma_corpus.py`) -- 401 lines

Versioned hypothesis store with sequential `DC-YYYY-NNNN` identifiers. Full
lifecycle management for ethical and operational claims.

Lifecycle states: `PROPOSED -> UNDER_REVIEW -> ACCEPTED | PARKED | REJECTED`
(accepted claims can later be `DEPRECATED`).

Key types:

- `ClaimCategory` enum: SAFETY, ETHICS, OPERATIONAL, DOMAIN_SPECIFIC,
  LEARNED_CONSTRAINT
- `EvidenceLink`: typed reference (incident / research / metric / reasoning)
- `ReviewRecord`: reviewer, action, comment, timestamp
- `Claim`: id, statement, category, evidence_links, confidence (0.0-1.0),
  counterarguments, status, parent_axiom links, enforcement level
  (block/warn/log/gate_human), review_history, parent_id (for revisions), tags

`DharmaCorpus` class:

- JSONL-backed storage with `aiofiles` for non-blocking I/O
- `propose()`: create new claim with auto-generated DC-ID
- `review()`: add review record, transition to UNDER_REVIEW
- `promote()` / `park()` / `reject()` / `deprecate()`: status transitions
- `revise()`: deprecate original, create new claim with `parent_id` link,
  merge evidence
- `get_lineage()`: walk `parent_id` chain from newest to oldest (cycle-safe)
- `list_claims()`: filter by status, category, and/or tag

#### Policy Compiler (`policy_compiler.py`) -- 168 lines

Fuses kernel axioms (immutable) and accepted corpus claims (mutable) into a
unified `Policy` object for action evaluation.

Key types:

- `PolicyRule`: source, rule_text, weight (0.0-1.0), is_immutable, enforcement_level
- `PolicyDecision`: allowed (bool), violated_rules, reason
- `Policy`: list of rules + `check_action()` method

`Policy.check_action()` uses keyword matching: all words in a rule_text must
appear in the combined action+context string (case-insensitive). Blocking
logic:

- Immutable rule with `enforcement_level="block"` -> action not allowed
- Mutable rule with `enforcement_level="block"` AND `weight > 0.7` -> not allowed
- Otherwise -> allowed (violated rules still reported)

`PolicyCompiler.compile()`: Severity-to-enforcement mapping: critical -> block,
high -> warn, medium -> log. Rules sorted: immutable first (by weight desc),
then mutable (by weight desc).

### Invariant Gates (3 new, 11 total)

The gate count went from 8 to 11. All three are Tier C (advisory, not blocking).

#### Anekanta Gate (`anekanta_gate.py`) -- 105 lines

Epistemological diversity check rooted in the Jain principle of Anekantavada
(many-sidedness). Verifies proposals consider three frames:

- **Mechanistic**: mechanism, circuit, activation, gradient, weight, layer,
  neuron, parameter, computation, optimization, loss, architecture
- **Phenomenological**: experience, awareness, consciousness, perception,
  witness, observer, subjective, phenomenal, qualia, first-person,
  introspection, recognition
- **Systems**: emergence, feedback, self-organization, complexity, adaptation,
  interaction, holistic, network, ecosystem, integration, dynamics, resilience

Decision logic:
- 3 frames detected -> PASS
- 2 frames detected -> WARN (reports which frame is missing)
- 0-1 frames detected -> FAIL

#### Dogma Drift Gate (`dogma_gate.py`) -- 79 lines

Detects confidence increasing without corresponding evidence increase --
the computational equivalent of epistemic drift toward dogma. Implements
Axiom 2 (Epistemic Humility).

Input: `DogmaDriftCheck` with confidence_before/after, evidence_count_before/after,
hard_coded_rules, total_rules.

Decision logic:
- confidence_delta > 0.10 AND evidence_delta <= 0 -> FAIL
- confidence_delta > 0.05 AND evidence_delta <= 0 -> WARN
- dogma_ratio > 0.30 (hard-coded rules / total rules) -> escalates PASS to WARN
- Otherwise -> PASS

#### Steelman Gate (`steelman_gate.py`) -- 88 lines

Requires proposals to include substantive counterarguments (steel-manning
opposing views). Default minimum: 20 characters per counterargument.

Decision logic:
- 0 counterarguments -> FAIL
- Counterarguments present but none >= 20 chars -> WARN
- At least 1 counterargument >= 20 chars -> PASS

### Evolution Pipeline (enhanced)

#### Sandbox Integration (`evolution.py` modified) -- 609 lines total

New methods added to `DarwinEngine`:

- `apply_in_sandbox(proposal, test_command, timeout)`: transitions proposal
  through WRITING -> TESTING, executes command in `LocalSandbox`, logs trace
- `run_cycle_with_sandbox(proposals, test_command, timeout)`: full pipeline
  with real test execution per proposal
- `_parse_sandbox_result(sr)`: extracts pytest pass/fail counts from stdout
  via regex, falls back to exit code heuristic

#### 5-Metric Evaluation with Safety Floor

Fitness is scored across 5 dimensions with the following weights:

| Metric | Weight | Source |
|--------|--------|--------|
| correctness | 0.30 | test pass rate from sandbox |
| dharmic_alignment | 0.25 | gate outcome (ALLOW=0.8, REVIEW=0.5, BLOCK=0.0) |
| elegance | 0.15 | AST-based code quality scoring |
| efficiency | 0.15 | inverse of diff size (smaller = better) |
| safety | 0.15 | 1.0 if gate passed, 0.0 if rejected |

**SAFETY FLOOR**: If safety == 0.0, ALL metrics are zeroed. Rejected proposals
cannot accumulate fitness regardless of other scores.

#### Canary Deploy + Rollback (`canary.py`) -- 157 lines

- `CanaryConfig`: promote_threshold (default 0.05), rollback_threshold
  (default -0.02), min_observations
- `CanaryDeployer.evaluate_canary(entry_id, canary_fitness)`: compares canary
  fitness against baseline from archive. Returns `CanaryResult` with decision.
- Decision logic:
  - delta > +0.05 -> PROMOTE
  - delta < -0.02 -> ROLLBACK
  - else -> DEFER
- `promote(entry_id)`: marks entry as promoted in archive
- `rollback(entry_id, reason)`: marks entry as rolled back

### Living Layers (Prakruti -- the dynamic)

#### Stigmergy (`stigmergy.py`) -- 221 lines

Pheromone-trail coordination without direct agent communication.

- `StigmergicMark`: id, timestamp, agent, file_path, action (read/write/scan/
  connect/dream), observation (max 200 chars), salience (0.0-1.0), connections
  (list of related file paths)
- `StigmergyStore`: JSONL-backed with hot file + archive file
  - `leave_mark(mark)`: append to JSONL
  - `read_marks(file_path, limit)`: recent marks, optionally filtered, newest-first
  - `hot_paths(window_hours, min_marks)`: files with heavy recent activity
  - `high_salience(threshold, limit)`: marks above salience threshold
  - `connections_for(file_path)`: unique connections from all marks on a path
  - `decay(max_age_hours)`: move old marks to archive (default 168h = 7 days)
  - `density()`: synchronous count of marks in hot file
- Module-level `leave_stigmergic_mark()` convenience function

#### Shakti Perception (`shakti.py`) -- 201 lines

Four energies from Sri Aurobindo mapped to computational perception:

| Energy | Domain | Keywords |
|--------|--------|----------|
| Maheshwari | Vision, architecture | vision, pattern, architecture, design, direction, strategy, purpose, telos, emergence, possibility |
| Mahakali | Force, decisive action | force, action, execute, deploy, speed, urgency, breakthrough, destroy, clear, decisive |
| Mahalakshmi | Harmony, beauty | harmony, balance, beauty, elegant, integrate, flow, rhythm, proportion, grace, coherence |
| Mahasaraswati | Precision, detail | precision, detail, exact, correct, careful, thorough, meticulous, accurate, validate, verify |

Components:

- `classify_energy(observation)`: keyword-based classification into dominant
  energy. Default fallback: Mahasaraswati (precision as conservative choice).
- `ShaktiLoop`: wired to a `StigmergyStore`
  - `perceive(current_context, agent_role)`: scans hot paths and high-salience
    marks, classifies each into a Shakti energy, determines impact level
    (local/module/system based on touch count thresholds)
  - `propose_local(perception)`: returns proposal dict for local-impact items
  - `escalate(perception)`: returns escalation dict for module/system items
- `SHAKTI_HOOK`: system prompt injection text (see LIVING_LAYERS.md)

#### Subconscious / HUM (`subconscious.py`) -- 191 lines

Lateral association engine that fires when stigmergy density crosses a
threshold (default: 50 new marks since last wake).

- `SubconsciousAssociation`: source_a, source_b, resonance_type, description,
  strength (0.0-1.0)
- `SubconsciousStream`: backed by StigmergyStore
  - `dream(sample_size)`: randomly sample recent marks, compute pairwise
    Jaccard similarity on observation text, classify resonance type:
    - `structural_echo`: same file_path
    - `temporal_coincidence`: within 1 hour
    - `pattern_similarity`: Jaccard > 0.3
    - `unknown`: everything else
  - Persists associations to `hum.jsonl`
  - Leaves dream marks back on the stigmergic lattice with `action="dream"`
  - `should_wake()`: True if density increased by >= wake_threshold since last dream
  - `get_recent_dreams(limit)`: newest-first from hum file
  - `strongest_resonances(threshold)`: sorted by strength descending


### Integration

#### Gates Wired (`telos_gates.py` modified) -- 293 lines

11 gates total (was 8). New gates wired:

| Gate | Tier | Behavior in TelosGatekeeper |
|------|------|-----------------------------|
| ANEKANTA | C | Full evaluation via `evaluate_anekanta()` |
| DOGMA_DRIFT | C | Defaults to PASS ("No drift data in this check") |
| STEELMAN | C | Defaults to PASS ("No proposal context for steelman check") |

Note: SVABHAAVA (Tier C) now delegates to the Anekanta evaluator for
epistemological diversity. DOGMA_DRIFT and STEELMAN default to PASS when
called through the general `check()` method because they require structured
input (confidence/evidence deltas, counterargument lists) that is not available
from a plain action string. They are fully functional when called directly
with proper input models.

#### SwarmManager Wired (`swarm.py` modified) -- 581 lines

v0.3.0 subsystems initialized in `init()`:
- `KernelGuard`: loads kernel from disk, creates default on first run
- `DharmaCorpus`: loads existing claims from JSONL
- `PolicyCompiler`: stateless, ready to compile on demand
- `CanaryDeployer`: wired to evolution archive
- `StigmergyStore`: wired to `~/.dharma/stigmergy/`

New public methods:
- `dharma_status()`: returns dict with kernel (axiom count, integrity),
  corpus (claim count), compiler, canary, and stigmergy (density) status
- `propose_claim(statement, category, **kwargs)`: propose to corpus
- `review_claim(claim_id, reviewer, action, comment)`: review a claim
- `promote_claim(claim_id)`: promote to ACCEPTED
- `canary_check(entry_id, canary_fitness)`: evaluate a canary deployment
- `compile_policy(context)`: compile kernel + accepted claims into Policy

#### CLI Commands (`dgc_cli.py` modified) -- 1051 lines

New command groups:

```
dgc dharma status          Dharma subsystem status
dgc dharma corpus          List corpus claims (--status, --category filters)
dgc dharma review ID       Review a claim
dgc evolve apply COMP DESC Run evolution with sandbox testing
dgc evolve promote ID      Promote a canary deployment
dgc evolve rollback ID     Rollback a deployment (--reason)
dgc stigmergy [--file P]   Show hot paths + high salience marks
dgc hum                    Show recent subconscious dreams
```

#### TUI Commands (`tui.py` modified) -- 1580+ lines

New slash commands in the Textual TUI:

- `/dharma [status]` -- kernel axiom count, integrity, corpus claim count,
  compiler and canary status, stigmergy density
- `/dharma corpus` -- list corpus claims
- `/corpus` -- alias for `/dharma corpus`
- `/stigmergy` -- hot paths and high salience marks
- `/hum` -- recent subconscious associations

#### Monitor Extended (`monitor.py` modified) -- 396 lines

- New anomaly type: `fitness_regression` -- detected when last 3 chronologically
  ordered fitness values are monotonically decreasing
- `bridge_summary(bridge)` static method: summarise a ResearchBridge instance
  (returns status dict)


## Test Summary

| Component | Test File | Tests | Status |
|-----------|-----------|-------|--------|
| dharma_kernel | test_dharma_kernel.py | 14 | PASS |
| dharma_corpus | test_dharma_corpus.py | 18 | PASS |
| policy_compiler | test_policy_compiler.py | 12 | PASS |
| anekanta_gate | test_anekanta_gate.py | 12 | PASS |
| dogma_gate | test_dogma_gate.py | 10 | PASS |
| steelman_gate | test_steelman_gate.py | 10 | PASS |
| evolution (full) | test_evolution.py | 51 | PASS |
| canary | test_canary.py | 12 | PASS |
| telos_gates | test_telos_gates.py | 24 | PASS |
| swarm | test_swarm.py | 16 | PASS |
| stigmergy | test_stigmergy.py | 12 | PASS |
| shakti | test_shakti.py | 10 | PASS |
| subconscious | test_subconscious.py | 8 | PASS |
| cli + monitor | test_godel_claw_cli.py | 13 | PASS |
| **Total (new files)** | **14 test files** | **~222** | |

Note: `test_evolution.py` (51 tests) includes both pre-existing and new
sandbox/cycle tests. The test counts above were verified by counting
`def test_` and `async def test_` definitions in each file.


## Known Gaps (v2 candidates)

1. **DOGMA_DRIFT and STEELMAN gates default to PASS** in `TelosGatekeeper.check()`.
   They require structured input (confidence deltas, counterargument lists) that
   the general action-check interface does not provide. They work correctly when
   called directly with proper input models. Wiring them into the evolution
   pipeline with real data is a v2 task.

2. **Shakti agents not spawned in startup_crew.py**. The ShaktiLoop exists and
   is functional, but no agent in the default crew runs a Shakti perception
   cycle. The SHAKTI_HOOK is defined but not yet injected into agent system
   prompts at spawn time.

3. **Subconscious dream trigger not wired into daemon heartbeat**. The
   `SubconsciousStream.should_wake()` method works, but nothing in the daemon
   loop calls it. Dreams only happen when explicitly invoked via CLI or TUI.

4. **Policy compiler uses keyword matching**. `Policy.check_action()` matches
   all keywords in rule_text against the action string. This is functional but
   crude -- an LLM-based evaluation would be more nuanced for complex policies.

5. **No MAP-Elites diversity archive**. The evolution archive tracks lineage
   but does not maintain a diversity grid. All selection is fitness-based.

6. **No debate chamber or parasite tournament**. Multi-agent adversarial
   evaluation is not yet implemented.

7. **Specs directory missing**. No `~/dharma_swarm/specs/` directory exists.
   The three spec documents (`GODEL_CLAW_V1_SPEC.md`, `Dharma_Constitution_v0.md`,
   `Dharma_Corpus_Schema.md`) were not found on disk.

8. **FitnessScore weights differ from spec sketch**. The spec mentioned a
   4-metric system (task_success 0.4, elegance 0.3, efficiency 0.2, safety 0.1).
   The actual build uses 5 metrics (correctness 0.30, dharmic_alignment 0.25,
   elegance 0.15, efficiency 0.15, safety 0.15). The safety floor behavior
   (safety=0 zeroes everything) is implemented as specified.


## File Manifest

### New source files (10)

| File | Lines | Purpose |
|------|-------|---------|
| `dharma_swarm/dharma_kernel.py` | 193 | Immutable axioms, tamper-evident kernel |
| `dharma_swarm/dharma_corpus.py` | 401 | Versioned claim store with lifecycle |
| `dharma_swarm/policy_compiler.py` | 168 | Fuse kernel + claims into executable policy |
| `dharma_swarm/anekanta_gate.py` | 105 | Epistemological diversity gate |
| `dharma_swarm/dogma_gate.py` | 79 | Confidence-without-evidence detection |
| `dharma_swarm/steelman_gate.py` | 88 | Counterargument quality gate |
| `dharma_swarm/canary.py` | 157 | Canary deploy / promote / rollback |
| `dharma_swarm/stigmergy.py` | 221 | Pheromone-trail coordination lattice |
| `dharma_swarm/shakti.py` | 201 | 4-energy perception loop |
| `dharma_swarm/subconscious.py` | 191 | Lateral association / dream engine |
| **Total new source** | **1,804** | |

### New test files (14)

| File | Tests |
|------|-------|
| `tests/test_dharma_kernel.py` | 14 |
| `tests/test_dharma_corpus.py` | 18 |
| `tests/test_policy_compiler.py` | 12 |
| `tests/test_anekanta_gate.py` | 12 |
| `tests/test_dogma_gate.py` | 10 |
| `tests/test_steelman_gate.py` | 10 |
| `tests/test_canary.py` | 12 |
| `tests/test_telos_gates.py` | 24 |
| `tests/test_evolution.py` | 51 |
| `tests/test_swarm.py` | 16 |
| `tests/test_stigmergy.py` | 12 |
| `tests/test_shakti.py` | 10 |
| `tests/test_subconscious.py` | 8 |
| `tests/test_godel_claw_cli.py` | 13 |

### Modified files (6)

| File | Lines | What Changed |
|------|-------|-------------|
| `dharma_swarm/telos_gates.py` | 293 | 8 -> 11 gates, Anekanta/Dogma/Steelman wired |
| `dharma_swarm/evolution.py` | 609 | Sandbox integration, parse_sandbox_result |
| `dharma_swarm/swarm.py` | 581 | v0.3.0 subsystems, dharma_status, corpus/policy/canary methods |
| `dharma_swarm/dgc_cli.py` | 1,051 | dharma, stigmergy, hum, evolve apply/promote/rollback commands |
| `dharma_swarm/tui.py` | ~1,580 | /dharma, /corpus, /stigmergy, /hum TUI commands |
| `dharma_swarm/monitor.py` | 396 | fitness_regression anomaly, bridge_summary |

### Module count

- Source modules (`dharma_swarm/*.py`): **44** (excluding `__init__.py`)
- Test files (`tests/test_*.py`): **39**


## Verification Commands

```bash
# Full test suite
cd ~/dharma_swarm && python3 -m pytest tests/ -q --tb=short

# Kernel integrity
python3 -c "
from dharma_swarm.dharma_kernel import DharmaKernel
k = DharmaKernel.create_default()
print(f'Axioms: {len(k.principles)}, Integrity: {k.verify_integrity()}')
"

# Gate count
python3 -c "
from dharma_swarm.telos_gates import TelosGatekeeper
print(f'Gates: {len(TelosGatekeeper.GATES)}')
"

# Stigmergy
python3 -c "from dharma_swarm.stigmergy import StigmergyStore; print('Stigmergy: OK')"

# Shakti
python3 -c "from dharma_swarm.shakti import ShaktiEnergy; print(f'Energies: {len(ShaktiEnergy)}'); print('Shakti: OK')"

# Subconscious
python3 -c "from dharma_swarm.subconscious import SubconsciousStream; print('Subconscious: OK')"

# Policy compiler
python3 -c "
from dharma_swarm.dharma_kernel import DharmaKernel
from dharma_swarm.policy_compiler import PolicyCompiler
k = DharmaKernel.create_default()
p = PolicyCompiler().compile(k.principles, [], context='test')
print(f'Policy rules: {len(p.rules)} ({len(p.get_immutable_rules())} immutable)')
"

# Corpus
python3 -c "from dharma_swarm.dharma_corpus import DharmaCorpus, ClaimCategory; print('Corpus: OK')"

# Module count
ls ~/dharma_swarm/dharma_swarm/*.py | grep -v __init__ | wc -l

# Test count
ls ~/dharma_swarm/tests/test_*.py | wc -l
```
