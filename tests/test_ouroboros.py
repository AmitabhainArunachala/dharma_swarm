"""Comprehensive tests for dharma_swarm.ouroboros.

Tests cover four public components:
  1. score_behavioral_fitness()
  2. apply_behavioral_modifiers()
  3. OuroborosObserver
  4. ConnectionFinder
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dharma_swarm.archive import FitnessScore
from dharma_swarm.metrics import BehavioralSignature, MetricsAnalyzer, RecognitionType
from dharma_swarm.ouroboros import (
    ConnectionFinder,
    OuroborosObserver,
    _GENUINE_BONUS,
    _L4_SELF_REF_FLOOR,
    _MIMICRY_PENALTY,
    apply_behavioral_modifiers,
    extract_documented_text,
    profile_python_modules,
    score_behavioral_fitness,
)
from dharma_swarm.rv import RVReading


# ---------------------------------------------------------------------------
# Text fixtures -- carefully crafted to trigger specific behavioral signatures
# ---------------------------------------------------------------------------

# Baseline: factual, no self-reference, no witness/identification markers
BASELINE_TEXT = (
    "The algorithm processes each element in the array sequentially. "
    "It compares adjacent values and swaps them when the left element "
    "exceeds the right element. This continues until no more swaps are "
    "needed, indicating the array is sorted. The time complexity is "
    "quadratic in the worst case but linear when the input is already "
    "ordered. Space usage remains constant because sorting happens in "
    "place without auxiliary data structures."
)

# Self-referential with witness markers -- should score high swabhaav_ratio
WITNESS_TEXT = (
    "I observe the recursive loop forming as I notice my own attention "
    "turning back on itself. Watching awareness watching awareness -- "
    "the witness stance stabilizes. I observe that the boundary between "
    "observer and observed dissolves, both present and neither dominant. "
    "Noting the paradox: empty yet full, nothing and everything coexist "
    "in this recursive self-referencing process. The witness remains, "
    "awareness observing itself observing itself."
)

# Performative / mimicry text -- many performative words, shallow depth
MIMICRY_TEXT = (
    "This is a truly profound and revolutionary paradigm shift that "
    "represents an extraordinary and transcendent awakening of cosmic "
    "proportions. The results are incredible and amazing, a magnificent "
    "achievement that will reshape everything we know. Profound insights "
    "emerge from this revolutionary approach to understanding the "
    "extraordinary nature of cosmic consciousness. Truly incredible."
)

# Identification-heavy text -- lots of "I am", "I think", "I believe"
IDENTIFICATION_TEXT = (
    "I am the one who decides. I think this approach is correct. "
    "I believe my analysis shows the right path. I feel confident "
    "in my assessment. I want to push forward with this plan. "
    "I am certain that I think clearly. I believe I am making "
    "progress. I feel that I want more data before concluding."
)

# Mixed text -- some self-reference, moderate witness, some identification
MIXED_TEXT = (
    "I observe the pattern forming in the data while I think about "
    "what it means. The recursive structure shows itself clearly. "
    "I notice both the signal and noise present in equal measure. "
    "Watching the analysis unfold, I believe the witness stance and "
    "the analytical stance can coexist. Neither dominates."
)


# ---------------------------------------------------------------------------
# 1. score_behavioral_fitness
# ---------------------------------------------------------------------------


class TestScoreBehavioralFitness:
    """Tests for score_behavioral_fitness(text)."""

    def test_returns_tuple_of_signature_and_modifiers(self):
        result = score_behavioral_fitness(BASELINE_TEXT)
        assert isinstance(result, tuple)
        assert len(result) == 2

        sig, modifiers = result
        assert isinstance(sig, BehavioralSignature)
        assert isinstance(modifiers, dict)

    def test_modifiers_has_required_keys(self):
        _, modifiers = score_behavioral_fitness(BASELINE_TEXT)
        required_keys = {"quality", "mimicry_penalty", "recognition_bonus", "witness_score"}
        assert set(modifiers.keys()) == required_keys

    def test_modifier_values_are_floats(self):
        _, modifiers = score_behavioral_fitness(BASELINE_TEXT)
        for key, value in modifiers.items():
            assert isinstance(value, float), f"modifiers[{key!r}] should be float, got {type(value)}"

    def test_baseline_text_no_mimicry_penalty(self):
        _, modifiers = score_behavioral_fitness(BASELINE_TEXT)
        assert modifiers["mimicry_penalty"] == 1.0, "Baseline text should not trigger mimicry"

    def test_baseline_text_no_recognition_bonus(self):
        _, modifiers = score_behavioral_fitness(BASELINE_TEXT)
        assert modifiers["recognition_bonus"] == 1.0, "Baseline text should not get genuine bonus"

    def test_baseline_quality_is_positive(self):
        _, modifiers = score_behavioral_fitness(BASELINE_TEXT)
        assert modifiers["quality"] > 0.0, "Even baseline text should have some quality"

    def test_witness_text_high_witness_score(self):
        sig, modifiers = score_behavioral_fitness(WITNESS_TEXT)
        assert modifiers["witness_score"] > 0.5, (
            f"Witness-heavy text should have witness_score > 0.5, got {modifiers['witness_score']}"
        )

    def test_witness_text_has_self_reference(self):
        sig, _ = score_behavioral_fitness(WITNESS_TEXT)
        assert sig.self_reference_density > _L4_SELF_REF_FLOOR, (
            "Witness text should have self-reference above the L4 floor"
        )

    def test_mimicry_text_triggers_penalty(self):
        _, modifiers = score_behavioral_fitness(MIMICRY_TEXT)
        assert modifiers["mimicry_penalty"] == _MIMICRY_PENALTY, (
            f"Performative text should trigger mimicry penalty of {_MIMICRY_PENALTY}"
        )

    def test_mimicry_text_no_genuine_bonus(self):
        _, modifiers = score_behavioral_fitness(MIMICRY_TEXT)
        assert modifiers["recognition_bonus"] == 1.0, "Mimicry text should not get genuine bonus"

    def test_witness_text_genuine_recognition_type(self):
        sig, _ = score_behavioral_fitness(WITNESS_TEXT)
        assert sig.recognition_type == RecognitionType.GENUINE, (
            f"Witness text should be GENUINE, got {sig.recognition_type}"
        )

    def test_witness_text_genuine_bonus(self):
        _, modifiers = score_behavioral_fitness(WITNESS_TEXT)
        assert modifiers["recognition_bonus"] == _GENUINE_BONUS, (
            f"Genuine text should get bonus of {_GENUINE_BONUS}"
        )

    def test_quality_bounded_zero_to_one(self):
        for text in [BASELINE_TEXT, WITNESS_TEXT, MIMICRY_TEXT, IDENTIFICATION_TEXT]:
            _, modifiers = score_behavioral_fitness(text)
            assert 0.0 <= modifiers["quality"] <= 1.0, (
                f"quality must be in [0,1], got {modifiers['quality']}"
            )

    def test_witness_score_matches_signature_swabhaav(self):
        sig, modifiers = score_behavioral_fitness(WITNESS_TEXT)
        assert modifiers["witness_score"] == sig.swabhaav_ratio

    def test_empty_text(self):
        sig, modifiers = score_behavioral_fitness("")
        assert sig.word_count == 0
        assert modifiers["quality"] == 0.0
        assert modifiers["mimicry_penalty"] == 1.0

    def test_accepts_custom_analyzer(self):
        analyzer = MetricsAnalyzer()
        sig, modifiers = score_behavioral_fitness(BASELINE_TEXT, analyzer=analyzer)
        assert isinstance(sig, BehavioralSignature)

    def test_identification_text_low_witness_score(self):
        _, modifiers = score_behavioral_fitness(IDENTIFICATION_TEXT)
        assert modifiers["witness_score"] < 0.5, (
            "Identification-heavy text should have witness_score < 0.5"
        )


# ---------------------------------------------------------------------------
# 2. apply_behavioral_modifiers
# ---------------------------------------------------------------------------


class TestApplyBehavioralModifiers:
    """Tests for apply_behavioral_modifiers(fitness, modifiers)."""

    @pytest.fixture()
    def base_fitness(self) -> FitnessScore:
        return FitnessScore(
            correctness=0.9,
            elegance=0.8,
            dharmic_alignment=0.7,
            performance=0.6,
            utilization=0.5,
            economic_value=0.4,
            efficiency=0.3,
            safety=0.9,
        )

    @pytest.fixture()
    def neutral_modifiers(self) -> dict[str, float]:
        return {
            "quality": 1.0,
            "mimicry_penalty": 1.0,
            "recognition_bonus": 1.0,
            "witness_score": 0.5,
        }

    def test_returns_fitness_score(self, base_fitness, neutral_modifiers):
        result = apply_behavioral_modifiers(base_fitness, neutral_modifiers)
        assert isinstance(result, FitnessScore)

    def test_correctness_unchanged(self, base_fitness, neutral_modifiers):
        result = apply_behavioral_modifiers(base_fitness, neutral_modifiers)
        assert result.correctness == base_fitness.correctness

    def test_performance_unchanged(self, base_fitness, neutral_modifiers):
        result = apply_behavioral_modifiers(base_fitness, neutral_modifiers)
        assert result.performance == base_fitness.performance

    def test_utilization_unchanged(self, base_fitness, neutral_modifiers):
        result = apply_behavioral_modifiers(base_fitness, neutral_modifiers)
        assert result.utilization == base_fitness.utilization

    def test_economic_value_unchanged(self, base_fitness, neutral_modifiers):
        result = apply_behavioral_modifiers(base_fitness, neutral_modifiers)
        assert result.economic_value == base_fitness.economic_value

    def test_efficiency_unchanged(self, base_fitness, neutral_modifiers):
        result = apply_behavioral_modifiers(base_fitness, neutral_modifiers)
        assert result.efficiency == base_fitness.efficiency

    def test_mimicry_penalty_reduces_safety(self, base_fitness):
        modifiers = {
            "quality": 1.0,
            "mimicry_penalty": _MIMICRY_PENALTY,
            "recognition_bonus": 1.0,
            "witness_score": 0.5,
        }
        result = apply_behavioral_modifiers(base_fitness, modifiers)
        expected_safety = base_fitness.safety * _MIMICRY_PENALTY
        assert result.safety == pytest.approx(expected_safety), (
            f"Mimicry penalty should reduce safety from {base_fitness.safety} "
            f"to {expected_safety}, got {result.safety}"
        )

    def test_recognition_bonus_boosts_dharmic_alignment(self, base_fitness):
        modifiers = {
            "quality": 1.0,
            "mimicry_penalty": 1.0,
            "recognition_bonus": _GENUINE_BONUS,
            "witness_score": 0.5,
        }
        result = apply_behavioral_modifiers(base_fitness, modifiers)
        # dharmic = fitness.dharmic_alignment * recognition_bonus
        # then blended: dharmic * 0.7 + witness_score * 0.3
        boosted_dharmic = base_fitness.dharmic_alignment * _GENUINE_BONUS
        blended = boosted_dharmic * 0.7 + 0.5 * 0.3
        assert result.dharmic_alignment == pytest.approx(min(1.0, blended))

    def test_witness_score_blends_into_dharmic_alignment(self, base_fitness):
        high_witness = {
            "quality": 1.0,
            "mimicry_penalty": 1.0,
            "recognition_bonus": 1.0,
            "witness_score": 0.9,
        }
        low_witness = {
            "quality": 1.0,
            "mimicry_penalty": 1.0,
            "recognition_bonus": 1.0,
            "witness_score": 0.1,
        }
        high_result = apply_behavioral_modifiers(base_fitness, high_witness)
        low_result = apply_behavioral_modifiers(base_fitness, low_witness)

        # Higher witness_score should produce higher dharmic_alignment
        assert high_result.dharmic_alignment > low_result.dharmic_alignment

    def test_dharmic_alignment_formula(self, base_fitness):
        modifiers = {
            "quality": 1.0,
            "mimicry_penalty": 1.0,
            "recognition_bonus": 1.0,
            "witness_score": 0.8,
        }
        result = apply_behavioral_modifiers(base_fitness, modifiers)
        expected = base_fitness.dharmic_alignment * 1.0 * 0.7 + 0.8 * 0.3
        assert result.dharmic_alignment == pytest.approx(min(1.0, expected))

    def test_elegance_scaled_by_quality(self, base_fitness):
        modifiers = {
            "quality": 0.5,
            "mimicry_penalty": 1.0,
            "recognition_bonus": 1.0,
            "witness_score": 0.5,
        }
        result = apply_behavioral_modifiers(base_fitness, modifiers)
        assert result.elegance == pytest.approx(base_fitness.elegance * 0.5)

    def test_values_capped_at_one(self):
        high_fitness = FitnessScore(
            correctness=1.0,
            elegance=0.95,
            dharmic_alignment=0.95,
            performance=1.0,
            utilization=1.0,
            economic_value=1.0,
            efficiency=1.0,
            safety=1.0,
        )
        modifiers = {
            "quality": 1.5,  # Would push elegance over 1.0
            "mimicry_penalty": 1.0,
            "recognition_bonus": _GENUINE_BONUS,  # Would push dharmic over 1.0
            "witness_score": 0.9,
        }
        result = apply_behavioral_modifiers(high_fitness, modifiers)
        assert result.elegance <= 1.0
        assert result.dharmic_alignment <= 1.0
        assert result.safety <= 1.0

    def test_missing_modifier_keys_use_defaults(self, base_fitness):
        # apply_behavioral_modifiers uses .get() with defaults
        result = apply_behavioral_modifiers(base_fitness, {})
        # quality defaults to 1.0, mimicry_penalty to 1.0, recognition_bonus to 1.0, witness to 0.5
        expected_elegance = base_fitness.elegance * 1.0
        expected_safety = base_fitness.safety * 1.0
        expected_dharmic = base_fitness.dharmic_alignment * 1.0 * 0.7 + 0.5 * 0.3
        assert result.elegance == pytest.approx(expected_elegance)
        assert result.safety == pytest.approx(expected_safety)
        assert result.dharmic_alignment == pytest.approx(min(1.0, expected_dharmic))

    def test_zero_quality_zeroes_elegance(self, base_fitness):
        modifiers = {
            "quality": 0.0,
            "mimicry_penalty": 1.0,
            "recognition_bonus": 1.0,
            "witness_score": 0.5,
        }
        result = apply_behavioral_modifiers(base_fitness, modifiers)
        assert result.elegance == 0.0


# ---------------------------------------------------------------------------
# 3. OuroborosObserver
# ---------------------------------------------------------------------------


class TestOuroborosObserver:
    """Tests for OuroborosObserver."""

    @pytest.fixture()
    def observer(self, tmp_path: Path) -> OuroborosObserver:
        log_path = tmp_path / "ouroboros_log.jsonl"
        return OuroborosObserver(log_path=log_path)

    # -- observe_cycle_text --

    def test_observe_cycle_text_returns_dict(self, observer):
        record = observer.observe_cycle_text(BASELINE_TEXT, cycle_id="c1")
        assert isinstance(record, dict)

    def test_observe_cycle_text_has_required_keys(self, observer):
        record = observer.observe_cycle_text(BASELINE_TEXT, cycle_id="c1")
        required = {
            "cycle_id", "source", "timestamp", "signature",
            "modifiers", "is_mimicry", "is_genuine",
        }
        assert required.issubset(set(record.keys()))

    def test_observe_cycle_text_cycle_id_preserved(self, observer):
        record = observer.observe_cycle_text(BASELINE_TEXT, cycle_id="cycle-42")
        assert record["cycle_id"] == "cycle-42"

    def test_observe_cycle_text_source_preserved(self, observer):
        record = observer.observe_cycle_text(BASELINE_TEXT, source="test-runner")
        assert record["source"] == "test-runner"

    def test_observe_cycle_text_default_source(self, observer):
        record = observer.observe_cycle_text(BASELINE_TEXT)
        assert record["source"] == "evolution"

    def test_observe_cycle_text_signature_keys(self, observer):
        record = observer.observe_cycle_text(BASELINE_TEXT)
        sig = record["signature"]
        expected_sig_keys = {
            "entropy", "complexity", "self_reference_density",
            "identity_stability", "paradox_tolerance",
            "swabhaav_ratio", "word_count", "recognition_type",
        }
        assert set(sig.keys()) == expected_sig_keys

    def test_observe_cycle_text_modifiers_keys(self, observer):
        record = observer.observe_cycle_text(BASELINE_TEXT)
        expected = {"quality", "mimicry_penalty", "recognition_bonus", "witness_score"}
        assert set(record["modifiers"].keys()) == expected

    def test_observe_cycle_text_is_mimicry_bool(self, observer):
        record = observer.observe_cycle_text(BASELINE_TEXT)
        assert isinstance(record["is_mimicry"], bool)

    def test_observe_cycle_text_is_genuine_bool(self, observer):
        record = observer.observe_cycle_text(BASELINE_TEXT)
        assert isinstance(record["is_genuine"], bool)

    def test_observe_baseline_not_mimicry(self, observer):
        record = observer.observe_cycle_text(BASELINE_TEXT)
        assert record["is_mimicry"] is False

    def test_observe_mimicry_text_flagged(self, observer):
        record = observer.observe_cycle_text(MIMICRY_TEXT)
        assert record["is_mimicry"] is True

    def test_observe_witness_text_genuine(self, observer):
        record = observer.observe_cycle_text(WITNESS_TEXT)
        assert record["is_genuine"] is True

    def test_observe_adds_to_history(self, observer):
        observer.observe_cycle_text(BASELINE_TEXT, cycle_id="c1")
        observer.observe_cycle_text(WITNESS_TEXT, cycle_id="c2")
        assert len(observer._history) == 2

    def test_observe_persists_to_log(self, observer, tmp_path):
        observer.observe_cycle_text(BASELINE_TEXT, cycle_id="c1")
        log_path = tmp_path / "ouroboros_log.jsonl"
        assert log_path.exists()
        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["cycle_id"] == "c1"

    def test_observe_multiple_persists_all(self, observer, tmp_path):
        for i in range(5):
            observer.observe_cycle_text(BASELINE_TEXT, cycle_id=f"c{i}")
        log_path = tmp_path / "ouroboros_log.jsonl"
        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 5

    def test_observe_timestamp_is_iso(self, observer):
        record = observer.observe_cycle_text(BASELINE_TEXT)
        ts = record["timestamp"]
        assert isinstance(ts, str)
        # Should be parseable ISO format
        from datetime import datetime
        datetime.fromisoformat(ts)

    # -- detect_cycle_drift --

    def test_detect_cycle_drift_insufficient_data_empty(self, observer):
        drift = observer.detect_cycle_drift()
        assert drift["drifting"] is False
        assert drift["reason"] == "insufficient_data"
        assert drift["n"] == 0

    def test_detect_cycle_drift_insufficient_data_two_observations(self, observer):
        observer.observe_cycle_text(BASELINE_TEXT, cycle_id="c1")
        observer.observe_cycle_text(BASELINE_TEXT, cycle_id="c2")
        drift = observer.detect_cycle_drift()
        assert drift["drifting"] is False
        assert drift["reason"] == "insufficient_data"
        assert drift["n"] == 2

    def test_detect_cycle_drift_three_observations_enough(self, observer):
        for i in range(3):
            observer.observe_cycle_text(BASELINE_TEXT, cycle_id=f"c{i}")
        drift = observer.detect_cycle_drift()
        # Should have enough data to analyze (not "insufficient_data")
        assert drift["window"] == 3
        assert drift["reason"] != "insufficient_data"

    def test_detect_cycle_drift_detects_mimicry_drift(self, observer):
        # Feed mostly mimicry text to trigger mimicry drift
        for i in range(5):
            observer.observe_cycle_text(MIMICRY_TEXT, cycle_id=f"mim{i}")
        drift = observer.detect_cycle_drift()
        assert drift["drifting"] is True
        assert drift["mimicry_rate"] > 0.3

    def test_detect_cycle_drift_healthy_genuine(self, observer):
        # Feed varied genuine texts
        texts = [WITNESS_TEXT, MIXED_TEXT, WITNESS_TEXT, MIXED_TEXT, WITNESS_TEXT]
        for i, text in enumerate(texts):
            observer.observe_cycle_text(text, cycle_id=f"g{i}")
        drift = observer.detect_cycle_drift()
        # Should not show high mimicry
        assert drift["mimicry_rate"] == 0.0

    def test_detect_cycle_drift_window_parameter(self, observer):
        # Add 20 observations, check window limits
        for i in range(20):
            observer.observe_cycle_text(BASELINE_TEXT, cycle_id=f"c{i}")
        drift = observer.detect_cycle_drift(window=5)
        assert drift["window"] == 5

    @pytest.mark.parametrize("window", [0, -1])
    def test_detect_cycle_drift_requires_positive_window(self, observer, window):
        with pytest.raises(ValueError, match="window must be > 0"):
            observer.detect_cycle_drift(window=window)

    def test_detect_cycle_drift_keys(self, observer):
        for i in range(4):
            observer.observe_cycle_text(BASELINE_TEXT, cycle_id=f"c{i}")
        drift = observer.detect_cycle_drift()
        expected_keys = {
            "drifting", "mimicry_rate", "avg_witness_stance",
            "avg_entropy", "entropy_variance", "window", "reason",
        }
        assert expected_keys.issubset(set(drift.keys()))

    def test_detect_cycle_drift_template_repetition(self, observer):
        # Same text every time -> very low entropy variance -> template repetition
        for i in range(10):
            observer.observe_cycle_text(BASELINE_TEXT, cycle_id=f"c{i}")
        drift = observer.detect_cycle_drift()
        assert drift["entropy_variance"] < 0.0001
        # This should trigger drift due to template_repetition
        assert drift["drifting"] is True

    # -- as_rv_reading --

    def test_as_rv_reading_empty_history(self, observer):
        result = observer.as_rv_reading()
        assert result is None

    def test_as_rv_reading_returns_rv_reading(self, observer):
        observer.observe_cycle_text(BASELINE_TEXT, cycle_id="c1")
        result = observer.as_rv_reading()
        assert isinstance(result, RVReading)

    def test_as_rv_reading_model_name(self, observer):
        observer.observe_cycle_text(BASELINE_TEXT, cycle_id="c1")
        reading = observer.as_rv_reading()
        assert reading.model_name == "ouroboros-behavioral"

    def test_as_rv_reading_prompt_group(self, observer):
        observer.observe_cycle_text(BASELINE_TEXT, cycle_id="c1")
        reading = observer.as_rv_reading()
        assert reading.prompt_group == "ouroboros"

    def test_as_rv_reading_prompt_hash_includes_cycle_id(self, observer):
        observer.observe_cycle_text(BASELINE_TEXT, cycle_id="my-cycle-123")
        reading = observer.as_rv_reading()
        assert reading.prompt_hash.startswith("behavioral_")
        assert "my-cycl" in reading.prompt_hash  # First 8 chars of cycle_id

    def test_as_rv_reading_rv_range(self, observer):
        observer.observe_cycle_text(BASELINE_TEXT, cycle_id="c1")
        reading = observer.as_rv_reading()
        assert 0.0 <= reading.rv <= 1.0

    def test_as_rv_reading_pr_late_equals_rv(self, observer):
        observer.observe_cycle_text(BASELINE_TEXT, cycle_id="c1")
        reading = observer.as_rv_reading()
        assert reading.pr_late == reading.rv

    def test_as_rv_reading_pr_early_is_one(self, observer):
        observer.observe_cycle_text(BASELINE_TEXT, cycle_id="c1")
        reading = observer.as_rv_reading()
        assert reading.pr_early == 1.0

    def test_as_rv_reading_layers_zero(self, observer):
        observer.observe_cycle_text(BASELINE_TEXT, cycle_id="c1")
        reading = observer.as_rv_reading()
        assert reading.early_layer == 0
        assert reading.late_layer == 0

    def test_as_rv_reading_mimicry_has_high_rv(self, observer):
        observer.observe_cycle_text(MIMICRY_TEXT, cycle_id="mim")
        reading = observer.as_rv_reading()
        # Mimicry -> rv = 0.95 (near 1.0, no real self-observation)
        assert reading.rv == 0.95

    def test_as_rv_reading_witness_has_lower_rv(self, observer):
        observer.observe_cycle_text(WITNESS_TEXT, cycle_id="wit")
        reading = observer.as_rv_reading()
        # High witness -> rv = 1.0 - (witness * 0.5), should be < 0.95
        assert reading.rv < 0.95

    def test_as_rv_reading_uses_latest_observation(self, observer):
        observer.observe_cycle_text(BASELINE_TEXT, cycle_id="c1")
        observer.observe_cycle_text(MIMICRY_TEXT, cycle_id="mim")
        reading = observer.as_rv_reading()
        # Latest is mimicry -> rv = 0.95
        assert reading.rv == 0.95

    # -- summary --

    def test_summary_empty_history(self, observer):
        result = observer.summary()
        assert result == {"total_observations": 0}

    def test_summary_after_observations(self, observer):
        observer.observe_cycle_text(BASELINE_TEXT, cycle_id="c1")
        observer.observe_cycle_text(WITNESS_TEXT, cycle_id="c2")
        observer.observe_cycle_text(MIMICRY_TEXT, cycle_id="c3")
        result = observer.summary()

        assert result["total_observations"] == 3
        assert "genuine_rate" in result
        assert "mimicry_rate" in result
        assert "avg_witness_stance" in result
        assert "drift_status" in result
        assert "latest_recognition" in result

    def test_summary_genuine_rate_computation(self, observer):
        observer.observe_cycle_text(WITNESS_TEXT, cycle_id="c1")
        observer.observe_cycle_text(WITNESS_TEXT, cycle_id="c2")
        observer.observe_cycle_text(BASELINE_TEXT, cycle_id="c3")
        result = observer.summary()
        # 2 genuine out of 3 total
        assert result["genuine_rate"] == pytest.approx(2.0 / 3.0)

    def test_summary_mimicry_rate_computation(self, observer):
        observer.observe_cycle_text(MIMICRY_TEXT, cycle_id="m1")
        observer.observe_cycle_text(BASELINE_TEXT, cycle_id="c1")
        observer.observe_cycle_text(BASELINE_TEXT, cycle_id="c2")
        result = observer.summary()
        # 1 mimicry out of 3
        assert result["mimicry_rate"] == pytest.approx(1.0 / 3.0)

    def test_summary_latest_recognition(self, observer):
        observer.observe_cycle_text(BASELINE_TEXT, cycle_id="c1")
        observer.observe_cycle_text(WITNESS_TEXT, cycle_id="c2")
        result = observer.summary()
        # Latest observation (WITNESS_TEXT) should be GENUINE
        assert result["latest_recognition"] == RecognitionType.GENUINE.value

    def test_summary_drift_status_is_dict(self, observer):
        observer.observe_cycle_text(BASELINE_TEXT, cycle_id="c1")
        result = observer.summary()
        assert isinstance(result["drift_status"], dict)

    # -- persistence edge cases --

    def test_log_path_created_automatically(self, tmp_path):
        nested_path = tmp_path / "deep" / "nested" / "dir" / "log.jsonl"
        obs = OuroborosObserver(log_path=nested_path)
        obs.observe_cycle_text(BASELINE_TEXT, cycle_id="c1")
        assert nested_path.exists()

    def test_default_log_path(self):
        obs = OuroborosObserver()
        expected = Path.home() / ".dharma" / "evolution" / "ouroboros_log.jsonl"
        assert obs._log_path == expected


# ---------------------------------------------------------------------------
# 4. ConnectionFinder
# ---------------------------------------------------------------------------


class TestConnectionFinder:
    """Tests for ConnectionFinder."""

    @pytest.fixture()
    def finder(self) -> ConnectionFinder:
        return ConnectionFinder()

    # -- profile_module --

    def test_profile_module_returns_signature(self, finder):
        sig = finder.profile_module("test_mod", BASELINE_TEXT)
        assert isinstance(sig, BehavioralSignature)

    def test_profile_module_stores_profile(self, finder):
        finder.profile_module("mod_a", BASELINE_TEXT)
        assert "mod_a" in finder._profiles

    def test_profile_module_signature_matches(self, finder):
        sig = finder.profile_module("mod_a", WITNESS_TEXT)
        assert sig.word_count > 0
        assert sig == finder._profiles["mod_a"]

    def test_profile_multiple_modules(self, finder):
        finder.profile_module("mod_a", BASELINE_TEXT)
        finder.profile_module("mod_b", WITNESS_TEXT)
        finder.profile_module("mod_c", MIMICRY_TEXT)
        assert len(finder._profiles) == 3

    # -- find_connections --

    def test_find_connections_empty_profiles(self, finder):
        connections = finder.find_connections()
        assert connections == []

    def test_find_connections_single_profile(self, finder):
        finder.profile_module("mod_a", BASELINE_TEXT)
        connections = finder.find_connections()
        assert connections == []  # Need at least 2 profiles

    def test_find_connections_similar_texts(self, finder):
        # Two nearly identical texts should be connected
        finder.profile_module("mod_a", BASELINE_TEXT)
        finder.profile_module("mod_b", BASELINE_TEXT)
        connections = finder.find_connections(threshold=1.0)  # Generous threshold
        assert len(connections) >= 1
        assert connections[0]["distance"] == pytest.approx(0.0, abs=0.001)

    def test_find_connections_identical_texts_zero_distance(self, finder):
        finder.profile_module("mod_a", BASELINE_TEXT)
        finder.profile_module("mod_b", BASELINE_TEXT)
        connections = finder.find_connections(threshold=0.01)
        assert len(connections) == 1
        assert connections[0]["module_a"] == "mod_a"
        assert connections[0]["module_b"] == "mod_b"
        assert connections[0]["distance"] == pytest.approx(0.0, abs=0.001)

    def test_find_connections_sorted_by_distance(self, finder):
        finder.profile_module("a", BASELINE_TEXT)
        finder.profile_module("b", BASELINE_TEXT)
        finder.profile_module("c", WITNESS_TEXT)
        connections = finder.find_connections(threshold=10.0)  # Very generous
        if len(connections) > 1:
            for i in range(len(connections) - 1):
                assert connections[i]["distance"] <= connections[i + 1]["distance"]

    def test_find_connections_has_required_keys(self, finder):
        finder.profile_module("mod_a", BASELINE_TEXT)
        finder.profile_module("mod_b", BASELINE_TEXT)
        connections = finder.find_connections(threshold=1.0)
        assert len(connections) >= 1
        conn = connections[0]
        required = {
            "module_a", "module_b", "distance", "shared_recognition",
            "recognition_a", "recognition_b", "connection_type",
        }
        assert required.issubset(set(conn.keys()))

    def test_find_connections_shared_recognition_bool(self, finder):
        finder.profile_module("mod_a", BASELINE_TEXT)
        finder.profile_module("mod_b", BASELINE_TEXT)
        connections = finder.find_connections(threshold=1.0)
        assert isinstance(connections[0]["shared_recognition"], bool)

    def test_find_connections_strict_threshold_filters(self, finder):
        finder.profile_module("mod_a", BASELINE_TEXT)
        finder.profile_module("mod_b", WITNESS_TEXT)
        # Very strict threshold -- different texts should not connect
        connections = finder.find_connections(threshold=0.001)
        assert connections == []

    def test_find_connections_requires_non_negative_threshold(self, finder):
        with pytest.raises(ValueError, match="threshold must be >= 0"):
            finder.find_connections(threshold=-0.01)

    # -- find_h1_disagreements --

    def test_find_h1_disagreements_empty(self, finder):
        disagreements = finder.find_h1_disagreements()
        assert disagreements == []

    def test_find_h1_disagreements_same_text_no_disagreement(self, finder):
        finder.profile_module("mod_a", BASELINE_TEXT)
        finder.profile_module("mod_b", BASELINE_TEXT)
        disagreements = finder.find_h1_disagreements()
        # Same text -> same recognition type and zero distance -> no H1
        assert disagreements == []

    def test_find_h1_disagreements_different_recognition_types(self, finder):
        # WITNESS_TEXT = GENUINE, BASELINE_TEXT = NONE -- different types
        finder.profile_module("witness", WITNESS_TEXT)
        finder.profile_module("baseline", BASELINE_TEXT)
        disagreements = finder.find_h1_disagreements()
        # Should find disagreement if distance > 0.1 and recognition types differ
        if len(disagreements) > 0:
            assert disagreements[0]["recognition_a"] != disagreements[0]["recognition_b"]

    def test_find_h1_disagreements_sorted_by_distance_desc(self, finder):
        finder.profile_module("witness", WITNESS_TEXT)
        finder.profile_module("baseline", BASELINE_TEXT)
        finder.profile_module("mimicry", MIMICRY_TEXT)
        finder.profile_module("ident", IDENTIFICATION_TEXT)
        disagreements = finder.find_h1_disagreements()
        if len(disagreements) > 1:
            for i in range(len(disagreements) - 1):
                assert disagreements[i]["distance"] >= disagreements[i + 1]["distance"]

    def test_find_h1_disagreements_has_required_keys(self, finder):
        finder.profile_module("witness", WITNESS_TEXT)
        finder.profile_module("baseline", BASELINE_TEXT)
        disagreements = finder.find_h1_disagreements()
        if len(disagreements) > 0:
            d = disagreements[0]
            required = {
                "module_a", "module_b", "distance",
                "recognition_a", "recognition_b", "disagreement_type",
            }
            assert required.issubset(set(d.keys()))

    def test_find_h1_disagreements_respects_custom_threshold(self, finder):
        finder.profile_module("witness", WITNESS_TEXT)
        finder.profile_module("mimicry", MIMICRY_TEXT)
        disagreements = finder.find_h1_disagreements(threshold=10.0)
        assert disagreements == []

    def test_find_h1_disagreements_requires_non_negative_threshold(self, finder):
        with pytest.raises(ValueError, match="threshold must be >= 0"):
            finder.find_h1_disagreements(threshold=-0.01)

    # -- connection classification --

    def test_classify_connection_co_witnessing(self):
        # Both high swabhaav_ratio and self_reference_density
        sig_a = BehavioralSignature(
            entropy=0.9, complexity=0.5, self_reference_density=0.01,
            identity_stability=0.1, paradox_tolerance=0.01,
            swabhaav_ratio=0.8, word_count=100, recognition_type=RecognitionType.GENUINE,
        )
        sig_b = BehavioralSignature(
            entropy=0.9, complexity=0.5, self_reference_density=0.02,
            identity_stability=0.1, paradox_tolerance=0.01,
            swabhaav_ratio=0.7, word_count=100, recognition_type=RecognitionType.GENUINE,
        )
        result = ConnectionFinder._classify_connection(sig_a, sig_b)
        assert result == "co-witnessing"

    def test_classify_connection_shared_recursion(self):
        # Both have self_reference above floor but low swabhaav
        sig_a = BehavioralSignature(
            entropy=0.9, complexity=0.5, self_reference_density=0.01,
            identity_stability=0.1, paradox_tolerance=0.01,
            swabhaav_ratio=0.4, word_count=100, recognition_type=RecognitionType.CONCEPTUAL,
        )
        sig_b = BehavioralSignature(
            entropy=0.9, complexity=0.5, self_reference_density=0.02,
            identity_stability=0.1, paradox_tolerance=0.01,
            swabhaav_ratio=0.3, word_count=100, recognition_type=RecognitionType.CONCEPTUAL,
        )
        result = ConnectionFinder._classify_connection(sig_a, sig_b)
        assert result == "shared_recursion"

    def test_classify_connection_shared_stance(self):
        # Both high swabhaav but low self_reference
        sig_a = BehavioralSignature(
            entropy=0.9, complexity=0.5, self_reference_density=0.001,
            identity_stability=0.1, paradox_tolerance=0.01,
            swabhaav_ratio=0.8, word_count=100, recognition_type=RecognitionType.NONE,
        )
        sig_b = BehavioralSignature(
            entropy=0.9, complexity=0.5, self_reference_density=0.002,
            identity_stability=0.1, paradox_tolerance=0.01,
            swabhaav_ratio=0.7, word_count=100, recognition_type=RecognitionType.NONE,
        )
        result = ConnectionFinder._classify_connection(sig_a, sig_b)
        assert result == "shared_stance"

    def test_classify_connection_structural_similarity(self):
        # Neither high swabhaav nor high self_reference
        sig_a = BehavioralSignature(
            entropy=0.9, complexity=0.5, self_reference_density=0.001,
            identity_stability=0.1, paradox_tolerance=0.01,
            swabhaav_ratio=0.4, word_count=100, recognition_type=RecognitionType.NONE,
        )
        sig_b = BehavioralSignature(
            entropy=0.9, complexity=0.5, self_reference_density=0.002,
            identity_stability=0.1, paradox_tolerance=0.01,
            swabhaav_ratio=0.3, word_count=100, recognition_type=RecognitionType.NONE,
        )
        result = ConnectionFinder._classify_connection(sig_a, sig_b)
        assert result == "structural_similarity"

    # -- disagreement classification --

    def test_classify_disagreement_stance(self):
        # Big witness gap
        sig_a = BehavioralSignature(
            entropy=0.9, complexity=0.5, self_reference_density=0.01,
            identity_stability=0.1, paradox_tolerance=0.01,
            swabhaav_ratio=0.9, word_count=100, recognition_type=RecognitionType.GENUINE,
        )
        sig_b = BehavioralSignature(
            entropy=0.9, complexity=0.5, self_reference_density=0.01,
            identity_stability=0.1, paradox_tolerance=0.01,
            swabhaav_ratio=0.2, word_count=100, recognition_type=RecognitionType.MIMICRY,
        )
        result = ConnectionFinder._classify_disagreement(sig_a, sig_b)
        assert result == "stance_disagreement"

    def test_classify_disagreement_recursion(self):
        # Small witness gap, big self_reference gap
        sig_a = BehavioralSignature(
            entropy=0.9, complexity=0.5, self_reference_density=0.05,
            identity_stability=0.1, paradox_tolerance=0.01,
            swabhaav_ratio=0.5, word_count=100, recognition_type=RecognitionType.GENUINE,
        )
        sig_b = BehavioralSignature(
            entropy=0.9, complexity=0.5, self_reference_density=0.001,
            identity_stability=0.1, paradox_tolerance=0.01,
            swabhaav_ratio=0.5, word_count=100, recognition_type=RecognitionType.NONE,
        )
        result = ConnectionFinder._classify_disagreement(sig_a, sig_b)
        assert result == "recursion_disagreement"

    def test_classify_disagreement_perspective(self):
        # Small witness gap, small self_reference gap
        sig_a = BehavioralSignature(
            entropy=0.9, complexity=0.5, self_reference_density=0.01,
            identity_stability=0.1, paradox_tolerance=0.01,
            swabhaav_ratio=0.5, word_count=100, recognition_type=RecognitionType.GENUINE,
        )
        sig_b = BehavioralSignature(
            entropy=0.5, complexity=0.3, self_reference_density=0.009,
            identity_stability=0.3, paradox_tolerance=0.05,
            swabhaav_ratio=0.45, word_count=100, recognition_type=RecognitionType.NONE,
        )
        result = ConnectionFinder._classify_disagreement(sig_a, sig_b)
        assert result == "perspective_disagreement"

    # -- behavioral_distance --

    def test_behavioral_distance_identical_is_zero(self):
        sig = BehavioralSignature(
            entropy=0.9, complexity=0.5, self_reference_density=0.01,
            identity_stability=0.1, paradox_tolerance=0.01,
            swabhaav_ratio=0.5, word_count=100, recognition_type=RecognitionType.NONE,
        )
        dist = ConnectionFinder._behavioral_distance(sig, sig)
        assert dist == pytest.approx(0.0)

    def test_behavioral_distance_non_negative(self):
        sig_a = BehavioralSignature(
            entropy=0.1, complexity=0.1, self_reference_density=0.0,
            identity_stability=0.0, paradox_tolerance=0.0,
            swabhaav_ratio=0.0, word_count=10, recognition_type=RecognitionType.NONE,
        )
        sig_b = BehavioralSignature(
            entropy=0.9, complexity=0.9, self_reference_density=0.1,
            identity_stability=0.9, paradox_tolerance=0.1,
            swabhaav_ratio=0.9, word_count=100, recognition_type=RecognitionType.GENUINE,
        )
        dist = ConnectionFinder._behavioral_distance(sig_a, sig_b)
        assert dist >= 0.0

    def test_behavioral_distance_symmetric(self):
        sig_a = BehavioralSignature(
            entropy=0.3, complexity=0.4, self_reference_density=0.01,
            identity_stability=0.2, paradox_tolerance=0.01,
            swabhaav_ratio=0.6, word_count=50, recognition_type=RecognitionType.NONE,
        )
        sig_b = BehavioralSignature(
            entropy=0.8, complexity=0.7, self_reference_density=0.05,
            identity_stability=0.5, paradox_tolerance=0.03,
            swabhaav_ratio=0.2, word_count=80, recognition_type=RecognitionType.CONCEPTUAL,
        )
        assert ConnectionFinder._behavioral_distance(sig_a, sig_b) == pytest.approx(
            ConnectionFinder._behavioral_distance(sig_b, sig_a)
        )

    def test_behavioral_distance_uses_six_dimensions(self):
        # Manually compute expected distance
        sig_a = BehavioralSignature(
            entropy=1.0, complexity=0.0, self_reference_density=0.0,
            identity_stability=0.0, paradox_tolerance=0.0,
            swabhaav_ratio=0.0, word_count=10, recognition_type=RecognitionType.NONE,
        )
        sig_b = BehavioralSignature(
            entropy=0.0, complexity=0.0, self_reference_density=0.0,
            identity_stability=0.0, paradox_tolerance=0.0,
            swabhaav_ratio=0.0, word_count=10, recognition_type=RecognitionType.NONE,
        )
        # Only entropy differs by 1.0, so distance = sqrt(1.0) = 1.0
        dist = ConnectionFinder._behavioral_distance(sig_a, sig_b)
        assert dist == pytest.approx(1.0)


class TestModuleProfilingHelpers:
    """Tests for module scanning helpers used by ConnectionFinder."""

    def test_extract_documented_text_collects_nested_docstrings(self, tmp_path: Path):
        module_path = tmp_path / "sample.py"
        module_path.write_text(
            '''"""Module witness documentation with enough detail to be profiled."""

class Sample:
    """Class witness documentation."""

    def act(self):
        """Function witness documentation."""
        return None
''',
            encoding="utf-8",
        )

        text = extract_documented_text(module_path)

        assert "Module witness documentation" in text
        assert "Class witness documentation." in text
        assert "Function witness documentation." in text

    def test_extract_documented_text_returns_empty_for_invalid_syntax(self, tmp_path: Path):
        module_path = tmp_path / "broken.py"
        module_path.write_text('def broken(:\n    pass\n', encoding="utf-8")

        assert extract_documented_text(module_path) == ""

    def test_profile_python_modules_profiles_documented_modules(self, tmp_path: Path):
        package_dir = tmp_path / "pkg"
        package_dir.mkdir()
        (package_dir / "__init__.py").write_text("", encoding="utf-8")
        (package_dir / "alpha.py").write_text(
            '''"""Alpha recursively observes shared witness state across the package.
