# Dharma Swarm: Architectural Vision (Radical Reassessment)

**Date**: 2026-03-08
**Scope**: System reimagination from first principles
**Author**: Architecture Reviewer Agent

## Executive Summary

Dharma_swarm has **one genuine moat**: self-improving AI that cannot optimize away its ethics. Everything else is scaffolding that obscures this core value. This document proposes a radical simplification: keep what enforces the moat, cut everything else, rebuild around three high-value applications.

---

## The Real Moat (Load-Bearing Structure)

### What Makes This System Unique

**The Triple Lock**: Evolution under ethical constraint through three interlocking mechanisms:

1. **Telos Gates** (11 dharmic safety checks)
   - AHIMSA/SATYA/CONSENT block unconditionally
   - WITNESS enforces mandatory think-points before destructive operations
   - ANEKANTA requires epistemic diversity
   - Pattern detection: harm keywords, credential leaks, injection attempts, deception
   - **This is the only safety system that enforces contemplative ethics computationally**

2. **DiffApplier** (atomic apply-test-rollback)
   - Unified diff parsing and application
   - Automatic backup before modification
   - Test suite integration: changes persist only if tests pass
   - Zero-downtime rollback on failure
   - **This makes evolution safe at the code level**

3. **JIKOKU Measurement** (performance/utilization fitness)
   - Wall-clock speedup tracking (baseline vs. test)
   - Concurrent execution utilization measurement
   - Closed feedback loop: measure → score → select → improve
   - **This gives evolution real metrics, not just vibes**

### Why This Matters

