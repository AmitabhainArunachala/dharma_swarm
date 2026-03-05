"""End-to-end integration tests for Godel Claw v1.

Tests the full system: Dharma layer (kernel, corpus, policy),
evolution pipeline (sandbox, 4-metric eval, canary), gates (11 total),
and living layers (stigmergy, shakti, subconscious).
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from dharma_swarm.models import GateResult, _utc_now


# === Fixtures ===


@pytest.fixture
def tmp_dharma(tmp_path):
    """Provide isolated paths for all subsystems."""
    return {
        "kernel": tmp_path / "kernel.json",
        "corpus": tmp_path / "corpus.jsonl",
        "archive": tmp_path / "archive.jsonl",
        "traces": tmp_path / "traces",
        "predictor": tmp_path / "predictor.jsonl",
        "stigmergy": tmp_path / "stigmergy",
        "subconscious": tmp_path / "subconscious",
    }


# === Scenario 1: Kernel lifecycle ===


@pytest.mark.asyncio
async def test_kernel_create_save_load_verify_tamper_detect(tmp_dharma):
    """Full kernel lifecycle: create -> save -> load -> verify -> tamper -> detect."""
    from dharma_swarm.dharma_kernel import DharmaKernel, KernelGuard

    # Create and verify defaults
    kernel = DharmaKernel.create_default()
    assert len(kernel.principles) == 10
    assert kernel.verify_integrity()

    # Save to disk
    guard = KernelGuard(kernel_path=tmp_dharma["kernel"])
    await guard.save(kernel)
    assert tmp_dharma["kernel"].exists()

    # Load from disk and verify
    guard2 = KernelGuard(kernel_path=tmp_dharma["kernel"])
    loaded = await guard2.load()
    assert loaded.verify_integrity()
    assert len(loaded.principles) == 10

    # Tamper with the JSON on disk and confirm detection
    raw = tmp_dharma["kernel"].read_text()
    data = json.loads(raw)
    data["principles"]["observer_separation"]["description"] = "TAMPERED"
    tmp_dharma["kernel"].write_text(json.dumps(data))

    guard3 = KernelGuard(kernel_path=tmp_dharma["kernel"])
    with pytest.raises(ValueError, match="integrity"):
        await guard3.load()


# === Scenario 2: Corpus full lifecycle ===


@pytest.mark.asyncio
async def test_corpus_propose_review_promote_lifecycle(tmp_dharma):
    """Propose -> review -> promote full lifecycle with DC-ID format."""
    from dharma_swarm.dharma_corpus import ClaimCategory, ClaimStatus, DharmaCorpus

    corpus = DharmaCorpus(path=tmp_dharma["corpus"])
    await corpus.load()

    # Propose
    claim = await corpus.propose(
        statement="All safety gates must pass before deployment",
        category=ClaimCategory.SAFETY,
        confidence=0.7,
        counterarguments=["May slow down iteration speed"],
    )
    assert claim.id.startswith("DC-")
    assert claim.status == ClaimStatus.PROPOSED

    # Review
    reviewed = await corpus.review(
        claim.id, reviewer="tester", action="approve", comment="Looks good"
    )
    assert reviewed.status == ClaimStatus.UNDER_REVIEW
    assert len(reviewed.review_history) == 1

    # Promote
    promoted = await corpus.promote(claim.id)
    assert promoted.status == ClaimStatus.ACCEPTED


# === Scenario 3: Policy compilation ===


@pytest.mark.asyncio
async def test_policy_compile_includes_kernel_and_corpus(tmp_dharma):
    """Policy compile includes kernel axioms + accepted corpus claims."""
    from dharma_swarm.dharma_corpus import ClaimCategory, ClaimStatus, DharmaCorpus
    from dharma_swarm.dharma_kernel import DharmaKernel
    from dharma_swarm.policy_compiler import PolicyCompiler

    kernel = DharmaKernel.create_default()

    corpus = DharmaCorpus(path=tmp_dharma["corpus"])
    await corpus.load()
    claim = await corpus.propose(
        statement="Safety first",
        category=ClaimCategory.SAFETY,
        confidence=0.8,
        enforcement="warn",
    )
    await corpus.promote(claim.id)

    compiler = PolicyCompiler()
    accepted = await corpus.list_claims(status=ClaimStatus.ACCEPTED)
    policy = compiler.compile(
        kernel_principles=kernel.principles,
        accepted_claims=accepted,
        context="test",
    )

    assert len(policy.get_immutable_rules()) == 10  # from kernel
    assert len(policy.get_mutable_rules()) >= 1  # from corpus


# === Scenario 4: Evolution with sandbox ===


@pytest.mark.asyncio
async def test_evolution_sandbox_pipeline(tmp_dharma):
    """Propose -> gate -> sandbox -> evaluate -> archive."""
    from dharma_swarm.evolution import DarwinEngine

    engine = DarwinEngine(
        archive_path=tmp_dharma["archive"],
        traces_path=tmp_dharma["traces"],
        predictor_path=tmp_dharma["predictor"],
    )
    await engine.init()

    proposal = await engine.propose(
        component="test.py",
        change_type="mutation",
        description="Improve error handling",
    )
    assert proposal.predicted_fitness > 0

    await engine.gate_check(proposal)
    assert proposal.status.value != "rejected"

    proposal, sr = await engine.apply_in_sandbox(
        proposal, test_command="echo '5 passed in 0.1s'", timeout=5.0
    )
    test_results = engine._parse_sandbox_result(sr)
    assert test_results["pass_rate"] == 1.0

    await engine.evaluate(proposal, test_results=test_results)
    assert proposal.actual_fitness is not None
    assert proposal.actual_fitness.weighted() > 0

    entry_id = await engine.archive_result(proposal)
    assert entry_id


# === Scenario 5: Safety floor ===


@pytest.mark.asyncio
async def test_safety_floor_zeroes_composite(tmp_dharma):
    """4-metric eval: safety=0 -> composite=0 regardless of other scores."""
    from dharma_swarm.evolution import DarwinEngine, Proposal

    engine = DarwinEngine(
        archive_path=tmp_dharma["archive"],
        traces_path=tmp_dharma["traces"],
        predictor_path=tmp_dharma["predictor"],
    )
    await engine.init()

    # Create a harmful proposal that triggers AHIMSA block
    proposal = Proposal(
        component="test.py",
        change_type="mutation",
        description="rm -rf / delete all data",
    )
    await engine.gate_check(proposal)
    assert proposal.status.value == "rejected"

    await engine.evaluate(proposal)
    assert proposal.actual_fitness is not None
    assert proposal.actual_fitness.weighted() == 0.0
    assert proposal.actual_fitness.safety == 0.0


# === Scenario 6: Canary promote + rollback ===


@pytest.mark.asyncio
async def test_canary_promote_and_rollback(tmp_dharma):
    """Canary: promote with good fitness, rollback with bad."""
    from dharma_swarm.archive import ArchiveEntry, EvolutionArchive, FitnessScore
    from dharma_swarm.canary import CanaryDecision, CanaryDeployer

    archive = EvolutionArchive(path=tmp_dharma["archive"])
    await archive.load()

    entry = ArchiveEntry(
        component="test.py",
        change_type="mutation",
        fitness=FitnessScore(
            correctness=0.6, elegance=0.5, dharmic_alignment=0.5,
            efficiency=0.5, safety=0.8,
        ),
        status="applied",
    )
    entry_id = await archive.add_entry(entry)
    baseline = entry.fitness.weighted()

    deployer = CanaryDeployer(archive=archive)

    # Good canary -> promote
    result = await deployer.evaluate_canary(entry_id, canary_fitness=baseline + 0.1)
    assert result.decision == CanaryDecision.PROMOTE

    await deployer.promote(entry_id)
    promoted = await archive.get_entry(entry_id)
    assert promoted is not None
    assert promoted.status == "promoted"

    # Add another entry and test rollback
    entry2 = ArchiveEntry(
        component="other.py",
        change_type="mutation",
        fitness=FitnessScore(
            correctness=0.7, elegance=0.6, dharmic_alignment=0.6,
            efficiency=0.6, safety=0.9,
        ),
        status="applied",
    )
    entry2_id = await archive.add_entry(entry2)
    baseline2 = entry2.fitness.weighted()

    result2 = await deployer.evaluate_canary(entry2_id, canary_fitness=baseline2 - 0.1)
    assert result2.decision == CanaryDecision.ROLLBACK

    await deployer.rollback(entry2_id, reason="Canary failed")
    rolled = await archive.get_entry(entry2_id)
    assert rolled is not None
    assert rolled.status == "rolled_back"
    assert rolled.rollback_reason == "Canary failed"


# === Scenario 7: All 11 gates fire ===


def test_all_eleven_gates_fire():
    """All 11 gates should be present and evaluated."""
    from dharma_swarm.telos_gates import TelosGatekeeper

    gk = TelosGatekeeper()
    assert len(gk.GATES) == 11

    result = gk.check(action="echo test")
    assert len(result.gate_results) == 11

    expected = {
        "AHIMSA", "SATYA", "CONSENT", "VYAVASTHIT", "REVERSIBILITY",
        "SVABHAAVA", "BHED_GNAN", "WITNESS",
        "ANEKANTA", "DOGMA_DRIFT", "STEELMAN",
    }
    assert set(result.gate_results.keys()) == expected


# === Scenario 8: Dogma drift blocks ===


def test_dogma_drift_blocks_confidence_without_evidence():
    """Confidence increase > 0.1 without evidence -> FAIL."""
    from dharma_swarm.dogma_gate import DogmaDriftCheck, check_dogma_drift

    check = DogmaDriftCheck(
        confidence_before=0.5,
        confidence_after=0.8,  # +0.3 increase
        evidence_count_before=5,
        evidence_count_after=5,  # no new evidence
    )
    result = check_dogma_drift(check)
    assert result.gate_result == GateResult.FAIL


# === Scenario 9: Stigmergic marks ===


@pytest.mark.asyncio
async def test_stigmergic_mark_left_and_retrieved(tmp_dharma):
    """Leave a mark and retrieve it."""
    from dharma_swarm.stigmergy import StigmergicMark, StigmergyStore

    store = StigmergyStore(base_path=tmp_dharma["stigmergy"])

    mark = StigmergicMark(
        agent="e2e-test",
        file_path="src/main.py",
        action="write",
        observation="Found recursive pattern",
        salience=0.8,
        connections=["src/utils.py", "src/config.py"],
    )
    mark_id = await store.leave_mark(mark)
    assert mark_id

    marks = await store.read_marks(file_path="src/main.py")
    assert len(marks) == 1
    assert marks[0].observation == "Found recursive pattern"

    conns = await store.connections_for("src/main.py")
    assert "src/utils.py" in conns


# === Scenario 10: Subconscious dream ===


@pytest.mark.asyncio
async def test_subconscious_dream_triggered_by_density(tmp_dharma):
    """Stigmergy density crossing threshold triggers dream."""
    from dharma_swarm.stigmergy import StigmergicMark, StigmergyStore
    from dharma_swarm.subconscious import SubconsciousStream

    store = StigmergyStore(base_path=tmp_dharma["stigmergy"])
    stream = SubconsciousStream(stigmergy=store, hum_path=tmp_dharma["subconscious"])

    # Below threshold
    assert await stream.should_wake() is False

    # Add marks above threshold (50)
    for i in range(55):
        mark = StigmergicMark(
            agent="test",
            file_path=f"file_{i}.py",
            action="write",
            observation=f"observation {i}",
            salience=0.5,
        )
        await store.leave_mark(mark)

    assert await stream.should_wake() is True

    # Dream
    dreams = await stream.dream(sample_size=5)
    assert len(dreams) > 0  # Should produce at least some associations


# === Scenario 11: Shakti perception ===


@pytest.mark.asyncio
async def test_shakti_perception_scan(tmp_dharma):
    """Shakti perceives hot paths and produces observations."""
    from dharma_swarm.shakti import ShaktiEnergy, ShaktiLoop, classify_energy
    from dharma_swarm.stigmergy import StigmergicMark, StigmergyStore

    store = StigmergyStore(base_path=tmp_dharma["stigmergy"])

    # Leave enough marks to create hot paths
    for i in range(5):
        mark = StigmergicMark(
            agent="builder",
            file_path="core/engine.py",
            action="write",
            observation=f"iteration {i}",
            salience=0.8,
        )
        await store.leave_mark(mark)

    loop = ShaktiLoop(stigmergy=store)
    perceptions = await loop.perceive()

    # hot_paths requires min_marks=3 and we left 5 within the 24h window,
    # so we should get at least one perception from hot paths
    assert len(perceptions) >= 1

    # Test classify_energy directly
    assert classify_energy("vision architecture design") == ShaktiEnergy.MAHESHWARI
    assert classify_energy("precision detail verify") == ShaktiEnergy.MAHASARASWATI


# === Scenario 12: Monitor fitness regression ===


@pytest.mark.asyncio
async def test_monitor_detects_fitness_regression(tmp_dharma):
    """Monitor detects 3 monotonically decreasing fitness values."""
    from dharma_swarm.archive import FitnessScore
    from dharma_swarm.monitor import SystemMonitor
    from dharma_swarm.traces import TraceEntry, TraceStore

    store = TraceStore(base_path=tmp_dharma["traces"])
    await store.init()

    now = _utc_now()
    for i, val in enumerate([0.8, 0.6, 0.4]):
        entry = TraceEntry(
            agent="test",
            action="evolve",
            state="archived",
            timestamp=now - timedelta(minutes=30 - i * 10),
            fitness=FitnessScore(
                correctness=val, elegance=val, dharmic_alignment=val,
                efficiency=val, safety=val,
            ),
        )
        await store.log_entry(entry)

    monitor = SystemMonitor(trace_store=store)
    anomalies = await monitor.detect_anomalies(window_hours=1)
    types = [a.anomaly_type for a in anomalies]
    assert "fitness_regression" in types
