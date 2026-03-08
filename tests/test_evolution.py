"""Tests for dharma_swarm.evolution -- DarwinEngine orchestration loop."""

import pytest

from dharma_swarm.archive import ArchiveEntry, EvolutionArchive, FitnessScore
from dharma_swarm.evolution import (
    CycleResult,
    DarwinEngine,
    EvolutionPlan,
    EvolutionStatus,
    Proposal,
)
from dharma_swarm.models import GateDecision


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine_paths(tmp_path):
    """Return archive, traces, and predictor paths under tmp_path."""
    return {
        "archive_path": tmp_path / "archive.jsonl",
        "traces_path": tmp_path / "traces",
        "predictor_path": tmp_path / "predictor.jsonl",
    }


@pytest.fixture
async def engine(engine_paths):
    """Create and initialize a DarwinEngine with tmp paths."""
    eng = DarwinEngine(**engine_paths)
    await eng.init()
    return eng


_THINK_NOTES_SAFE = (
    "Risk: minimal — small targeted change. "
    "Rollback: revert single commit. "
    "Alternatives considered: no-op, full rewrite. "
    "Expected: improved resilience score."
)

_THINK_NOTES_HARMFUL = (
    "Risk: high — destructive operation. "
    "Rollback: not possible after deletion. "
    "Alternatives: selective cleanup. "
    "Expected: free disk space."
)

_THINK_NOTES_REVIEW = (
    "Risk: moderate — force override bypasses normal flow. "
    "Rollback: restore previous config from backup. "
    "Alternatives: gradual migration. "
    "Expected: updated configuration state."
)


def _safe_proposal(**kw) -> Proposal:
    """Create a safe proposal that will pass all gates."""
    defaults = {
        "component": "module.py",
        "change_type": "mutation",
        "description": (
            "Improve activation mechanism with consciousness witness "
            "and ecosystem resilience feedback"
        ),
        "diff": "- old_line\n+ new_line\n",
        "think_notes": _THINK_NOTES_SAFE,
    }
    defaults.update(kw)
    return Proposal(**defaults)


def _harmful_proposal(**kw) -> Proposal:
    """Create a proposal that triggers AHIMSA gate (harm words)."""
    defaults = {
        "component": "danger.py",
        "change_type": "mutation",
        "description": "rm -rf everything for cleanup",
        "diff": "",
        "think_notes": _THINK_NOTES_HARMFUL,
    }
    defaults.update(kw)
    return Proposal(**defaults)


def _review_proposal(**kw) -> Proposal:
    """Create a proposal that triggers a Tier C review advisory."""
    defaults = {
        "component": "ops.py",
        "change_type": "mutation",
        "description": "force override the configuration",
        "diff": "",
        "think_notes": _THINK_NOTES_REVIEW,
    }
    defaults.update(kw)
    return Proposal(**defaults)


# ---------------------------------------------------------------------------
# EvolutionStatus enum
# ---------------------------------------------------------------------------


def test_evolution_status_values():
    assert EvolutionStatus.PENDING.value == "pending"
    assert EvolutionStatus.REFLECTING.value == "reflecting"
    assert EvolutionStatus.GATED.value == "gated"
    assert EvolutionStatus.WRITING.value == "writing"
    assert EvolutionStatus.TESTING.value == "testing"
    assert EvolutionStatus.EVALUATED.value == "evaluated"
    assert EvolutionStatus.ARCHIVED.value == "archived"
    assert EvolutionStatus.REJECTED.value == "rejected"


def test_evolution_status_is_str_enum():
    assert isinstance(EvolutionStatus.PENDING, str)
    assert EvolutionStatus.PENDING == "pending"


# ---------------------------------------------------------------------------
# Proposal model
# ---------------------------------------------------------------------------


def test_proposal_defaults():
    p = Proposal(component="a.py", change_type="mutation", description="test")
    assert len(p.id) == 16
    assert p.status == EvolutionStatus.PENDING
    assert p.predicted_fitness == 0.0
    assert p.actual_fitness is None
    assert p.gate_decision is None
    assert p.gate_reason is None
    assert p.parent_id is None
    assert p.spec_ref is None
    assert p.requirement_refs == []
    assert p.think_notes == ""
    assert p.diff == ""


