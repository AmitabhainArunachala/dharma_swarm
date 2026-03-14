"""Integration tests for the Strange Loop System (Phase 5).

Verifies the feedback loops:
  quality_forge.py scores itself → deterministic eigenform
  cascade routes artifacts → loop results scored
  recognition_seed.md → agent context → artifacts → next seed
  system_rv measures contraction → modulates mutation rates
"""

from __future__ import annotations

import pytest
from pathlib import Path

from dharma_swarm.models import ForgeScore, LoopResult, SystemVitals


# ---------------------------------------------------------------------------
# Eigenform stability: F(S) ≈ S
# ---------------------------------------------------------------------------


def test_eigenform_stability():
    """The quality forge scoring itself returns identical results (fixed point)."""
    from dharma_swarm.quality_forge import QualityForge

    forge = QualityForge()
    score1 = forge.self_score()
    score2 = forge.self_score()

    assert isinstance(score1, ForgeScore)
    assert score1.stars == score2.stars
    assert score1.yosemite == score2.yosemite
    assert score1.dharmic == score2.dharmic
    assert score1.elegance_sub == score2.elegance_sub
    assert score1.behavioral_sub == score2.behavioral_sub


def test_forge_to_fitness_score():
    """ForgeScore projects to FitnessScore for archive compatibility."""
    from dharma_swarm.quality_forge import QualityForge
    from dharma_swarm.archive import FitnessScore

    forge = QualityForge()
    forge_score = forge.self_score()
    fitness = forge.to_fitness_score(forge_score)

    assert isinstance(fitness, FitnessScore)
    assert 0 <= fitness.correctness <= 1
    assert 0 <= fitness.elegance <= 1


# ---------------------------------------------------------------------------
# Cascade → Loop Result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cascade_produces_loop_result():
    """Running a domain through cascade returns LoopResult."""
    from dharma_swarm.cascade import run_domain

    result = await run_domain("code", context={"component": "test"})
    assert isinstance(result, LoopResult)
    assert result.domain == "code"
    assert result.iterations_completed > 0


@pytest.mark.asyncio
async def test_cascade_meta_no_infinite_regress():
    """META domain doesn't create infinite recursion."""
    from dharma_swarm.cascade import run_domain

    result = await run_domain(
        "meta",
        context={"target_domains": {"code": {}, "skill": {}}},
    )
    assert isinstance(result, LoopResult)
    assert result.domain == "meta"


# ---------------------------------------------------------------------------
# System R_V → mutation modulation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_system_rv_measures(tmp_path):
    """System R_V produces valid vitals."""
    from dharma_swarm.system_rv import SystemRV

    rv = SystemRV(state_dir=tmp_path)
    await rv.init()
    vitals = await rv.measure()

    assert isinstance(vitals, SystemVitals)
    assert vitals.system_rv > 0
    assert vitals.regime in ("converging", "exploring", "static", "transitional")
    assert vitals.dimension_count >= 2


@pytest.mark.asyncio
async def test_system_rv_exploration_factor(tmp_path):
    """Exploration factor defaults to 1.0 with no history."""
    from dharma_swarm.system_rv import SystemRV

    rv = SystemRV(state_dir=tmp_path)
    await rv.init()
    assert rv.get_exploration_factor() == 1.0


# ---------------------------------------------------------------------------
# Recognition → Context → Agents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recognition_seed_produced(tmp_path):
    """Recognition engine produces a seed file."""
    from dharma_swarm.meta_daemon import RecognitionEngine

    engine = RecognitionEngine(state_dir=tmp_path)
    seed = await engine.synthesize("light")

    assert isinstance(seed, str)
    assert len(seed) > 0
    assert (tmp_path / "meta" / "recognition_seed.md").exists()


