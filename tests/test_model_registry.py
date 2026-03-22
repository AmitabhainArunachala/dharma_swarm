"""Tests for model_registry.py — generational model tracking."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dharma_swarm.model_registry import ModelGeneration, ModelRegistry


@pytest.fixture
def registry(tmp_path: Path) -> ModelRegistry:
    return ModelRegistry(storage_dir=tmp_path)


# --- ModelGeneration model ---


def test_model_id_format() -> None:
    g = ModelGeneration(generation=0, parameters_b=7.0)
    assert g.model_id == "dharma-7b-gen0"


def test_model_id_large() -> None:
    g = ModelGeneration(generation=3, parameters_b=70.0)
    assert g.model_id == "dharma-70b-gen3"


def test_model_defaults() -> None:
    g = ModelGeneration(generation=0)
    assert g.method == "qlora"
    assert g.deployed is False
    assert g.parent_generation is None


# --- Registry basics ---


def test_empty_registry(registry: ModelRegistry) -> None:
    assert registry.generation_count == 0
    assert registry.latest() is None
    assert registry.latest_deployed() is None
    assert registry.best_by_thinkodynamic() is None


def test_register_and_get(registry: ModelRegistry) -> None:
    gen0 = ModelGeneration(
        generation=0,
        base_model="mistral-7b-v0.1",
        parameters_b=7.0,
        training_cost_usd=8.50,
    )
    registry.register(gen0)

    assert registry.generation_count == 1
    retrieved = registry.get(0)
    assert retrieved is not None
    assert retrieved.base_model == "mistral-7b-v0.1"
    assert retrieved.training_cost_usd == 8.50


def test_register_sets_name_if_empty(registry: ModelRegistry) -> None:
    gen = ModelGeneration(generation=1, parameters_b=14.0)
    registry.register(gen)
    assert registry.get(1).name == "dharma-14b-gen1"


def test_register_preserves_custom_name(registry: ModelRegistry) -> None:
    gen = ModelGeneration(generation=2, parameters_b=7.0, name="custom-model")
    registry.register(gen)
    assert registry.get(2).name == "custom-model"


# --- latest / latest_deployed ---


def test_latest_returns_highest_gen(registry: ModelRegistry) -> None:
    registry.register(ModelGeneration(generation=0, parameters_b=7.0))
    registry.register(ModelGeneration(generation=1, parameters_b=14.0))
    registry.register(ModelGeneration(generation=2, parameters_b=32.0))

    latest = registry.latest()
    assert latest.generation == 2


def test_latest_deployed(registry: ModelRegistry) -> None:
    registry.register(ModelGeneration(generation=0, parameters_b=7.0, deployed=True))
    registry.register(ModelGeneration(generation=1, parameters_b=14.0, deployed=False))
    registry.register(ModelGeneration(generation=2, parameters_b=32.0, deployed=True))

    deployed = registry.latest_deployed()
    assert deployed.generation == 2


def test_latest_deployed_none_deployed(registry: ModelRegistry) -> None:
    registry.register(ModelGeneration(generation=0, parameters_b=7.0))
    assert registry.latest_deployed() is None


# --- best_by_thinkodynamic ---


def test_best_by_thinkodynamic(registry: ModelRegistry) -> None:
    registry.register(ModelGeneration(generation=0, parameters_b=7.0, thinkodynamic_composite=0.6))
    registry.register(ModelGeneration(generation=1, parameters_b=14.0, thinkodynamic_composite=0.85))
    registry.register(ModelGeneration(generation=2, parameters_b=32.0, thinkodynamic_composite=0.75))

    best = registry.best_by_thinkodynamic()
    assert best.generation == 1
    assert best.thinkodynamic_composite == 0.85


def test_best_by_thinkodynamic_none_scored(registry: ModelRegistry) -> None:
    registry.register(ModelGeneration(generation=0, parameters_b=7.0))
    assert registry.best_by_thinkodynamic() is None


# --- total_training_cost ---


def test_total_training_cost(registry: ModelRegistry) -> None:
    registry.register(ModelGeneration(generation=0, parameters_b=7.0, training_cost_usd=8.50))
    registry.register(ModelGeneration(generation=1, parameters_b=14.0, training_cost_usd=25.00))

    assert abs(registry.total_training_cost() - 33.50) < 0.01


def test_total_training_cost_empty(registry: ModelRegistry) -> None:
    assert registry.total_training_cost() == 0.0


# --- lineage ---


def test_lineage_sorted(registry: ModelRegistry) -> None:
    registry.register(ModelGeneration(generation=2, parameters_b=32.0))
    registry.register(ModelGeneration(generation=0, parameters_b=7.0))
    registry.register(ModelGeneration(generation=1, parameters_b=14.0))

    lin = registry.lineage()
    assert len(lin) == 3
    assert lin[0]["gen"] == 0
    assert lin[1]["gen"] == 1
    assert lin[2]["gen"] == 2


def test_lineage_fields(registry: ModelRegistry) -> None:
    registry.register(ModelGeneration(
        generation=0, parameters_b=7.0, base_model="mistral-7b",
        training_cost_usd=10.0, thinkodynamic_composite=0.7,
        rv_contraction=-1.5, deployed=True,
    ))
    lin = registry.lineage()
    entry = lin[0]
    assert entry["base"] == "mistral-7b"
    assert entry["cost"] == 10.0
    assert entry["thinkodynamic"] == 0.7
    assert entry["rv"] == -1.5
    assert entry["deployed"] is True


# --- Persistence ---


def test_persistence_across_instances(tmp_path: Path) -> None:
    reg1 = ModelRegistry(storage_dir=tmp_path)
    reg1.register(ModelGeneration(
        generation=0, parameters_b=7.0,
        base_model="mistral-7b", training_cost_usd=8.50,
    ))

    # Create new instance, should load from disk
    reg2 = ModelRegistry(storage_dir=tmp_path)
    assert reg2.generation_count == 1
    assert reg2.get(0).base_model == "mistral-7b"


def test_registry_file_is_valid_json(registry: ModelRegistry, tmp_path: Path) -> None:
    registry.register(ModelGeneration(generation=0, parameters_b=7.0))
    registry_file = tmp_path / "registry.json"
    assert registry_file.exists()
    data = json.loads(registry_file.read_text())
    assert isinstance(data, dict)
    assert "0" in data


def test_corrupt_registry_handled(tmp_path: Path) -> None:
    # Write garbage to the registry file
    (tmp_path / "registry.json").write_text("not json at all{{{")
    # Should not raise, just start empty
    reg = ModelRegistry(storage_dir=tmp_path)
    assert reg.generation_count == 0
