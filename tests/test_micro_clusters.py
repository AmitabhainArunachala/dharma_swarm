"""Tests for micro-cluster integrations (Phase 6).

Verifies the 5 cross-subsystem wiring patterns work correctly.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dharma_swarm.micro_clusters import (
    anomalies_to_cascade_input,
    associations_to_context_layer,
    gate_score_to_model_hint,
    run_micro_clusters,
)


class TestGateToRouting:
    def test_low_score_selects_strong(self) -> None:
        model = gate_score_to_model_hint(0.3)
        assert "claude" in model or "anthropic" in model

    def test_high_score_selects_efficient(self) -> None:
        model = gate_score_to_model_hint(0.8)
        assert "llama" in model or "free" in model

    def test_custom_threshold(self) -> None:
        model = gate_score_to_model_hint(
            0.4, threshold=0.3, strong_model="strong", weak_model="weak",
        )
        assert model == "weak"

    def test_at_threshold_selects_weak(self) -> None:
        model = gate_score_to_model_hint(0.5, threshold=0.5)
        assert "llama" in model or "free" in model


class TestAnomaliesToCascade:
    def test_converts_anomalies(self) -> None:
        anomaly = MagicMock()
        anomaly.anomaly_type = "failure_spike"
        anomaly.severity = "high"
        anomaly.description = "3 failures in 5 minutes"
        anomaly.id = "anom-1"

        result = anomalies_to_cascade_input([anomaly])
        assert len(result) == 1
        assert result[0]["source"] == "monitor"
        assert result[0]["anomaly_type"] == "failure_spike"
        assert result[0]["suggested_action"] == "investigate_error_pattern"

    def test_empty_list(self) -> None:
        assert anomalies_to_cascade_input([]) == []

    def test_unknown_anomaly_type(self) -> None:
        anomaly = MagicMock()
        anomaly.anomaly_type = "unknown_thing"
        anomaly.severity = "low"
        anomaly.description = "weird"
        anomaly.id = "anom-2"

        result = anomalies_to_cascade_input([anomaly])
        assert result[0]["suggested_action"] == "investigate"


class TestAssociationsToContext:
    def test_filters_by_strength(self) -> None:
        strong = MagicMock(
            source_a="A", source_b="B",
            resonance_type="semantic", strength=0.8,
        )
        weak = MagicMock(
            source_a="C", source_b="D",
            resonance_type="temporal", strength=0.1,
        )
        result = associations_to_context_layer([strong, weak], min_strength=0.3)
        assert len(result["tier5_associations"]) == 1
        assert result["tier5_associations"][0]["source_a"] == "A"

    def test_respects_max_items(self) -> None:
        assocs = [
            MagicMock(
                source_a=f"S{i}", source_b=f"T{i}",
                resonance_type="r", strength=0.9 - i * 0.01,
            )
            for i in range(10)
        ]
        result = associations_to_context_layer(assocs, max_items=3)
        assert len(result["tier5_associations"]) == 3

    def test_empty_returns_empty(self) -> None:
        result = associations_to_context_layer([])
        assert result["tier5_associations"] == []
        assert result["tier5_summary"] == ""

    def test_summary_format(self) -> None:
        assoc = MagicMock(
            source_a="X", source_b="Y",
            resonance_type="causal", strength=0.75,
        )
        result = associations_to_context_layer([assoc])
        assert "X ↔ Y" in result["tier5_summary"]
        assert "causal" in result["tier5_summary"]


class TestRunMicroClusters:
    @pytest.mark.asyncio
    async def test_all_none_returns_empty(self) -> None:
        result = await run_micro_clusters()
        assert result == {}

    @pytest.mark.asyncio
    async def test_partial_subsystems(self) -> None:
        """Only available subsystems are wired."""
        mock_monitor = AsyncMock()
        mock_report = MagicMock()
        mock_report.anomalies = []
        mock_monitor.check_health.return_value = mock_report

        result = await run_micro_clusters(monitor=mock_monitor)
        # No anomalies → no cascade inputs key
        assert "anomaly_cascade_inputs" not in result

    @pytest.mark.asyncio
    async def test_monitor_with_anomalies(self) -> None:
        anomaly = MagicMock()
        anomaly.anomaly_type = "agent_silent"
        anomaly.severity = "medium"
        anomaly.description = "Agent X silent for 10 min"
        anomaly.id = "a1"

        mock_monitor = AsyncMock()
        mock_report = MagicMock()
        mock_report.anomalies = [anomaly]
        mock_monitor.check_health.return_value = mock_report

        result = await run_micro_clusters(monitor=mock_monitor)
        assert result["anomaly_cascade_inputs"] == 1

    @pytest.mark.asyncio
    async def test_subconscious_enrichment(self) -> None:
        assoc = MagicMock(
            source_a="P", source_b="Q",
            resonance_type="pattern", strength=0.6,
        )
        mock_subconscious = AsyncMock()
        mock_subconscious.dream.return_value = [assoc]

        result = await run_micro_clusters(subconscious=mock_subconscious)
        assert result["context_enrichments"] == 1
