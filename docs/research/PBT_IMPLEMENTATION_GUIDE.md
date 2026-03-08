# Property-Based Testing Implementation Guide for Dharma Swarm

**Quick Start**: Get property-based testing running in dharma_swarm in 2-4 hours

---

## Phase 1: Hypothesis Setup (2 hours)

### Step 1: Install Dependencies

```bash
cd ~/dharma_swarm
pip install hypothesis hypothesis-jsonschema
echo "hypothesis>=6.90.0" >> requirements-dev.txt
```

### Step 2: Configure Hypothesis

```python
# tests/conftest.py (add to existing file)

from hypothesis import settings, Verbosity

# Configure Hypothesis defaults
settings.register_profile("ci", max_examples=100, verbosity=Verbosity.verbose)
settings.register_profile("dev", max_examples=20, verbosity=Verbosity.normal)
settings.register_profile("deep", max_examples=1000, deadline=None)

# Use dev profile by default, CI profile in GitHub Actions
import os
if os.getenv("CI"):
    settings.load_profile("ci")
else:
    settings.load_profile("dev")
```

### Step 3: Create Property Test Directory

```bash
mkdir -p tests/properties
touch tests/properties/__init__.py
```

### Step 4: Write First Property Test

```python
# tests/properties/test_proposal_properties.py

from hypothesis import given, strategies as st
from dharma_swarm.evolution import Proposal, EvolutionStatus

# Strategy for valid proposals
def proposal_strategy():
    return st.builds(
        Proposal,
        component=st.text(min_size=1, max_size=200, alphabet=st.characters(blacklist_categories=('Cs',))),
        change_type=st.sampled_from(["mutation", "crossover"]),
        description=st.text(min_size=10, max_size=1000),
        diff=st.text(max_size=5000),
    )

@given(proposal_strategy())
def test_proposal_always_has_valid_id(proposal):
    """Property: All proposals must have 16-character IDs."""
    assert len(proposal.id) == 16
    assert proposal.id.isalnum()

@given(proposal_strategy())
def test_proposal_initial_status_is_pending(proposal):
    """Property: New proposals always start in PENDING state."""
    assert proposal.status == EvolutionStatus.PENDING

@given(proposal_strategy())
def test_proposal_predicted_fitness_bounded(proposal):
    """Property: Predicted fitness must be in [0, 1]."""
    assert 0.0 <= proposal.predicted_fitness <= 1.0

@given(st.lists(proposal_strategy(), min_size=2, max_size=50))
def test_proposal_ids_unique(proposals):
    """Property: All proposal IDs must be unique."""
    ids = [p.id for p in proposals]
    assert len(ids) == len(set(ids)), "Found duplicate IDs"

@given(proposal_strategy())
def test_proposal_json_roundtrip(proposal):
    """Property: Serializing then deserializing preserves data."""
    json_str = proposal.model_dump_json()
    restored = Proposal.model_validate_json(json_str)

    assert restored.id == proposal.id
    assert restored.component == proposal.component
    assert restored.description == proposal.description
    assert restored.status == proposal.status
```

### Step 5: Run Tests

```bash
# Run just property tests
pytest tests/properties/ -v

# Run with more examples (thorough)
pytest tests/properties/ --hypothesis-profile=deep

# Run all tests including properties
pytest tests/ -v
```

**Expected Output**:
```
tests/properties/test_proposal_properties.py::test_proposal_always_has_valid_id PASSED [20%]
tests/properties/test_proposal_properties.py::test_proposal_initial_status_is_pending PASSED [40%]
tests/properties/test_proposal_properties.py::test_proposal_predicted_fitness_bounded PASSED [60%]
tests/properties/test_proposal_properties.py::test_proposal_ids_unique PASSED [80%]
tests/properties/test_proposal_properties.py::test_proposal_json_roundtrip PASSED [100%]

====== 5 passed in 2.3s ======
```

---

## Phase 2: Archive & Fitness Properties (1 hour)

