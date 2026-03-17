"""Tests for Ginko Brier scoring system."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

# Redirect DHARMA_HOME to temp dir for test isolation
_temp_dir = tempfile.mkdtemp()
os.environ["DHARMA_HOME"] = _temp_dir

from unittest.mock import AsyncMock, Mock, patch

from dharma_swarm.ginko_brier import (
    BrierDashboard,
    Prediction,
    build_dashboard,
    check_edge_validation,
    compute_brier_score,
    compute_brier_by_group,
    compute_calibration,
    compute_win_rate,
    format_dashboard_report,
    log_resolution_notification,
    record_prediction,
    resolve_prediction,
    get_pending_predictions,
    get_overdue_predictions,
    webhook_notify,
    _load_all_predictions,
    _save_all_predictions,
    NOTIFICATIONS_FILE,
    PREDICTIONS_FILE,
)


@pytest.fixture(autouse=True)
def clean_predictions():
    """Clean predictions and notifications files before each test."""
    if PREDICTIONS_FILE.exists():
        PREDICTIONS_FILE.unlink()
    if NOTIFICATIONS_FILE.exists():
        NOTIFICATIONS_FILE.unlink()
    yield
    if PREDICTIONS_FILE.exists():
        PREDICTIONS_FILE.unlink()
    if NOTIFICATIONS_FILE.exists():
        NOTIFICATIONS_FILE.unlink()


class TestRecordPrediction:
    def test_basic_record(self):
        pred = record_prediction(
            question="Will SPY close above 500 tomorrow?",
            probability=0.7,
            resolve_by="2026-04-01T16:00:00Z",
            category="equity",
            source="financial-intel",
        )
        assert pred.id
        assert pred.probability == 0.7
        assert pred.category == "equity"
        assert pred.outcome is None
        assert pred.brier_score is None

    def test_persists_to_disk(self):
        record_prediction("Test?", 0.5, "2026-04-01T00:00:00Z")
        assert PREDICTIONS_FILE.exists()
        lines = PREDICTIONS_FILE.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["question"] == "Test?"

    def test_multiple_predictions(self):
        for i in range(5):
            record_prediction(f"Q{i}?", 0.1 * (i + 1), "2026-04-01T00:00:00Z")
        preds = _load_all_predictions()
        assert len(preds) == 5

    def test_invalid_probability(self):
        with pytest.raises(ValueError):
            record_prediction("Test?", 1.5, "2026-04-01T00:00:00Z")
        with pytest.raises(ValueError):
            record_prediction("Test?", -0.1, "2026-04-01T00:00:00Z")

    def test_metadata(self):
        pred = record_prediction(
            "Test?", 0.5, "2026-04-01T00:00:00Z",
            metadata={"regime": "bull", "confidence": 0.9},
        )
        assert pred.metadata["regime"] == "bull"


class TestResolvePrediction:
    def test_resolve_yes(self):
        pred = record_prediction("Test?", 0.8, "2026-04-01T00:00:00Z")
        resolved = resolve_prediction(pred.id, 1.0)
        assert resolved is not None
        assert resolved.outcome == 1.0
        assert resolved.brier_score == pytest.approx(0.04)  # (0.8 - 1.0)^2

    def test_resolve_no(self):
        pred = record_prediction("Test?", 0.8, "2026-04-01T00:00:00Z")
        resolved = resolve_prediction(pred.id, 0.0)
        assert resolved is not None
        assert resolved.outcome == 0.0
        assert resolved.brier_score == pytest.approx(0.64)  # (0.8 - 0.0)^2

    def test_resolve_persists(self):
        pred = record_prediction("Test?", 0.5, "2026-04-01T00:00:00Z")
        resolve_prediction(pred.id, 1.0)
        loaded = _load_all_predictions()
        assert loaded[0].outcome == 1.0
        assert loaded[0].resolved_at is not None

    def test_resolve_nonexistent(self):
        result = resolve_prediction("nonexistent", 1.0)
        assert result is None

    def test_double_resolve(self):
        pred = record_prediction("Test?", 0.5, "2026-04-01T00:00:00Z")
        resolve_prediction(pred.id, 1.0)
        result = resolve_prediction(pred.id, 0.0)
        assert result is None  # Already resolved

    def test_invalid_outcome(self):
        pred = record_prediction("Test?", 0.5, "2026-04-01T00:00:00Z")
        with pytest.raises(ValueError):
            resolve_prediction(pred.id, 0.5)


class TestBrierScore:
    def test_perfect_prediction(self):
        """Perfect predictions should score 0."""
        pred1 = record_prediction("A?", 1.0, "2026-04-01T00:00:00Z")
        resolve_prediction(pred1.id, 1.0)
        pred2 = record_prediction("B?", 0.0, "2026-04-01T00:00:00Z")
        resolve_prediction(pred2.id, 0.0)
        score = compute_brier_score()
        assert score == pytest.approx(0.0)

    def test_worst_prediction(self):
        """Maximally wrong predictions should score 1.0."""
        pred1 = record_prediction("A?", 1.0, "2026-04-01T00:00:00Z")
        resolve_prediction(pred1.id, 0.0)
        pred2 = record_prediction("B?", 0.0, "2026-04-01T00:00:00Z")
        resolve_prediction(pred2.id, 1.0)
        score = compute_brier_score()
        assert score == pytest.approx(1.0)

    def test_coin_flip(self):
        """50/50 predictions should score ~0.25."""
        for i in range(100):
            pred = record_prediction(f"Q{i}?", 0.5, "2026-04-01T00:00:00Z")
            resolve_prediction(pred.id, 1.0 if i % 2 == 0 else 0.0)
        score = compute_brier_score()
        assert score == pytest.approx(0.25)

    def test_no_resolved(self):
        record_prediction("Pending?", 0.5, "2026-12-01T00:00:00Z")
        assert compute_brier_score() is None

    def test_by_category(self):
        p1 = record_prediction("A?", 0.9, "2026-04-01T00:00:00Z", category="equity")
        resolve_prediction(p1.id, 1.0)
        p2 = record_prediction("B?", 0.9, "2026-04-01T00:00:00Z", category="crypto")
        resolve_prediction(p2.id, 0.0)
        by_cat = compute_brier_by_group("category")
        assert by_cat["equity"] < by_cat["crypto"]


class TestCalibration:
    def test_calibration_bins(self):
        """Test calibration curve computation."""
        # Create predictions across probability range
        for i in range(10):
            prob = (i + 0.5) / 10
            pred = record_prediction(f"Q{i}?", prob, "2026-04-01T00:00:00Z")
            resolve_prediction(pred.id, 1.0 if prob > 0.5 else 0.0)

        cal = compute_calibration()
        assert len(cal) > 0
        for entry in cal:
            assert "bin_center" in entry
            assert "predicted_mean" in entry
            assert "actual_mean" in entry
            assert "count" in entry

    def test_empty_calibration(self):
        assert compute_calibration() == []


class TestWinRate:
    def test_perfect_wins(self):
        p1 = record_prediction("A?", 0.9, "2026-04-01T00:00:00Z")
        resolve_prediction(p1.id, 1.0)
        p2 = record_prediction("B?", 0.1, "2026-04-01T00:00:00Z")
        resolve_prediction(p2.id, 0.0)
        assert compute_win_rate() == pytest.approx(1.0)

    def test_no_wins(self):
        p1 = record_prediction("A?", 0.9, "2026-04-01T00:00:00Z")
        resolve_prediction(p1.id, 0.0)
        p2 = record_prediction("B?", 0.1, "2026-04-01T00:00:00Z")
        resolve_prediction(p2.id, 1.0)
        assert compute_win_rate() == pytest.approx(0.0)

    def test_empty(self):
        assert compute_win_rate() is None


class TestDashboard:
    def test_empty_dashboard(self):
        db = build_dashboard()
        assert db.total_predictions == 0
        assert db.edge_validated is False

    def test_dashboard_with_data(self):
        for i in range(10):
            p = record_prediction(f"Q{i}?", 0.7, "2026-04-01T00:00:00Z")
            resolve_prediction(p.id, 1.0 if i < 7 else 0.0)
        db = build_dashboard()
        assert db.total_predictions == 10
        assert db.resolved_predictions == 10
        assert db.overall_brier is not None

    def test_format_report(self):
        p = record_prediction("Test?", 0.8, "2026-04-01T00:00:00Z")
        resolve_prediction(p.id, 1.0)
        report = format_dashboard_report()
        assert "Shakti Ginko" in report
        assert "Brier" in report


class TestEdgeValidation:
    def test_not_validated_empty(self):
        result = check_edge_validation()
        assert result["validated"] is False
        assert len(result["reasons"]) > 0

    def test_not_validated_few_predictions(self):
        for i in range(10):
            p = record_prediction(f"Q{i}?", 0.9, "2026-04-01T00:00:00Z")
            resolve_prediction(p.id, 1.0)
        result = check_edge_validation()
        assert result["validated"] is False
        assert any("500" in r for r in result["reasons"])


class TestPending:
    def test_get_pending(self):
        record_prediction("Pending1?", 0.5, "2026-12-01T00:00:00Z")
        record_prediction("Pending2?", 0.6, "2026-12-01T00:00:00Z")
        p3 = record_prediction("Resolved?", 0.7, "2026-04-01T00:00:00Z")
        resolve_prediction(p3.id, 1.0)
        pending = get_pending_predictions()
        assert len(pending) == 2

    def test_get_overdue(self):
        record_prediction("Overdue?", 0.5, "2020-01-01T00:00:00Z")
        record_prediction("Future?", 0.5, "2030-01-01T00:00:00Z")
        overdue = get_overdue_predictions()
        assert len(overdue) == 1
        assert overdue[0].question == "Overdue?"


class TestLogResolutionNotification:
    def test_writes_notification_file(self):
        """log_resolution_notification creates the JSONL file and writes an entry."""
        pred_dict = {
            "question": "Will SPY close higher?",
            "probability": 0.7,
            "prediction_id": "abc123",
        }
        log_resolution_notification(pred_dict, outcome=1.0, brier_score=0.09)
        assert NOTIFICATIONS_FILE.exists()
        lines = NOTIFICATIONS_FILE.read_text().strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["question"] == "Will SPY close higher?"
        assert entry["probability"] == 0.7
        assert entry["outcome"] == 1.0
        assert entry["brier_score"] == 0.09
        assert entry["prediction_id"] == "abc123"
        assert "timestamp" in entry

    def test_appends_multiple_notifications(self):
        """Multiple calls append separate lines."""
        for i in range(3):
            log_resolution_notification(
                {"question": f"Q{i}?", "probability": 0.5, "id": f"id{i}"},
                outcome=1.0,
                brier_score=0.25,
            )
        lines = NOTIFICATIONS_FILE.read_text().strip().split("\n")
        assert len(lines) == 3

    def test_uses_id_fallback(self):
        """Falls back to 'id' key when 'prediction_id' is absent."""
        log_resolution_notification(
            {"question": "Test?", "probability": 0.5, "id": "fallback_id"},
            outcome=0.0,
            brier_score=0.25,
        )
        entry = json.loads(NOTIFICATIONS_FILE.read_text().strip())
        assert entry["prediction_id"] == "fallback_id"


class TestWebhookNotify:
    @pytest.mark.asyncio
    async def test_returns_false_when_no_url(self):
        """webhook_notify returns False when GINKO_WEBHOOK_URL is not set."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GINKO_WEBHOOK_URL", None)
            result = await webhook_notify(
                {"question": "Test?", "probability": 0.5},
                outcome=1.0,
                brier_score=0.25,
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_sends_webhook_on_success(self):
        """webhook_notify returns True when the POST succeeds."""
        # Create a resolved prediction so compute_brier_score() returns a value
        p = record_prediction("Webhook test?", 0.8, "2026-04-01T00:00:00Z")
        resolve_prediction(p.id, 1.0)

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = lambda: None

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.dict(os.environ, {"GINKO_WEBHOOK_URL": "https://example.com/hook"}):
            with patch("dharma_swarm.ginko_brier.httpx.AsyncClient", return_value=mock_client):
                result = await webhook_notify(
                    {"question": "Will SPY go up?", "probability": 0.7},
                    outcome=1.0,
                    brier_score=0.09,
                )
                assert result is True

        # Verify the POST was called with correct payload shape
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "https://example.com/hook"
        payload = call_args[1]["json"]
        assert payload["prediction_question"] == "Will SPY go up?"
        assert payload["probability"] == 0.7
        assert payload["outcome"] == 1.0
        assert payload["brier_score"] == 0.09
        assert "running_brier" in payload
        assert "timestamp" in payload

    @pytest.mark.asyncio
    async def test_returns_false_on_http_error(self):
        """webhook_notify returns False on HTTP error status."""
        import httpx

        mock_response = AsyncMock()
        mock_response.status_code = 500
        mock_response.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError(
                "Server Error",
                request=httpx.Request("POST", "https://example.com/hook"),
                response=httpx.Response(500),
            )
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.dict(os.environ, {"GINKO_WEBHOOK_URL": "https://example.com/hook"}):
            with patch("dharma_swarm.ginko_brier.httpx.AsyncClient", return_value=mock_client):
                result = await webhook_notify(
                    {"question": "Test?", "probability": 0.5},
                    outcome=0.0,
                    brier_score=0.25,
                )
                assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_connection_error(self):
        """webhook_notify returns False on connection failure."""
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=ConnectionError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.dict(os.environ, {"GINKO_WEBHOOK_URL": "https://example.com/hook"}):
            with patch("dharma_swarm.ginko_brier.httpx.AsyncClient", return_value=mock_client):
                result = await webhook_notify(
                    {"question": "Test?", "probability": 0.5},
                    outcome=1.0,
                    brier_score=0.25,
                )
                assert result is False
