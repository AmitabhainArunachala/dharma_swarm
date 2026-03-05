"""Policy compiler for DHARMA SWARM.

Compiles kernel principles and accepted claims into a unified Policy
that can evaluate actions against dharmic constraints. Immutable rules
(from the kernel) always override mutable rules (from the corpus).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from dharma_swarm.models import _utc_now


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

EnforcementLevel = Literal["block", "warn", "log", "gate_human"]

_SEVERITY_TO_ENFORCEMENT: dict[str, EnforcementLevel] = {
    "critical": "block",
    "high": "warn",
    "medium": "log",
}


class PolicyRule(BaseModel):
    """A single rule inside a compiled policy."""

    source: str
    rule_text: str
    weight: float = Field(ge=0.0, le=1.0)
    is_immutable: bool
    enforcement_level: EnforcementLevel


class PolicyDecision(BaseModel):
    """Result of checking an action against a policy."""

    allowed: bool
    violated_rules: list[PolicyRule] = Field(default_factory=list)
    reason: str = ""


class Policy(BaseModel):
    """A compiled set of rules ready for action evaluation."""

    rules: list[PolicyRule] = Field(default_factory=list)
    context: str = ""
    compiled_at: str = Field(default_factory=lambda: _utc_now().isoformat())

    def get_immutable_rules(self) -> list[PolicyRule]:
        """Return all immutable (kernel-derived) rules."""
        return [r for r in self.rules if r.is_immutable]

    def get_mutable_rules(self) -> list[PolicyRule]:
        """Return all mutable (corpus-derived) rules."""
        return [r for r in self.rules if not r.is_immutable]

    def check_action(self, action: str, context: str = "") -> PolicyDecision:
        """Evaluate an action string against all policy rules.

        Matching is keyword-based: every word in the rule_text is checked
        against the combined action+context string (case-insensitive).
        A rule is considered matched if *all* its keywords appear.

        Blocking logic:
        - Immutable rule with enforcement_level="block" -> not allowed.
        - Mutable rule with enforcement_level="block" and weight > 0.7 -> not allowed.
        """
        combined = (action + " " + context).lower()
        violated: list[PolicyRule] = []

        for rule in self.rules:
            keywords = rule.rule_text.lower().split()
            if all(kw in combined for kw in keywords):
                violated.append(rule)

        blocked = False
        reasons: list[str] = []

        for rule in violated:
            if rule.enforcement_level == "block":
                if rule.is_immutable:
                    blocked = True
                    reasons.append(
                        f"immutable block: {rule.source}"
                    )
                elif rule.weight > 0.7:
                    blocked = True
                    reasons.append(
                        f"mutable block (weight={rule.weight}): {rule.source}"
                    )

        return PolicyDecision(
            allowed=not blocked,
            violated_rules=violated,
            reason="; ".join(reasons) if reasons else "",
        )


# ---------------------------------------------------------------------------
# Compiler
# ---------------------------------------------------------------------------


class PolicyCompiler:
    """Stateless compiler that fuses kernel principles and corpus claims."""

    def compile(
        self,
        kernel_principles: dict[str, Any],
        accepted_claims: list[Any],
        context: str = "",
    ) -> Policy:
        """Compile kernel principles and accepted claims into a Policy.

        Args:
            kernel_principles: Mapping of name -> principle object. Each
                principle must expose ``name``, ``description``,
                ``formal_constraint``, and ``severity`` attributes.
            accepted_claims: List of claim objects. Each must expose
                ``id``, ``statement``, ``confidence``, and ``enforcement``
                attributes.
            context: Free-text description of what this policy is for.

        Returns:
            A Policy with immutable rules (from kernel) sorted before
            mutable rules (from claims), ordered by weight descending
            within each group.
        """
        immutable_rules: list[PolicyRule] = []
        mutable_rules: list[PolicyRule] = []

        for name, principle in kernel_principles.items():
            severity: str = getattr(principle, "severity", "medium")
            enforcement = _SEVERITY_TO_ENFORCEMENT.get(severity, "log")
            rule = PolicyRule(
                source=f"kernel:{name}",
                rule_text=getattr(principle, "formal_constraint", ""),
                weight=1.0,
                is_immutable=True,
                enforcement_level=enforcement,
            )
            immutable_rules.append(rule)

        for claim in accepted_claims:
            rule = PolicyRule(
                source=f"corpus:{getattr(claim, 'id', 'unknown')}",
                rule_text=getattr(claim, "statement", ""),
                weight=float(getattr(claim, "confidence", 0.5)),
                is_immutable=False,
                enforcement_level=getattr(claim, "enforcement", "log"),
            )
            mutable_rules.append(rule)

        # Sort: immutable first, then mutable — each group by weight desc.
        immutable_rules.sort(key=lambda r: r.weight, reverse=True)
        mutable_rules.sort(key=lambda r: r.weight, reverse=True)

        return Policy(
            rules=immutable_rules + mutable_rules,
            context=context,
        )
