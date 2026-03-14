"""Common phase functions shared across cascade domains.

These are the default gate and eigenform functions referenced by LoopDomain configs.
All functions are deterministic stubs — real LLM wiring is a follow-up task.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def telos_gate(artifact: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Gate function — checks artifact against telos constraints via TelosGatekeeper.

    Runs all 11 dharmic gates (AHIMSA, SATYA, CONSENT, etc.) against the
    artifact content.  Falls back to a basic content-length check if
    TelosGatekeeper is unavailable or raises.
    """
    try:
        from dharma_swarm.telos_gates import TelosGatekeeper

        gk = TelosGatekeeper()
        content = artifact.get("content", "")
        action = context.get("action", context.get("tool", "cascade_domain"))
        # Truncate content for efficiency — gates do keyword scanning, not deep reading
        content_str = content[:2000] if isinstance(content, str) else ""

        result = gk.check(
            action=action,
            content=content_str,
            tool_name=context.get("tool", "cascade_domain"),
        )

        # GateDecision is a str enum ("allow", "block", "review")
        decision_val = result.decision.value if hasattr(result.decision, "value") else str(result.decision)
        passed = decision_val in ("allow", "review")

        # Build per-gate score map from gate_results: dict[str, tuple[GateResult, str]]
        gate_scores: dict[str, float] = {}
        for gate_name, (gate_result, _) in result.gate_results.items():
            gate_scores[gate_name] = 1.0 if gate_result.value == "PASS" else 0.0

        return {
            "passed": passed,
            "decision": decision_val,
            "reason": result.reason,
            "gate_scores": gate_scores,
        }
    except Exception as e:
        # Fallback to basic check if TelosGatekeeper not available
        logger.debug("TelosGatekeeper unavailable, using fallback gate: %s", e)
        content = artifact.get("content", "")
        passed = len(content) > 0 if isinstance(content, str) else True
        return {
            "passed": passed,
            "decision": "allow" if passed else "block",
            "reason": f"fallback gate (TelosGatekeeper error: {e})",
            "gate_scores": {"telos": 1.0 if passed else 0.0},
        }


def default_eigenform(current: dict[str, Any], previous: dict[str, Any]) -> float:
    """Default eigenform distance — normalised L1 on fitness vectors.

    Returns a float in [0, inf). When distance < epsilon, the loop has
    found a fixed point: F(S) ≈ S.
    """
    c_vec = _extract_fitness_vector(current)
    p_vec = _extract_fitness_vector(previous)

    if not c_vec or not p_vec:
        return float("inf")

    # Pad to same length
    max_len = max(len(c_vec), len(p_vec))
    c_vec.extend([0.0] * (max_len - len(c_vec)))
    p_vec.extend([0.0] * (max_len - len(p_vec)))

    # Normalised L1
    total = sum(abs(c - p) for c, p in zip(c_vec, p_vec))
    norm = max(1.0, sum(abs(c) + abs(p) for c, p in zip(c_vec, p_vec)) / 2.0)
    return total / norm


def _extract_fitness_vector(artifact: dict[str, Any]) -> list[float]:
    """Pull numeric fitness values from an artifact dict."""
    fitness = artifact.get("fitness", {})
    if isinstance(fitness, dict):
        return [float(v) for v in fitness.values() if isinstance(v, (int, float))]

    score = artifact.get("score", artifact.get("stars", None))
    if isinstance(score, (int, float)):
        return [float(score)]

    return []


def default_generate(seed: dict[str, Any] | None, context: dict[str, Any]) -> dict[str, Any]:
    """Default generate — returns seed or empty artifact. Stub."""
    if seed:
        return dict(seed)
    return {"content": "", "fitness": {}, "metadata": {"generated": True}}


def default_test(artifact: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Default test — always passes. Stub."""
    artifact["test_passed"] = True
    artifact["test_results"] = {"status": "pass", "details": "stub test"}
    return artifact


def default_score(artifact: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Default score — assigns baseline fitness. Stub."""
    content = artifact.get("content", "")
    base_score = min(1.0, len(content) / 1000.0) if isinstance(content, str) else 0.5
    artifact["fitness"] = artifact.get("fitness", {})
    artifact["fitness"]["quality"] = base_score
    artifact["fitness"]["completeness"] = 1.0 if artifact.get("test_passed") else 0.0
    artifact["score"] = (base_score + artifact["fitness"]["completeness"]) / 2.0
    return artifact


def default_mutate(artifact: dict[str, Any], context: dict[str, Any],
                   mutation_rate: float = 0.1) -> dict[str, Any]:
    """Default mutate — marks artifact as mutated. Stub."""
    mutated = dict(artifact)
    mutated["metadata"] = mutated.get("metadata", {})
    mutated["metadata"]["mutated"] = True
    mutated["metadata"]["mutation_rate"] = mutation_rate
    return mutated


def default_select(candidates: list[dict[str, Any]],
                   context: dict[str, Any]) -> dict[str, Any]:
    """Default select — pick highest-scoring candidate."""
    if not candidates:
        return {"content": "", "fitness": {}}
    return max(candidates, key=lambda c: c.get("score", 0.0))
