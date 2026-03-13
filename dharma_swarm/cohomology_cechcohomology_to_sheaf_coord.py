"""Bridge shared claim assessments into Cech-style sheaf coordination.

This cluster module connects the generic `CechCohomology` machinery to the
`to_sheaf_coordination` pattern used by verification pipelines. The core
invariant is that local sections encode the shared proposition itself, while
confidence and evidence remain auxiliary metadata.
"""

from __future__ import annotations

import re
from itertools import combinations
from typing import Any, Mapping, Sequence

from pydantic import BaseModel, Field

from dharma_swarm.sheaf import (
    CechCohomology,
    CoordinationProtocol,
    CoordinationResult,
    Discovery,
    InformationChannel,
    NoosphereSite,
)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(value: str) -> str:
    normalized = _SLUG_RE.sub("_", value.strip().lower()).strip("_")
    return normalized or "claim"


class LocalClaimAssessment(BaseModel):
    """One local assessment of a shared proposition."""

    source_id: str
    target_id: str
    claim_name: str = "valid"
    agrees_with_claim: bool = True
    confidence: float = 0.0
    evidence_refs: list[str] = Field(default_factory=list)
    evidence_summary: str = ""
    topic: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def claim_key(self) -> str:
        return f"target_{_slug(self.target_id)}_{_slug(self.claim_name)}"

    @property
    def proposition_content(self) -> str:
        verdict = "true" if self.agrees_with_claim else "false"
        return f"{self.claim_name}:{verdict}"

    @property
    def coordination_topic(self) -> str:
        return self.topic or f"target:{self.target_id}"

    def to_discovery(self) -> Discovery:
        return Discovery(
            agent_id=self.source_id,
            claim_key=self.claim_key,
            content=self.proposition_content,
            confidence=self.confidence,
            evidence=list(self.evidence_refs),
            perspective=self.source_id,
            metadata={
                **self.metadata,
                "target_id": self.target_id,
                "claim_name": self.claim_name,
                "agrees_with_claim": self.agrees_with_claim,
                "evidence_summary": self.evidence_summary,
            },
        )


def _normalize_assessments(
    assessments: Sequence[LocalClaimAssessment | Mapping[str, Any]],
) -> list[LocalClaimAssessment]:
    return [
        item
        if isinstance(item, LocalClaimAssessment)
        else LocalClaimAssessment.model_validate(item)
        for item in assessments
    ]


def build_complete_overlap_site(
    assessments: Sequence[LocalClaimAssessment | Mapping[str, Any]],
) -> NoosphereSite:
    """Build a fully overlapping site for a shared coordination session."""

    normalized = _normalize_assessments(assessments)
    agent_ids = list(dict.fromkeys(item.source_id for item in normalized))
    topics = list(dict.fromkeys(item.coordination_topic for item in normalized))
    channels = [
        InformationChannel(
            source_agent=left,
            target_agent=right,
            topics=list(topics),
            weight=1.0,
        )
        for left, right in combinations(agent_ids, 2)
    ]
    return NoosphereSite(agent_ids, channels)


def to_sheaf_coordination(
    assessments: Sequence[LocalClaimAssessment | Mapping[str, Any]],
    *,
    cohomology: CechCohomology | None = None,
) -> CoordinationResult | None:
    """Map local assessments onto a sheaf coordination result."""

    normalized = _normalize_assessments(assessments)
    if not normalized:
        return None

    protocol = CoordinationProtocol(
        build_complete_overlap_site(normalized),
        cohomology=cohomology,
    )
    for assessment in normalized:
        protocol.publish(assessment.source_id, [assessment.to_discovery()])
    return protocol.coordinate()


__all__ = [
    "LocalClaimAssessment",
    "build_complete_overlap_site",
    "to_sheaf_coordination",
]
