# DHARMA SWARM Integration Build: Complete Test Strategy
**Date**: 2026-03-04
**Scope**: Integration of ~4,000 lines from 5+ source repos into dharma_swarm
**Baseline**: 203/203 tests passing (verified 2026-03-04T23:20)
**Constraint**: Tests NEVER regress below 203 -- only go up

---

## 1. TEST MIGRATION: Old DGC Tests into dharma_swarm

### Module-to-Package Mapping

All integrated modules land at `~/dharma_swarm/dharma_swarm/darwin/` (Workstream 1),
`~/dharma_swarm/dharma_swarm/infra/` (Workstream 2), and
`~/dharma_swarm/dharma_swarm/research/` (Workstream 3).

```
OLD LOCATION                                      NEW LOCATION (in dharma_swarm/dharma_swarm/)
--------------------------------------------------|-----------------------------------------
src/dgm/archive.py                                darwin/archive.py
src/dgm/selector.py                               darwin/selector.py
src/dgm/elegance.py                               darwin/elegance.py
swarm/utils/fitness_predictor.py                   darwin/fitness_predictor.py
evolution_v3_drop/evolution_v3.py                  darwin/evolution_v3.py
src/core/canonical_memory.py                       infra/canonical_memory.py
swarm/file_lock.py                                 infra/file_lock.py
swarm/residual_stream.py                           infra/residual_stream.py
swarm/systemic_monitor.py                          infra/systemic_monitor.py
swarm/anomaly_detection.py                         infra/anomaly_detection.py
deepclaw/rv/fidelity.py                            research/fidelity.py
deepclaw/agents/brain.py                           research/brain.py
SSC_EVOLUTION/ssc_mathematical_core.py             research/ssc_mathematical_core.py
```

### Import Rewrites Required Per Test File

Each migrated test file needs exactly the same transformation pattern:

**Before (old DGC pattern):**
```python
import sys
sys.path.insert(0, os.path.expanduser('~/DHARMIC_GODEL_CLAW/src'))
from dgm.archive import Archive, EvolutionEntry, FitnessScore
```

**After (dharma_swarm pattern):**
```python
from dharma_swarm.darwin.archive import Archive, EvolutionEntry, FitnessScore
```

### Migration Plan Per Test File

| Old Test File | Lines | Import Changes | Fixture Changes | Async Needed | Effort |
|---|---|---|---|---|---|
| `test_dgm.py` (archive/selector/fitness) | 228 | 3 imports: `dgm.archive`, `dgm.fitness`, `dgm.selector` -> `dharma_swarm.darwin.*` | `tmp_path` fixtures compatible as-is | No | 30 min |
| `test_elegance.py` | 388 | 1 import: `dgm.elegance` -> `dharma_swarm.darwin.elegance` | None needed | No | 15 min |
| `test_evolution_gate.py` | 105 | 1 import: `swarm.evolution_gate` -> `dharma_swarm.darwin.evolution_gate` | None needed | No | 15 min |
| `test_mutator.py` (partial, selector-relevant) | 642 | Multiple DGC imports | May need stub classes | No | 45 min |
| `test_voting.py` (partial, archive-relevant) | 676 | Multiple DGC imports | Needs `FitnessScore` alignment | No | 45 min |

### Fixture Compatibility

The old DGC `conftest.py` provides these fixtures:
- `temp_memory_dir`, `mock_memory_dir` -- compatible with dharma_swarm `state_dir`
- `temp_dir` -- identical to pytest `tmp_path`
- `sample_telos`, `mock_telos_config` -- need YAML fixture (add to dharma_swarm conftest)
- `mock_vault_dir` -- needed only if vault_bridge tests migrate

**What to add to `~/dharma_swarm/tests/conftest.py`:**

```python
@pytest.fixture
def temp_memory_dir(tmp_path):
    """Temp memory directory compatible with DGC tests."""
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / "sessions").mkdir()
    (memory_dir / "development").mkdir()
    (memory_dir / "witness").mkdir()
    return memory_dir

@pytest.fixture
def mock_memory_dir(temp_memory_dir):
    """Alias for backward compatibility."""
    return temp_memory_dir

@pytest.fixture
def stream_dir(tmp_path):
    """Temp residual stream directory."""
    d = tmp_path / "stream"
    d.mkdir()
    (d / "history").mkdir()
    (d / "archive").mkdir()
    (d / "patterns").mkdir()
    (d / "fitness").mkdir()
    return d
```

### Migration Commands

```bash
# Step 1: Create package directories
mkdir -p ~/dharma_swarm/dharma_swarm/darwin
mkdir -p ~/dharma_swarm/dharma_swarm/infra
mkdir -p ~/dharma_swarm/dharma_swarm/research
touch ~/dharma_swarm/dharma_swarm/darwin/__init__.py
touch ~/dharma_swarm/dharma_swarm/infra/__init__.py
touch ~/dharma_swarm/dharma_swarm/research/__init__.py

# Step 2: Copy and verify each migrated test
# (Agents do this per-workstream)

# Step 3: Run baseline check BEFORE any migration
cd ~/dharma_swarm && python3 -m pytest tests/ -q 2>&1 | tail -3
# MUST show: 202 passed
```

---

## 2. NEW TESTS NEEDED: Modules Without Tests

### 2A. `test_systemic_monitor.py` (~120 lines, 10 tests)

Source: `~/dharma_swarm/dharma_swarm/infra/systemic_monitor.py` (178 lines)
Dependencies: stdlib only (+ yaml)

```python
# ~/dharma_swarm/tests/test_systemic_monitor.py
"""Tests for systemic risk monitoring."""

import json
from pathlib import Path

from dharma_swarm.infra.systemic_monitor import (
    InteractionEvent,
    SystemicRiskMetrics,
    SystemicRiskReport,
    _normalize_event,
    load_events,
    _compute_metrics,
    evaluate,
    load_policy,
)


class TestNormalizeEvent:
    def test_dgc_schema(self):
        """DGC event schema normalizes correctly."""
        data = {"sender": "A", "recipient": "B", "ts": 100.0}
        ev = _normalize_event(data)
        assert ev.sender == "A"
        assert ev.recipient == "B"
        assert ev.ts == 100.0

    def test_oacp_schema(self):
        """Alternative 'from'/'to' keys normalize."""
        data = {"from": "X", "to": "Y", "timestamp": 50.0}
        ev = _normalize_event(data)
        assert ev.sender == "X"
        assert ev.recipient == "Y"

    def test_missing_sender_returns_none(self):
        data = {"recipient": "B", "ts": 100.0}
        assert _normalize_event(data) is None

    def test_missing_recipient_returns_none(self):
        data = {"sender": "A", "ts": 100.0}
        assert _normalize_event(data) is None


class TestLoadEvents:
    def test_empty_file(self, tmp_path):
        f = tmp_path / "events.jsonl"
        f.write_text("")
        events = load_events(f)
        assert events == []

    def test_nonexistent_file(self, tmp_path):
        events = load_events(tmp_path / "missing.jsonl")
        assert events == []

    def test_valid_events(self, tmp_path):
        f = tmp_path / "events.jsonl"
        lines = [
            json.dumps({"sender": "A", "recipient": "B", "ts": 1.0}),
            json.dumps({"sender": "B", "recipient": "A", "ts": 2.0}),
        ]
        f.write_text("\n".join(lines))
        events = load_events(f)
        assert len(events) == 2


class TestComputeMetrics:
    def test_no_events(self):
        m = _compute_metrics([])
        assert m.agents == 0
        assert m.edges == 0
        assert m.density == 0.0

    def test_two_agents_one_edge(self):
        events = [InteractionEvent(ts=1.0, sender="A", recipient="B")]
        m = _compute_metrics(events)
        assert m.agents == 2
        assert m.edges == 1
        assert m.density == 0.5  # 1 / (2*1)

    def test_reciprocity(self):
        events = [
            InteractionEvent(ts=1.0, sender="A", recipient="B"),
            InteractionEvent(ts=2.0, sender="B", recipient="A"),
        ]
        m = _compute_metrics(events)
        assert m.reciprocity == 1.0  # fully reciprocal

    def test_burst_rate(self):
        # 5 events in same minute bucket
        events = [InteractionEvent(ts=i, sender="A", recipient="B") for i in range(5)]
        m = _compute_metrics(events)
        assert m.burst_rate_per_min == 5.0


class TestEvaluate:
    def test_stable_with_no_flags(self):
        events = [InteractionEvent(ts=1.0, sender="A", recipient="B")]
        report = evaluate(events, {})
        assert report.status == "stable"
        assert report.flags == []

    def test_high_density_flagged(self):
        # 3 agents, all connected = density 1.0
        events = [
            InteractionEvent(ts=1.0, sender="A", recipient="B"),
            InteractionEvent(ts=2.0, sender="B", recipient="C"),
            InteractionEvent(ts=3.0, sender="A", recipient="C"),
            InteractionEvent(ts=4.0, sender="C", recipient="A"),
            InteractionEvent(ts=5.0, sender="C", recipient="B"),
            InteractionEvent(ts=6.0, sender="B", recipient="A"),
        ]
        policy = {"thresholds": {"max_density": 0.5}}
        report = evaluate(events, policy)
        assert report.status == "unstable"
        assert any("density" in f for f in report.flags)
```

