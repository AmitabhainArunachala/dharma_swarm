# Fitness Landscape Analysis - DGC System

**Date**: 2026-03-08
**Purpose**: Complete mapping of fitness evaluation, benchmarks, and meta-evolution opportunities

---

## Current Fitness System

### 5-Dimensional Fitness (archive.py)

```python
class FitnessScore(BaseModel):
    correctness: float = 0.0      # Test pass rate (0-1)
    dharmic_alignment: float = 0.0 # Gate outcomes (0-1)
    elegance: float = 0.0         # Code quality (0-1)
    efficiency: float = 0.0       # Diff size penalty (0-1)
    safety: float = 0.0           # Gate pass/fail (0-1)
```

**Default weights**:
```python
{
    "correctness": 0.30,        # 30% - Does it work?
    "dharmic_alignment": 0.25,  # 25% - Does it align with telos?
    "elegance": 0.15,           # 15% - Is it beautiful?
    "efficiency": 0.15,         # 15% - Is it minimal?
    "safety": 0.15,             # 15% - Did gates pass?
}
```

**Weighted total**: `sum(dimension * weight) = [0.0, 1.0]`

### How Each Dimension is Measured

#### 1. Correctness (30%)
**Source**: Test execution results
```python
correctness = float(test_results.get("pass_rate", 0.0))
```

**Inputs**:
- `test_results["pass_rate"]` - Fraction of tests passing (0.0 to 1.0)
- If missing: defaults to 0.0

**Current limitation**: Binary pass/fail. No gradation for "mostly working" or "partial correctness".

#### 2. Dharmic Alignment (25%)
**Source**: Telos gate decisions
```python
if proposal.gate_decision == GateDecision.ALLOW.value:
    dharmic_alignment = 0.8
elif proposal.gate_decision == GateDecision.REVIEW.value:
    dharmic_alignment = 0.5
else:  # BLOCK
    dharmic_alignment = 0.0
```

**Inputs**:
- ALLOW → 0.8 (high alignment)
- REVIEW → 0.5 (medium, needs human review)
- BLOCK → 0.0 (misaligned)

**Current limitation**: Fixed thresholds (0.0, 0.5, 0.8). Doesn't account for *which* gates triggered or *how many* gates passed.

#### 3. Elegance (15%)
**Source**: AST-based code analysis (elegance.py)
```python
if code:
    elegance_score = evaluate_elegance(code)
    elegance = elegance_score.overall
else:
    elegance = 0.5  # Default
```

**Metrics** (from elegance.py):
- **Cyclomatic complexity**: Lower is better
- **Nesting depth**: Shallower is better
- **Line length**: Shorter is better
- **Naming quality**: Descriptive names
- **Docstring presence**: Documentation coverage

**Score formula**:
```python
overall = (
    (1.0 - complexity_penalty) * 0.4 +
    (1.0 - nesting_penalty) * 0.2 +
    (1.0 - length_penalty) * 0.2 +
    naming_score * 0.1 +
    docstring_score * 0.1
)
```

**Current limitation**: Only evaluates Python AST. Doesn't measure semantic elegance or architectural beauty.

#### 4. Efficiency (15%)
**Source**: Diff size
```python
diff_lines = len(proposal.diff.splitlines()) if proposal.diff else 0
efficiency = 1.0 - min(diff_lines / 1000.0, 1.0)
```

**Formula**:
- 0 lines → 1.0 (perfect)
- 500 lines → 0.5 (medium)
- 1000+ lines → 0.0 (inefficient)

**Current limitation**:
- Doesn't measure *runtime* efficiency (speed, memory)
- Penalizes large refactors even if they improve overall structure
- Should incorporate JIKOKU metrics (utilization, pramāda)

#### 5. Safety (15%)
**Source**: Gate pass/fail
```python
safety = 1.0 if proposal.status != EvolutionStatus.REJECTED else 0.0
```

**Formula**:
- Gates passed → 1.0
- Gates blocked → 0.0

**Safety floor**: If safety == 0.0, **entire fitness becomes 0.0** (regardless of other scores).

**Current limitation**: Binary. Doesn't distinguish between "barely passed" and "overwhelmingly safe".

---

## Benchmarks Across DGC System

### 1. JIKOKU Benchmarks (Just Added)

**Metrics**:
- **Wall clock time**: Total execution time (180ms current)
- **Utilization**: Concurrent operation density (226.6% current)
- **Pramāda (idle)**: Wasted time between operations (-126.6% current)
- **Category breakdown**: Time spent per operation type
- **Span durations**: Individual operation timing

