from dharma_swarm.claim_graph import ClaimGraphBuilder
from dharma_swarm.dharma_corpus import Claim, ClaimCategory, ClaimStatus
from dharma_swarm.postmortem_reader import PostmortemArtifact, PostmortemReader


def _claim(
    claim_id: str,
    statement: str,
    *,
    tags: list[str] | None = None,
) -> Claim:
    return Claim(
        id=claim_id,
        statement=statement,
        category=ClaimCategory.ARCHITECTURAL,
        confidence=0.9,
        enforcement="warn",
        status=ClaimStatus.ACCEPTED,
        tags=tags or [],
    )


def test_reader_infers_surface_and_failure_mode():
    graph = ClaimGraphBuilder().build(
        [
            _claim("DC-2026-0001", "routing conflicts require explicit reroute guard"),
            _claim("DC-2026-0002", "provenance must be attached to governance decisions"),
        ]
    )
    artifact = PostmortemArtifact(
        title="Dispatch routing anomaly",
        summary="A routing conflict caused repeated dispatch misassignment.",
        failure_signature="dispatch route mismatch",
    )
    diagnosis = PostmortemReader().read(artifact, graph)
    assert diagnosis.recommended_surface == "orchestrator"
    assert diagnosis.failure_mode == "routing_conflict"
    assert diagnosis.relevant_claims


def test_reader_surfaces_contradictions():
    graph = ClaimGraphBuilder().build(
        [
            _claim("DC-2026-0001", "prefer reroute", tags=["contradiction:DC-2026-0002"]),
            _claim("DC-2026-0002", "prefer direct dispatch"),
        ]
    )
    artifact = PostmortemArtifact(
        title="Contradictory routing policy",
        summary="Contradiction between routing rules triggered unstable behavior.",
    )
    diagnosis = PostmortemReader().read(artifact, graph)
    assert diagnosis.failure_mode == "contradiction_drift"
    assert diagnosis.contradictions
