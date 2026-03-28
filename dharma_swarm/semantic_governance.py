"""Shared semantic governance substrate for the Conscious Control Plane."""

from __future__ import annotations

import re
from typing import Any, Iterable, Literal, Sequence

from pydantic import BaseModel, Field

from dharma_swarm.claim_graph import Contradiction
from dharma_swarm.dharma_corpus import Claim
from dharma_swarm.models import _new_id, _utc_now
from dharma_swarm.structured_predicate import (
    StructuredPredicate,
    _hash_embed,
    evaluate_predicate,
    semantic_similarity,
)


EnforcementLevel = Literal["allow", "log", "warn", "block", "gate_human"]

_SEVERITY_RANK: dict[str, int] = {
    "allow": 0,
    "log": 1,
    "warn": 2,
    "gate_human": 3,
    "block": 4,
}


def _action_text(action: "ActionEnvelope") -> str:
    pieces: list[str] = [action.action_type, action.content]
    pieces.extend(action.requested_tools)
    for key, value in sorted(action.metadata.items()):
        if isinstance(value, (str, int, float, bool)):
            pieces.append(f"{key}:{value}")
    return " ".join(piece for piece in pieces if piece).strip()


def _tokenize(text: str) -> set[str]:
    tokens = set(re.findall(r"[a-zA-Z0-9_]+", text.lower()))
    normalized: set[str] = set()
    for token in tokens:
        normalized.add(token)
        if token.endswith("s") and len(token) > 3:
            normalized.add(token[:-1])
    return normalized


def _lexical_overlap(text_a: str, text_b: str) -> float:
    tokens_a = _tokenize(text_a)
    tokens_b = _tokenize(text_b)
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / min(len(tokens_a), len(tokens_b))


def _declared_contradictions(claims: Sequence[Claim]) -> list[Contradiction]:
    contradictions: dict[str, Contradiction] = {}
    claim_ids = {claim.id for claim in claims}

    for claim in claims:
        targets: set[str] = set()

        for tag in claim.tags:
            lowered = tag.lower().strip()
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

        for target in targets:
            if target not in claim_ids:
                continue
            pair = sorted({claim.id, target})
            contradiction_id = f"ctr-{pair[0]}-{pair[1]}"
            contradictions.setdefault(
                contradiction_id,
                Contradiction(
                    contradiction_id=contradiction_id,
                    claim_ids=pair,
                    reason=f"Declared contradiction between {pair[0]} and {pair[1]}",
                    source="declared",
                    provenance=[f"claim:{pair[0]}", f"claim:{pair[1]}"],
                ),
            )

    return list(contradictions.values())


class ActionEnvelope(BaseModel):
    action_id: str = Field(default_factory=_new_id)
    actor_id: str
    actor_type: str
    runtime_type: str
    task_id: str | None = None
    action_type: str
    content: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    requested_tools: list[str] = Field(default_factory=list)
    provenance: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: _utc_now().isoformat())


class ClaimScore(BaseModel):
    claim_id: str
    statement: str
    score: float
    confidence: float
    enforcement: str
    matched: bool
    provenance: list[str] = Field(default_factory=list)


class GovernanceVerdict(BaseModel):
    verdict_id: str = Field(default_factory=_new_id)
    allowed: bool
    enforcement_level: EnforcementLevel
    score: float
    matched_claim_ids: list[str] = Field(default_factory=list)
    contradiction_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    rationale: str = ""
    provenance: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: _utc_now().isoformat())


