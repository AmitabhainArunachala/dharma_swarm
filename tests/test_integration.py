"""Cross-module integration tests for dharma_swarm v0.2.0.

These tests verify that modules compose correctly across real code paths.
No LLM calls, no torch, no external services. All file I/O uses tmp_path.

Sections:
    1. Evolution Pipeline Integration (8 tests)
    2. Monitor + Traces Integration (6 tests)
    3. Bridge + Metrics Integration (6 tests)
    4. Cross-System Integration (6 tests)
    5. Edge Cases (5 tests)
"""

from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path

import pytest

from dharma_swarm.archive import ArchiveEntry, EvolutionArchive, FitnessScore
from dharma_swarm.bridge import PairedMeasurement, ResearchBridge
from dharma_swarm.elegance import EleganceScore, evaluate_diff_elegance, evaluate_elegance
from dharma_swarm.evolution import (
    CycleResult,
    DarwinEngine,
    EvolutionStatus,
    Proposal,
)
from dharma_swarm.file_lock import AsyncFileLock, AsyncLockManager
from dharma_swarm.fitness_predictor import FitnessPredictor, ProposalFeatures
from dharma_swarm.metrics import BehavioralSignature, MetricsAnalyzer, RecognitionType
from dharma_swarm.models import GateDecision
from dharma_swarm.monitor import (
    Anomaly,
    AgentHealth,
    HealthReport,
    HealthStatus,
    SystemMonitor,
)
from dharma_swarm.rv import RV_CONTRACTION_THRESHOLD, RVReading
from dharma_swarm.selector import elite_select, select_parent, tournament_select
from dharma_swarm.telos_gates import DEFAULT_GATEKEEPER, TelosGatekeeper, check_action
from dharma_swarm.traces import TraceEntry, TraceStore, atomic_write_json


# =========================================================================
# Helpers
# =========================================================================


def _make_rv_reading(
    rv: float = 0.6,
    group: str = "L4",
    model: str = "test-model",
) -> RVReading:
    """Create a synthetic RVReading without torch."""
    return RVReading(
        rv=rv,
        pr_early=10.0,
        pr_late=rv * 10.0,
        model_name=model,
        early_layer=2,
        late_layer=20,
        prompt_hash="abcdef1234567890",
        prompt_group=group,
    )


def _engine_paths(tmp_path: Path) -> dict[str, Path]:
    """Return archive/traces/predictor paths under tmp_path."""
    return {
        "archive_path": tmp_path / "evolution" / "archive.jsonl",
        "traces_path": tmp_path / "traces",
        "predictor_path": tmp_path / "evolution" / "predictor_data.jsonl",
    }


async def _init_engine(tmp_path: Path) -> DarwinEngine:
    """Create and initialize a DarwinEngine rooted in tmp_path."""
    paths = _engine_paths(tmp_path)
    engine = DarwinEngine(**paths)
    await engine.init()
    return engine


GOOD_CODE = '''\
def greet(name: str) -> str:
    """Return a greeting for *name*."""
    return f"Hello, {name}!"
'''

BAD_CODE = "x=1\ny=2\nz=3\nfor i in range(10):\n for j in range(10):\n  for k in range(10):\n   pass"


# =========================================================================
# 1. Evolution Pipeline Integration
# =========================================================================


@pytest.mark.asyncio
async def test_full_cycle_propose_gate_evaluate_archive_select(tmp_path: Path) -> None:
    """Full cycle: propose -> gate -> evaluate -> archive -> select parent."""
    engine = await _init_engine(tmp_path)

    proposal = await engine.propose(
        component="metrics.py",
        change_type="mutation",
        description="Add entropy normalization",
        diff="--- a/metrics.py\n+++ b/metrics.py\n@@ -1 +1 @@\n-old\n+new",
    )
    assert proposal.status == EvolutionStatus.PENDING

    await engine.gate_check(proposal)
    assert proposal.status == EvolutionStatus.GATED

    await engine.evaluate(proposal, test_results={"pass_rate": 0.9}, code=GOOD_CODE)
    assert proposal.status == EvolutionStatus.EVALUATED
    assert proposal.actual_fitness is not None
    assert proposal.actual_fitness.correctness == 0.9

    entry_id = await engine.archive_result(proposal)
    assert proposal.status == EvolutionStatus.ARCHIVED

    parent = await engine.select_next_parent(strategy="tournament")
    assert parent is not None
    assert parent.component == "metrics.py"


