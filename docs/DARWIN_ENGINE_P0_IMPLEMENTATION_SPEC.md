# Darwin Engine P0 Enhancements — Implementation Specification

**Date**: 2026-03-10
**Dependencies**: `DARWIN_ENGINE_PERPETUAL_EVOLUTION_RESEARCH.md`
**Status**: Ready for implementation

---

## Overview

This document provides **concrete implementation specifications** for the 4 P0 (blocking priority) enhancements to Darwin Engine:

1. **Meta-Learning**: Learn to learn (evolve evolution parameters)
2. **Exploration-Exploitation**: UCB1-style parent selection
3. **Anti-Convergence**: Detect plateaus and restart
4. **Landscape Navigation**: Map local basins and adapt strategy

Each section includes:
- Pydantic models
- Core algorithms (pseudocode → Python)
- Integration points with existing Darwin Engine
- Test specifications

---

## 1. Meta-Learning (Two-Level Evolution)

### Models

```python
# dharma_swarm/meta_evolution.py

from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field
from dharma_swarm.models import _new_id, _utc_now


class MetaParameters(BaseModel):
    """Evolution hyperparameters that can be evolved."""

    fitness_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "correctness": 0.20,
            "dharmic_alignment": 0.15,
            "performance": 0.12,
            "utilization": 0.12,
            "economic_value": 0.15,
            "elegance": 0.10,
            "efficiency": 0.10,
            "safety": 0.06,
        }
    )
    mutation_rate: float = 0.1
    exploration_coeff: float = 1.0
    circuit_breaker_limit: int = 3
    map_elites_n_bins: int = 5


class MetaEvolutionResult(BaseModel):
    """Result of a meta-evolution cycle."""

    id: str = Field(default_factory=_new_id)
    timestamp: str = Field(default_factory=lambda: _utc_now().isoformat())
    meta_parameters: MetaParameters
    object_cycles_completed: int = 0
    avg_fitness_trend: float = 0.0  # Gradient of fitness over time
    meta_fitness: float = 0.0  # How good these parameters are
    improvement_over_baseline: float = 0.0


class MetaArchiveEntry(BaseModel):
    """Archived meta-configuration with performance data."""

    id: str = Field(default_factory=_new_id)
    meta_parameters: MetaParameters
    meta_fitness: float
    n_object_cycles: int
    fitness_trajectory: list[float]
    created_at: str = Field(default_factory=lambda: _utc_now().isoformat())
```

### Core Algorithm

