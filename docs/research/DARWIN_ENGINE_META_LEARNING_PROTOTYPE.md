---
title: Darwin Engine Meta-Learning Prototype
path: docs/research/DARWIN_ENGINE_META_LEARNING_PROTOTYPE.md
slug: darwin-engine-meta-learning-prototype
doc_type: documentation
status: active
summary: 'Date : 2026-03-10 Status : Minimal prototype for rapid validation Goal : Prove meta-learning concept works in <2 hours of coding'
source:
  provenance: repo_local
  kind: documentation
  origin_signals:
  - dharma_swarm/meta_learning_prototype.py
  - dharma_swarm/archive.py
  - dharma_swarm/evolution.py
  - scripts/test_meta_learning.py
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
- research_synthesis
connected_python_files:
- dharma_swarm/meta_learning_prototype.py
- dharma_swarm/archive.py
- dharma_swarm/evolution.py
- scripts/test_meta_learning.py
connected_python_modules:
- dharma_swarm.meta_learning_prototype
- dharma_swarm.archive
- dharma_swarm.evolution
- scripts.test_meta_learning
connected_relevant_files:
- dharma_swarm/meta_learning_prototype.py
- dharma_swarm/archive.py
- dharma_swarm/evolution.py
- scripts/test_meta_learning.py
- docs/plans/ALLOUT_6H_MODE.md
improvement:
  room_for_improvement:
  - Strengthen cross-links to adjacent docs and implementing modules.
  - Separate durable knowledge from transient session context.
  - Add a tighter summary for first-pass retrieval.
  - Review whether this file should stay in `docs` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: documentation
  vault_path: docs/research/DARWIN_ENGINE_META_LEARNING_PROTOTYPE.md
  retrieval_terms:
  - darwin
  - engine
  - meta
  - learning
  - prototype
  - date
  - '2026'
  - status
  - minimal
  - rapid
  - validation
  - goal
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: working
  semantic_weight: 0.6
  coordination_comment: 'Date : 2026-03-10 Status : Minimal prototype for rapid validation Goal : Prove meta-learning concept works in <2 hours of coding'
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising docs/research/DARWIN_ENGINE_META_LEARNING_PROTOTYPE.md reinforces its salience without needing a separate message.
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
# Darwin Engine Meta-Learning Prototype

**Date**: 2026-03-10
**Status**: Minimal prototype for rapid validation
**Goal**: Prove meta-learning concept works in <2 hours of coding

---

## The 80/20 Prototype

**Core idea**: Instead of building the full meta-evolution infrastructure, create a **minimal working prototype** that proves the concept:

1. **Single meta-parameter**: Fitness weights (easiest to evolve, most impactful)
2. **Simple meta-fitness**: Just fitness trend gradient (no variance/final fitness weighting)
3. **Minimal mutation**: Dirichlet sampling only (no crossover)
4. **Fast validation**: 5 object cycles per meta-cycle (not 10)
5. **No persistence**: In-memory only (no meta-archive JSONL yet)

**Expected outcome**: Demonstrate that evolving fitness weights improves object-level performance.

---

## Prototype Code

### File: `dharma_swarm/meta_learning_prototype.py`

```python
"""Minimal meta-learning prototype for Darwin Engine.

Proves the concept: evolving fitness weights improves evolution performance.
"""

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
        """Run meta-learning experiment.

        Args:
            proposals: List of proposals for object-level evolution
            n_meta_cycles: Number of meta-cycles to run
            n_object_cycles: Number of object cycles per meta-cycle

        Returns:
            Dict with results: fitness trajectories, weight history, improvement
        """
        results = {
            "meta_cycles": [],
            "weight_history": [],
            "fitness_improvement": 0.0,
        }

        for meta_i in range(n_meta_cycles):
            print(f"\n=== Meta-Cycle {meta_i + 1}/{n_meta_cycles} ===")
            print(f"Current weights: {self._format_weights(self.fitness_weights)}")

            # Run object-level evolution
            fitness_trajectory = []
            for obj_i in range(n_object_cycles):
                # Inject current fitness weights into Darwin Engine
                # (This requires Darwin Engine to accept custom weights)
                cycle_result = await self.darwin.run_cycle(proposals)
                fitness_trajectory.append(cycle_result.best_fitness)
                print(f"  Object cycle {obj_i + 1}: fitness={cycle_result.best_fitness:.3f}")

            # Compute meta-fitness (fitness trend gradient)
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
            if meta_fitness < 0.0:  # Negative trend = declining fitness
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
        """Meta-fitness = gradient of fitness trend (positive = improving)."""
        if len(fitness_trajectory) < 2:
            return 0.0
        return float(np.mean(np.diff(fitness_trajectory)))

    def _evolve_weights(self) -> dict[str, float]:
        """Generate new weights via Dirichlet sampling + small mutation."""
        # Strategy 1: Sample from Dirichlet (generates valid probability distribution)
        n_dims = len(self.fitness_weights)
        new_weights_vec = np.random.dirichlet([1.0] * n_dims)

        # Map back to dict
        new_weights = dict(zip(self.fitness_weights.keys(), new_weights_vec))

        # Strategy 2: Small Gaussian mutation around current weights (alternative)
        # mutated = {}
        # for k, v in self.fitness_weights.items():
        #     mutated[k] = max(0.01, v + np.random.normal(0, 0.05))
        # total = sum(mutated.values())
        # new_weights = {k: v / total for k, v in mutated.items()}

        return new_weights

    @staticmethod
    def _format_weights(weights: dict[str, float]) -> str:
        """Format weights for pretty printing."""
        return ", ".join(f"{k[:3]}={v:.2f}" for k, v in weights.items())
```

