"""Tests for dharma_swarm.benchmark_registry."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dharma_swarm.benchmark_registry import (
    Benchmark,
    BenchmarkRegistry,
    _DEFAULT_BENCHMARKS,
)


@pytest.fixture()
def registry(tmp_path: Path) -> BenchmarkRegistry:
    return BenchmarkRegistry(path=tmp_path / "benchmarks.json")


class TestBenchmark:
    def test_fields(self):
        b = Benchmark(name="x", metric="ratio", baseline_value=0.9, threshold=0.8)
        assert b.name == "x"
        assert b.last_measured == 0.0
        assert b.last_value == 0.0


class TestBenchmarkRegistry:
    def test_seeds_defaults_on_new(self, registry: BenchmarkRegistry):
        assert len(registry) == len(_DEFAULT_BENCHMARKS)
        assert "gate_pass_rate" in registry
        assert "import_health" in registry

    def test_persists_to_disk(self, registry: BenchmarkRegistry):
        assert registry._path.exists()
        data = json.loads(registry._path.read_text())
        assert len(data) == len(_DEFAULT_BENCHMARKS)

    def test_register_new_benchmark(self, registry: BenchmarkRegistry):
        bm = registry.register("new_one", "count", baseline=100, threshold=80)
        assert bm.name == "new_one"
        assert "new_one" in registry
        assert len(registry) == len(_DEFAULT_BENCHMARKS) + 1

    def test_register_overwrites(self, registry: BenchmarkRegistry):
        registry.register("gate_pass_rate", "ratio", baseline=0.95, threshold=0.9)
        assert len(registry) == len(_DEFAULT_BENCHMARKS)

    def test_check_passes(self, registry: BenchmarkRegistry):
        assert registry.check("gate_pass_rate", 0.85) is True

    def test_check_fails(self, registry: BenchmarkRegistry):
        assert registry.check("gate_pass_rate", 0.5) is False

    def test_check_unknown_raises(self, registry: BenchmarkRegistry):
        with pytest.raises(KeyError):
            registry.check("nonexistent", 1.0)

    def test_update_records_value(self, registry: BenchmarkRegistry):
        registry.update("gate_pass_rate", 0.92)
        bm = registry._benchmarks["gate_pass_rate"]
        assert bm.last_value == 0.92
        assert bm.last_measured > 0

    def test_update_persists(self, registry: BenchmarkRegistry):
        registry.update("eval_pass_rate", 0.95)
        reg2 = BenchmarkRegistry(path=registry._path)
        assert reg2._benchmarks["eval_pass_rate"].last_value == 0.95

    def test_report_all_ok_initially(self, registry: BenchmarkRegistry):
        report = registry.report()
        assert len(report) == len(_DEFAULT_BENCHMARKS)
        assert all(r["status"] == "ok" for r in report)

    def test_report_detects_regression(self, registry: BenchmarkRegistry):
        registry.update("gate_pass_rate", 0.5)
        report = registry.report()
        gpr = next(r for r in report if r["name"] == "gate_pass_rate")
        assert gpr["status"] == "regression"

    def test_load_corrupt_file(self, tmp_path: Path):
        p = tmp_path / "bad.json"
        p.write_text("NOT VALID JSON{{{")
        reg = BenchmarkRegistry(path=p)
        assert len(reg) == len(_DEFAULT_BENCHMARKS)

    def test_contains(self, registry: BenchmarkRegistry):
        assert "gate_pass_rate" in registry
        assert "nonexistent" not in registry

    def test_len(self, registry: BenchmarkRegistry):
        assert len(registry) >= 4
