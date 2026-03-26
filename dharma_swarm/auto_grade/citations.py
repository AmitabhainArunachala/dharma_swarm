"""Citation scoring helpers for AutoGrade."""

from __future__ import annotations

import re

from dharma_swarm.auto_research.models import ClaimRecord

_CITATION_RE = re.compile(r"\[([^\[\]]+)\]")


def extract_citation_source_ids(citations: list[str]) -> list[str]:
    source_ids: list[str] = []
    for citation in citations:
        match = _CITATION_RE.fullmatch(str(citation).strip())
        if match:
            source_ids.append(match.group(1).strip())
    return source_ids


def citation_coverage(claims: list[ClaimRecord]) -> float:
    if not claims:
        return 0.0
    covered = sum(1 for claim in claims if claim.citations)
    return covered / len(claims)


def citation_precision(claims: list[ClaimRecord], valid_source_ids: set[str]) -> float:
    if not claims:
        return 0.0

    precise = 0
    for claim in claims:
        cited = set(extract_citation_source_ids(claim.citations))
        expected = set(claim.supporting_source_ids) | set(claim.contradicting_source_ids)
        if cited and cited.issubset(valid_source_ids) and (not expected or cited.issubset(expected)):
            precise += 1
    return precise / len(claims)


def has_fabricated_citations(claims: list[ClaimRecord], valid_source_ids: set[str]) -> bool:
    for claim in claims:
        cited = extract_citation_source_ids(claim.citations)
        if len(cited) != len(claim.citations):
            return True
        if any(source_id not in valid_source_ids for source_id in cited):
            return True
    return False
