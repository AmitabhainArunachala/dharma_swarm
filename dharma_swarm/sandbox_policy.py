"""Agent Sandbox Policy — gate-as-sandbox runtime enforcement layer.

Extends the existing sandbox.py (execution isolation) and telos_gates.py
(gate evaluation) with declarative per-agent sandbox policies that enforce
filesystem, command, network, and resource constraints.

Closes VSM Gap #3 (Algedonic Signal) by routing critical violations
directly to Dhyana (S5 override).

Ground: Beer (S3 control + S5 override), Dada Bhagwan (witness observes all),
Ashby (requisite variety in security policy), Varela (autopoietic boundary
= sandbox membrane), P1, P3, P6.
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from dharma_swarm.models import _new_id, _utc_now

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_POLICY_DIR = Path.home() / ".dharma" / "sandbox"
_POLICY_FILE = "policies.jsonl"
_VIOLATIONS_FILE = "violations.jsonl"
_ALGEDONIC_FILE = "algedonic_alerts.jsonl"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class FilesystemPolicy(BaseModel):
    """Filesystem access rules for an agent."""
    read_allowed: list[str] = Field(default_factory=list)  # glob patterns
    write_allowed: list[str] = Field(default_factory=list)
    read_blocked: list[str] = Field(default_factory=list)
    write_blocked: list[str] = Field(default_factory=list)


class CommandPolicy(BaseModel):
    """Command execution rules for an agent."""
    allowed: list[str] = Field(default_factory=list)  # command prefixes
    blocked: list[str] = Field(default_factory=list)


class NetworkPolicy(BaseModel):
    """Network access rules for an agent."""
    allowed_hosts: list[str] = Field(default_factory=list)
    blocked_hosts: list[str] = Field(default_factory=lambda: ["*"])


class ResourcePolicy(BaseModel):
    """Resource limits for an agent."""
    max_memory_mb: int = 512
    max_cpu_cores: int = 1
    max_disk_mb: int = 1024
    max_actions_per_minute: int = 60


class SandboxPolicy(BaseModel):
    """Complete sandbox policy for an agent.

    Corresponds to a property on an agent's OntologyObj, making agents
    discover their own constraints by querying the ontology (P4).
    """

    id: str = Field(default_factory=_new_id)
    agent_id: str
    agent_name: str = ""
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    # Ontology scope
    workspace_root: str = ""
    allowed_action_types: list[str] = Field(default_factory=list)
    allowed_object_types: list[str] = Field(default_factory=list)

    # Runtime policies
    filesystem: FilesystemPolicy = Field(default_factory=FilesystemPolicy)
    commands: CommandPolicy = Field(default_factory=CommandPolicy)
    network: NetworkPolicy = Field(default_factory=NetworkPolicy)
    resources: ResourcePolicy = Field(default_factory=ResourcePolicy)

    # Escalation
    escalation_on_violation: str = "block_and_alert"
    is_active: bool = True


class SandboxViolation(BaseModel):
    """A recorded sandbox policy violation."""

    id: str = Field(default_factory=_new_id)
    timestamp: datetime = Field(default_factory=_utc_now)
    agent_id: str
    agent_name: str = ""
    policy_id: str
    violation_type: str  # filesystem, command, network, resource, action_type
    severity: str = "high"  # critical, high, medium, low
    description: str
    action_attempted: str = ""
    policy_rule: str = ""
    enforcement: str = "blocked"  # blocked, allowed_with_log, killed


class AlgedonicAlert(BaseModel):
    """Emergency alert bypassing normal channels to reach Dhyana (S5).

    The algedonic channel from Beer's VSM — pain/pleasure signals
    that bypass management hierarchy. Closes VSM Gap #3.
    """

    id: str = Field(default_factory=_new_id)
    timestamp: datetime = Field(default_factory=_utc_now)
    source: str
    severity: str = "critical"
    message: str
    violation_id: str = ""
    agent_id: str = ""
    acknowledged: bool = False
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class EnforcementResult(BaseModel):
    """Result of enforcing a sandbox policy check."""

    allowed: bool
    reason: str = ""
    tier: str = "C"  # A (hard block + algedonic), B (block), C (monitor)
    violation: Optional[SandboxViolation] = None
    algedonic_alert: Optional[AlgedonicAlert] = None


# ---------------------------------------------------------------------------
# Policy checking functions
# ---------------------------------------------------------------------------


def check_filesystem(
    policy: FilesystemPolicy, path: str, operation: str,
) -> tuple[bool, str]:
    """Check if a filesystem operation is allowed by policy."""
    blocked = policy.write_blocked if operation == "write" else policy.read_blocked
    allowed = policy.write_allowed if operation == "write" else policy.read_allowed

    for pattern in blocked:
        if fnmatch.fnmatch(path, pattern):
            return False, f"Path {path} matches blocked pattern '{pattern}'"

    if not allowed:
        return True, "No allow rules — default allow"
    for pattern in allowed:
        if fnmatch.fnmatch(path, pattern):
            return True, f"Path matches allowed pattern '{pattern}'"
    return False, f"Path {path} not in any allowed pattern"


def check_command(policy: CommandPolicy, command: str) -> tuple[bool, str]:
    """Check if a command is allowed by policy."""
    cmd_lower = command.lower().strip()
    for pattern in policy.blocked:
        if cmd_lower.startswith(pattern.lower()):
            return False, f"Command matches blocked prefix '{pattern}'"
    if not policy.allowed:
        return True, "No allow rules — default allow"
    for pattern in policy.allowed:
        if cmd_lower.startswith(pattern.lower()):
            return True, f"Command matches allowed prefix '{pattern}'"
    return False, f"Command '{command}' not in any allowed prefix"


def check_network(policy: NetworkPolicy, host: str) -> tuple[bool, str]:
    """Check if network access to a host is allowed."""
    for pattern in policy.blocked_hosts:
        if pattern == "*" and policy.allowed_hosts:
            continue
        if fnmatch.fnmatch(host, pattern):
            return False, f"Host {host} matches blocked pattern '{pattern}'"
    if not policy.allowed_hosts:
        if "*" in policy.blocked_hosts:
            return False, "All hosts blocked by default"
        return True, "No restrictions"
    for pattern in policy.allowed_hosts:
        if fnmatch.fnmatch(host, pattern):
            return True, f"Host matches allowed pattern '{pattern}'"
    return False, f"Host {host} not in any allowed pattern"


# ---------------------------------------------------------------------------
# Dangerous command detection
# ---------------------------------------------------------------------------

_DANGEROUS_COMMANDS = ["rm -rf /", "dd if=", "mkfs", "> /dev/", "chmod -R 777 /"]


def is_dangerous_command(command: str) -> bool:
    """Check if a command is dangerous enough to warrant Tier A enforcement."""
    cmd_lower = command.lower()
    return any(d in cmd_lower for d in _DANGEROUS_COMMANDS)


# ---------------------------------------------------------------------------
# PolicyEnforcer
# ---------------------------------------------------------------------------


class PolicyEnforcer:
    """Manages sandbox policies, enforces checks, records violations.

    Sits alongside the existing SandboxManager (sandbox.py) which handles
    execution isolation. This class handles declarative policy enforcement.

    All violations are witnessed (P6). Critical violations trigger algedonic
    alerts to Dhyana (S5). Even emergency stops leave an audit trail.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or _DEFAULT_POLICY_DIR
        self.policies_path = self.base_dir / _POLICY_FILE
        self.violations_path = self.base_dir / _VIOLATIONS_FILE
        self.algedonic_path = self.base_dir / _ALGEDONIC_FILE
        self._policies: dict[str, SandboxPolicy] = {}

    # -- lifecycle -----------------------------------------------------------

    async def init(self) -> None:
        await asyncio.to_thread(self._init_sync)

    def _init_sync(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        if self.policies_path.exists():
            self._load_policies()

    def _load_policies(self) -> None:
        self._policies.clear()
        for line in self.policies_path.read_text().strip().split("\n"):
            if not line:
                continue
            try:
                policy = SandboxPolicy.model_validate(json.loads(line))
                self._policies[policy.agent_id] = policy
            except (json.JSONDecodeError, ValueError):
                continue

    def _save_policies(self) -> None:
        with open(self.policies_path, "w") as f:
            for policy in self._policies.values():
                f.write(json.dumps(json.loads(policy.model_dump_json()), default=str) + "\n")

    # -- policy management ---------------------------------------------------

    async def register_policy(self, policy: SandboxPolicy) -> str:
        """Register or update a sandbox policy for an agent."""
        return await asyncio.to_thread(self._register_sync, policy)

    def _register_sync(self, policy: SandboxPolicy) -> str:
        self._policies[policy.agent_id] = policy
        self._save_policies()
        return policy.id

    async def get_policy(self, agent_id: str) -> Optional[SandboxPolicy]:
        return self._policies.get(agent_id)

    async def revoke_policy(self, agent_id: str, revoked_by: str = "dharma_kernel") -> bool:
        """Revoke an agent's sandbox policy. Beer's S5 override."""
        return await asyncio.to_thread(self._revoke_sync, agent_id, revoked_by)

    def _revoke_sync(self, agent_id: str, revoked_by: str) -> bool:
        policy = self._policies.get(agent_id)
        if not policy:
            return False
        policy.is_active = False
        policy.updated_at = _utc_now()
        self._save_policies()
        self._store_algedonic(AlgedonicAlert(
            source="policy_enforcer",
            severity="high",
            message=f"Policy revoked for agent {agent_id} by {revoked_by}",
            agent_id=agent_id,
        ))
        return True

    # -- enforcement ---------------------------------------------------------

    async def check_action(
        self,
        agent_id: str,
        action_type: str,
        *,
        file_path: str = "",
        file_operation: str = "",
        command: str = "",
        network_host: str = "",
    ) -> EnforcementResult:
        """Check if an action is allowed by the agent's sandbox policy."""
        return await asyncio.to_thread(
            self._check_action_sync, agent_id, action_type,
            file_path, file_operation, command, network_host,
        )

    def _check_action_sync(
        self,
        agent_id: str,
        action_type: str,
        file_path: str,
        file_operation: str,
        command: str,
        network_host: str,
    ) -> EnforcementResult:
        policy = self._policies.get(agent_id)

        if not policy:
            return EnforcementResult(
                allowed=True,
                reason="No sandbox policy registered — default allow",
                tier="C",
            )

        if not policy.is_active:
            violation = self._record_violation(
                agent_id, policy.id, "policy_revoked", "critical",
                f"Agent {agent_id} attempted action with revoked policy",
                action_type,
            )
            alert = self._trigger_algedonic(
                "sandbox_enforcement",
                f"Revoked agent {agent_id} attempted: {action_type}",
                violation.id, agent_id,
            )
            return EnforcementResult(
                allowed=False, reason="Policy revoked", tier="A",
                violation=violation, algedonic_alert=alert,
            )

        # Action type check
        if policy.allowed_action_types and action_type not in policy.allowed_action_types:
            violation = self._record_violation(
                agent_id, policy.id, "action_type", "high",
                f"Action type '{action_type}' not allowed",
                action_type, f"allowed: {policy.allowed_action_types}",
            )
            return EnforcementResult(
                allowed=False, reason=violation.description, tier="B",
                violation=violation,
            )

        # Filesystem check
        if file_path and file_operation:
            allowed, reason = check_filesystem(policy.filesystem, file_path, file_operation)
            if not allowed:
                violation = self._record_violation(
                    agent_id, policy.id, "filesystem", "high",
                    reason, f"{file_operation} {file_path}",
                )
                return EnforcementResult(
                    allowed=False, reason=reason, tier="B", violation=violation,
                )

        # Command check
        if command:
            allowed, reason = check_command(policy.commands, command)
            if not allowed:
                severity = "critical" if is_dangerous_command(command) else "high"
                violation = self._record_violation(
                    agent_id, policy.id, "command", severity, reason, command,
                )
                tier = "A" if severity == "critical" else "B"
                alert = None
                if tier == "A":
                    alert = self._trigger_algedonic(
                        "sandbox_enforcement",
                        f"Dangerous command blocked from {agent_id}: {command}",
                        violation.id, agent_id,
                    )
                return EnforcementResult(
                    allowed=False, reason=reason, tier=tier,
                    violation=violation, algedonic_alert=alert,
                )

        # Network check
        if network_host:
            allowed, reason = check_network(policy.network, network_host)
            if not allowed:
                violation = self._record_violation(
                    agent_id, policy.id, "network", "medium",
                    reason, f"connect to {network_host}",
                )
                return EnforcementResult(
                    allowed=False, reason=reason, tier="B", violation=violation,
                )

        return EnforcementResult(allowed=True, reason="All policy checks passed", tier="C")

    # -- violation recording -------------------------------------------------

    def _record_violation(
        self, agent_id: str, policy_id: str, vtype: str,
        severity: str, description: str, action: str = "", rule: str = "",
    ) -> SandboxViolation:
        policy = self._policies.get(agent_id)
        violation = SandboxViolation(
            agent_id=agent_id,
            agent_name=policy.agent_name if policy else "",
            policy_id=policy_id,
            violation_type=vtype,
            severity=severity,
            description=description,
            action_attempted=action,
            policy_rule=rule,
        )
        self._store_violation(violation)
        return violation

    def _store_violation(self, violation: SandboxViolation) -> None:
        with open(self.violations_path, "a") as f:
            f.write(json.dumps(json.loads(violation.model_dump_json()), default=str) + "\n")

    # -- algedonic channel ---------------------------------------------------

    def _trigger_algedonic(
        self, source: str, message: str, violation_id: str = "", agent_id: str = "",
    ) -> AlgedonicAlert:
        alert = AlgedonicAlert(
            source=source, message=message,
            violation_id=violation_id, agent_id=agent_id,
        )
        self._store_algedonic(alert)
        return alert

    def _store_algedonic(self, alert: AlgedonicAlert) -> None:
        with open(self.algedonic_path, "a") as f:
            f.write(json.dumps(json.loads(alert.model_dump_json()), default=str) + "\n")

    # -- read ----------------------------------------------------------------

    async def get_violations(
        self, agent_id: Optional[str] = None, severity: Optional[str] = None, limit: int = 50,
    ) -> list[SandboxViolation]:
        return await asyncio.to_thread(self._get_violations_sync, agent_id, severity, limit)

    def _get_violations_sync(
        self, agent_id: Optional[str], severity: Optional[str], limit: int,
    ) -> list[SandboxViolation]:
        if not self.violations_path.exists():
            return []
        violations: list[SandboxViolation] = []
        for line in self.violations_path.read_text().strip().split("\n"):
            if not line:
                continue
            try:
                v = SandboxViolation.model_validate(json.loads(line))
                if agent_id and v.agent_id != agent_id:
                    continue
                if severity and v.severity != severity:
                    continue
                violations.append(v)
            except (json.JSONDecodeError, ValueError):
                continue
        violations.sort(key=lambda v: v.timestamp, reverse=True)
        return violations[:limit]

    async def get_algedonic_alerts(
        self, acknowledged: Optional[bool] = None, limit: int = 20,
    ) -> list[AlgedonicAlert]:
        return await asyncio.to_thread(self._get_alerts_sync, acknowledged, limit)

    def _get_alerts_sync(self, acknowledged: Optional[bool], limit: int) -> list[AlgedonicAlert]:
        if not self.algedonic_path.exists():
            return []
        alerts: list[AlgedonicAlert] = []
        for line in self.algedonic_path.read_text().strip().split("\n"):
            if not line:
                continue
            try:
                a = AlgedonicAlert.model_validate(json.loads(line))
                if acknowledged is not None and a.acknowledged != acknowledged:
                    continue
                alerts.append(a)
            except (json.JSONDecodeError, ValueError):
                continue
        alerts.sort(key=lambda a: a.timestamp, reverse=True)
        return alerts[:limit]

    async def acknowledge_alert(self, alert_id: str, acknowledged_by: str) -> bool:
        return await asyncio.to_thread(self._ack_sync, alert_id, acknowledged_by)

    def _ack_sync(self, alert_id: str, acknowledged_by: str) -> bool:
        if not self.algedonic_path.exists():
            return False
        lines = self.algedonic_path.read_text().strip().split("\n")
        updated = False
        new_lines: list[str] = []
        for line in lines:
            if not line:
                continue
            try:
                data = json.loads(line)
                if data.get("id") == alert_id:
                    data["acknowledged"] = True
                    data["acknowledged_at"] = _utc_now().isoformat()
                    data["acknowledged_by"] = acknowledged_by
                    updated = True
                new_lines.append(json.dumps(data, default=str))
            except json.JSONDecodeError:
                new_lines.append(line)
        if updated:
            self.algedonic_path.write_text("\n".join(new_lines) + "\n")
        return updated
