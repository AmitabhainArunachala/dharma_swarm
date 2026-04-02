from __future__ import annotations

import unittest

from dharma_swarm.operator_core.permissions import GovernanceFilter, GovernancePolicy
from dharma_swarm.tui.engine.events import ThinkingComplete, ToolCallComplete, ToolResult


class OperatorCorePermissionsTests(unittest.TestCase):
    def test_gated_tools_require_confirmation(self) -> None:
        event = ToolCallComplete(
            session_id="sess-1",
            provider_id="codex",
            tool_call_id="tool-1",
            tool_name="Bash",
            arguments="git status",
        )
        filtered = GovernanceFilter(policy=GovernancePolicy(), session_id="sess-1").process(event)
        self.assertIsNotNone(filtered)
        self.assertTrue(filtered.provider_options["requires_confirmation"])

    def test_blocked_tools_are_suppressed(self) -> None:
        event = ToolCallComplete(
            session_id="sess-1",
            provider_id="codex",
            tool_call_id="tool-2",
            tool_name="Write",
            arguments='{"file_path":"a.txt"}',
        )
        filtered = GovernanceFilter(
            policy=GovernancePolicy(blocked_tools={"Write"}),
            session_id="sess-1",
        ).process(event)
        self.assertIsNone(filtered)

    def test_tool_results_are_sanitized_and_truncated(self) -> None:
        event = ToolResult(
            session_id="sess-1",
            provider_id="codex",
            tool_call_id="tool-3",
            tool_name="Read",
            content="ok\x01" + ("x" * 20),
        )
        filtered = GovernanceFilter(
            policy=GovernancePolicy(max_tool_output_chars=5),
            session_id="sess-1",
        ).process(event)
        self.assertIsNotNone(filtered)
        self.assertNotIn("\x01", filtered.content)
        self.assertIn("truncated", filtered.content)

    def test_thinking_audit_can_be_redirected(self) -> None:
        entries: list[dict[str, object]] = []
        filter_ = GovernanceFilter(
            policy=GovernancePolicy(),
            session_id="sess-1",
            audit_writer=entries.append,
        )
        event = ThinkingComplete(session_id="sess-1", provider_id="codex", content="private chain")
        filter_.process(event)
        self.assertEqual(entries[0]["action"], "event_forwarded")
        self.assertIn("thinking_hash", entries[0])


if __name__ == "__main__":
    unittest.main()