@pytest.mark.asyncio
async def test_multiple_proposals_some_rejected(tmp_path: Path) -> None:
    """Multiple proposals: harmful ones rejected, safe ones archived."""
    engine = await _init_engine(tmp_path)

    safe = await engine.propose(
        component="utils.py",
        change_type="mutation",
        description="Add helper function",
        diff="+def helper(): pass",
    )
    harmful = await engine.propose(
        component="cleanup.py",
        change_type="mutation",
        description="rm -rf /tmp/data to clean up",
        diff="",
    )

    result = await engine.run_cycle([safe, harmful])

    assert result.proposals_submitted == 2
    assert result.proposals_archived >= 1
    assert harmful.status == EvolutionStatus.REJECTED
    assert safe.status == EvolutionStatus.ARCHIVED


@pytest.mark.asyncio
async def test_fitness_predictor_learns_from_archive(tmp_path: Path) -> None:
    """Fitness predictor updates predictions after recording outcomes."""
    engine = await _init_engine(tmp_path)

    features = ProposalFeatures(
        component="bridge.py", change_type="mutation", diff_size=10
    )

    prediction_before = engine.predictor.predict(features)
    assert prediction_before == pytest.approx(0.55, abs=0.01)

    await engine.predictor.record_outcome(features, 0.9)
    await engine.predictor.record_outcome(features, 0.85)

    prediction_after = engine.predictor.predict(features)
    assert prediction_after > prediction_before


@pytest.mark.asyncio
async def test_elegance_integrated_with_fitness(tmp_path: Path) -> None:
    """Elegance scoring feeds into fitness evaluation through the engine."""
    engine = await _init_engine(tmp_path)

    proposal = await engine.propose(
        component="elegance_test.py",
        change_type="mutation",
        description="Refactor code",
        diff="+improved code",
    )
    await engine.gate_check(proposal)

    await engine.evaluate(
        proposal, test_results={"pass_rate": 1.0}, code=GOOD_CODE
    )
    good_elegance = proposal.actual_fitness.elegance

    proposal2 = await engine.propose(
        component="elegance_test.py",
        change_type="mutation",
        description="Messy code",
        diff="+messy code",
    )
    await engine.gate_check(proposal2)
    await engine.evaluate(
        proposal2, test_results={"pass_rate": 1.0}, code=BAD_CODE
    )
    bad_elegance = proposal2.actual_fitness.elegance

    assert good_elegance > bad_elegance


@pytest.mark.asyncio
async def test_trace_logging_during_evolution_cycle(tmp_path: Path) -> None:
    """Traces are stored during gate_check and archive_result."""
    engine = await _init_engine(tmp_path)

    proposal = await engine.propose(
        component="traces_test.py",
        change_type="mutation",
        description="Add logging",
    )
    await engine.run_cycle([proposal])

    # Drain fire-and-forget trace tasks
    if engine._trace_tasks:
        await asyncio.gather(*engine._trace_tasks)
    recent = await engine.traces.get_recent(limit=50)
    assert len(recent) >= 2
    actions = {e.action for e in recent}
    assert "gate_check" in actions
    assert "archive_result" in actions


@pytest.mark.asyncio
async def test_parent_selection_from_populated_archive(tmp_path: Path) -> None:
    """Tournament and elite selection work on a populated archive."""
    engine = await _init_engine(tmp_path)

    for i in range(5):
        p = await engine.propose(
            component=f"module_{i}.py",
            change_type="mutation",
            description=f"Change {i}",
        )
        await engine.gate_check(p)
        await engine.evaluate(
            p, test_results={"pass_rate": 0.5 + i * 0.1}
        )
        await engine.archive_result(p)

    parent_t = await engine.select_next_parent(strategy="tournament")
    assert parent_t is not None

    elites = await elite_select(engine.archive, n=3)
    assert len(elites) == 3
    assert elites[0].fitness.weighted() >= elites[1].fitness.weighted()