**Stored**: `~/.dharma/jikoku/JIKOKU_LOG.jsonl`

**Kaizen reports**: Weekly continuous improvement analysis

**Status**: ✅ Production-ready, self-measuring

### 2. Evolution Archive Benchmarks

**Metrics**:
- **Fitness trend**: Weighted fitness over time
- **Success rate**: Proposals passed vs rejected
- **Component hotspots**: Most-evolved modules
- **Lineage depth**: Parent-child chains

**Stored**: `~/.dharma/evolution/archive.jsonl`

**Query**:
```python
await engine.get_fitness_trend(component="swarm.py")
# Returns: [(timestamp, fitness), ...]
```

**Status**: ✅ Working, but no automated reporting

### 3. Test Suite Benchmarks

**Metrics**:
- **Pass rate**: 1647/1647 tests passing (100%)
- **Coverage**: (Not currently measured)
- **Test duration**: ~36s for full suite
- **Regression detection**: pytest failures

**Run**: `python -m pytest tests/ -q`

**Status**: ✅ Stable baseline, no trend tracking

### 4. System Monitor Benchmarks (monitor.py)

**Anomaly detection**:
- **failure_spike**: Task failure rate > threshold
- **agent_silent**: Agent hasn't reported in > threshold
- **throughput_drop**: Task completion rate drops

**Health checks**:
```python
await swarm.health_check()
# Returns: {"status": "healthy", "anomalies": [...]}
```

**Status**: ✅ Code exists, rarely used in practice

### 5. Predictor Benchmarks (fitness_predictor.py)

**ML-based fitness prediction**:
- Learns from archive history
- Predicts fitness before execution
- Used for parent selection

**Metrics**:
- **Prediction accuracy**: (Not currently tracked)
- **Training data size**: Number of archived entries

**Status**: ⚠️ Exists but no validation metrics

### 6. Ecosystem Health (ecosystem_bridge.py)

**File-level benchmarks**:
- **Paths exist**: Which ecosystem paths are available
- **File counts**: Files per domain
- **Last modified**: Staleness detection

**Domains tracked**:
- Research (mech-interp, PSMV)
- Infrastructure (AGNI, trishula)
- Code (dharma_swarm, rvm-toolkit)

**Status**: ✅ Working, manual review

---

## What's Missing: Meta-Benchmarks

### 1. Fitness Function Performance

**Question**: How good are our fitness functions at predicting success?

**Metrics we should track**:
- **Correlation**: Does high fitness → successful code?
- **False positives**: High fitness but breaks in production
- **False negatives**: Low fitness but works great
- **Calibration**: Are scores accurate probabilities?

**Current state**: ❌ Not measured

**How to add**:
```python
class FitnessValidation(BaseModel):
    proposal_id: str
    predicted_fitness: float
    actual_outcome: bool  # Did it work in production?
    error_type: str | None  # If failed: "regression", "performance", etc.

# After deployment, record outcomes
await validator.record_outcome(
    proposal_id=entry.id,
    actual_outcome=production_success,
    error_type=error_type if not production_success else None
)

# Analyze fitness function accuracy
report = await validator.fitness_accuracy_report()
# {
#   "precision": 0.85,  # Of high-fitness proposals, how many succeeded?
#   "recall": 0.90,     # Of successful changes, how many had high fitness?
#   "f1_score": 0.875,
#   "calibration_error": 0.12  # How well do scores match probabilities?
# }
```

### 2. Weight Optimization

**Question**: Are the default weights (30% correctness, 25% dharmic, etc.) optimal?

**Current weights** (hardcoded):
```python
_DEFAULT_WEIGHTS = {
    "correctness": 0.30,
    "dharmic_alignment": 0.25,
    "elegance": 0.15,
    "efficiency": 0.15,
    "safety": 0.15,
}
```

**Opportunity**: Learn weights from outcomes

**Approach**:
```python
class AdaptiveWeights:
    """Learn fitness weights from production outcomes."""

    async def optimize_weights(
        self,
        validation_data: list[FitnessValidation],
        objective: str = "f1_score"
    ) -> dict[str, float]:
        """Find weights that maximize prediction accuracy.

        Uses grid search or gradient descent to find optimal
        weighting of fitness dimensions based on actual outcomes.
        """
        # Grid search over weight space
        best_weights = None
        best_score = 0.0

        for weights in self._generate_weight_candidates():
            # Recompute fitness with these weights
            predictions = [
                self._compute_fitness(v, weights) > 0.7
                for v in validation_data
            ]
            actuals = [v.actual_outcome for v in validation_data]

            # Measure prediction quality
            score = self._compute_metric(predictions, actuals, objective)

            if score > best_score:
                best_score = score
                best_weights = weights

        return best_weights
```

