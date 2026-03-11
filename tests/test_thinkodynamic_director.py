from __future__ import annotations

from pathlib import Path

import pytest

from dharma_swarm.models import TaskStatus
from dharma_swarm.thinkodynamic_director import ThinkodynamicDirector


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
