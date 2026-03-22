"""Tests for EconomicEngine, ResourceScout, DatasetBuilder, and ModelRegistry."""

from __future__ import annotations

from pathlib import Path

import pytest

from dharma_swarm.economic_engine import (
    BudgetCategory,
    BudgetState,
    EconomicEngine,
    ExpenseCategory,
    RevenueSource,
    TransactionType,
)
from dharma_swarm.resource_scout import (
    GPUProvider,
    GPUType,
    ResourceScout,
    TrainingEstimate,
)
from dharma_swarm.dataset_builder import (
    DatasetBuilder,
    DatasetConfig,
    DatasetSample,
)
from dharma_swarm.model_registry import (
    ModelGeneration,
    ModelRegistry,
)


# ---------------------------------------------------------------------------
# EconomicEngine
# ---------------------------------------------------------------------------

class TestEconomicEngine:

    def test_creation(self, tmp_path):
        e = EconomicEngine(storage_dir=tmp_path)
        assert e.balance == 0.0
        assert e.transaction_count == 0

    def test_record_revenue(self, tmp_path):
        e = EconomicEngine(storage_dir=tmp_path)
        tx = e.record_revenue(10.0, RevenueSource.CRYPTO_MINING, "Mined ETH")
        assert tx.type == TransactionType.REVENUE
        assert tx.amount_usd == 10.0
        assert e.balance == 10.0

    def test_revenue_auto_allocates_budget(self, tmp_path):
        e = EconomicEngine(storage_dir=tmp_path)
        e.record_revenue(100.0, RevenueSource.CRYPTO_MINING)
        # 60% training, 20% ops, 10% reserve, 10% reinvestment
        assert e.budget.training == 60.0
        assert e.budget.operations == 20.0
        assert e.budget.reserve == 10.0
        assert e.budget.reinvestment == 10.0

    def test_record_expense(self, tmp_path):
        e = EconomicEngine(storage_dir=tmp_path)
        e.record_revenue(50.0, RevenueSource.GRANTS)
        e.record_expense(10.0, ExpenseCategory.GPU_TRAINING, "RunPod 1hr")
        assert e.balance == 40.0
        assert e.budget.training == 20.0  # 50*0.6=30, minus 10

    def test_can_afford_training(self, tmp_path):
        e = EconomicEngine(storage_dir=tmp_path)
        e.record_revenue(100.0, RevenueSource.API_SERVICES)
        assert e.can_afford_training(50.0)  # 60.0 budget > 50
        assert not e.can_afford_training(70.0)  # 60.0 budget < 70

    def test_api_savings(self, tmp_path):
        e = EconomicEngine(storage_dir=tmp_path)
        e.record_api_savings(0.50, "Used local model instead of Opus")
        assert e.balance == 0.50
        snap = e.snapshot()
        assert snap.revenue_by_source.get("api_savings", 0) == 0.50

    def test_allocate_budget(self, tmp_path):
        e = EconomicEngine(storage_dir=tmp_path)
        e.record_revenue(100.0, RevenueSource.GRANTS)
        # Move $5 from reinvestment to training
        e.allocate_budget(BudgetCategory.TRAINING, 5.0, from_category=BudgetCategory.REINVESTMENT)
        assert e.budget.training == 65.0  # 60 + 5
        assert e.budget.reinvestment == 5.0  # 10 - 5

    def test_snapshot(self, tmp_path):
        e = EconomicEngine(storage_dir=tmp_path)
        e.record_revenue(100.0, RevenueSource.CRYPTO_MINING)
        e.record_expense(20.0, ExpenseCategory.GPU_TRAINING)
        snap = e.snapshot()
        assert snap.total_revenue == 100.0
        assert snap.total_expenses == 20.0
        assert snap.net_balance == 80.0
        assert snap.transaction_count == 2

    def test_persistence(self, tmp_path):
        e1 = EconomicEngine(storage_dir=tmp_path)
        e1.record_revenue(50.0, RevenueSource.BOUNTIES)
        e1.record_expense(10.0, ExpenseCategory.API_CALLS)

        # Load in new instance
        e2 = EconomicEngine(storage_dir=tmp_path)
        assert e2.transaction_count == 2
        assert e2.balance == 40.0
        assert e2.budget.training == 20.0  # 50*0.6 - 10

    def test_budget_state_total(self):
        b = BudgetState(training=10, inference=5, operations=3, reserve=2, reinvestment=1)
        assert b.total == 21.0


