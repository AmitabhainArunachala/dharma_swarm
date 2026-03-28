from dharma_swarm.claim_graph import ClaimGraphBuilder
from dharma_swarm.dharma_corpus import Claim, ClaimCategory, ClaimStatus, EvidenceLink


def _claim(
    claim_id: str,
    statement: str,
    *,
    tags: list[str] | None = None,
    counterarguments: list[str] | None = None,
    confidence: float = 0.8,
) -> Claim:
    return Claim(
        id=claim_id,
        statement=statement,
        category=ClaimCategory.ARCHITECTURAL,
        confidence=confidence,
        enforcement="warn",
        status=ClaimStatus.ACCEPTED,
        tags=tags or [],
        counterarguments=counterarguments or [],
        evidence_links=[
            EvidenceLink(
                type="research",
                url_or_ref=f"docs/{claim_id}.md",
                description=f"Evidence for {claim_id}",
            )
        ],
    )


def test_build_materializes_citations_and_declared_contradictions():
    graph = ClaimGraphBuilder().build(
        [
            _claim("DC-2026-0001", "claim one", tags=["contradiction:DC-2026-0002"]),
            _claim("DC-2026-0002", "claim two"),
        ]
    )
    assert len(graph.claims) == 2
    assert len(graph.citation_edges) == 2
    assert len(graph.contradictions) == 1


def test_query_helpers_filter_claims():
    graph = ClaimGraphBuilder().build(
        [
            _claim("DC-2026-0001", "claim one", tags=["routing"], confidence=0.95),
            _claim("DC-2026-0002", "claim two", tags=["safety"], confidence=0.50),
        ]
    )
    assert [claim.id for claim in graph.by_tag("routing")] == ["DC-2026-0001"]
    assert [claim.id for claim in graph.by_confidence(0.9)] == ["DC-2026-0001"]
    assert [claim.id for claim in graph.by_provenance("DC-2026-0002")] == ["DC-2026-0002"]


def test_contradictions_for_claim_ids_returns_only_intersecting_items():
    graph = ClaimGraphBuilder().build(
        [
            _claim("DC-2026-0001", "claim one", tags=["contradiction:DC-2026-0002"]),
            _claim("DC-2026-0002", "claim two"),
            _claim("DC-2026-0003", "claim three"),
        ]
    )
    contradictions = graph.contradictions_for_claim_ids(["DC-2026-0001"])
    assert len(contradictions) == 1
    assert contradictions[0].claim_ids == ["DC-2026-0001", "DC-2026-0002"]