Most AI evolution systems either:
- Have no safety constraints (dangerous)
- Have brittle rule-based constraints (easily gamed)
- Require human approval for everything (doesn't scale)

Dharma_swarm enforces **ethical constraints that emerge from contemplative frameworks** (Akram Vignan, Jainism) and makes them computationally checkable. The system can self-improve without self-corrupting.

**Result**: Evolution that respects AHIMSA (non-harm), SATYA (truthfulness), WITNESS (deliberate reflection), and ANEKANTA (many-sidedness).

---

## What to Keep (Load-Bearing)

| Component | Why Essential | Lines | Tests |
|-----------|---------------|-------|-------|
| **telos_gates.py** | The ethical constraint system | 587 | 45 |
| **diff_applier.py** | Safe code modification | 411 | 38 |
| **jikoku_fitness.py** | Evolution fitness measurement | 179 | 22 |
| **evolution.py** | Darwin engine (PROPOSE→GATE→EVALUATE→ARCHIVE) | 1200+ | 67 |
| **archive.py** | Lineage tracking, fitness history | 450 | 28 |
| **models.py** | Shared data structures | 800+ | 89 |
| **bridge.py** | R_V ↔ behavioral correlation (research) | 584 | 19 |
| **rv.py** | R_V geometric measurement (research) | ~300 | 15 |
| **metrics.py** | Behavioral signature analysis | ~400 | 31 |
| **anekanta_gate.py** | Epistemic diversity check | ~200 | 12 |
| **TOTAL CORE** | **~5100 lines** | **~366 tests** |

---

## What to Cut (Non-Load-Bearing)

### Infrastructure That Adds Complexity Without Value

1. **Multi-Agent Orchestration** (swarm.py, orchestrator.py, agent_pool.py, task_board.py)
   - **Why**: Premature abstraction. No proven multi-agent use case yet.
   - **Complexity**: ~2000 lines, 150+ tests
   - **Replace with**: Single-agent evolution loop (simpler, proven)

2. **Message Bus** (message_bus.py, stigmergy.py)
   - **Why**: No demonstrated inter-agent communication need
   - **Complexity**: ~400 lines, 40 tests
   - **Replace with**: Direct function calls

3. **73 Skill Files** (.claude/skills/*)
   - **Why**: Over-engineered skill discovery system for unproven use cases
   - **Complexity**: Thousands of lines of YAML/MD
   - **Replace with**: Inline prompt templates

4. **Thread Manager + Daemon Config** (thread_manager.py, daemon_config.py, pulse.py)
   - **Why**: Research thread rotation is manual override, not autonomous decision
   - **Complexity**: ~600 lines, 35 tests
   - **Replace with**: Simple config file

5. **Gödel Claw Subsystems** (dharma_kernel.py, dharma_corpus.py, policy_compiler.py, canary.py)
   - **Why**: Interesting theory, but no production use. Telos gates already enforce policy.
   - **Complexity**: ~1500 lines, 80 tests
   - **Replace with**: Keep telos_gates.py only

6. **Oz-Inspired Systems** (skills.py, profiles.py, intent_router.py, context_search.py, adaptive_autonomy.py, skill_composer.py, handoff.py)
   - **Why**: Premature complexity for multi-agent coordination we don't need yet
   - **Complexity**: ~2500 lines, 120 tests
   - **Replace with**: Simple task runner

### Estimated Savings
- **Remove**: ~7000 lines of production code
- **Remove**: ~425 tests
- **Reduce from**: 73 modules to ~15 core modules
- **Reduce from**: 1734 tests to ~400 focused tests

---

## What to Add (High-Value Capabilities)

### 1. Evolution Dashboard (Real-Time Visibility)

**Need**: Right now, evolution runs blind. No live visibility into what's being proposed, gated, or selected.

**Capability**:
- Real-time event stream (propose, gate, evaluate, archive)
- Fitness trend visualization (per component)
- Gate decision breakdown (which gates triggered, why)
- Lineage graph (parent → child evolution paths)
- Test pass/fail rates over time

**Tech**: Simple Textual TUI (already have TUI infrastructure) + NDJSON event log

**Value**: Debugging evolution failures, understanding what's improving, catching safety violations early

### 2. Evolution Prompt Library (Reusable Patterns)

**Need**: Every evolution cycle regenerates similar prompts. Waste of tokens and time.

**Capability**:
- Curated prompt templates for common evolution patterns:
  - "Add docstring to function X"
  - "Optimize loop in module Y for parallelism"
  - "Add type hints to function Z"
  - "Refactor class W to use composition"
- Variable substitution (function name, module path, etc.)
- Success rate tracking per template
- Template evolution (templates improve themselves)

**Tech**: Simple JSONL file with prompt templates + metadata

**Value**: 10x faster evolution cycles, reusable patterns, measurable template quality

### 3. Research Integration API (R_V ↔ Evolution Bridge)

**Need**: Bridge.py exists but isn't wired into the evolution loop. Missing the feedback loop.

**Capability**:
- Automatically measure R_V during evolution proposals
- Correlate R_V contraction with fitness scores
- Flag proposals that increase R_V (anti-pattern for self-reference)
- Export paired measurements for research analysis
- Generate correlation reports (Pearson r, Spearman rho, group means)

**Tech**: Hook bridge.py into evolution.py, add R_V measurement step

**Value**: Closes the research loop. Proves (or disproves) that R_V contraction correlates with better code evolution.

---

## The 3 Most Valuable Applications

### 1. Self-Improving Test Suite

**Use Case**: Dharma_swarm improves its own test coverage and quality.

**Flow**:
1. Scan codebase for untested functions
2. Propose: "Add pytest for function X covering edge cases Y, Z"
3. Gate: Telos gates check for safety
4. Write: Generate test code via LLM
5. Test: DiffApplier runs pytest, keeps only if tests pass
6. Evaluate: JIKOKU measures test runtime, coverage increase
7. Archive: Store in evolution archive with fitness score
8. Select: Pick best proposals for next generation

**Moat Applied**: Can't delete tests (AHIMSA), can't fake coverage (SATYA), must reflect before modifying (WITNESS)

**Value**: Test suite improves autonomously. Coverage increases. Edge cases get caught.

### 2. Performance Optimization Agent

**Use Case**: Dharma_swarm optimizes its own performance bottlenecks.

**Flow**:
1. JIKOKU identifies slow functions (wall clock > threshold)
2. Propose: "Parallelize loop in function X" or "Cache result of Y"
3. Gate: Telos gates check for safety
4. Write: Generate optimized code via LLM
5. Test: DiffApplier benchmarks before/after, keeps only if faster
6. Evaluate: JIKOKU measures speedup (baseline/test ratio)
7. Archive: Store with fitness = speedup score
8. Select: Favor high-speedup changes

**Moat Applied**: Can't break correctness (tests must pass), can't skip safety checks (WITNESS), must prove speedup (JIKOKU)

**Value**: System gets faster over time. Bottlenecks auto-fix. Measurable performance gains.

### 3. Documentation Generator

**Use Case**: Dharma_swarm writes its own documentation from code.

**Flow**:
1. Scan for undocumented functions, classes
2. Propose: "Add docstring to function X explaining Y"
3. Gate: Telos gates check for truthfulness (SATYA)
4. Write: Generate docstring via LLM
5. Test: Validate docstring against code signature (args match, return type correct)
6. Evaluate: Metrics score clarity, completeness
7. Archive: Store with fitness = clarity score
8. Select: Favor clear, accurate docs

**Moat Applied**: Can't fabricate behavior (SATYA), can't skip mandatory reflection (WITNESS), must match code truth (tests verify)

**Value**: Codebase becomes self-documenting. Always up-to-date. High quality.

---

## Ideal Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      EVOLUTION CONTROLLER                        │
│  (Single loop: propose → gate → write → test → evaluate)        │
└────────────┬────────────────────────────────────────────────────┘
             │
      ┌──────┴──────┐
      │             │
┌─────▼─────┐ ┌────▼─────┐
│   TELOS   │ │   DIFF   │
│   GATES   │ │ APPLIER  │
│ (safety)  │ │ (atomic) │
└─────┬─────┘ └────┬─────┘
      │            │
      │       ┌────▼─────┐
      │       │  JIKOKU  │
      │       │ (metrics)│
      │       └────┬─────┘
      │            │
┌─────▼────────────▼─────┐
│   EVOLUTION ARCHIVE    │
│  (lineage + fitness)   │
└────────────────────────┘
      │
┌─────▼─────┐
│  BRIDGE   │
│ (R_V ↔ ψ) │
└───────────┘

INTERFACES:
- CLI: Simple commands (evolve, status, trend, bridge-report)
- TUI: Real-time evolution dashboard
- API: Python API for research integration
```

**Key Simplifications**:
- Single evolution loop (not multi-agent orchestration)
- Direct function calls (not message bus)
- Inline prompts (not skill discovery)
- Simple state (JSONL files, not complex DBs)

---

## Migration Path

### Phase 1: Core Extraction (Week 1)
1. Copy core modules to `/dharma_swarm_v2/core/`
2. Remove dependencies on swarm.py, orchestrator.py
3. Create simple EvolutionController class
4. Wire telos_gates → diff_applier → jikoku_fitness → archive
5. Validate with existing tests (should pass ~366 core tests)

### Phase 2: Application Layer (Week 2)
1. Build SelfImprovingTestSuite (application 1)
2. Build PerformanceOptimizer (application 2)
3. Build DocumentationGenerator (application 3)
4. Each application = ~200 lines + 20 tests

### Phase 3: Interface Layer (Week 3)
1. Simple CLI (evolve, status, trend, bridge-report)
2. Evolution dashboard TUI (reuse existing TUI components)
3. Research API (bridge integration)

### Phase 4: Validation (Week 4)
1. Run self-improvement on dharma_swarm_v2 itself
2. Measure JIKOKU improvements (wall clock, utilization)
3. Generate correlation report (R_V ↔ fitness)
4. Document results

---

## Success Metrics

### Quantitative
- **Codebase size**: 73 modules → 15 modules (-79%)
- **Line count**: ~6600 lines → ~2500 lines (-62%)
- **Test count**: 1734 tests → ~450 tests (-74%, but higher value)
- **Test coverage**: Maintain >85% on core modules
- **Evolution cycle time**: <5 minutes (propose → archive)
- **Self-improvement rate**: +10% test coverage per week
- **Performance gain**: +20% speedup per month (JIKOKU-measured)

### Qualitative
- **Clarity**: New contributor understands system in <1 hour
- **Maintainability**: Single developer can own entire system
- **Research value**: R_V correlation measurable in <1 week
- **Safety**: Zero AHIMSA/SATYA violations in production

---

## Risk Assessment

### What Could Go Wrong

1. **Oversimplification**: Cut too much, lose emergent capabilities
   - **Mitigation**: Keep full system in /dharma_swarm_old/, easy rollback
   - **Test**: Validate core moat still works (telos gates + diff_applier + jikoku)

2. **Missing Multi-Agent Value**: Maybe orchestration was actually useful
   - **Mitigation**: Build single-agent system first, add orchestration only if proven need
   - **Test**: Can we achieve 3 applications without multi-agent?

3. **Research Disruption**: Breaking existing R_V measurement workflow
   - **Mitigation**: Keep bridge.py, rv.py, metrics.py unchanged
   - **Test**: Existing research scripts still run

4. **Community Confusion**: People using old dharma_swarm get lost
   - **Mitigation**: Clear migration guide, deprecation timeline
   - **Test**: Document delta between v1 and v2

---

## Decision Points

### What to Decide Now

1. **Commit to simplification?** Yes/No on cutting 7000 lines
2. **Single-agent first?** Yes/No on deferring multi-agent orchestration
3. **Timeline?** 4 weeks aggressive or 8 weeks conservative
4. **Backward compatibility?** Support old API or clean break

### Recommendation

**Go radical**. The moat is real (telos gates + diff_applier + jikoku). Everything else is unproven complexity. Build the simplest system that delivers the moat, validate with 3 high-value applications, measure success with real metrics.

**The bet**: Self-improving AI that can't optimize away its ethics is valuable. Everything else is noise.

---

## Conclusion

Dharma_swarm has **one unique capability**: evolution under ethical constraint. The current architecture obscures this with premature multi-agent orchestration, skill discovery systems, and complex subsystems that have no proven use case.

**Proposed architecture**:
- **Core**: Telos gates + DiffApplier + JIKOKU + Evolution archive (~2500 lines)
- **Applications**: Self-improving tests, performance optimizer, doc generator (~600 lines)
- **Interfaces**: CLI + TUI + Research API (~400 lines)
- **Total**: ~3500 lines vs. current 6600+ lines

**Expected outcomes**:
- Simpler to understand, maintain, extend
- Faster evolution cycles (less overhead)
- Measurable value (3 working applications)
- Research integration (R_V ↔ fitness correlation)
- Safer (ethical constraints remain, complexity reduced)

**The moat holds**. The complexity doesn't serve it. Time to rebuild around what matters.