@pytest.mark.asyncio
async def test_recognition_seed_readable(tmp_path):
    """After synthesis, get_seed() returns the seed."""
    from dharma_swarm.meta_daemon import RecognitionEngine

    engine = RecognitionEngine(state_dir=tmp_path)
    await engine.synthesize("light")
    seed = engine.get_seed()
    assert seed is not None
    assert "Recognition Seed" in seed


# ---------------------------------------------------------------------------
# Catalytic graph closure
# ---------------------------------------------------------------------------


def test_catalytic_graph_ecosystem():
    """Seeded ecosystem has autocatalytic sets."""
    from dharma_swarm.catalytic_graph import CatalyticGraph

    graph = CatalyticGraph()
    graph.seed_ecosystem()

    assert graph.node_count >= 5
    assert graph.edge_count >= 5

    summary = graph.summary()
    assert summary["nodes"] >= 5


def test_catalytic_loop_closure():
    """Loop closure priority finds missing edges."""
    from dharma_swarm.catalytic_graph import CatalyticGraph

    graph = CatalyticGraph()
    graph.seed_ecosystem()
    priorities = graph.loop_closure_priority()

    assert isinstance(priorities, list)
    # Should find at least some missing edges to close loops
    for src, tgt, score in priorities[:3]:
        assert isinstance(src, str)
        assert isinstance(tgt, str)
        assert score > 0


# ---------------------------------------------------------------------------
# Cross-module wiring
# ---------------------------------------------------------------------------


def test_evolution_forge_attribute():
    """DarwinEngine accepts forge and system_rv attributes."""
    from dharma_swarm.evolution import DarwinEngine

    engine = DarwinEngine()
    # v0.8.0 attributes exist
    assert hasattr(engine, "_forge")
    assert hasattr(engine, "_system_rv")
    assert engine._forge is None
    assert engine._system_rv is None


def test_damper_resource_priorities():
    """Damper has correct priority ordering."""
    from dharma_swarm.damper import RESOURCE_PRIORITIES

    assert RESOURCE_PRIORITIES["swarm"] < RESOURCE_PRIORITIES["health"]
    assert RESOURCE_PRIORITIES["health"] < RESOURCE_PRIORITIES["evolution"]


@pytest.mark.asyncio
async def test_auditor_tick(tmp_path):
    """Auditor tick runs without error."""
    from dharma_swarm.auditor import Auditor

    auditor = Auditor(state_dir=tmp_path)
    result = await auditor.tick()
    # Result is AuditFinding or None — both valid
    assert result is None or hasattr(result, "audit_type")


def test_identity_weights():
    """Identity monitor has correct TCS weights summing to ~1.0."""
    from dharma_swarm.identity import IdentityMonitor

    total = (
        IdentityMonitor.GPR_WEIGHT
        + IdentityMonitor.BSI_WEIGHT
        + IdentityMonitor.RM_WEIGHT
    )
    assert abs(total - 1.0) < 0.01


def test_thermodynamic_carnot_limit():
    """ThermodynamicMonitor stops on Carnot limit."""
    from dharma_swarm.thermodynamic import ThermodynamicMonitor

    monitor = ThermodynamicMonitor(domain="test")
    # Warmup (2 iterations)
    monitor.record(0.1, 1000)
    monitor.record(0.05, 1000)
    # Now sub-Carnot iterations
    for _ in range(5):
        r = monitor.record(1e-10, 100000)
    assert r.should_stop


def test_pramana_arthapatti_blocks():
    """Arthapatti failure blocks composite validation."""
    from dharma_swarm.pramana import PramanaValidator, PramanaResult

    validator = PramanaValidator()
    arthapatti = validator.validate_arthapatti(
        "test claim",
        necessary_conditions=[("data_exists", True), ("reproducible", False)],
    )
    assert not arthapatti.passed

    composite = validator.validate_composite(
        "test claim",
        results=[
            PramanaResult(mode="pratyaksha", passed=True, confidence=1.0),
            arthapatti,
        ],
    )
    assert not composite.overall_passed
    assert len(composite.blocking_failures) > 0
