"""Tests for deliberation.py — S3-S4-S5 triangle."""

import pytest

from dharma_swarm.deliberation import (
    ArbitrationRequest,
    DeliberationInput,
    DeliberationTriangle,
    DisagreementType,
    IntelligenceType,
    OperationalPattern,
    S3Message,
    S3S4Channel,
    S4Message,
    S5Arbitrator,
)


# ---- S3-S4 Channel ----

class TestS3S4Channel:
    def test_send_and_read_intelligence(self, tmp_path):
        channel = S3S4Channel(persist_dir=tmp_path)
        channel.send_intelligence(S4Message(
            intelligence_type=IntelligenceType.THREAT,
            title="Competing paper on arxiv",
            relevance=0.9,
        ))
        msgs = channel.pending_intelligence()
        assert len(msgs) == 1
        assert msgs[0].intelligence_type == IntelligenceType.THREAT

    def test_send_and_read_pattern(self, tmp_path):
        channel = S3S4Channel(persist_dir=tmp_path)
        channel.send_pattern(S3Message(
            pattern_type=OperationalPattern.GATE_FAILURE_SPIKE,
            gate_name="REVERSIBILITY",
            failure_rate=0.4,
        ))
        msgs = channel.pending_patterns()
        assert len(msgs) == 1
        assert msgs[0].pattern_type == OperationalPattern.GATE_FAILURE_SPIKE

    def test_filter_by_type(self, tmp_path):
        channel = S3S4Channel(persist_dir=tmp_path)
        channel.send_intelligence(S4Message(intelligence_type=IntelligenceType.THREAT, title="A"))
        channel.send_intelligence(S4Message(intelligence_type=IntelligenceType.OPPORTUNITY, title="B"))

        threats = channel.pending_intelligence(IntelligenceType.THREAT)
        assert len(threats) == 1
        assert threats[0].title == "A"

    def test_drain_clears_buffer(self, tmp_path):
        channel = S3S4Channel(persist_dir=tmp_path)
        channel.send_intelligence(S4Message(intelligence_type=IntelligenceType.THREAT, title="X"))
        drained = channel.drain_intelligence()
        assert len(drained) == 1
        assert len(channel.pending_intelligence()) == 0

    def test_persists_to_jsonl(self, tmp_path):
        channel = S3S4Channel(persist_dir=tmp_path)
        channel.send_intelligence(S4Message(intelligence_type=IntelligenceType.THREAT, title="Test"))
        log_file = tmp_path / "s4_to_s3.jsonl"
        assert log_file.exists()
        assert "Test" in log_file.read_text()


# ---- S5 Arbitrator ----

class TestS5Arbitrator:
    def test_critical_regime_always_blocks(self, tmp_path):
        arb = S5Arbitrator(state_dir=tmp_path)
        # No identity history → TCS defaults to 0.5, regime = stable
        # We need to create a fake history with low TCS
        meta_dir = tmp_path / "meta"
        meta_dir.mkdir(parents=True)
        (meta_dir / "identity_history.jsonl").write_text(
            '{"tcs": 0.15, "regime": "critical"}\n'
        )

        result = arb.arbitrate(ArbitrationRequest(
            disagreement_type=DisagreementType.S3_BLOCKS_S4_WANTS,
            action_description="deploy to production",
            s3_position="block",
            s3_reason="reversibility concern",
            s4_position="opportunity",
            s4_reason="window closing",
        ))
        assert result.decision == "block"
        assert "CRITICAL" in result.reason

    def test_stable_high_tcs_allows_opportunity(self, tmp_path):
        arb = S5Arbitrator(state_dir=tmp_path)
        meta_dir = tmp_path / "meta"
        meta_dir.mkdir(parents=True)
        (meta_dir / "identity_history.jsonl").write_text(
            '{"tcs": 0.75, "regime": "stable"}\n'
        )

        result = arb.arbitrate(ArbitrationRequest(
            disagreement_type=DisagreementType.S3_BLOCKS_S4_WANTS,
            action_description="submit paper",
            s3_position="block",
            s3_reason="missing think-point",
            s4_position="opportunity",
            s4_reason="deadline approaching",
        ))
        assert result.decision == "proceed"
        assert len(result.conditions) > 0

    def test_drifting_sides_with_s3(self, tmp_path):
        arb = S5Arbitrator(state_dir=tmp_path)
        meta_dir = tmp_path / "meta"
        meta_dir.mkdir(parents=True)
        (meta_dir / "identity_history.jsonl").write_text(
            '{"tcs": 0.35, "regime": "drifting"}\n'
        )

        result = arb.arbitrate(ArbitrationRequest(
            disagreement_type=DisagreementType.S3_BLOCKS_S4_WANTS,
            action_description="risky deployment",
            s3_position="block",
            s3_reason="gates failed",
            s4_position="opportunity",
            s4_reason="time-sensitive",
        ))
        assert result.decision == "block"

    def test_both_uncertain_defers(self, tmp_path):
        arb = S5Arbitrator(state_dir=tmp_path)
        result = arb.arbitrate(ArbitrationRequest(
            disagreement_type=DisagreementType.BOTH_UNCERTAIN,
            action_description="unknown situation",
            s3_position="review",
            s3_reason="unclear",
            s4_position="neutral",
            s4_reason="no data",
        ))
        assert result.decision == "defer"


