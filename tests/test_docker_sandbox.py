"""Tests for Docker sandbox, sandbox monitor, and SandboxManager auto-selection.

Split into:
    - Unit tests (always run, mock Docker CLI)
    - Integration tests (require Docker, marked with @pytest.mark.docker)
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dharma_swarm.docker_sandbox import (
    ContainerConfig,
    ContainerEvent,
    DockerSandbox,
    NetworkMode,
)
from dharma_swarm.models import SandboxResult
from dharma_swarm.sandbox import LocalSandbox, SandboxManager
from dharma_swarm.sandbox_monitor import (
    EventSeverity,
    MonitorEvent,
    SandboxMonitor,
)


# ---------------------------------------------------------------------------
# DockerSandbox unit tests (mocked Docker CLI)
# ---------------------------------------------------------------------------

class TestDockerSandboxUnit:
    """Unit tests — Docker CLI is mocked, no real containers."""

    @pytest.mark.asyncio
    async def test_docker_available_true(self):
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.wait = AsyncMock(return_value=0)
            mock_exec.return_value = mock_proc
            assert await DockerSandbox.docker_available() is True

    @pytest.mark.asyncio
    async def test_docker_available_false_when_not_installed(self):
        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            assert await DockerSandbox.docker_available() is False

    def test_default_config(self):
        config = ContainerConfig()
        assert config.image == "python:3.11-slim"
        assert config.memory_limit == "2g"
        assert config.cpu_limit == 2.0
        assert config.network_mode == NetworkMode.BRIDGE
        assert config.gpu is False

    def test_custom_config(self):
        config = ContainerConfig(
            image="nvidia/cuda:12.0-devel",
            memory_limit="8g",
            cpu_limit=4.0,
            network_mode=NetworkMode.HOST,
            gpu=True,
        )
        assert config.gpu is True
        assert config.network_mode == NetworkMode.HOST

    def test_container_name_unique(self):
        s1 = DockerSandbox()
        s2 = DockerSandbox()
        assert s1.container_name != s2.container_name

    def test_not_running_initially(self):
        sb = DockerSandbox()
        assert sb.is_running is False
        assert sb.container_id is None
        assert sb.events == []

    def test_event_callback_called(self):
        callback = MagicMock()
        sb = DockerSandbox(event_callback=callback)
        # Manually record an event
        event = ContainerEvent(
            timestamp=1.0,
            container_id="test123",
            event_type="created",
        )
        sb._record_event(event)
        callback.assert_called_once_with(event)

    def test_network_mode_enum(self):
        assert NetworkMode.NONE.value == "none"
        assert NetworkMode.BRIDGE.value == "bridge"
        assert NetworkMode.HOST.value == "host"


# ---------------------------------------------------------------------------
# SandboxMonitor tests
# ---------------------------------------------------------------------------

class TestSandboxMonitor:
    """Tests for behavioral monitoring."""

    def test_creation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = SandboxMonitor("test-container", log_dir=Path(tmpdir))
            assert monitor.container_id == "test-container"
            assert monitor.event_count == 0

    def test_record_network_connection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = SandboxMonitor("test", log_dir=Path(tmpdir))
            event = monitor.record_network_connection(
                remote_ip="1.2.3.4", port=443
            )
            assert event.category == "network"
            assert event.severity == EventSeverity.INFO
            assert monitor.event_count == 1

    def test_ssh_connection_is_notable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = SandboxMonitor("test", log_dir=Path(tmpdir))
            event = monitor.record_network_connection(
                remote_ip="1.2.3.4", port=22
            )
            assert event.severity == EventSeverity.NOTABLE

    def test_crypto_port_is_significant(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = SandboxMonitor("test", log_dir=Path(tmpdir))
            # Bitcoin P2P port
            event = monitor.record_network_connection(
                remote_ip="1.2.3.4", port=8333
            )
            assert event.severity == EventSeverity.SIGNIFICANT

    def test_record_compute_usage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = SandboxMonitor("test", log_dir=Path(tmpdir))
            event = monitor.record_compute_usage(cpu_percent=50.0, gpu_percent=30.0)
            assert event.severity == EventSeverity.INFO

    def test_high_gpu_is_significant(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = SandboxMonitor("test", log_dir=Path(tmpdir))
            event = monitor.record_compute_usage(gpu_percent=96.0)
            assert event.severity == EventSeverity.SIGNIFICANT

    def test_record_financial_event(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = SandboxMonitor("test", log_dir=Path(tmpdir))
            event = monitor.record_financial_event(
                amount=0.001, currency="ETH", direction="earned"
            )
            assert event.category == "financial"
            assert event.severity == EventSeverity.SIGNIFICANT

    def test_large_financial_event_is_alert(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = SandboxMonitor("test", log_dir=Path(tmpdir))
            event = monitor.record_financial_event(
                amount=50.0, currency="USD", direction="spent"
            )
            assert event.severity == EventSeverity.ALERT

    def test_mining_process_is_significant(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = SandboxMonitor("test", log_dir=Path(tmpdir))
            event = monitor.record_process_creation(
                process_name="xmrig", command_line="xmrig --pool ...", pid=1234
            )
            assert event.severity == EventSeverity.SIGNIFICANT

    def test_telos_callback_on_significant(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            callback = MagicMock(return_value="pass")
            monitor = SandboxMonitor("test", log_dir=Path(tmpdir), telos_callback=callback)
            event = monitor.record_financial_event(
                amount=1.0, currency="ETH", direction="earned"
            )
            callback.assert_called_once()
            assert event.telos_evaluated is True
            assert event.telos_result == "pass"

    def test_events_persist_to_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = SandboxMonitor("test", log_dir=Path(tmpdir))
            monitor.record_network_connection("1.2.3.4", 80)
            monitor.record_compute_usage(cpu_percent=50.0)

            log_file = Path(tmpdir) / "test.jsonl"
            assert log_file.exists()
            lines = log_file.read_text().strip().split("\n")
            assert len(lines) == 2
            first = json.loads(lines[0])
            assert first["category"] == "network"

    def test_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = SandboxMonitor("test", log_dir=Path(tmpdir))
            monitor.record_network_connection("1.2.3.4", 80)
            monitor.record_network_connection("1.2.3.4", 22)
            monitor.record_financial_event(0.01, "BTC", "earned")

            s = monitor.summary()
            assert s["total_events"] == 3
            assert s["financial_events"] == 1
            assert s["by_category"]["network"] == 2

    def test_sensitive_path_is_alert(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = SandboxMonitor("test", log_dir=Path(tmpdir))
            event = monitor.record_filesystem_access("/root/.ssh/id_rsa", "read")
            assert event.severity == EventSeverity.ALERT


# ---------------------------------------------------------------------------
# SandboxManager auto-selection tests
# ---------------------------------------------------------------------------

class TestSandboxManagerAutoSelect:
    """Tests for the three-layer sandbox selection."""

    def test_sync_create_returns_local(self):
        mgr = SandboxManager()
        sb = mgr.create(sandbox_type="local")
        assert isinstance(sb, LocalSandbox)
        assert mgr.active_count == 1

    def test_sync_create_docker_raises(self):
        mgr = SandboxManager()
        with pytest.raises(Exception):
            mgr.create(sandbox_type="docker")

    @pytest.mark.asyncio
    async def test_async_create_auto_falls_back_to_local(self):
        mgr = SandboxManager(prefer_docker=False)
        sb = await mgr.create_async(sandbox_type="auto")
        assert isinstance(sb, LocalSandbox)

    @pytest.mark.asyncio
    async def test_async_create_auto_with_docker(self):
        mgr = SandboxManager(prefer_docker=True)
        with patch.object(DockerSandbox, "docker_available", return_value=True):
            sb = await mgr.create_async(sandbox_type="auto")
            assert isinstance(sb, DockerSandbox)

    @pytest.mark.asyncio
    async def test_async_create_explicit_local(self):
        mgr = SandboxManager(prefer_docker=True)
        sb = await mgr.create_async(sandbox_type="local")
        assert isinstance(sb, LocalSandbox)

    @pytest.mark.asyncio
    async def test_shutdown_all(self):
        mgr = SandboxManager(prefer_docker=False)
        sb1 = await mgr.create_async()
        sb2 = await mgr.create_async()
        assert mgr.active_count == 2
        await mgr.shutdown_all()
        assert mgr.active_count == 0

    @pytest.mark.asyncio
    async def test_docker_preferred_property(self):
        mgr = SandboxManager(prefer_docker=True)
        assert mgr.docker_preferred is True
        mgr2 = SandboxManager(prefer_docker=False)
        assert mgr2.docker_preferred is False


# ---------------------------------------------------------------------------
# Integration tests (require Docker)
# ---------------------------------------------------------------------------

@pytest.mark.docker
class TestDockerSandboxIntegration:
    """Integration tests — require Docker daemon running."""

    @pytest.mark.asyncio
    async def test_docker_is_available(self):
        assert await DockerSandbox.docker_available()

    @pytest.mark.asyncio
    async def test_full_container_lifecycle(self):
        sb = DockerSandbox(config=ContainerConfig(
            image="python:3.11-slim",
            memory_limit="512m",
            cpu_limit=1.0,
            network_mode=NetworkMode.NONE,
        ))
        try:
            assert not sb.is_running
            result = await sb.execute("echo hello", timeout=15.0)
            assert sb.is_running
            assert result.exit_code == 0
            assert "hello" in result.stdout
        finally:
            await sb.cleanup()
            assert not sb.is_running

    @pytest.mark.asyncio
    async def test_python_execution(self):
        sb = DockerSandbox(config=ContainerConfig(
            image="python:3.11-slim",
            network_mode=NetworkMode.NONE,
        ))
        try:
            result = await sb.execute_python("print(2 + 2)", timeout=15.0)
            assert result.exit_code == 0
            assert "4" in result.stdout
        finally:
            await sb.cleanup()

    @pytest.mark.asyncio
    async def test_timeout_enforcement(self):
        sb = DockerSandbox(config=ContainerConfig(
            network_mode=NetworkMode.NONE,
        ))
        try:
            result = await sb.execute("sleep 60", timeout=3.0)
            assert result.timed_out
        finally:
            await sb.cleanup()

    @pytest.mark.asyncio
    async def test_events_recorded(self):
        sb = DockerSandbox(config=ContainerConfig(
            network_mode=NetworkMode.NONE,
        ))
        try:
            await sb.execute("echo test", timeout=10.0)
            assert len(sb.events) >= 2  # created + executed
            assert sb.events[0].event_type == "created"
            assert sb.events[1].event_type == "executed"
        finally:
            await sb.cleanup()
            # Should have destroyed event
            assert any(e.event_type == "destroyed" for e in sb.events)

    @pytest.mark.asyncio
    async def test_network_none_blocks_outbound(self):
        sb = DockerSandbox(config=ContainerConfig(
            network_mode=NetworkMode.NONE,
        ))
        try:
            result = await sb.execute(
                "curl -s --max-time 3 http://example.com || echo BLOCKED",
                timeout=10.0,
            )
            # Should fail since network=none
            assert "BLOCKED" in result.stdout or result.exit_code != 0
        finally:
            await sb.cleanup()
