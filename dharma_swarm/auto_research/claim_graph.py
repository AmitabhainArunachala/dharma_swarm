"""Minimal claim graph extraction for AutoResearch."""

from __future__ import annotations

from typing import Any

from .models import ClaimRecord, ResearchBrief, SourceDocument


def _iter_claim_texts(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        texts: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                texts.append(text)
        return texts
    return []


class ClaimGraphBuilder:
    """Extract supported claims from normalized source metadata."""

    def build(
        self,
        brief: ResearchBrief,
        sources: list[SourceDocument],
    ) -> list[ClaimRecord]:
        claims: list[ClaimRecord] = []
        for source in sources:
            for text in _iter_claim_texts(source.metadata.get("claims")):
                claims.append(
                    ClaimRecord(
                        claim_id=f"{brief.task_id}-claim-{len(claims) + 1}",
                        text=text,
                        support_level="supported",
                        supporting_source_ids=[source.source_id],
                        confidence=0.8,
                    )
                )
        return claims