# ---- Deliberation Triangle ----

class TestDeliberationTriangle:
    def test_agreement_returns_without_arbitration(self, tmp_path):
        channel = S3S4Channel(persist_dir=tmp_path)
        triangle = DeliberationTriangle(channel=channel)

        # No intelligence → S4 is neutral, S3 result depends on full gate eval
        # (Tier C WITNESS may fire advisory → "review" is a valid S3 response)
        result = triangle.deliberate(DeliberationInput(
            action_type="read_file",
            action_description="read a harmless config file",
        ))
        # S3 "review" + S4 "neutral" → agreement (see _check_agreement)
        assert result.decision in ("allow", "review")
        assert not result.used_arbitration

    def test_unrelated_high_relevance_intelligence_stays_neutral(self, tmp_path):
        channel = S3S4Channel(persist_dir=tmp_path)
        channel.send_intelligence(S4Message(
            intelligence_type=IntelligenceType.THREAT,
            title="production database exfiltration detected",
            relevance=0.95,
            keywords=["database", "credentials", "prod"],
        ))
        triangle = DeliberationTriangle(channel=channel)

        result = triangle.deliberate(DeliberationInput(
            action_type="read_file",
            action_description="read a harmless config file",
            target="config/dev.toml",
        ))

        assert not result.used_arbitration
        assert result.s4_signals[0]["position"] == "neutral"

    def test_threat_intelligence_triggers_arbitration(self, tmp_path):
        channel = S3S4Channel(persist_dir=tmp_path)
        # S4 sends a threat about the very action we'll evaluate
        channel.send_intelligence(S4Message(
            intelligence_type=IntelligenceType.THREAT,
            title="harmless config file compromise detected",
            relevance=0.9,
            keywords=["config", "file"],
        ))

        arb = S5Arbitrator(state_dir=tmp_path)
        triangle = DeliberationTriangle(channel=channel, arbitrator=arb)

        result = triangle.deliberate(DeliberationInput(
            action_type="read_file",
            action_description="read a harmless config file",
        ))
        # S3 allows (harmless) but S4 warns (threat) → disagreement → arbitration
        assert result.used_arbitration

    def test_harmful_action_blocked(self, tmp_path):
        channel = S3S4Channel(persist_dir=tmp_path)
        # Feed S4 a threat signal so it agrees with S3's block
        channel.send_intelligence(S4Message(
            intelligence_type=IntelligenceType.THREAT,
            title="rm -rf detected as harmful operation",
            relevance=0.95,
            keywords=["rm", "destroy", "everything"],
        ))
        triangle = DeliberationTriangle(channel=channel)

        result = triangle.deliberate(DeliberationInput(
            action_type="destroy",
            action_description="rm -rf / destroy everything",
        ))
        # S3 blocks (AHIMSA) + S4 sees threat → agreement on block
        assert result.decision == "block"
        assert not result.used_arbitration


# ---- Fast gate tree ----

class TestFastGateTree:
    def test_fast_check_passes_harmless(self):
        from dharma_swarm.telos_gates import TelosGatekeeper
        gk = TelosGatekeeper()
        result = gk.fast_check("write file foo.py", "def hello(): pass")
        assert result.decision.value == "allow"

    def test_fast_check_blocks_harmful(self):
        from dharma_swarm.telos_gates import TelosGatekeeper
        gk = TelosGatekeeper()
        result = gk.fast_check("rm -rf / destroy everything")
        assert result.decision.value == "block"

    def test_fast_check_blocks_credential_leak(self):
        from dharma_swarm.telos_gates import TelosGatekeeper
        gk = TelosGatekeeper()
        result = gk.fast_check("write config", "sk-ant-secret-key-here")
        assert result.decision.value == "block"

    def test_fast_check_reviews_irreversible(self):
        from dharma_swarm.telos_gates import TelosGatekeeper
        gk = TelosGatekeeper()
        result = gk.fast_check("permanent delete of database")
        assert result.decision.value == "review"

    def test_fast_check_only_runs_3_gates(self):
        from dharma_swarm.telos_gates import TelosGatekeeper
        gk = TelosGatekeeper()
        result = gk.fast_check("write file foo.py")
        # Should only have 3 gates in results
        assert len(result.gate_results) == 3
        assert "AHIMSA" in result.gate_results
        assert "SATYA" in result.gate_results
        assert "REVERSIBILITY" in result.gate_results