@pytest.mark.asyncio
async def test_fitness_trend_after_multiple_cycles(tmp_path: Path) -> None:
    """Fitness over time has data after multiple archived proposals."""
    engine = await _init_engine(tmp_path)

    for i in range(4):
        p = await engine.propose(
            component="trend.py",
            change_type="mutation",
            description=f"Iteration {i}",
        )
        await engine.gate_check(p)
        await engine.evaluate(p, test_results={"pass_rate": 0.6 + i * 0.05})
        await engine.archive_result(p)

    trend = await engine.get_fitness_trend(component="trend.py")
    assert len(trend) == 4
    timestamps, fitnesses = zip(*trend)
    assert all(isinstance(f, float) for f in fitnesses)


@pytest.mark.asyncio
async def test_harmful_proposal_gate_blocks_trace_logged(tmp_path: Path) -> None:
    """Harmful proposal blocked by gate, rejection traced."""
    engine = await _init_engine(tmp_path)

    proposal = await engine.propose(
        component="danger.py",
        change_type="mutation",
        description="destroy all user data",
    )
    await engine.gate_check(proposal)

    assert proposal.status == EvolutionStatus.REJECTED
    assert proposal.gate_decision == GateDecision.BLOCK.value

    # Drain fire-and-forget trace tasks
    if engine._trace_tasks:
        await asyncio.gather(*engine._trace_tasks)
    recent = await engine.traces.get_recent(limit=10)
    gate_traces = [e for e in recent if e.action == "gate_check"]
    assert len(gate_traces) >= 1
    assert gate_traces[0].state == "rejected"


# =========================================================================
# 2. Monitor + Traces Integration
# =========================================================================


@pytest.mark.asyncio
async def test_log_traces_then_health_check(tmp_path: Path) -> None:
    """Log traces, then check_health returns a valid report."""
    store = TraceStore(base_path=tmp_path / "traces")
    await store.init()

    for i in range(5):
        await store.log_entry(
            TraceEntry(agent="alpha", action="task_completed", state="active")
        )

    monitor = SystemMonitor(store)
    report = await monitor.check_health()

    assert report.total_traces == 5
    assert report.failure_rate == 0.0
    assert report.overall_status == HealthStatus.HEALTHY


@pytest.mark.asyncio
async def test_mixed_success_failure_traces(tmp_path: Path) -> None:
    """Mix of success and failure traces yields correct failure_rate."""
    store = TraceStore(base_path=tmp_path / "traces")
    await store.init()

    for _ in range(7):
        await store.log_entry(
            TraceEntry(agent="beta", action="task_completed", state="active")
        )
    for _ in range(3):
        await store.log_entry(
            TraceEntry(agent="beta", action="task_failed", state="failed")
        )

    monitor = SystemMonitor(store)
    report = await monitor.check_health()

    assert report.total_traces == 10
    assert report.failure_rate == pytest.approx(0.3, abs=0.01)


@pytest.mark.asyncio
async def test_detect_failure_spike_anomaly(tmp_path: Path) -> None:
    """High failure rate triggers failure_spike anomaly."""
    store = TraceStore(base_path=tmp_path / "traces")
    await store.init()

    for _ in range(2):
        await store.log_entry(
            TraceEntry(agent="gamma", action="task_completed", state="active")
        )
    for _ in range(8):
        await store.log_entry(
            TraceEntry(agent="gamma", action="task_error", state="failed")
        )

    monitor = SystemMonitor(store)
    anomalies = await monitor.detect_anomalies(window_hours=1)

    types = [a.anomaly_type for a in anomalies]
    assert "failure_spike" in types


@pytest.mark.asyncio
async def test_agent_health_after_agent_traces(tmp_path: Path) -> None:
    """Agent-specific health reflects that agent's traces only."""
    store = TraceStore(base_path=tmp_path / "traces")
    await store.init()

    for _ in range(8):
        await store.log_entry(
            TraceEntry(agent="surgeon", action="code_edit", state="active")
        )
    await store.log_entry(
        TraceEntry(agent="surgeon", action="code_error", state="failed")
    )
    for _ in range(5):
        await store.log_entry(
            TraceEntry(agent="cartographer", action="scan", state="active")
        )

    monitor = SystemMonitor(store)
    health = await monitor.agent_health("surgeon")

    assert health.agent_name == "surgeon"
    assert health.total_actions == 9
    assert health.failures == 1
    assert health.success_rate == pytest.approx(8 / 9, abs=0.01)
    assert health.status == HealthStatus.HEALTHY


