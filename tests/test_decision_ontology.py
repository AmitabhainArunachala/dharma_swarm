from __future__ import annotations

from dharma_swarm.decision_ontology import (
    ChallengeSeverity,
    DecisionChallenge,
    DecisionClaim,
    DecisionContext,
    DecisionEvidence,
    DecisionLog,
    DecisionMetric,
    DecisionOption,
    DecisionQualityVerdict,
    DecisionRecord,
    DecisionReview,
    DecisionState,
    EvidenceKind,
    ReviewVerdict,
)
from dharma_swarm.decision_router import CollaborationMode, DecisionRouter, RoutePath


def _battle_ready_record() -> DecisionRecord:
    option_hold = DecisionOption(
        option_id="hold",
        title="Keep current worker-slot routing",
        description="Do not introduce typed decision records.",
        selected=False,
    )
    option_upgrade = DecisionOption(
        option_id="upgrade",
        title="Introduce a decision ontology and quality case",
        description="Route high-impact decisions through typed evidence and review objects.",
        selected=True,
        tradeoffs=["More structure up front", "Requires migration of critical flows"],
    )
    return DecisionRecord(
        title="Adopt a typed decision ontology for mission-critical choices",
        statement=(
            "DGC should move high-impact mission choices into a typed ontology "
            "with evidence, challenges, reviews, and measurable outcomes."
        ),
        context=DecisionContext(
            mission="make DGC intellectually sharper and audit-ready",
            owner="codex-primus",
            time_horizon="30 days",
            domains=["orchestration", "quality", "knowledge systems"],
            constraints=["Must stay deterministic for scoring", "Must fit current runtime"],
            assumptions=["Most important decisions can be represented as typed records"],
            risk_score=0.58,
            uncertainty=0.34,
            novelty=0.62,
            urgency=0.72,
            expected_impact=0.88,
            reversible=False,
        ),
        options=[option_hold, option_upgrade],
        claims=[
            DecisionClaim(
                text="Typed decision objects reduce ambiguity across agents.",
                supports_option_id="upgrade",
                evidence_refs=["ev-arch", "ev-palantir"],
                confidence=0.87,
            ),
            DecisionClaim(
                text="A hard-gated quality case is harder to game than prose self-rating.",
                supports_option_id="upgrade",
                evidence_refs=["ev-test", "ev-palantir"],
                confidence=0.84,
            ),
        ],
        evidence=[
            DecisionEvidence(
                evidence_id="ev-arch",
                kind=EvidenceKind.REPO_FACT,
                summary="Current DGC quality scoring is mostly heuristic and text-shaped.",
                source_uri="repo:/Users/dhyana/dharma_swarm/dharma_swarm/evaluator.py",
                confidence=0.94,
                verified=True,
                provenance_refs=["artifact:evaluator.py"],
            ),
            DecisionEvidence(
                evidence_id="ev-test",
                kind=EvidenceKind.TEST,
                summary="Decision ontology scoring is covered with deterministic tests.",
                source_uri="repo:/Users/dhyana/dharma_swarm/tests/test_decision_ontology.py",
                confidence=0.9,
                verified=True,
                provenance_refs=["artifact:test_decision_ontology.py"],
            ),
            DecisionEvidence(
                evidence_id="ev-palantir",
                kind=EvidenceKind.PRIMARY_SOURCE,
                summary=(
                    "Palantir's Ontology combines data, logic, action, and security "
                    "to model decisions rather than just raw data."
                ),
                source_uri="https://www.palantir.com/docs/foundry/architecture-center/ontology-system/",
                confidence=0.92,
                verified=True,
                provenance_refs=["source:palantir-ontology-system"],
            ),
        ],
        challenges=[
            DecisionChallenge(
                summary="Extra structure may slow low-risk tasks.",
                severity=ChallengeSeverity.MEDIUM,
                source_agent="kimi-challenger",
                addressed=True,
                response="Keep reflex actions outside the ontology; require it only for high-impact decisions.",
            ),
            DecisionChallenge(
                summary="Agents may fabricate evidence links unless the traceability layer is enforced.",
                severity=ChallengeSeverity.HIGH,
                source_agent="nim-validator",
                addressed=True,
                response="Hard-fail records whose selected option lacks claim-to-evidence support.",
            ),
        ],
        metrics=[
            DecisionMetric(
                name="decision_reversal_rate",
                baseline="unknown",
                target="< 10% for high-impact missions",
                measurement_plan="Track approved decisions reversed within 14 days.",
                owner="nim-validator",
            ),
            DecisionMetric(
                name="evidence_coverage_ratio",
                baseline="0.0",
                target=">= 0.85",
                measurement_plan="Measure claims with at least one grounded evidence reference.",
                owner="glm-researcher",
            ),
        ],
        reviews=[
            DecisionReview(
                reviewer="codex-primus",
                role="orchestrator",
                verdict=ReviewVerdict.PASS,
                notes="Schema is implementable against the current router and provenance seams.",
            ),
            DecisionReview(
                reviewer="opus-primus",
                role="orchestrator",
                verdict=ReviewVerdict.PASS,
                notes="Quality case is stronger than prose-scoring and preserves counterargument pressure.",
            ),
        ],
        next_actions=[
            "Integrate decision records into mission selection and campaign updates.",
            "Require typed quality cases for high-impact autonomous actions.",
        ],
        kill_criteria=[
            "If completion latency rises >25% without quality gain, narrow the ontology scope.",
        ],
        provenance_refs=["report:palantir-ontology-upgrade", "artifact:decision_ontology.py"],
    )


