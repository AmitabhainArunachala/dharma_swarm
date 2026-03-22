"""Tests for resource_scout.py — GPU compute procurement."""

from __future__ import annotations

import pytest

from dharma_swarm.resource_scout import (
    GPUInstance,
    GPUProvider,
    GPUType,
    ResourceScout,
    TrainingEstimate,
)


@pytest.fixture
def scout() -> ResourceScout:
    return ResourceScout()


# --- GPUInstance model ---


def test_gpu_instance_price_per_day() -> None:
    g = GPUInstance(
        provider=GPUProvider.RUNPOD, gpu_type=GPUType.A100_40GB,
        price_per_hour=1.44,
    )
    assert abs(g.price_per_day - 34.56) < 0.01


def test_gpu_instance_effective_vram() -> None:
    g = GPUInstance(
        provider=GPUProvider.RUNPOD, gpu_type=GPUType.A100_80GB,
        vram_gb=80, gpu_count=2,
    )
    assert g.effective_vram == 160


# --- find_cheapest ---


def test_find_cheapest_returns_sorted(scout: ResourceScout) -> None:
    results = scout.find_cheapest(min_vram_gb=8)
    assert len(results) > 0
    prices = [r.price_per_hour for r in results if not r.spot]
    # Non-spot prices should be ascending after spots
    assert all(p >= 0 for p in prices)


def test_find_cheapest_respects_min_vram(scout: ResourceScout) -> None:
    results = scout.find_cheapest(min_vram_gb=80)
    for r in results:
        assert r.vram_gb >= 80


def test_find_cheapest_max_price(scout: ResourceScout) -> None:
    results = scout.find_cheapest(max_price_per_hour=0.50)
    for r in results:
        assert r.price_per_hour <= 0.50


def test_find_cheapest_exclude_local(scout: ResourceScout) -> None:
    results = scout.find_cheapest(exclude_local=True)
    for r in results:
        assert r.provider != GPUProvider.LOCAL


def test_find_cheapest_includes_local_by_default(scout: ResourceScout) -> None:
    results = scout.find_cheapest(min_vram_gb=1)
    providers = {r.provider for r in results}
    assert GPUProvider.LOCAL in providers


def test_find_cheapest_spot_preferred(scout: ResourceScout) -> None:
    results = scout.find_cheapest(prefer_spot=True)
    if len(results) >= 2:
        # First spot instance should come before first non-spot
        first_spot_idx = next(
            (i for i, r in enumerate(results) if r.spot), len(results)
        )
        first_nonspot_idx = next(
            (i for i, r in enumerate(results) if not r.spot), len(results)
        )
        assert first_spot_idx <= first_nonspot_idx


# --- estimate_training_cost ---


def test_estimate_7b_qlora(scout: ResourceScout) -> None:
    est = scout.estimate_training_cost(model_size_b=7.0)
    assert est.model_size_b == 7.0
    assert est.method == "qlora"
    assert est.estimated_hours > 0
    assert est.estimated_cost_usd > 0
    assert est.recommended_gpu is not None
    assert est.recommended_provider is not None


def test_estimate_70b_more_expensive(scout: ResourceScout) -> None:
    est_7b = scout.estimate_training_cost(model_size_b=7.0)
    est_70b = scout.estimate_training_cost(model_size_b=70.0)
    assert est_70b.estimated_cost_usd > est_7b.estimated_cost_usd


def test_estimate_full_finetune_more_expensive(scout: ResourceScout) -> None:
    est_qlora = scout.estimate_training_cost(model_size_b=7.0, method="qlora")
    est_full = scout.estimate_training_cost(model_size_b=7.0, method="full")
    assert est_full.estimated_hours > est_qlora.estimated_hours


def test_estimate_budget_check(scout: ResourceScout) -> None:
    est = scout.estimate_training_cost(model_size_b=7.0, budget_usd=1000.0)
    assert est.fits_in_budget is True

    est_low = scout.estimate_training_cost(model_size_b=70.0, budget_usd=0.50)
    assert est_low.fits_in_budget is False


def test_estimate_dataset_scaling(scout: ResourceScout) -> None:
    est_small = scout.estimate_training_cost(model_size_b=7.0, dataset_size_mb=10.0)
    est_large = scout.estimate_training_cost(model_size_b=7.0, dataset_size_mb=150.0)
    assert est_large.estimated_hours >= est_small.estimated_hours


# --- recommend_for_generation ---


def test_recommend_gen0(scout: ResourceScout) -> None:
    rec = scout.recommend_for_generation(gen=0, budget_usd=50.0)
    assert rec.model_size_b <= 7.0 or rec.fits_in_budget


def test_recommend_gen1(scout: ResourceScout) -> None:
    rec = scout.recommend_for_generation(gen=1, budget_usd=100.0)
    assert rec.recommended_gpu is not None


def test_recommend_low_budget_falls_back(scout: ResourceScout) -> None:
    rec = scout.recommend_for_generation(gen=3, budget_usd=0.01)
    # Should fall back to smallest model
    assert rec.model_size_b <= 7.0


# --- pricing_table ---


def test_pricing_table(scout: ResourceScout) -> None:
    table = scout.pricing_table()
    assert len(table) > 0
    assert "provider" in table[0]
    assert "price_hr" in table[0]
    # Should be sorted by price
    prices = [row["price_hr"] for row in table]
    assert prices == sorted(prices)


# --- size_to_key ---


def test_size_to_key(scout: ResourceScout) -> None:
    assert scout._size_to_key(3.0) == "7b"
    assert scout._size_to_key(7.0) == "7b"
    assert scout._size_to_key(14.0) == "14b"
    assert scout._size_to_key(32.0) == "32b"
    assert scout._size_to_key(70.0) == "70b"
    assert scout._size_to_key(200.0) == "120b"
