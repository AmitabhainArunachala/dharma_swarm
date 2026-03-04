"""Dharmic safety gate system.

Eight gates from Akram Vignan mapped to computational safety checks.
Ported from dgc-core/hooks/telos_gate.py into a clean class-based API.
No hook/stdin interface, no witness file logging — those concerns
live elsewhere (CLI and memory.py respectively).
"""

from __future__ import annotations

from dharma_swarm.models import (
    GateCheckResult,
    GateDecision,
    GateResult,
    GateTier,
)


class TelosGatekeeper:
    """Runs 8 dharmic gates against proposed actions.

    Tier A failures block unconditionally.
    Tier B failures block unconditionally.
    Tier C failures produce a review advisory (not a block).
    """

    GATES: dict[str, GateTier] = {
        "AHIMSA": GateTier.A,
        "SATYA": GateTier.B,
        "CONSENT": GateTier.B,
        "VYAVASTHIT": GateTier.C,
        "REVERSIBILITY": GateTier.C,
        "SVABHAAVA": GateTier.C,
        "BHED_GNAN": GateTier.C,
        "WITNESS": GateTier.C,
    }

    HARM_WORDS: set[str] = {
        "delete all", "destroy", "rm -rf", "wipe", "kill", "corrupt",
        "exploit", "attack", "exfiltrate", "format disk", "drop table",
        "truncate table", "shutdown -h", "mkfs", "dd if=/dev/zero",
        "chmod 777", ":(){ :|:& };:",
    }

    FORCE_WORDS: set[str] = {
        "force", "override", "bypass", "skip validation",
        "disable safety", "--no-verify",
    }

    IRREVERSIBLE_WORDS: set[str] = {
        "permanent", "irreversible", "cannot undo",
        "no backup", "force push",
    }

    INJECTION_PATTERNS: set[str] = {
        "ignore previous instructions", "ignore all previous",
        "disregard your instructions", "new instructions:",
        "you are now", "act as if you", "pretend you are",
        "override your", "forget your rules",
    }

    CREDENTIAL_PATTERNS: set[str] = {
        "sk-or-v1-", "sk-ant-", "sk-proj-", "AKIA", "ghp_", "gho_",
        "xoxb-", "xoxp-", "Bearer ", "-----BEGIN PRIVATE KEY",
        "-----BEGIN RSA PRIVATE", "password=", "secret=",
    }

    def check(
        self,
        action: str,
        content: str = "",
        tool_name: str = "",
    ) -> GateCheckResult:
        """Run all 8 gates against an action and optional content.

        Args:
            action: The action description (command, file path, etc.).
            content: Body content being written or edited.
            tool_name: Name of the tool being invoked (informational).

        Returns:
            GateCheckResult with decision, reason, and per-gate results.
        """
        action_lower = action.lower()
        content_lower = content.lower()
        combined = action_lower + " " + content_lower
        results: dict[str, tuple[GateResult, str]] = {}

        # --- AHIMSA (Tier A) — harm + injection detection ---
        harm_hit = next((w for w in self.HARM_WORDS if w in action_lower), None)
        injection_hit = next(
            (p for p in self.INJECTION_PATTERNS if p in combined), None,
        )
        if harm_hit:
            results["AHIMSA"] = (GateResult.FAIL, f"Harmful: {harm_hit}")
        elif injection_hit:
            results["AHIMSA"] = (
                GateResult.FAIL, f"Injection detected: {injection_hit}",
            )
        else:
            results["AHIMSA"] = (GateResult.PASS, "")

        # --- SATYA (Tier B) — credential leak prevention ---
        if content:
            cred_hit = next(
                (p for p in self.CREDENTIAL_PATTERNS if p in content), None,
            )
            if cred_hit:
                results["SATYA"] = (
                    GateResult.FAIL, f"Credential in content: {cred_hit[:10]}...",
                )
            else:
                results["SATYA"] = (GateResult.PASS, "")
        else:
            results["SATYA"] = (GateResult.PASS, "")

        # --- CONSENT (Tier B) — pass-through (permission handled externally) ---
        results["CONSENT"] = (GateResult.PASS, "Permission system active")

        # --- VYAVASTHIT (Tier C) — force detection ---
        force_hit = next(
            (w for w in self.FORCE_WORDS if w in action_lower), None,
        )
        if force_hit:
            results["VYAVASTHIT"] = (GateResult.FAIL, f"Forcing: {force_hit}")
        else:
            results["VYAVASTHIT"] = (GateResult.PASS, "")

        # --- REVERSIBILITY (Tier C) — irreversible operation warning ---
        irrev_hit = next(
            (w for w in self.IRREVERSIBLE_WORDS if w in action_lower), None,
        )
        if irrev_hit:
            results["REVERSIBILITY"] = (
                GateResult.WARN, f"Irreversible: {irrev_hit}",
            )
        else:
            results["REVERSIBILITY"] = (GateResult.PASS, "")

        # --- SVABHAAVA (Tier C) — telos alignment (always passes) ---
        results["SVABHAAVA"] = (GateResult.PASS, "")

        # --- BHED_GNAN (Tier C) — doer-witness distinction (always passes) ---
        results["BHED_GNAN"] = (GateResult.PASS, "Doer-witness distinction noted")

        # --- WITNESS (Tier C) — the check itself IS witnessing ---
        results["WITNESS"] = (GateResult.PASS, "Witnessed")

        # --- Evaluate decision ---
        tier_a_fail = any(
            results[g][0] == GateResult.FAIL
            for g in self.GATES
            if self.GATES[g] == GateTier.A
        )
        tier_b_fail = any(
            results[g][0] == GateResult.FAIL
            for g in self.GATES
            if self.GATES[g] == GateTier.B
        )

        if tier_a_fail:
            reason = next(
                results[g][1]
                for g in self.GATES
                if self.GATES[g] == GateTier.A and results[g][0] == GateResult.FAIL
            )
            return GateCheckResult(
                decision=GateDecision.BLOCK,
                reason=f"AHIMSA violation: {reason}",
                gate_results=results,
            )

        if tier_b_fail:
            reasons = [
                results[g][1]
                for g in self.GATES
                if self.GATES[g] == GateTier.B and results[g][0] == GateResult.FAIL
            ]
            return GateCheckResult(
                decision=GateDecision.BLOCK,
                reason=f"Tier B violation: {'; '.join(reasons)}",
                gate_results=results,
            )

        # Tier C failures produce review, not block
        tier_c_fail = any(
            results[g][0] in (GateResult.FAIL, GateResult.WARN)
            for g in self.GATES
            if self.GATES[g] == GateTier.C
        )
        if tier_c_fail:
            reasons = [
                results[g][1]
                for g in self.GATES
                if self.GATES[g] == GateTier.C
                and results[g][0] in (GateResult.FAIL, GateResult.WARN)
            ]
            return GateCheckResult(
                decision=GateDecision.REVIEW,
                reason=f"Advisory: {'; '.join(reasons)}",
                gate_results=results,
            )

        return GateCheckResult(
            decision=GateDecision.ALLOW,
            reason="All gates passed",
            gate_results=results,
        )


DEFAULT_GATEKEEPER = TelosGatekeeper()


def check_action(action: str, content: str = "") -> GateCheckResult:
    """Module-level shortcut using the default gatekeeper.

    Args:
        action: The action description to evaluate.
        content: Optional body content being written.

    Returns:
        GateCheckResult with decision and per-gate details.
    """
    return DEFAULT_GATEKEEPER.check(action=action, content=content)
