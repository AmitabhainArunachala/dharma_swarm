"""Tests for the predictive self-model."""

import pytest
from pathlib import Path

from dharma_swarm.self_prediction import PredictionRecord, SelfPredictor


@pytest.fixture
def predictor(tmp_path):
    """SelfPredictor with a temp history file."""
    return SelfPredictor(history_path=tmp_path / "predictions.jsonl")


class TestSelfPredictor:
    def test_predict_returns_record(self, predictor):
        record = predictor.predict(pulse_id="test-1", task_type="general")
        assert isinstance(record, PredictionRecord)
        assert record.predicted_duration_ms > 0
        assert 0.0 <= record.predicted_failure_prob <= 1.0

    def test_predict_uses_defaults_when_no_history(self, predictor):
        record = predictor.predict(pulse_id="test-1")
        # Should use default values
        assert record.predicted_duration_ms == 10_000.0
        assert record.predicted_failure_prob == 0.2

    def test_score_computes_error(self, predictor):
        record = predictor.predict(pulse_id="test-1")
        scored = predictor.score(record, actual_ms=8000.0, success=True)
        assert scored.actual_duration_ms == 8000.0
        assert scored.actual_success is True
        assert scored.duration_error is not None
        assert scored.duration_error == record.predicted_duration_ms - 8000.0

    def test_surprise_detection(self, predictor):
        # Build history with consistent 10s durations
        for i in range(5):
            r = predictor.predict(pulse_id=f"hist-{i}", task_type="general")
            predictor.score(r, actual_ms=10_000.0, success=True)

        # Now a prediction that's way off should be a surprise
        new_record = predictor.predict(pulse_id="surprise-1", task_type="general")
        scored = predictor.score(new_record, actual_ms=100.0, success=True)
        # The error is huge compared to historical std (~0)
        assert scored.surprise is True

    def test_calibration_with_no_data(self, predictor):
        cal = predictor.calibration()
        assert cal["status"] == "insufficient_data"
        assert cal["count"] == 0

    def test_calibration_with_data(self, predictor):
        for i in range(5):
            r = predictor.predict(pulse_id=f"cal-{i}")
            predictor.score(r, actual_ms=9500.0 + i * 100, success=True)

        cal = predictor.calibration()
        assert cal["status"] == "measured"
        assert cal["total_predictions"] == 5
        assert cal["mean_absolute_duration_error_ms"] >= 0

    def test_persistence(self, tmp_path):
        path = tmp_path / "predictions.jsonl"
        p1 = SelfPredictor(history_path=path)
        r = p1.predict(pulse_id="persist-1")
        p1.score(r, actual_ms=5000.0, success=True)

        # Load a new predictor from the same file
        p2 = SelfPredictor(history_path=path)
        assert len(p2._history) >= 1