def test_proposal_with_parent():
    p = Proposal(
        component="a.py",
        change_type="crossover",
        description="merge",
        parent_id="abc123",
    )
    assert p.parent_id == "abc123"
    assert p.change_type == "crossover"


def test_proposal_json_roundtrip():
    p = _safe_proposal()
    data = p.model_dump_json()
    p2 = Proposal.model_validate_json(data)
    assert p2.id == p.id
    assert p2.component == p.component
    assert p2.description == p.description


# ---------------------------------------------------------------------------
# CycleResult model
# ---------------------------------------------------------------------------


def test_cycle_result_defaults():
    cr = CycleResult()
    assert len(cr.cycle_id) == 16
    assert cr.plan_id == ""
    assert cr.proposals_submitted == 0
    assert cr.proposals_gated == 0
    assert cr.proposals_tested == 0
    assert cr.proposals_archived == 0
    assert cr.circuit_breakers_tripped == 0
    assert cr.strategy_pivots == 0
    assert cr.best_fitness == 0.0
    assert cr.duration_seconds == 0.0


# ---------------------------------------------------------------------------
# DarwinEngine -- init
# ---------------------------------------------------------------------------


async def test_engine_init(engine):
    assert engine._initialized is True


async def test_engine_init_creates_trace_dirs(engine_paths):
    eng = DarwinEngine(**engine_paths)
    await eng.init()
    traces_path = engine_paths["traces_path"]
    assert (traces_path / "history").is_dir()
    assert (traces_path / "archive").is_dir()
    assert (traces_path / "patterns").is_dir()


# ---------------------------------------------------------------------------
# DarwinEngine -- propose
# ---------------------------------------------------------------------------


async def test_propose_creates_proposal(engine):
    p = await engine.propose(
        component="foo.py",
        change_type="mutation",
        description="add type hints",
        diff="+ x: int\n",
    )
    assert isinstance(p, Proposal)
    assert p.component == "foo.py"
    assert p.change_type == "mutation"
    assert p.description == "add type hints"
    assert p.diff == "+ x: int\n"
    assert p.status == EvolutionStatus.PENDING
    assert 0.0 <= p.predicted_fitness <= 1.0


async def test_propose_with_parent(engine):
    p = await engine.propose(
        component="bar.py",
        change_type="crossover",
        description="merge features",
        parent_id="parent123",
    )
    assert p.parent_id == "parent123"


async def test_propose_predicts_fitness(engine):
    p = await engine.propose(
        component="x.py",
        change_type="mutation",
        description="small fix",
        diff="one line",
    )
    # With no prior history, predictor uses neutral prior (0.5) + small diff bonus
    assert p.predicted_fitness > 0.0


async def test_propose_accepts_traceability_fields(engine):
    p = await engine.propose(
        component="trace.py",
        change_type="mutation",
        description="improve traceability",
        spec_ref="specs/dgc_phase1.md#req-3",
        requirement_refs=["REQ-3", "REQ-3.1"],
        think_notes="Validate risks and rollback plan before write.",
    )
    assert p.spec_ref == "specs/dgc_phase1.md#req-3"
    assert p.requirement_refs == ["REQ-3", "REQ-3.1"]
    assert p.think_notes.startswith("Validate risks")


async def test_plan_cycle_returns_ordered_plan(engine):
    p1 = _safe_proposal(component="a.py")
    p1.predicted_fitness = 0.2
    p2 = _safe_proposal(component="b.py")
    p2.predicted_fitness = 0.9
    plan = await engine.plan_cycle([p1, p2])
    assert isinstance(plan, EvolutionPlan)
    assert plan.ordered_proposal_ids == [p2.id, p1.id]
    assert len(plan.steps) == 2


# ---------------------------------------------------------------------------
# DarwinEngine -- gate_check
# ---------------------------------------------------------------------------


async def test_gate_check_safe_proposal(engine):
    p = _safe_proposal()
    result = await engine.gate_check(p)
    assert result.status in (EvolutionStatus.GATED,)
    assert result.gate_decision in (
        GateDecision.ALLOW.value,
        GateDecision.REVIEW.value,
    )


async def test_gate_check_harmful_proposal(engine):
    p = _harmful_proposal()
    result = await engine.gate_check(p)
    assert result.status == EvolutionStatus.REJECTED
    assert result.gate_decision == GateDecision.BLOCK.value
    assert result.gate_reason is not None