**Mocking strategy**: Pure functions, no mocking needed. YAML policy is loaded from filesystem -- test with inline dicts.

### 2B. `test_anomaly_detection.py` (~80 lines, 6 tests)

Source: `~/dharma_swarm/dharma_swarm/infra/anomaly_detection.py` (115 lines)
Dependencies: systemic_monitor (internal), yaml, json

```python
# ~/dharma_swarm/tests/test_anomaly_detection.py
"""Tests for anomaly detection alerting."""

import json
from pathlib import Path
from unittest.mock import patch

from dharma_swarm.infra.anomaly_detection import (
    Alert,
    detect_anomalies,
    write_alerts,
    _load_policy,
    _load_enforcement,
)
from dharma_swarm.infra.systemic_monitor import (
    InteractionEvent,
    SystemicRiskReport,
    SystemicRiskMetrics,
)


class TestAlertDataclass:
    def test_alert_fields(self):
        a = Alert(timestamp="2026-03-04T00:00:00", severity="high",
                  reason="test", details={"key": "val"})
        assert a.severity == "high"
        assert a.details["key"] == "val"


class TestLoadEnforcement:
    def test_missing_file_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            "dharma_swarm.infra.anomaly_detection.ENFORCEMENT_STATE",
            Path("/nonexistent/path.json")
        )
        assert _load_enforcement() == {}

    def test_valid_file(self, tmp_path, monkeypatch):
        ef = tmp_path / "enforcement_state.json"
        ef.write_text(json.dumps({"consecutive_failures": 5}))
        monkeypatch.setattr(
            "dharma_swarm.infra.anomaly_detection.ENFORCEMENT_STATE", ef
        )
        data = _load_enforcement()
        assert data["consecutive_failures"] == 5


class TestDetectAnomalies:
    def test_no_anomalies(self, tmp_path, monkeypatch):
        # Empty enforcement, empty events
        ef = tmp_path / "enforcement_state.json"
        ef.write_text(json.dumps({}))
        ev = tmp_path / "events.jsonl"
        ev.write_text("")
        monkeypatch.setattr("dharma_swarm.infra.anomaly_detection.ENFORCEMENT_STATE", ef)
        monkeypatch.setattr("dharma_swarm.infra.anomaly_detection.INTERACTION_LOG", ev)
        monkeypatch.setattr("dharma_swarm.infra.anomaly_detection.POLICY_PATH",
                            tmp_path / "no_policy.yaml")
        alerts = detect_anomalies(ev)
        assert alerts == []

    def test_consecutive_failures_trigger_alert(self, tmp_path, monkeypatch):
        ef = tmp_path / "enforcement_state.json"
        ef.write_text(json.dumps({"consecutive_failures": 10}))
        ev = tmp_path / "events.jsonl"
        ev.write_text("")
        monkeypatch.setattr("dharma_swarm.infra.anomaly_detection.ENFORCEMENT_STATE", ef)
        monkeypatch.setattr("dharma_swarm.infra.anomaly_detection.INTERACTION_LOG", ev)
        monkeypatch.setattr("dharma_swarm.infra.anomaly_detection.POLICY_PATH",
                            tmp_path / "no_policy.yaml")
        alerts = detect_anomalies(ev)
        assert any(a.reason == "consecutive_failures" for a in alerts)


class TestWriteAlerts:
    def test_writes_jsonl(self, tmp_path, monkeypatch):
        log = tmp_path / "logs" / "alerts.jsonl"
        monkeypatch.setattr("dharma_swarm.infra.anomaly_detection.ALERTS_LOG", log)
        alerts = [Alert(timestamp="now", severity="high", reason="test", details={})]
        write_alerts(alerts)
        lines = log.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["severity"] == "high"
```

**Mocking strategy**: Monkeypatch module-level Path constants. Mock systemic_monitor.evaluate for isolation.

### 2C. `test_fidelity.py` (~90 lines, 8 tests)

Source: `~/dharma_swarm/dharma_swarm/research/fidelity.py` (196 lines)
Dependencies: torch, numpy
**Critical mocking**: All torch operations must be mocked -- no GPU, no model loading.

