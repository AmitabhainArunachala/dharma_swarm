"""Tests for active_inference.py — Friston P10 embodiment.

Covers: Belief, Prediction, PredictionError, GenerativeModel,
ActiveInferenceEngine (predict, observe, EFE, free energy, persistence).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dharma_swarm.active_inference import (
    ActiveInferenceEngine,
    Belief,
    GenerativeModel,
    Prediction,
    PredictionError,
)


# ---------------------------------------------------------------------------
# Belief
# ---------------------------------------------------------------------------

class TestBelief:
    def test_defaults(self):
        b = Belief()
        assert b.mean == 0.5
        assert b.precision == 1.0
        assert b.observation_count == 0

    def test_variance_inverse_of_precision(self):
        b = Belief(precision=4.0)
        assert b.variance() == pytest.approx(0.25)

    def test_variance_floor(self):
        b = Belief(precision=0.0)
        assert b.variance() > 0  # never infinite

    def test_roundtrip_dict(self):
        b = Belief(mean=0.7, precision=3.5, observation_count=10)
        d = b.to_dict()
        b2 = Belief.from_dict(d)
        assert b2.mean == pytest.approx(b.mean, abs=1e-5)
        assert b2.precision == pytest.approx(b.precision, abs=1e-5)
        assert b2.observation_count == b.observation_count


# ---------------------------------------------------------------------------
# GenerativeModel
# ---------------------------------------------------------------------------

class TestGenerativeModel:
    def test_get_belief_creates_default(self):
        m = GenerativeModel(agent_id="a1")
        b = m.get_belief("code")
        assert b.mean == 0.5
        assert b.precision == 1.0
        assert "code" in m.beliefs

    def test_get_belief_returns_existing(self):
        m = GenerativeModel(agent_id="a1")
        m.beliefs["code"] = Belief(mean=0.8, precision=5.0)
        b = m.get_belief("code")
        assert b.mean == 0.8

    def test_model_complexity_zero_when_empty(self):
        m = GenerativeModel(agent_id="a1")
        assert m.model_complexity() == 0.0

    def test_model_complexity_zero_at_prior(self):
        m = GenerativeModel(agent_id="a1")
        m.beliefs["general"] = Belief(mean=0.5, precision=1.0)
        # KL(q||p) = 0 when q == p
        assert m.model_complexity() == pytest.approx(0.0, abs=1e-6)

    def test_model_complexity_increases_with_drift(self):
        m = GenerativeModel(agent_id="a1")
        m.beliefs["general"] = Belief(mean=0.9, precision=5.0)
        assert m.model_complexity() > 0.0

    def test_preferred_quality_defaults_moksha(self):
        m = GenerativeModel(agent_id="a1")
        assert m.preferred_quality == 1.0

    def test_roundtrip_dict(self):
        m = GenerativeModel(agent_id="a1")
        m.beliefs["code"] = Belief(mean=0.7, precision=3.0, observation_count=5)
        m.beliefs["research"] = Belief(mean=0.6, precision=2.0, observation_count=3)
        d = m.to_dict()
        m2 = GenerativeModel.from_dict(d)
        assert m2.agent_id == "a1"
        assert len(m2.beliefs) == 2
        assert m2.beliefs["code"].mean == pytest.approx(0.7, abs=1e-5)


# ---------------------------------------------------------------------------
# ActiveInferenceEngine — predict
# ---------------------------------------------------------------------------

class TestPredict:
    def test_predict_returns_prediction(self):
        engine = ActiveInferenceEngine(state_dir=Path("/tmp/ai_test_predict"))
        pred = engine.predict("agent-1", "task-42", "code")
        assert isinstance(pred, Prediction)
        assert pred.agent_id == "agent-1"
        assert pred.task_id == "task-42"
        assert pred.task_type == "code"

    def test_predict_uses_belief_mean(self):
        engine = ActiveInferenceEngine(state_dir=Path("/tmp/ai_test_predict2"))
        model = engine.get_model("agent-1")
        model.beliefs["code"] = Belief(mean=0.8, precision=5.0)
        pred = engine.predict("agent-1", "task-1", "code")
        assert pred.predicted_quality == pytest.approx(0.8)
        assert pred.predicted_precision == pytest.approx(5.0)

    def test_predict_default_task_type(self):
        engine = ActiveInferenceEngine(state_dir=Path("/tmp/ai_test_predict3"))
        pred = engine.predict("agent-1", "task-1")
        assert pred.task_type == "general"
        assert pred.predicted_quality == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# ActiveInferenceEngine — observe
# ---------------------------------------------------------------------------

class TestObserve:
    def test_observe_returns_prediction_error(self):
        engine = ActiveInferenceEngine(state_dir=Path("/tmp/ai_test_observe"))
        pred = engine.predict("agent-1", "task-1", "code")
        pe = engine.observe(pred, observed_quality=0.7, persist=False)
        assert isinstance(pe, PredictionError)
        assert pe.observed_quality == pytest.approx(0.7)
        assert pe.error == pytest.approx(0.2)  # 0.7 - 0.5

    def test_observe_updates_belief_mean(self):
        engine = ActiveInferenceEngine(state_dir=Path("/tmp/ai_test_observe2"))
        pred = engine.predict("agent-1", "task-1", "code")
        engine.observe(pred, observed_quality=0.9, persist=False)
        belief = engine.get_model("agent-1").get_belief("code")
        # Mean should shift toward 0.9
        assert belief.mean > 0.5

    def test_observe_increases_precision(self):
        engine = ActiveInferenceEngine(state_dir=Path("/tmp/ai_test_observe3"))
        pred = engine.predict("agent-1", "task-1", "code")
        initial_prec = engine.get_model("agent-1").get_belief("code").precision
        engine.observe(pred, observed_quality=0.6, persist=False)
        assert engine.get_model("agent-1").get_belief("code").precision > initial_prec

    def test_observe_increments_observation_count(self):
        engine = ActiveInferenceEngine(state_dir=Path("/tmp/ai_test_observe4"))
        pred = engine.predict("agent-1", "task-1", "code")
        engine.observe(pred, observed_quality=0.7, persist=False)
        assert engine.get_model("agent-1").get_belief("code").observation_count == 1

    def test_observe_clamps_quality(self):
        engine = ActiveInferenceEngine(state_dir=Path("/tmp/ai_test_observe5"))
        pred = engine.predict("agent-1", "task-1")
        pe = engine.observe(pred, observed_quality=1.5, persist=False)
        assert pe.observed_quality == 1.0
        pe2 = engine.observe(
            engine.predict("agent-1", "task-2"),
            observed_quality=-0.3,
            persist=False,
        )
        assert pe2.observed_quality == 0.0

    def test_observe_perfect_prediction_zero_error(self):
        engine = ActiveInferenceEngine(state_dir=Path("/tmp/ai_test_observe6"))
        model = engine.get_model("agent-1")
        model.beliefs["code"] = Belief(mean=0.7, precision=5.0)
        pred = engine.predict("agent-1", "task-1", "code")
        pe = engine.observe(pred, observed_quality=0.7, persist=False)
        assert pe.error == pytest.approx(0.0)

    def test_multiple_observations_converge(self):
        engine = ActiveInferenceEngine(state_dir=Path("/tmp/ai_test_converge"))
        # Feed 20 observations of quality=0.8
        for i in range(20):
            pred = engine.predict("agent-1", f"task-{i}", "code")
            engine.observe(pred, observed_quality=0.8, persist=False)
        belief = engine.get_model("agent-1").get_belief("code")
        # Mean should be close to 0.8
        assert belief.mean == pytest.approx(0.8, abs=0.1)
        # Precision should be higher than initial
        assert belief.precision > 1.0


# ---------------------------------------------------------------------------
# ActiveInferenceEngine — expected_free_energy
# ---------------------------------------------------------------------------

class TestExpectedFreeEnergy:
    def test_efe_lower_for_better_match(self):
        engine = ActiveInferenceEngine(state_dir=Path("/tmp/ai_test_efe"))
        # Agent-A: high quality beliefs for code (mean=0.9)
        model_a = engine.get_model("agent-a")
        model_a.beliefs["code"] = Belief(mean=0.9, precision=10.0, observation_count=10)
        # Agent-B: low quality beliefs for code (mean=0.3)
        model_b = engine.get_model("agent-b")
        model_b.beliefs["code"] = Belief(mean=0.3, precision=10.0, observation_count=10)

        efe_a = engine.expected_free_energy("agent-a", "code")
        efe_b = engine.expected_free_energy("agent-b", "code")
        # Agent-A should have lower EFE (better match, closer to preferred=1.0)
        assert efe_a < efe_b

    def test_efe_lower_for_higher_precision(self):
        engine = ActiveInferenceEngine(state_dir=Path("/tmp/ai_test_efe2"))
        # Same mean, different precision
        model_a = engine.get_model("agent-a")
        model_a.beliefs["code"] = Belief(mean=0.7, precision=10.0, observation_count=10)
        model_b = engine.get_model("agent-b")
        model_b.beliefs["code"] = Belief(mean=0.7, precision=1.0, observation_count=10)

        efe_a = engine.expected_free_energy("agent-a", "code")
        efe_b = engine.expected_free_energy("agent-b", "code")
        # Higher precision = lower ambiguity = lower EFE
        assert efe_a < efe_b

    def test_efe_exploration_bonus_for_new_agents(self):
        engine = ActiveInferenceEngine(state_dir=Path("/tmp/ai_test_efe3"))
        # New agent with 0 observations
        efe_new = engine.expected_free_energy("new-agent", "code")
        # Experienced agent with many observations
        model_exp = engine.get_model("exp-agent")
        model_exp.beliefs["code"] = Belief(mean=0.5, precision=1.0, observation_count=20)
        efe_exp = engine.expected_free_energy("exp-agent", "code")
        # New agent gets exploration bonus (lower EFE)
        assert efe_new < efe_exp

    def test_efe_unknown_task_type(self):
        engine = ActiveInferenceEngine(state_dir=Path("/tmp/ai_test_efe4"))
        efe = engine.expected_free_energy("agent-1", "never_seen_before")
        assert isinstance(efe, float)


# ---------------------------------------------------------------------------
# ActiveInferenceEngine — free_energy
# ---------------------------------------------------------------------------

class TestFreeEnergy:
    def test_free_energy_zero_for_new_agent(self):
        engine = ActiveInferenceEngine(state_dir=Path("/tmp/ai_test_fe"))
        fe = engine.free_energy("new-agent")
        assert fe == 0.0

    def test_free_energy_lower_for_aligned_agent(self):
        engine = ActiveInferenceEngine(state_dir=Path("/tmp/ai_test_fe2"))
        # Aligned agent: beliefs close to preferred (1.0)
        model_a = engine.get_model("aligned")
        model_a.beliefs["code"] = Belief(mean=0.95, precision=10.0, observation_count=20)
        # Misaligned agent: beliefs far from preferred
        model_b = engine.get_model("misaligned")
        model_b.beliefs["code"] = Belief(mean=0.2, precision=10.0, observation_count=20)

        fe_a = engine.free_energy("aligned")
        fe_b = engine.free_energy("misaligned")
        assert fe_a < fe_b


# ---------------------------------------------------------------------------
# ActiveInferenceEngine — persistence
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_persist_and_reload(self, tmp_path):
        state_dir = tmp_path / "dharma"
        engine = ActiveInferenceEngine(state_dir=state_dir)
        model = engine.get_model("agent-1")
        model.beliefs["code"] = Belief(mean=0.8, precision=5.0, observation_count=10)
        engine._persist()

        # Create new engine, should reload
        engine2 = ActiveInferenceEngine(state_dir=state_dir)
        model2 = engine2.get_model("agent-1")
        assert model2.beliefs["code"].mean == pytest.approx(0.8, abs=1e-5)
        assert model2.beliefs["code"].precision == pytest.approx(5.0, abs=1e-5)

    def test_prediction_error_log(self, tmp_path):
        state_dir = tmp_path / "dharma"
        engine = ActiveInferenceEngine(state_dir=state_dir)
        pred = engine.predict("agent-1", "task-1", "code")
        engine.observe(pred, observed_quality=0.7, persist=True)

        log_file = state_dir / "active_inference" / "prediction_errors.jsonl"
        assert log_file.is_file()
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["agent_id"] == "agent-1"
        assert entry["error"] == pytest.approx(0.2, abs=1e-5)

    def test_reset_agent(self, tmp_path):
        state_dir = tmp_path / "dharma"
        engine = ActiveInferenceEngine(state_dir=state_dir)
        engine.get_model("agent-1").beliefs["code"] = Belief(mean=0.9)
        engine.reset_agent("agent-1")
        # Should get fresh model
        model = engine.get_model("agent-1")
        assert len(model.beliefs) == 0


# ---------------------------------------------------------------------------
# ActiveInferenceEngine — summaries
# ---------------------------------------------------------------------------

class TestSummaries:
    def test_agent_summary(self):
        engine = ActiveInferenceEngine(state_dir=Path("/tmp/ai_test_summary"))
        model = engine.get_model("agent-1")
        model.beliefs["code"] = Belief(mean=0.7, precision=3.0, observation_count=5)
        summary = engine.agent_summary("agent-1")
        assert summary["agent_id"] == "agent-1"
        assert summary["belief_count"] == 1
        assert summary["total_observations"] == 5
        assert "free_energy" in summary

    def test_system_free_energy(self):
        engine = ActiveInferenceEngine(state_dir=Path("/tmp/ai_test_sysfe"))
        engine.get_model("a1").beliefs["code"] = Belief(mean=0.7, observation_count=5)
        engine.get_model("a2").beliefs["code"] = Belief(mean=0.3, observation_count=5)
        sfe = engine.system_free_energy()
        assert sfe["agent_count"] == 2
        assert "total_free_energy" in sfe
        assert "per_agent" in sfe


# ---------------------------------------------------------------------------
# Integration: predict → observe loop
# ---------------------------------------------------------------------------

class TestPredictObserveLoop:
    def test_full_loop_reduces_error(self):
        """Repeated predict→observe should reduce prediction error over time."""
        engine = ActiveInferenceEngine(state_dir=Path("/tmp/ai_test_loop"))
        errors = []
        for i in range(30):
            pred = engine.predict("agent-1", f"task-{i}", "code")
            pe = engine.observe(pred, observed_quality=0.75, persist=False)
            errors.append(abs(pe.error))

        # Error should decrease: first few errors > last few errors
        early = sum(errors[:5]) / 5
        late = sum(errors[-5:]) / 5
        assert late < early

    def test_mixed_task_types_separate_beliefs(self):
        """Different task types maintain independent beliefs."""
        engine = ActiveInferenceEngine(state_dir=Path("/tmp/ai_test_mixed"))
        for i in range(10):
            pred_code = engine.predict("agent-1", f"code-{i}", "code")
            engine.observe(pred_code, observed_quality=0.9, persist=False)
            pred_research = engine.predict("agent-1", f"research-{i}", "research")
            engine.observe(pred_research, observed_quality=0.3, persist=False)

        model = engine.get_model("agent-1")
        assert model.beliefs["code"].mean > model.beliefs["research"].mean

    def test_precision_caps_at_max(self):
        """Precision should not exceed max_precision."""
        engine = ActiveInferenceEngine(state_dir=Path("/tmp/ai_test_maxprec"))
        for i in range(500):
            pred = engine.predict("agent-1", f"task-{i}", "code")
            engine.observe(pred, observed_quality=0.7, persist=False)
        belief = engine.get_model("agent-1").get_belief("code")
        assert belief.precision <= engine.get_model("agent-1").max_precision


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_prediction_to_dict(self):
        p = Prediction(
            agent_id="a1", task_id="t1", task_type="code",
            predicted_quality=0.7, predicted_precision=3.0,
        )
        d = p.to_dict()
        assert d["agent_id"] == "a1"
        assert d["predicted_quality"] == pytest.approx(0.7)

    def test_prediction_error_to_dict(self):
        pe = PredictionError(
            agent_id="a1", task_id="t1", task_type="code",
            predicted_quality=0.5, observed_quality=0.8,
            error=0.3, precision_weighted_error=0.15, free_energy=0.01,
        )
        d = pe.to_dict()
        assert d["error"] == pytest.approx(0.3)
        assert d["free_energy"] == pytest.approx(0.01)