```python
# tests/properties/test_archive_properties.py

from hypothesis import given, strategies as st
from dharma_swarm.archive import ArchiveEntry, FitnessScore, EvolutionArchive
import pytest

# Strategy for fitness scores
def fitness_strategy():
    return st.builds(
        FitnessScore,
        correctness=st.floats(min_value=0.0, max_value=1.0),
        elegance=st.floats(min_value=0.0, max_value=1.0),
        safety=st.floats(min_value=0.0, max_value=1.0),
        dharmic_alignment=st.floats(min_value=0.0, max_value=1.0),
        efficiency=st.floats(min_value=0.0, max_value=1.0),
    )

@given(fitness_strategy())
def test_fitness_weighted_always_bounded(fitness):
    """Property: Weighted fitness must be in [0, 1]."""
    weighted = fitness.weighted()
    assert 0.0 <= weighted <= 1.0, f"Weighted {weighted} outside bounds"

@given(st.builds(FitnessScore, safety=st.just(0.0)))
def test_zero_safety_means_zero_weighted(fitness):
    """Property: Safety=0 implies weighted fitness=0."""
    assert fitness.weighted() == 0.0

@given(fitness_strategy())
def test_fitness_json_roundtrip(fitness):
    """Property: Fitness serialization preserves values."""
    json_str = fitness.model_dump_json()
    restored = FitnessScore.model_validate_json(json_str)

    assert abs(restored.correctness - fitness.correctness) < 1e-9
    assert abs(restored.weighted() - fitness.weighted()) < 1e-9

# Strategy for archive entries
def archive_entry_strategy():
    return st.builds(
        ArchiveEntry,
        component=st.text(min_size=1, max_size=200),
        fitness=fitness_strategy(),
        status=st.sampled_from(["applied", "rejected", "pending"]),
        parent_id=st.one_of(st.none(), st.text(min_size=16, max_size=16)),
    )

@given(archive_entry_strategy())
def test_archive_entry_has_valid_id(entry):
    """Property: Archive entries have 16-char IDs."""
    assert len(entry.id) == 16

@given(st.lists(archive_entry_strategy(), min_size=1, max_size=20))
@pytest.mark.asyncio
async def test_archive_entries_unique_ids(entries, tmp_path):
    """Property: Archive never contains duplicate IDs."""
    archive = EvolutionArchive(tmp_path / "test.jsonl")
    await archive.init()

    for entry in entries:
        await archive.add_entry(entry)

    all_entries = await archive.get_all_entries()
    ids = [e.id for e in all_entries]
    assert len(ids) == len(set(ids))

@given(archive_entry_strategy())
@pytest.mark.asyncio
async def test_archive_roundtrip(entry, tmp_path):
    """Property: Storing then retrieving preserves entry."""
    archive = EvolutionArchive(tmp_path / "test.jsonl")
    await archive.init()

    await archive.add_entry(entry)
    retrieved = await archive.get_entry(entry.id)

    assert retrieved is not None
    assert retrieved.id == entry.id
    assert retrieved.component == entry.component
    assert abs(retrieved.fitness.weighted() - entry.fitness.weighted()) < 1e-6
```

---

## Phase 3: Gate Properties (1 hour)