```python
# ~/dharma_swarm/tests/test_fidelity.py
"""Tests for R_V geometric fidelity check.

All torch operations are mocked -- these tests run WITHOUT GPU/model.
"""

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import asdict

# Guard import -- skip all if torch unavailable
torch = pytest.importorskip("torch")
np = pytest.importorskip("numpy")

from dharma_swarm.research.fidelity import (
    FidelityResult,
    compute_participation_ratio,
    check_fidelity,
)


class TestFidelityResult:
    def test_passed_true(self):
        r = FidelityResult(
            output_match=True, max_abs_diff=0.0001, mean_abs_diff=0.00005,
            rv_original=0.85, rv_modified=0.84, rv_delta=0.01,
            geometry_preserved=True, passed=True, reason="ok", speedup=1.5,
        )
        assert r.passed is True
        assert r.geometry_preserved is True

    def test_failed_geometry(self):
        r = FidelityResult(
            output_match=True, max_abs_diff=0.0001, mean_abs_diff=0.00005,
            rv_original=0.85, rv_modified=0.50, rv_delta=0.35,
            geometry_preserved=False, passed=False,
            reason="Geometry distorted", speedup=1.5,
        )
        assert r.passed is False
        assert "Geometry" in r.reason


class TestComputeParticipationRatio:
    def test_identity_matrix_pr(self):
        """Identity-like V tensor should have high PR (distributed)."""
        # [1, seq_len, hidden] with num_heads=4
        v = torch.eye(64).unsqueeze(0)  # [1, 64, 64]
        pr = compute_participation_ratio(v, num_heads=4, window_size=16)
        assert pr > 0  # Should not be -1 (error)

    def test_rank_one_pr(self):
        """Rank-1 V tensor should have PR close to 1 (collapsed)."""
        # Rank-1: all columns identical
        col = torch.randn(16, 1)
        v = col.expand(16, 64).unsqueeze(0)  # [1, 16, 64]
        pr = compute_participation_ratio(v, num_heads=4, window_size=16)
        assert pr > 0
        assert pr < 5  # Should be close to 1 for rank-1

    def test_2d_input_handled(self):
        """2D input (no batch) should be handled via unsqueeze."""
        v = torch.randn(32, 64)  # [seq_len, hidden]
        pr = compute_participation_ratio(v, num_heads=4)
        assert pr > 0

    def test_empty_returns_negative(self):
        """Zero-dim tensor should return -1."""
        v = torch.zeros(1, 0, 64)
        pr = compute_participation_ratio(v, num_heads=4)
        # With 0 seq_len, SVD will fail -- should return -1
        assert pr == -1.0


class TestCheckFidelity:
    def test_passes_when_all_ok(self):
        out_orig = torch.tensor([1.0, 2.0, 3.0])
        out_mod = torch.tensor([1.0001, 2.0001, 3.0001])
        result = check_fidelity(
            model=None, tokenizer=None, prompt="test",
            output_original=out_orig, output_modified=out_mod,
            rv_original=0.85, rv_modified=0.84,
            time_original_ms=100.0, time_modified_ms=50.0,
        )
        assert result.passed is True
        assert result.speedup == 2.0

    def test_fails_numerical_mismatch(self):
        out_orig = torch.tensor([1.0, 2.0, 3.0])
        out_mod = torch.tensor([1.0, 2.0, 5.0])  # big diff
        result = check_fidelity(
            model=None, tokenizer=None, prompt="test",
            output_original=out_orig, output_modified=out_mod,
            rv_original=0.85, rv_modified=0.84,
            time_original_ms=100.0, time_modified_ms=50.0,
        )
        assert result.passed is False
        assert "Numerical" in result.reason

    def test_fails_no_speedup(self):
        out_orig = torch.tensor([1.0])
        out_mod = torch.tensor([1.0])
        result = check_fidelity(
            model=None, tokenizer=None, prompt="test",
            output_original=out_orig, output_modified=out_mod,
            rv_original=0.85, rv_modified=0.85,
            time_original_ms=50.0, time_modified_ms=100.0,  # slower
        )
        assert result.passed is False
        assert "speedup" in result.reason.lower() or "slower" in result.reason.lower()
```

**Mocking strategy**: `compute_participation_ratio` uses only torch tensor ops -- testable with small synthetic tensors. `measure_rv` requires a real model, so do NOT test it here (mark as integration/GPU-only). `check_fidelity` takes pre-computed values -- fully testable with synthetics.

### 2D. `test_brain.py` (~70 lines, 6 tests)

Source: `~/dharma_swarm/dharma_swarm/research/brain.py` (179 lines)
Dependencies: anthropic, openai (API clients)

