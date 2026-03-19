"""Tests for Godel Claw CLI commands and monitor extensions."""

from __future__ import annotations

import pytest

from dharma_swarm.dgc_cli import _build_parser


class TestParserNewCommands:
    """Test that new CLI commands are registered in the parser."""

    def test_dharma_status_parses(self):
        parser = _build_parser()
        args = parser.parse_args(["dharma", "status"])
        assert args.command == "dharma"
        assert args.dharma_cmd == "status"

    def test_dharma_corpus_parses(self):
        parser = _build_parser()
        args = parser.parse_args(["dharma", "corpus"])
        assert args.command == "dharma"
        assert args.dharma_cmd == "corpus"

    def test_dharma_corpus_with_filters(self):
        parser = _build_parser()
        args = parser.parse_args(["dharma", "corpus", "--status", "accepted", "--category", "safety"])
        assert args.corpus_status == "accepted"
        assert args.corpus_category == "safety"

    def test_dharma_review_parses(self):
        parser = _build_parser()
        args = parser.parse_args(["dharma", "review", "DC-2026-0001"])
        assert args.claim_id == "DC-2026-0001"

    def test_evolve_apply_parses(self):
        parser = _build_parser()
        args = parser.parse_args(["evolve", "apply", "module.py", "Add logging"])
        assert args.evolve_cmd == "apply"
        assert args.component == "module.py"

    def test_evolve_promote_parses(self):
        parser = _build_parser()
        args = parser.parse_args(["evolve", "promote", "entry123"])
        assert args.evolve_cmd == "promote"
        assert args.entry_id == "entry123"

    def test_evolve_rollback_parses(self):
        parser = _build_parser()
        args = parser.parse_args(["evolve", "rollback", "entry123", "--reason", "test"])
        assert args.evolve_cmd == "rollback"
        assert args.reason == "test"

    def test_stigmergy_parses(self):
        parser = _build_parser()
        args = parser.parse_args(["stigmergy"])
        assert args.command == "stigmergy"

    def test_stigmergy_with_file(self):
        parser = _build_parser()
        args = parser.parse_args(["stigmergy", "--file", "src/main.py"])
        assert args.stig_file == "src/main.py"

    def test_hum_parses(self):
        parser = _build_parser()
        args = parser.parse_args(["hum"])
        assert args.command == "hum"

    def test_eval_leaderboard_parses(self):
        parser = _build_parser()
        args = parser.parse_args(["eval", "leaderboard", "--limit", "7"])
        assert args.command == "eval"
        assert args.eval_cmd == "leaderboard"
        assert args.limit == 7

    def test_eval_models_parses(self):
        parser = _build_parser()
        args = parser.parse_args(["eval", "models", "--task-type", "code", "--limit", "3"])
        assert args.command == "eval"
        assert args.eval_cmd == "models"
        assert args.task_type == "code"
        assert args.limit == 3

    def test_eval_research_parses(self):
        parser = _build_parser()
        args = parser.parse_args(["eval", "research", "--task-type", "research", "--limit", "2"])
        assert args.command == "eval"
        assert args.eval_cmd == "research"
        assert args.task_type == "research"
        assert args.limit == 2


class TestMonitorExtensions:
    """Test monitor fitness_regression and bridge_summary."""

    @pytest.mark.asyncio
    async def test_fitness_regression_detected(self, tmp_path):
        from datetime import timedelta

        from dharma_swarm.archive import FitnessScore
        from dharma_swarm.models import _utc_now
        from dharma_swarm.monitor import SystemMonitor
        from dharma_swarm.traces import TraceEntry, TraceStore

        store = TraceStore(base_path=tmp_path / "traces")
        await store.init()

        # Create 3 entries with decreasing fitness
        now = _utc_now()
        for i, fit_val in enumerate([0.8, 0.6, 0.4]):
            entry = TraceEntry(
                agent="test",
                action="evolve",
                state="archived",
                timestamp=now - timedelta(minutes=30 - i * 10),
                fitness=FitnessScore(
                    correctness=fit_val,
                    elegance=fit_val,
                    dharmic_alignment=fit_val,
                    efficiency=fit_val,
                    safety=fit_val,
                ),
            )
            await store.log_entry(entry)

        monitor = SystemMonitor(trace_store=store)
        anomalies = await monitor.detect_anomalies(window_hours=1)
        types = [a.anomaly_type for a in anomalies]
        assert "fitness_regression" in types

    def test_bridge_summary_none(self):
        from dharma_swarm.monitor import SystemMonitor

        result = SystemMonitor.bridge_summary(None)
        assert result["status"] == "not_initialized"

    def test_bridge_summary_object(self):
        from dharma_swarm.monitor import SystemMonitor

        class FakeBridge:
            pass

        result = SystemMonitor.bridge_summary(FakeBridge())
        assert result["status"] == "active"
