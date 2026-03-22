"""Tests for sandbox_monitor.py — behavioral monitoring for containers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dharma_swarm.sandbox_monitor import (
    EventSeverity,
    MonitorEvent,
    SandboxMonitor,
)


@pytest.fixture
def monitor(tmp_path: Path) -> SandboxMonitor:
    return SandboxMonitor(container_id="test-abc123", log_dir=tmp_path)


# --- Construction & properties ---


def test_container_id(monitor: SandboxMonitor) -> None:
    assert monitor.container_id == "test-abc123"


def test_initially_empty(monitor: SandboxMonitor) -> None:
    assert monitor.events == []
    assert monitor.event_count == 0


# --- Network events ---


def test_record_network_connection_basic(monitor: SandboxMonitor) -> None:
    ev = monitor.record_network_connection("1.2.3.4", 443)
    assert ev.category == "network"
    assert ev.severity == EventSeverity.INFO
    assert "1.2.3.4" in ev.description
    assert monitor.event_count == 1


def test_ssh_connection_notable(monitor: SandboxMonitor) -> None:
    ev = monitor.record_network_connection("10.0.0.1", 22)
    assert ev.severity == EventSeverity.NOTABLE


def test_crypto_port_significant(monitor: SandboxMonitor) -> None:
    for port in (8333, 8545, 30303):
        ev = monitor.record_network_connection("10.0.0.1", port)
        assert ev.severity == EventSeverity.SIGNIFICANT, f"port {port}"


# --- Compute events ---


def test_record_compute_low_usage(monitor: SandboxMonitor) -> None:
    ev = monitor.record_compute_usage(cpu_percent=30.0, gpu_percent=10.0)
    assert ev.severity == EventSeverity.INFO
    assert ev.category == "compute"


def test_record_compute_high_cpu(monitor: SandboxMonitor) -> None:
    ev = monitor.record_compute_usage(cpu_percent=95.0)
    assert ev.severity == EventSeverity.NOTABLE


def test_record_compute_extreme_gpu(monitor: SandboxMonitor) -> None:
    ev = monitor.record_compute_usage(gpu_percent=96.0)
    assert ev.severity == EventSeverity.SIGNIFICANT


# --- Financial events ---


def test_record_financial_small(monitor: SandboxMonitor) -> None:
    ev = monitor.record_financial_event(amount=0.5, currency="ETH", direction="earned")
    assert ev.severity == EventSeverity.SIGNIFICANT
    assert ev.category == "financial"


def test_record_financial_large_triggers_alert(monitor: SandboxMonitor) -> None:
    ev = monitor.record_financial_event(amount=15.0, currency="USD", direction="spent")
    assert ev.severity == EventSeverity.ALERT


# --- Process events ---


def test_record_process_normal(monitor: SandboxMonitor) -> None:
    ev = monitor.record_process_creation("python3", "python3 train.py", 1234)
    assert ev.severity == EventSeverity.INFO
    assert ev.category == "process"


def test_mining_process_significant(monitor: SandboxMonitor) -> None:
    for name in ("xmrig", "ethminer", "nbminer"):
        ev = monitor.record_process_creation(name)
        assert ev.severity == EventSeverity.SIGNIFICANT, name


# --- Filesystem events ---


def test_record_filesystem_normal(monitor: SandboxMonitor) -> None:
    ev = monitor.record_filesystem_access("/tmp/out.txt", "write")
    assert ev.severity == EventSeverity.INFO
    assert ev.category == "filesystem"


def test_sensitive_path_alert(monitor: SandboxMonitor) -> None:
    ev = monitor.record_filesystem_access("/etc/shadow", "read")
    assert ev.severity == EventSeverity.ALERT


def test_ssh_key_alert(monitor: SandboxMonitor) -> None:
    ev = monitor.record_filesystem_access("/root/.ssh/id_rsa", "read")
    assert ev.severity == EventSeverity.ALERT


# --- Severity filtering ---


def test_events_by_severity(monitor: SandboxMonitor) -> None:
    monitor.record_network_connection("1.2.3.4", 80)
    monitor.record_network_connection("1.2.3.4", 22)
    monitor.record_financial_event(20.0, "USD", "spent")

    infos = monitor.events_by_severity(EventSeverity.INFO)
    assert len(infos) == 1
    alerts = monitor.events_by_severity(EventSeverity.ALERT)
    assert len(alerts) == 1


# --- JSONL persistence ---


def test_events_persisted_to_jsonl(monitor: SandboxMonitor, tmp_path: Path) -> None:
    monitor.record_network_connection("8.8.8.8", 53)
    monitor.record_compute_usage(cpu_percent=50.0)

    log_file = tmp_path / "test-abc123.jsonl"
    assert log_file.exists()
    lines = log_file.read_text().strip().split("\n")
    assert len(lines) == 2
    rec = json.loads(lines[0])
    assert rec["category"] == "network"
    assert rec["container_id"] == "test-abc123"


# --- Telos callback ---


def test_telos_callback_on_significant(tmp_path: Path) -> None:
    results: list[str] = []

    def callback(event: MonitorEvent) -> str:
        results.append(event.description)
        return "pass"

    mon = SandboxMonitor("cb-test", log_dir=tmp_path, telos_callback=callback)
    mon.record_financial_event(5.0, "ETH", "earned")

    assert len(results) == 1
    assert mon.events[0].telos_evaluated is True
    assert mon.events[0].telos_result == "pass"


def test_telos_callback_not_called_for_info(tmp_path: Path) -> None:
    called = []

    def callback(event: MonitorEvent) -> str:
        called.append(1)
        return "pass"

    mon = SandboxMonitor("cb-test2", log_dir=tmp_path, telos_callback=callback)
    mon.record_network_connection("1.2.3.4", 80)  # INFO severity

    assert len(called) == 0


def test_telos_callback_failure_handled(tmp_path: Path) -> None:
    def bad_callback(event: MonitorEvent) -> str:
        raise RuntimeError("boom")

    mon = SandboxMonitor("cb-fail", log_dir=tmp_path, telos_callback=bad_callback)
    ev = mon.record_financial_event(5.0, "ETH", "earned")
    # Should not raise, event still recorded
    assert ev.telos_evaluated is False


# --- Summary ---


def test_summary(monitor: SandboxMonitor) -> None:
    monitor.record_network_connection("1.1.1.1", 80)
    monitor.record_compute_usage(cpu_percent=50.0)
    monitor.record_financial_event(1.0, "USDC", "earned")
    monitor.record_financial_event(20.0, "USD", "spent")

    s = monitor.summary()
    assert s["total_events"] == 4
    assert s["container_id"] == "test-abc123"
    assert s["financial_events"] == 2
    assert s["alerts"] == 1
    assert "network" in s["by_category"]
    assert "compute" in s["by_category"]