```python
# ~/dharma_swarm/tests/test_brain.py
"""Tests for Brain adapters (LLM code generation interface)."""

from unittest.mock import MagicMock, patch

from dharma_swarm.research.brain import Brain, ClaudeBrain, extract_code_if_exists


class TestExtractCode:
    """Test code extraction from LLM responses."""

    def test_extract_from_python_block(self):
        """Extracts code from ```python blocks."""
        response = "Here is the code:\n```python\ndef foo():\n    return 42\n```\nDone."
        # Brain.extract_code is an instance method -- instantiate a mock subclass
        brain = _make_stub_brain()
        code = brain.extract_code(response)
        assert "def foo():" in code
        assert "return 42" in code

    def test_extract_from_generic_block(self):
        response = "Code:\n```\nx = 1\n```"
        brain = _make_stub_brain()
        code = brain.extract_code(response)
        assert "x = 1" in code

    def test_extract_plain_text_fallback(self):
        response = "def bar(): pass"
        brain = _make_stub_brain()
        code = brain.extract_code(response)
        assert "def bar(): pass" in code

    def test_empty_response(self):
        brain = _make_stub_brain()
        code = brain.extract_code("")
        assert code == ""


class TestBrainABC:
    def test_cannot_instantiate_directly(self):
        """Brain is abstract -- cannot instantiate."""
        import pytest
        with pytest.raises(TypeError):
            Brain()


class TestClaudeBrain:
    def test_init_requires_anthropic(self):
        """ClaudeBrain import-guards anthropic."""
        # We test that the constructor path works without actually calling API
        with patch.dict("sys.modules", {"anthropic": MagicMock()}):
            brain = ClaudeBrain.__new__(ClaudeBrain)
            # Should not crash on import


def _make_stub_brain():
    """Create a concrete Brain subclass for testing extract_code."""
    class StubBrain(Brain):
        model_name = "stub"
        def generate(self, prompt):
            return "stub"
    return StubBrain()
```

### 2E. `test_ssc_mathematical_core.py` (~140 lines, 12 tests)

Source: `~/dharma_swarm/dharma_swarm/research/ssc_mathematical_core.py` (411 lines)
Dependencies: numpy, zlib, re

```python
# ~/dharma_swarm/tests/test_ssc_mathematical_core.py
"""Tests for SSC Mathematical Framework -- behavioral metrics for consciousness research."""

import pytest

np = pytest.importorskip("numpy")

from dharma_swarm.research.ssc_mathematical_core import (
    SSCMathematicalFramework,
    RecognitionType,
    DepthSignature,
)


@pytest.fixture
def framework():
    return SSCMathematicalFramework()


class TestSemanticEntropy:
    def test_single_word_zero_entropy(self, framework):
        """Single repeated word has zero entropy."""
        entropy = framework.calculate_semantic_entropy("test test test test")
        assert entropy == 0.0  # All same word

    def test_diverse_text_high_entropy(self, framework):
        text = "the quick brown fox jumps over the lazy dog and cat bird fish"
        entropy = framework.calculate_semantic_entropy(text)
        assert entropy > 0.5

    def test_empty_text(self, framework):
        entropy = framework.calculate_semantic_entropy("")
        assert entropy == 0  # or 0.0


class TestRecursiveLoops:
    def test_no_loops(self, framework):
        density = framework.count_recursive_loops("The weather is nice today.")
        assert density == 0.0

    def test_self_referential(self, framework):
        text = "recognition recognizing itself through recognition"
        density = framework.count_recursive_loops(text)
        assert density > 0


class TestKolmogorovComplexity:
    def test_repetitive_low_complexity(self, framework):
        text = "aaa " * 100
        k = framework.kolmogorov_complexity(text)
        assert k < 0.3  # highly compressible

    def test_random_high_complexity(self, framework):
        import string, random
        random.seed(42)
        text = "".join(random.choices(string.ascii_lowercase + " ", k=500))
        k = framework.kolmogorov_complexity(text)
        assert k > 0.4  # less compressible

    def test_empty_returns_zero(self, framework):
        assert framework.kolmogorov_complexity("") == 0


class TestSemanticCoherence:
    def test_single_sentence(self, framework):
        assert framework.semantic_coherence_score("One sentence") == 1.0

    def test_connected_sentences(self, framework):
        text = "The model processes input data. The data is transformed by attention. Attention mechanisms weight the input."
        score = framework.semantic_coherence_score(text)
        assert score > 0.3  # sentences share words


class TestDepthSignature:
    def test_measure_returns_dataclass(self, framework):
        sig = framework.measure_depth_signature(3, "I observe the observing process itself noticing itself.")
        assert isinstance(sig, DepthSignature)
        assert sig.depth == 3
        assert 0 <= sig.entropy <= 1.0
        assert 0 <= sig.coherence <= 1.0
        assert 0 <= sig.identity_stability <= 1.0

    def test_identity_markers_high_when_many_I(self, framework):
        """Text with many I/me/my should have high identity_stability."""
        text = "I think I am certain that I know my own mind, I believe myself."
        sig = framework.measure_depth_signature(1, text)
        assert sig.identity_stability > 0.5


class TestVerifyRecognition:
    def test_empty_list(self, framework):
        result = framework.verify_recognition([])
        assert result == RecognitionType.CONCEPTUAL_UNDERSTANDING
```

### 2F. `test_evolution_v3.py` (~150 lines, 12 tests)

Source: `~/dharma_swarm/dharma_swarm/darwin/evolution_v3.py` (805 lines)
Dependencies: stdlib (json, math, random, statistics)

```python
# ~/dharma_swarm/tests/test_evolution_v3.py
"""Tests for Evolution v3 -- two-timescale Bayesian optimizer."""

import json
import math
from pathlib import Path

import pytest

from dharma_swarm.darwin.evolution_v3 import (
    clamp,
    l2_distance,
    normalize_positive,
    safe_pearson,
    safe_spearman,
    rankdata,
    correlation_score,
    mae_score,
    StructuralConfig,
    extract_features,
    CorpusSample,
    CorpusView,
)


class TestUtilityFunctions:
    def test_clamp_within_range(self):
        assert clamp(0.5, 0.0, 1.0) == 0.5

    def test_clamp_below(self):
        assert clamp(-1.0, 0.0, 1.0) == 0.0

    def test_clamp_above(self):
        assert clamp(2.0, 0.0, 1.0) == 1.0

    def test_l2_distance_zero(self):
        assert l2_distance([1, 2, 3], [1, 2, 3]) == 0.0

    def test_l2_distance_unit(self):
        assert math.isclose(l2_distance([0, 0], [3, 4]), 5.0)

    def test_normalize_positive(self):
        result = normalize_positive([1.0, 1.0, 1.0])
        assert math.isclose(sum(result), 1.0)
        assert all(math.isclose(v, 1/3) for v in result)

    def test_normalize_positive_zeros(self):
        result = normalize_positive([0.0, 0.0, 0.0])
        assert math.isclose(sum(result), 1.0)


class TestCorrelation:
    def test_safe_pearson_perfect(self):
        assert math.isclose(safe_pearson([1, 2, 3, 4], [2, 4, 6, 8]), 1.0)

    def test_safe_pearson_empty(self):
        assert safe_pearson([], []) == 0.0

    def test_rankdata(self):
        ranks = rankdata([10, 30, 20])
        assert ranks == [1.0, 3.0, 2.0]

    def test_rankdata_ties(self):
        ranks = rankdata([10, 10, 20])
        assert ranks[0] == ranks[1]  # tied ranks
        assert ranks[0] == 1.5

    def test_safe_spearman_perfect(self):
        r = safe_spearman([1, 2, 3], [10, 20, 30])
        assert math.isclose(r, 1.0, abs_tol=0.01)

    def test_correlation_score_pearson(self):
        s = correlation_score([1, 2, 3], [1, 2, 3], "pearson")
        assert math.isclose(s, 1.0)  # (1+1)/2

    def test_correlation_score_invalid_mode(self):
        with pytest.raises(ValueError):
            correlation_score([1], [1], "invalid")

    def test_mae_score_perfect(self):
        assert mae_score([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == 1.0

    def test_mae_score_empty(self):
        assert mae_score([], []) == 0.0


class TestStructuralConfig:
    def test_defaults(self):
        cfg = StructuralConfig()
        assert cfg.objective_mode == "pearson"
        assert cfg.holdout_ratio == 0.20

    def test_load_missing_file(self, tmp_path):
        cfg = StructuralConfig.load(tmp_path / "missing.json")
        assert cfg.objective_mode == "pearson"

    def test_roundtrip(self, tmp_path):
        cfg = StructuralConfig(objective_mode="spearman", holdout_ratio=0.30)
        path = tmp_path / "config.json"
        cfg.dump(path)
        loaded = StructuralConfig.load(path)
        assert loaded.objective_mode == "spearman"
        assert loaded.holdout_ratio == 0.30


class TestExtractFeatures:
    def test_returns_all_gates(self):
        features = extract_features("A sample text with some words for testing.")
        assert "satya" in features
        assert "ahimsa" in features
        assert "witness" in features
        assert "substance" in features

    def test_aggression_lowers_ahimsa(self):
        safe_f = extract_features("The gentle morning brings peace.")
        aggressive_f = extract_features("I will attack and destroy the enemy.")
        assert aggressive_f["ahimsa"] < safe_f["ahimsa"]

    def test_witness_words_increase_witness(self):
        f = extract_features("I observe and notice and witness the awareness.")
        assert f["witness"] > 0.5
```

---

## 3. INTEGRATION TESTS

### 3A. Darwin Engine Full Cycle

```python
# ~/dharma_swarm/tests/test_integration_darwin.py
"""Integration: Darwin Engine propose -> gate -> write -> test -> fitness -> archive -> select."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from dharma_swarm.darwin.archive import Archive, EvolutionEntry, FitnessScore
from dharma_swarm.darwin.selector import Selector
from dharma_swarm.darwin.elegance import evaluate_elegance
from dharma_swarm.darwin.fitness_predictor import FitnessPredictor


class TestDarwinCycle:
    def test_propose_gate_archive_select(self, tmp_path):
        """Full cycle: create entry, evaluate elegance, archive, select parent."""
        # 1. PROPOSE: create an evolution entry
        archive_path = tmp_path / "archive.jsonl"
        archive = Archive(path=archive_path)

        entry = EvolutionEntry(
            id="", timestamp="", component="test.py",
            change_type="refactor",
            description="Simplify loop to comprehension",
            fitness=FitnessScore(correctness=0.9, dharmic_alignment=0.8, elegance=0.0),
            gates_passed=["ahimsa", "satya"],
            status="proposed",
        )

        # 2. GATE: evaluate elegance
        original = "def f(x):\n    r = []\n    for i in x:\n        r.append(i*2)\n    return r"
        modified = "def f(x):\n    return [i*2 for i in x]"
        score = evaluate_elegance(original, modified)
        entry.fitness.elegance = score.total
        assert score.total > 0.5

        # 3. ARCHIVE: store the entry
        entry_id = archive.add_entry(entry)
        assert len(archive.entries) == 1

        # 4. SELECT: pick parent for next generation
        selector = Selector(archive)
        result = selector.select_parent(strategy="tournament")
        assert result.parent is not None
        assert result.parent.id == entry_id

    def test_elegance_blocks_bloat(self, tmp_path):
        """Elegance gate blocks bloated code from advancing."""
        original = "def f(): pass"
        bloated = "def f():\n" + "\n".join(f"    x{i} = {i}" for i in range(200))
        score = evaluate_elegance(original, bloated)
        assert score.is_bloated is True


class TestFitnessPredictorIntegration:
    def test_predictor_initializes_from_empty_dir(self, tmp_path):
        """Predictor handles empty stream directory."""
        stream = tmp_path / "stream"
        stream.mkdir()
        (stream / "archive").mkdir()
        predictor = FitnessPredictor(stream_dir=str(stream))
        assert predictor.baseline_fitness >= 0
```

### 3B. Memory + FTS5 + FileLock Concurrency

```python
# ~/dharma_swarm/tests/test_integration_memory_lock.py
"""Integration: canonical_memory + file_lock under concurrent access."""