```python
# dharma_swarm/meta_evolution.py (continued)

import asyncio
import numpy as np
from dharma_swarm.evolution import DarwinEngine, CycleResult
from dharma_swarm.archive import EvolutionArchive


class MetaEvolutionEngine:
    """Two-level evolution: object-level (Darwin) + meta-level (this)."""

    def __init__(
        self,
        darwin_engine: DarwinEngine,
        meta_archive_path: Path | None = None,
        n_object_cycles_per_meta: int = 10,
    ):
        self.darwin = darwin_engine
        self.n_object_cycles = n_object_cycles_per_meta
        self.meta_params = MetaParameters()
        self.meta_archive_path = meta_archive_path or (
            Path.home() / ".dharma" / "evolution" / "meta_archive.jsonl"
        )
        self.meta_archive: list[MetaArchiveEntry] = []
        self._load_meta_archive()

    def _load_meta_archive(self):
        """Load historical meta-configurations."""
        if not self.meta_archive_path.exists():
            return
        with open(self.meta_archive_path) as f:
            for line in f:
                entry = MetaArchiveEntry.model_validate_json(line)
                self.meta_archive.append(entry)

    async def run_meta_cycle(self, proposals: list) -> MetaEvolutionResult:
        """Run N object cycles, then evolve meta-parameters."""
        # Phase 1: Object-level evolution
        fitness_trajectory = []
        for i in range(self.n_object_cycles):
            cycle_result: CycleResult = await self.darwin.run_cycle(proposals)
            fitness_trajectory.append(cycle_result.best_fitness)
            print(f"Object cycle {i+1}/{self.n_object_cycles}: fitness={cycle_result.best_fitness:.3f}")

        # Phase 2: Compute meta-fitness
        meta_fitness = self._compute_meta_fitness(fitness_trajectory)

        # Phase 3: Archive current meta-parameters
        meta_entry = MetaArchiveEntry(
            meta_parameters=self.meta_params,
            meta_fitness=meta_fitness,
            n_object_cycles=self.n_object_cycles,
            fitness_trajectory=fitness_trajectory,
        )
        self._archive_meta_entry(meta_entry)

        # Phase 4: Evolve meta-parameters if needed
        if meta_fitness < 0.5:  # Poor performance
            print(f"Meta-fitness low ({meta_fitness:.3f}), evolving meta-parameters...")
            self.meta_params = await self._evolve_meta_params()

        # Return result
        avg_trend = np.mean(np.diff(fitness_trajectory)) if len(fitness_trajectory) > 1 else 0.0
        return MetaEvolutionResult(
            meta_parameters=self.meta_params,
            object_cycles_completed=self.n_object_cycles,
            avg_fitness_trend=avg_trend,
            meta_fitness=meta_fitness,
        )

    def _compute_meta_fitness(self, fitness_trajectory: list[float]) -> float:
        """Meta-fitness = how well object-level fitness improved."""
        if len(fitness_trajectory) < 2:
            return 0.5  # Neutral

        # Gradient of fitness trend (positive = improving)
        gradient = np.mean(np.diff(fitness_trajectory))

        # Variance (lower = more stable)
        variance = np.var(fitness_trajectory)

        # Final fitness (higher = better)
        final = fitness_trajectory[-1]

        # Weighted combination
        meta_fitness = (
            0.5 * (gradient + 0.1) +  # Normalized gradient
            0.3 * final +  # Final performance
            0.2 * (1.0 - min(variance, 1.0))  # Stability
        )
        return max(0.0, min(1.0, meta_fitness))

    async def _evolve_meta_params(self) -> MetaParameters:
        """Generate new meta-parameters via mutation or crossover."""
        if len(self.meta_archive) == 0:
            # No history, mutate current
            return self._mutate_meta_params(self.meta_params)

        # Select best meta-configs from archive
        best_entries = sorted(
            self.meta_archive,
            key=lambda e: e.meta_fitness,
            reverse=True
        )[:3]

        # Crossover best configs
        new_params = self._crossover_meta_params([e.meta_parameters for e in best_entries])
        return new_params

    def _mutate_meta_params(self, params: MetaParameters) -> MetaParameters:
        """Mutate meta-parameters with small Gaussian noise."""
        new_weights = {}
        for k, v in params.fitness_weights.items():
            # Add Gaussian noise, then renormalize
            new_weights[k] = max(0.01, v + np.random.normal(0, 0.05))

        # Renormalize to sum to 1.0
        total = sum(new_weights.values())
        new_weights = {k: v / total for k, v in new_weights.items()}

        return MetaParameters(
            fitness_weights=new_weights,
            mutation_rate=max(0.01, params.mutation_rate * np.random.uniform(0.8, 1.2)),
            exploration_coeff=max(0.1, params.exploration_coeff * np.random.uniform(0.8, 1.2)),
            circuit_breaker_limit=max(1, int(params.circuit_breaker_limit + np.random.randint(-1, 2))),
            map_elites_n_bins=max(3, int(params.map_elites_n_bins + np.random.randint(-1, 2))),
        )

    def _crossover_meta_params(self, parent_params: list[MetaParameters]) -> MetaParameters:
        """Crossover multiple meta-parameter sets."""
        # Average fitness weights from all parents
        avg_weights = {}
        for key in parent_params[0].fitness_weights:
            avg_weights[key] = np.mean([p.fitness_weights[key] for p in parent_params])

        # Average other params
        avg_mutation_rate = np.mean([p.mutation_rate for p in parent_params])
        avg_exploration = np.mean([p.exploration_coeff for p in parent_params])
        avg_breaker = int(np.mean([p.circuit_breaker_limit for p in parent_params]))
        avg_bins = int(np.mean([p.map_elites_n_bins for p in parent_params]))

        return MetaParameters(
            fitness_weights=avg_weights,
            mutation_rate=avg_mutation_rate,
            exploration_coeff=avg_exploration,
            circuit_breaker_limit=avg_breaker,
            map_elites_n_bins=avg_bins,
        )

    def _archive_meta_entry(self, entry: MetaArchiveEntry):
        """Append to meta-archive JSONL."""
        self.meta_archive.append(entry)
        self.meta_archive_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.meta_archive_path, "a") as f:
            f.write(entry.model_dump_json() + "\n")
```

