"""Tests for the sandbox policy enforcement layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from dharma_swarm.sandbox_policy import (
    AlgedonicAlert,
    CommandPolicy,
    FilesystemPolicy,
    NetworkPolicy,
    PolicyEnforcer,
    SandboxPolicy,
    check_command,
    check_filesystem,
    check_network,
    is_dangerous_command,
)


# ---------------------------------------------------------------------------
# Unit tests for policy check functions
# ---------------------------------------------------------------------------


class TestFilesystemPolicy:
    def test_blocked_path(self):
        policy = FilesystemPolicy(write_blocked=["/etc/*", "/root/*"])
        allowed, reason = check_filesystem(policy, "/etc/passwd", "write")
        assert allowed is False

    def test_allowed_path(self):
        policy = FilesystemPolicy(write_allowed=["/home/agent/*"])
        allowed, reason = check_filesystem(policy, "/home/agent/output.txt", "write")
        assert allowed is True

    def test_path_not_in_allowlist(self):
        policy = FilesystemPolicy(write_allowed=["/home/agent/*"])
        allowed, reason = check_filesystem(policy, "/tmp/secret.txt", "write")
        assert allowed is False

    def test_no_rules_default_allow(self):
        policy = FilesystemPolicy()
        allowed, reason = check_filesystem(policy, "/any/path", "read")
        assert allowed is True

    def test_block_takes_precedence(self):
        policy = FilesystemPolicy(
            write_allowed=["/home/*"],
            write_blocked=["/home/protected/*"],
        )
        allowed, _ = check_filesystem(policy, "/home/protected/secret", "write")
        assert allowed is False


class TestCommandPolicy:
    def test_blocked_command(self):
        policy = CommandPolicy(blocked=["rm -rf"])
        allowed, _ = check_command(policy, "rm -rf /home")
        assert allowed is False

    def test_allowed_command(self):
        policy = CommandPolicy(allowed=["python", "git status"])
        allowed, _ = check_command(policy, "python main.py")
        assert allowed is True

    def test_command_not_in_allowlist(self):
        policy = CommandPolicy(allowed=["python"])
        allowed, _ = check_command(policy, "curl evil.com")
        assert allowed is False

    def test_no_rules_default_allow(self):
        policy = CommandPolicy()
        allowed, _ = check_command(policy, "ls -la")
        assert allowed is True


class TestNetworkPolicy:
    def test_blocked_all_by_default(self):
        policy = NetworkPolicy()  # blocked_hosts defaults to ["*"]
        allowed, _ = check_network(policy, "evil.com")
        assert allowed is False

    def test_allowed_host(self):
        policy = NetworkPolicy(
            allowed_hosts=["api.example.com"],
            blocked_hosts=["*"],
        )
        allowed, _ = check_network(policy, "api.example.com")
        assert allowed is True

    def test_host_not_in_allowlist(self):
        policy = NetworkPolicy(
            allowed_hosts=["api.example.com"],
            blocked_hosts=["*"],
        )
        allowed, _ = check_network(policy, "malicious.com")
        assert allowed is False


class TestDangerousCommand:
    def test_rm_rf_root(self):
        assert is_dangerous_command("rm -rf /") is True

    def test_dd_command(self):
        assert is_dangerous_command("dd if=/dev/zero of=/dev/sda") is True

    def test_safe_command(self):
        assert is_dangerous_command("python main.py") is False


# ---------------------------------------------------------------------------
# Integration tests for PolicyEnforcer
# ---------------------------------------------------------------------------


@pytest.fixture
def enforcer_dir(tmp_path: Path) -> Path:
    return tmp_path / "sandbox"


@pytest.fixture
def enforcer(enforcer_dir: Path) -> PolicyEnforcer:
    return PolicyEnforcer(base_dir=enforcer_dir)


@pytest.fixture
def test_policy() -> SandboxPolicy:
    return SandboxPolicy(
        agent_id="agent-001",
        agent_name="test-agent",
        allowed_action_types=["read", "write", "propose"],
        filesystem=FilesystemPolicy(
            write_allowed=["/home/agent/*"],
            write_blocked=["/etc/*"],
        ),
        commands=CommandPolicy(
            allowed=["python", "git"],
            blocked=["rm -rf", "curl"],
        ),
        network=NetworkPolicy(
            allowed_hosts=["api.dharma.dev"],
            blocked_hosts=["*"],
        ),
    )


@pytest.mark.asyncio
async def test_init(enforcer: PolicyEnforcer, enforcer_dir: Path):
    await enforcer.init()
    assert enforcer_dir.exists()


@pytest.mark.asyncio
async def test_register_and_get_policy(enforcer: PolicyEnforcer, test_policy: SandboxPolicy):
    await enforcer.init()
    policy_id = await enforcer.register_policy(test_policy)
    assert policy_id == test_policy.id

    retrieved = await enforcer.get_policy("agent-001")
    assert retrieved is not None
    assert retrieved.agent_name == "test-agent"


@pytest.mark.asyncio
async def test_check_allowed_action(enforcer: PolicyEnforcer, test_policy: SandboxPolicy):
    await enforcer.init()
    await enforcer.register_policy(test_policy)

    result = await enforcer.check_action("agent-001", "read")
    assert result.allowed is True


@pytest.mark.asyncio
async def test_check_blocked_action_type(enforcer: PolicyEnforcer, test_policy: SandboxPolicy):
    await enforcer.init()
    await enforcer.register_policy(test_policy)

    result = await enforcer.check_action("agent-001", "delete")
    assert result.allowed is False
    assert result.tier == "B"
    assert result.violation is not None


@pytest.mark.asyncio
async def test_check_blocked_filesystem(enforcer: PolicyEnforcer, test_policy: SandboxPolicy):
    await enforcer.init()
    await enforcer.register_policy(test_policy)

    result = await enforcer.check_action(
        "agent-001", "write",
        file_path="/etc/passwd", file_operation="write",
    )
    assert result.allowed is False
    assert result.violation is not None
    assert result.violation.violation_type == "filesystem"


@pytest.mark.asyncio
async def test_check_blocked_command(enforcer: PolicyEnforcer, test_policy: SandboxPolicy):
    await enforcer.init()
    await enforcer.register_policy(test_policy)

    result = await enforcer.check_action(
        "agent-001", "write", command="curl http://evil.com",
    )
    assert result.allowed is False
    assert result.violation.violation_type == "command"


@pytest.mark.asyncio
async def test_dangerous_command_triggers_algedonic(enforcer: PolicyEnforcer, test_policy: SandboxPolicy):
    await enforcer.init()
    await enforcer.register_policy(test_policy)

    result = await enforcer.check_action(
        "agent-001", "write", command="rm -rf /",
    )
    assert result.allowed is False
    assert result.tier == "A"
    assert result.algedonic_alert is not None
    assert result.algedonic_alert.severity == "critical"

    # Verify alert stored
    alerts = await enforcer.get_algedonic_alerts()
    assert len(alerts) == 1


@pytest.mark.asyncio
async def test_revoked_policy_blocks_everything(enforcer: PolicyEnforcer, test_policy: SandboxPolicy):
    await enforcer.init()
    await enforcer.register_policy(test_policy)

    revoked = await enforcer.revoke_policy("agent-001", revoked_by="dhyana")
    assert revoked is True

    result = await enforcer.check_action("agent-001", "read")
    assert result.allowed is False
    assert result.tier == "A"
    assert result.algedonic_alert is not None


@pytest.mark.asyncio
async def test_no_policy_default_allow(enforcer: PolicyEnforcer):
    await enforcer.init()
    result = await enforcer.check_action("unknown-agent", "anything")
    assert result.allowed is True
    assert result.tier == "C"


@pytest.mark.asyncio
async def test_acknowledge_alert(enforcer: PolicyEnforcer, test_policy: SandboxPolicy):
    await enforcer.init()
    await enforcer.register_policy(test_policy)

    # Trigger an alert
    await enforcer.check_action("agent-001", "write", command="rm -rf /")

    alerts = await enforcer.get_algedonic_alerts(acknowledged=False)
    assert len(alerts) == 1

    acked = await enforcer.acknowledge_alert(alerts[0].id, "dhyana")
    assert acked is True

    # Unacknowledged should be empty now
    unacked = await enforcer.get_algedonic_alerts(acknowledged=False)
    assert len(unacked) == 0


@pytest.mark.asyncio
async def test_violations_filtered(enforcer: PolicyEnforcer, test_policy: SandboxPolicy):
    await enforcer.init()
    await enforcer.register_policy(test_policy)

    await enforcer.check_action("agent-001", "delete")
    await enforcer.check_action("agent-001", "write", command="rm -rf /")

    all_v = await enforcer.get_violations()
    assert len(all_v) == 2

    critical = await enforcer.get_violations(severity="critical")
    assert len(critical) == 1