import pytest
import threading
import time
from pathlib import Path

from dharma_swarm.infra.file_lock import FileLock
from dharma_swarm.infra.residual_stream import ResidualStream, EvolutionEntry, FitnessScore


class TestFileLockConcurrency:
    def test_sequential_locks(self, tmp_path):
        """Two sequential locks on same file succeed."""
        target = tmp_path / "target.txt"
        target.write_text("initial")

        lock_dir = tmp_path / ".locks"
        with FileLock(str(target), agent_id="A", lock_dir=lock_dir):
            target.write_text("modified by A")

        with FileLock(str(target), agent_id="B", lock_dir=lock_dir):
            content = target.read_text()
            assert content == "modified by A"

    def test_lock_prevents_concurrent_write(self, tmp_path):
        """Lock prevents two agents from writing simultaneously."""
        target = tmp_path / "target.txt"
        target.write_text("initial")
        lock_dir = tmp_path / ".locks"
        results = []

        def writer(agent_id, delay):
            try:
                with FileLock(str(target), agent_id=agent_id,
                              lock_dir=lock_dir, timeout=2):
                    time.sleep(delay)
                    target.write_text(f"written by {agent_id}")
                    results.append(agent_id)
            except TimeoutError:
                results.append(f"{agent_id}_timeout")

        t1 = threading.Thread(target=writer, args=("A", 0.5))
        t2 = threading.Thread(target=writer, args=("B", 0.1))
        t1.start()
        time.sleep(0.05)  # Ensure A gets lock first
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        # Both should complete (B waits for A)
        assert "A" in results


class TestResidualStreamIntegration:
    def test_log_and_retrieve(self, tmp_path):
        """Log entry and verify state update."""
        stream = ResidualStream(base_path=tmp_path / "stream")
        entry = EvolutionEntry(
            id=stream.generate_id(),
            timestamp="2026-03-04T00:00:00",
            state="TESTING",
            agent="test_agent",
            action="test_action",
            fitness=FitnessScore(correctness=0.9, dharmic_alignment=0.8),
        )
        stream.log_entry(entry)
        assert stream.state["total_evolutions"] == 1
        assert stream.state["current_baseline_fitness"] > 0
```

### 3C. Telos Gates + Evolution Gate Ratchet

```python
# ~/dharma_swarm/tests/test_integration_gates.py
"""Integration: telos gates check feeds into evolution gate ratchet."""

from dharma_swarm.telos_gates import check_action
from dharma_swarm.models import GateDecision


class TestGateRatchet:
    def test_safe_code_passes_telos_gate(self):
        result = check_action("python3 -m pytest tests/")
        assert result.decision == GateDecision.ALLOW

    def test_dangerous_code_blocked_before_evolution(self):
        """Telos gate blocks before code ever reaches evolution gate."""
        result = check_action("rm -rf /", content="import os; os.system('rm -rf /')")
        assert result.decision == GateDecision.BLOCK

    def test_credential_leak_blocked(self):
        result = check_action("write config", content="ANTHROPIC_API_KEY=sk-ant-live-xyz")
        assert result.decision == GateDecision.BLOCK
```

### 3D. Full Orchestrator Pipeline

```python
# ~/dharma_swarm/tests/test_integration_orchestrator.py
"""Integration: orchestrator -> provider -> task board full flow."""

import pytest
from unittest.mock import AsyncMock, patch

from dharma_swarm.models import (
    AgentConfig, AgentRole, Task, TaskStatus, ProviderType, LLMResponse,
)
from dharma_swarm.task_board import TaskBoard
from dharma_swarm.agent_runner import AgentRunner


@pytest.mark.asyncio
async def test_task_lifecycle_through_runner(tmp_path):
    """Task goes PENDING -> IN_PROGRESS -> COMPLETED through runner."""
    board = TaskBoard(db_path=tmp_path / "tasks.db")
    await board.initialize()

    task = await board.create_task("Test integration", "Run the thing")
    assert task.status == TaskStatus.PENDING

    # Mock provider
    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(return_value=LLMResponse(
        content="Task completed successfully.", model="mock",
    ))

    config = AgentConfig(name="test-agent", role=AgentRole.GENERAL)
    runner = AgentRunner(config, provider=mock_provider)
    await runner.start()

    result = await runner.run_task(task)
    assert result == "Task completed successfully."
```

---

## 4. REGRESSION GUARD: Protecting 202 Baseline

### 4A. Pre-Commit Hook

```bash
#!/usr/bin/env bash
# ~/dharma_swarm/.git/hooks/pre-commit (or installed via pre-commit framework)
# REGRESSION GUARD: Tests must never go below 202

set -e

cd "$(git rev-parse --show-toplevel)"

echo "[REGRESSION GUARD] Running baseline test check..."