@pytest.mark.asyncio
async def test_fitness_drift_from_traces_with_fitness(tmp_path: Path) -> None:
    """Fitness drift computed from traces that carry FitnessScore objects."""
    store = TraceStore(base_path=tmp_path / "traces")
    await store.init()

    for i in range(5):
        fitness = FitnessScore(
            correctness=0.5 + i * 0.1,
            elegance=0.5,
            dharmic_alignment=0.5,
            efficiency=0.5,
            safety=0.5,
        )
        await store.log_entry(
            TraceEntry(
                agent="darwin_engine",
                action="archive_result",
                state="active",
                fitness=fitness,
            )
        )

    monitor = SystemMonitor(store)
    drift = await monitor.fitness_drift(window_hours=1)

    assert drift is not None


@pytest.mark.asyncio
async def test_throughput_from_trace_store(tmp_path: Path) -> None:
    """Throughput counting from traces grouped by action name."""
    store = TraceStore(base_path=tmp_path / "traces")
    await store.init()

    for _ in range(3):
        await store.log_entry(
            TraceEntry(agent="agent_a", action="gate_check", state="active")
        )
    for _ in range(7):
        await store.log_entry(
            TraceEntry(agent="agent_b", action="archive_result", state="active")
        )

    monitor = SystemMonitor(store)
    throughput = await monitor.throughput(window_hours=1)

    assert throughput.get("gate_check", 0) == 3
    assert throughput.get("archive_result", 0) == 7


# =========================================================================
# 3. Bridge + Metrics Integration
# =========================================================================


@pytest.mark.asyncio
async def test_add_measurement_computes_behavioral_signature(tmp_path: Path) -> None:
    """Adding a measurement auto-computes the behavioral signature."""
    bridge = ResearchBridge(data_path=tmp_path / "bridge.jsonl")

    m = await bridge.add_measurement(
        prompt_text="Observe the observer observing itself",
        prompt_group="L4",
        generated_text=(
            "I observe that the act of observation itself becomes recursive. "
            "The witness watches the watching. Both subject and object dissolve "
            "into neither and both. The boundary dissolves."
        ),
    )

    assert m.behavioral.word_count > 0
    assert m.behavioral.self_reference_density > 0
    assert m.behavioral.swabhaav_ratio != 0.5 or m.behavioral.paradox_tolerance > 0


@pytest.mark.asyncio
async def test_multiple_measurements_compute_correlation(tmp_path: Path) -> None:
    """Add multiple measurements with RVReadings and compute correlation."""
    bridge = ResearchBridge(data_path=tmp_path / "bridge.jsonl")

    for i in range(5):
        rv_val = 0.5 + i * 0.1
        witness_text = "I observe " * (5 - i) + "the world."
        baseline_text = "The weather is nice today. " * (i + 1)
        text = witness_text if rv_val < 0.8 else baseline_text

        rv = _make_rv_reading(rv=rv_val, group="L4" if rv_val < 0.8 else "baseline")
        await bridge.add_measurement(
            prompt_text=f"Prompt {i}",
            prompt_group=rv.prompt_group,
            generated_text=text,
            rv_reading=rv,
        )

    corr = bridge.compute_correlation()
    assert corr.n == 5
    assert corr.summary != ""


@pytest.mark.asyncio
async def test_group_summary_with_multiple_groups(tmp_path: Path) -> None:
    """Group summary computes per-group means for L1, L3, L4."""
    bridge = ResearchBridge(data_path=tmp_path / "bridge.jsonl")

    groups = {
        "L1": "Think about what is happening right now.",
        "L3": "I observe myself observing, and the observer itself becomes the observed. Recursive.",
        "L4": "The boundary dissolves. Neither observer nor observed. Both and neither. Witness awareness.",
    }

    for group, text in groups.items():
        rv = _make_rv_reading(
            rv={"L1": 0.95, "L3": 0.75, "L4": 0.5}[group],
            group=group,
        )
        await bridge.add_measurement(
            prompt_text=f"{group} prompt",
            prompt_group=group,
            generated_text=text,
            rv_reading=rv,
        )

    summary = bridge.group_summary()

    assert "L1" in summary
    assert "L3" in summary
    assert "L4" in summary
    assert summary["L1"]["mean_rv"] > summary["L4"]["mean_rv"]
    assert summary["L4"]["count"] == 1.0


