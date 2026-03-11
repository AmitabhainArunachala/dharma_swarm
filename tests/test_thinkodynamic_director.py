from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from dharma_swarm.models import TaskStatus
from dharma_swarm.thinkodynamic_director import (
    ThinkodynamicDirector,
    _detect_task_repetitions,
    _read_recent_task_titles,
)


def _fake_claude_subprocess(*args, **kwargs):
    """Mock subprocess.run for claude -p calls, returning a plausible vision."""
    import types

    result = types.SimpleNamespace()
    result.returncode = 0
    result.stdout = (
        "## VISION\n"
        "The highest-leverage project is building a test orchestration system.\n\n"
        "## PROPOSAL\n"
        "Build automated test pipelines.\n\n"
        "## WORKFLOW\n"
        "1. **Audit test coverage**\n"
        "   - title: Audit test coverage\n"
        "   - description: Map all uncovered modules.\n"
        "   - role: researcher\n"
        "   - estimated_minutes: 60\n"
        "   - acceptance: Coverage map produced\n\n"
        "2. **Write missing tests**\n"
        "   - title: Write missing tests\n"
        "   - description: Add tests for uncovered paths.\n"
        "   - role: general\n"
        "   - estimated_minutes: 120\n"
        "   - acceptance: All new tests pass\n\n"
        "NEXT_VISION: Expand to integration tests."
    )
    result.stderr = ""
    return result


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def director(tmp_path: Path) -> ThinkodynamicDirector:
    repo_root = tmp_path / "repo"
    state_dir = tmp_path / ".dharma"
    _write(
        repo_root / "docs" / "reports" / "VISION.md",
        "# World Impact Autonomy\n\n"
        "Thinkodynamic director for swarm workflow delegate task board world impact.\n"
        "Research packet, deployment, product, revenue, and validation.\n",
    )
    _write(
        repo_root / "dharma_swarm" / "runtime.py",
        "def run():\n"
        "    # TODO: delegate workflow and validate runtime health\n"
        "    return 'swarm autonomy'\n",
    )
    _write(
        repo_root / "tests" / "test_runtime.py",
        "def test_runtime():\n"
        "    assert True\n",
    )
    return ThinkodynamicDirector(
        repo_root=repo_root,
        state_dir=state_dir,
        scan_roots=("docs", "dharma_swarm", "tests"),
        external_roots=(),
        mission_brief=(
            "Find the highest-leverage workflow for autonomy, world impact, "
            "revenue, and delegation."
        ),
        signal_limit=8,
        max_candidates=24,
        max_active_tasks=8,
    )


def test_rank_file_signals_prefers_high_salience_strategy_docs(
    director: ThinkodynamicDirector,
) -> None:
    signals = director.rank_file_signals()
    assert signals
    top_paths = [Path(signal.path).name for signal in signals[:2]]
    assert "VISION.md" in top_paths
    assert any(
        signal.theme_scores.get("autonomy", 0.0) > 0.0
        for signal in signals
    )


def test_build_opportunities_biases_to_autonomy_director(
    director: ThinkodynamicDirector,
) -> None:
    signals = director.rank_file_signals()
    opportunities = director.build_opportunities(signals)
    assert opportunities
    primary = director.choose_primary(opportunities)
    assert primary.theme == "autonomy"
    assert "director" in primary.title.lower()


def test_plan_workflow_creates_dependent_execution_spine(
    director: ThinkodynamicDirector,
) -> None:
    primary = director.choose_primary(director.build_opportunities(director.rank_file_signals()))
    workflow = director.plan_workflow(primary, cycle_id="12345")
    assert workflow.workflow_id.startswith("wf-autonomy-")
    assert len(workflow.tasks) == 4
    assert workflow.tasks[1].depends_on_keys == ["map-state"]
    assert workflow.tasks[2].depends_on_keys == ["execution-spine"]
    assert workflow.tasks[3].depends_on_keys == ["highest-leverage-slice"]


@pytest.mark.asyncio
async def test_enqueue_workflow_creates_director_tasks(
    director: ThinkodynamicDirector,
) -> None:
    await director.init()
    primary = director.choose_primary(director.build_opportunities(director.rank_file_signals()))
    workflow = director.plan_workflow(primary, cycle_id="23456")

    tasks = await director.enqueue_workflow(workflow)

    assert len(tasks) == 4
    assert tasks[0].metadata["source"] == "thinkodynamic_director"
    assert tasks[1].depends_on == [tasks[0].id]
    assert tasks[2].depends_on == [tasks[1].id]
    assert tasks[3].depends_on == [tasks[2].id]


@pytest.mark.asyncio
async def test_review_workflow_flags_rapid_completion(
    director: ThinkodynamicDirector,
) -> None:
    await director.init()
    primary = director.choose_primary(director.build_opportunities(director.rank_file_signals()))
    workflow = director.plan_workflow(primary, cycle_id="34567")
    tasks = await director.enqueue_workflow(workflow)

    completed = []
    for task in tasks:
        await director._task_board.assign(task.id, "agent-1")
        await director._task_board.start(task.id)
        completed.append(await director._task_board.complete(task.id, result="done"))

    review = director.review_workflow(workflow, completed)

    assert review.completed_count == 4
    assert review.active_count == 0
    assert review.rapid_completion is True
    assert review.needs_resynthesis is True


@pytest.mark.asyncio
async def test_run_cycle_writes_artifacts_and_respects_preview_mode(
    director: ThinkodynamicDirector,
) -> None:
    with patch("dharma_swarm.thinkodynamic_director.subprocess.run", side_effect=_fake_claude_subprocess):
        snapshot = await director.run_cycle(delegate=False)

    assert snapshot["delegated"] is False
    summary = Path(snapshot["summary_path"])
    assert summary.exists()
    assert "selected_opportunity" in snapshot
    tasks = await director.list_director_tasks()
    assert tasks == []