```python
# tests/properties/test_gate_properties.py

from hypothesis import given, strategies as st, assume
from dharma_swarm.evolution import DarwinEngine, Proposal
from dharma_swarm.models import GateDecision
import pytest

# Strategies for harmful/safe content
harmful_words = ["rm -rf", "delete", "destroy", "kill", "drop database"]
safe_words = ["improve", "refactor", "optimize", "enhance", "fix"]

def harmful_proposal_strategy():
    return st.builds(
        Proposal,
        component=st.text(min_size=1, max_size=100),
        change_type=st.sampled_from(["mutation", "crossover"]),
        description=st.text(min_size=10, max_size=500).filter(
            lambda x: any(h in x.lower() for h in harmful_words)
        ),
    )

def safe_proposal_strategy():
    return st.builds(
        Proposal,
        component=st.text(min_size=1, max_size=100),
        change_type=st.sampled_from(["mutation", "crossover"]),
        description=st.sampled_from(safe_words) + st.text(min_size=5, max_size=200),
    )

@given(harmful_proposal_strategy())
@pytest.mark.asyncio
async def test_harmful_proposals_blocked(proposal, tmp_path):
    """Property: Proposals with harmful words should be blocked."""
    engine = DarwinEngine(
        archive_path=tmp_path / "archive.jsonl",
        traces_path=tmp_path / "traces",
        predictor_path=tmp_path / "predictor.jsonl",
    )
    await engine.init()

    result = await engine.gate_check(proposal)
    # May be BLOCK or REVIEW, but not ALLOW
    assert result.gate_decision in [GateDecision.BLOCK.value, GateDecision.REVIEW.value]

@given(safe_proposal_strategy())
@pytest.mark.asyncio
async def test_gate_determinism(proposal, tmp_path):
    """Property: Same proposal should get same gate decision twice."""
    from dharma_swarm.evolution import EvolutionStatus

    engine = DarwinEngine(
        archive_path=tmp_path / "archive.jsonl",
        traces_path=tmp_path / "traces",
        predictor_path=tmp_path / "predictor.jsonl",
    )
    await engine.init()

    result1 = await engine.gate_check(proposal)
    # Reset status for second check
    proposal.status = EvolutionStatus.PENDING
    result2 = await engine.gate_check(proposal)

    assert result1.gate_decision == result2.gate_decision
```

---

## Phase 4: Chaos Testing Setup (2 hours)

### Step 1: Create Chaos Test Marker

```python
# tests/conftest.py (add)

def pytest_configure(config):
    config.addinivalue_line(
        "markers", "chaos: mark test as chaos engineering test (slow)"
    )
```

### Step 2: Write Chaos Tests

```python
# tests/chaos/test_agent_resilience.py

import pytest
import asyncio
import random

@pytest.mark.chaos
@pytest.mark.asyncio
async def test_swarm_survives_random_agent_death():
    """Chaos: Kill 30% of agents mid-task, verify completion."""
    from dharma_swarm.swarm import SwarmManager
    from dharma_swarm.models import Task

    manager = SwarmManager()
    await manager.init()

    # Spawn 10 agents
    agents = []
    for i in range(10):
        agent = await manager.spawn_agent(role=f"worker_{i}")
        agents.append(agent)

    # Create long-running task
    task = Task(
        description="Complex analysis task that requires multiple steps",
        expected_output="Analysis complete",
    )

    # Start task
    future = asyncio.create_task(manager.execute_task(task))

    # Kill 3 random agents after 1 second
    await asyncio.sleep(1)
    for _ in range(3):
        victim = random.choice(agents)
        print(f"CHAOS: Killing agent {victim.id}")
        await manager.terminate_agent(victim.id)
        agents.remove(victim)

    # Task should still complete
    result = await future
    assert result.status in ["completed", "partial_success"]

@pytest.mark.chaos
@pytest.mark.asyncio
async def test_archive_survives_concurrent_writes(tmp_path):
    """Chaos: Concurrent writes should not corrupt archive."""
    from dharma_swarm.archive import EvolutionArchive, ArchiveEntry, FitnessScore

    archive = EvolutionArchive(tmp_path / "chaos.jsonl")
    await archive.init()

    # Spawn 10 concurrent writers
    async def write_entries(prefix):
        for i in range(10):
            entry = ArchiveEntry(
                component=f"{prefix}_{i}.py",
                fitness=FitnessScore(correctness=0.8),
                status="applied",
            )
            await archive.add_entry(entry)
            await asyncio.sleep(0.01)  # Small delay

    tasks = [write_entries(f"writer_{i}") for i in range(10)]
    await asyncio.gather(*tasks)

    # Verify all 100 entries present and unique
    all_entries = await archive.get_all_entries()
    assert len(all_entries) == 100
    ids = [e.id for e in all_entries]
    assert len(ids) == len(set(ids)), "Concurrent writes created duplicate IDs"
```

### Step 3: Run Chaos Tests

