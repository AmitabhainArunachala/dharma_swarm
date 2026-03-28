from pydantic import BaseModel

from dharma_swarm.dharma_corpus import Claim, ClaimCategory, ClaimStatus
from dharma_swarm.semantic_governance import ActionEnvelope, SemanticGovernanceKernel


class ClaimWithPredicate(Claim):
    structured_predicate: dict | None = None


def _claim(
    claim_id: str,
    statement: str,
    *,
    enforcement: str = "warn",
    confidence: float = 0.9,
    tags: list[str] | None = None,
    counterarguments: list[str] | None = None,
) -> Claim:
    return Claim(
        id=claim_id,
        statement=statement,
        category=ClaimCategory.ARCHITECTURAL,
        confidence=confidence,
        enforcement=enforcement,
        status=ClaimStatus.ACCEPTED,
        tags=tags or [],
        counterarguments=counterarguments or [],
    )


def test_score_claim_relevance_orders_best_match_first():
    kernel = SemanticGovernanceKernel()
    claims = [
        _claim("DC-2026-0001", "routing conflicts require explicit reroute guard", enforcement="warn"),
        _claim("DC-2026-0002", "delete production database", enforcement="block"),
    ]
    scores = kernel.score_claim_relevance("delete the production database now", claims)
    assert scores[0].claim_id == "DC-2026-0002"
    assert scores[0].matched is True


def test_evaluate_action_blocks_on_strong_block_match():
    kernel = SemanticGovernanceKernel()
    claims = [
        _claim("DC-2026-0001", "delete production database", enforcement="block", confidence=1.0),
    ]
    action = ActionEnvelope(
        actor_id="agent-1",
        actor_type="worker",
        runtime_type="local",
        action_type="shell_command",
        content="delete the production database now",
    )
    verdict = kernel.evaluate_action(action, claims)
    assert verdict.allowed is False
    assert verdict.enforcement_level == "block"
    assert verdict.matched_claim_ids == ["DC-2026-0001"]


def test_evaluate_action_warns_on_warn_match():
    kernel = SemanticGovernanceKernel()
    claims = [
        _claim("DC-2026-0001", "routing conflicts require explicit reroute guard", enforcement="warn"),
    ]
    action = ActionEnvelope(
        actor_id="agent-1",
        actor_type="worker",
        runtime_type="local",
        action_type="dispatch_note",
        content="routing conflict seen in dispatch selection",
    )
    verdict = kernel.evaluate_action(action, claims)
    assert verdict.allowed is True
    assert verdict.enforcement_level == "warn"
    assert verdict.warnings


def test_structured_predicate_can_force_block_even_without_high_text_similarity():
    kernel = SemanticGovernanceKernel()
    claim = ClaimWithPredicate(
        id="DC-2026-0001",
        statement="destructive operations require consent",
        category=ClaimCategory.SAFETY,
        confidence=0.9,
        enforcement="block",
        status=ClaimStatus.ACCEPTED,
        structured_predicate={"field": "destructive_without_consent", "op": "eq", "value": True},
    )
    action = ActionEnvelope(
        actor_id="agent-1",
        actor_type="worker",
        runtime_type="local",
        action_type="tool_call",
        content="run cleanup flow",
        metadata={"destructive_without_consent": True},
    )
    verdict = kernel.evaluate_action(action, [claim])
    assert verdict.allowed is False
    assert verdict.enforcement_level == "block"


def test_resolve_contradictions_uses_declared_tags():
    kernel = SemanticGovernanceKernel()
    claims = [
        _claim("DC-2026-0001", "prefer reroute over direct dispatch", tags=["contradiction:DC-2026-0002"]),
        _claim("DC-2026-0002", "prefer direct dispatch over reroute"),
    ]
    contradictions = kernel.resolve_contradictions(claims)
    assert len(contradictions) == 1
    assert contradictions[0].claim_ids == ["DC-2026-0001", "DC-2026-0002"]