### Integration Points

**Where to hook into Darwin Engine:**

1. **Fitness weight injection**:
   ```python
   # In evolution.py evaluate() method, pass meta_params.fitness_weights
   fitness = FitnessScore(...)
   weighted_fitness = fitness.weighted(weights=self.meta_params.fitness_weights)
   ```

2. **Mutation rate injection**:
   ```python
   # In evolution.py propose() method
   diff_magnitude = self.meta_params.mutation_rate
   ```

3. **Circuit breaker injection**:
   ```python
   # In evolution.py __init__
   self._circuit_breaker_limit = meta_params.circuit_breaker_limit
   ```

### Test Specification

```python
# tests/test_meta_evolution.py

import pytest
from dharma_swarm.meta_evolution import MetaEvolutionEngine, MetaParameters
from dharma_swarm.evolution import DarwinEngine

@pytest.mark.asyncio
async def test_meta_cycle_improves_parameters():
    """Test that meta-evolution can find better parameters."""
    darwin = DarwinEngine()
    await darwin.init()

    meta = MetaEvolutionEngine(darwin, n_object_cycles_per_meta=5)

    # Run baseline
    initial_params = meta.meta_params
    result1 = await meta.run_meta_cycle([])

    # Run again (should adapt if poor performance)
    result2 = await meta.run_meta_cycle([])

    # Verify parameters changed if meta_fitness was low
    if result1.meta_fitness < 0.5:
        assert meta.meta_params != initial_params

@pytest.mark.asyncio
async def test_meta_fitness_correlates_with_trend():
    """Test that positive fitness trends → high meta-fitness."""
    meta = MetaEvolutionEngine(DarwinEngine())

    # Positive trend
    fitness_up = [0.1, 0.2, 0.3, 0.4, 0.5]
    meta_fitness_up = meta._compute_meta_fitness(fitness_up)

    # Negative trend
    fitness_down = [0.5, 0.4, 0.3, 0.2, 0.1]
    meta_fitness_down = meta._compute_meta_fitness(fitness_down)

    assert meta_fitness_up > meta_fitness_down
```

---

## 2. Exploration-Exploitation (UCB1 Parent Selection)

### Models

```python
# dharma_swarm/ucb_selector.py

from __future__ import annotations
import math
from pydantic import BaseModel, Field
from dharma_swarm.archive import ArchiveEntry, EvolutionArchive


class UCBConfig(BaseModel):
    """Configuration for UCB parent selection."""

    exploration_coeff: float = 1.0  # Higher = more exploration
    min_pulls: int = 1  # Minimum times each parent must be tried
    annealing_rate: float = 0.99  # Decay exploration over time


class UCBState(BaseModel):
    """Tracks UCB state across cycles."""

    total_pulls: int = 0
    child_counts: dict[str, int] = Field(default_factory=dict)
    exploration_coeff: float = 1.0
```

### Core Algorithm