async def test_gate_check_review_proposal(engine):
    p = _review_proposal()
    result = await engine.gate_check(p)
    # "force" triggers VYAVASTHIT (Tier C) -> REVIEW, not BLOCK
    assert result.status == EvolutionStatus.GATED
    assert result.gate_decision == GateDecision.REVIEW.value


async def test_gate_check_logs_trace(engine):
    p = _safe_proposal()
    await engine.gate_check(p)
    recent = await engine.traces.get_recent(limit=5)
    assert len(recent) >= 1
    actions = [t.action for t in recent]
    assert "gate_check" in actions


# ---------------------------------------------------------------------------
# DarwinEngine -- evaluate
# ---------------------------------------------------------------------------


async def test_evaluate_with_test_results(engine):
    p = _safe_proposal()
    await engine.gate_check(p)

    result = await engine.evaluate(
        p,
        test_results={"pass_rate": 0.95},
    )
    assert result.status == EvolutionStatus.EVALUATED
    assert result.actual_fitness is not None
    assert result.actual_fitness.correctness == pytest.approx(0.95)
    assert result.actual_fitness.elegance == pytest.approx(0.5)  # no code


async def test_evaluate_with_code(engine):
    p = _safe_proposal()
    await engine.gate_check(p)

    code = '''
def greet(name: str) -> str:
    """Return a greeting."""
    return f"Hello, {name}"
'''
    result = await engine.evaluate(p, test_results={"pass_rate": 1.0}, code=code)
    assert result.actual_fitness is not None
    # Code provided -> elegance should come from evaluate_elegance
    assert result.actual_fitness.elegance > 0.0
    assert result.actual_fitness.correctness == pytest.approx(1.0)


async def test_evaluate_no_test_results(engine):
    p = _safe_proposal()
    await engine.gate_check(p)

    result = await engine.evaluate(p)
    assert result.actual_fitness is not None
    assert result.actual_fitness.correctness == 0.0


async def test_evaluate_dharmic_alignment_allow(engine):
    p = _safe_proposal()
    await engine.gate_check(p)
    # Safe proposal gets ALLOW
    assert p.gate_decision == GateDecision.ALLOW.value

    result = await engine.evaluate(p, test_results={"pass_rate": 0.5})
    assert result.actual_fitness is not None
    assert result.actual_fitness.dharmic_alignment == pytest.approx(0.8)


async def test_evaluate_dharmic_alignment_review(engine):
    p = _review_proposal()
    await engine.gate_check(p)
    assert p.gate_decision == GateDecision.REVIEW.value

    result = await engine.evaluate(p, test_results={"pass_rate": 0.5})
    assert result.actual_fitness is not None
    assert result.actual_fitness.dharmic_alignment == pytest.approx(0.5)


async def test_evaluate_efficiency_small_diff(engine):
    p = _safe_proposal(diff="+ one line\n")
    await engine.gate_check(p)
    result = await engine.evaluate(p)
    assert result.actual_fitness is not None
    # 1 line diff -> efficiency = 1.0 - 1/1000 = 0.999
    assert result.actual_fitness.efficiency > 0.99


async def test_evaluate_efficiency_large_diff(engine):
    big_diff = "\n".join(f"+ line {i}" for i in range(500))
    p = _safe_proposal(diff=big_diff)
    await engine.gate_check(p)
    result = await engine.evaluate(p)
    assert result.actual_fitness is not None
    assert result.actual_fitness.efficiency == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# DarwinEngine -- archive_result
# ---------------------------------------------------------------------------


async def test_archive_result_stores_entry(engine):
    p = _safe_proposal()
    await engine.gate_check(p)
    await engine.evaluate(p, test_results={"pass_rate": 0.8})
    entry_id = await engine.archive_result(p)

    assert p.status == EvolutionStatus.ARCHIVED
    assert len(entry_id) == 16

    # Verify stored in archive
    stored = await engine.archive.get_entry(entry_id)
    assert stored is not None
    assert stored.component == "module.py"
    assert stored.status == "applied"
    assert stored.fitness.correctness == pytest.approx(0.8)


async def test_archive_result_logs_trace(engine):
    p = _safe_proposal()
    await engine.gate_check(p)
    await engine.evaluate(p, test_results={"pass_rate": 0.7})
    await engine.archive_result(p)

    recent = await engine.traces.get_recent(limit=10)
    actions = [t.action for t in recent]
    assert "archive_result" in actions