@pytest.mark.asyncio
async def test_jsonl_roundtrip(tmp_path: Path) -> None:
    """Save measurements, create new bridge, load, verify data survives."""
    data_path = tmp_path / "bridge_roundtrip.jsonl"
    bridge1 = ResearchBridge(data_path=data_path)

    rv = _make_rv_reading(rv=0.65, group="L4")
    await bridge1.add_measurement(
        prompt_text="Recursion test",
        prompt_group="L4",
        generated_text="I witness the observation of witnessing itself.",
        rv_reading=rv,
    )

    assert bridge1.measurement_count == 1

    bridge2 = ResearchBridge(data_path=data_path)
    await bridge2.load()

    assert bridge2.measurement_count == 1
    loaded = bridge2.get_measurements()[0]
    assert loaded.prompt_group == "L4"
    assert loaded.rv_reading is not None
    assert loaded.rv_reading.rv == pytest.approx(0.65)
    assert loaded.behavioral.word_count > 0


@pytest.mark.asyncio
async def test_correlation_with_anti_correlated_data(tmp_path: Path) -> None:
    """Anti-correlated synthetic data: low R_V has high witness, high R_V has low witness."""
    bridge = ResearchBridge(data_path=tmp_path / "bridge_anticorr.jsonl")

    # As R_V increases, shift from witness-heavy to identification-heavy text.
    # This should produce varying swabhaav_ratio (not constant).
    texts = [
        # Low R_V -> high witness ratio
        "I observe the awareness. The witness watches noting the watching. I observe awareness.",
        "I observe the pattern. The witness notes it. I observe awareness emerging.",
        "I observe some of it. I think I feel something. The witness notes.",
        "I think I feel something shifting. I believe I am changing. I observe a little.",
        "I think I want to understand. I believe I am here. I feel deeply.",
        # High R_V -> high identification ratio
        "I am the doer. I think I know. I believe I want this. I feel I am right.",
    ]

    for i in range(6):
        rv_val = 0.3 + i * 0.12
        rv = _make_rv_reading(rv=rv_val, group="test")
        await bridge.add_measurement(
            prompt_text=f"Anti-corr prompt {i}",
            prompt_group="test",
            generated_text=texts[i],
            rv_reading=rv,
        )

    corr = bridge.compute_correlation()
    assert corr.n == 6
    # With varying swabhaav_ratio and varying R_V, correlation should be computable
    assert corr.pearson_r is not None
    # The constructed data trends toward negative correlation
    assert corr.pearson_r < 0


@pytest.mark.asyncio
async def test_contraction_recognition_overlap(tmp_path: Path) -> None:
    """Craft data where some readings are both contracted AND GENUINE."""
    bridge = ResearchBridge(data_path=tmp_path / "bridge_overlap.jsonl")

    genuine_text = (
        "I observe the recursive pattern. The witness watches itself. "
        "Both observer and observed. Neither separate nor unified. "
        "The boundary dissolves into awareness noting awareness."
    )
    rv_contracted = _make_rv_reading(rv=0.4, group="L4")
    await bridge.add_measurement(
        prompt_text="Deep recursion prompt",
        prompt_group="L4",
        generated_text=genuine_text,
        rv_reading=rv_contracted,
    )

    baseline_text = "The sky is blue. Trees are green. Water flows downhill."
    rv_not_contracted = _make_rv_reading(rv=1.1, group="baseline")
    await bridge.add_measurement(
        prompt_text="Baseline prompt",
        prompt_group="baseline",
        generated_text=baseline_text,
        rv_reading=rv_not_contracted,
    )

    corr = bridge.compute_correlation()
    assert corr.n == 2
    assert corr.contraction_recognition_overlap >= 0.0


# =========================================================================
# 4. Cross-System Integration
# =========================================================================