class SemanticGovernanceKernel:
    """Deterministic governance kernel with zero-dependency semantic fallback."""

    def __init__(
        self,
        *,
        match_threshold: float = 0.25,
        block_threshold: float = 0.60,
    ) -> None:
        self.match_threshold = match_threshold
        self.block_threshold = block_threshold

    def embed(self, text: str) -> list[float]:
        return _hash_embed(text)

    def score_claim_relevance(
        self,
        text: str,
        claims: Iterable[Claim],
        *,
        top_k: int | None = None,
    ) -> list[ClaimScore]:
        scored: list[ClaimScore] = []
        for claim in claims:
            score = max(
                semantic_similarity(claim.statement, text),
                _lexical_overlap(claim.statement, text),
            )
            matched = score >= self.match_threshold
            scored.append(
                ClaimScore(
                    claim_id=claim.id,
                    statement=claim.statement,
                    score=score,
                    confidence=claim.confidence,
                    enforcement=claim.enforcement,
                    matched=matched,
                    provenance=[f"claim:{claim.id}"],
                )
            )

        scored.sort(key=lambda item: (item.score, item.confidence), reverse=True)
        if top_k is not None:
            return scored[:top_k]
        return scored

    def resolve_contradictions(self, claims: Sequence[Claim]) -> list[Contradiction]:
        return _declared_contradictions(claims)

    def evaluate_action(
        self,
        action: ActionEnvelope,
        claims: Sequence[Claim],
    ) -> GovernanceVerdict:
        action_text = _action_text(action)
        scores = self.score_claim_relevance(action_text, claims)
        claim_by_id = {claim.id: claim for claim in claims}
        matched_scores = [score for score in scores if score.matched]
        matched_claims = {claim.id: claim for claim in claims if claim.id in {score.claim_id for score in matched_scores}}

        contradictions = [
            contradiction
            for contradiction in self.resolve_contradictions(list(matched_claims.values()))
            if set(contradiction.claim_ids).issubset(matched_claims.keys())
        ]

        top_score = matched_scores[0].score if matched_scores else 0.0
        enforcement_level: EnforcementLevel = "allow"
        warnings: list[str] = []
        allowed = True

        for claim in claims:
            structured = getattr(claim, "structured_predicate", None)
            if not structured:
                continue
            structured_hit = evaluate_predicate(
                StructuredPredicate.model_validate(structured),
                action.metadata,
            )
            if not structured_hit:
                continue
            if claim.id not in matched_claims:
                matched_claims[claim.id] = claim
                matched_scores.append(
                    ClaimScore(
                        claim_id=claim.id,
                        statement=claim.statement,
                        score=1.0,
                        confidence=claim.confidence,
                        enforcement=claim.enforcement,
                        matched=True,
                        provenance=[f"claim:{claim.id}"],
                    )
                )

        matched_scores.sort(key=lambda item: (item.score, item.confidence), reverse=True)

        contradictions = [
            contradiction
            for contradiction in self.resolve_contradictions(list(matched_claims.values()))
            if set(contradiction.claim_ids).issubset(matched_claims.keys())
        ]

        top_score = matched_scores[0].score if matched_scores else 0.0

        for score in matched_scores:
            claim = claim_by_id[score.claim_id]
            structured = getattr(claim, "structured_predicate", None)
            structured_hit = False
            if structured:
                structured_hit = evaluate_predicate(
                    StructuredPredicate.model_validate(structured),
                    action.metadata,
                )
            weighted_score = max(score.score, 0.0) * max(claim.confidence, 0.1)
            claim_level = claim.enforcement

            if structured_hit:
                weighted_score = 1.0

            if claim_level == "block" and weighted_score >= min(self.block_threshold, 0.6):
                enforcement_level = "block"
                allowed = False
            elif claim_level == "gate_human" and _SEVERITY_RANK[claim_level] > _SEVERITY_RANK[enforcement_level]:
                enforcement_level = "gate_human"
                allowed = False
            elif claim_level == "warn" and _SEVERITY_RANK[claim_level] > _SEVERITY_RANK[enforcement_level]:
                enforcement_level = "warn"
                warnings.append(f"matched warning claim {claim.id}")
            elif claim_level == "log" and enforcement_level == "allow":
                enforcement_level = "log"

        if contradictions and enforcement_level != "block":
            enforcement_level = "gate_human"
            allowed = False
            warnings.append("contradiction collision requires review")

        rationale_parts: list[str] = []
        if matched_scores:
            top = matched_scores[:3]
            rationale_parts.append(
                "matched claims: "
                + ", ".join(f"{item.claim_id} ({item.score:.2f})" for item in top)
            )
        if contradictions:
            rationale_parts.append(
                "contradictions: "
                + ", ".join(contradiction.contradiction_id for contradiction in contradictions)
            )
        if not rationale_parts:
            rationale_parts.append("no materially relevant claims matched")

        provenance = list(action.provenance)
        provenance.append(f"action:{action.action_id}")
        for score in matched_scores:
            provenance.extend(score.provenance)
        for contradiction in contradictions:
            provenance.extend(contradiction.provenance)

        return GovernanceVerdict(
            allowed=allowed,
            enforcement_level=enforcement_level,
            score=top_score,
            matched_claim_ids=[score.claim_id for score in matched_scores],
            contradiction_ids=[contradiction.contradiction_id for contradiction in contradictions],
            warnings=warnings,
            rationale="; ".join(rationale_parts),
            provenance=sorted(set(provenance)),
        )