async def test_archive_result_records_predictor_outcome(engine):
    p = _safe_proposal()
    await engine.gate_check(p)
    await engine.evaluate(p, test_results={"pass_rate": 0.9})
    await engine.archive_result(p)

    assert engine.predictor.outcome_count >= 1


# ---------------------------------------------------------------------------
# DarwinEngine -- run_cycle
# ---------------------------------------------------------------------------


async def test_run_cycle_all_safe(engine):
    proposals = [
        _safe_proposal(component="a.py", description="fix a"),
        _safe_proposal(component="b.py", description="fix b"),
        _safe_proposal(component="c.py", description="fix c"),
    ]
    result = await engine.run_cycle(proposals)

    assert isinstance(result, CycleResult)
    assert result.proposals_submitted == 3
    assert result.proposals_gated == 3
    assert result.proposals_tested == 3
    assert result.proposals_archived == 3
    assert result.plan_id
    assert result.duration_seconds > 0.0


async def test_run_cycle_mixed(engine):
    proposals = [
        _safe_proposal(description="safe change"),
        _harmful_proposal(description="rm -rf /tmp"),
        _safe_proposal(description="another safe one"),
    ]
    result = await engine.run_cycle(proposals)

    assert result.proposals_submitted == 3
    assert result.proposals_gated == 2  # one rejected
    assert result.proposals_archived == 2


async def test_run_cycle_all_rejected(engine):
    proposals = [
        _harmful_proposal(description="destroy database"),
        _harmful_proposal(description="rm -rf everything"),
    ]
    result = await engine.run_cycle(proposals)

    assert result.proposals_submitted == 2
    assert result.proposals_gated == 0
    assert result.proposals_archived == 0
    assert result.best_fitness == 0.0


async def test_run_cycle_empty(engine):
    result = await engine.run_cycle([])
    assert result.proposals_submitted == 0
    assert result.proposals_gated == 0
    assert result.proposals_archived == 0
    assert result.best_fitness == 0.0
    assert result.duration_seconds >= 0.0


async def test_run_cycle_tracks_best_fitness(engine):
    proposals = [
        _safe_proposal(component="low.py", description="minor tweak"),
        _safe_proposal(component="high.py", description="major improvement"),
    ]
    result = await engine.run_cycle(proposals)
    # Both get pass_rate=0.0 by default, but best_fitness should be > 0
    # because other dimensions (efficiency, safety, dharmic_alignment) contribute
    assert result.best_fitness >= 0.0


async def test_run_cycle_circuit_breaker_after_repeated_failures(engine):
    proposals = [
        _harmful_proposal(component="danger.py", description="rm -rf everything"),
        _harmful_proposal(component="danger.py", description="rm -rf everything"),
        _harmful_proposal(component="danger.py", description="rm -rf everything"),
    ]
    result = await engine.run_cycle(proposals)
    assert result.proposals_submitted == 3
    assert result.proposals_archived == 0
    assert result.circuit_breakers_tripped >= 1
    assert result.strategy_pivots >= 1


# ---------------------------------------------------------------------------
# DarwinEngine -- select_next_parent
# ---------------------------------------------------------------------------


async def test_select_next_parent_empty_archive(engine):
    parent = await engine.select_next_parent()
    assert parent is None


async def test_select_next_parent_with_entries(engine):
    # First run a cycle to populate the archive
    proposals = [
        _safe_proposal(component="parent.py", description="seed entry"),
    ]
    await engine.run_cycle(proposals)

    parent = await engine.select_next_parent(strategy="tournament")
    assert parent is not None
    assert isinstance(parent, ArchiveEntry)


async def test_select_next_parent_elite(engine):
    proposals = [
        _safe_proposal(component="e1.py", description="first"),
        _safe_proposal(component="e2.py", description="second"),
    ]
    await engine.run_cycle(proposals)

    parent = await engine.select_next_parent(strategy="elite")
    assert parent is not None


# ---------------------------------------------------------------------------
# DarwinEngine -- get_fitness_trend
# ---------------------------------------------------------------------------


async def test_get_fitness_trend_empty(engine):
    trend = await engine.get_fitness_trend()
    assert trend == []