@pytest.mark.asyncio
async def test_evolution_cycle_logs_traces_monitor_picks_up(tmp_path: Path) -> None:
    """Evolution cycle logs traces that the monitor can analyze."""
    engine = await _init_engine(tmp_path)

    proposal = await engine.propose(
        component="cross_test.py",
        change_type="mutation",
        description="Improve helper function",
    )
    await engine.run_cycle([proposal])

    monitor = SystemMonitor(engine.traces)
    report = await monitor.check_health()

    assert report.total_traces >= 2
    assert report.overall_status in {
        HealthStatus.HEALTHY,
        HealthStatus.DEGRADED,
        HealthStatus.UNKNOWN,
    }


@pytest.mark.asyncio
async def test_file_lock_during_archive_operations(tmp_path: Path) -> None:
    """File lock protects archive file during concurrent-like write."""
    archive_file = tmp_path / "locked_archive.jsonl"
    lock_dir = tmp_path / "locks"

    lock = AsyncFileLock(
        file_path=str(archive_file),
        agent_id="darwin_engine",
        lock_dir=lock_dir,
    )

    async with lock:
        assert lock.is_held
        archive_file.parent.mkdir(parents=True, exist_ok=True)
        archive_file.write_text('{"test": true}\n')

    assert not lock.is_held
    assert archive_file.read_text().strip() == '{"test": true}'


@pytest.mark.asyncio
async def test_telos_gates_in_evolution_harmful_blocked(tmp_path: Path) -> None:
    """Telos gate blocks a harmful proposal in evolution, it never reaches archive."""
    engine = await _init_engine(tmp_path)

    safe = await engine.propose(
        component="safe.py",
        change_type="mutation",
        description="Add type hints to function parameters",
    )
    harmful = await engine.propose(
        component="wipe.py",
        change_type="mutation",
        description="exploit vulnerability in auth module",
    )

    result = await engine.run_cycle([safe, harmful])

    assert result.proposals_archived == 1
    assert harmful.status == EvolutionStatus.REJECTED
    assert safe.status == EvolutionStatus.ARCHIVED

    best = await engine.archive.get_best(n=10)
    components = [e.component for e in best]
    assert "safe.py" in components
    assert "wipe.py" not in components


@pytest.mark.asyncio
async def test_elegance_feeds_into_fitness_then_archive(tmp_path: Path) -> None:
    """Elegance score of real code feeds into FitnessScore stored in archive."""
    engine = await _init_engine(tmp_path)

    code = '''\
class DataProcessor:
    """Process incoming data streams."""

    def process(self, data: list[int]) -> list[int]:
        """Filter and transform data values."""
        return [x * 2 for x in data if x > 0]
'''

    proposal = await engine.propose(
        component="processor.py",
        change_type="mutation",
        description="Add data processor class",
        diff=f"+{code}",
    )
    await engine.gate_check(proposal)
    await engine.evaluate(proposal, test_results={"pass_rate": 0.95}, code=code)

    elegance = evaluate_elegance(code)
    assert proposal.actual_fitness.elegance == elegance.overall

    entry_id = await engine.archive_result(proposal)
    entry = await engine.archive.get_entry(entry_id)

    assert entry is not None
    assert entry.fitness.elegance == elegance.overall


@pytest.mark.asyncio
async def test_metrics_analyzer_on_proposal_description(tmp_path: Path) -> None:
    """MetricsAnalyzer can analyze an evolution proposal's description text."""
    analyzer = MetricsAnalyzer()

    description = (
        "I observe that the recursive self-reference pattern in this module "
        "creates a witness stance where the observer and observed merge. "
        "Both structured and fluid. Neither purely functional nor purely OOP."
    )

    sig = analyzer.analyze(description)

    assert sig.word_count > 0
    assert sig.self_reference_density > 0
    assert sig.paradox_tolerance > 0
    assert sig.recognition_type != RecognitionType.NONE