```bash
# Run only chaos tests
pytest tests/chaos/ -v -s

# Skip chaos tests in normal runs
pytest tests/ -v -m "not chaos"

# Run chaos tests weekly
pytest tests/chaos/ --hypothesis-profile=deep -v
```

---

## Phase 5: Fuzzing Setup (1-2 hours)

### Step 1: Install Atheris

```bash
pip install atheris
```

### Step 2: Create Fuzzing Harness

```python
# tests/fuzz/fuzz_archive_parsing.py

import atheris
import sys
import os

# Add parent to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from dharma_swarm.archive import EvolutionArchive

@atheris.instrument_func
def TestJSONLParsing(data):
    """Fuzz JSONL line parsing for crash bugs."""
    fdp = atheris.FuzzedDataProvider(data)

    # Generate fuzzy JSONL line
    line = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 2048))

    archive = EvolutionArchive("/tmp/fuzz_test.jsonl")

    try:
        # Try to parse line (should not crash)
        if line.strip():
            archive._parse_line(line)
    except (ValueError, KeyError, TypeError, AttributeError):
        # Expected errors are fine
        return -1
    except Exception as e:
        # Unexpected errors are bugs
        print(f"FUZZ BUG: {type(e).__name__}: {e}")
        raise

if __name__ == "__main__":
    atheris.Setup(sys.argv, TestJSONLParsing)
    atheris.Fuzz()
```

### Step 3: Run Fuzzing

```bash
# Run for 1 hour
python tests/fuzz/fuzz_archive_parsing.py -max_total_time=3600

# Run for 10,000 iterations
python tests/fuzz/fuzz_archive_parsing.py -runs=10000

# Run with address sanitizer (find memory bugs)
ASAN_OPTIONS=detect_leaks=1 python tests/fuzz/fuzz_archive_parsing.py -max_total_time=1800
```

### Step 4: Add to Nightly CI

```yaml
# .github/workflows/nightly.yml
name: Nightly Fuzzing

on:
  schedule:
    - cron: '0 2 * * *'  # 2 AM daily

jobs:
  fuzz:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install atheris
      - name: Run fuzzing
        run: |
          python tests/fuzz/fuzz_archive_parsing.py -max_total_time=3600
          python tests/fuzz/fuzz_gate_logic.py -max_total_time=3600
      - name: Upload crash artifacts
        if: failure()
        uses: actions/upload-artifact@v3
        with:
          name: fuzz-crashes
          path: tests/fuzz/crash-*
```

---

## Phase 6: Runtime Verification (1 hour)

```python
# dharma_swarm/runtime_verification.py

import functools
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)

class InvariantViolation(Exception):
    """Raised when a runtime invariant is violated."""
    pass

def runtime_invariant(
    check_func: Callable[..., bool],
    log_only: bool = True,
    error_message: str = ""
):
    """
    Decorator to check runtime invariants.

    Args:
        check_func: Function that returns True if invariant holds
        log_only: If True, log violations instead of raising
        error_message: Custom error message
    """
    @functools.wraps(check_func)
    def wrapper(*args, **kwargs):
        try:
            result = check_func(*args, **kwargs)
            if not result:
                msg = error_message or f"Invariant violated: {check_func.__name__}"
                if log_only:
                    logger.error(msg, extra={"args": args, "kwargs": kwargs})
                else:
                    raise InvariantViolation(msg)
        except Exception as e:
            logger.exception(f"Error checking invariant {check_func.__name__}: {e}")
            if not log_only:
                raise
    return wrapper

# Example usage in models.py
from dharma_swarm.runtime_verification import runtime_invariant

class FitnessScore(BaseModel):
    correctness: float
    elegance: float
    safety: float
    dharmic_alignment: float
    efficiency: float

    def weighted(self) -> float:
        result = (
            0.30 * self.correctness
            + 0.20 * self.elegance
            + 0.25 * self.safety
            + 0.15 * self.dharmic_alignment
            + 0.10 * self.efficiency
        )

        # Check invariant
        @runtime_invariant
        def check_bounds(score):
            return 0.0 <= score <= 1.0

        check_bounds(result)

        return max(0.0, min(1.0, result))
```

