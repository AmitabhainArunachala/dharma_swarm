from __future__ import annotations

from dataclasses import dataclass, field

from dharma_swarm.runtime_fields import RuntimeFieldRegistry


@dataclass
class Sampler:
    temperature: float = 0.7


@dataclass
class Workflow:
    system_prompt: str = "You are a helpful assistant."
    sampler: Sampler = field(default_factory=Sampler)
    metadata: dict[str, str] = field(default_factory=lambda: {"style": "precise"})
    steps: list[dict[str, object]] = field(
        default_factory=lambda: [{"name": "draft", "enabled": True}]
    )


def test_track_plain_attribute_and_mutate() -> None:
    workflow = Workflow()
    registry = RuntimeFieldRegistry()

    registry.track(workflow, "system_prompt")

    assert registry.get("system_prompt") == "You are a helpful assistant."
    registry.set("system_prompt", "You are a critical reviewer.")
    assert workflow.system_prompt == "You are a critical reviewer."


def test_track_nested_path_for_attribute_dict_and_list() -> None:
    workflow = Workflow()
    registry = RuntimeFieldRegistry()

    registry.track(workflow, "sampler.temperature", name="temperature")
    registry.track(workflow, "metadata['style']", name="style")
    registry.track(workflow, "steps[0]['enabled']", name="draft_enabled")

    registry.set("temperature", 0.2)
    registry.set("style", "concise")
    registry.set("draft_enabled", False)

    assert workflow.sampler.temperature == 0.2
    assert workflow.metadata["style"] == "concise"
    assert workflow.steps[0]["enabled"] is False


def test_reset_restores_initial_values() -> None:
    workflow = Workflow()
    registry = RuntimeFieldRegistry()
    registry.track(
        [
            (workflow, "system_prompt"),
            (workflow, "sampler.temperature", "temperature"),
        ]
    )

    registry.set("system_prompt", "Changed")
    registry.set("temperature", 0.1)
    registry.reset()

    assert workflow.system_prompt == "You are a helpful assistant."
    assert workflow.sampler.temperature == 0.7


def test_reset_field_restores_single_registered_value() -> None:
    workflow = Workflow()
    registry = RuntimeFieldRegistry()
    registry.track(workflow, "metadata['style']", name="style")

    registry.set("style", "bold")
    registry.reset_field("style")

    assert workflow.metadata["style"] == "precise"


def test_batch_track_registers_multiple_names() -> None:
    workflow = Workflow()
    registry = RuntimeFieldRegistry()

    registry.track(
        [
            (workflow, "system_prompt"),
            (workflow, "sampler.temperature", "temperature"),
        ]
    )

    assert registry.names() == ["system_prompt", "temperature"]
