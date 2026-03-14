"""META domain — evolves LoopDomain configs themselves.

THE strange loop: domains are candidates. The META domain can mutate
max_iterations, fitness_threshold, mutation_rate, etc. of other domains.

Constraint: target_domains excludes "meta" (no infinite regress).
"""

from __future__ import annotations

import copy
import random
from typing import Any

from dharma_swarm.models import LoopDomain


def get_domain(config: dict[str, Any] | None = None) -> LoopDomain:
    """Return the META domain configuration."""
    cfg = config or {}
    return LoopDomain(
        name="meta",
        generate_fn="dharma_swarm.cascade_domains.meta.generate",
        test_fn="dharma_swarm.cascade_domains.meta.test",
        score_fn="dharma_swarm.cascade_domains.meta.score",
        gate_fn="dharma_swarm.cascade_domains.meta.gate",
        mutate_fn="dharma_swarm.cascade_domains.meta.mutate",
        select_fn="dharma_swarm.cascade_domains.common.default_select",
        eigenform_fn="dharma_swarm.cascade_domains.common.default_eigenform",
        max_iterations=cfg.get("max_iterations", 10),
        fitness_threshold=cfg.get("fitness_threshold", 0.7),
        eigenform_epsilon=cfg.get("eigenform_epsilon", 0.03),
    )


# Tunable parameters and their bounds
_TUNABLE_PARAMS = {
    "max_iterations": (5, 100),
    "fitness_threshold": (0.3, 0.9),
    "mutation_rate": (0.01, 0.5),
    "eigenform_epsilon": (0.01, 0.2),
    "convergence_window": (3, 30),
    "max_duration_seconds": (60.0, 3600.0),
}


def generate(seed: dict[str, Any] | None, context: dict[str, Any]) -> dict[str, Any]:
    """Generate a domain config variant. Stub — returns current configs."""
    if seed:
        return dict(seed)

    # Start with existing domain configs from context
    target_domains = context.get("target_domains", {})
    # Never include "meta" in targets (no infinite regress)
    target_domains = {k: v for k, v in target_domains.items() if k != "meta"}

    return {
        "content": "meta domain config variant",
        "target_domains": target_domains,
        "fitness": {},
    }


def test(artifact: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Test meta artifact — verify configs are within valid bounds."""
    target_domains = artifact.get("target_domains", {})
    valid = True
    issues: list[str] = []

    for domain_name, domain_cfg in target_domains.items():
        if domain_name == "meta":
            valid = False
            issues.append("meta domain cannot target itself")
            continue

        for param, (lo, hi) in _TUNABLE_PARAMS.items():
            val = domain_cfg.get(param)
            if val is not None and not (lo <= val <= hi):
                valid = False
                issues.append(f"{domain_name}.{param}={val} outside [{lo},{hi}]")

    artifact["test_passed"] = valid
    artifact["test_results"] = {"status": "pass" if valid else "fail", "issues": issues}
    return artifact


def score(artifact: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Score meta artifact based on config quality. Stub."""
    target_domains = artifact.get("target_domains", {})
    if not target_domains:
        artifact["fitness"] = {"coverage": 0.0}
        artifact["score"] = 0.0
        return artifact

    # Score based on coverage and parameter diversity
    coverage = min(1.0, len(target_domains) / 4.0)
    validity = 1.0 if artifact.get("test_passed") else 0.0

    artifact["fitness"] = {
        "coverage": coverage,
        "validity": validity,
    }
    artifact["score"] = (coverage + validity) / 2.0
    return artifact


def gate(artifact: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Gate for meta domain — blocks self-targeting."""
    target_domains = artifact.get("target_domains", {})
    has_meta = "meta" in target_domains
    return {
        "passed": not has_meta,
        "decision": "block" if has_meta else "allow",
        "reason": "meta cannot target itself" if has_meta else "valid target set",
        "gate_scores": {"no_regress": 0.0 if has_meta else 1.0},
    }


def mutate(artifact: dict[str, Any], context: dict[str, Any],
           mutation_rate: float = 0.1) -> dict[str, Any]:
    """Mutate domain configs — perturb tunable parameters."""
    mutated = copy.deepcopy(artifact)
    target_domains = mutated.get("target_domains", {})

    for domain_cfg in target_domains.values():
        for param, (lo, hi) in _TUNABLE_PARAMS.items():
            if param in domain_cfg and random.random() < mutation_rate:
                current = domain_cfg[param]
                # Perturb by ±10%
                delta = (hi - lo) * 0.1 * (random.random() * 2 - 1)
                if isinstance(current, int):
                    domain_cfg[param] = max(int(lo), min(int(hi), int(current + delta)))
                else:
                    domain_cfg[param] = max(lo, min(hi, current + delta))

    mutated["metadata"] = mutated.get("metadata", {})
    mutated["metadata"]["mutated"] = True
    mutated["metadata"]["mutation_rate"] = mutation_rate
    return mutated
