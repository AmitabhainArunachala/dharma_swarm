"""Tests for the Loop Supervisor."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from dharma_swarm.loop_supervisor import (
    LoopHealth,
    LoopSupervisor,
    StateChangeTracker,
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

    def test_alert_write_failure_does_not_abort_tick(self, tmp_path, monkeypatch):
        alert_file = tmp_path / "alert.md"
        monkeypatch.setattr("dharma_swarm.loop_supervisor.ALERT_FILE", alert_file)
        original_write_text = Path.write_text

        def _raise_for_alert(self, data, *args, **kwargs):
            if self == alert_file:
                raise PermissionError("no write access")
            return original_write_text(self, data, *args, **kwargs)

        monkeypatch.setattr(Path, "write_text", _raise_for_alert)

        sup = LoopSupervisor()
        sup.register_loop("swarm", expected_interval=1.0)
        sup._loops["swarm"].last_tick = time.monotonic() - 100.0

        alerts = sup.tick()
        assert [a.alert_type for a in alerts] == ["LOOP_STALL"]

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

    def test_progress_stagnation_alert(self):
        sup = LoopSupervisor()
        sup.register_loop("overnight", expected_interval=60.0)
        sup.record_tick("overnight")

        sup.record_progress("overnight", 0.5, improved=True)
        for _ in range(3):
            sup.record_progress("overnight", 0.5, improved=False)

        alerts = sup.tick()
        progress_alerts = [a for a in alerts if a.alert_type == "NO_PROGRESS"]
        assert len(progress_alerts) == 1
        assert progress_alerts[0].loop_name == "overnight"

    def test_progress_resets_stagnation(self):
        sup = LoopSupervisor()
        sup.register_loop("overnight", expected_interval=60.0)
        sup.record_progress("overnight", 0.2, improved=True)
        sup.record_progress("overnight", 0.2, improved=False)
        sup.record_progress("overnight", 0.3, improved=True)
        assert sup._loops["overnight"].stagnant_cycles == 0


class TestCLI:
    def test_no_state(self, monkeypatch):
        monkeypatch.setattr("dharma_swarm.loop_supervisor.SUPERVISOR_STATE",
                            Path("/nonexistent"))
        rc = cmd_loop_status()
        assert rc == 0


# ---------------------------------------------------------------------------
# State Change Gate Tests
# ---------------------------------------------------------------------------


class TestStateChangeTracker:
    def test_empty_tracker_is_dead(self):
        tracker = StateChangeTracker()
        assert tracker.is_dead_cycle
        assert tracker.total_changes == 0

    def test_file_write_not_dead(self):
        tracker = StateChangeTracker()
        tracker.record_file_write("/tmp/test.py")
        assert not tracker.is_dead_cycle
        assert tracker.total_changes == 1

    def test_test_change_not_dead(self):
        tracker = StateChangeTracker()
        tracker.record_test_change(3)
        assert not tracker.is_dead_cycle
        assert tracker.total_changes == 3

    def test_metric_update_not_dead(self):
        tracker = StateChangeTracker()
        tracker.record_metric_update(2)
        assert not tracker.is_dead_cycle

    def test_reset_clears_all(self):
        tracker = StateChangeTracker()
        tracker.record_file_write("/tmp/a.py")
        tracker.record_test_change(1)
        tracker.record_metric_update(1)
        tracker.reset()
        assert tracker.is_dead_cycle
        assert tracker.total_changes == 0

    def test_to_dict(self):
        tracker = StateChangeTracker()
        tracker.record_file_write("/tmp/a.py")
        d = tracker.to_dict()
        assert d["total_changes"] == 1
        assert d["is_dead_cycle"] is False
        assert "/tmp/a.py" in d["files_written"]


class TestStateChangeGate:
    def test_no_alert_when_changes_exist(self):
        sup = LoopSupervisor()
        sup.register_loop("test_loop", expected_interval=60.0)
        sup.state_tracker.record_file_write("/tmp/test.py")
        alert = sup.check_state_change("test_loop")
        assert alert is None

    def test_alert_on_dead_cycle(self):
        sup = LoopSupervisor()
        sup.register_loop("test_loop", expected_interval=60.0)
        # No state changes recorded
        alert = sup.check_state_change("test_loop")
        assert alert is not None
        assert alert.alert_type == "DEAD_CYCLE"
        assert alert.intervention == "LOG_WARNING"

    def test_escalation_on_consecutive_dead_cycles(self):
        sup = LoopSupervisor()
        sup.register_loop("test_loop", expected_interval=60.0)

        # First dead cycle -> LOG_WARNING
        alert1 = sup.check_state_change("test_loop")
        assert alert1.intervention == "LOG_WARNING"
        sup.reset_cycle()

        # Second -> PAUSE_LOOP
        alert2 = sup.check_state_change("test_loop")
        assert alert2.intervention == "PAUSE_LOOP"
        sup.reset_cycle()

        # Third -> REDUCE_SCOPE
        alert3 = sup.check_state_change("test_loop")
        assert alert3.intervention == "REDUCE_SCOPE"

    def test_consecutive_count_resets_on_success(self):
        sup = LoopSupervisor()
        sup.register_loop("test_loop", expected_interval=60.0)

        # Two dead cycles
        sup.check_state_change("test_loop")
        sup.reset_cycle()
        sup.check_state_change("test_loop")
        sup.reset_cycle()

        # Successful cycle resets count
        sup.state_tracker.record_file_write("/tmp/x.py")
        sup.check_state_change("test_loop")
        sup.reset_cycle()

        # Next dead cycle starts from 1 again
        alert = sup.check_state_change("test_loop")
        assert alert.intervention == "LOG_WARNING"

    def test_reset_cycle_clears_tracker(self):
        sup = LoopSupervisor()
        sup.state_tracker.record_file_write("/tmp/a.py")
        sup.reset_cycle()
        assert sup.state_tracker.is_dead_cycle
