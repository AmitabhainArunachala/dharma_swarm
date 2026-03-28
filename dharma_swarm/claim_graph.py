"""Claim graph substrate for governance-oriented retrieval.

Builds a lightweight, deterministic graph projection over DharmaCorpus claims.
The goal is not a maximal knowledge graph. The goal is a stable substrate for
citations, contradictions, prescriptions, and audit findings that can feed the
control plane without adding heavyweight dependencies.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Iterable

from pydantic import BaseModel, Field

from dharma_swarm.dharma_corpus import Claim, ClaimStatus
from dharma_swarm.models import _new_id, _utc_now


def _declared_contradiction_targets(claim: Claim) -> set[str]:
    targets: set[str] = set()

    for tag in claim.tags:
        lowered = tag.strip().lower()
        for prefix in ("contradiction:", "contradicts:", "opposes:"):
            if lowered.startswith(prefix):
                target = tag.split(":", 1)[1].strip()
                if target:
                    targets.add(target)

    for counterargument in claim.counterarguments:
        text = counterargument.strip()
        if text.startswith("claim:"):
            target = text.split(":", 1)[1].strip()
            if target:
                targets.add(target)

    return targets


class CitationEdge(BaseModel):
    claim_id: str
    source_ref: str
    evidence_type: str
    description: str = ""


class Contradiction(BaseModel):
    contradiction_id: str
    claim_ids: list[str]
    reason: str
    source: str = "declared"
    provenance: list[str] = Field(default_factory=list)


class Prescription(BaseModel):
    prescription_id: str = Field(default_factory=_new_id)
    source_finding_id: str
    target_surface: str
    prescription_type: str
    bounded_change: str
    supporting_claim_ids: list[str] = Field(default_factory=list)
    contradiction_ids: list[str] = Field(default_factory=list)
    human_review_required: bool = False
    rollback_plan: str = ""
    provenance: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: _utc_now().isoformat())


class AuditFinding(BaseModel):
    finding_id: str = Field(default_factory=_new_id)
    title: str
    summary: str
    severity: str = "medium"
    source_artifact: str = ""
    relevant_text: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: _utc_now().isoformat())


class ClaimGraph(BaseModel):
    claims: list[Claim] = Field(default_factory=list)
    citation_edges: list[CitationEdge] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)

    def claim_map(self) -> dict[str, Claim]:
        return {claim.id: claim for claim in self.claims}

    def by_tag(self, tag: str) -> list[Claim]:
        return [claim for claim in self.claims if tag in claim.tags]

    def by_category(self, category: str) -> list[Claim]:
        category_value = str(category)
        return [claim for claim in self.claims if str(claim.category) == category_value]

    def by_provenance(self, needle: str) -> list[Claim]:
        lowered = needle.lower()
        claim_ids = {
            edge.claim_id
            for edge in self.citation_edges
            if lowered in edge.source_ref.lower() or lowered in edge.description.lower()
        }
        return [claim for claim in self.claims if claim.id in claim_ids]

    def by_confidence(self, minimum: float) -> list[Claim]:
        return [claim for claim in self.claims if claim.confidence >= minimum]

    def contradictions_for_claim_ids(self, claim_ids: Iterable[str]) -> list[Contradiction]:
        wanted = set(claim_ids)
        return [
            contradiction
            for contradiction in self.contradictions
            if wanted.intersection(contradiction.claim_ids)
        ]


class ClaimGraphBuilder:
    """Project claims into a queryable graph-oriented representation."""

    def build(
        self,
        claims: Iterable[Claim],
        *,
        include_statuses: set[ClaimStatus] | None = None,
    ) -> ClaimGraph:
        allowed_statuses = include_statuses or {ClaimStatus.ACCEPTED}

        filtered_claims = [
            claim
            for claim in claims
            if claim.status in allowed_statuses
        ]

        citation_edges: list[CitationEdge] = []
        contradiction_map: OrderedDict[str, Contradiction] = OrderedDict()
        claim_ids = {claim.id for claim in filtered_claims}

        for claim in filtered_claims:
            for evidence in claim.evidence_links:
                citation_edges.append(
                    CitationEdge(
                        claim_id=claim.id,
                        source_ref=evidence.url_or_ref,
                        evidence_type=evidence.type,
                        description=evidence.description,
                    )
                )

            for target in _declared_contradiction_targets(claim):
                if target not in claim_ids:
                    continue
                pair = sorted({claim.id, target})
                contradiction_id = f"ctr-{pair[0]}-{pair[1]}"
                contradiction_map.setdefault(
                    contradiction_id,
                    Contradiction(
                        contradiction_id=contradiction_id,
                        claim_ids=pair,
                        reason=f"Declared contradiction between {pair[0]} and {pair[1]}",
                        source="declared",
                        provenance=[f"claim:{claim.id}", f"claim:{target}"],
                    ),
                )

        return ClaimGraph(
            claims=filtered_claims,
            citation_edges=citation_edges,
            contradictions=list(contradiction_map.values()),
        )