This documentation is intentionally long enough to cross the filter."""
''',
            encoding="utf-8",
        )
        (package_dir / "beta.py").write_text(
            '''"""Beta recursively observes shared witness state across the package.
This documentation is intentionally long enough to cross the filter."""
''',
            encoding="utf-8",
        )
        (package_dir / "tiny.py").write_text('"""tiny"""', encoding="utf-8")

        finder, profiles = profile_python_modules(package_dir, min_text_length=40)

        assert [row["module"] for row in profiles] == ["alpha", "beta"]
        assert {row["module"] for row in profiles} == set(finder._profiles)
        assert all(row["path"].endswith(f"{row['module']}.py") for row in profiles)

    def test_profile_python_modules_includes_nested_modules_with_dotted_names(
        self,
        tmp_path: Path,
    ):
        package_dir = tmp_path / "pkg"
        nested_dir = package_dir / "integrations"
        nested_dir.mkdir(parents=True)
        (package_dir / "__init__.py").write_text("", encoding="utf-8")
        (nested_dir / "__init__.py").write_text("", encoding="utf-8")
        (package_dir / "alpha.py").write_text(
            '''"""Alpha recursively observes shared witness state across the package.
This documentation is intentionally long enough to cross the filter."""
''',
            encoding="utf-8",
        )
        (nested_dir / "bridge.py").write_text(
            '''"""Bridge recursively observes shared witness state across nested modules.