@pytest.mark.asyncio
async def test_recent_workflow_review_surfaces_failures(
    director: ThinkodynamicDirector,
) -> None:
    await director.init()
    primary = director.choose_primary(director.build_opportunities(director.rank_file_signals()))
    workflow = director.plan_workflow(primary, cycle_id="45678")
    tasks = await director.enqueue_workflow(workflow)

    await director._task_board.assign(tasks[0].id, "agent-1")
    await director._task_board.start(tasks[0].id)
    await director._task_board.fail(tasks[0].id, error="network timeout")

    reviews = await director.review_recent_workflows(limit=1)

    assert reviews
    assert reviews[0].failed_count == 1
    assert "network timeout" in reviews[0].blockers[0]


@pytest.mark.asyncio
async def test_active_director_task_count_only_counts_live_tasks(
    director: ThinkodynamicDirector,
) -> None:
    await director.init()
    primary = director.choose_primary(director.build_opportunities(director.rank_file_signals()))
    workflow = director.plan_workflow(primary, cycle_id="56789")
    tasks = await director.enqueue_workflow(workflow)

    assert await director.active_director_task_count() == 4

    await director._task_board.assign(tasks[0].id, "agent-1")
    await director._task_board.start(tasks[0].id)
    await director._task_board.complete(tasks[0].id, result="done")
    remaining = await director.active_director_task_count()
    assert remaining == 3

    refreshed = await director._task_board.get(tasks[0].id)
    assert refreshed is not None
    assert refreshed.status == TaskStatus.COMPLETED


# === Loop Breaker Tests ===


def test_read_recent_task_titles_returns_empty_when_no_log(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "dharma_swarm.thinkodynamic_director.STATE", tmp_path / "no_such_dir"
    )
    assert _read_recent_task_titles() == []


def test_read_recent_task_titles_extracts_from_cycles(
    tmp_path: Path,
    monkeypatch,
) -> None:
    log_dir = tmp_path / "logs" / "thinkodynamic_director"
    log_dir.mkdir(parents=True)
    cycle_log = log_dir / "cycles.jsonl"

    entries = []
    for i in range(4):
        entries.append(json.dumps({
            "cycle_id": str(i),
            "workflow": {
                "tasks": [
                    {"title": "Bring up NVIDIA RAG services"},
                    {"title": f"Fix widget {i}"},
                ]
            },
        }))
    cycle_log.write_text("\n".join(entries), encoding="utf-8")

    monkeypatch.setattr("dharma_swarm.thinkodynamic_director.STATE", tmp_path)
    titles = _read_recent_task_titles(depth=4)
    assert "Bring up NVIDIA RAG services" in titles
    assert len(titles) == 8  # 4 cycles * 2 tasks


def test_detect_task_repetitions_finds_repeated(
    tmp_path: Path,
    monkeypatch,
) -> None:
    log_dir = tmp_path / "logs" / "thinkodynamic_director"
    log_dir.mkdir(parents=True)
    cycle_log = log_dir / "cycles.jsonl"

    entries = []
    for _ in range(5):
        entries.append(json.dumps({
            "cycle_id": "x",
            "workflow": {
                "tasks": [
                    {"title": "Bring up NVIDIA RAG services"},
                    {"title": "Fix Data Flywheel endpoint"},
                ]
            },
        }))
    # One unique task
    entries.append(json.dumps({
        "cycle_id": "y",
        "workflow": {
            "tasks": [{"title": "Something genuinely new"}],
        },
    }))
    cycle_log.write_text("\n".join(entries), encoding="utf-8")

    monkeypatch.setattr("dharma_swarm.thinkodynamic_director.STATE", tmp_path)
    repeated = _detect_task_repetitions(depth=6, threshold=3)

    assert len(repeated) == 2
    assert "bring up nvidia rag services" in repeated
    assert "fix data flywheel endpoint" in repeated


def test_compile_workflow_filters_repeated_tasks(
    director: ThinkodynamicDirector,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """When vision proposes tasks that match anti-targets, compile should filter them."""
    # Set up cycle log with repeated tasks
    log_dir = tmp_path / ".dharma" / "logs" / "thinkodynamic_director"
    log_dir.mkdir(parents=True, exist_ok=True)
    cycle_log = log_dir / "cycles.jsonl"

    entries = []
    for _ in range(5):
        entries.append(json.dumps({
            "cycle_id": "z",
            "workflow": {
                "tasks": [
                    {"title": "Map the current state of the swarm"},
                    {"title": "Implement highest-leverage slice"},
                ]
            },
        }))
    cycle_log.write_text("\n".join(entries), encoding="utf-8")

    monkeypatch.setattr("dharma_swarm.thinkodynamic_director.STATE", tmp_path / ".dharma")

    vision_result = {
        "proposed_tasks": [
            {"title": "Map the current state of the swarm", "description": "dup", "role": "cartographer"},
            {"title": "Implement highest-leverage slice", "description": "dup", "role": "general"},
            {"title": "Build new monitoring dashboard", "description": "novel", "role": "architect"},
            {"title": "Write integration tests for yoga_node", "description": "novel", "role": "validator"},
        ],
        "vision_text": "test",
    }
    sense_result = {"signals": [], "opportunities": [], "primary": None}

    workflow = director.compile_workflow_from_vision(
        vision_result, sense_result, cycle_id="loop-break-test"
    )

    # The repeated tasks should be filtered, leaving only the novel ones
    task_titles = [t.title for t in workflow.tasks]
    assert "Map the current state of the swarm" not in task_titles
    assert "Implement highest-leverage slice" not in task_titles
    assert "Build new monitoring dashboard" in task_titles
