"""Search contracts for AutoResearch."""

from __future__ import annotations

from typing import Any, Protocol

from .models import ResearchBrief, ResearchQuery, SourceDocument


RawSourceDocument = SourceDocument | dict[str, Any]


class SearchBackend(Protocol):
    def search(
        self,
        brief: ResearchBrief,
        queries: list[ResearchQuery],
    ) -> list[RawSourceDocument]: ...


class NullSearchBackend:
    def search(
        self,
        brief: ResearchBrief,
        queries: list[ResearchQuery],
    ) -> list[RawSourceDocument]:
        return []
