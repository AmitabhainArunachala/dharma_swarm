---
title: Darwin Engine Quick-Start Guide
path: docs/architecture/DARWIN_ENGINE_QUICK_START_GUIDE.md
slug: darwin-engine-quick-start-guide
doc_type: documentation
status: active
summary: 'Date : 2026-03-10 Audience : Engineer starting Darwin Engine enhancement work (Day 1) Time to complete : 2-4 hours (prototype validation)'
source:
  provenance: repo_local
  kind: documentation
  origin_signals:
  - dharma_swarm/archive.py
  - dharma_swarm/evolution.py
  - tests/test_evolution.py
  - dharma_swarm/meta_learning_prototype.py
  - scripts/test_meta_learning.py
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- software_architecture
- knowledge_management
- research_methodology
- verification
- frontend_engineering
- operations
inspiration:
- verification
- research_synthesis
connected_python_files:
- dharma_swarm/archive.py
- dharma_swarm/evolution.py
- tests/test_evolution.py
- dharma_swarm/meta_learning_prototype.py
- scripts/test_meta_learning.py
connected_python_modules:
- dharma_swarm.archive
- dharma_swarm.evolution
- tests.test_evolution
- dharma_swarm.meta_learning_prototype
- scripts.test_meta_learning
connected_relevant_files:
- dharma_swarm/archive.py
- dharma_swarm/evolution.py
- tests/test_evolution.py
- dharma_swarm/meta_learning_prototype.py
- scripts/test_meta_learning.py
improvement:
  room_for_improvement:
  - Strengthen cross-links to adjacent docs and implementing modules.
  - Separate durable knowledge from transient session context.
  - Add a tighter summary for first-pass retrieval.
  - Review whether this file should stay in `docs` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: documentation
  vault_path: docs/architecture/DARWIN_ENGINE_QUICK_START_GUIDE.md
  retrieval_terms:
  - darwin
  - engine
  - quick
  - start
  - guide
  - date
  - '2026'
  - audience
  - engineer
  - starting
  - enhancement
  - work
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: working
  semantic_weight: 0.6
  coordination_comment: 'Date : 2026-03-10 Audience : Engineer starting Darwin Engine enhancement work (Day 1) Time to complete : 2-4 hours (prototype validation)'
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising docs/architecture/DARWIN_ENGINE_QUICK_START_GUIDE.md reinforces its salience without needing a separate message.
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
# Darwin Engine Quick-Start Guide

**Date**: 2026-03-10
**Audience**: Engineer starting Darwin Engine enhancement work (Day 1)
**Time to complete**: 2-4 hours (prototype validation)

---

## What You're Building

A **2-hour prototype** that proves meta-learning can improve Darwin Engine evolution. If it works, you'll have validated the core concept and can proceed to the full 10-week implementation.

**Goal**: Run 3 meta-cycles (5 object-cycles each) and demonstrate that evolving fitness weights improves object-level fitness by >5%.

---

## Prerequisites

**Required**:
- Python 3.11+
- `dharma_swarm` installed and working
- 1-2 hours of uninterrupted time

**Helpful**:
- Read `DARWIN_ENGINE_RESEARCH_EXECUTIVE_SUMMARY.md` (10 min overview)
- Understand basic evolutionary algorithms (mutation, fitness, selection)

**Not required**:
- Deep understanding of Darwin Engine internals
- Knowledge of meta-learning theory
- Experience with genetic algorithms

---

## Step 1: Read the Context (15 minutes)

### What is meta-learning?

**Normal evolution** (object-level):
```
Fitness weights: [fixed]
↓
Generate proposals → Evaluate fitness → Select parents → Repeat
```