**Result**: Weights evolve based on what *actually* predicts success.

### 3. Dimension Evolution

**Question**: Should we add/remove fitness dimensions?

**Current dimensions**: Fixed set of 5

**Opportunities**:
- **Add JIKOKU metrics**: Utilization, pramāda as fitness dimensions
- **Add runtime performance**: Execution speed, memory usage
- **Add user satisfaction**: Does this change help users?
- **Remove low-signal dimensions**: If elegance never correlates with success, drop it

**Approach**:
```python
class DimensionRegistry:
    """Dynamic fitness dimension management."""

    def register_dimension(
        self,
        name: str,
        evaluator: Callable[[Proposal], float],
        initial_weight: float = 0.05
    ):
        """Add a new fitness dimension.

        Start with low weight (0.05), increase if it proves predictive.
        """
        self.dimensions[name] = {
            "evaluator": evaluator,
            "weight": initial_weight,
            "predictive_power": 0.0,  # Updated from validation data
        }

    async def prune_dimensions(self, threshold: float = 0.1):
        """Remove dimensions with low predictive power."""
        for name, dim in list(self.dimensions.items()):
            if dim["predictive_power"] < threshold:
                logger.info(f"Pruning dimension {name} (power={dim['predictive_power']:.3f})")
                del self.dimensions[name]
```

**Result**: Fitness function evolves to match what matters.

---

## Proposed: Meta-Evolution System

### Architecture

```
┌─────────────────────────────────────────────────────┐
│ Layer 1: CODE EVOLUTION (Current System)           │
│ - Proposals mutate code                             │
│ - Darwin engine evaluates fitness                   │
│ - Archive stores results                            │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│ Layer 2: FITNESS EVOLUTION (New System)             │
│ - Track production outcomes                         │
│ - Validate fitness predictions                      │
│ - Optimize weights & dimensions                     │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│ Layer 3: META-EVOLUTION (Future System)             │
│ - Evolve evaluation strategies themselves           │
│ - Test alternative fitness formulas                 │
│ - A/B test different weight sets                    │
└─────────────────────────────────────────────────────┘
```

### Implementation Plan

#### Phase 1: Validation Tracking (Week 1)

**Goal**: Start measuring fitness function accuracy

**Tasks**:
1. Create `FitnessValidation` model
2. Add `record_outcome()` to track production results
3. Build `fitness_accuracy_report()` analyzer
4. Generate weekly fitness calibration reports

**Output**: Know if current fitness function is accurate

#### Phase 2: Weight Optimization (Week 2)

**Goal**: Learn optimal weights from data

**Tasks**:
1. Implement `AdaptiveWeights.optimize_weights()`
2. Grid search over weight combinations
3. Compare optimized weights vs defaults
4. A/B test: half of proposals use learned weights

**Output**: Data-driven weight tuning

#### Phase 3: Dimension Evolution (Week 3-4)

**Goal**: Dynamic fitness dimensions

**Tasks**:
1. Create `DimensionRegistry` for pluggable dimensions
2. Add JIKOKU dimensions: `utilization_improvement`, `pramada_reduction`
3. Add runtime dimensions: `execution_speed`, `memory_efficiency`
4. Implement `prune_dimensions()` based on predictive power
5. Auto-discover correlations: which dimensions predict success?

**Output**: Fitness function adapts to what matters

#### Phase 4: Meta-Evolution (Week 5-8)

**Goal**: Evolve the evolution system itself

**Tasks**:
1. Treat fitness functions as evolvable code
2. Propose mutations to fitness evaluation logic
3. Evaluate meta-proposals: does this fitness function predict better?
4. Archive fitness function lineage
5. Select best-performing fitness functions

**Output**: Self-improving evaluation system

---

## JIKOKU Integration Opportunity

### Current Gap

**JIKOKU measures**:
- Wall clock time
- Utilization
- Pramāda (idle time)
- Operation categories

**Fitness doesn't use**:
- Any JIKOKU metrics

### Proposed Integration

Add two new fitness dimensions:

#### 1. Performance Improvement (10% weight)