# ---------------------------------------------------------------------------
# ResourceScout
# ---------------------------------------------------------------------------

class TestResourceScout:

    def test_find_cheapest(self):
        scout = ResourceScout()
        options = scout.find_cheapest(min_vram_gb=8)
        assert len(options) > 0
        # Should be sorted by price
        prices = [g.price_per_hour for g in options]
        assert prices == sorted(prices) or options[0].spot  # Spot first, then sorted

    def test_find_cheapest_high_vram(self):
        scout = ResourceScout()
        options = scout.find_cheapest(min_vram_gb=80)
        assert all(g.vram_gb >= 80 for g in options)

    def test_find_cheapest_exclude_local(self):
        scout = ResourceScout()
        options = scout.find_cheapest(min_vram_gb=1, exclude_local=True)
        assert all(g.provider != GPUProvider.LOCAL for g in options)

    def test_estimate_7b_training(self):
        scout = ResourceScout()
        est = scout.estimate_training_cost(model_size_b=7.0)
        assert est.estimated_hours > 0
        assert est.estimated_cost_usd > 0
        assert est.recommended_gpu is not None

    def test_estimate_70b_training(self):
        scout = ResourceScout()
        est = scout.estimate_training_cost(model_size_b=70.0)
        assert est.estimated_hours > 10  # Should be substantial
        assert est.recommended_gpu in (GPUType.A100_40GB, GPUType.A100_80GB, GPUType.H100_80GB)

    def test_estimate_fits_budget(self):
        scout = ResourceScout()
        est = scout.estimate_training_cost(model_size_b=7.0, budget_usd=100.0)
        assert est.fits_in_budget is True
        est2 = scout.estimate_training_cost(model_size_b=70.0, budget_usd=1.0)
        assert est2.fits_in_budget is False

    def test_recommend_gen0(self):
        scout = ResourceScout()
        rec = scout.recommend_for_generation(gen=0, budget_usd=20.0)
        assert rec.model_size_b == 7.0
        assert rec.fits_in_budget is True

    def test_recommend_gen2_fallback(self):
        scout = ResourceScout()
        # With tiny budget, should fall back to smaller model
        rec = scout.recommend_for_generation(gen=2, budget_usd=5.0)
        assert rec.model_size_b <= 32.0  # Fell back from 32B target

    def test_pricing_table(self):
        scout = ResourceScout()
        table = scout.pricing_table()
        assert len(table) > 0
        assert "provider" in table[0]
        assert "price_hr" in table[0]


# ---------------------------------------------------------------------------
# DatasetBuilder
# ---------------------------------------------------------------------------

class TestDatasetBuilder:

    def test_creation(self, tmp_path):
        builder = DatasetBuilder(output_dir=tmp_path)
        assert builder is not None

    def test_build_no_extra_sources(self, tmp_path):
        builder = DatasetBuilder(output_dir=tmp_path)
        config = DatasetConfig(
            name="test",
            include_foundations=False,
            include_dreams=False,
            include_stigmergy=False,
            include_evolution=False,
        )
        stats = builder.build(config)
        # Only trajectories (if any exist from live system)
        assert stats.by_source.get("foundation", 0) == 0
        assert stats.by_source.get("dream", 0) == 0
        assert stats.by_source.get("stigmergy", 0) == 0
        assert stats.by_source.get("evolution", 0) == 0

    def test_sample_format_openai(self, tmp_path):
        builder = DatasetBuilder(output_dir=tmp_path)
        sample = DatasetSample(
            messages=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ],
            source="test",
        )
        formatted = builder._format_sample(sample, "openai")
        assert "messages" in formatted
        assert len(formatted["messages"]) == 3

    def test_sample_format_alpaca(self, tmp_path):
        builder = DatasetBuilder(output_dir=tmp_path)
        sample = DatasetSample(
            messages=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "question"},
                {"role": "assistant", "content": "answer"},
            ],
            source="test",
        )
        formatted = builder._format_sample(sample, "alpaca")
        assert "instruction" in formatted
        assert "output" in formatted
        assert formatted["output"] == "answer"

    def test_dataset_config_defaults(self):
        config = DatasetConfig()
        assert config.min_thinkodynamic_score == 0.7
        assert config.success_only is True
        assert config.chat_format == "openai"


