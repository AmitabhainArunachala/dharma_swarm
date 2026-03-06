"""Provider runner: execute adapter streams with normalized failure semantics."""

from __future__ import annotations

from dataclasses import dataclass, field

from .adapters.base import CompletionRequest, ProviderAdapter
from .events import CanonicalEvent, EventType


@dataclass(slots=True)
class ProviderRunResult:
    """Collected events from a provider execution."""

    events: list[CanonicalEvent] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(e.event_type == EventType.TASK_FAILED for e in self.events)


class ProviderRunner:
    """Runs a provider adapter and normalizes exceptions as failure events."""

    def __init__(self, adapter: ProviderAdapter) -> None:
        self.adapter = adapter

    async def run(self, request: CompletionRequest) -> ProviderRunResult:
        out = ProviderRunResult()
        try:
            async for event in self.adapter.stream(request):
                out.events.append(event)
        except Exception as exc:
            out.events.append(
                CanonicalEvent(
                    event_type=EventType.TASK_FAILED,
                    source_agent=self.adapter.name,
                    session_id=request.session_id,
                    payload={"error": str(exc)},
                )
            )
        return out