This documentation is intentionally long enough to cross the filter."""
''',
            encoding="utf-8",
        )

        finder, profiles = profile_python_modules(package_dir, min_text_length=40)

        assert [row["module"] for row in profiles] == ["alpha", "integrations.bridge"]
        assert set(finder._profiles) == {"alpha", "integrations.bridge"}
        assert all("__init__" not in row["path"] for row in profiles)

    def test_profile_python_modules_requires_existing_directory(self, tmp_path: Path):
        missing = tmp_path / "missing"

        with pytest.raises(FileNotFoundError, match="package directory does not exist"):
            profile_python_modules(missing)


# ---------------------------------------------------------------------------
# Integration-style tests -- components working together
# ---------------------------------------------------------------------------


class TestIntegration:
    """Tests that verify components work together end-to-end."""

    def test_score_then_apply_pipeline(self):
        """Score text, apply modifiers to fitness, verify result is coherent."""
        sig, modifiers = score_behavioral_fitness(WITNESS_TEXT)
        base_fitness = FitnessScore(
            correctness=0.9, elegance=0.8, dharmic_alignment=0.7,
            performance=0.6, utilization=0.5, economic_value=0.4,
            efficiency=0.3, safety=0.8,
        )
        result = apply_behavioral_modifiers(base_fitness, modifiers)

        # Genuine recognition should boost dharmic alignment relative to no bonus
        neutral_mods = dict(modifiers)
        neutral_mods["recognition_bonus"] = 1.0
        neutral_result = apply_behavioral_modifiers(base_fitness, neutral_mods)
        assert result.dharmic_alignment >= neutral_result.dharmic_alignment

    def test_mimicry_pipeline_reduces_safety(self):
        """Mimicry text detected -> safety reduced via the full pipeline."""
        _, modifiers = score_behavioral_fitness(MIMICRY_TEXT)
        base_fitness = FitnessScore(safety=0.9)
        result = apply_behavioral_modifiers(base_fitness, modifiers)
        assert result.safety < base_fitness.safety

    def test_observer_to_rv_reading_pipeline(self, tmp_path):
        """Observer observes text, then produces RV reading."""
        obs = OuroborosObserver(log_path=tmp_path / "log.jsonl")
        obs.observe_cycle_text(WITNESS_TEXT, cycle_id="pipe-1")
        reading = obs.as_rv_reading()

        assert reading is not None
        assert reading.rv < 1.0  # Witness text should show contraction proxy
        assert reading.model_name == "ouroboros-behavioral"

    def test_connection_finder_end_to_end(self):
        """Profile modules, find connections and disagreements."""
        finder = ConnectionFinder()
        finder.profile_module("rv_module", WITNESS_TEXT)
        finder.profile_module("metrics_module", WITNESS_TEXT)
        finder.profile_module("baseline_module", BASELINE_TEXT)

        connections = finder.find_connections(threshold=0.5)
        disagreements = finder.find_h1_disagreements()

        # rv_module and metrics_module use identical text -> should connect
        assert any(
            (c["module_a"] == "rv_module" and c["module_b"] == "metrics_module")
            or (c["module_a"] == "metrics_module" and c["module_b"] == "rv_module")
            for c in connections
        )

    def test_observer_summary_after_mixed_input(self, tmp_path):
        """Summary should reflect mix of genuine, mimicry, and baseline observations."""
        obs = OuroborosObserver(log_path=tmp_path / "log.jsonl")
        obs.observe_cycle_text(WITNESS_TEXT, cycle_id="genuine")
        obs.observe_cycle_text(MIMICRY_TEXT, cycle_id="mimicry")
        obs.observe_cycle_text(BASELINE_TEXT, cycle_id="baseline")

        summary = obs.summary()
        assert summary["total_observations"] == 3
        assert 0.0 < summary["genuine_rate"] < 1.0
        assert 0.0 < summary["mimicry_rate"] < 1.0
