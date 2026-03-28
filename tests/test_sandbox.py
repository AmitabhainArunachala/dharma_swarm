"""Tests for dharma_swarm.sandbox."""

import pytest

from dharma_swarm.sandbox import LocalSandbox, SandboxError, SandboxManager


@pytest.mark.asyncio
async def test_execute_echo():
    sb = LocalSandbox()
    result = await sb.execute("echo hello")
    assert result.exit_code == 0
    assert "hello" in result.stdout
    assert result.duration_seconds > 0
    await sb.cleanup()


@pytest.mark.asyncio
async def test_execute_python():
    sb = LocalSandbox()
    result = await sb.execute_python("print(2 + 2)")
    assert result.exit_code == 0
    assert "4" in result.stdout
    await sb.cleanup()


@pytest.mark.asyncio
async def test_execute_timeout():
    sb = LocalSandbox()
    result = await sb.execute("sleep 10", timeout=0.5)
    assert result.timed_out
    await sb.cleanup()


@pytest.mark.asyncio
async def test_execute_failure():
    sb = LocalSandbox()
    result = await sb.execute("exit 1")
    assert result.exit_code == 1
    await sb.cleanup()


def test_safety_rm_rf():
    with pytest.raises(SandboxError):
        LocalSandbox._check_safety("rm -rf /")


def test_safety_fork_bomb():
    with pytest.raises(SandboxError):
        LocalSandbox._check_safety(":(){ :|:& };:")


def test_safety_safe_command():
    # Should not raise
    LocalSandbox._check_safety("echo hello")
    LocalSandbox._check_safety("ls -la")
    LocalSandbox._check_safety("python3 script.py")


@pytest.mark.asyncio
async def test_sandbox_manager():
    mgr = SandboxManager()
    sb = mgr.create()
    assert mgr.active_count == 1
    result = await sb.execute("echo test")
    assert result.exit_code == 0
    await mgr.shutdown_all()
    assert mgr.active_count == 0


def test_sandbox_manager_invalid_type():
    mgr = SandboxManager()
    with pytest.raises(SandboxError, match="Unknown sandbox type"):
        mgr.create(sandbox_type="nonexistent")


def test_sandbox_manager_docker_sync_raises():
    """Docker sandbox requires async creation via create_async()."""
    mgr = SandboxManager()
    with pytest.raises(SandboxError, match="async creation"):
        mgr.create(sandbox_type="docker")
