"""Postmortem reader for failure-to-prescription diagnosis."""

from __future__ import annotations

from typing import Iterable

from pydantic import BaseModel, Field

from dharma_swarm.claim_graph import ClaimGraph, Contradiction
from dharma_swarm.models import _new_id, _utc_now
from dharma_swarm.semantic_governance import ClaimScore, SemanticGovernanceKernel


_SURFACE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "orchestrator": ("route", "routing", "dispatch", "assignment", "claim timeout"),
    "policy_compiler": ("policy", "predicate", "enforcement", "verdict", "rule"),
    "telos_gates": ("gate", "block", "unsafe", "consent", "oversight"),
    "orientation_packet": ("orientation", "context", "stale context", "self-model"),
    "claim_graph": ("claim", "citation", "contradiction", "evidence", "provenance"),
    "runtime_bridge": ("bridge", "adapter", "mcp", "a2a", "external runtime"),
}


class PostmortemArtifact(BaseModel):
    finding_id: str = Field(default_factory=_new_id)
    title: str
    summary: str
    failure_signature: str = ""
    affected_surfaces: list[str] = Field(default_factory=list)
    action_excerpt: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)
    provenance: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: _utc_now().isoformat())


class PostmortemDiagnosis(BaseModel):
    diagnosis_id: str = Field(default_factory=_new_id)
    finding_id: str
    failure_mode: str
    summary: str
    relevant_claims: list[ClaimScore] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    candidate_surfaces: list[str] = Field(default_factory=list)
    recommended_surface: str | None = None
    provenance: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: _utc_now().isoformat())


def _artifact_text(artifact: PostmortemArtifact) -> str:
    pieces = [
        artifact.title,
        artifact.summary,
        artifact.failure_signature,
        artifact.action_excerpt,
    ]
    for key, value in sorted(artifact.metadata.items()):
        pieces.append(f"{key}:{value}")
    return " ".join(piece for piece in pieces if piece)


def _infer_surfaces(artifact: PostmortemArtifact) -> list[str]:
    text = _artifact_text(artifact).lower()
    surfaces = list(artifact.affected_surfaces)
    for surface, keywords in _SURFACE_KEYWORDS.items():
        if any(keyword in text for keyword in keywords) and surface not in surfaces:
            surfaces.append(surface)
    return surfaces


def _infer_failure_mode(surfaces: Iterable[str], contradictions: list[Contradiction], text: str) -> str:
    lowered = text.lower()
    if contradictions:
        return "contradiction_drift"
    if "provenance" in lowered or "citation" in lowered:
        return "provenance_gap"
    if "stale" in lowered or "context" in lowered or "orientation" in lowered:
        return "stale_orientation"
    if "unsafe" in lowered or "block" in lowered or "consent" in lowered:
        return "unsafe_action"
    if "route" in lowered or "dispatch" in lowered or "assignment" in lowered:
        return "routing_conflict"
    if "policy" in lowered or "predicate" in lowered or "rule" in lowered:
        return "policy_mismatch"
    if "runtime_bridge" in set(surfaces):
        return "bridge_mismatch"
    return "unknown_failure_mode"


class PostmortemReader:
    """Read failure artifacts into bounded diagnoses."""

    def __init__(self, *, kernel: SemanticGovernanceKernel | None = None) -> None:
        self.kernel = kernel or SemanticGovernanceKernel()

    def read(
        self,
        artifact: PostmortemArtifact,
        graph: ClaimGraph,
        *,
        top_k: int = 5,
    ) -> PostmortemDiagnosis:
        text = _artifact_text(artifact)
        relevant_claims = self.kernel.score_claim_relevance(text, graph.claims, top_k=top_k)
        matched_claim_ids = [score.claim_id for score in relevant_claims if score.matched]
        contradictions = graph.contradictions_for_claim_ids(matched_claim_ids)
        if not contradictions and "contradiction" in text.lower():
            contradictions = graph.contradictions[: min(3, len(graph.contradictions))]
        candidate_surfaces = _infer_surfaces(artifact)
        recommended_surface = candidate_surfaces[0] if candidate_surfaces else None
        failure_mode = _infer_failure_mode(candidate_surfaces, contradictions, text)

        provenance = list(artifact.provenance)
        provenance.append(f"finding:{artifact.finding_id}")
        provenance.extend(f"claim:{claim_id}" for claim_id in matched_claim_ids)
        provenance.extend(
            contradiction.contradiction_id for contradiction in contradictions
        )

        summary = (
            f"{failure_mode} affecting {recommended_surface or 'unknown surface'}"
            if recommended_surface
            else failure_mode
        )

        return PostmortemDiagnosis(
            finding_id=artifact.finding_id,
            failure_mode=failure_mode,
            summary=summary,
            relevant_claims=relevant_claims,
            contradictions=contradictions,
            candidate_surfaces=candidate_surfaces,
            recommended_surface=recommended_surface,
            provenance=sorted(set(provenance)),
        )