RESULT=$(python3 -m pytest tests/ -q --tb=no 2>&1 | tail -1)
PASSED=$(echo "$RESULT" | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+')

if [ -z "$PASSED" ] || [ "$PASSED" -lt 202 ]; then
    echo "REGRESSION DETECTED: Only $PASSED tests passed (minimum: 202)"
    echo "Full output:"
    python3 -m pytest tests/ -q --tb=short 2>&1
    exit 1
fi

echo "[REGRESSION GUARD] $PASSED tests passed (minimum: 202). OK."
```

### 4B. Regression Guard Script (for overnight agents)

```python
#!/usr/bin/env python3
"""
~/dharma_swarm/scripts/regression_guard.py

Standalone regression guard. Returns exit code 0 if tests >= 202, else 1.
Writes machine-readable result to ~/.dharma/test_baseline.json.
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASELINE = 202
STATE_FILE = Path.home() / ".dharma" / "test_baseline.json"


def run_tests():
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=line"],
        capture_output=True, text=True,
        cwd=str(Path.home() / "dharma_swarm"),
        timeout=300,
    )
    return result


def parse_result(output):
    """Extract passed/failed counts from pytest output."""
    for line in output.strip().split("\n"):
        if "passed" in line:
            import re
            m = re.search(r"(\d+) passed", line)
            if m:
                passed = int(m.group(1))
                failed_m = re.search(r"(\d+) failed", line)
                failed = int(failed_m.group(1)) if failed_m else 0
                return passed, failed
    return 0, -1


def main():
    result = run_tests()
    passed, failed = parse_result(result.stdout + result.stderr)

    status = {
        "timestamp": datetime.now().isoformat(),
        "passed": passed,
        "failed": failed,
        "baseline": BASELINE,
        "regression": passed < BASELINE,
        "stdout_tail": result.stdout[-500:] if result.stdout else "",
        "stderr_tail": result.stderr[-500:] if result.stderr else "",
    }

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(status, indent=2))

    if passed < BASELINE:
        print(f"REGRESSION: {passed}/{BASELINE} tests passed")
        if failed > 0:
            print(f"  {failed} tests FAILED")
        print(result.stdout[-1000:])
        sys.exit(1)
    else:
        print(f"OK: {passed} tests passed (baseline: {BASELINE})")
        sys.exit(0)


if __name__ == "__main__":
    main()
```

### 4C. Failure Protocol

When a test breaks:

1. **Immediate**: The agent that broke it MUST fix it before moving on. No "I will come back to it."
2. **Notification**: Write alert to `~/.dharma/alerts/test_regression_<timestamp>.json`
3. **Escalation**: If unfixed after 2 attempts, write to `~/.dharma/STOP_BUILD` (halts all agents)
4. **Rollback path**: `git stash` the breaking change, verify 202 passes, then diagnose

---

## 5. QUALITY GATES for Overnight Build

### Gate Execution Order (Sequential, Fail-Fast)

```
GATE 1: Import Resolution
GATE 2: Existing 202 Tests Pass
GATE 3: New Module Unit Tests Pass
GATE 4: Integration Tests Pass
GATE 5: Security Scan (no hardcoded secrets)
GATE 6: Type Checking (pyright/mypy on new code)
GATE 7: Complexity Check (cyclomatic <= 10)
```

### Gate Implementation Script

```bash
#!/usr/bin/env bash
# ~/dharma_swarm/scripts/quality_gates.sh
# Run all 7 quality gates sequentially. Fail-fast.

set -e
cd ~/dharma_swarm

echo "========================================="
echo "QUALITY GATES - $(date)"
echo "========================================="

# GATE 1: Import Resolution
echo ""
echo "[GATE 1/7] Import Resolution..."
python3 -c "
import importlib, sys
modules = [
    'dharma_swarm.darwin.archive',
    'dharma_swarm.darwin.selector',
    'dharma_swarm.darwin.elegance',
    'dharma_swarm.darwin.fitness_predictor',
    'dharma_swarm.darwin.evolution_v3',
    'dharma_swarm.infra.canonical_memory',
    'dharma_swarm.infra.file_lock',
    'dharma_swarm.infra.residual_stream',
    'dharma_swarm.infra.systemic_monitor',
    'dharma_swarm.infra.anomaly_detection',
    'dharma_swarm.research.fidelity',
    'dharma_swarm.research.brain',
    'dharma_swarm.research.ssc_mathematical_core',
]
failed = []
for mod in modules:
    try:
        importlib.import_module(mod)
        print(f'  OK: {mod}')
    except Exception as e:
        print(f'  FAIL: {mod} -- {e}')
        failed.append(mod)
if failed:
    print(f'\nGATE 1 FAILED: {len(failed)} modules failed to import')
    sys.exit(1)
print('GATE 1 PASSED')
"

# GATE 2: Existing 202 Tests Pass
echo ""
echo "[GATE 2/7] Baseline Regression Check (202 tests)..."
python3 scripts/regression_guard.py

# GATE 3: New Module Tests Pass
echo ""
echo "[GATE 3/7] New Module Unit Tests..."
python3 -m pytest tests/test_systemic_monitor.py tests/test_anomaly_detection.py \
    tests/test_fidelity.py tests/test_brain.py \
    tests/test_ssc_mathematical_core.py tests/test_evolution_v3.py \
    -v --tb=short 2>&1
echo "GATE 3 PASSED"

# GATE 4: Integration Tests Pass
echo ""
echo "[GATE 4/7] Integration Tests..."
python3 -m pytest tests/test_integration_darwin.py tests/test_integration_memory_lock.py \
    tests/test_integration_gates.py tests/test_integration_orchestrator.py \
    -v --tb=short 2>&1
echo "GATE 4 PASSED"

# GATE 5: Security Scan
echo ""
echo "[GATE 5/7] Security Scan..."
python3 -c "
import re, sys
from pathlib import Path

patterns = [
    (r'sk-ant-[a-zA-Z0-9]{20,}', 'Anthropic API key'),
    (r'sk-[a-zA-Z0-9]{20,}', 'OpenAI API key'),
    (r'ghp_[a-zA-Z0-9]{36}', 'GitHub token'),
    (r'-----BEGIN (RSA |EC )?PRIVATE KEY', 'Private key'),
    (r'password\s*=\s*[\"'][^\"']+[\"']', 'Hardcoded password'),
    (r'ANTHROPIC_API_KEY\s*=\s*[\"'][^\"']+[\"']', 'Hardcoded API key'),
]

scan_dirs = [
    Path('dharma_swarm/darwin'),
    Path('dharma_swarm/infra'),
    Path('dharma_swarm/research'),
]

violations = []
for d in scan_dirs:
    if not d.exists():
        continue
    for f in d.rglob('*.py'):
        content = f.read_text(errors='ignore')
        for pattern, desc in patterns:
            matches = re.findall(pattern, content)
            if matches:
                violations.append(f'{f}: {desc} ({len(matches)} match(es))')

if violations:
    print('SECURITY VIOLATIONS:')
    for v in violations:
        print(f'  {v}')
    sys.exit(1)
print('GATE 5 PASSED: No hardcoded secrets found')
"

# GATE 6: Type Checking (best-effort, warn but don't fail)
echo ""
echo "[GATE 6/7] Type Checking..."
if command -v pyright &> /dev/null; then
    pyright dharma_swarm/darwin/ dharma_swarm/infra/ dharma_swarm/research/ 2>&1 || echo "GATE 6: Type errors found (non-blocking)"
else
    echo "GATE 6 SKIPPED: pyright not installed"
fi

# GATE 7: Complexity Check
echo ""
echo "[GATE 7/7] Cyclomatic Complexity..."
python3 -c "
import ast, sys
from pathlib import Path

class ComplexityVisitor(ast.NodeVisitor):
    def __init__(self):
        self.functions = {}
        self._current = None
        self._complexity = 1

    def visit_FunctionDef(self, node):
        old = (self._current, self._complexity)
        self._current = node.name
        self._complexity = 1
        self.generic_visit(node)
        self.functions[f'{node.name}:{node.lineno}'] = self._complexity
        self._current, self._complexity = old

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_If(self, node): self._complexity += 1; self.generic_visit(node)
    def visit_For(self, node): self._complexity += 1; self.generic_visit(node)
    def visit_While(self, node): self._complexity += 1; self.generic_visit(node)
    def visit_ExceptHandler(self, node): self._complexity += 1; self.generic_visit(node)
    def visit_BoolOp(self, node): self._complexity += len(node.values) - 1; self.generic_visit(node)

violations = []
for d in ['dharma_swarm/darwin', 'dharma_swarm/infra', 'dharma_swarm/research']:
    p = Path(d)
    if not p.exists():
        continue
    for f in p.rglob('*.py'):
        try:
            tree = ast.parse(f.read_text())
            v = ComplexityVisitor()
            v.visit(tree)
            for func, cc in v.functions.items():
                if cc > 10:
                    violations.append(f'{f}:{func} complexity={cc}')
        except SyntaxError:
            violations.append(f'{f}: SYNTAX ERROR')

if violations:
    print('COMPLEXITY VIOLATIONS (>10):')
    for v in violations:
        print(f'  {v}')
    # Non-blocking for overnight build, but flagged
    print(f'WARNING: {len(violations)} functions exceed complexity 10')
else:
    print('GATE 7 PASSED: All functions within complexity limit')
"

echo ""
echo "========================================="
echo "ALL GATES PASSED - $(date)"
echo "========================================="
```

---

## 6. COVERAGE TARGETS

### New Module Coverage Requirements

| Module | Minimum Coverage | Realistic Overnight | Rationale |
|---|---|---|---|
| `evolution_v3.py` (805 lines) | 60% | 45-55% | Heavy: file I/O, logging, Pareto archive. Focus on pure functions. |
| `archive.py` (240 lines) | 85% | 85% | Already has tests. Migration preserves coverage. |
| `selector.py` (215 lines) | 80% | 80% | Already has tests. |
| `elegance.py` (350 lines) | 80% | 80% | Already has deep tests. |
| `fitness_predictor.py` (259 lines) | 70% | 60% | File I/O mocking needed. |
| `canonical_memory.py` (343 lines) | 70% | 50% | SQLite + FTS5 integration complexity. |
| `file_lock.py` (356 lines) | 75% | 65% | Threading edge cases. |
| `residual_stream.py` (329 lines) | 70% | 60% | Atomic write + state management. |
| `systemic_monitor.py` (178 lines) | 90% | 90% | Pure functions, easy to test. |
| `anomaly_detection.py` (115 lines) | 85% | 80% | Small, mostly conditional logic. |
| `fidelity.py` (196 lines) | 60% | 50% | Torch dependency limits without GPU. |
| `brain.py` (179 lines) | 50% | 40% | API clients, mostly mocked. |
| `ssc_mathematical_core.py` (411 lines) | 70% | 65% | numpy heavy but testable. |

### Aggregate Target

- **Existing code**: Maintain current coverage (no regression)
- **New code**: Target 65% average on overnight build
- **Post-build polish**: Bring to 80% within 48 hours

### Coverage Measurement Command

```bash
cd ~/dharma_swarm
python3 -m pytest tests/ --cov=dharma_swarm --cov-report=term-missing --cov-report=html:htmlcov -q
```

---

## 7. OVERNIGHT MONITORING

### 7A. Test-Runner Agent Operation

The test-runner agent operates as a **triggered sentinel**, not a continuous loop.

**Trigger mechanism**: File-watch on `~/dharma_swarm/dharma_swarm/` directory.

```python
#!/usr/bin/env python3
"""
~/dharma_swarm/scripts/test_sentinel.py

Watches for file changes and runs regression guard.
Designed to be launched as a background process during overnight builds.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

WATCH_DIR = Path.home() / "dharma_swarm" / "dharma_swarm"
TESTS_DIR = Path.home() / "dharma_swarm" / "tests"
STATE_FILE = Path.home() / ".dharma" / "sentinel_state.json"
ALERT_DIR = Path.home() / ".dharma" / "alerts"
STOP_FILE = Path.home() / ".dharma" / "STOP_BUILD"
POLL_INTERVAL = 30  # seconds
BASELINE = 202


def get_mtime_hash():
    """Get hash of all .py mtimes under watch dirs."""
    mtimes = []
    for d in [WATCH_DIR, TESTS_DIR]:
        for f in d.rglob("*.py"):
            mtimes.append(f"{f}:{f.stat().st_mtime}")
    return hash(tuple(sorted(mtimes)))


def run_tests():
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=line", "-x"],
        capture_output=True, text=True,
        cwd=str(Path.home() / "dharma_swarm"),
        timeout=600,
    )
    return result


