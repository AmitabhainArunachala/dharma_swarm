from __future__ import annotations

import json
import tempfile
from pathlib import Path
import unittest

from dharma_swarm.operator_core.adapters import (
    event_envelope_from_legacy_event,
    permission_decision_from_tool_call,
    routing_decision_from_policy,
    runtime_snapshot_from_operator_snapshot,
    session_from_meta,
)
from dharma_swarm.operator_core.permission_payloads import (
    build_permission_decision_payload,
    build_permission_history_payload,
    build_permission_outcome_payload,
    build_permission_resolution_payload,
)
from dharma_swarm.operator_core.routing_payloads import build_agent_routes_payload, build_routing_decision_payload
from dharma_swarm.operator_core.runtime_payloads import build_runtime_snapshot_payload
from dharma_swarm.operator_core.workspace_payloads import build_workspace_snapshot_payload
from dharma_swarm.operator_core.contracts import (
    EventAudience,
    EventTransport,
    PermissionDecisionKind,
    PermissionRisk,
    RuntimeHealth,
)
from dharma_swarm.tui.engine.events import PermissionDecisionEvent, PermissionResolutionEvent, ToolCallComplete, ToolResult
from dharma_swarm.operator_core.permissions import GovernancePolicy
from dharma_swarm.operator_core.session_store import SessionStore


