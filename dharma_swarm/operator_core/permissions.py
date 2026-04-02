"""Canonical permission and governance controls for the shared operator core."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Any, Callable

from dharma_swarm.tui.engine.events import CanonicalEvent, ThinkingComplete, ToolCallComplete

HOME = Path.home()
AUDIT_ROOT = HOME / ".dharma" / "sessions"


def sanitize_control_chars(value: str) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)


@dataclass(slots=True)
class GovernancePolicy:
    redact_thinking_in_audit: bool = True
    redact_raw_events: bool = True
    max_tool_output_chars: int = 50_000

    blocked_tools: set[str] = field(default_factory=set)
    gated_tools: set[str] = field(default_factory=lambda: {"Bash", "Write", "Edit", "NotebookEdit"})
    auto_approved_tools: set[str] = field(default_factory=lambda: {"Read", "Glob", "Grep", "WebSearch", "WebFetch"})

    sanitize_tool_results: bool = True
    max_system_prompt_chars: int = 60_000

    audit_enabled: bool = True
    audit_retention_days: int = 90


class GovernanceFilter:
    """Applies policy checks, redaction, and audit logging."""

    def __init__(
        self,
        *,
        policy: GovernancePolicy,
        session_id: str,
        audit_writer: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.policy = policy
        self.session_id = session_id
        self._audit_writer = audit_writer
        self._audit_path = AUDIT_ROOT / session_id / "audit.jsonl"
        self._audit_path.parent.mkdir(parents=True, exist_ok=True)

    def process(self, event: CanonicalEvent) -> CanonicalEvent | None:
        if self.policy.redact_raw_events:
            event.raw = None

        if isinstance(event, ToolCallComplete):
            if event.tool_name in self.policy.blocked_tools:
                self._audit("tool_blocked", event)
                return None
            if event.tool_name in self.policy.gated_tools:
                opts = dict(event.provider_options)
                opts["requires_confirmation"] = True
                event.provider_options = opts

        if hasattr(event, "content"):
            content = getattr(event, "content")
            if isinstance(content, str):
                if self.policy.sanitize_tool_results:
                    content = sanitize_control_chars(content)
                if len(content) > self.policy.max_tool_output_chars:
                    original_len = len(content)
                    content = content[: self.policy.max_tool_output_chars] + f"\n\n... (truncated from {original_len} chars)"
                setattr(event, "content", content)

        if self.policy.audit_enabled:
            self._audit("event_forwarded", event)
        return event

    def _audit(self, action: str, event: CanonicalEvent) -> None:
        entry: dict[str, Any] = {
            "timestamp": time.time(),
            "action": action,
            "event_type": event.type,
            "session_id": self.session_id,
        }

        if self.policy.redact_thinking_in_audit and isinstance(event, ThinkingComplete):
            entry["thinking_hash"] = hashlib.sha256(event.content.encode("utf-8")).hexdigest()
            entry["thinking_len"] = len(event.content)
            entry["is_redacted"] = event.is_redacted
        else:
            payload = asdict(event)
            if self.policy.redact_raw_events:
                payload["raw"] = None
            entry["event"] = payload

        if self._audit_writer is not None:
            self._audit_writer(entry)
            return

        with open(self._audit_path, "a") as handle:
            handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