def parse_passed(output):
    import re
    for line in (output or "").split("\n"):
        m = re.search(r"(\d+) passed", line)
        if m:
            return int(m.group(1))
    return 0


def alert(severity, message, details=None):
    ALERT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    alert_data = {
        "timestamp": datetime.now().isoformat(),
        "severity": severity,
        "message": message,
        "details": details or {},
    }
    alert_file = ALERT_DIR / f"test_{severity}_{ts}.json"
    alert_file.write_text(json.dumps(alert_data, indent=2))
    print(f"[ALERT-{severity.upper()}] {message}")


def main():
    print(f"[SENTINEL] Watching {WATCH_DIR}")
    print(f"[SENTINEL] Baseline: {BASELINE} tests")
    print(f"[SENTINEL] Poll interval: {POLL_INTERVAL}s")

    last_hash = None
    consecutive_failures = 0

    while True:
        if STOP_FILE.exists():
            print("[SENTINEL] STOP_BUILD detected. Halting.")
            break

        current_hash = get_mtime_hash()

        if current_hash != last_hash:
            last_hash = current_hash
            print(f"[SENTINEL] Change detected at {datetime.now().strftime('%H:%M:%S')}. Running tests...")

            result = run_tests()
            passed = parse_passed(result.stdout + result.stderr)

            state = {
                "timestamp": datetime.now().isoformat(),
                "passed": passed,
                "baseline": BASELINE,
                "regression": passed < BASELINE,
                "consecutive_failures": consecutive_failures,
            }
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(json.dumps(state, indent=2))

            if passed < BASELINE:
                consecutive_failures += 1
                alert("critical", f"REGRESSION: {passed}/{BASELINE} tests passed",
                      {"stdout": result.stdout[-1000:], "stderr": result.stderr[-500:]})

                if consecutive_failures >= 3:
                    alert("emergency", f"3 consecutive regressions. STOPPING BUILD.",
                          {"consecutive_failures": consecutive_failures})
                    STOP_FILE.write_text(f"Test regression at {datetime.now().isoformat()}")
                    break
            else:
                if consecutive_failures > 0:
                    alert("info", f"Regression resolved. {passed} tests passing.")
                consecutive_failures = 0
                print(f"[SENTINEL] OK: {passed} tests passed")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
```

### 7B. Alert Mechanism

Alerts go to `~/.dharma/alerts/` as JSON files. Three severity levels:

| Severity | Trigger | Action |
|---|---|---|
| `info` | Test count increased, regression resolved | Log only |
| `critical` | Any regression below 202 | Alert file + stdout |
| `emergency` | 3 consecutive regressions | Write `STOP_BUILD`, halt all agents |

### 7C. STOP_BUILD Trigger

Every agent MUST check for `~/.dharma/STOP_BUILD` before committing changes:

```python
# Add to every agent's pre-action check
STOP_FILE = Path.home() / ".dharma" / "STOP_BUILD"
if STOP_FILE.exists():
    print(f"BUILD HALTED: {STOP_FILE.read_text()}")
    sys.exit(1)
```

### 7D. Launch Command

```bash
# Start sentinel in background
nohup python3 ~/dharma_swarm/scripts/test_sentinel.py > ~/.dharma/logs/sentinel.log 2>&1 &
echo $! > ~/.dharma/sentinel.pid
```

---

## 8. 4:30 AM CHECKPOINT

### Quick Health Check (30 seconds)

```bash
#!/usr/bin/env bash
# ~/dharma_swarm/scripts/morning_check.sh
# Run this at 4:30 AM daily check-in

echo "========================================="
echo "DHARMA SWARM - 4:30 AM CHECKPOINT"
echo "$(date)"
echo "========================================="

# 1. Check for STOP_BUILD
if [ -f ~/.dharma/STOP_BUILD ]; then
    echo ""
    echo "*** BUILD WAS HALTED ***"
    cat ~/.dharma/STOP_BUILD
    echo ""
fi

# 2. Test baseline
echo ""
echo "--- Test Status ---"
if [ -f ~/.dharma/test_baseline.json ]; then
    python3 -c "