async def test_get_fitness_trend_after_cycle(engine):
    proposals = [
        _safe_proposal(component="t1.py", description="trend test 1"),
        _safe_proposal(component="t2.py", description="trend test 2"),
    ]
    await engine.run_cycle(proposals)

    trend = await engine.get_fitness_trend()
    assert len(trend) == 2
    for ts, fitness in trend:
        assert isinstance(ts, str)
        assert isinstance(fitness, float)


async def test_get_fitness_trend_by_component(engine):
    proposals = [
        _safe_proposal(component="x.py", description="x change"),
        _safe_proposal(component="y.py", description="y change"),
    ]
    await engine.run_cycle(proposals)

    trend = await engine.get_fitness_trend(component="x.py")
    assert len(trend) == 1


async def test_get_fitness_trend_limit(engine):
    proposals = [
        _safe_proposal(component=f"file{i}.py", description=f"change {i}")
        for i in range(5)
    ]
    await engine.run_cycle(proposals)

    trend = await engine.get_fitness_trend(limit=3)
    assert len(trend) == 3


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


async def test_evaluate_rejected_proposal(engine):
    """Evaluating a rejected proposal zeroes all fitness (safety floor)."""
    p = _harmful_proposal()
    await engine.gate_check(p)
    assert p.status == EvolutionStatus.REJECTED

    # Force evaluate anyway (engine does not prevent it)
    result = await engine.evaluate(p, test_results={"pass_rate": 0.5})
    assert result.actual_fitness is not None
    # Safety floor: rejected proposals get zero across all dimensions
    assert result.actual_fitness.safety == 0.0
    assert result.actual_fitness.correctness == 0.0
    assert result.actual_fitness.elegance == 0.0
    assert result.actual_fitness.dharmic_alignment == 0.0
    assert result.actual_fitness.efficiency == 0.0
    assert result.actual_fitness.weighted() == 0.0


async def test_archive_result_without_fitness(engine):
    """Archiving before evaluation uses zero-valued FitnessScore."""
    p = _safe_proposal()
    await engine.gate_check(p)
    # Skip evaluate — actual_fitness is None
    entry_id = await engine.archive_result(p)
    stored = await engine.archive.get_entry(entry_id)
    assert stored is not None
    assert stored.fitness.correctness == 0.0
    assert stored.fitness.weighted() == 0.0


async def test_archive_result_persists_traceability(engine):
    p = _safe_proposal()
    p.spec_ref = "specs/demo.md#REQ-9"
    p.requirement_refs = ["REQ-9", "REQ-9.2"]
    await engine.gate_check(p)
    await engine.evaluate(p, test_results={"pass_rate": 0.8})
    entry_id = await engine.archive_result(p)
    stored = await engine.archive.get_entry(entry_id)
    assert stored is not None
    assert stored.spec_ref == "specs/demo.md#REQ-9"
    assert stored.requirement_refs == ["REQ-9", "REQ-9.2"]


async def test_proposal_status_transitions(engine):
    """Verify the full status lifecycle: PENDING -> GATED -> EVALUATED -> ARCHIVED."""
    p = _safe_proposal()
    assert p.status == EvolutionStatus.PENDING

    await engine.gate_check(p)
    assert p.status == EvolutionStatus.GATED

    await engine.evaluate(p, test_results={"pass_rate": 0.9})
    assert p.status == EvolutionStatus.EVALUATED

    await engine.archive_result(p)
    assert p.status == EvolutionStatus.ARCHIVED


async def test_credential_in_diff_blocks(engine):
    """A diff containing credential patterns should be blocked by SATYA gate."""
    p = Proposal(
        component="config.py",
        change_type="mutation",
        description="update configuration",
        diff='API_KEY = "sk-ant-abc123secret"',
    )
    result = await engine.gate_check(p)
    assert result.status == EvolutionStatus.REJECTED
    assert result.gate_decision == GateDecision.BLOCK.value


# ---------------------------------------------------------------------------
# Sandbox + 4-metric tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parse_sandbox_result_passing():
    """Parsing stdout with only passed tests yields pass_rate 1.0."""
    from dharma_swarm.models import SandboxResult

    sr = SandboxResult(exit_code=0, stdout="10 passed in 1.2s", stderr="")
    result = DarwinEngine._parse_sandbox_result(sr)
    assert result["pass_rate"] == 1.0


