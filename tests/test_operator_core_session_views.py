from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dharma_swarm.operator_core.session_views import build_session_catalog, build_session_detail
from dharma_swarm.operator_core.permission_payloads import build_permission_decision_payload, build_permission_resolution_payload
from dharma_swarm.operator_core.session_store import SessionStore
from dharma_swarm.tui.engine.events import (
    PermissionDecisionEvent,
    PermissionResolutionEvent,
    SessionEnd,
    SessionStart,
    TextDelta,
    ToolCallComplete,
    ToolResult,
    UsageReport,
)


class OperatorCoreSessionViewTests(unittest.TestCase):
    def test_build_session_catalog_and_detail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SessionStore(root=Path(temp_dir))
            session_id = store.create_session(
                session_id="sess-1",
                provider_id="codex",
                model_id="gpt-5.4",
                cwd="/repo",
                title="overnight build",
            )
            store.append_event(session_id, SessionStart(session_id=session_id, provider_id="codex", model="gpt-5.4"))
            store.append_event(session_id, TextDelta(session_id=session_id, provider_id="codex", content="thinking..."))
            store.append_event(
                session_id,
                ToolCallComplete(
                    session_id=session_id,
                    provider_id="codex",
                    tool_call_id="tool-1",
                    tool_name="Read",
                    arguments='{"file_path":"README.md"}',
                ),
            )
            store.append_event(
                session_id,
                ToolResult(
                    session_id=session_id,
                    provider_id="codex",
                    tool_call_id="tool-1",
                    tool_name="Read",
                    content="ok",
                ),
            )
            store.append_event(session_id, UsageReport(session_id=session_id, provider_id="codex", total_cost_usd=1.5))
            store.append_event(session_id, SessionEnd(session_id=session_id, provider_id="codex", success=True))
            store.finalize_session(session_id, status="completed", total_cost_usd=1.5, total_turns=1)
            decision = build_permission_decision_payload(
                ToolCallComplete(
                    session_id=session_id,
                    provider_id="codex",
                    tool_call_id="tool-approval-1",
                    tool_name="Bash",
                    arguments="git status",
                    provider_options={"requires_confirmation": True},
                )
            )
            resolution = build_permission_resolution_payload(
                action_id=decision["action_id"],
                resolution="approved",
                metadata={"session_id": session_id},
            )
            store.append_event(
                session_id,
                PermissionDecisionEvent(
                    session_id=session_id,
                    provider_id="codex",
                    action_id=str(decision["action_id"]),
                    tool_name=str(decision["tool_name"]),
                    risk=str(decision["risk"]),
                    decision=str(decision["decision"]),
                    rationale=str(decision["rationale"]),
                    policy_source=str(decision["policy_source"]),
                    requires_confirmation=bool(decision["requires_confirmation"]),
                    command_prefix=str(decision["command_prefix"] or "") or None,
                    metadata=dict(decision["metadata"]),
                ),
            )
            store.append_event(
                session_id,
                PermissionResolutionEvent(
                    session_id=session_id,
                    provider_id="codex",
                    action_id=str(resolution["action_id"]),
                    resolution=str(resolution["resolution"]),
                    resolved_at=str(resolution["resolved_at"]),
                    actor=str(resolution["actor"]),
                    summary=str(resolution["summary"]),
                    note=str(resolution["note"] or "") or None,
                    enforcement_state=str(resolution["enforcement_state"]),
                    metadata=dict(resolution["metadata"]),
                ),
            )

            catalog = build_session_catalog(store, cwd="/repo")
            json.dumps(catalog)
            self.assertEqual(catalog["version"], "v1")
            self.assertEqual(catalog["domain"], "session_catalog")
            self.assertEqual(catalog["count"], 1)
            self.assertTrue(catalog["sessions"][0]["replay_ok"])
            self.assertEqual(catalog["sessions"][0]["session"]["session_id"], "sess-1")
            self.assertEqual(catalog["sessions"][0]["total_turns"], 1)
            self.assertEqual(catalog["sessions"][0]["total_cost_usd"], 1.5)
            self.assertEqual(catalog["sessions"][0]["session"]["metadata"]["total_turns"], 1)

            detail = build_session_detail(store, session_id)
            json.dumps(detail)
            self.assertEqual(detail["version"], "v1")
            self.assertEqual(detail["domain"], "session_detail")
            self.assertEqual(detail["session"]["session_id"], "sess-1")
            self.assertEqual(detail["compaction_preview"]["protected_event_types"][0], "session_start")
            self.assertEqual(detail["recent_events"][-1]["event_type"], "permission_resolution")
            self.assertIn("session_end", detail["compaction_preview"]["recent_event_types"])
            self.assertEqual(detail["approval_history"]["count"], 1)
            self.assertEqual(detail["approval_history"]["entries"][0]["status"], "approved")

    def test_build_session_catalog_matches_normalized_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SessionStore(root=Path(temp_dir))
            session_id = store.create_session(
                session_id="sess-1",
                provider_id="codex",
                model_id="gpt-5.4",
                cwd=f"{temp_dir}/repo/..",
                title="normalized path",
            )
            store.finalize_session(session_id, status="completed", total_turns=0)

            catalog = build_session_catalog(store, cwd=temp_dir)

            self.assertEqual(catalog["count"], 1)
            self.assertEqual(catalog["sessions"][0]["session"]["session_id"], "sess-1")

    def test_build_session_detail_surfaces_replay_degradation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = SessionStore(root=root)
            session_id = store.create_session(
                session_id="sess-1",
                provider_id="codex",
                model_id="gpt-5.4",
                cwd="/repo",
                title="replay degraded",
            )
            snapshots_path = root / session_id / "snapshots.jsonl"
            snapshots_path.unlink()

            detail = build_session_detail(store, session_id)

            self.assertFalse(detail["replay_ok"])
            self.assertEqual(detail["replay_issues"], ["snapshot log missing"])
            self.assertEqual(detail["compaction_preview"]["event_count"], 0)
            self.assertEqual(detail["recent_events"], [])


if __name__ == "__main__":
    unittest.main()
