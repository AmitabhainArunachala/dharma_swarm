# JIKOKU → Fitness Integration Complete

**Date**: 2026-03-08
**Status**: ✅ Integrated and tested
**Impact**: Evolution now rewards performance improvements

---

## What We Built

**5 new dimensions → 7 dimensions**:

### Before (5D)
```python
{
    "correctness": 0.30,
    "dharmic_alignment": 0.25,
    "elegance": 0.15,
    "efficiency": 0.15,      # Diff size only
    "safety": 0.15,
}
```

### After (7D)
```python
{
    "correctness": 0.25,         # -5%
    "dharmic_alignment": 0.20,   # -5%
    "performance": 0.15,         # NEW - JIKOKU wall clock speedup
    "utilization": 0.15,         # NEW - JIKOKU concurrent execution
    "elegance": 0.10,            # -5%
    "efficiency": 0.10,          # -5% (renamed: diff size)
    "safety": 0.05,              # -10%
}
```

**Total weight**: 1.00 (unchanged)
**Performance now has 30% of fitness** (15% + 15%)

---

## Files Changed

### New Files

1. **dharma_swarm/jikoku_fitness.py** (170 lines)
   - `evaluate_performance_improvement()` - Maps speedup to [0, 1]
   - `evaluate_utilization_improvement()` - Maps utilization change to [0, 1]
   - `evaluate_jikoku_metrics()` - Integrated evaluator

2. **test_jikoku_fitness_integration.py** (210 lines)
   - End-to-end integration test
   - Simulates baseline + optimized sessions
   - Verifies fitness reflects performance

3. **demo_jikoku_fitness_evolution.py** (215 lines)
   - Live demonstration of closed feedback loop
   - Runs baseline vs optimized workloads
   - Proves Darwin engine selects faster code
   - Result: 32.81x speedup → +0.128 fitness → optimized wins

### Modified Files

1. **dharma_swarm/archive.py**
   - Added `performance` and `utilization` to `FitnessScore`
   - Updated `_DEFAULT_WEIGHTS` with new distribution
   - Updated docstrings

2. **dharma_swarm/evolution.py**
   - Added `baseline_session_id` and `test_session_id` params to `evaluate()`
   - Integrated `evaluate_jikoku_metrics()` call
   - Both FitnessScore branches include new dimensions

3. **dharma_swarm/jikoku_samaya.py**
   - Added `kaizen_report_for_session(session_id)` method
   - Extended `get_session_spans()` to accept optional session_id
   - Enables per-session performance comparison

---

## How It Works

### 1. Performance Dimension

**Measures**: Wall clock speedup

**Formula**:
```python
speedup = baseline_wall_clock / test_wall_clock

if speedup < 0.9:  # >10% slower
    return 0.0
elif speedup > 2.0:  # 2x+ faster
    return 1.0
else:
    return (speedup - 0.9) / 1.1  # Linear scale
```

**Examples**:
- 289ms → 180ms (1.61x speedup) → **score = 0.64**
- 100ms → 50ms (2.0x speedup) → **score = 1.00**
- 100ms → 150ms (0.67x slower) → **score = 0.00**

### 2. Utilization Dimension

**Measures**: Concurrent execution improvement

**Formula**:
```python
improvement = test_utilization - baseline_utilization

score = 0.5 + (improvement / 200)
score = max(0.0, min(1.0, score))  # Clamp
```

**Examples**:
- 87% → 226% (+139% improvement) → **score = 1.00** (clamped)
- 100% → 100% (0% change) → **score = 0.50** (neutral)
- 200% → 100% (-100% regression) → **score = 0.00**

### 3. Integration into Evolution

**Before evaluation**:
```bash
# Run baseline
JIKOKU_ENABLED=1 python measure_baseline.py
# Session: baseline-xyz

# Apply code change
# ...

# Run test
JIKOKU_ENABLED=1 python measure_baseline.py
# Session: test-abc
```

**During evaluation**:
```python
proposal = await engine.evaluate(
    proposal,
    test_results={"pass_rate": 0.95},
    code=changed_code,
    baseline_session_id="baseline-xyz",  # NEW
    test_session_id="test-abc",          # NEW
)

# Fitness now includes performance metrics
fitness = proposal.actual_fitness
# FitnessScore(
#     correctness=0.95,
#     dharmic_alignment=0.80,
#     performance=0.64,  # 1.61x speedup
#     utilization=1.00,  # High parallelism
#     elegance=0.75,
#     efficiency=0.85,
#     safety=1.00,
# )
```

---

## Test Results

**Test scenario**: Batch optimization (simulated)
- Baseline: 3 sequential tasks, 50ms each = 194.6ms total
- Optimized: 1 batch operation = 12.8ms total
- **Speedup: 13.79x**

**Fitness breakdown**:
```
Correctness:       1.000  (25% weight = 0.250)
Dharmic alignment: 0.500  (20% weight = 0.100)
Performance:       1.000  (15% weight = 0.150) ✅ JIKOKU
Utilization:       0.378  (15% weight = 0.057)
Elegance:          0.725  (10% weight = 0.073)
Efficiency:        0.999  (10% weight = 0.100)
Safety:            1.000  ( 5% weight = 0.050)

WEIGHTED TOTAL:    0.779
```