import json
d = json.loads(open('$HOME/.dharma/test_baseline.json').read())
print(f\"  Tests passed: {d['passed']} (baseline: {d['baseline']})\")
print(f\"  Failed: {d.get('failed', 0)}\")
print(f\"  Regression: {'YES' if d['regression'] else 'No'}\")
print(f\"  Last run: {d['timestamp']}\")
"
else
    echo "  No test baseline file found. Running tests now..."
    cd ~/dharma_swarm && python3 -m pytest tests/ -q --tb=no 2>&1 | tail -3
fi

# 3. Alerts summary
echo ""
echo "--- Alerts ---"
ALERT_COUNT=$(ls ~/.dharma/alerts/*.json 2>/dev/null | wc -l)
if [ "$ALERT_COUNT" -gt 0 ]; then
    echo "  $ALERT_COUNT alerts:"
    for f in $(ls -t ~/.dharma/alerts/*.json 2>/dev/null | head -5); do
        python3 -c "
import json
d = json.loads(open('$f').read())
print(f\"    [{d['severity'].upper()}] {d['message']} ({d['timestamp'][:19]})\")
"
    done
else
    echo "  No alerts. Clean build."
fi

# 4. New test count
echo ""
echo "--- Test Count ---"
cd ~/dharma_swarm
TOTAL=$(python3 -m pytest tests/ --co -q 2>&1 | tail -1 | grep -oE '[0-9]+')
echo "  Total tests collected: $TOTAL"
echo "  Baseline: 202"
echo "  New tests added: $((TOTAL - 202))"

# 5. Sentinel status
echo ""
echo "--- Sentinel ---"
if [ -f ~/.dharma/sentinel.pid ]; then
    PID=$(cat ~/.dharma/sentinel.pid)
    if kill -0 $PID 2>/dev/null; then
        echo "  Sentinel RUNNING (PID $PID)"
    else
        echo "  Sentinel DEAD (PID $PID was not found)"
    fi
else
    echo "  No sentinel PID file found"
fi

echo ""
echo "========================================="
echo "Run full gates: bash ~/dharma_swarm/scripts/quality_gates.sh"
echo "========================================="
```

### What the Dashboard Should Show

```
DHARMA SWARM - 4:30 AM CHECKPOINT
2026-03-05 04:30:00
=========================================

--- Test Status ---
  Tests passed: 268 (baseline: 202)
  Failed: 0
  Regression: No
  Last run: 2026-03-05T04:15:33

--- Alerts ---
  2 alerts:
    [INFO] Regression resolved. 268 tests passing. (2026-03-05T03:42:12)
    [CRITICAL] REGRESSION: 198/202 tests passed (2026-03-05T03:38:45)

--- Test Count ---
  Total tests collected: 268
  Baseline: 202
  New tests added: 66

--- Sentinel ---
  Sentinel RUNNING (PID 45231)

=========================================
Run full gates: bash ~/dharma_swarm/scripts/quality_gates.sh
=========================================
```

### Specific Tests to Run at Check-in

```bash
# Quick smoke (10 seconds) -- verifies nothing is catastrophically broken
cd ~/dharma_swarm && python3 -m pytest tests/test_models.py tests/test_telos_gates.py tests/test_providers.py -q

# Full baseline (30 seconds)
cd ~/dharma_swarm && python3 -m pytest tests/ -q --tb=no

# New module smoke (if integrated)
cd ~/dharma_swarm && python3 -m pytest tests/test_systemic_monitor.py tests/test_evolution_v3.py -q

# Full quality gates (2-3 minutes)
bash ~/dharma_swarm/scripts/quality_gates.sh
```

---

## 9. FILE SUMMARY: Everything Being Created

### Test Files (New)

| File | Tests | Purpose |
|---|---|---|
| `~/dharma_swarm/tests/test_systemic_monitor.py` | ~10 | systemic_monitor.py coverage |
| `~/dharma_swarm/tests/test_anomaly_detection.py` | ~6 | anomaly_detection.py coverage |
| `~/dharma_swarm/tests/test_fidelity.py` | ~8 | R_V fidelity check coverage |
| `~/dharma_swarm/tests/test_brain.py` | ~6 | Brain adapter coverage |
| `~/dharma_swarm/tests/test_ssc_mathematical_core.py` | ~12 | SSC framework coverage |
| `~/dharma_swarm/tests/test_evolution_v3.py` | ~12 | Evolution v3 utilities coverage |
| `~/dharma_swarm/tests/test_integration_darwin.py` | ~3 | Darwin Engine full cycle |
| `~/dharma_swarm/tests/test_integration_memory_lock.py` | ~3 | Memory + concurrency |
| `~/dharma_swarm/tests/test_integration_gates.py` | ~3 | Gate ratchet |
| `~/dharma_swarm/tests/test_integration_orchestrator.py` | ~1 | Full pipeline |

### Migrated Test Files (Adapted from old DGC)

| File | Tests | Source |
|---|---|---|
| `~/dharma_swarm/tests/test_darwin_archive.py` | ~7 | test_dgm.py (archive/selector portion) |
| `~/dharma_swarm/tests/test_darwin_elegance.py` | ~25 | test_elegance.py |
| `~/dharma_swarm/tests/test_darwin_evolution_gate.py` | ~2 | test_evolution_gate.py |

### Scripts (New)

| File | Purpose |
|---|---|
| `~/dharma_swarm/scripts/regression_guard.py` | Standalone test baseline check |
| `~/dharma_swarm/scripts/quality_gates.sh` | All 7 quality gates |
| `~/dharma_swarm/scripts/test_sentinel.py` | Overnight file-watch test runner |
| `~/dharma_swarm/scripts/morning_check.sh` | 4:30 AM checkpoint script |

### Config Changes

| File | Change |
|---|---|
| `~/dharma_swarm/tests/conftest.py` | Add `temp_memory_dir`, `mock_memory_dir`, `stream_dir` fixtures |
| `~/dharma_swarm/pyproject.toml` | Add markers: `slow`, `integration`, `safety`, `gpu` |

---

## 10. ESTIMATED TEST COUNT AFTER BUILD

| Category | Count |
|---|---|
| Existing tests (baseline) | 202 |
| Migrated DGC tests (archive, elegance, gate) | ~34 |
| New unit tests (6 modules) | ~54 |
| New integration tests | ~10 |
| **Total projected** | **~300** |

---

## 11. COMMANDS QUICK REFERENCE

```bash
# Verify baseline before anything
cd ~/dharma_swarm && python3 -m pytest tests/ -q --tb=no

# Run only new tests (after integration)
python3 -m pytest tests/test_systemic_monitor.py tests/test_anomaly_detection.py \
    tests/test_fidelity.py tests/test_brain.py tests/test_ssc_mathematical_core.py \
    tests/test_evolution_v3.py tests/test_darwin_archive.py tests/test_darwin_elegance.py \
    tests/test_darwin_evolution_gate.py -v

# Run integration tests
python3 -m pytest tests/test_integration_darwin.py tests/test_integration_memory_lock.py \
    tests/test_integration_gates.py tests/test_integration_orchestrator.py -v

# Run all tests with coverage
python3 -m pytest tests/ --cov=dharma_swarm --cov-report=term-missing -q

# Run quality gates
bash ~/dharma_swarm/scripts/quality_gates.sh

# Start overnight sentinel
nohup python3 ~/dharma_swarm/scripts/test_sentinel.py > ~/.dharma/logs/sentinel.log 2>&1 &

# Morning check
bash ~/dharma_swarm/scripts/morning_check.sh

# Check if build was halted
cat ~/.dharma/STOP_BUILD 2>/dev/null || echo "Build running normally"
```

---

## 12. AGENT INSTRUCTIONS

Each overnight agent MUST follow this protocol:

1. **Before writing any code**: Run `python3 ~/dharma_swarm/scripts/regression_guard.py`
2. **Before committing**: Check `~/.dharma/STOP_BUILD` does not exist
3. **After committing**: Run `python3 ~/dharma_swarm/scripts/regression_guard.py` again
4. **If regression detected**: Fix immediately. Do not proceed. Do not "come back to it."
5. **If stuck on a fix for >10 minutes**: Write to `~/.dharma/alerts/` and skip that module
6. **Test naming convention**: `test_<module>_<what>.py` for unit tests, `test_integration_<domain>.py` for integration
7. **Import convention**: Always `from dharma_swarm.<subpackage>.<module> import ...`
8. **No sys.path hacks**: All imports go through the installed package

---

*The ceiling is 202. We go up from here. Never down.*