# ---------------------------------------------------------------------------
# ModelRegistry
# ---------------------------------------------------------------------------

class TestModelRegistry:

    def test_creation(self, tmp_path):
        r = ModelRegistry(storage_dir=tmp_path)
        assert r.generation_count == 0

    def test_register(self, tmp_path):
        r = ModelRegistry(storage_dir=tmp_path)
        gen0 = r.register(ModelGeneration(
            generation=0,
            base_model="mistral-7b-v0.1",
            parameters_b=7.0,
            training_cost_usd=8.50,
        ))
        assert gen0.name == "dharma-7b-gen0"
        assert r.generation_count == 1

    def test_latest(self, tmp_path):
        r = ModelRegistry(storage_dir=tmp_path)
        r.register(ModelGeneration(generation=0, parameters_b=7.0, base_model="m7b"))
        r.register(ModelGeneration(generation=1, parameters_b=32.0, base_model="q32b"))
        latest = r.latest()
        assert latest is not None
        assert latest.generation == 1
        assert latest.parameters_b == 32.0

    def test_latest_deployed(self, tmp_path):
        r = ModelRegistry(storage_dir=tmp_path)
        r.register(ModelGeneration(generation=0, parameters_b=7.0, deployed=True, base_model="m7b"))
        r.register(ModelGeneration(generation=1, parameters_b=32.0, deployed=False, base_model="q32b"))
        deployed = r.latest_deployed()
        assert deployed is not None
        assert deployed.generation == 0  # Only gen0 is deployed

    def test_best_by_thinkodynamic(self, tmp_path):
        r = ModelRegistry(storage_dir=tmp_path)
        r.register(ModelGeneration(generation=0, parameters_b=7.0, thinkodynamic_composite=0.6, base_model="m7b"))
        r.register(ModelGeneration(generation=1, parameters_b=32.0, thinkodynamic_composite=0.85, base_model="q32b"))
        best = r.best_by_thinkodynamic()
        assert best is not None
        assert best.generation == 1

    def test_total_training_cost(self, tmp_path):
        r = ModelRegistry(storage_dir=tmp_path)
        r.register(ModelGeneration(generation=0, parameters_b=7.0, training_cost_usd=10, base_model="m"))
        r.register(ModelGeneration(generation=1, parameters_b=32.0, training_cost_usd=150, base_model="q"))
        assert r.total_training_cost() == 160.0

    def test_lineage(self, tmp_path):
        r = ModelRegistry(storage_dir=tmp_path)
        r.register(ModelGeneration(generation=0, parameters_b=7.0, base_model="m7b"))
        r.register(ModelGeneration(generation=1, parameters_b=32.0, parent_generation=0, base_model="q32b"))
        lin = r.lineage()
        assert len(lin) == 2
        assert lin[0]["gen"] == 0
        assert lin[1]["gen"] == 1

    def test_persistence(self, tmp_path):
        r1 = ModelRegistry(storage_dir=tmp_path)
        r1.register(ModelGeneration(generation=0, parameters_b=7.0, base_model="m7b"))

        r2 = ModelRegistry(storage_dir=tmp_path)
        assert r2.generation_count == 1
        assert r2.get(0) is not None
        assert r2.get(0).parameters_b == 7.0

    def test_model_id(self):
        g = ModelGeneration(generation=2, parameters_b=70.0, base_model="llama")
        assert g.model_id == "dharma-70b-gen2"