**Meta-evolution** (two-level):
```
Meta-cycle 1:
  Fitness weights: config A
  ↓
  Run 5 object cycles → Measure fitness trend
  ↓
  Meta-fitness: trend = -0.002 (declining)
  ↓
  Evolve weights → config B

Meta-cycle 2:
  Fitness weights: config B
  ↓
  Run 5 object cycles → Measure fitness trend
  ↓
  Meta-fitness: trend = +0.008 (improving!)
  ↓
  Keep weights
```

**Key insight**: If config B produces better fitness trends than config A, keep config B. Over time, discover optimal weights.

### Why fitness weights matter

Current weights (hardcoded in `archive.py`):
```python
_DEFAULT_WEIGHTS = {
    "correctness": 0.20,      # 20% of total fitness
    "dharmic_alignment": 0.15,
    "performance": 0.12,
    "utilization": 0.12,
    "economic_value": 0.15,
    "elegance": 0.10,
    "efficiency": 0.10,
    "safety": 0.06,
}
```

**Questions**:
- Are these optimal? (Probably not, they're guesses)
- Do they vary by task? (Probably yes)
- Can evolution find better ones? (That's what we're testing)

---

## Step 2: Code Changes (1 Hour)

### Change 1: Allow Custom Fitness Weights

**File**: `dharma_swarm/archive.py`
**Location**: Line ~40, in `FitnessScore` class

**Current code**:
```python
def weighted(self, weights: dict[str, float] | None = None) -> float:
    w = weights or _DEFAULT_WEIGHTS
    return sum(getattr(self, k, 0.0) * v for k, v in w.items())
```

**If this method doesn't exist yet, add it**:
```python
class FitnessScore(BaseModel):
    # ... existing fields ...

    def weighted(self, weights: dict[str, float] | None = None) -> float:
        """Compute weighted fitness score.

        Args:
            weights: Optional custom weights. If None, uses _DEFAULT_WEIGHTS.

        Returns:
            Weighted sum of fitness dimensions.
        """
        w = weights or _DEFAULT_WEIGHTS
        return sum(getattr(self, k, 0.0) * v for k, v in w.items())
```

**Test it**:
```python
# In Python REPL
from dharma_swarm.archive import FitnessScore

fitness = FitnessScore(correctness=0.8, elegance=0.6)
print(fitness.weighted())  # Default weights
print(fitness.weighted({"correctness": 1.0, "elegance": 0.0}))  # Custom weights
```

### Change 2: Inject Custom Weights into Darwin Engine

**File**: `dharma_swarm/evolution.py`
**Location**: In `DarwinEngine.__init__` and `evaluate()` methods

**In `__init__`** (add parameter):
```python
class DarwinEngine:
    def __init__(
        self,
        archive_path: Path | None = None,
        traces_path: Path | None = None,
        predictor_path: Path | None = None,
        circuit_breaker_limit: int = 3,
        max_reflection_reroutes: int = 2,
        custom_fitness_weights: dict[str, float] | None = None,  # NEW
    ) -> None:
        self.archive = EvolutionArchive(path=archive_path)
        self.traces = TraceStore(base_path=traces_path)
        self.predictor = FitnessPredictor(history_path=predictor_path)
        self._circuit_breaker_limit = max(1, int(circuit_breaker_limit))
        self._max_reflection_reroutes = max(0, int(max_reflection_reroutes))
        self._custom_fitness_weights = custom_fitness_weights  # NEW
        self._initialized: bool = False
```

**In `evaluate()`** (use custom weights):
```python
async def evaluate(
    self,
    proposal: Proposal,
    test_results: dict[str, Any] | None = None,
    code: str | None = None,
    baseline_session_id: str | None = None,
    test_session_id: str | None = None,
) -> Proposal:
    # ... existing code for computing fitness ...

    fitness = FitnessScore(
        correctness=correctness,
        elegance=elegance,
        dharmic_alignment=dharmic_alignment,
        performance=performance,
        utilization=utilization,
        efficiency=efficiency,
        safety=safety,
    )

    proposal.actual_fitness = fitness
    proposal.status = EvolutionStatus.EVALUATED

    # Use custom weights if provided
    weighted_fitness = fitness.weighted(weights=self._custom_fitness_weights)

    logger.info(
        "Proposal %s evaluated: weighted=%.3f",
        proposal.id,
        weighted_fitness,  # Use this value
    )
    return proposal
```

**Test it**:
```bash
# Run existing tests to verify nothing broke
python -m pytest tests/test_evolution.py -v
```

### Change 3: Create Meta-Learning Prototype

**File**: `dharma_swarm/meta_learning_prototype.py` (new file)

**Create the file** and paste this code:

```python
"""Minimal meta-learning prototype for Darwin Engine."""

from __future__ import annotations
import numpy as np
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dharma_swarm.evolution import DarwinEngine, CycleResult


class MetaLearningPrototype:
    """Minimal two-level evolution: learn fitness weights."""

    def __init__(self, darwin_engine: DarwinEngine):
        self.darwin = darwin_engine
        self.fitness_weights = self._default_weights()
        self.meta_history: list[dict] = []

    @staticmethod
    def _default_weights() -> dict[str, float]:
        """Current hardcoded weights from archive.py."""
        return {
            "correctness": 0.20,
            "dharmic_alignment": 0.15,
            "performance": 0.12,
            "utilization": 0.12,
            "economic_value": 0.15,
            "elegance": 0.10,
            "efficiency": 0.10,
            "safety": 0.06,
        }

    async def run_meta_experiment(
        self,
        proposals: list,
        n_meta_cycles: int = 3,
        n_object_cycles: int = 5,
    ) -> dict:
        """Run meta-learning experiment."""
        results = {
            "meta_cycles": [],
            "weight_history": [],
            "fitness_improvement": 0.0,
        }

        for meta_i in range(n_meta_cycles):
            print(f"\n=== Meta-Cycle {meta_i + 1}/{n_meta_cycles} ===")
            print(f"Current weights: {self._format_weights(self.fitness_weights)}")

            # Update Darwin Engine's custom weights
            self.darwin._custom_fitness_weights = self.fitness_weights

            # Run object-level evolution
            fitness_trajectory = []
            for obj_i in range(n_object_cycles):
                cycle_result = await self.darwin.run_cycle(proposals)
                fitness_trajectory.append(cycle_result.best_fitness)
                print(f"  Object cycle {obj_i + 1}: fitness={cycle_result.best_fitness:.3f}")

            # Compute meta-fitness
            meta_fitness = self._compute_meta_fitness(fitness_trajectory)
            print(f"Meta-fitness (trend): {meta_fitness:.3f}")

            # Store history
            results["meta_cycles"].append({
                "meta_cycle": meta_i,
                "fitness_trajectory": fitness_trajectory,
                "meta_fitness": meta_fitness,
                "weights": dict(self.fitness_weights),
            })
            results["weight_history"].append(dict(self.fitness_weights))

            # Evolve weights if performance is poor
            if meta_fitness < 0.0:
                print("  → Fitness declining, evolving weights...")
                self.fitness_weights = self._evolve_weights()
            else:
                print("  → Fitness improving, keeping weights")

        # Compute overall improvement
        first_trajectory = results["meta_cycles"][0]["fitness_trajectory"]
        last_trajectory = results["meta_cycles"][-1]["fitness_trajectory"]
        results["fitness_improvement"] = (
            np.mean(last_trajectory) - np.mean(first_trajectory)
        )

        print(f"\n=== Meta-Learning Complete ===")
        print(f"Fitness improvement: {results['fitness_improvement']:.3f}")
        print(f"Final weights: {self._format_weights(self.fitness_weights)}")

        return results

    def _compute_meta_fitness(self, fitness_trajectory: list[float]) -> float:
        """Meta-fitness = gradient of fitness trend."""
        if len(fitness_trajectory) < 2:
            return 0.0
        return float(np.mean(np.diff(fitness_trajectory)))

    def _evolve_weights(self) -> dict[str, float]:
        """Generate new weights via Dirichlet sampling."""
        n_dims = len(self.fitness_weights)
        new_weights_vec = np.random.dirichlet([1.0] * n_dims)
        return dict(zip(self.fitness_weights.keys(), new_weights_vec))

    @staticmethod
    def _format_weights(weights: dict[str, float]) -> str:
        """Format weights for printing."""
        return ", ".join(f"{k[:3]}={v:.2f}" for k, v in weights.items())
```

**Test it**:
```bash
python -c "from dharma_swarm.meta_learning_prototype import MetaLearningPrototype; print('Import successful')"
```

---

## Step 3: Create Test Script (30 Minutes)

**File**: `scripts/test_meta_learning.py` (new file)

**Create the file** and paste this code:

```python
#!/usr/bin/env python3
"""Test meta-learning prototype on synthetic evolution task."""

import asyncio
from dharma_swarm.evolution import DarwinEngine, Proposal
from dharma_swarm.meta_learning_prototype import MetaLearningPrototype


async def generate_test_proposals(n: int = 5) -> list[Proposal]:
    """Generate synthetic proposals for testing."""
    proposals = []
    for i in range(n):
        proposals.append(
            Proposal(
                component="test_module.py",
                change_type="mutation",
                description=f"Test mutation {i}",
                diff=f"# Change {i}\n",
            )
        )
    return proposals


async def main():
    """Run meta-learning validation experiment."""
    print("=== Meta-Learning Prototype Validation ===\n")

    # Initialize Darwin Engine
    darwin = DarwinEngine()
    await darwin.init()

    # Create meta-learner
    meta = MetaLearningPrototype(darwin)

    # Generate test proposals
    proposals = await generate_test_proposals(n=5)

    # Run meta-experiment
    results = await meta.run_meta_experiment(
        proposals=proposals,
        n_meta_cycles=3,
        n_object_cycles=5,
    )

    # Analyze results
    print("\n=== Analysis ===")
    print(f"Fitness improvement: {results['fitness_improvement']:.3f}")

    if results['fitness_improvement'] > 0:
        print("✓ Meta-learning SUCCESSFUL: Fitness improved")
    else:
        print("✗ Meta-learning FAILED: No improvement (may need more cycles)")

    # Plot weight evolution
    print("\n=== Weight Evolution ===")
    for i, weights in enumerate(results['weight_history']):
        print(f"Meta-cycle {i}: {meta._format_weights(weights)}")


if __name__ == "__main__":
    asyncio.run(main())
```

**Make executable**:
```bash
chmod +x scripts/test_meta_learning.py
```

---

## Step 4: Run the Experiment (15 Minutes)

```bash
# From dharma_swarm/ directory
python scripts/test_meta_learning.py
```

**Expected output** (success scenario):
```
=== Meta-Learning Prototype Validation ===

=== Meta-Cycle 1/3 ===
Current weights: cor=0.20, dha=0.15, per=0.12, uti=0.12, eco=0.15, ele=0.10, eff=0.10, saf=0.06
  Object cycle 1: fitness=0.450
  Object cycle 2: fitness=0.455
  Object cycle 3: fitness=0.452
  Object cycle 4: fitness=0.448
  Object cycle 5: fitness=0.447
Meta-fitness (trend): -0.002
  → Fitness declining, evolving weights...

=== Meta-Cycle 2/3 ===
Current weights: cor=0.25, dha=0.18, per=0.10, uti=0.08, eco=0.12, ele=0.12, eff=0.09, saf=0.06
  Object cycle 1: fitness=0.465
  Object cycle 2: fitness=0.472
  Object cycle 3: fitness=0.481
  Object cycle 4: fitness=0.489
  Object cycle 5: fitness=0.495
Meta-fitness (trend): 0.008
  → Fitness improving, keeping weights

=== Meta-Cycle 3/3 ===
Current weights: cor=0.25, dha=0.18, per=0.10, uti=0.08, eco=0.12, ele=0.12, eff=0.09, saf=0.06
  Object cycle 1: fitness=0.501
  Object cycle 2: fitness=0.510
  Object cycle 3: fitness=0.518
  Object cycle 4: fitness=0.525
  Object cycle 5: fitness=0.531
Meta-fitness (trend): 0.007
  → Fitness improving, keeping weights

=== Meta-Learning Complete ===
Fitness improvement: 0.081
Final weights: cor=0.25, dha=0.18, per=0.10, uti=0.08, eco=0.12, ele=0.12, eff=0.09, saf=0.06

=== Analysis ===
Fitness improvement: 0.081
✓ Meta-learning SUCCESSFUL: Fitness improved
```

**Interpretation**:
- Meta-cycle 1: Default weights → declining fitness
- Meta-cycle 2: Evolved weights (higher correctness, dharmic) → improving fitness
- Meta-cycle 3: Same weights → continued improvement
- **Result**: +8.1% fitness improvement via weight evolution

---

## Step 5: Interpret Results (30 Minutes)

### Success Criteria

**Success**: Fitness improvement > 0.05 (5%)

**Reasons for success**:
- Weight evolution discovered better config than defaults
- Meta-learning loop worked as designed
- Object-level evolution responded to weight changes

**Next steps**:
1. Document successful weight config
2. Run longer experiment (5 meta-cycles, 10 object-cycles)
3. Proceed to full P0 implementation (10 weeks)

### Failure Scenarios

**Scenario 1**: Fitness improvement < 0.05 but > 0
- **Interpretation**: Meta-learning is working but needs more cycles
- **Action**: Increase to 5 meta-cycles, re-run
- **If still fails**: Increase to 10 meta-cycles

**Scenario 2**: Fitness improvement ≈ 0
- **Interpretation**: Weight evolution not finding better configs
- **Action**: Debug why fitness isn't changing
  - Check: Are proposals diverse enough?
  - Check: Is fitness evaluation working correctly?
  - Try: Different mutation strategy (Gaussian instead of Dirichlet)

**Scenario 3**: Fitness declining (< 0)
- **Interpretation**: Weight evolution is making things worse
- **Action**: Debug weight sampling
  - Check: Are new weights valid (sum to 1.0)?
  - Check: Are weights being injected correctly?
  - Try: Smaller mutations (perturb existing weights slightly)

### Debugging Checklist

If experiment fails:

1. **Verify weight injection**:
   ```python
   # Add debug print in evaluate()
   print(f"Using weights: {self._custom_fitness_weights}")
   ```

2. **Check fitness computation**:
   ```python
   # In test script
   print(f"Default weighted: {fitness.weighted()}")
   print(f"Custom weighted: {fitness.weighted(custom_weights)}")
   ```

3. **Verify proposal diversity**:
   ```python
   # Are all proposals identical?
   for p in proposals:
       print(p.component, p.change_type, p.diff[:50])
   ```

4. **Check meta-fitness calculation**:
   ```python
   # Is gradient being computed correctly?
   trajectory = [0.1, 0.2, 0.3]
   print(np.mean(np.diff(trajectory)))  # Should be 0.1
   ```

---

## Step 6: Next Actions (Decision Point)

### If Prototype Succeeds

**Short-term (1 week)**:
1. Clean up prototype code (add docstrings, type hints)
2. Add unit tests for `MetaLearningPrototype`
3. Extend to evolve mutation rate (not just weights)
4. Document findings in `DARWIN_ENGINE_META_LEARNING_RESULTS.md`

**Medium-term (4 weeks)**:
1. Implement full `meta_evolution.py` from P0 spec
2. Add meta-archive persistence (JSONL)
3. Implement crossover (average best meta-configs)
4. Benchmark on real evolution tasks (not synthetic)

**Long-term (10 weeks)**:
1. Complete all P0 enhancements (UCB, convergence, landscape)
2. Integration testing (100-cycle runs)
3. Production deployment
4. Research paper (optional)

### If Prototype Fails

**Immediate**:
1. Debug using checklist above
2. Increase meta-cycles to 5-10
3. Try different mutation strategy
4. Consult with meta-learning expert

**If still fails after debugging**:
1. Shelve meta-learning for now
2. Focus on other P0 enhancements (UCB, convergence)
3. Return to meta-learning after other components proven

---

## Troubleshooting

### Error: "Module 'dharma_swarm.meta_learning_prototype' not found"

**Cause**: File not created or in wrong location

**Fix**:
```bash
# Verify file exists
ls dharma_swarm/meta_learning_prototype.py

# If not, create it
touch dharma_swarm/meta_learning_prototype.py
# Paste code from Step 2
```

### Error: "TypeError: weighted() got unexpected keyword argument 'weights'"

**Cause**: Changes to `archive.py` not applied

**Fix**: Re-check Step 2, Change 1. Ensure `weighted()` method accepts `weights` parameter.

### Error: "AttributeError: 'DarwinEngine' object has no attribute '_custom_fitness_weights'"

**Cause**: Changes to `evolution.py` not applied

**Fix**: Re-check Step 2, Change 2. Ensure `__init__` adds `_custom_fitness_weights` attribute.

### Error: "RuntimeError: Event loop is closed"

**Cause**: Async issues

**Fix**: Ensure running with `asyncio.run(main())`, not direct `await main()`.

---

## Success Checklist

Before declaring success:

- [ ] Code changes compile (no syntax errors)
- [ ] Tests pass: `pytest tests/test_evolution.py -v`
- [ ] Prototype imports: `from dharma_swarm.meta_learning_prototype import MetaLearningPrototype`
- [ ] Test script runs: `python scripts/test_meta_learning.py`
- [ ] Results show improvement: fitness_improvement > 0.05
- [ ] Weight evolution logged: see different weights across meta-cycles
- [ ] No errors or warnings in output

---

## Time Estimate

| Step | Time | Cumulative |
|------|------|------------|
| 1. Read context | 15 min | 15 min |
| 2. Code changes | 60 min | 1h 15m |
| 3. Test script | 30 min | 1h 45m |
| 4. Run experiment | 15 min | 2h |
| 5. Interpret results | 30 min | 2h 30m |
| 6. Next actions (if success) | 30 min | 3h |
| **Total** | **2-3 hours** | |

**Note**: If debugging needed, add 1-2 hours.

---

## Resources

### Documentation
- `DARWIN_ENGINE_RESEARCH_EXECUTIVE_SUMMARY.md` - High-level overview
- `DARWIN_ENGINE_PERPETUAL_EVOLUTION_RESEARCH.md` - Deep dive (14 gaps)
- `DARWIN_ENGINE_P0_IMPLEMENTATION_SPEC.md` - Full implementation specs
- `DARWIN_ENGINE_META_LEARNING_PROTOTYPE.md` - Detailed prototype guide

### Code Locations
- `dharma_swarm/archive.py` - FitnessScore class
- `dharma_swarm/evolution.py` - DarwinEngine class
- `dharma_swarm/meta_learning_prototype.py` - Prototype (you create this)
- `scripts/test_meta_learning.py` - Test script (you create this)

### Key Concepts
- **Meta-learning**: Learning to learn (evolve evolution parameters)
- **Fitness weights**: 8-dimensional score combination
- **Object-level**: Normal evolution (proposals → fitness → selection)
- **Meta-level**: Evolution of evolution (weights → meta-fitness → weight mutation)

---

**JSCA!** Quick-start guide complete. Day 1 engineer can now validate meta-learning in 2-3 hours.
