"""Groundedness and traceability helpers for AutoGrade."""

from __future__ import annotations

from dharma_swarm.auto_research.models import ClaimRecord


def unsupported_claim_ratio(claims: list[ClaimRecord]) -> float:
    if not claims:
        return 1.0
    unsupported = 0
    for claim in claims:
        if claim.support_level != "supported" or not claim.supporting_source_ids or not claim.citations:
            unsupported += 1
    return unsupported / len(claims)


def groundedness(claims: list[ClaimRecord]) -> float:
    if not claims:
        return 0.0
    grounded = 0
    for claim in claims:
        if claim.support_level == "supported" and claim.supporting_source_ids and claim.citations:
            grounded += 1
    return grounded / len(claims)


def traceability(claims: list[ClaimRecord], valid_source_ids: set[str]) -> float:
    if not claims:
        return 0.0
    traced = 0
    for claim in claims:
        cited_source_ids = {
            citation.strip("[]")
            for citation in claim.citations
            if citation.startswith("[") and citation.endswith("]")
        }
        if (
            cited_source_ids
            and cited_source_ids.issubset(valid_source_ids)
            and cited_source_ids.issubset(set(claim.supporting_source_ids) | set(claim.contradicting_source_ids))
        ):
            traced += 1
    return traced / len(claims)