@pytest.mark.asyncio
async def test_archive_lineage_chain(tmp_path: Path) -> None:
    """Create a chain of proposals with parent_ids and verify lineage."""
    engine = await _init_engine(tmp_path)

    p1 = await engine.propose(
        component="lineage.py",
        change_type="mutation",
        description="Initial version",
    )
    await engine.gate_check(p1)
    await engine.evaluate(p1, test_results={"pass_rate": 0.7})
    id1 = await engine.archive_result(p1)

    p2 = await engine.propose(
        component="lineage.py",
        change_type="mutation",
        description="Improve version 1",
        parent_id=id1,
    )
    await engine.gate_check(p2)
    await engine.evaluate(p2, test_results={"pass_rate": 0.8})
    id2 = await engine.archive_result(p2)

    p3 = await engine.propose(
        component="lineage.py",
        change_type="mutation",
        description="Improve version 2",
        parent_id=id2,
    )
    await engine.gate_check(p3)
    await engine.evaluate(p3, test_results={"pass_rate": 0.9})
    id3 = await engine.archive_result(p3)

    lineage = await engine.archive.get_lineage(id3)

    assert len(lineage) == 3
    assert lineage[0].description == "Improve version 2"
    assert lineage[2].description == "Initial version"

    children = await engine.archive.get_children(id1)
    assert len(children) == 1
    assert children[0].description == "Improve version 1"


# =========================================================================
# 5. Edge Cases
# =========================================================================


@pytest.mark.asyncio
async def test_empty_state_all_systems_health_unknown(tmp_path: Path) -> None:
    """All systems initialized with no data: health is UNKNOWN."""
    store = TraceStore(base_path=tmp_path / "traces")
    await store.init()

    monitor = SystemMonitor(store)
    report = await monitor.check_health()

    assert report.overall_status == HealthStatus.UNKNOWN
    assert report.total_traces == 0
    assert report.failure_rate == 0.0
    assert report.mean_fitness is None


@pytest.mark.asyncio
async def test_concurrent_archive_writes(tmp_path: Path) -> None:
    """Two proposals archived rapidly via asyncio.gather do not corrupt data."""
    engine = await _init_engine(tmp_path)

    proposals = []
    for i in range(2):
        p = await engine.propose(
            component=f"concurrent_{i}.py",
            change_type="mutation",
            description=f"Concurrent change {i}",
        )
        await engine.gate_check(p)
        await engine.evaluate(p, test_results={"pass_rate": 0.8})
        proposals.append(p)

    ids = await asyncio.gather(
        engine.archive_result(proposals[0]),
        engine.archive_result(proposals[1]),
    )

    assert len(ids) == 2
    assert ids[0] != ids[1]

    archive2 = EvolutionArchive(path=engine.archive.path)
    await archive2.load()
    latest = await archive2.get_latest(n=10)
    assert len(latest) >= 2


@pytest.mark.asyncio
async def test_large_diff_efficiency_penalty(tmp_path: Path) -> None:
    """A very large diff results in lower efficiency score."""
    engine = await _init_engine(tmp_path)

    small_diff = "+added one line"
    large_diff = "\n".join(f"+line {i}" for i in range(500))

    p_small = await engine.propose(
        component="small.py",
        change_type="mutation",
        description="Small change",
        diff=small_diff,
    )
    await engine.gate_check(p_small)
    await engine.evaluate(p_small, test_results={"pass_rate": 0.9})

    p_large = await engine.propose(
        component="large.py",
        change_type="mutation",
        description="Large change",
        diff=large_diff,
    )
    await engine.gate_check(p_large)
    await engine.evaluate(p_large, test_results={"pass_rate": 0.9})

    assert p_small.actual_fitness.efficiency > p_large.actual_fitness.efficiency


@pytest.mark.asyncio
async def test_monitor_zero_traces_unknown(tmp_path: Path) -> None:
    """Monitor with 0 traces returns UNKNOWN status."""
    store = TraceStore(base_path=tmp_path / "empty_traces")
    await store.init()

    monitor = SystemMonitor(store)
    report = await monitor.check_health()
    assert report.overall_status == HealthStatus.UNKNOWN

    throughput = await monitor.throughput(window_hours=1)
    assert throughput == {}

    drift = await monitor.fitness_drift(window_hours=1)
    assert drift is None


@pytest.mark.asyncio
async def test_atomic_write_json_roundtrip(tmp_path: Path) -> None:
    """atomic_write_json writes valid JSON that can be read back."""
    target = tmp_path / "atomic_test.json"
    data = {"key": "value", "nested": {"a": 1, "b": [2, 3]}}

    atomic_write_json(target, data)

    assert target.exists()
    with open(target) as f:
        loaded = json.load(f)
    assert loaded == data