```python
async def evaluate_performance_improvement(
    proposal: Proposal,
    baseline_session: str,
    test_session: str,
) -> float:
    """Measure performance impact using JIKOKU data.

    Returns:
        0.0 = Performance regression
        0.5 = No change
        1.0 = Significant speedup
    """
    tracer = get_global_tracer()

    # Get baseline metrics
    baseline_report = tracer.kaizen_report_for_session(baseline_session)
    baseline_wall_clock = baseline_report["wall_clock_sec"]

    # Get test metrics
    test_report = tracer.kaizen_report_for_session(test_session)
    test_wall_clock = test_report["wall_clock_sec"]

    # Compute speedup
    speedup = baseline_wall_clock / test_wall_clock

    # Map to [0, 1]
    if speedup < 0.9:  # Regression
        return 0.0
    elif speedup > 2.0:  # 2x speedup
        return 1.0
    else:  # Linear scale between
        return (speedup - 0.9) / 1.1
```

#### 2. Efficiency (Utilization) (10% weight)

```python
async def evaluate_utilization_improvement(
    proposal: Proposal,
    baseline_session: str,
    test_session: str,
) -> float:
    """Measure utilization impact using JIKOKU data.

    Returns:
        0.0 = Utilization decreased
        0.5 = No change
        1.0 = High concurrent execution
    """
    tracer = get_global_tracer()

    baseline_util = tracer.kaizen_report_for_session(baseline_session)["utilization_pct"]
    test_util = tracer.kaizen_report_for_session(test_session)["utilization_pct"]

    improvement = test_util - baseline_util

    # Map to [0, 1]
    if improvement < -20:  # Major regression
        return 0.0
    elif improvement > 100:  # Added parallelism
        return 1.0
    else:
        return 0.5 + (improvement / 200)
```

**New weight distribution**:
```python
{
    "correctness": 0.25,            # -5% (still most important)
    "dharmic_alignment": 0.20,      # -5%
    "performance": 0.15,            # NEW
    "utilization": 0.15,            # NEW
    "elegance": 0.10,               # -5%
    "efficiency": 0.10,             # -5%
    "safety": 0.05,                 # -10% (binary, less nuanced)
}
```

**Result**: Fitness now rewards performance improvements measured by JIKOKU.

---

## Concrete Next Steps

### Option A: Quick Win - Add JIKOKU to Fitness

**Effort**: 2-3 hours
**Impact**: Medium (immediate performance-aware evolution)

**Tasks**:
1. Add `performance_improvement` dimension
2. Add `utilization_improvement` dimension
3. Update `_DEFAULT_WEIGHTS` to include them
4. Run evolution cycle, verify JIKOKU metrics influence selection

### Option B: Foundation - Validation Tracking

**Effort**: 1-2 days
**Impact**: High (enables all future meta-evolution)

**Tasks**:
1. Create `FitnessValidation` model + storage
2. Add `record_outcome()` to track production results
3. Build validation report generator
4. Set up weekly cron to analyze fitness accuracy

### Option C: Full Meta-Evolution

**Effort**: 2-4 weeks
**Impact**: Transformational (self-improving fitness)

**Tasks**:
1. All of Option B
2. Implement adaptive weight learning
3. Add dynamic dimension registry
4. Build meta-evolution loop (fitness functions evolve)
5. A/B test learned vs default fitness

---

## Recommendation

**Start with Option A** (JIKOKU integration) because:
1. We just built JIKOKU - leverage it immediately
2. 2-3 hour implementation
3. Proves concept: fitness can evolve to include new signals
4. Creates immediate value: evolution now optimizes for performance

**Then Option B** (validation tracking) because:
5. Foundation for all meta-evolution
6. Answers critical question: "Are our fitness functions accurate?"
7. Enables data-driven weight tuning

**Finally Option C** when:
8. We have validation data (need Option B first)
9. We've proven JIKOKU integration works (Option A)
10. We're ready for true meta-evolution

---

## The Vision

**Current state**: Fixed fitness function evaluates evolving code

**Near future** (Option A): Fitness includes performance metrics

**Mid future** (Option B): Fitness weights adapt to outcomes

**End state** (Option C): **Fitness function itself evolves**

```
Generation 0: Default weights [0.30, 0.25, 0.15, 0.15, 0.15]
Generation 10: Learned weights [0.25, 0.20, 0.20, 0.20, 0.15]
Generation 50: New dimension added (user_satisfaction)
Generation 100: Elegance dimension pruned (low predictive power)
Generation 500: Fitness evaluation logic mutated (custom formula)
```

**The meta-loop**: Code evolves → Fitness measures code → Fitness itself evolves → Better code evolution

---

**JSCA! The fitness function can evolve just like the code it evaluates.**
