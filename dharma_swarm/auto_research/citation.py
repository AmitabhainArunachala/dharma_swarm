"""Citation helpers for AutoResearch."""

from __future__ import annotations

from .models import ClaimRecord, SourceDocument


class CitationFormatter:
    def format_source(self, source: SourceDocument) -> str:
        return f"[{source.source_id}]"

    def format_claim(self, claim: ClaimRecord) -> list[str]:
        source_ids = claim.supporting_source_ids or claim.contradicting_source_ids
        return [f"[{source_id}]" for source_id in source_ids]