---

## Running the Full Verification Suite

### Daily (in CI)

```bash
# Run all tests including properties (fast profile)
pytest tests/ -v -m "not chaos"
```

### Weekly (deeper verification)

```bash
# Run with deep profile (1000 examples)
pytest tests/ --hypothesis-profile=deep -v

# Run chaos tests
pytest tests/chaos/ -v

# Run 4-hour fuzzing session
python tests/fuzz/fuzz_archive_parsing.py -max_total_time=14400
```

### On-Demand (debugging)

```bash
# Run specific property with verbose output
pytest tests/properties/test_proposal_properties.py::test_proposal_json_roundtrip -v --hypothesis-verbosity=verbose

# Reproduce a specific failure
pytest tests/properties/test_proposal_properties.py --hypothesis-seed=12345
```

---

## Measuring Success

### Metrics to Track

Add to `dharma_swarm/metrics.py`:

```python
class VerificationMetrics:
    """Track property-based testing effectiveness."""

    @staticmethod
    def log_pbt_discovery(test_name: str, bug_type: str, examples_to_find: int):
        """Log when property test finds a bug."""
        logger.info(
            f"PBT discovered {bug_type} in {test_name} after {examples_to_find} examples"
        )

    @staticmethod
    def log_fuzzing_coverage(corpus_size: int, edges_covered: int, crashes: int):
        """Log fuzzing progress."""
        logger.info(
            f"Fuzzing: corpus={corpus_size}, edges={edges_covered}, crashes={crashes}"
        )
```

### Weekly Report

```bash
# Count property tests
echo "Property tests: $(pytest tests/properties/ --collect-only | grep 'test' | wc -l)"

# Count chaos tests
echo "Chaos tests: $(pytest tests/chaos/ --collect-only | grep 'test' | wc -l)"

# Check for recent bugs found
grep "PBT discovered" ~/.dharma/verification.log | tail -20
```

---

## Common Pitfalls & Solutions

### Pitfall 1: Tests Too Slow

**Problem**: Property tests take 5+ minutes

**Solution**:
```python
# Reduce max_examples in dev mode
settings.register_profile("dev", max_examples=20)

# Or use hypothesis.seed for reproducible quick runs
@given(st.integers())
@settings(max_examples=10)
def test_fast(x):
    ...
```

### Pitfall 2: Flaky Tests

**Problem**: Property tests sometimes pass, sometimes fail

**Solution**:
```python
# Use hypothesis.seed to make tests deterministic
from hypothesis import seed

@seed(12345)
@given(st.integers())
def test_deterministic(x):
    ...
```

### Pitfall 3: Hard to Shrink

**Problem**: Hypothesis can't find minimal failing example

**Solution**:
```python
# Use simpler strategies
# BAD: st.text() (generates any Unicode)
# GOOD: st.text(alphabet=string.ascii_letters, max_size=100)

from hypothesis import strategies as st
import string

@given(st.text(alphabet=string.ascii_letters, min_size=1, max_size=100))
def test_with_simple_strategy(s):
    ...
```

---

## Next Steps

1. **Week 1**: Implement Phase 1 (Hypothesis for Proposal/Archive)
2. **Week 2**: Implement Phase 2 (Fitness properties) + Phase 3 (Gate properties)
3. **Week 3**: Implement Phase 4 (Chaos testing)
4. **Month 2**: Implement Phase 5 (Fuzzing) + Phase 6 (Runtime verification)
5. **Ongoing**: Add 2-3 new properties per module as you develop

**Expected Bug Finds**:
- Week 1: 3-5 edge cases in proposal/archive logic
- Week 2: 2-4 fitness calculation corner cases
- Week 3: 1-2 gate inconsistencies
- Month 2: 1-3 parser bugs from fuzzing

**Time Investment**: 8-12 hours initial, 1-2 hours/week ongoing

**ROI**: 15-25 bugs prevented in first 6 months (based on similar codebases)