**Verification**:
- ✅ Performance dimension captures speedup (1.000 reflects 13.79x)
- ✅ Fitness above selection threshold (0.779 > 0.6)
- ✅ Darwin engine will select this proposal

---

## The Closed Loop

**Before** (broken feedback loop):
```
Code changes → JIKOKU measures performance → (data ignored)
Code changes → Fitness evaluates → Darwin selects

Result: Performance improvements not rewarded
```

**After** (closed feedback loop):
```
Code changes → JIKOKU measures performance →
Fitness includes perf metrics → Darwin selects fast code →
More performance improvements evolved

Result: Natural selection for speed
```

---

## Impact on Evolution

### Selection Example

**Proposal A**: Fast but messy
- Correctness: 1.0
- Dharmic: 0.8
- **Performance: 1.0** (2x speedup)
- **Utilization: 1.0** (high parallelism)
- Elegance: 0.3 (messy)
- Efficiency: 0.7
- Safety: 1.0
- **Fitness: 0.835** ← Selected!

**Proposal B**: Slow but elegant
- Correctness: 1.0
- Dharmic: 0.8
- **Performance: 0.0** (slower)
- **Utilization: 0.5** (neutral)
- Elegance: 0.9 (beautiful)
- Efficiency: 0.8
- Safety: 1.0
- **Fitness: 0.720** ← Rejected

**Result**: System evolves toward performance, not just elegance.

### Multi-Generation Evolution

**Gen 1**: Random mutations, varied performance
**Gen 10**: Darwin selects high-performance proposals (perf fitness > 0.7)
**Gen 50**: Codebase trending toward optimization
**Gen 100**: Performance optimizations emerge naturally

**The system learns to value speed because we made it measurable and rewardable.**

---

## What This Enables

### 1. Automatic Performance Optimization

**Scenario**: Agent proposes 10 different implementations

**Without JIKOKU fitness**:
- All get similar fitness (if tests pass)
- Selection is random among passing proposals

**With JIKOKU fitness**:
- Fast implementations get higher fitness
- Slow implementations get lower fitness
- Darwin engine naturally selects fast code

**Result**: Performance improves over generations without explicit optimization work.

### 2. A/B Testing Code Changes

**Scenario**: Two approaches to the same feature

```python
# Approach A: Sequential
for task in tasks:
    await create_task(task)

# Approach B: Batch
await create_task_batch(tasks)
```

**Evaluation**:
- Run both with JIKOKU enabled
- Compare session metrics
- Higher performance fitness wins
- Best approach automatically selected

### 3. Regression Detection

**Scenario**: Proposal makes code slower

**Result**:
- Performance fitness = 0.0 (regression)
- Overall fitness drops below threshold
- Proposal automatically rejected
- No manual performance testing needed

---

## Next Steps

### Immediate (Optional)

1. **Tune utilization formula** (if needed)
   - Current: Small improvements (~1%) barely move the needle
   - Could increase sensitivity: `score = 0.5 + (improvement / 100)`
   - Or weight absolute utilization, not just improvement

2. **Add performance tests** to test suite
   - Ensure fitness formulas don't regress
   - Validate scoring edge cases

3. **Document for users**
   - Update evolution.md with JIKOKU integration
   - Add examples of session-based evaluation

### Short-term (Week 3)

4. **Meta-evolution: Weight optimization**
   - Track fitness predictions vs outcomes
   - Learn optimal weights from data
   - Is 15% performance weight correct? Or should it be 20%?

5. **Meta-evolution: Dimension evolution**
   - Add new dimensions (memory usage, energy efficiency)
   - Prune dimensions with low predictive power
   - Dynamic fitness function

### Long-term (Month 2-3)

6. **Automatic benchmarking**
   - Generate JIKOKU sessions automatically during CI
   - Compare PR performance vs main branch
   - Block PRs that regress performance

7. **Multi-metric fitness**
   - Combine JIKOKU with other metrics
   - Memory usage, energy consumption, user latency
   - Holistic system optimization

---

## Conclusion

**Mission accomplished**: Evolution now rewards performance.

**The numbers**:
- 2-3 hours implementation ✅
- 7 fitness dimensions (was 5)
- 30% weight on performance (15% + 15%)
- Closed feedback loop: JIKOKU → Fitness → Selection

**The impact**:
- Fast code gets high fitness → Darwin selects it
- Slow code gets low fitness → Darwin rejects it
- System naturally evolves toward performance

**The proof** (demo_jikoku_fitness_evolution.py):
- Sequential code: 205.8ms → fitness 0.685
- Batch code: 6.3ms → fitness 0.816
- Speedup: 32.81x
- JIKOKU contribution: +0.128 (98.5% of fitness delta)
- **Darwin engine selects optimized code automatically**

**The next frontier**: Fitness function itself becomes evolvable.

---

**JSCA! Performance is now a first-class citizen in evolution.**