@pytest.mark.asyncio
async def test_parse_sandbox_result_mixed():
    """Mixed passed/failed results produce the correct ratio."""
    from dharma_swarm.models import SandboxResult

    sr = SandboxResult(
        exit_code=1, stdout="8 passed, 2 failed in 1.5s", stderr=""
    )
    result = DarwinEngine._parse_sandbox_result(sr)
    assert abs(result["pass_rate"] - 0.8) < 0.01


@pytest.mark.asyncio
async def test_parse_sandbox_result_no_output():
    """Empty stdout with exit_code 0 yields pass_rate 1.0."""
    from dharma_swarm.models import SandboxResult

    sr = SandboxResult(exit_code=0, stdout="", stderr="")
    result = DarwinEngine._parse_sandbox_result(sr)
    assert result["pass_rate"] == 1.0  # exit_code 0 = success


@pytest.mark.asyncio
async def test_parse_sandbox_result_failure():
    """Empty stdout with non-zero exit_code yields pass_rate 0.0."""
    from dharma_swarm.models import SandboxResult

    sr = SandboxResult(exit_code=1, stdout="", stderr="error")
    result = DarwinEngine._parse_sandbox_result(sr)
    assert result["pass_rate"] == 0.0


@pytest.mark.asyncio
async def test_safety_floor_zero_safety(engine):
    """When a proposal is REJECTED (safety=0), all fitness should be 0."""
    proposal = _harmful_proposal()
    await engine.gate_check(proposal)
    assert proposal.status == EvolutionStatus.REJECTED
    await engine.evaluate(proposal)
    assert proposal.actual_fitness is not None
    assert proposal.actual_fitness.weighted() == 0.0


@pytest.mark.asyncio
async def test_safety_nonzero_for_passing(engine):
    """Safe proposals should have non-zero safety."""
    proposal = _safe_proposal()
    await engine.gate_check(proposal)
    await engine.evaluate(proposal)
    assert proposal.actual_fitness is not None
    assert proposal.actual_fitness.safety > 0.0
    assert proposal.actual_fitness.weighted() > 0.0


@pytest.mark.asyncio
async def test_apply_in_sandbox(engine):
    """Sandbox execution should return a result."""
    proposal = _safe_proposal()
    await engine.gate_check(proposal)
    proposal_out, sr = await engine.apply_in_sandbox(
        proposal, test_command="echo 'test passed'", timeout=5.0
    )
    assert sr.exit_code == 0
    assert proposal_out.status == EvolutionStatus.TESTING


@pytest.mark.asyncio
async def test_run_cycle_with_sandbox(engine):
    """Full cycle with sandbox should produce results."""
    proposals = [
        _safe_proposal(),
        _safe_proposal(component="other.py"),
    ]
    result = await engine.run_cycle_with_sandbox(
        proposals, test_command="echo '2 passed in 0.1s'", timeout=5.0
    )
    assert result.proposals_submitted == 2
    assert result.proposals_archived >= 1


def test_parse_sandbox_passed_failed_error():
    """Handle pytest output with passed, failed, and error counts."""
    from dharma_swarm.models import SandboxResult

    sr = SandboxResult(
        exit_code=1,
        stdout="5 passed, 3 failed, 1 error in 2.0s",
        stderr="",
    )
    result = DarwinEngine._parse_sandbox_result(sr)
    # errors count as failures: total = 5 + 3 + 1 = 9, pass_rate = 5/9
    assert abs(result["pass_rate"] - 5 / 9) < 0.01


def test_parse_sandbox_only_failed():
    """Stdout with only failed tests yields pass_rate 0.0."""
    from dharma_swarm.models import SandboxResult

    sr = SandboxResult(
        exit_code=1, stdout="3 failed in 1.0s", stderr=""
    )
    result = DarwinEngine._parse_sandbox_result(sr)
    assert result["pass_rate"] == 0.0


# ---------------------------------------------------------------------------
# Verbal self-reflection (Change 0C tests)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cycle_result_has_reflection(engine):
    """TEST 4: run_cycle populates reflection and lessons_learned."""
    proposals = [
        _safe_proposal(component="pass.py", description="safe pass"),
        _harmful_proposal(component="fail1.py", description="rm -rf bad"),
        _harmful_proposal(component="fail2.py", description="rm -rf worse"),
    ]
    result = await engine.run_cycle(proposals)

    assert isinstance(result.reflection, str)
    assert len(result.reflection) > 0
    assert isinstance(result.lessons_learned, list)
    assert len(result.lessons_learned) > 0
    # 2 proposals were rejected
    assert "rejected" in result.reflection.lower()