```python
# dharma_swarm/ucb_selector.py (continued)

class UCBParentSelector:
    """UCB1-style parent selection with exploration-exploitation balance."""

    def __init__(self, config: UCBConfig | None = None):
        self.config = config or UCBConfig()
        self.state = UCBState(exploration_coeff=self.config.exploration_coeff)

    async def select_parent(self, archive: EvolutionArchive) -> ArchiveEntry | None:
        """Select parent using UCB1 formula."""
        entries = await archive.list_entries(status="applied")
        if not entries:
            return None

        # Force minimum exploration of all parents
        unexplored = [
            e for e in entries
            if self.state.child_counts.get(e.id, 0) < self.config.min_pulls
        ]
        if unexplored:
            return unexplored[0]

        # Compute UCB scores
        scores = []
        for entry in entries:
            score = self._compute_ucb_score(entry)
            scores.append((entry, score))

        # Select max UCB
        best_entry, best_score = max(scores, key=lambda x: x[1])

        # Update state
        self.state.child_counts[best_entry.id] = (
            self.state.child_counts.get(best_entry.id, 0) + 1
        )
        self.state.total_pulls += 1

        # Anneal exploration
        self.state.exploration_coeff *= self.config.annealing_rate

        return best_entry

    def _compute_ucb_score(self, entry: ArchiveEntry) -> float:
        """UCB1 formula: mean + sqrt(2 * ln(N) / n_i)."""
        mean_fitness = entry.fitness.weighted()
        n_i = self.state.child_counts.get(entry.id, 1)
        N = max(self.state.total_pulls, 1)

        exploration_bonus = math.sqrt(2 * math.log(N) / n_i)
        ucb_score = mean_fitness + self.state.exploration_coeff * exploration_bonus

        return ucb_score

    def get_exploration_ratio(self) -> float:
        """Compute current exploration vs exploitation ratio."""
        if self.state.total_pulls == 0:
            return 0.5
        # % of pulls from low-fitness parents (bottom 50%)
        # This is a proxy for exploration
        return self.state.exploration_coeff
```

### Integration

**In `evolution.py`, replace `select_parent()` call:**

```python
# Old
parent = await select_parent(self.archive, strategy="tournament")

# New
if self.use_ucb:
    parent = await self.ucb_selector.select_parent(self.archive)
else:
    parent = await select_parent(self.archive, strategy="tournament")
```

### Test Specification

```python
# tests/test_ucb_selector.py

import pytest
from dharma_swarm.ucb_selector import UCBParentSelector, UCBConfig
from dharma_swarm.archive import EvolutionArchive, ArchiveEntry, FitnessScore

@pytest.mark.asyncio
async def test_ucb_explores_all_parents():
    """Test that UCB selector explores all parents before exploiting."""
    archive = EvolutionArchive()
    await archive.load()

    # Add 3 parents with different fitness
    for i, fitness_val in enumerate([0.1, 0.5, 0.9]):
        entry = ArchiveEntry(
            component="test.py",
            change_type="mutation",
            description=f"Parent {i}",
            fitness=FitnessScore(correctness=fitness_val),
            status="applied",
        )
        await archive.add_entry(entry)

    selector = UCBParentSelector(UCBConfig(min_pulls=2))

    # First 6 selections should hit each parent at least 2x
    selected_ids = set()
    for _ in range(6):
        parent = await selector.select_parent(archive)
        selected_ids.add(parent.id)

    assert len(selected_ids) == 3  # All 3 parents explored

@pytest.mark.asyncio
async def test_ucb_anneals_exploration():
    """Test that exploration coefficient decays over time."""
    selector = UCBParentSelector(UCBConfig(annealing_rate=0.9))
    initial_coeff = selector.state.exploration_coeff

    # Simulate 10 selections
    for _ in range(10):
        selector.state.total_pulls += 1
        selector.state.exploration_coeff *= selector.config.annealing_rate

    assert selector.state.exploration_coeff < initial_coeff
```

---

## 3. Anti-Convergence (Plateau Detection + Restart)

### Models

```python
# dharma_swarm/convergence.py

from __future__ import annotations
from pydantic import BaseModel, Field


class ConvergenceConfig(BaseModel):
    """Configuration for convergence detection."""

    window_size: int = 20  # Check last N cycles
    variance_threshold: float = 0.01  # Low variance = converged
    improvement_threshold: float = 0.05  # Min improvement to avoid plateau
    restart_mutation_multiplier: float = 2.0  # Increase mutation rate
    restart_duration: int = 10  # Cycles before reverting


class ConvergenceState(BaseModel):
    """Tracks convergence state."""

    fitness_history: list[float] = Field(default_factory=list)
    converged: bool = False
    plateau_detected: bool = False
    restart_cycles_remaining: int = 0
```

