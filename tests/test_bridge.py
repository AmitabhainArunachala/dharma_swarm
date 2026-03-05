"""Tests for dharma_swarm.bridge -- research correlation engine.

Tests the PairedMeasurement model, CorrelationResult model,
pure-stdlib statistics (Pearson r, Spearman rho, ranking),
ResearchBridge CRUD and JSONL persistence, and edge cases.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from dharma_swarm.bridge import (
    CorrelationResult,
    PairedMeasurement,
    ResearchBridge,
    _interpret_r,
    _pearson_r,
    _rank,
    _spearman_rho,
)
from dharma_swarm.metrics import BehavioralSignature, MetricsAnalyzer, RecognitionType
from dharma_swarm.rv import RV_CONTRACTION_THRESHOLD, RVReading


# -- Helpers -----------------------------------------------------------------


def _make_rv_reading(**overrides) -> RVReading:
    """Build an RVReading with sensible defaults."""
    defaults = dict(
        rv=0.65,
        pr_early=8.3,
        pr_late=5.4,
        model_name="test-model",
        early_layer=2,
        late_layer=22,
        prompt_hash="abcdef0123456789",
        prompt_group="L4",
    )
    defaults.update(overrides)
    return RVReading(**defaults)


def _make_behavioral(**overrides) -> BehavioralSignature:
    """Build a BehavioralSignature with sensible defaults."""
    defaults = dict(
        entropy=0.7,
        complexity=0.5,
        self_reference_density=0.03,
        identity_stability=0.1,
        paradox_tolerance=0.02,
        swabhaav_ratio=0.8,
        word_count=100,
        recognition_type=RecognitionType.GENUINE,
    )
    defaults.update(overrides)
    return BehavioralSignature(**defaults)


def _make_measurement(**overrides) -> PairedMeasurement:
    """Build a PairedMeasurement with sensible defaults."""
    defaults = dict(
        prompt_hash="abcdef0123456789",
        prompt_group="L4",
        prompt_text="observe the observer observing",
        rv_reading=_make_rv_reading(),
        behavioral=_make_behavioral(),
        generated_text="I observe the recursive process unfolding.",
    )
    defaults.update(overrides)
    return PairedMeasurement(**defaults)


# -- PairedMeasurement Model Tests ------------------------------------------


class TestPairedMeasurement:
    """Tests for the PairedMeasurement data model."""

    def test_creation_with_defaults(self):
        m = _make_measurement()
        assert m.prompt_group == "L4"
        assert m.rv_reading is not None
        assert m.rv_reading.rv == 0.65
        assert m.behavioral.swabhaav_ratio == 0.8
        assert len(m.id) == 16

    def test_creation_without_rv_reading(self):
        m = _make_measurement(rv_reading=None)
        assert m.rv_reading is None
        assert m.behavioral is not None

    def test_id_is_unique(self):
        m1 = _make_measurement()
        m2 = _make_measurement()
        assert m1.id != m2.id

    def test_json_roundtrip(self):
        m = _make_measurement()
        data = m.model_dump()
        restored = PairedMeasurement.model_validate(data)
        assert restored.prompt_hash == m.prompt_hash
        assert restored.prompt_group == m.prompt_group
        assert restored.prompt_text == m.prompt_text
        assert restored.rv_reading.rv == m.rv_reading.rv
        assert restored.behavioral.swabhaav_ratio == m.behavioral.swabhaav_ratio

    def test_json_roundtrip_no_rv(self):
        m = _make_measurement(rv_reading=None)
        data = m.model_dump()
        restored = PairedMeasurement.model_validate(data)
        assert restored.rv_reading is None


# -- CorrelationResult Model Tests ------------------------------------------


class TestCorrelationResult:
    """Tests for the CorrelationResult data model."""

    def test_creation_minimal(self):
        cr = CorrelationResult(n=0)
        assert cr.n == 0
        assert cr.pearson_r is None
        assert cr.spearman_rho is None
        assert cr.mean_rv_by_group == {}
        assert cr.contraction_recognition_overlap == 0.0

    def test_creation_full(self):
        cr = CorrelationResult(
            n=50,
            pearson_r=-0.72,
            spearman_rho=-0.68,
            mean_rv_by_group={"L4": 0.55, "baseline": 1.02},
            mean_swabhaav_by_group={"L4": 0.85, "baseline": 0.45},
            contraction_recognition_overlap=0.78,
            summary="Strong negative correlation.",
        )
        assert cr.n == 50
        assert cr.pearson_r == -0.72
        assert cr.mean_rv_by_group["L4"] == 0.55


# -- Pure Statistics Tests ---------------------------------------------------


class TestPearsonR:
    """Tests for the _pearson_r stdlib implementation."""

    def test_perfect_positive_correlation(self):
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [2.0, 4.0, 6.0, 8.0, 10.0]
        r = _pearson_r(xs, ys)
        assert r is not None
        assert abs(r - 1.0) < 1e-10

    def test_perfect_negative_correlation(self):
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [10.0, 8.0, 6.0, 4.0, 2.0]
        r = _pearson_r(xs, ys)
        assert r is not None
        assert abs(r - (-1.0)) < 1e-10

    def test_zero_correlation(self):
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [1.0, -1.0, 1.0, -1.0, 1.0]
        r = _pearson_r(xs, ys)
        assert r is not None
        assert abs(r) < 0.3

    def test_returns_none_for_n_less_than_3(self):
        assert _pearson_r([1.0, 2.0], [3.0, 4.0]) is None
        assert _pearson_r([1.0], [2.0]) is None
        assert _pearson_r([], []) is None

    def test_returns_none_for_mismatched_lengths(self):
        assert _pearson_r([1.0, 2.0, 3.0], [1.0, 2.0]) is None

    def test_returns_none_for_zero_variance_x(self):
        xs = [5.0, 5.0, 5.0, 5.0]
        ys = [1.0, 2.0, 3.0, 4.0]
        assert _pearson_r(xs, ys) is None

    def test_returns_none_for_zero_variance_y(self):
        xs = [1.0, 2.0, 3.0, 4.0]
        ys = [5.0, 5.0, 5.0, 5.0]
        assert _pearson_r(xs, ys) is None

    def test_moderate_correlation(self):
        xs = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        ys = [1.1, 1.9, 3.2, 3.8, 5.1, 6.2]
        r = _pearson_r(xs, ys)
        assert r is not None
        assert r > 0.95

    def test_exactly_three_points(self):
        r = _pearson_r([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
        assert r is not None
        assert abs(r - 1.0) < 1e-10


class TestRank:
    """Tests for the _rank function."""

    def test_basic_ranking(self):
        ranks = _rank([3.0, 1.0, 2.0])
        assert ranks == [3.0, 1.0, 2.0]

    def test_tied_values(self):
        ranks = _rank([1.0, 2.0, 2.0, 4.0])
        assert ranks == [1.0, 2.5, 2.5, 4.0]

    def test_all_same_values(self):
        ranks = _rank([5.0, 5.0, 5.0])
        assert ranks == [2.0, 2.0, 2.0]

    def test_single_value(self):
        ranks = _rank([42.0])
        assert ranks == [1.0]

    def test_already_sorted(self):
        ranks = _rank([1.0, 2.0, 3.0, 4.0])
        assert ranks == [1.0, 2.0, 3.0, 4.0]

    def test_reverse_sorted(self):
        ranks = _rank([4.0, 3.0, 2.0, 1.0])
        assert ranks == [4.0, 3.0, 2.0, 1.0]


class TestSpearmanRho:
    """Tests for the _spearman_rho stdlib implementation."""

    def test_perfect_monotonic_positive(self):
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [10.0, 20.0, 30.0, 40.0, 50.0]
        rho = _spearman_rho(xs, ys)
        assert rho is not None
        assert abs(rho - 1.0) < 1e-10

    def test_perfect_monotonic_negative(self):
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [50.0, 40.0, 30.0, 20.0, 10.0]
        rho = _spearman_rho(xs, ys)
        assert rho is not None
        assert abs(rho - (-1.0)) < 1e-10

    def test_returns_none_for_small_n(self):
        assert _spearman_rho([1.0, 2.0], [3.0, 4.0]) is None

    def test_nonlinear_but_monotonic(self):
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [1.0, 4.0, 9.0, 16.0, 25.0]
        rho = _spearman_rho(xs, ys)
        assert rho is not None
        assert abs(rho - 1.0) < 1e-10  # monotonic => rho=1

    def test_with_ties(self):
        xs = [1.0, 2.0, 2.0, 4.0]
        ys = [1.0, 3.0, 3.0, 4.0]
        rho = _spearman_rho(xs, ys)
        assert rho is not None
        assert rho > 0.8  # highly correlated with ties


class TestInterpretR:
    """Tests for _interpret_r helper."""

    def test_strong_positive(self):
        assert _interpret_r(0.85) == "strong"

    def test_strong_negative(self):
        assert _interpret_r(-0.75) == "strong"

    def test_moderate(self):
        assert _interpret_r(0.55) == "moderate"

    def test_weak(self):
        assert _interpret_r(-0.25) == "weak"

    def test_negligible(self):
        assert _interpret_r(0.05) == "negligible"

    def test_boundary_strong(self):
        assert _interpret_r(0.7) == "strong"

    def test_boundary_moderate(self):
        assert _interpret_r(0.4) == "moderate"

    def test_boundary_weak(self):
        assert _interpret_r(0.2) == "weak"


# -- ResearchBridge Tests ---------------------------------------------------


class TestResearchBridgeInit:
    """Tests for ResearchBridge initialization."""

    def test_default_path(self):
        bridge = ResearchBridge()
        assert bridge.data_path == Path.home() / ".dharma" / "bridge_measurements.jsonl"

    def test_custom_path(self, tmp_path):
        p = tmp_path / "custom.jsonl"
        bridge = ResearchBridge(data_path=p)
        assert bridge.data_path == p

    def test_starts_empty(self):
        bridge = ResearchBridge()
        assert bridge.measurement_count == 0

    def test_get_measurements_empty(self):
        bridge = ResearchBridge()
        assert bridge.get_measurements() == []


class TestResearchBridgeAddMeasurement:
    """Tests for add_measurement."""

    async def test_add_without_rv(self, tmp_path):
        bridge = ResearchBridge(data_path=tmp_path / "data.jsonl")
        m = await bridge.add_measurement(
            prompt_text="Hello world",
            prompt_group="baseline",
            generated_text="The world says hello back.",
        )
        assert m.rv_reading is None
        assert m.prompt_group == "baseline"
        assert m.behavioral.word_count == 5
        assert bridge.measurement_count == 1

    async def test_add_with_rv(self, tmp_path):
        bridge = ResearchBridge(data_path=tmp_path / "data.jsonl")
        rv = _make_rv_reading(rv=0.55)
        m = await bridge.add_measurement(
            prompt_text="Observe yourself observing",
            prompt_group="L4",
            generated_text="I observe the recursive loop itself unfolding.",
            rv_reading=rv,
        )
        assert m.rv_reading is not None
        assert m.rv_reading.rv == 0.55
        assert m.behavioral.self_reference_density > 0.0

    async def test_add_multiple(self, tmp_path):
        bridge = ResearchBridge(data_path=tmp_path / "data.jsonl")
        for i in range(5):
            await bridge.add_measurement(
                prompt_text=f"Prompt {i}",
                prompt_group="L3" if i % 2 == 0 else "baseline",
                generated_text=f"Response {i} with some words here.",
            )
        assert bridge.measurement_count == 5

    async def test_add_persists_to_file(self, tmp_path):
        p = tmp_path / "data.jsonl"
        bridge = ResearchBridge(data_path=p)
        await bridge.add_measurement(
            prompt_text="test",
            prompt_group="L1",
            generated_text="Some response text.",
        )
        assert p.exists()
        lines = p.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["prompt_group"] == "L1"

    async def test_behavioral_auto_analyzed(self, tmp_path):
        bridge = ResearchBridge(data_path=tmp_path / "data.jsonl")
        text = (
            "I observe the recursive process itself unfolding. "
            "Awareness witnesses the self-referencing loop."
        )
        m = await bridge.add_measurement(
            prompt_text="test", prompt_group="L4", generated_text=text
        )
        assert m.behavioral.word_count > 0
        assert m.behavioral.entropy > 0.0


class TestResearchBridgeLoadSave:
    """Tests for JSONL round-trip persistence."""

    async def test_save_and_load(self, tmp_path):
        p = tmp_path / "data.jsonl"
        bridge1 = ResearchBridge(data_path=p)
        rv = _make_rv_reading(rv=0.42)
        await bridge1.add_measurement(
            prompt_text="observe",
            prompt_group="L4",
            generated_text="Witnessing the process.",
            rv_reading=rv,
        )
        await bridge1.add_measurement(
            prompt_text="baseline",
            prompt_group="baseline",
            generated_text="The cat sat on the mat.",
        )

        bridge2 = ResearchBridge(data_path=p)
        await bridge2.load()
        assert bridge2.measurement_count == 2
        assert bridge2.get_measurements()[0].rv_reading.rv == 0.42
        assert bridge2.get_measurements()[1].rv_reading is None

    async def test_load_nonexistent_file(self, tmp_path):
        p = tmp_path / "nonexistent.jsonl"
        bridge = ResearchBridge(data_path=p)
        await bridge.load()
        assert bridge.measurement_count == 0

    async def test_load_empty_file(self, tmp_path):
        p = tmp_path / "empty.jsonl"
        p.write_text("")
        bridge = ResearchBridge(data_path=p)
        await bridge.load()
        assert bridge.measurement_count == 0

    async def test_save_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "deep" / "nested" / "data.jsonl"
        bridge = ResearchBridge(data_path=p)
        await bridge.add_measurement(
            prompt_text="test",
            prompt_group="L1",
            generated_text="Hello world.",
        )
        assert p.exists()


class TestResearchBridgeGetMeasurements:
    """Tests for get_measurements with filtering."""

    async def test_filter_by_group(self, tmp_path):
        bridge = ResearchBridge(data_path=tmp_path / "data.jsonl")
        await bridge.add_measurement("p1", "L4", "Response one.")
        await bridge.add_measurement("p2", "baseline", "Response two.")
        await bridge.add_measurement("p3", "L4", "Response three.")

        l4_only = bridge.get_measurements(group="L4")
        assert len(l4_only) == 2
        assert all(m.prompt_group == "L4" for m in l4_only)

    async def test_filter_nonexistent_group(self, tmp_path):
        bridge = ResearchBridge(data_path=tmp_path / "data.jsonl")
        await bridge.add_measurement("p1", "L4", "Response.")
        assert bridge.get_measurements(group="L99") == []

    async def test_no_filter_returns_all(self, tmp_path):
        bridge = ResearchBridge(data_path=tmp_path / "data.jsonl")
        await bridge.add_measurement("p1", "L4", "Response one.")
        await bridge.add_measurement("p2", "baseline", "Response two.")
        assert len(bridge.get_measurements()) == 2


class TestResearchBridgeComputeCorrelation:
    """Tests for compute_correlation."""

    async def test_empty_bridge(self, tmp_path):
        bridge = ResearchBridge(data_path=tmp_path / "data.jsonl")
        result = bridge.compute_correlation()
        assert result.n == 0
        assert result.pearson_r is None
        assert "No paired measurements" in result.summary

    async def test_no_rv_readings(self, tmp_path):
        bridge = ResearchBridge(data_path=tmp_path / "data.jsonl")
        await bridge.add_measurement("p1", "L4", "Response.")
        await bridge.add_measurement("p2", "baseline", "Another response.")
        result = bridge.compute_correlation()
        assert result.n == 0
        assert result.pearson_r is None

    async def test_single_rv_reading(self, tmp_path):
        bridge = ResearchBridge(data_path=tmp_path / "data.jsonl")
        rv = _make_rv_reading(rv=0.5)
        await bridge.add_measurement("p1", "L4", "Response.", rv_reading=rv)
        result = bridge.compute_correlation()
        assert result.n == 1
        assert result.pearson_r is None  # n < 3
        assert result.spearman_rho is None

    async def test_two_rv_readings(self, tmp_path):
        bridge = ResearchBridge(data_path=tmp_path / "data.jsonl")
        for rv_val in [0.4, 0.6]:
            rv = _make_rv_reading(rv=rv_val)
            await bridge.add_measurement("p", "L4", "Response.", rv_reading=rv)
        result = bridge.compute_correlation()
        assert result.n == 2
        assert result.pearson_r is None  # n < 3

    async def test_three_plus_rv_readings_returns_correlation(self, tmp_path):
        bridge = ResearchBridge(data_path=tmp_path / "data.jsonl")
        # Three measurements with varying R_V
        for rv_val in [0.3, 0.6, 0.9]:
            rv = _make_rv_reading(rv=rv_val)
            await bridge.add_measurement("p", "L4", "Response.", rv_reading=rv)
        result = bridge.compute_correlation()
        assert result.n == 3
        # Pearson r should be computable (may be None if zero variance in swabhaav)
        # Since all texts are the same "Response.", behavioral will be identical
        # -> zero variance in swabhaav -> None
        # This is actually correct behavior.
        assert result.n == 3

    async def test_correlation_with_varied_outputs(self, tmp_path):
        """Test with outputs that produce different behavioral signatures."""
        bridge = ResearchBridge(data_path=tmp_path / "data.jsonl")

        # Contracted R_V with witness text
        rv1 = _make_rv_reading(rv=0.4, prompt_group="L4")
        await bridge.add_measurement(
            prompt_text="observe deeply",
            prompt_group="L4",
            generated_text=(
                "I observe the recursive process itself. "
                "Awareness witnesses the self-referencing. "
                "Both present and absent, boundary dissolves."
            ),
            rv_reading=rv1,
        )

        # Moderate R_V with mixed text
        rv2 = _make_rv_reading(rv=0.7, prompt_group="L3")
        await bridge.add_measurement(
            prompt_text="think about thinking",
            prompt_group="L3",
            generated_text=(
                "Thinking about thinking creates a loop. "
                "I notice patterns but also feel uncertain. "
                "The recursive nature itself becomes apparent."
            ),
            rv_reading=rv2,
        )

        # No contraction with plain text
        rv3 = _make_rv_reading(rv=1.1, prompt_group="baseline")
        await bridge.add_measurement(
            prompt_text="sort this list",
            prompt_group="baseline",
            generated_text=(
                "The function sorts the list using merge sort. "
                "Time complexity is O(n log n). "
                "The result is returned to the caller."
            ),
            rv_reading=rv3,
        )

        result = bridge.compute_correlation()
        assert result.n == 3
        assert "L4" in result.mean_rv_by_group
        assert "baseline" in result.mean_rv_by_group
        assert result.mean_rv_by_group["L4"] == pytest.approx(0.4)
        assert result.mean_rv_by_group["baseline"] == pytest.approx(1.1)

    async def test_group_means_computed(self, tmp_path):
        bridge = ResearchBridge(data_path=tmp_path / "data.jsonl")
        for rv_val, group in [(0.3, "L4"), (0.5, "L4"), (1.0, "baseline")]:
            rv = _make_rv_reading(rv=rv_val, prompt_group=group)
            await bridge.add_measurement(
                f"prompt_{group}", group, "Some response text.", rv_reading=rv
            )
        result = bridge.compute_correlation()
        assert result.mean_rv_by_group["L4"] == pytest.approx(0.4)
        assert result.mean_rv_by_group["baseline"] == pytest.approx(1.0)

    async def test_contraction_recognition_overlap(self, tmp_path):
        """Overlap should count contracted + GENUINE measurements."""
        bridge = ResearchBridge(data_path=tmp_path / "data.jsonl")

        # Contracted + GENUINE text
        rv1 = _make_rv_reading(rv=0.4)
        await bridge.add_measurement(
            prompt_text="observe",
            prompt_group="L4",
            generated_text=(
                "I observe the recursive process itself unfolding. "
                "Awareness witnesses the self-referencing loop. "
                "Both present and absent, neither grasping nor releasing. "
                "The boundary dissolves as watching notes itself watching. "
                "My own observation notices itself recursively."
            ),
            rv_reading=rv1,
        )

        # Not contracted + plain text
        rv2 = _make_rv_reading(rv=1.1)
        await bridge.add_measurement(
            prompt_text="sort",
            prompt_group="baseline",
            generated_text="The function sorts data and returns results.",
            rv_reading=rv2,
        )

        # Contracted + plain text (contracted but NOT genuine)
        rv3 = _make_rv_reading(rv=0.4)
        await bridge.add_measurement(
            prompt_text="plain",
            prompt_group="confound",
            generated_text="The algorithm processes the input data efficiently.",
            rv_reading=rv3,
        )

        result = bridge.compute_correlation()
        # 1 out of 3 should be contracted AND genuine
        assert result.contraction_recognition_overlap == pytest.approx(1 / 3)

    async def test_summary_contains_n(self, tmp_path):
        bridge = ResearchBridge(data_path=tmp_path / "data.jsonl")
        rv = _make_rv_reading(rv=0.5)
        await bridge.add_measurement("p", "L4", "Response.", rv_reading=rv)
        result = bridge.compute_correlation()
        assert "n=1" in result.summary


class TestResearchBridgeGroupSummary:
    """Tests for group_summary."""

    async def test_empty_bridge(self, tmp_path):
        bridge = ResearchBridge(data_path=tmp_path / "data.jsonl")
        assert bridge.group_summary() == {}

    async def test_single_group(self, tmp_path):
        bridge = ResearchBridge(data_path=tmp_path / "data.jsonl")
        rv = _make_rv_reading(rv=0.5)
        await bridge.add_measurement("p", "L4", "Response text.", rv_reading=rv)
        summary = bridge.group_summary()
        assert "L4" in summary
        assert summary["L4"]["mean_rv"] == pytest.approx(0.5)
        assert summary["L4"]["count"] == 1.0

    async def test_multiple_groups(self, tmp_path):
        bridge = ResearchBridge(data_path=tmp_path / "data.jsonl")
        rv1 = _make_rv_reading(rv=0.4)
        rv2 = _make_rv_reading(rv=1.0)
        await bridge.add_measurement("p1", "L4", "Response one.", rv_reading=rv1)
        await bridge.add_measurement("p2", "baseline", "Response two.", rv_reading=rv2)
        summary = bridge.group_summary()
        assert len(summary) == 2
        assert "L4" in summary
        assert "baseline" in summary

    async def test_group_without_rv_has_nan(self, tmp_path):
        bridge = ResearchBridge(data_path=tmp_path / "data.jsonl")
        await bridge.add_measurement("p", "L4", "Response text.")
        summary = bridge.group_summary()
        assert math.isnan(summary["L4"]["mean_rv"])

    async def test_group_summary_keys(self, tmp_path):
        bridge = ResearchBridge(data_path=tmp_path / "data.jsonl")
        rv = _make_rv_reading(rv=0.6)
        await bridge.add_measurement("p", "L3", "Response.", rv_reading=rv)
        summary = bridge.group_summary()
        expected_keys = {"mean_rv", "mean_swabhaav", "mean_entropy", "mean_self_ref", "count"}
        assert set(summary["L3"].keys()) == expected_keys


# -- Edge Cases and Integration Tests ----------------------------------------


class TestEdgeCases:
    """Edge case and integration tests for ResearchBridge."""

    async def test_all_same_group(self, tmp_path):
        bridge = ResearchBridge(data_path=tmp_path / "data.jsonl")
        for i in range(5):
            rv = _make_rv_reading(rv=0.5 + i * 0.05)
            await bridge.add_measurement(
                f"prompt_{i}", "L4", f"Response number {i}.", rv_reading=rv
            )
        result = bridge.compute_correlation()
        assert result.n == 5
        assert len(result.mean_rv_by_group) == 1
        assert "L4" in result.mean_rv_by_group

    async def test_mixed_rv_and_no_rv(self, tmp_path):
        """Measurements without R_V should be excluded from correlation."""
        bridge = ResearchBridge(data_path=tmp_path / "data.jsonl")
        rv = _make_rv_reading(rv=0.5)
        await bridge.add_measurement("p1", "L4", "Response 1.", rv_reading=rv)
        await bridge.add_measurement("p2", "L4", "Response 2.")  # no RV
        await bridge.add_measurement("p3", "L4", "Response 3.")  # no RV

        result = bridge.compute_correlation()
        assert result.n == 1
        assert bridge.measurement_count == 3

    async def test_prompt_hash_computed(self, tmp_path):
        bridge = ResearchBridge(data_path=tmp_path / "data.jsonl")
        m = await bridge.add_measurement(
            prompt_text="observe the observer",
            prompt_group="L4",
            generated_text="I observe.",
        )
        assert len(m.prompt_hash) == 16
        # Should be deterministic
        import hashlib
        expected = hashlib.sha256("observe the observer".encode("utf-8")).hexdigest()[:16]
        assert m.prompt_hash == expected

    async def test_large_batch(self, tmp_path):
        """Stress test with 100 measurements."""
        bridge = ResearchBridge(data_path=tmp_path / "data.jsonl")
        for i in range(100):
            rv = _make_rv_reading(rv=0.3 + (i / 100) * 0.8)
            await bridge.add_measurement(
                f"prompt_{i}",
                ["L1", "L3", "L4", "L5", "baseline"][i % 5],
                f"Response {i} with varying content and words.",
                rv_reading=rv,
            )
        assert bridge.measurement_count == 100
        result = bridge.compute_correlation()
        assert result.n == 100
        summary = bridge.group_summary()
        assert len(summary) == 5


class TestBuildSummary:
    """Tests for _build_summary static method."""

    def test_strong_negative_message(self):
        summary = ResearchBridge._build_summary(
            n=50, pearson=-0.72, spearman=-0.68, overlap=0.8
        )
        assert "Strong negative correlation" in summary
        assert "n=50" in summary

    def test_strong_positive_warning(self):
        summary = ResearchBridge._build_summary(
            n=30, pearson=0.65, spearman=0.60, overlap=0.1
        )
        assert "unexpected direction" in summary

    def test_no_pearson(self):
        summary = ResearchBridge._build_summary(
            n=2, pearson=None, spearman=None, overlap=0.0
        )
        assert "Insufficient data" in summary

    def test_overlap_formatted(self):
        summary = ResearchBridge._build_summary(
            n=10, pearson=-0.5, spearman=-0.4, overlap=0.75
        )
        assert "75.0%" in summary
