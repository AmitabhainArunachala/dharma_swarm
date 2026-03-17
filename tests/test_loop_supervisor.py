"""Tests for the Loop Supervisor."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from dharma_swarm.loop_supervisor import (
    LoopHealth,
    LoopSupervisor,
    SupervisorAlert,
    _ErrorWindow,
    _escalation_level,
    cmd_loop_status,
)


class TestLoopHealth:
    def test_defaults(self):
        h = LoopHealth(name="test")
        assert h.name == "test"
        assert h.tick_count == 0
        assert h.error_count == 0
        assert h.last_tick == 0.0

    def test_is_stalled_never_ticked(self):
        h = LoopHealth(name="test")
        assert h.is_stalled is False  # Never started

    def test_is_stalled_after_timeout(self):
        h = LoopHealth(name="test", expected_interval=1.0)
        h.last_tick = time.monotonic() - 10.0  # 10s ago, 2x = 2s
        assert h.is_stalled is True

    def test_not_stalled_recent(self):
        h = LoopHealth(name="test", expected_interval=60.0)
        h.last_tick = time.monotonic() - 30.0  # 30s ago, 2x = 120s
        assert h.is_stalled is False

    def test_to_dict(self):
        h = LoopHealth(name="test", tick_count=5)
        d = h.to_dict()
        assert d["name"] == "test"
        assert d["tick_count"] == 5
        assert "is_stalled" in d
        assert "stale_seconds" in d


class TestEscalationLevel:
    def test_low_severity(self):
        assert _escalation_level(0, 1.5) == "LOG_WARNING"

    def test_pause_threshold(self):
        assert _escalation_level(4, 2.5) == "PAUSE_LOOP"

    def test_reduce_scope(self):
        assert _escalation_level(6, 3.5) == "REDUCE_SCOPE"

    def test_alert_dhyana(self):
        assert _escalation_level(15, 6.0) == "ALERT_DHYANA"


class TestErrorWindow:
    def test_not_storm_few_errors(self):
        ew = _ErrorWindow()
        ew.add("error1")
        ew.add("error2")
        assert ew.is_storm(threshold=3) is False

    def test_storm_same_error(self):
        ew = _ErrorWindow()
        for _ in range(5):
            ew.add("same error message")
        assert ew.is_storm(threshold=3) is True

    def test_no_storm_different_errors(self):
        ew = _ErrorWindow()
        for i in range(5):
            ew.add(f"unique error {i}")
        assert ew.is_storm(threshold=3) is False

    def test_window_expiry(self):
        ew = _ErrorWindow(window_seconds=0.0)  # Instant expiry
        ew.add("error")
        ew.add("error")
        ew.add("error")
        # After pruning, all should be expired
        ew.add("trigger")  # This prunes old ones
        assert ew.is_storm(threshold=3) is False


class TestLoopSupervisor:
    def test_register_and_tick(self):
        sup = LoopSupervisor()
        sup.register_loop("swarm", expected_interval=60.0)
        sup.record_tick("swarm")

        status = sup.status()
        assert "swarm" in status["loops"]
        assert status["loops"]["swarm"]["tick_count"] == 1

    def test_detect_stall(self):
        sup = LoopSupervisor()
        sup.register_loop("swarm", expected_interval=1.0)
        # Record a tick far in the past
        sup._loops["swarm"].last_tick = time.monotonic() - 100.0

        alerts = sup.tick()
        stall_alerts = [a for a in alerts if a.alert_type == "LOOP_STALL"]
        assert len(stall_alerts) == 1
        assert stall_alerts[0].loop_name == "swarm"

    def test_detect_retry_storm(self):
        sup = LoopSupervisor()
        sup.register_loop("evolution", expected_interval=600.0)
        sup.record_tick("evolution")  # Not stalled

        for _ in range(5):
            sup.record_error("evolution", "same error")

        alerts = sup.tick()
        storm_alerts = [a for a in alerts if a.alert_type == "RETRY_STORM"]
        assert len(storm_alerts) == 1

    def test_no_alerts_healthy(self):
        sup = LoopSupervisor()
        sup.register_loop("swarm", expected_interval=60.0)
        sup.record_tick("swarm")

        alerts = sup.tick()
        # Should be no stall, no storm
        stall_or_storm = [
            a for a in alerts
            if a.alert_type in ("LOOP_STALL", "RETRY_STORM")
        ]
        assert len(stall_or_storm) == 0

    def test_record_error_keeps_last_5(self):
        sup = LoopSupervisor()
        sup.register_loop("test", expected_interval=60.0)
        for i in range(10):
            sup.record_error("test", f"error_{i}")
        assert len(sup._loops["test"].last_errors) == 5

    def test_alert_file_written(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.loop_supervisor.ALERT_FILE",
                            tmp_path / "alert.md")
        sup = LoopSupervisor()
        sup.register_loop("swarm", expected_interval=1.0)
        sup._loops["swarm"].last_tick = time.monotonic() - 100.0

        sup.tick()
        alert_file = tmp_path / "alert.md"
        assert alert_file.exists()
        content = alert_file.read_text()
        assert "LOOP_STALL" in content

    def test_status_shape(self):
        sup = LoopSupervisor()
        sup.register_loop("a", 60.0)
        sup.register_loop("b", 120.0)
        status = sup.status()
        assert "loops" in status
        assert "recent_alerts" in status
        assert "total_alerts" in status
        assert len(status["loops"]) == 2

    def test_save_and_load_state(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.loop_supervisor.SUPERVISOR_STATE", tmp_path)
        sup = LoopSupervisor()
        sup.register_loop("test", 60.0)
        sup.record_tick("test")
        sup.save_state()

        loaded = LoopSupervisor.load_state()
        assert loaded is not None
        assert "test" in loaded["loops"]

    def test_eval_degradation_detection(self, monkeypatch):
        history = [
            {"pass_at_1": 1.0, "results": []},
            {"pass_at_1": 0.5, "results": []},  # 50% drop
        ]
        monkeypatch.setattr(
            "dharma_swarm.ecc_eval_harness.load_history",
            lambda: history,
        )
        sup = LoopSupervisor()
        alert = sup._check_eval_degradation()
        assert alert is not None
        assert alert.alert_type == "EVAL_REGRESSION"


class TestCLI:
    def test_no_state(self, monkeypatch):
        monkeypatch.setattr("dharma_swarm.loop_supervisor.SUPERVISOR_STATE",
                            Path("/nonexistent"))
        rc = cmd_loop_status()
        assert rc == 0