def test_decision_quality_is_audit_ready_for_well_grounded_record() -> None:
    record = _battle_ready_record()

    assessment = record.evaluate_quality()

    assert assessment.verdict == DecisionQualityVerdict.AUDIT_READY
    assert assessment.overall_score > 0.85
    assert assessment.hard_failures == []


def test_decision_quality_fails_without_evidence_or_counterarguments() -> None:
    record = DecisionRecord(
        title="Make a blind architecture call",
        statement="We should replace the router.",
        context=DecisionContext(
            mission="test",
            owner="operator",
            time_horizon="today",
        ),
        options=[
            DecisionOption(option_id="a", title="Replace", selected=True),
            DecisionOption(option_id="b", title="Keep"),
        ],
        claims=[
            DecisionClaim(
                text="It feels cleaner.",
                supports_option_id="a",
                evidence_refs=[],
            )
        ],
        metrics=[],
        next_actions=[],
    )

    assessment = record.evaluate_quality()

    assert assessment.verdict == DecisionQualityVerdict.FRAGILE
    assert "no_evidence" in assessment.hard_failures
    assert "no_counterarguments" in assessment.hard_failures
    assert "no_metrics" in assessment.hard_failures


def test_decision_quality_fails_when_selected_option_lacks_supported_claim() -> None:
    record = _battle_ready_record()
    record.claims[0].supports_option_id = "hold"
    record.claims[1].supports_option_id = "hold"

    assessment = record.evaluate_quality()

    assert assessment.verdict == DecisionQualityVerdict.FRAGILE
    assert "selected_option_has_no_supported_claim" in assessment.hard_failures


def test_decision_record_bridges_into_router_context() -> None:
    record = _battle_ready_record()
    assessment = record.evaluate_quality()
    router = DecisionRouter()

    decision_input = record.to_decision_input(assessment=assessment)
    route = router.route(decision_input)
    collaboration = router.route_collaboration(decision_input)

    assert decision_input.context["decision_quality_verdict"] == "audit_ready"
    assert route.path == RoutePath.ESCALATE
    assert collaboration.mode == CollaborationMode.MULTI_AGENT


def test_failed_review_prevents_audit_ready_verdict() -> None:
    record = _battle_ready_record()
    record.reviews[1].verdict = ReviewVerdict.FAIL

    assessment = record.evaluate_quality()

    assert assessment.verdict == DecisionQualityVerdict.DEFENSIBLE
    assert "failed_review_present" in assessment.warnings


# ---------------------------------------------------------------------------
# DecisionLog persistence tests
# ---------------------------------------------------------------------------


def _minimal_record() -> DecisionRecord:
    """Create a minimal valid record for log tests."""
    return DecisionRecord(
        title="Test decision",
        statement="Should we add logging?",
        context=DecisionContext(mission="test", owner="operator"),
        options=[
            DecisionOption(option_id="a", title="Yes", selected=True),
            DecisionOption(option_id="b", title="No"),
        ],
    )


def test_decision_log_record_and_list(tmp_path) -> None:
    log = DecisionLog(path=tmp_path / "decisions.jsonl")
    record = _battle_ready_record()

    assessment = log.record(record)

    assert assessment.verdict == DecisionQualityVerdict.AUDIT_READY
    entries = log.list_decisions()
    assert len(entries) == 1
    assert entries[0]["decision"]["title"] == record.title
    assert entries[0]["assessment"]["verdict"] == "audit_ready"


def test_decision_log_multiple_entries(tmp_path) -> None:
    log = DecisionLog(path=tmp_path / "decisions.jsonl")
    for _ in range(5):
        log.record(_minimal_record())

    entries = log.list_decisions(limit=3)
    assert len(entries) == 3


def test_decision_log_empty_file(tmp_path) -> None:
    log = DecisionLog(path=tmp_path / "decisions.jsonl")
    assert log.list_decisions() == []


def test_decision_log_filter_by_verdict(tmp_path) -> None:
    log = DecisionLog(path=tmp_path / "decisions.jsonl")
    # Minimal record → FRAGILE (no evidence, no counterarguments)
    log.record(_minimal_record())
    # Battle-ready → AUDIT_READY
    log.record(_battle_ready_record())

    fragile = log.list_decisions(verdict=DecisionQualityVerdict.FRAGILE)
    audit = log.list_decisions(verdict=DecisionQualityVerdict.AUDIT_READY)

    assert len(fragile) == 1
    assert len(audit) == 1


def test_decision_log_filter_by_state(tmp_path) -> None:
    log = DecisionLog(path=tmp_path / "decisions.jsonl")
    record = _minimal_record()
    record.state = DecisionState.APPROVED
    log.record(record)
    log.record(_minimal_record())  # default = DRAFT

    approved = log.list_decisions(state=DecisionState.APPROVED)
    draft = log.list_decisions(state=DecisionState.DRAFT)

    assert len(approved) == 1
    assert len(draft) == 1


def test_decision_log_creates_parent_dirs(tmp_path) -> None:
    log = DecisionLog(path=tmp_path / "deep" / "nested" / "decisions.jsonl")
    assessment = log.record(_minimal_record())
    assert assessment is not None
    assert (tmp_path / "deep" / "nested" / "decisions.jsonl").exists()