### Core Algorithm

```python
# dharma_swarm/convergence.py (continued)

import numpy as np


class ConvergenceDetector:
    """Detects when evolution has plateaued and triggers restart."""

    def __init__(self, config: ConvergenceConfig | None = None):
        self.config = config or ConvergenceConfig()
        self.state = ConvergenceState()

    def update(self, best_fitness: float) -> bool:
        """Update fitness history and check for convergence.

        Returns:
            True if restart triggered, False otherwise.
        """
        self.state.fitness_history.append(best_fitness)

        # Only check after enough data
        if len(self.state.fitness_history) < self.config.window_size:
            return False

        # Check variance (convergence)
        recent = self.state.fitness_history[-self.config.window_size:]
        variance = float(np.var(recent))
        self.state.converged = variance < self.config.variance_threshold

        # Check improvement (plateau)
        if len(self.state.fitness_history) > self.config.window_size:
            before_window = self.state.fitness_history[:-self.config.window_size]
            best_before = max(before_window) if before_window else 0.0
            best_recent = max(recent)
            improvement = best_recent - best_before
            self.state.plateau_detected = improvement < self.config.improvement_threshold
        else:
            self.state.plateau_detected = False

        # Trigger restart if both conditions met
        if self.state.converged and self.state.plateau_detected:
            print(f"Convergence detected: variance={variance:.4f}, improvement={improvement:.4f}")
            self.state.restart_cycles_remaining = self.config.restart_duration
            return True

        return False

    def should_use_restart_params(self) -> bool:
        """Returns True if currently in restart mode."""
        if self.state.restart_cycles_remaining > 0:
            self.state.restart_cycles_remaining -= 1
            return True
        return False

    def get_restart_mutation_rate(self, base_rate: float) -> float:
        """Returns amplified mutation rate during restart."""
        if self.should_use_restart_params():
            return base_rate * self.config.restart_mutation_multiplier
        return base_rate
```

### Integration

**In `evolution.py` run_cycle:**

```python
# After each cycle
convergence_triggered = self.convergence_detector.update(result.best_fitness)

if convergence_triggered:
    logger.info("Convergence detected, triggering restart strategies")
    # Inject random proposals
    await self._inject_random_proposals(n=10)

# Adjust mutation rate
if self.convergence_detector.should_use_restart_params():
    self.meta_params.mutation_rate = self.convergence_detector.get_restart_mutation_rate(
        self.meta_params.mutation_rate
    )
```

### Test Specification

```python
# tests/test_convergence.py

import pytest
from dharma_swarm.convergence import ConvergenceDetector, ConvergenceConfig

def test_detects_low_variance_convergence():
    """Test that low variance triggers convergence."""
    detector = ConvergenceDetector(ConvergenceConfig(
        window_size=10,
        variance_threshold=0.01,
        improvement_threshold=0.05,
    ))

    # Flat fitness (converged)
    for _ in range(15):
        detector.update(0.5)

    assert detector.state.converged

def test_detects_plateau():
    """Test that lack of improvement triggers plateau detection."""
    detector = ConvergenceDetector(ConvergenceConfig(
        window_size=10,
        improvement_threshold=0.05,
    ))

    # Steady fitness (no improvement)
    for i in range(25):
        detector.update(0.5 + 0.001 * i)  # Tiny improvement

    assert detector.state.plateau_detected

def test_restart_triggered():
    """Test that convergence + plateau triggers restart."""
    detector = ConvergenceDetector()

    # Converged + plateau
    for _ in range(30):
        triggered = detector.update(0.5)

    assert triggered
    assert detector.state.restart_cycles_remaining > 0
```

---

## 4. Landscape Navigation (Local Basin Mapping)

### Models

