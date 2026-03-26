"""Runtime-field optimizer bridge for safe evolutionary trials.

This module keeps Phase 5 scoped to runtime-field mutation, projection, and
rollback. It deliberately avoids code-file mutation and optional optimizer
dependencies on import.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Iterable

from dharma_swarm.runtime_fields import RuntimeFieldRegistry, safe_deepcopy


@dataclass(frozen=True)
class RuntimeFieldCandidate:
    """A serializable optimizer-facing view of one mutable runtime field."""

    name: str
    path: str
    value_type: str
    current_value: Any
    rollback_value: Any
    domain: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeFieldMutation:
    """One proposed runtime-field mutation."""

    field_name: str
    candidate_value: Any
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuntimeFieldTrialResult:
    """Structured record of a runtime-field mutation trial."""

    mutations: list[RuntimeFieldMutation]
    applied_fields: list[str]
    rolled_back: bool
    before: dict[str, Any]
    after: dict[str, Any]
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OptimizerAdapterAvailability:
    """Availability and support constraints for an optional optimizer adapter."""

    name: str
    available: bool
    reason: str = ""
    supports_prompt_only: bool = False

    def supports(self, candidate: RuntimeFieldCandidate) -> bool:
        if self.supports_prompt_only:
            return candidate.domain == "prompt"
        return candidate.domain in {"numeric", "categorical", "prompt"}


def _infer_candidate_domain(
    *,
    name: str,
    path: str,
    value_type: str,
    current_value: Any,
) -> str:
    lowered_name = name.lower()
    lowered_path = path.lower()
    if isinstance(current_value, bool):
        return "categorical"
    if isinstance(current_value, (int, float)):
        return "numeric"
    if value_type in {"int", "float"}:
        return "numeric"
    if isinstance(current_value, str):
        if "prompt" in lowered_name or "prompt" in lowered_path or "instruction" in lowered_path:
            return "prompt"
        return "categorical"
    raise ValueError(
        f"Unsupported runtime field type for optimizer projection: {value_type}"
    )


def runtime_field_candidates_from_manifest(
    manifest: Iterable[dict[str, Any]],
) -> list[RuntimeFieldCandidate]:
    """Project manifest rows into stable optimizer candidates."""

    candidates: list[RuntimeFieldCandidate] = []
    for row in manifest:
        name = str(row.get("name", "")).strip()
        path = str(row.get("path", "")).strip()
        value_type = str(row.get("value_type", "")).strip() or type(row.get("current_value")).__name__
        current_value = safe_deepcopy(row.get("current_value"))
        if not name or not path:
            raise ValueError("Manifest rows must include non-empty name and path")
        domain = _infer_candidate_domain(
            name=name,
            path=path,
            value_type=value_type,
            current_value=current_value,
        )
        candidates.append(
            RuntimeFieldCandidate(
                name=name,
                path=path,
                value_type=value_type,
                current_value=current_value,
                rollback_value=safe_deepcopy(current_value),
                domain=domain,
                metadata={
                    "path": path,
                    "rollback_supported": True,
                },
            )
        )
    return candidates


def apply_runtime_field_mutations(
    registry: RuntimeFieldRegistry,
    mutations: Iterable[RuntimeFieldMutation],
) -> RuntimeFieldTrialResult:
    """Apply runtime-field mutations through the canonical registry."""

    before: dict[str, Any] = {}
    mutation_list = list(mutations)
    applied_fields: list[str] = []
    for mutation in mutation_list:
        before[mutation.field_name] = safe_deepcopy(registry.get(mutation.field_name))
        registry.set(mutation.field_name, mutation.candidate_value)
        applied_fields.append(mutation.field_name)
    after = {
        field_name: safe_deepcopy(registry.get(field_name))
        for field_name in applied_fields
    }
    return RuntimeFieldTrialResult(
        mutations=mutation_list,
        applied_fields=applied_fields,
        rolled_back=False,
        before=before,
        after=after,
    )


def rollback_runtime_field_trial(
    registry: RuntimeFieldRegistry,
    trial_result: RuntimeFieldTrialResult,
) -> RuntimeFieldTrialResult:
    """Rollback a runtime-field trial to the registry snapshot state."""

    for field_name in reversed(trial_result.applied_fields):
        registry.reset_field(field_name)
    trial_result.rolled_back = True
    trial_result.metadata["rolled_back_fields"] = list(trial_result.applied_fields)
    return trial_result


def render_runtime_field_trial_diff(
    mutations: Iterable[RuntimeFieldMutation],
) -> str:
    """Render runtime-field mutations as a stable archive diff payload."""

    payload = [
        {
            "field_name": mutation.field_name,
            "candidate_value": mutation.candidate_value,
            "metadata": dict(mutation.metadata),
        }
        for mutation in mutations
    ]
    return json.dumps(payload, sort_keys=True, indent=2, default=str)


__all__ = [
    "OptimizerAdapterAvailability",
    "RuntimeFieldCandidate",
    "RuntimeFieldMutation",
    "RuntimeFieldTrialResult",
    "apply_runtime_field_mutations",
    "render_runtime_field_trial_diff",
    "rollback_runtime_field_trial",
    "runtime_field_candidates_from_manifest",
]