class OperatorCoreAdapterTests(unittest.TestCase):
    def test_event_envelope_from_legacy_event(self) -> None:
        event = ToolResult(
            session_id="sess-1",
            provider_id="codex",
            tool_call_id="tool-1",
            tool_name="Read",
            content="ok",
            is_error=False,
        )

        envelope = event_envelope_from_legacy_event(
            event,
            audience=EventAudience.TUI,
            transport=EventTransport.STDIO,
        )

        self.assertEqual(envelope.event_type, "tool_result")
        self.assertEqual(envelope.session_id, "sess-1")
        self.assertEqual(envelope.payload["tool_name"], "Read")
        self.assertEqual(envelope.audience, EventAudience.TUI)
        self.assertEqual(envelope.transport, EventTransport.STDIO)

    def test_session_from_meta(self) -> None:
        session = session_from_meta(
            {
                "session_id": "sess-1",
                "provider_id": "codex",
                "model_id": "gpt-5.4",
                "cwd": "/repo",
                "created_at": "2026-04-02T00:00:00Z",
                "updated_at": "2026-04-02T00:05:00Z",
                "status": "running",
                "git_branch": "main",
                "title": "active coding session",
                "provider_session_id": "provider-7",
                "total_cost_usd": 1.25,
                "total_turns": 8,
            }
        )

        self.assertEqual(session.session_id, "sess-1")
        self.assertEqual(session.branch_label, "main")
        self.assertEqual(session.summary, "active coding session")
        self.assertEqual(session.metadata["provider_session_id"], "provider-7")

    def test_routing_decision_from_policy(self) -> None:
        decision = routing_decision_from_policy(
            {
                "selected_route": "codex:gpt-5.4",
                "selected_provider": "codex",
                "selected_model": "gpt-5.4",
                "strategy": "responsive",
                "active_label": "GPT-5.4",
                "default_route": "codex:gpt-5.4",
                "targets": [{"alias": "primary"}],
                "fallback_chain": [
                    {"provider": "claude", "model": "sonnet-4.6"},
                    {"provider": "openrouter", "model": "qwen2.5-coder"},
                ],
            }
        )

        self.assertEqual(decision.provider_id, "codex")
        self.assertEqual(decision.fallback_chain[0], "claude:sonnet-4.6")
        self.assertFalse(decision.degraded)

    def test_build_routing_decision_payload_is_json_ready(self) -> None:
        payload = build_routing_decision_payload(
            {
                "selected_route": "codex:gpt-5.4",
                "selected_provider": "codex",
                "selected_model": "gpt-5.4",
                "strategy": "responsive",
                "active_label": "GPT-5.4",
                "default_route": "codex:gpt-5.4",
                "targets": [{"alias": "primary", "provider": "codex", "model": "gpt-5.4", "label": "GPT-5.4"}],
                "strategies": ["responsive", "genius"],
                "fallback_chain": [{"provider": "claude", "model": "sonnet-4.6", "label": "Sonnet 4.6"}],
            }
        )

        self.assertEqual(payload["version"], "v1")
        self.assertEqual(payload["domain"], "routing_decision")
        self.assertEqual(payload["decision"]["route_id"], "codex:gpt-5.4")
        self.assertEqual(payload["decision"]["fallback_chain"][0], "claude:sonnet-4.6")
        self.assertEqual(payload["fallback_targets"][0]["label"], "Sonnet 4.6")

    def test_build_agent_routes_payload_is_json_ready(self) -> None:
        payload = build_agent_routes_payload(
            {
                "routes": [{"intent": "deep_code_work", "provider": "codex", "model_alias": "codex-5.4", "reasoning": "high", "role": "builder"}],
                "openclaw": {"present": True, "readable": True, "agents_count": 3, "providers": ["codex", "claude"]},
                "subagent_capabilities": ["route by task type"],
            }
        )

        self.assertEqual(payload["version"], "v1")
        self.assertEqual(payload["domain"], "agent_routes")
        self.assertEqual(payload["routes"][0]["intent"], "deep_code_work")
        self.assertEqual(payload["openclaw"]["agents_count"], 3)

    def test_runtime_snapshot_from_operator_snapshot(self) -> None:
        snapshot = runtime_snapshot_from_operator_snapshot(
            {
                "runtime_db": "/tmp/runtime.db",
                "overview": {
                    "sessions": 4,
                    "claims": 10,
                    "active_claims": 2,
                    "runs": 3,
                    "active_runs": 1,
                    "artifacts": 9,
                    "promoted_facts": 6,
                    "context_bundles": 2,
                    "operator_actions": 12,
                },
                "runs": [
                    {
                        "run_id": "run-1",
                        "status": "running",
                        "failure_code": "",
                    }
                ],
                "actions": [],
            },
            repo_root="/repo",
            bridge_status="connected",
        )

        self.assertEqual(snapshot.health, RuntimeHealth.OK)
        self.assertEqual(snapshot.active_session_count, 4)
        self.assertEqual(snapshot.context_bundle_count, 2)
        self.assertEqual(snapshot.metrics["claims"], "10")
        self.assertEqual(snapshot.verification_status, "unknown")

    def test_runtime_snapshot_marks_errors_critical(self) -> None:
        snapshot = runtime_snapshot_from_operator_snapshot(
            {
                "runtime_db": "/tmp/runtime.db",
                "error": "sqlite unavailable",
                "overview": {},
                "runs": [],
                "actions": [],
            },
            repo_root="/repo",
            bridge_status="degraded",
        )

        self.assertEqual(snapshot.health, RuntimeHealth.CRITICAL)
        self.assertEqual(snapshot.warnings[0], "sqlite unavailable")

    def test_runtime_snapshot_uses_supervisor_preview_for_verification_truth(self) -> None:
        snapshot = runtime_snapshot_from_operator_snapshot(
            {
                "runtime_db": "/tmp/runtime.db",
                "overview": {
                    "sessions": 2,
                    "active_runs": 1,
                    "artifacts": 3,
                    "context_bundles": 1,
                },
                "runs": [],
                "actions": [],
            },
            repo_root="/repo",
            bridge_status="connected",
            supervisor_preview={
                "Verification status": "all 3 checks passing",
                "Next task": "ship dashboard control-plane merge",
                "Active task": "wire supervisor truth",
            },
        )

        self.assertEqual(snapshot.verification_status, "all 3 checks passing")
        self.assertEqual(snapshot.next_task, "ship dashboard control-plane merge")
        self.assertEqual(snapshot.active_task, "wire supervisor truth")

    def test_build_runtime_snapshot_payload_is_json_ready(self) -> None:
        payload = build_runtime_snapshot_payload(
            {
                "runtime_db": "/tmp/runtime.db",
                "overview": {
                    "sessions": 2,
                    "claims": 3,
                    "active_claims": 1,
                    "acknowledged_claims": 1,
                    "runs": 4,
                    "active_runs": 1,
                    "artifacts": 5,
                    "promoted_facts": 2,
                    "context_bundles": 1,
                    "operator_actions": 6,
                },
                "runs": [],
                "actions": [],
            },
            repo_root="/repo",
            bridge_status="connected",
            supervisor_preview={"Verification status": "ok"},
        )

        self.assertEqual(payload["version"], "v1")
        self.assertEqual(payload["domain"], "runtime_snapshot")
        self.assertEqual(payload["snapshot"]["repo_root"], "/repo")
        self.assertEqual(payload["snapshot"]["active_session_count"], 2)
        self.assertEqual(payload["snapshot"]["metrics"]["acknowledged_claims"], "1")

    def test_build_workspace_snapshot_payload_is_json_ready(self) -> None:
        payload = build_workspace_snapshot_payload(
            repo_root="/repo",
            git_summary={
                "branch": "main",
                "head": "abc1234",
                "staged": 1,
                "unstaged": 2,
                "untracked": 3,
                "changed_hotspots": [{"name": "terminal", "count": 4}],
                "changed_paths": ["terminal/src/app.tsx"],
                "sync_summary": "origin/main | ahead 0 | behind 1",
                "sync_status": "tracking",
                "upstream": "origin/main",
                "ahead": 0,
                "behind": 1,
            },
            topology={
                "warnings": ["sab_canonical_repo_missing"],
                "dgc": {
                    "repos": [
                        {
                            "name": "dharma_swarm",
                            "role": "canonical_core",
                            "canonical": True,
                            "path": "/repo",
                            "exists": True,
                            "is_git": True,
                            "branch": "main...origin/main",
                            "head": "abc1234",
                            "dirty": True,
                            "modified_count": 2,
                            "untracked_count": 1,
                        }
                    ]
                },
                "sab": {"repos": []},
            },
            summary=type(
                "Summary",
                (),
                {
                    "python_modules": 10,
                    "python_tests": 5,
                    "shell_scripts": 3,
                    "markdown_docs": 2,
                    "workflows": ["ci.yml"],
                    "language_mix": {".py": 20, ".md": 3},
                    "largest_python_files": [
                        type("FileMetric", (), {"path": "dharma_swarm/app.py", "lines": 120, "defs": 8, "classes": 1, "imports": 5})()
                    ],
                    "most_imported_modules": [
                        type("ModuleMetric", (), {"module": "dharma_swarm.models", "count": 7})()
                    ],
                },
            )(),
        )

        self.assertEqual(payload["version"], "v1")
        self.assertEqual(payload["domain"], "workspace_snapshot")
        self.assertEqual(payload["git"]["branch"], "main")
        self.assertEqual(payload["git"]["changed_hotspots"][0]["name"], "terminal")
        self.assertEqual(payload["topology"]["repos"][0]["name"], "dharma_swarm")
        self.assertEqual(payload["inventory"]["python_modules"], 10)
        self.assertEqual(payload["largest_python_files"][0]["path"], "dharma_swarm/app.py")

    def test_permission_decision_from_tool_call_for_safe_read(self) -> None:
        decision = permission_decision_from_tool_call(
            ToolCallComplete(
                session_id="sess-1",
                provider_id="codex",
                tool_call_id="tool-1",
                tool_name="Read",
                arguments='{"file_path":"README.md"}',
            ),
            policy=GovernancePolicy(),
        )

        self.assertEqual(decision.decision, PermissionDecisionKind.ALLOW)
        self.assertEqual(decision.risk, PermissionRisk.SAFE_READ)
        self.assertFalse(decision.requires_confirmation)

    def test_permission_decision_from_tool_call_for_gated_bash(self) -> None:
        decision = permission_decision_from_tool_call(
            ToolCallComplete(
                session_id="sess-1",
                provider_id="codex",
                tool_call_id="tool-2",
                tool_name="Bash",
                arguments="git status",
            ),
            policy=GovernancePolicy(),
        )

        self.assertEqual(decision.decision, PermissionDecisionKind.REQUIRE_APPROVAL)
        self.assertEqual(decision.risk, PermissionRisk.SHELL_OR_NETWORK)
        self.assertTrue(decision.requires_confirmation)

    def test_build_permission_decision_payload_is_json_ready(self) -> None:
        payload = build_permission_decision_payload(
            ToolCallComplete(
                session_id="sess-1",
                provider_id="codex",
                tool_call_id="tool-2",
                tool_name="Bash",
                arguments="git status",
            ),
            policy=GovernancePolicy(),
        )

        self.assertEqual(payload["version"], "v1")
        self.assertEqual(payload["domain"], "permission_decision")
        self.assertEqual(payload["action_id"][:5], "perm-")
        self.assertEqual(payload["tool_name"], "Bash")
        self.assertEqual(payload["decision"], "require_approval")
        self.assertEqual(payload["metadata"]["session_id"], "sess-1")

    def test_build_permission_resolution_payload_is_json_ready(self) -> None:
        payload = build_permission_resolution_payload(
            action_id="perm-123",
            resolution="approved",
            actor="operator",
            note="safe after inspection",
            metadata={"session_id": "sess-1"},
        )

        json.dumps(payload)
        self.assertEqual(payload["version"], "v1")
        self.assertEqual(payload["domain"], "permission_resolution")
        self.assertEqual(payload["action_id"], "perm-123")
        self.assertEqual(payload["resolution"], "approved")
        self.assertEqual(payload["actor"], "operator")
        self.assertEqual(payload["enforcement_state"], "recorded_only")
        self.assertEqual(payload["metadata"]["session_id"], "sess-1")

    def test_build_permission_outcome_payload_is_json_ready(self) -> None:
        payload = build_permission_outcome_payload(
            action_id="perm-123",
            outcome="runtime_applied",
            metadata={"session_id": "sess-1", "runtime_action_id": "approval_perm-123"},
        )

        json.dumps(payload)
        self.assertEqual(payload["version"], "v1")
        self.assertEqual(payload["domain"], "permission_outcome")
        self.assertEqual(payload["action_id"], "perm-123")
        self.assertEqual(payload["outcome"], "runtime_applied")
        self.assertEqual(payload["source"], "runtime")
        self.assertEqual(payload["metadata"]["runtime_action_id"], "approval_perm-123")

    def test_build_permission_history_payload_reconstructs_resolution_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(root=Path(tmpdir))
            session_id = store.create_session(provider_id="codex", model_id="gpt-5.4", cwd="/repo", session_id="sess-1")
            store.append_event(
                session_id,
                PermissionDecisionEvent(
                    session_id=session_id,
                    provider_id="codex",
                    action_id="perm-123",
                    tool_name="Bash",
                    risk="shell_or_network",
                    decision="require_approval",
                    rationale="Bash is not classified as safe and remains operator-gated",
                    policy_source="legacy-governance",
                    requires_confirmation=True,
                    command_prefix="git status",
                    metadata={"session_id": session_id, "provider_id": "codex", "tool_call_id": "tool-9"},
                ),
            )
            store.append_event(
                session_id,
                PermissionResolutionEvent(
                    session_id=session_id,
                    provider_id="codex",
                    action_id="perm-123",
                    resolution="approved",
                    resolved_at="2026-04-02T00:10:00Z",
                    actor="operator",
                    summary="approved perm-123",
                    enforcement_state="recorded_only",
                    metadata={"session_id": session_id, "provider_id": "codex"},
                ),
            )

            payload = build_permission_history_payload(store)

        self.assertEqual(payload["version"], "v1")
        self.assertEqual(payload["domain"], "permission_history")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["entries"][0]["decision"]["action_id"], "perm-123")
        self.assertEqual(payload["entries"][0]["resolution"]["resolution"], "approved")
        self.assertEqual(payload["entries"][0]["status"], "approved")
        self.assertFalse(payload["entries"][0]["pending"])

    def test_build_permission_history_payload_migrates_legacy_audit_only_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(root=Path(tmpdir))
            session_id = store.create_session(provider_id="codex", model_id="gpt-5.4", cwd="/repo", session_id="sess-audit")
            store.append_audit(
                session_id,
                {
                    "domain": "permission_decision",
                    "action_id": "perm-audit-1",
                    "created_at": "2026-04-02T00:00:00Z",
                    "payload": {
                        "version": "v1",
                        "domain": "permission_decision",
                        "action_id": "perm-audit-1",
                        "tool_name": "Bash",
                        "risk": "shell_or_network",
                        "decision": "require_approval",
                        "rationale": "legacy audit gated",
                        "policy_source": "legacy-governance",
                        "requires_confirmation": True,
                        "metadata": {"session_id": session_id},
                    },
                },
            )
            store.append_audit(
                session_id,
                {
                    "domain": "permission_resolution",
                    "action_id": "perm-audit-1",
                    "created_at": "2026-04-02T00:10:00Z",
                    "payload": {
                        "version": "v1",
                        "domain": "permission_resolution",
                        "action_id": "perm-audit-1",
                        "resolution": "approved",
                        "resolved_at": "2026-04-02T00:10:00Z",
                        "actor": "operator",
                        "summary": "approved perm-audit-1",
                        "enforcement_state": "recorded_only",
                        "metadata": {"session_id": session_id},
                    },
                },
            )

            payload = build_permission_history_payload(store)
            migrated_events = store.load_transcript(
                session_id,
                include_types={"permission_decision", "permission_resolution"},
            )
            remaining_audit = store.load_audit(
                session_id,
                include_domains={"permission_decision", "permission_resolution"},
            )

        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["entries"][0]["decision"]["action_id"], "perm-audit-1")
        self.assertEqual(payload["entries"][0]["resolution"]["resolution"], "approved")
        self.assertEqual(len(migrated_events), 2)
        self.assertEqual(migrated_events[0].type, "permission_decision")
        self.assertEqual(migrated_events[1].type, "permission_resolution")
        self.assertEqual(remaining_audit, [])

    def test_permission_decision_from_tool_call_for_destructive_bash(self) -> None:
        decision = permission_decision_from_tool_call(
            ToolCallComplete(
                session_id="sess-1",
                provider_id="codex",
                tool_call_id="tool-3",
                tool_name="Bash",
                arguments="git reset --hard HEAD",
            ),
            policy=GovernancePolicy(),
        )

        self.assertEqual(decision.risk, PermissionRisk.DESTRUCTIVE)

    def test_permission_decision_from_tool_call_for_blocked_tool(self) -> None:
        decision = permission_decision_from_tool_call(
            ToolCallComplete(
                session_id="sess-1",
                provider_id="codex",
                tool_call_id="tool-4",
                tool_name="Write",
                arguments='{"file_path":"danger.txt"}',
            ),
            policy=GovernancePolicy(blocked_tools={"Write"}),
        )

        self.assertEqual(decision.decision, PermissionDecisionKind.DENY)
        self.assertEqual(decision.risk, PermissionRisk.WORKSPACE_MUTATION)

    def test_build_permission_decision_payload_is_json_ready(self) -> None:
        payload = build_permission_decision_payload(
            ToolCallComplete(
                session_id="sess-1",
                provider_id="codex",
                tool_call_id="tool-5",
                tool_name="Bash",
                arguments="git status",
            ),
            policy=GovernancePolicy(),
        )

        json.dumps(payload)
        self.assertEqual(payload["version"], "v1")
        self.assertEqual(payload["domain"], "permission_decision")
        self.assertTrue(str(payload["action_id"]).startswith("perm-"))
        self.assertEqual(payload["tool_name"], "Bash")
        self.assertEqual(payload["risk"], "shell_or_network")
        self.assertEqual(payload["decision"], "require_approval")
        self.assertTrue(payload["requires_confirmation"])
        self.assertEqual(payload["command_prefix"], "git status")
        self.assertEqual(payload["metadata"]["tool_call_id"], "tool-5")
        self.assertEqual(payload["metadata"]["provider_id"], "codex")
        self.assertEqual(payload["metadata"]["session_id"], "sess-1")


if __name__ == "__main__":
    unittest.main()