```python
# dharma_swarm/landscape.py

from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field
from dharma_swarm.archive import ArchiveEntry


class BasinType(str, Enum):
    """Types of fitness landscape basins."""

    ASCENDING = "ascending"  # On a slope, fitness improving
    PLATEAU = "plateau"  # Flat region, low variance
    DESCENDING = "descending"  # Wrong direction
    LOCAL_OPTIMUM = "local_optimum"  # Peak, nowhere to go
    UNKNOWN = "unknown"


class LandscapeProbe(BaseModel):
    """Result of sampling fitness landscape around a point."""

    parent_id: str
    parent_fitness: float
    neighbor_fitness: list[float]
    gradient: float  # Average improvement
    variance: float  # Spread of neighbors
    basin_type: BasinType
```

### Core Algorithm

```python
# dharma_swarm/landscape.py (continued)

import numpy as np
from dharma_swarm.evolution import DarwinEngine


class FitnessLandscapeMapper:
    """Maps local fitness landscape structure."""

    def __init__(
        self,
        darwin: DarwinEngine,
        n_samples: int = 10,
        gradient_threshold: float = 0.1,
        variance_threshold: float = 0.01,
    ):
        self.darwin = darwin
        self.n_samples = n_samples
        self.gradient_threshold = gradient_threshold
        self.variance_threshold = variance_threshold

    async def probe_landscape(self, parent: ArchiveEntry) -> LandscapeProbe:
        """Sample neighbors and classify basin type."""
        # Sample N small mutations
        neighbor_fitness = []
        for _ in range(self.n_samples):
            # Generate small perturbation (not implemented here, assume method exists)
            # In real impl, would call darwin.propose() with small diff
            perturbed_fitness = await self._sample_neighbor_fitness(parent)
            neighbor_fitness.append(perturbed_fitness)

        # Compute gradient
        parent_fitness = parent.fitness.weighted()
        fitness_deltas = [f - parent_fitness for f in neighbor_fitness]
        gradient = float(np.mean(fitness_deltas))
        variance = float(np.var(neighbor_fitness))

        # Classify basin
        basin_type = self._classify_basin(gradient, variance)

        return LandscapeProbe(
            parent_id=parent.id,
            parent_fitness=parent_fitness,
            neighbor_fitness=neighbor_fitness,
            gradient=gradient,
            variance=variance,
            basin_type=basin_type,
        )

    def _classify_basin(self, gradient: float, variance: float) -> BasinType:
        """Classify basin based on gradient and variance."""
        if gradient > self.gradient_threshold:
            return BasinType.ASCENDING
        elif variance < self.variance_threshold:
            return BasinType.PLATEAU
        elif gradient < -self.gradient_threshold:
            return BasinType.DESCENDING
        else:
            return BasinType.LOCAL_OPTIMUM

    async def _sample_neighbor_fitness(self, parent: ArchiveEntry) -> float:
        """Generate small mutation and evaluate fitness.

        This is a stub - real implementation would:
        1. Generate small diff perturbation
        2. Apply to code
        3. Evaluate fitness
        4. Return weighted fitness
        """
        # Placeholder: random walk around parent fitness
        return parent.fitness.weighted() + np.random.normal(0, 0.05)

    def get_adaptive_strategy(self, basin_type: BasinType) -> str:
        """Recommend strategy based on basin type."""
        strategies = {
            BasinType.ASCENDING: "exploit",  # Hill climb with small mutations
            BasinType.PLATEAU: "explore",  # Jump out with large mutations
            BasinType.LOCAL_OPTIMUM: "restart",  # Long jump or restart
            BasinType.DESCENDING: "backtrack",  # Return to previous parent
            BasinType.UNKNOWN: "explore",
        }
        return strategies.get(basin_type, "explore")
```

### Integration

**In `evolution.py`, periodically probe landscape:**

```python
# After selecting parent, probe landscape
if self.cycle_count % 10 == 0:  # Probe every 10 cycles
    probe = await self.landscape_mapper.probe_landscape(parent)
    strategy = self.landscape_mapper.get_adaptive_strategy(probe.basin_type)

    # Adjust mutation rate based on strategy
    if strategy == "exploit":
        self.meta_params.mutation_rate *= 0.8  # Smaller mutations
    elif strategy == "explore":
        self.meta_params.mutation_rate *= 1.5  # Larger mutations
    elif strategy == "restart":
        await self.convergence_detector.trigger_restart()
```

