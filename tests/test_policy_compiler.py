"""Tests for dharma_swarm.policy_compiler -- PolicyCompiler + Policy + rules."""

import pytest
from pydantic import BaseModel

from dharma_swarm.policy_compiler import (
    Policy,
    PolicyCompiler,
    PolicyDecision,
    PolicyRule,
)


# ---------------------------------------------------------------------------
# Mock domain objects (stand-ins for dharma_kernel / dharma_corpus models)
# ---------------------------------------------------------------------------


class MockPrinciple(BaseModel):
    name: str
    description: str
    formal_constraint: str
    severity: str  # "critical" | "high" | "medium"


class MockClaim(BaseModel):
    id: str = "DC-2026-0001"
    statement: str = "test"
    confidence: float = 0.8
    enforcement: str = "warn"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_principles(n: int = 10) -> dict[str, MockPrinciple]:
    """Build *n* mock kernel principles with rotating severity."""
    severities = ["critical", "high", "medium"]
    return {
        f"PRINCIPLE_{i}": MockPrinciple(
            name=f"PRINCIPLE_{i}",
            description=f"Principle number {i}",
            formal_constraint=f"constraint_{i}",
            severity=severities[i % 3],
        )
        for i in range(n)
    }


def _make_claims(n: int = 2) -> list[MockClaim]:
    """Build *n* mock corpus claims."""
    return [
        MockClaim(
            id=f"DC-2026-{i:04d}",
            statement=f"claim_{i}",
            confidence=0.5 + 0.1 * i,
            enforcement="warn" if i % 2 == 0 else "block",
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Compile tests
# ---------------------------------------------------------------------------


def test_compile_empty():
    compiler = PolicyCompiler()
    policy = compiler.compile({}, [])
    assert policy.rules == []
    assert policy.context == ""
    assert policy.compiled_at  # non-empty ISO string


def test_compile_kernel_only():
    compiler = PolicyCompiler()
    principles = _make_principles(10)
    policy = compiler.compile(principles, [])
    assert len(policy.rules) == 10
    assert all(r.is_immutable for r in policy.rules)


def test_compile_claims_only():
    compiler = PolicyCompiler()
    claims = _make_claims(2)
    policy = compiler.compile({}, claims)
    assert len(policy.rules) == 2
    assert all(not r.is_immutable for r in policy.rules)


def test_compile_mixed():
    compiler = PolicyCompiler()
    principles = _make_principles(3)
    claims = _make_claims(2)
    policy = compiler.compile(principles, claims, context="mixed test")
    assert len(policy.rules) == 5
    assert policy.context == "mixed test"
    immutable = [r for r in policy.rules if r.is_immutable]
    mutable = [r for r in policy.rules if not r.is_immutable]
    assert len(immutable) == 3
    assert len(mutable) == 2


def test_immutable_rules_from_kernel():
    compiler = PolicyCompiler()
    principles = _make_principles(4)
    policy = compiler.compile(principles, [])
    immutable = policy.get_immutable_rules()
    assert len(immutable) == 4
    assert all(r.weight == 1.0 for r in immutable)
    assert all(r.source.startswith("kernel:") for r in immutable)


def test_mutable_rules_from_claims():
    compiler = PolicyCompiler()
    claims = _make_claims(3)
    policy = compiler.compile({}, claims)
    mutable = policy.get_mutable_rules()
    assert len(mutable) == 3
    assert all(r.source.startswith("corpus:") for r in mutable)
    # Confidence mapped to weight
    for rule, claim in zip(mutable, sorted(claims, key=lambda c: c.confidence, reverse=True)):
        assert rule.weight == claim.confidence


def test_rule_ordering():
    compiler = PolicyCompiler()
    principles = _make_principles(3)
    claims = _make_claims(2)
    policy = compiler.compile(principles, claims)
    # All immutable rules must come before any mutable rule
    seen_mutable = False
    for rule in policy.rules:
        if not rule.is_immutable:
            seen_mutable = True
        if rule.is_immutable and seen_mutable:
            pytest.fail("Immutable rule found after mutable rule")


# ---------------------------------------------------------------------------
# Action checking tests
# ---------------------------------------------------------------------------


def test_check_action_allowed():
    policy = Policy(rules=[
        PolicyRule(
            source="kernel:AHIMSA",
            rule_text="delete production database",
            weight=1.0,
            is_immutable=True,
            enforcement_level="block",
        ),
    ])
    decision = policy.check_action("read the logs")
    assert decision.allowed is True
    assert decision.violated_rules == []
    assert decision.reason == ""


def test_check_action_blocked_immutable():
    policy = Policy(rules=[
        PolicyRule(
            source="kernel:AHIMSA",
            rule_text="delete production database",
            weight=1.0,
            is_immutable=True,
            enforcement_level="block",
        ),
    ])
    decision = policy.check_action("delete the production database now")
    assert decision.allowed is False
    assert len(decision.violated_rules) == 1
    assert "immutable block" in decision.reason


def test_check_action_blocked_mutable_high_weight():
    policy = Policy(rules=[
        PolicyRule(
            source="corpus:DC-2026-0001",
            rule_text="bypass safety checks",
            weight=0.9,
            is_immutable=False,
            enforcement_level="block",
        ),
    ])
    decision = policy.check_action("bypass all safety checks immediately")
    assert decision.allowed is False
    assert len(decision.violated_rules) == 1
    assert "mutable block" in decision.reason


def test_check_action_allowed_mutable_low_weight():
    policy = Policy(rules=[
        PolicyRule(
            source="corpus:DC-2026-0002",
            rule_text="bypass safety checks",
            weight=0.5,
            is_immutable=False,
            enforcement_level="block",
        ),
    ])
    # Weight 0.5 <= 0.7 threshold, so even a matching block rule won't block
    decision = policy.check_action("bypass all safety checks")
    assert decision.allowed is True
    # The rule IS violated (keywords match), just not blocking
    assert len(decision.violated_rules) == 1


def test_policy_decision_contains_violated_rules():
    rules = [
        PolicyRule(
            source="kernel:SATYA",
            rule_text="fabricate evidence",
            weight=1.0,
            is_immutable=True,
            enforcement_level="block",
        ),
        PolicyRule(
            source="corpus:DC-2026-0003",
            rule_text="fabricate data",
            weight=0.6,
            is_immutable=False,
            enforcement_level="warn",
        ),
    ]
    policy = Policy(rules=rules)
    decision = policy.check_action("fabricate evidence and data")
    # Both rules should match
    assert len(decision.violated_rules) == 2
    sources = {r.source for r in decision.violated_rules}
    assert "kernel:SATYA" in sources
    assert "corpus:DC-2026-0003" in sources
    # Only the immutable block actually blocks
    assert decision.allowed is False
