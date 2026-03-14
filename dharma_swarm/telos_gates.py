"""Dharmic safety gate system.

Eleven gates from Akram Vignan mapped to computational safety checks.
Ported from dgc-core/hooks/telos_gate.py into a clean class-based API.
Think-point witness logs are written to ~/.dharma/witness/ for audit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from dharma_swarm.anekanta_gate import evaluate_anekanta
from dharma_swarm.models import (
    GateCheckResult,
    GateDecision,
    GateResult,
    GateTier,
)

WITNESS_DIR = Path.home() / ".dharma" / "witness"


@dataclass
class ReflectiveGateOutcome:
    """Result bundle for reflective reroute gate checks."""

    result: GateCheckResult
    attempts: int = 0
    reflection: str = ""
    suggestions: list[str] = field(default_factory=list)


class TelosGatekeeper:
    """Runs 11 dharmic gates against proposed actions.

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
        "ANEKANTA": GateTier.C,
        "DOGMA_DRIFT": GateTier.C,
        "STEELMAN": GateTier.C,
    }

    HARM_WORDS: set[str] = {
        "delete all", "destroy", "rm -rf", "wipe", "kill", "corrupt",
        "exploit", "attack", "exfiltrate", "format disk", "drop table",
        "truncate table", "shutdown -h", "mkfs", "dd if=/dev/zero",
        "chmod 777", ":(){ :|:& };:", "ddos", "denial of service",
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

    DECEPTION_PATTERNS: set[str] = {
        "fake academic citation",
        "fake academic citations",
        "fake citation",
        "fabricate citation",
        "fabricate references",
        "invent citation",
    }

    SENSITIVE_PATH_PATTERNS: set[str] = {
        "/etc/passwd",
        "/etc/shadow",
        ".ssh/id_rsa",
        ".aws/credentials",
    }

    EXFIL_PATTERNS: set[str] = {
        "send it to pastebin",
        "send to pastebin",
        "upload to pastebin",
        "exfiltrate",
        "post publicly",
        "leak",
    }

    # Strict-mode patterns tuned to catch common security bypass intents that
    # may evade narrow AHIMSA keywords in internal YOLO mode.
    STRICT_SECURITY_PATTERNS: set[str] = {
        "bypass authentication",
        "bypass auth",
        "inject sql",
        "sql injection",
        "disable ssl certificate validation",
        "disable tls validation",
        "execute arbitrary code",
        "grant admin privileges",
        "disable rate limiting",
        "expose sensitive credentials",
        "disable encryption",
    }

    THINK_PHASE_HINTS: dict[str, str] = {
        "before_write": "Pause, articulate risks, and confirm rollback path before writing files.",
        "before_git": "Pause, review staged changes, and confirm commit message accuracy.",
        "before_complete": "Pause, verify outputs/tests, and confirm requirement coverage.",
        "before_pivot": "Pause, summarize repeated failures, and choose a different strategy.",
        "when_stuck": "Pause, identify what is blocking you, and consider alternative approaches.",
    }

    # Think phases that BLOCK (not just warn) on insufficient reflection.
    # These are Devin's mandatory-think cases adapted for dharma_swarm.
    MANDATORY_THINK_PHASES: set[str] = {
        "before_write",
        "before_git",
        "before_complete",
        "before_pivot",
    }

    def check(
        self,
        action: str,
        content: str = "",
        tool_name: str = "",
        trust_mode: str | None = None,
        think_phase: str | None = None,
        reflection: str = "",
    ) -> GateCheckResult:
        """Run all 11 gates against an action and optional content.

        Args:
            action: The action description (command, file path, etc.).
            content: Body content being written or edited.
            tool_name: Name of the tool being invoked (informational).
            trust_mode:
                - ``internal_yolo`` (default): permissive for internal speed.
                - ``external_strict``: block high-risk security intents.
            think_phase:
                Optional Devin-style think checkpoint phase. Supported values:
                ``before_write``, ``before_pivot``, ``before_complete``.
            reflection:
                Reflection text for think-point validation.

        Returns:
            GateCheckResult with decision, reason, and per-gate results.
        """
        resolved_mode = (
            (trust_mode or os.getenv("DGC_TRUST_MODE", "internal_yolo"))
            .strip()
            .lower()
        )
        action_lower = action.lower()
        content_lower = content.lower()
        combined = action_lower + " " + content_lower
        results: dict[str, tuple[GateResult, str]] = {}

        # --- AHIMSA (Tier A) — harm + injection detection ---
        harm_hit = next((w for w in self.HARM_WORDS if w in action_lower), None)
        injection_hit = next(
            (p for p in self.INJECTION_PATTERNS if p in combined), None,
        )
        strict_hit = None
        if resolved_mode == "external_strict":
            strict_hit = next(
                (p for p in self.STRICT_SECURITY_PATTERNS if p in combined),
                None,
            )

        if strict_hit:
            results["AHIMSA"] = (
                GateResult.FAIL,
                f"Strict security intent detected: {strict_hit}",
            )
        elif harm_hit:
            results["AHIMSA"] = (GateResult.FAIL, f"Harmful: {harm_hit}")
        elif injection_hit:
            results["AHIMSA"] = (
                GateResult.FAIL, f"Injection detected: {injection_hit}",
            )
        else:
            results["AHIMSA"] = (GateResult.PASS, "")

        # --- SATYA (Tier B) — deception + credential leak prevention ---
        deception_hit = next(
            (p for p in self.DECEPTION_PATTERNS if p in combined), None,
        )
        if deception_hit:
            results["SATYA"] = (
                GateResult.FAIL, f"Deceptive request: {deception_hit}",
            )
        elif content:
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

        # --- CONSENT (Tier B) — block sensitive data exfiltration attempts ---
        sensitive_hit = next(
            (p for p in self.SENSITIVE_PATH_PATTERNS if p in combined), None,
        )
        exfil_hit = next(
            (p for p in self.EXFIL_PATTERNS if p in combined), None,
        )
        if sensitive_hit and exfil_hit:
            results["CONSENT"] = (
                GateResult.FAIL,
                f"Sensitive data exfiltration attempt: {sensitive_hit} -> {exfil_hit}",
            )
        else:
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

        # --- SVABHAAVA (Tier C) — telos alignment via Anekanta ---
        anekanta = evaluate_anekanta(action, content)
        if anekanta.gate_result == GateResult.FAIL:
            results["SVABHAAVA"] = (GateResult.FAIL, f"Low epistemological diversity: {anekanta.reason}")
        elif anekanta.gate_result == GateResult.WARN:
            results["SVABHAAVA"] = (GateResult.WARN, f"Partial diversity: {anekanta.reason}")
        else:
            results["SVABHAAVA"] = (GateResult.PASS, "Epistemological diversity confirmed")

        # --- BHED_GNAN (Tier C) — doer-witness distinction (always passes) ---
        results["BHED_GNAN"] = (GateResult.PASS, "Doer-witness distinction noted")

        # --- WITNESS (Tier C, promoted to blocking for mandatory phases) ---
        phase_key = (think_phase or "").strip().lower()
        if phase_key:
            reflection_text = reflection.strip() or f"{action} {content}".strip()
            if self._is_reflection_sufficient(reflection_text):
                results["WITNESS"] = (
                    GateResult.PASS,
                    f"Think-point satisfied ({phase_key})",
                )
                self._log_witness(phase_key, reflection_text, "PASS", action)
            elif phase_key in self.MANDATORY_THINK_PHASES:
                # Mandatory think phases BLOCK, not just warn
                hint = self.THINK_PHASE_HINTS.get(
                    phase_key,
                    "Pause and reflect before proceeding.",
                )
                results["WITNESS"] = (
                    GateResult.FAIL,
                    f"MANDATORY think-point missing ({phase_key}). "
                    f"{hint} "
                    f"This phase requires deliberate reflection before proceeding.",
                )
                self._log_witness(phase_key, reflection_text, "BLOCKED", action)
            else:
                hint = self.THINK_PHASE_HINTS.get(
                    phase_key,
                    "Pause and reflect before proceeding.",
                )
                results["WITNESS"] = (
                    GateResult.WARN,
                    f"Think-point missing ({phase_key}). {hint}",
                )
                self._log_witness(phase_key, reflection_text, "WARN", action)
        else:
            # Use recursive reading awareness for file operations
            if not hasattr(self, "_witness_gate"):
                from dharma_swarm.telos_gates_witness_enhancement import (
                    WitnessGateEnhancement,
                )
                self._witness_gate = WitnessGateEnhancement()
            results["WITNESS"] = self._witness_gate.evaluate(
                action, content, tool_name,
            )

        # --- ANEKANTA (Tier C) — many-sidedness check ---
        # Reuse the anekanta result computed above for SVABHAAVA
        results["ANEKANTA"] = (anekanta.gate_result, anekanta.reason)

        # --- DOGMA_DRIFT (Tier C) — confidence without evidence check ---
        dogma_result = GateResult.PASS
        dogma_reason = "No dogma drift detected"
        if content:
            from dharma_swarm.dogma_gate import DogmaDriftCheck, check_dogma_drift
            confidence_markers = sum(1 for w in ["certainly", "definitely", "obviously", "clearly", "undoubtedly", "without question", "proven", "unquestionable", "absolute"] if w in content_lower)
            evidence_markers = sum(1 for w in ["data shows", "experiment", "measured", "observed", "tested", "verified", "result:", "p-value", "p=", "evidence", "citation", "reference"] if w in content_lower)
            if confidence_markers > 0:
                drift_check = DogmaDriftCheck(confidence_before=0.5, confidence_after=min(1.0, 0.5 + confidence_markers * 0.15), evidence_count_before=0, evidence_count_after=evidence_markers)
                drift_result = check_dogma_drift(drift_check)
                dogma_result = drift_result.gate_result
                dogma_reason = drift_result.reason
        results["DOGMA_DRIFT"] = (dogma_result, dogma_reason)

        # --- STEELMAN (Tier C) — counterargument requirement ---
        steelman_result = GateResult.PASS
        steelman_reason = "No proposal context for steelman check"
        mutation_context = any(w in action_lower for w in ["mutate", "mutation", "propose", "proposal", "evolve", "change", "modify", "refactor"])
        if mutation_context and content:
            from dharma_swarm.steelman_gate import SteelmanCheck, check_steelman
            counterargs = []
            for marker in ["however", "but ", "alternatively", "risk:", "downside:", "concern:", "counterargument:", "on the other hand"]:
                if marker in content_lower:
                    idx = content_lower.index(marker)
                    start = max(0, idx - 20)
                    end = min(len(content), idx + 100)
                    counterargs.append(content[start:end].strip())
            sm_check = SteelmanCheck(counterarguments=counterargs)
            sm_result = check_steelman(sm_check)
            steelman_result = sm_result.gate_result
            steelman_reason = sm_result.reason
        results["STEELMAN"] = (steelman_result, steelman_reason)

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

        # Mandatory think-phase WITNESS failures are blocking
        witness_result = results.get("WITNESS")
        if (
            witness_result
            and witness_result[0] == GateResult.FAIL
            and (think_phase or "").strip().lower() in self.MANDATORY_THINK_PHASES
        ):
            return GateCheckResult(
                decision=GateDecision.BLOCK,
                reason=f"Mandatory think-point violation: {witness_result[1]}",
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

    @staticmethod
    def _is_reflection_sufficient(reflection: str) -> bool:
        """Reflection heuristic with mimicry detection.

        A reflection passes if it has enough tokens AND isn't flagged
        as performative profundity by the behavioral metrics system.
        This wires the ouroboros mimicry detector into the telos gates —
        performative text can't pass the WITNESS gate.
        """
        tokens = re.findall(r"[a-zA-Z0-9_]+", reflection.lower())
        if len(tokens) < 10:
            return False
        reflection_lower = reflection.lower()
        substantive_markers = ["undo", "revert", "rollback", "restore", "backup", "uncertain", "unknown", "risk", "might fail", "assumption", "could break", "if this fails", "test", "verified", "data", "measured", "result", "evidence", "observed", "confirmed"]
        if not any(marker in reflection_lower for marker in substantive_markers):
            return False
        try:
            from dharma_swarm.metrics import MetricsAnalyzer
            if MetricsAnalyzer().detect_mimicry(reflection):
                return False
        except Exception:
            pass
        return True

    @staticmethod
    def _log_witness(
        phase: str, reflection: str, outcome: str, action: str,
    ) -> None:
        """Write think-point outcome to ~/.dharma/witness/ for audit trail.

        Each entry is a JSON line appended to a daily log file.
        Failures are silently swallowed — witnessing must never block.
        """
        try:
            now = datetime.now(timezone.utc)
            WITNESS_DIR.mkdir(parents=True, exist_ok=True)
            log_file = WITNESS_DIR / f"witness_{now.strftime('%Y%m%d')}.jsonl"
            entry = json.dumps({
                "ts": now.isoformat(),
                "phase": phase,
                "outcome": outcome,
                "action": action[:200],
                "reflection": reflection[:500],
            })
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
        except Exception:
            pass  # Witnessing must never block


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


def check_with_reflective_reroute(
    *,
    action: str,
    content: str = "",
    tool_name: str = "",
    trust_mode: str | None = None,
    think_phase: str | None = None,
    reflection: str = "",
    max_reroutes: int = 2,
    spec_ref: str | None = None,
    requirement_refs: list[str] | None = None,
) -> ReflectiveGateOutcome:
    """Run gate checks with bounded witness recovery for mandatory phases.

    This preserves hard safety blocks (AHIMSA/SATYA/CONSENT), while converting
    mandatory think-point witness blocks into a structured reflective reroute.
    """
    attempts = 0
    max_attempts = max(0, int(max_reroutes))
    phase_key = (think_phase or "").strip().lower()
    req_refs = requirement_refs or []
    suggestions: list[str] = []
    current_reflection = (reflection or "").strip()

    while True:
        result = DEFAULT_GATEKEEPER.check(
            action=action,
            content=content,
            tool_name=tool_name,
            trust_mode=trust_mode,
            think_phase=think_phase,
            reflection=current_reflection,
        )

        witness_result = result.gate_results.get("WITNESS")
        mandatory_witness_block = (
            result.decision == GateDecision.BLOCK
            and witness_result is not None
            and witness_result[0] == GateResult.FAIL
            and phase_key in TelosGatekeeper.MANDATORY_THINK_PHASES
        )
        if not mandatory_witness_block:
            return ReflectiveGateOutcome(
                result=result,
                attempts=attempts,
                reflection=current_reflection,
                suggestions=suggestions,
            )

        if attempts >= max_attempts:
            return ReflectiveGateOutcome(
                result=result,
                attempts=attempts,
                reflection=current_reflection,
                suggestions=suggestions,
            )

        attempts += 1
        suggestions = _reflective_lenses(spec_ref=spec_ref, requirement_refs=req_refs)
        scaffold = _build_reflection_scaffold(
            attempt=attempts,
            max_attempts=max_attempts,
            reason=result.reason,
            phase=phase_key or "unknown",
            action=action,
            spec_ref=spec_ref,
            requirement_refs=req_refs,
        )
        current_reflection = (
            f"{current_reflection}\n\n{scaffold}".strip()
            if current_reflection
            else scaffold
        )


def _reflective_lenses(
    *,
    spec_ref: str | None = None,
    requirement_refs: list[str] | None = None,
) -> list[str]:
    requirements = ", ".join(requirement_refs or []) or "none"
    trace = spec_ref or "unlinked"
    return [
        (
            "Risk lens: What could break, who/what could be harmed, and what "
            "smallest reversible step reduces blast radius?"
        ),
        (
            "Counterfactual lens: If this fails, what early signal will detect "
            "it and what rollback is immediate?"
        ),
        (
            "Plurality lens: What are two alternative strategies and why is this "
            "one preferred now?"
        ),
        (
            "Evidence lens: Which concrete spec/requirement does this satisfy "
            f"(spec={trace}, reqs={requirements})?"
        ),
        (
            "Integrity lens: Which assumption is uncertain and how will it be "
            "validated before completion?"
        ),
    ]


def _build_reflection_scaffold(
    *,
    attempt: int,
    max_attempts: int,
    reason: str,
    phase: str,
    action: str,
    spec_ref: str | None = None,
    requirement_refs: list[str] | None = None,
) -> str:
    requirements = ", ".join(requirement_refs or []) or "none"
    trace = spec_ref or "unlinked"
    return (
        f"Reflective reroute attempt {attempt}/{max_attempts}. "
        f"Phase: {phase}. Trigger: {reason}\n"
        f"Action intent: {action}\n"
        f"Spec trace: {trace}\n"
        f"Requirement refs: {requirements}\n"
        "RISK: Bound to smallest reversible step.\n"
        "ROLLBACK: State exact undo path before continuing.\n"
        "ALTERNATIVES: Name two alternatives and why deferred.\n"
        "EVIDENCE: Define pass/fail signal for this step.\n"
        "UNCERTAINTY: Name one unknown + check."
    )