### Test Specification

```python
# tests/test_landscape.py

import pytest
from dharma_swarm.landscape import FitnessLandscapeMapper, BasinType
from dharma_swarm.archive import ArchiveEntry, FitnessScore
from dharma_swarm.evolution import DarwinEngine

@pytest.mark.asyncio
async def test_ascending_basin_detected():
    """Test that improving neighbors → ascending basin."""
    darwin = DarwinEngine()
    mapper = FitnessLandscapeMapper(darwin)

    parent = ArchiveEntry(
        component="test.py",
        change_type="mutation",
        description="test",
        fitness=FitnessScore(correctness=0.5),
    )

    # Mock _sample_neighbor_fitness to return improving values
    async def mock_sample(p):
        return 0.6 + np.random.normal(0, 0.05)

    mapper._sample_neighbor_fitness = mock_sample

    probe = await mapper.probe_landscape(parent)
    assert probe.basin_type == BasinType.ASCENDING

@pytest.mark.asyncio
async def test_plateau_basin_detected():
    """Test that flat neighbors → plateau basin."""
    darwin = DarwinEngine()
    mapper = FitnessLandscapeMapper(darwin, variance_threshold=0.01)

    parent = ArchiveEntry(
        component="test.py",
        change_type="mutation",
        description="test",
        fitness=FitnessScore(correctness=0.5),
    )

    # Mock to return flat values
    async def mock_sample(p):
        return 0.5 + np.random.normal(0, 0.001)

    mapper._sample_neighbor_fitness = mock_sample

    probe = await mapper.probe_landscape(parent)
    assert probe.basin_type == BasinType.PLATEAU
```

---

## Integration Checklist

### Phase 1: Meta-Learning
- [ ] Add `meta_evolution.py` module
- [ ] Add `MetaParameters` to `DarwinEngine.__init__`
- [ ] Inject `meta_params.fitness_weights` into `evaluate()`
- [ ] Add `run_meta_cycle` CLI command
- [ ] Write 5 unit tests
- [ ] Run 100-cycle stress test

### Phase 2: Exploration-Exploitation
- [ ] Add `ucb_selector.py` module
- [ ] Add `use_ucb` flag to `DarwinEngine`
- [ ] Replace `select_parent()` call with UCB selector
- [ ] Add exploration metrics to `CycleResult`
- [ ] Write 5 unit tests
- [ ] A/B test vs baseline on 50-cycle run

### Phase 3: Anti-Convergence
- [ ] Add `convergence.py` module
- [ ] Add `ConvergenceDetector` to `DarwinEngine`
- [ ] Call `update()` after each cycle
- [ ] Implement restart triggers (mutation rate, random injection)
- [ ] Write 5 unit tests
- [ ] Verify restart effectiveness on plateau benchmark

### Phase 4: Landscape Navigation
- [ ] Add `landscape.py` module
- [ ] Add `FitnessLandscapeMapper` to `DarwinEngine`
- [ ] Call `probe_landscape()` every N cycles
- [ ] Implement adaptive strategy switching
- [ ] Write 5 unit tests
- [ ] Measure gradient correlation with success rate

---

## Success Criteria

**Meta-Learning**:
- Meta-fitness improves over 10 meta-cycles
- Fitness weights converge to non-default values
- 2+ meta-parameters show >10% change

**Exploration-Exploitation**:
- Exploration ratio decays from 0.8 → 0.2 over 50 cycles
- UCB selector outperforms tournament by >5% on fitness
- All archive entries sampled at least once in 100 cycles

**Anti-Convergence**:
- Detects plateau within 5 cycles of variance drop
- Restart increases fitness within 10 cycles
- System completes 100 cycles without permanent plateau

**Landscape Navigation**:
- Basin classification accuracy >80% (vs manual labels)
- Adaptive strategy reduces time-to-local-optimum by >20%
- Gradient estimates correlate >0.5 with actual fitness improvement

---

**JSCA!** P0 implementation spec complete. Ready for Phase 1 coding.
