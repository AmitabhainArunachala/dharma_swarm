from __future__ import annotations

from dataclasses import dataclass, field

from dharma_swarm.runtime_fields import RuntimeFieldRegistry


@dataclass
class _Sampler:
    temperature: float = 0.7


@dataclass
class _Workflow:
    system_prompt: str = "Research carefully."
    sampler: _Sampler = field(default_factory=_Sampler)
    metadata: dict[str, str] = field(default_factory=lambda: {"style": "precise"})


def test_optimizer_bridge_contracts_import_without_optional_dependencies() -> None:
    from dharma_swarm.optimizer_bridge import (
        RuntimeFieldCandidate,
        RuntimeFieldMutation,
        RuntimeFieldTrialResult,
    )

    mutation = RuntimeFieldMutation(field_name="temperature", candidate_value=0.2)
    result = RuntimeFieldTrialResult(
        mutations=[mutation],
        applied_fields=["temperature"],
        rolled_back=False,
        before={"temperature": 0.7},
        after={"temperature": 0.2},
    )
    candidate = RuntimeFieldCandidate(
        name="temperature",
        path="sampler.temperature",
        value_type="float",
        current_value=0.7,
        rollback_value=0.7,
        domain="numeric",
    )

    assert mutation.field_name == "temperature"
    assert result.applied_fields == ["temperature"]
    assert candidate.domain == "numeric"


def test_runtime_field_manifest_projects_supported_candidate_types() -> None:
    from dharma_swarm.optimizer_bridge import runtime_field_candidates_from_manifest

    manifest = [
        {
            "name": "system_prompt",
            "path": "system_prompt",
            "value_type": "str",
            "current_value": "Research carefully and cite every claim.",
        },
        {
            "name": "temperature",
            "path": "sampler.temperature",
            "value_type": "float",
            "current_value": 0.7,
        },
        {
            "name": "style",
            "path": "metadata['style']",
            "value_type": "str",
            "current_value": "precise",
        },
    ]

    candidates = runtime_field_candidates_from_manifest(manifest)
    by_name = {candidate.name: candidate for candidate in candidates}

    assert set(by_name) == {"system_prompt", "temperature", "style"}
    assert by_name["system_prompt"].domain == "prompt"
    assert by_name["temperature"].domain == "numeric"
    assert by_name["style"].domain == "categorical"
    assert by_name["style"].metadata["path"] == "metadata['style']"
    assert by_name["temperature"].rollback_value == 0.7


def test_apply_and_rollback_runtime_field_mutations_restores_registry_values() -> None:
    from dharma_swarm.optimizer_bridge import (
        RuntimeFieldMutation,
        apply_runtime_field_mutations,
        rollback_runtime_field_trial,
    )

    workflow = _Workflow()
    registry = RuntimeFieldRegistry()
    registry.track(
        [
            (workflow, "system_prompt"),
            (workflow, "sampler.temperature", "temperature"),
            (workflow, "metadata['style']", "style"),
        ]
    )

    trial = apply_runtime_field_mutations(
        registry,
        [
            RuntimeFieldMutation(field_name="temperature", candidate_value=0.2),
            RuntimeFieldMutation(field_name="style", candidate_value="exploratory"),
        ],
    )

    assert workflow.sampler.temperature == 0.2
    assert workflow.metadata["style"] == "exploratory"
    assert trial.applied_fields == ["temperature", "style"]
    assert trial.rolled_back is False

    rolled_back = rollback_runtime_field_trial(registry, trial)

    assert rolled_back.rolled_back is True
    assert workflow.sampler.temperature == 0.7
    assert workflow.metadata["style"] == "precise"


def test_optional_optimizer_adapters_are_guarded_and_textgrad_is_prompt_only() -> None:
    from dharma_swarm.optimizer_bridge import RuntimeFieldCandidate
    from dharma_swarm.optimizers import get_nevergrad_adapter, get_textgrad_adapter

    prompt_candidate = RuntimeFieldCandidate(
        name="system_prompt",
        path="system_prompt",
        value_type="str",
        current_value="Research carefully.",
        rollback_value="Research carefully.",
        domain="prompt",
    )
    numeric_candidate = RuntimeFieldCandidate(
        name="temperature",
        path="sampler.temperature",
        value_type="float",
        current_value=0.7,
        rollback_value=0.7,
        domain="numeric",
    )

    nevergrad = get_nevergrad_adapter()
    textgrad = get_textgrad_adapter()

    assert nevergrad.name == "nevergrad"
    assert textgrad.name == "textgrad"
    assert textgrad.supports(prompt_candidate) is True
    assert textgrad.supports(numeric_candidate) is False
    if not nevergrad.available:
        assert "optional dependency" in nevergrad.reason.lower()
    if not textgrad.available:
        assert "optional dependency" in textgrad.reason.lower()
