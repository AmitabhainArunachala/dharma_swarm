"""Tests for Adaptive Autonomy system."""

from __future__ import annotations

import pytest

from dharma_swarm.adaptive_autonomy import (
    AdaptiveAutonomy,
    AutonomyDecision,
    RiskLevel,
)


class TestRiskClassification:
    """Tests for action risk classification."""

    def test_safe_actions(self):
        auto = AdaptiveAutonomy()
        assert auto.classify_risk("read the config file") == RiskLevel.SAFE
        assert auto.classify_risk("list all modules") == RiskLevel.SAFE
        assert auto.classify_risk("search for function") == RiskLevel.SAFE
        assert auto.classify_risk("show status") == RiskLevel.SAFE

    def test_low_risk_actions(self):
        auto = AdaptiveAutonomy()
        assert auto.classify_risk("write note to shared") == RiskLevel.LOW
        assert auto.classify_risk("git status") == RiskLevel.LOW
        assert auto.classify_risk("create test file") == RiskLevel.LOW

    def test_medium_risk_actions(self):
        auto = AdaptiveAutonomy()
        assert auto.classify_risk("edit the config module") == RiskLevel.MEDIUM
        assert auto.classify_risk("modify the test file") == RiskLevel.MEDIUM
        assert auto.classify_risk("refactor the class") == RiskLevel.MEDIUM

    def test_high_risk_actions(self):
        auto = AdaptiveAutonomy()
        assert auto.classify_risk("deploy to staging") == RiskLevel.HIGH
        assert auto.classify_risk("git push the changes") == RiskLevel.HIGH
        assert auto.classify_risk("create pr for review") == RiskLevel.HIGH

    def test_critical_actions(self):
        auto = AdaptiveAutonomy()
        assert auto.classify_risk("delete all files") == RiskLevel.CRITICAL
        assert auto.classify_risk("rm -rf everything") == RiskLevel.CRITICAL
        assert auto.classify_risk("reset --hard") == RiskLevel.CRITICAL
        assert auto.classify_risk("expose api key") == RiskLevel.CRITICAL

    def test_unknown_defaults_to_medium(self):
        auto = AdaptiveAutonomy()
        assert auto.classify_risk("do something weird") == RiskLevel.MEDIUM


class TestAutonomyDecisions:
    """Tests for the autonomy decision matrix."""

    def test_locked_never_approves(self):
        auto = AdaptiveAutonomy(base_level="locked")
        decision = auto.should_auto_approve("read a file", RiskLevel.SAFE)
        assert decision.auto_approve is False

    def test_cautious_only_safe(self):
        auto = AdaptiveAutonomy(base_level="cautious")
        safe = auto.should_auto_approve("read file", RiskLevel.SAFE)
        low = auto.should_auto_approve("write note", RiskLevel.LOW)
        assert safe.auto_approve is True
        assert low.auto_approve is False

    def test_balanced_safe_and_low(self):
        auto = AdaptiveAutonomy(base_level="balanced")
        safe = auto.should_auto_approve("read", RiskLevel.SAFE)
        low = auto.should_auto_approve("log", RiskLevel.LOW)
        medium = auto.should_auto_approve("edit", RiskLevel.MEDIUM, confidence=0.5)
        assert safe.auto_approve is True
        assert low.auto_approve is True
        assert medium.auto_approve is False

    def test_balanced_high_confidence_medium(self):
        auto = AdaptiveAutonomy(base_level="balanced")
        decision = auto.should_auto_approve(
            "edit config", RiskLevel.MEDIUM, confidence=0.9
        )
        assert decision.auto_approve is True

    def test_aggressive_approves_most(self):
        # quiet_hours=set() avoids time-dependent downgrade during 2-4 AM
        auto = AdaptiveAutonomy(base_level="aggressive", quiet_hours=set())
        medium = auto.should_auto_approve("edit", RiskLevel.MEDIUM)
        high = auto.should_auto_approve("deploy", RiskLevel.HIGH, confidence=0.8)
        assert medium.auto_approve is True
        assert high.auto_approve is True

    def test_full_approves_everything_except_critical(self):
        auto = AdaptiveAutonomy(base_level="full", quiet_hours=set())
        high = auto.should_auto_approve("deploy", RiskLevel.HIGH)
        critical = auto.should_auto_approve("delete all", RiskLevel.CRITICAL)
        assert high.auto_approve is True
        assert critical.auto_approve is False

    def test_critical_never_auto_approved(self):
        for level in ["locked", "cautious", "balanced", "aggressive", "full"]:
            auto = AdaptiveAutonomy(base_level=level)
            decision = auto.should_auto_approve("delete", RiskLevel.CRITICAL)
            assert decision.auto_approve is False, f"level={level} approved critical"

    def test_escalation_for_critical(self):
        auto = AdaptiveAutonomy(base_level="balanced")
        decision = auto.should_auto_approve("delete all", RiskLevel.CRITICAL)
        assert decision.escalate_to == "human"


class TestAdaptiveHistory:
    """Tests for history-based autonomy adjustment."""

    def test_success_rate_starts_at_one(self):
        auto = AdaptiveAutonomy()
        assert auto.success_rate == 1.0

    def test_success_rate_tracks_outcomes(self):
        auto = AdaptiveAutonomy()
        auto.record_outcome(True)
        auto.record_outcome(True)
        auto.record_outcome(False)
        assert abs(auto.success_rate - 2 / 3) < 0.01

    def test_consecutive_failures_degrade(self):
        auto = AdaptiveAutonomy(base_level="aggressive", quiet_hours=set())
        assert auto.effective_level == "aggressive"
        auto.record_outcome(False)
        auto.record_outcome(False)
        auto.record_outcome(False)
        assert auto.effective_level == "locked"

    def test_success_resets_streak(self):
        auto = AdaptiveAutonomy(base_level="balanced")
        auto.record_outcome(False)
        auto.record_outcome(False)
        auto.record_outcome(True)  # breaks the streak
        auto.record_outcome(False)
        assert auto._consecutive_failures == 1  # reset after success

    def test_low_success_rate_downgrades(self):
        auto = AdaptiveAutonomy(base_level="aggressive")
        # Create low success rate
        for _ in range(3):
            auto.record_outcome(True)
        for _ in range(7):
            auto.record_outcome(False)
        # 30% success rate → should downgrade
        assert auto.effective_level in ("cautious", "locked")

    def test_reset_clears_history(self):
        auto = AdaptiveAutonomy()
        auto.record_outcome(False)
        auto.record_outcome(False)
        auto.reset()
        assert auto.success_rate == 1.0
        assert auto._consecutive_failures == 0

    def test_stats(self):
        auto = AdaptiveAutonomy(base_level="balanced")
        auto.record_outcome(True)
        stats = auto.stats()
        assert stats["base_level"] == "balanced"
        assert stats["effective_level"] == "balanced"
        assert stats["success_rate"] == 1.0
        assert stats["history_size"] == 1
