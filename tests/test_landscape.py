"""Tests for Darwin landscape probing."""

import pytest

from dharma_swarm.archive import ArchiveEntry, FitnessScore
from dharma_swarm.evolution import DarwinEngine, EvolutionStatus, Proposal
from dharma_swarm.landscape import BasinType, FitnessLandscapeMapper


@pytest.mark.asyncio
async def test_ascending_basin_detected():
    mapper = FitnessLandscapeMapper(DarwinEngine(), n_samples=5)
    parent = ArchiveEntry(
        component="test.py",
        change_type="mutation",
        description="test",
        fitness=FitnessScore(correctness=0.5, safety=1.0),
    )
    samples = iter([0.7, 0.68, 0.66, 0.69, 0.71])

    async def mock_sample(
        p,
        weights=None,
        workspace=None,
        test_command="python3 -m pytest tests/ -q --tb=short",
        timeout=60.0,
    ):
        del p, weights, workspace, test_command, timeout
        return next(samples)

    mapper._sample_neighbor_fitness = mock_sample
    probe = await mapper.probe_landscape(parent)
    assert probe.basin_type == BasinType.ASCENDING


@pytest.mark.asyncio
async def test_plateau_basin_detected():
    mapper = FitnessLandscapeMapper(
        DarwinEngine(),
        n_samples=5,
        variance_threshold=0.0005,
    )
    parent = ArchiveEntry(
        component="test.py",
        change_type="mutation",
        description="test",
        fitness=FitnessScore(correctness=0.5, safety=1.0),
    )
    parent_score = parent.fitness.weighted()
    samples = iter(
        [
            parent_score + 0.0001,
            parent_score + 0.0002,
            parent_score + 0.0001,
            parent_score + 0.0002,
            parent_score + 0.0001,
        ]
    )

    async def mock_sample(
        p,
        weights=None,
        workspace=None,
        test_command="python3 -m pytest tests/ -q --tb=short",
        timeout=60.0,
    ):
        del p, weights, workspace, test_command, timeout
        return next(samples)

    mapper._sample_neighbor_fitness = mock_sample
    probe = await mapper.probe_landscape(parent)
    assert probe.basin_type == BasinType.PLATEAU


def test_landscape_strategy_mapping():
    assert FitnessLandscapeMapper.get_adaptive_strategy(BasinType.ASCENDING) == "exploit"
    assert FitnessLandscapeMapper.get_adaptive_strategy(BasinType.PLATEAU) == "explore"
    assert FitnessLandscapeMapper.get_adaptive_strategy(BasinType.LOCAL_OPTIMUM) == "restart"


@pytest.mark.asyncio
async def test_neighbor_sampling_uses_darwin_pipeline(monkeypatch):
    darwin = DarwinEngine()
    mapper = FitnessLandscapeMapper(darwin)
    parent = ArchiveEntry(
        id="parent-1",
        component="sample.py",
        change_type="mutation",
        description="seed",
        fitness=FitnessScore(correctness=0.8, safety=1.0),
        diff="+ seed change\n",
        status="applied",
    )
    calls: list[str] = []
    proposal = Proposal(
        component="sample.py",
        change_type="mutation",
        description="probe",
    )

    async def fake_propose(**kwargs):
        calls.append("propose")
        proposal.diff = kwargs["diff"]
        proposal.parent_id = kwargs["parent_id"]
        return proposal

    async def fake_gate_check(candidate):
        calls.append("gate")
        candidate.status = EvolutionStatus.GATED
        candidate.gate_decision = "allow"
        return candidate

    async def fake_evaluate(candidate, test_results=None, **kwargs):
        del kwargs
        calls.append("evaluate")
        candidate.actual_fitness = FitnessScore(
            correctness=float(test_results["pass_rate"]),
            dharmic_alignment=0.8,
            performance=0.5,
            utilization=0.5,
            economic_value=0.5,
            elegance=0.5,
            efficiency=0.9,
            safety=1.0,
        )
        candidate.status = EvolutionStatus.EVALUATED
        return candidate

    monkeypatch.setattr(darwin, "propose", fake_propose)
    monkeypatch.setattr(darwin, "gate_check", fake_gate_check)
    monkeypatch.setattr(darwin, "evaluate", fake_evaluate)

    score = await mapper._sample_neighbor_fitness(parent)

    assert score > 0.0
    assert calls == ["propose", "gate", "evaluate"]
    assert proposal.parent_id == "parent-1"
    assert proposal.diff.startswith("--- a/sample.py")


@pytest.mark.asyncio
async def test_neighbor_sampling_uses_workspace_probe_path(monkeypatch, tmp_path):
    darwin = DarwinEngine(
        archive_path=tmp_path / "archive.jsonl",
        traces_path=tmp_path / "traces",
        predictor_path=tmp_path / "predictor.jsonl",
    )
    await darwin.init()
    mapper = FitnessLandscapeMapper(darwin)
    parent = ArchiveEntry(
        id="parent-2",
        component="sample.py",
        change_type="mutation",
        description="seed",
        fitness=FitnessScore(correctness=0.75, safety=1.0),
        diff="+ seed change\n",
        status="applied",
    )
    calls: list[str] = []
    proposal = Proposal(
        component="sample.py",
        change_type="mutation",
        description="probe",
    )

    async def fake_propose(**kwargs):
        calls.append("propose")
        proposal.diff = kwargs["diff"]
        return proposal

    async def fake_probe_eval(
        candidate,
        *,
        workspace,
        test_command,
        timeout,
    ):
        calls.append("probe_eval")
        assert workspace == tmp_path
        assert test_command == "python3 -c \"print('ok')\""
        assert timeout == pytest.approx(5.0)
        candidate.actual_fitness = FitnessScore(
            correctness=0.9,
            dharmic_alignment=0.8,
            performance=0.5,
            utilization=0.5,
            economic_value=0.5,
            elegance=0.5,
            efficiency=0.9,
            safety=1.0,
        )
        candidate.status = EvolutionStatus.EVALUATED
        return candidate

    monkeypatch.setattr(darwin, "propose", fake_propose)
    monkeypatch.setattr(darwin, "evaluate_probe_proposal", fake_probe_eval)

    score = await mapper._sample_neighbor_fitness(
        parent,
        workspace=tmp_path,
        test_command="python3 -c \"print('ok')\"",
        timeout=5.0,
    )

    assert score > 0.0
    assert calls == ["propose", "probe_eval"]
    assert proposal.diff.startswith("--- a/sample.py")


@pytest.mark.asyncio
async def test_workspace_probe_uses_snapshot_and_preserves_source(tmp_path):
    darwin = DarwinEngine(
        archive_path=tmp_path / "archive.jsonl",
        traces_path=tmp_path / "traces",
        predictor_path=tmp_path / "predictor.jsonl",
    )
    await darwin.init()
    mapper = FitnessLandscapeMapper(darwin, n_samples=2)

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sample = workspace / "sample.py"
    original = "def value():\n    return 1\n"
    sample.write_text(original, encoding="utf-8")

    parent = ArchiveEntry(
        id="parent-3",
        component="sample.py",
        change_type="mutation",
        description="seed",
        fitness=FitnessScore(correctness=0.8, safety=1.0),
        diff="+ seed change\n",
        status="applied",
    )

    probe = await mapper.probe_landscape(
        parent,
        workspace=workspace,
        test_command="python3 -c \"print('ok')\"",
        timeout=5.0,
    )

    assert len(probe.neighbor_fitness) == 2
    assert probe.parent_component == "sample.py"
    assert sample.read_text(encoding="utf-8") == original