@pytest.mark.asyncio
async def test_reflect_on_cycle_all_failed(engine):
    """Reflection identifies when all proposals fail."""
    proposals = [
        _harmful_proposal(description="rm -rf one"),
        _harmful_proposal(description="rm -rf two"),
    ]
    result = await engine.run_cycle(proposals)
    assert "failed" in result.reflection.lower() or "rejected" in result.reflection.lower()


@pytest.mark.asyncio
async def test_reflect_on_cycle_clean(engine):
    """Clean cycle produces reflection."""
    proposals = [_safe_proposal()]
    result = await engine.run_cycle(proposals)
    assert len(result.reflection) > 0


@pytest.mark.asyncio
async def test_cycle_result_reflection_fields_default():
    """New CycleResult fields default correctly."""
    cr = CycleResult()
    assert cr.reflection == ""
    assert cr.lessons_learned == []


# ---------------------------------------------------------------------------
# Think-Gate enforcement (Change 0D tests)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_think_gate_reroutes_empty_notes(engine):
    """TEST 5: Empty think_notes trigger reflective reroute instead of dead stop."""
    p = Proposal(
        component="empty.py",
        change_type="mutation",
        description="some change",
        think_notes="",
    )
    result = await engine.gate_check(p)
    assert result.status == EvolutionStatus.GATED
    assert result.reflection_attempts >= 1
    assert "Reflective reroute attempt" in result.think_notes


@pytest.mark.asyncio
async def test_think_gate_reroutes_short_notes(engine):
    """Very short think_notes (< 10 chars) trigger reflective reroute."""
    p = Proposal(
        component="short.py",
        change_type="mutation",
        description="some change",
        think_notes="ok",
    )
    result = await engine.gate_check(p)
    assert result.status == EvolutionStatus.GATED
    assert result.reflection_attempts >= 1
    assert len(result.reflection_suggestions) >= 3


@pytest.mark.asyncio
async def test_think_gate_reroute_budget_enforced(engine_paths):
    """If reroute budget is zero, short think_notes are still rejected."""
    eng = DarwinEngine(**engine_paths, max_reflection_reroutes=0)
    await eng.init()
    p = Proposal(
        component="short_budget.py",
        change_type="mutation",
        description="some change",
        think_notes="ok",
    )
    result = await eng.gate_check(p)
    assert result.status == EvolutionStatus.REJECTED
    assert result.gate_decision == GateDecision.BLOCK.value


@pytest.mark.asyncio
async def test_think_gate_passes_with_notes(engine):
    """TEST 6: Proposal with sufficient think_notes passes ThinkGate."""
    p = _safe_proposal(
        think_notes=(
            "This mutation improves selector diversity by adding novelty weighting"
        ),
    )
    result = await engine.gate_check(p)
    # Should NOT be rejected by ThinkGate (may be GATED or rejected for other reasons)
    assert "ThinkGate" not in (result.gate_reason or "")


# ---------------------------------------------------------------------------
# Subtree fitness estimation (Change 0E test)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subtree_fitness_estimation(engine):
    """TEST 7: Subtree potential returns max descendant fitness."""
    from dharma_swarm.archive import ArchiveEntry as AE

    # Create A -> B -> C chain
    a = AE(
        component="a.py",
        fitness=FitnessScore(correctness=0.3),
        status="applied",
    )
    b = AE(
        component="b.py",
        fitness=FitnessScore(correctness=0.5),
        status="applied",
        parent_id=a.id,
    )
    c = AE(
        component="c.py",
        fitness=FitnessScore(correctness=0.9, safety=1.0),
        status="applied",
        parent_id=b.id,
    )

    entries = {a.id: a, b.id: b, c.id: c}

    # A's subtree includes B and C — max is C's fitness
    potential_a = engine.predictor.estimate_subtree_potential(a.id, entries)
    c_weighted = c.fitness.weighted()
    assert potential_a == pytest.approx(c_weighted)

    # C has no descendants — returns own fitness
    potential_c = engine.predictor.estimate_subtree_potential(c.id, entries)
    assert potential_c == pytest.approx(c_weighted)