---

## Integration: Minimal Changes to Darwin Engine

**Problem**: Darwin Engine currently uses hardcoded weights from `archive.py`:
```python
_DEFAULT_WEIGHTS: dict[str, float] = {
    "correctness": 0.20,
    ...
}
```

**Solution**: Add optional `custom_weights` parameter to `FitnessScore.weighted()`:

### In `dharma_swarm/archive.py`:

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

### In `dharma_swarm/evolution.py`:

```python
class DarwinEngine:
    def __init__(
        self,
        # ... existing params ...
        custom_fitness_weights: dict[str, float] | None = None,
    ):
        # ... existing init ...
        self._custom_fitness_weights = custom_fitness_weights

    async def evaluate(
        self,
        proposal: Proposal,
        # ... existing params ...
    ) -> Proposal:
        # ... existing code ...

        # When computing weighted fitness:
        weighted = fitness.weighted(weights=self._custom_fitness_weights)
        # Use this value for logging, comparisons, etc.
```

---

## Validation Experiment

### Test Script: `scripts/test_meta_learning.py`

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

    # Plot weight evolution (optional)
    print("\n=== Weight Evolution ===")
    for i, weights in enumerate(results['weight_history']):
        print(f"Meta-cycle {i}: {meta._format_weights(weights)}")


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Expected Outcomes

### Success Scenario (Meta-Learning Works)

```
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
```

**Interpretation**: Meta-learning discovered that increasing `correctness` and `dharmic_alignment` weights while decreasing `utilization` and `performance` led to better object-level fitness trends.

### Failure Scenario (Needs More Cycles or Better Strategy)

```
=== Meta-Cycle 1/3 ===
...
Meta-fitness (trend): -0.001
  → Fitness declining, evolving weights...

=== Meta-Cycle 2/3 ===
...
Meta-fitness (trend): -0.002
  → Fitness declining, evolving weights...

=== Meta-Cycle 3/3 ===
...
Meta-fitness (trend): -0.001
  → Fitness declining, evolving weights...

=== Meta-Learning Complete ===
Fitness improvement: -0.005
```

**Interpretation**: Random weight sampling didn't find better configuration. Need:
- More meta-cycles (5+ instead of 3)
- Smarter mutation (e.g., hill climbing around current weights)
- Better meta-fitness (include stability, not just trend)

---

## Validation Checklist

- [ ] Add `custom_weights` parameter to `FitnessScore.weighted()`
- [ ] Add `custom_fitness_weights` to `DarwinEngine.__init__`
- [ ] Inject custom weights in `evaluate()` method
- [ ] Create `meta_learning_prototype.py`
- [ ] Create `scripts/test_meta_learning.py`
- [ ] Run validation experiment: `python scripts/test_meta_learning.py`
- [ ] Verify: fitness improvement > 0 after 3 meta-cycles
- [ ] If failed: increase to 5 meta-cycles or improve mutation strategy

**Time estimate**: 1-2 hours coding + 30min testing

---

## Next Steps After Validation

**If prototype succeeds:**
1. Implement full `meta_evolution.py` from P0 spec
2. Add meta-archive persistence (JSONL)
3. Implement crossover (average best meta-configs)
4. Add meta-fitness components (variance, final fitness)
5. Scale to 10 meta-cycles, 10 object-cycles each

**If prototype fails:**
1. Debug: Are proposals diverse enough?
2. Debug: Is fitness actually changing across cycles?
3. Try: Gradient-based weight optimization instead of Dirichlet sampling
4. Try: Multi-armed bandit for weight space search
5. Analyze: What weights correlate with high fitness?

---

## Research Questions to Answer

1. **Do fitness weights matter?**
   - Measure: Fitness variance when using different random weight configs
   - Expected: >10% variance → weights matter

2. **Can meta-learning find better weights than defaults?**
   - Measure: Compare evolved weights vs default after 5 meta-cycles
   - Expected: >5% improvement → meta-learning works

3. **How many meta-cycles needed for convergence?**
   - Measure: Weight change magnitude over meta-cycles
   - Expected: Converges within 5-10 meta-cycles

4. **Do evolved weights transfer across tasks?**
   - Measure: Apply evolved weights from task A to task B
   - Expected: >50% of improvement transfers → generalizable

---

**JSCA!** Minimal prototype spec complete. Ready for 2-hour implementation sprint.
