from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from dharma_swarm.engine.conversation_memory import ConversationMemoryStore
from dharma_swarm.models import AgentRole, AgentState, AgentStatus, ProviderType, TaskStatus
from dharma_swarm.thinkodynamic_director import (
    DirectorMindSpec,
    ThinkodynamicDirector,
    WorkflowPlan,
    WorkflowTaskPlan,
    _detect_task_repetitions,
    _parse_output_delegations,
    _parse_mission_deliverables,
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


def test_sense_can_promote_latent_gold_without_file_signals(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    state_dir = tmp_path / ".dharma"
    repo_root.mkdir(parents=True, exist_ok=True)

    store = ConversationMemoryStore(state_dir / "db" / "memory_plane.db")
    store.record_turn(
        session_id="sess-latent",
        task_id="task-memory",
        role="user",
        content=(
            "We could build a memory palace index for task recall and retrieval.\n"
            "Maybe resurface abandoned branches automatically when they become relevant."
        ),
        turn_index=1,
    )
    store.mark_task_outcome("task-memory", outcome="success")

    director = ThinkodynamicDirector(
        repo_root=repo_root,
        state_dir=state_dir,
        scan_roots=(),
        external_roots=(),
        mission_brief="Choose the next highest-leverage mission.",
        signal_limit=6,
        max_candidates=8,
        max_active_tasks=4,
    )

    sense = director.sense()

    assert sense["signals"] == []
    assert sense["latent_gold"]
    primary = sense["primary"]
    assert primary is not None
    assert primary.theme == "memory"
    assert "Latent gold:" in primary.why_now


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


def test_plan_workflow_attaches_primary_agent_preferences(
    director: ThinkodynamicDirector,
) -> None:
    primary = director.choose_primary(director.build_opportunities(director.rank_file_signals()))
    workflow = director.plan_workflow(primary, cycle_id="12345")

    assert workflow.tasks[0].preferred_agents[0] == "opus-primus"
    assert workflow.tasks[0].preferred_backends[0] == "claude-cli"
    assert workflow.tasks[2].preferred_agents[0] == "codex-primus"
    assert workflow.tasks[2].preferred_backends[0] == "codex-cli"
    assert ProviderType.CODEX.value in workflow.tasks[2].provider_allowlist


def test_director_auto_concurrency_caps_to_active_limit(tmp_path: Path) -> None:
    director = ThinkodynamicDirector(
        repo_root=tmp_path / "repo",
        state_dir=tmp_path / ".dharma",
        scan_roots=(),
        external_roots=(),
        max_active_tasks=4,
        max_concurrent_tasks=0,
    )

    assert director.max_active_tasks == 4
    assert director.max_concurrent_tasks == 4


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
    campaign = director.state_dir / "campaign.json"
    assert campaign.exists()
    payload = json.loads(campaign.read_text(encoding="utf-8"))
    assert payload["mission_title"]
    assert payload["artifacts"]


@pytest.mark.asyncio
async def test_deliberate_council_writes_heuristic_dialogue_without_swarm(
    director: ThinkodynamicDirector,
) -> None:
    await director.init()
    primary = director.choose_primary(director.build_opportunities(director.rank_file_signals()))
    workflow = director.plan_workflow(primary, cycle_id="council-1")

    council = await director.deliberate_council(
        cycle_id="council-1",
        workflow=workflow,
        vision_result={"vision_text": "Keep the mission sharp."},
        sense_result={"opportunities": [primary]},
    )

    assert council.members == ["codex-primus", "opus-primus"]
    dialogue_path = Path(council.dialogue_path)
    assert dialogue_path.exists()
    dialogue = dialogue_path.read_text(encoding="utf-8")
    assert "Director Council Dialogue" in dialogue
    assert "codex-primus" in dialogue
    assert "opus-primus" in dialogue


@pytest.mark.asyncio
async def test_query_council_member_times_out_named_runner(
    director: ThinkodynamicDirector,
    monkeypatch,
) -> None:
    class _SlowRunner:
        async def run_task(self, task):
            await asyncio.sleep(0.2)
            return "late"

    monkeypatch.setenv("DGC_THINKODYNAMIC_SWARM_RUNNER_TIMEOUT", "0.01")

    async def _fake_find_swarm_runner(name: str):
        return _SlowRunner()

    director._find_swarm_runner = _fake_find_swarm_runner  # type: ignore[assignment]

    member = DirectorMindSpec(
        name="codex-primus",
        role="meta",
        provider="openai",
        model="codex-test",
        backend="codex-cli",
        purpose="meta",
    )
    workflow = WorkflowPlan(
        cycle_id="council-timeout",
        workflow_id="wf-council-timeout",
        opportunity_id="opp-council-timeout",
        opportunity_title="Timeout council lane",
        theme="autonomy",
        thesis="Bound stuck runners.",
        why_now="Council should not hang forever.",
        expected_duration_min=5,
        tasks=[],
    )

    turn = await director._query_council_member(
        member,
        workflow,
        vision_result={"vision_text": "Keep moving."},
        sense_result={"opportunities": []},
    )

    assert turn.success is False
    assert "timed out" in turn.error


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


def test_parse_output_delegations_extracts_follow_on_tasks() -> None:
    text = (
        "Finished the slice.\n\n"
        "## DELEGATIONS\n"
        "- [validator] Add focused regression tests :: Cover the new worker loop.\n"
        "- [architect] Tighten retry policy :: Document why the backend order exists.\n"
    )

    delegations = _parse_output_delegations(text)

    assert len(delegations) == 2
    assert delegations[0]["role"] == "validator"
    assert delegations[0]["title"] == "Add focused regression tests"
    assert delegations[1]["description"] == "Document why the backend order exists."


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


# === Worker Loop Tests ===


@pytest.mark.asyncio
async def test_execute_pending_tasks_runs_and_produces_artifacts(
    director: ThinkodynamicDirector,
) -> None:
    """Worker loop should keep pulling newly ready tasks until the workflow clears."""
    await director.init()
    primary = director.choose_primary(director.build_opportunities(director.rank_file_signals()))
    workflow = director.plan_workflow(primary, cycle_id="worker-test-1")
    tasks = await director.enqueue_workflow(workflow)
    assert len(tasks) >= 2

    # Mock spawn_agent to return a fake result (no real API call)
    async def _fake_spawn(task_plan, wf, *, model="sonnet", timeout=600):
        return {
            "task_key": task_plan.key,
            "title": task_plan.title,
            "success": True,
            "output_length": 42,
            "output": f"Completed: {task_plan.title}. All good.",
            "blocked": False,
            "rapid": True,
            "provider": "test-mock",
        }

    director.spawn_agent = _fake_spawn  # type: ignore[assignment]

    results = await director.execute_pending_tasks(max_concurrent=2)
    assert len(results) == len(tasks)
    assert all(r["success"] for r in results)
    assert all(r["provider"] == "test-mock" for r in results)

    # Verify artifacts were written
    for r in results:
        artifact = Path(r["artifact"])
        assert artifact.exists()
        content = artifact.read_text()
        assert "DONE" in content
        assert r["title"] in content

    # Verify task board was updated
    completed_tasks = [
        t for t in await director.list_director_tasks()
        if t.status == TaskStatus.COMPLETED
    ]
    assert len(completed_tasks) == len(tasks)


@pytest.mark.asyncio
async def test_execute_pending_tasks_handles_blocked(
    director: ThinkodynamicDirector,
) -> None:
    """Worker loop should mark BLOCKED tasks as failed with blocker info."""
    await director.init()
    primary = director.choose_primary(director.build_opportunities(director.rank_file_signals()))
    workflow = director.plan_workflow(primary, cycle_id="worker-block-1")
    await director.enqueue_workflow(workflow)

    async def _blocked_spawn(task_plan, wf, *, model="sonnet", timeout=600):
        return {
            "task_key": task_plan.key,
            "title": task_plan.title,
            "success": True,
            "output_length": 30,
            "output": "BLOCKED: Need API key for external service.",
            "blocked": True,
            "rapid": True,
            "provider": "test-mock",
        }

    director.spawn_agent = _blocked_spawn  # type: ignore[assignment]

    results = await director.execute_pending_tasks(max_concurrent=1)
    assert len(results) == 1
    assert results[0]["blocked"] is True

    failed_tasks = [
        t for t in await director.list_director_tasks()
        if t.status == TaskStatus.FAILED
    ]
    assert len(failed_tasks) >= 1


@pytest.mark.asyncio
async def test_execute_pending_tasks_can_scope_to_cycle_id(
    director: ThinkodynamicDirector,
) -> None:
    await director.init()
    primary = director.choose_primary(director.build_opportunities(director.rank_file_signals()))
    older = director.plan_workflow(primary, cycle_id="cycle-old")
    newer = director.plan_workflow(primary, cycle_id="cycle-new")
    await director.enqueue_workflow(older)
    await director.enqueue_workflow(newer)

    async def _fake_spawn(task_plan, wf, *, model="sonnet", timeout=600):
        return {
            "task_key": task_plan.key,
            "title": task_plan.title,
            "success": True,
            "output_length": 24,
            "output": f"Completed: {wf.cycle_id}",
            "blocked": False,
            "rapid": True,
            "provider": "test-mock",
        }

    director.spawn_agent = _fake_spawn  # type: ignore[assignment]

    results = await director.execute_pending_tasks(max_concurrent=4, cycle_id="cycle-new")

    assert results
    assert all("cycle-new" in Path(result["artifact"]).read_text() for result in results)
    completed = [
        task for task in await director.list_director_tasks()
        if task.status == TaskStatus.COMPLETED
    ]
    assert completed
    assert all(
        str(task.metadata.get("director_cycle_id", "")) == "cycle-new"
        for task in completed
    )


@pytest.mark.asyncio
async def test_execute_pending_tasks_can_delegate_follow_on_work(
    director: ThinkodynamicDirector,
) -> None:
    await director.init()
    workflow = WorkflowPlan(
        cycle_id="dynamic-fanout",
        workflow_id="wf-dynamic-fanout",
        opportunity_id="opp-dynamic-fanout",
        opportunity_title="Dynamic fanout",
        theme="autonomy",
        thesis="Let one planning task seed follow-on work.",
        why_now="This proves the worker can keep moving without another director cycle.",
        expected_duration_min=30,
        tasks=[
            WorkflowTaskPlan(
                key="seed-fanout",
                title="Seed the fanout",
                description="Create the next tasks.",
                priority="high",
                role_hint="architect",
                acceptance=["Create follow-on tasks."],
            )
        ],
    )
    tasks = await director.enqueue_workflow(workflow)

    async def _fanout_spawn(task_plan, wf, *, model="sonnet", timeout=600):
        if task_plan.title == "Seed the fanout":
            return {
                "task_key": task_plan.key,
                "title": task_plan.title,
                "success": True,
                "output_length": 120,
                "output": (
                    "Completed the planning slice.\n\n"
                    "## DELEGATIONS\n"
                    "- [surgeon] Implement worker telemetry :: Write structured logs for each wave.\n"
                ),
                "blocked": False,
                "rapid": True,
                "provider": "codex-cli",
            }
        return {
            "task_key": task_plan.key,
            "title": task_plan.title,
            "success": True,
            "output_length": 48,
            "output": f"Completed child task: {task_plan.title}",
            "blocked": False,
            "rapid": True,
            "provider": "codex-cli",
        }

    director.spawn_agent = _fanout_spawn  # type: ignore[assignment]

    results = await director.execute_pending_tasks(max_concurrent=2, task_ids=[tasks[0].id])

    assert len(results) == 2
    assert any(result["title"] == "Seed the fanout" for result in results)
    assert any(result["title"] == "Implement worker telemetry" for result in results)
    child_tasks = [
        task for task in await director.list_director_tasks()
        if task.metadata.get("director_source_kind") == "dynamic_delegation"
    ]
    assert len(child_tasks) == 1


@pytest.mark.asyncio
async def test_execute_pending_tasks_suppresses_untrusted_fallback_delegations(
    director: ThinkodynamicDirector,
) -> None:
    await director.init()
    workflow = WorkflowPlan(
        cycle_id="fallback-delegation",
        workflow_id="wf-fallback-delegation",
        opportunity_id="opp-fallback-delegation",
        opportunity_title="Fallback delegation guard",
        theme="reliability",
        thesis="Fallback prose should not spawn new tasks.",
        why_now="Provider fallback can invent follow-on work.",
        expected_duration_min=15,
        tasks=[
            WorkflowTaskPlan(
                key="guard-fallback",
                title="Guard fallback output",
                description="Complete work without trusting fallback delegations.",
                priority="high",
                role_hint="validator",
                acceptance=["No untrusted child tasks created."],
            )
        ],
    )
    await director.enqueue_workflow(workflow)

    async def _fallback_spawn(task_plan, wf, *, model="sonnet", timeout=600):
        return {
            "task_key": task_plan.key,
            "title": task_plan.title,
            "success": True,
            "output_length": 120,
            "output": (
                "Completed via fallback.\n\n"
                "## DELEGATIONS\n"
                "- [surgeon] Invented child task :: This should not be trusted.\n"
            ),
            "blocked": False,
            "rapid": True,
            "provider": "openrouter-fallback",
        }

    director.spawn_agent = _fallback_spawn  # type: ignore[assignment]

    results = await director.execute_pending_tasks(max_concurrent=1)

    assert len(results) == 1
    assert results[0]["delegation_trusted"] is False
    assert results[0]["delegated_child_task_ids"] == []
    child_tasks = [
        task for task in await director.list_director_tasks()
        if task.metadata.get("director_source_kind") == "dynamic_delegation"
    ]
    assert child_tasks == []


@pytest.mark.asyncio
async def test_execute_pending_tasks_prefers_named_swarm_agent(
    director: ThinkodynamicDirector,
) -> None:
    await director.init()

    workflow = director._decorate_workflow_execution(
        WorkflowPlan(
            cycle_id="named-agent",
            workflow_id="wf-named-agent",
            opportunity_id="opp-named-agent",
            opportunity_title="Named agent execution",
            theme="autonomy",
            thesis="The director should use a persistent named runner when available.",
            why_now="This is the missing bridge from slots to minds.",
            expected_duration_min=20,
            evidence_paths=[],
            tasks=[
                WorkflowTaskPlan(
                    key="implement-slice",
                    title="Implement a precise slice",
                    description="Write the concrete implementation artifact.",
                    priority="high",
                    role_hint="general",
                    acceptance=["Artifact exists"],
                )
            ],
        )
    )
    await director.enqueue_workflow(workflow)

    class _FakeRunner:
        def __init__(self) -> None:
            self.state = AgentState(
                id="agent-codex-1",
                name="codex-primus",
                role=AgentRole.ORCHESTRATOR,
                status=AgentStatus.IDLE,
            )
            self._config = SimpleNamespace(provider=ProviderType.CODEX)
            self.last_task = None

        async def run_task(self, task):
            self.last_task = task
            return "named swarm runner completed the slice"

    class _FakePool:
        def __init__(self, runner) -> None:
            self._runner = runner

        async def get_idle_agents(self):
            return [self._runner.state]

        async def get(self, agent_id: str):
            if agent_id == self._runner.state.id:
                return self._runner
            return None

    runner = _FakeRunner()
    director._swarm_agent_pool = _FakePool(runner)

    async def _unexpected_spawn(*args, **kwargs):
        raise AssertionError("spawn_agent should not be used when a named runner is available")

    director.spawn_agent = _unexpected_spawn  # type: ignore[assignment]

    results = await director.execute_pending_tasks(max_concurrent=1)

    assert len(results) == 1
    assert results[0]["provider"] == "swarm:codex-primus"
    assert results[0]["agent_name"] == "codex-primus"
    assert runner.last_task is not None
    assert runner.last_task.metadata["available_provider_types"] == [ProviderType.CODEX.value]


@pytest.mark.asyncio
async def test_execute_pending_tasks_preserves_failure_output_on_task_record(
    director: ThinkodynamicDirector,
) -> None:
    await director.init()
    primary = director.choose_primary(director.build_opportunities(director.rank_file_signals()))
    workflow = director.plan_workflow(primary, cycle_id="worker-fail-1")
    await director.enqueue_workflow(workflow)

    async def _failed_spawn(task_plan, wf, *, model="sonnet", timeout=600):
        return {
            "task_key": task_plan.key,
            "title": task_plan.title,
            "success": False,
            "output_length": 55,
            "output": "(All vision providers failed or timed out within 24.0s)",
            "blocked": False,
            "rapid": False,
            "provider": "test-mock",
        }

    director.spawn_agent = _failed_spawn  # type: ignore[assignment]

    results = await director.execute_pending_tasks(max_concurrent=1)

    assert len(results) == 1
    failed_tasks = [
        task for task in await director.list_director_tasks()
        if task.status == TaskStatus.FAILED
    ]
    assert failed_tasks
    assert failed_tasks[0].result == "(All vision providers failed or timed out within 24.0s)"


@pytest.mark.asyncio
async def test_execute_pending_tasks_can_scope_to_specific_task_ids(
    director: ThinkodynamicDirector,
) -> None:
    await director.init()
    primary = director.choose_primary(director.build_opportunities(director.rank_file_signals()))
    workflow = director.plan_workflow(primary, cycle_id="cycle-explicit")
    tasks = await director.enqueue_workflow(workflow)

    async def _fake_spawn(task_plan, wf, *, model="sonnet", timeout=600):
        return {
            "task_key": task_plan.key,
            "title": task_plan.title,
            "success": True,
            "output_length": 16,
            "output": f"Completed: {task_plan.title}",
            "blocked": False,
            "rapid": True,
            "provider": "test-mock",
        }

    director.spawn_agent = _fake_spawn  # type: ignore[assignment]

    results = await director.execute_pending_tasks(
        max_concurrent=4,
        task_ids=[tasks[1].id],
    )

    assert results == []


@pytest.mark.asyncio
async def test_run_loop_uses_configured_worker_concurrency(
    director: ThinkodynamicDirector,
) -> None:
    director.max_concurrent_tasks = 5

    async def _fake_run_cycle(*, delegate=True, model="sonnet"):
        return {
            "cycle_id": "cycle-1",
            "delegated": True,
            "delegated_task_ids": ["task-1"],
            "workflow": {
                "workflow_id": "wf-1",
                "opportunity_id": "opp-1",
                "opportunity_title": "Concurrency test",
                "theme": "autonomy",
                "thesis": "Ensure run_loop honors configured worker concurrency.",
                "why_now": "The hardcoded cap should be gone.",
                "expected_duration_min": 5,
                "evidence_paths": [],
                "tasks": [],
            },
        }

    recorded: dict[str, int] = {}

    async def _fake_execute_pending_tasks(
        *,
        max_concurrent=3,
        model="sonnet",
        timeout=600,
        cycle_id=None,
        task_ids=None,
    ):
        recorded["max_concurrent"] = max_concurrent
        return []

    director.run_cycle = _fake_run_cycle  # type: ignore[assignment]
    director.execute_pending_tasks = _fake_execute_pending_tasks  # type: ignore[assignment]

    snapshots = await director.run_loop(once=True)

    assert snapshots
    assert recorded["max_concurrent"] == 5


# ------------------------------------------------------------------
# Mission-driven task decomposition (Gap #1 fix)
# ------------------------------------------------------------------


def test_parse_mission_deliverables_extracts_bullets():
    """Bullet-point deliverables should become task specs."""
    brief = (
        "Advance Jagat Kalyan in the highest-leverage way.\n"
        "- Produce a thesis document on AI carbon offsets\n"
        "- Build a ledger module for carbon accounting\n"
        "- Draft a partner outreach brief\n"
    )
    tasks = _parse_mission_deliverables(brief)
    assert len(tasks) == 3
    assert tasks[0]["title"] == "Produce a thesis document on AI carbon offsets"
    assert tasks[1]["title"] == "Build a ledger module for carbon accounting"
    assert tasks[2]["title"] == "Draft a partner outreach brief"


def test_parse_mission_deliverables_extracts_numbered():
    """Numbered list deliverables should become task specs."""
    brief = (
        "Complete the research sprint:\n"
        "1. Research existing offset protocols\n"
        "2. Analyze competitor landscape\n"
        "3. Design the integration API\n"
    )
    tasks = _parse_mission_deliverables(brief)
    assert len(tasks) == 3
    assert "Research existing offset protocols" in tasks[0]["title"]
    assert tasks[1]["role"] == "researcher"  # "analyze" → researcher
    assert tasks[2]["role"] == "architect"   # "design" → architect


def test_parse_mission_deliverables_returns_empty_for_default_mission():
    """The default mission has no structured deliverables."""
    from dharma_swarm.thinkodynamic_director import DEFAULT_MISSION
    tasks = _parse_mission_deliverables(DEFAULT_MISSION)
    assert tasks == []


def test_parse_mission_deliverables_returns_empty_for_prose():
    """Plain prose without bullets/numbers/imperatives yields no tasks."""
    brief = "Think about the best way to help the world."
    tasks = _parse_mission_deliverables(brief)
    assert tasks == []


def test_parse_mission_deliverables_extracts_imperative_verbs():
    """Imperative verb lines should be captured even without bullets."""
    brief = (
        "Create a dashboard for monitoring\n"
        "Investigate the failing pipeline\n"
        "Deploy the updated service\n"
    )
    tasks = _parse_mission_deliverables(brief)
    assert len(tasks) == 3
    assert tasks[0]["title"] == "Create a dashboard for monitoring"
    assert tasks[1]["role"] == "researcher"  # "investigate" → researcher


def test_parse_mission_deliverables_prefers_deliverables_section():
    """When a deliverables section exists, hard rules should not become tasks."""
    brief = (
        "# Mission\n"
        "Hard rules:\n"
        "- Do not idle\n"
        "- Prefer artifacts\n"
        "\n"
        "Deliverables:\n"
        "1. Build the semantic graph\n"
        "2. Generate the staged hyperfiles\n"
    )
    tasks = _parse_mission_deliverables(brief)
    assert len(tasks) == 2
    assert tasks[0]["title"] == "Build the semantic graph"
    assert tasks[1]["title"] == "Generate the staged hyperfiles"


def test_compile_workflow_uses_mission_deliverables(
    director: ThinkodynamicDirector,
) -> None:
    """When mission_brief has explicit deliverables, compile_workflow should
    use those as tasks instead of vision-proposed or opportunity-scored tasks."""
    director.mission_brief = (
        "Fix the carbon accounting system:\n"
        "- Audit the ledger module for bugs\n"
        "- Implement double-entry validation\n"
        "- Write integration tests for the ledger\n"
    )

    # Vision and sense results are irrelevant — mission deliverables win
    vision_result = {
        "proposed_tasks": [
            {"title": "Something the LLM proposed", "description": "x"},
            {"title": "Another LLM idea", "description": "y"},
        ],
        "vision_text": "LLM vision text",
    }
    sense_result = {"primary": None, "signals": [], "opportunities": []}

    workflow = director.compile_workflow_from_vision(
        vision_result, sense_result, cycle_id="mission-test-1",
    )

    assert workflow.theme == "mission"
    assert "mission" in workflow.workflow_id
    assert len(workflow.tasks) == 3
    assert workflow.tasks[0].title == "Audit the ledger module for bugs"
    assert workflow.tasks[1].title == "Implement double-entry validation"
    assert workflow.tasks[2].title == "Write integration tests for the ledger"
    # LLM-proposed tasks are NOT in the workflow
    task_titles = {t.title for t in workflow.tasks}
    assert "Something the LLM proposed" not in task_titles


def test_compile_workflow_promotes_campaign_execution_brief(
    director: ThinkodynamicDirector,
) -> None:
    campaign = director.state_dir / "campaign.json"
    campaign.parent.mkdir(parents=True, exist_ok=True)
    campaign.write_text(
        json.dumps(
            {
                "campaign_id": "campaign-brief-test",
                "mission_title": "Semantic execution brief",
                "mission_thesis": "Promote the hardened brief",
                "mission_theme": "semantic",
                "last_cycle_id": "cycle-0",
                "last_cycle_ts": "2026-03-13T00:00:00Z",
                "status": "planned",
                "task_count": 0,
                "task_titles": [],
                "delegated_task_ids": [],
                "review_summary": "",
                "blockers": [],
                "rapid_ascent": False,
                "evidence_paths": ["docs/reports/semantic.md"],
                "semantic_briefs": [],
                "execution_briefs": [
                    {
                        "brief_id": "execution-semantic-a",
                        "title": "Semantic bridge build brief",
                        "goal": "Promote the hardened semantic bridge into executable work.",
                        "readiness_score": 0.93,
                        "task_titles": [
                            "Map semantic bridge evidence",
                            "Implement semantic memory bridge improvements",
                            "Verify semantic bridge regressions",
                        ],
                        "acceptance": [
                            "Produce a real artifact.",
                            "Verify the touched path with evidence.",
                        ],
                        "evidence_paths": ["dharma_swarm/semantic_memory_bridge.py"],
                        "depends_on_briefs": ["semantic-a"],
                        "metadata": {"semantic_brief_id": "semantic-a"},
                    }
                ],
                "artifacts": [],
                "metrics": {},
                "previous_missions": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    workflow = director.compile_workflow_from_vision(
        {"proposed_tasks": [], "vision_text": "ignore"},
        {"primary": None, "signals": [], "opportunities": []},
        cycle_id="brief-test-1",
    )

    assert workflow.theme == "execution_brief"
    assert workflow.opportunity_id == "execution-semantic-a"
    assert [task.title for task in workflow.tasks] == [
        "Map semantic bridge evidence",
        "Implement semantic memory bridge improvements",
        "Verify semantic bridge regressions",
    ]


def test_compile_workflow_falls_through_without_deliverables(
    director: ThinkodynamicDirector,
) -> None:
    """With default mission (no deliverables), compile_workflow should use
    the standard vision/opportunity pipeline."""
    # director fixture uses default mission_brief
    vision_result = {
        "proposed_tasks": [
            {"title": "Audit test coverage", "description": "Map modules"},
            {"title": "Write missing tests", "description": "Add tests"},
        ],
        "vision_text": "Build test system",
    }
    sense_result = {"primary": None, "signals": [], "opportunities": []}

    workflow = director.compile_workflow_from_vision(
        vision_result, sense_result, cycle_id="fallthrough-1",
    )

    # Should use vision-proposed tasks, not mission path
    assert workflow.theme != "mission"
    assert "vision" in workflow.workflow_id
    assert len(workflow.tasks) == 2


@pytest.mark.asyncio
async def test_enqueue_workflow_dedupes_execution_brief_tasks(
    director: ThinkodynamicDirector,
) -> None:
    await director.init()
    workflow = director.workflow_from_execution_brief(
        brief=type("Brief", (), {
            "brief_id": "execution-semantic-a",
            "title": "Semantic bridge build brief",
            "goal": "Promote the hardened semantic bridge into executable work.",
            "readiness_score": 0.93,
            "task_titles": [
                "Map semantic bridge evidence",
                "Implement semantic memory bridge improvements",
                "Verify semantic bridge regressions",
            ],
            "acceptance": [
                "Produce a real artifact.",
                "Verify the touched path with evidence.",
            ],
            "evidence_paths": ["dharma_swarm/semantic_memory_bridge.py"],
        })(),
        cycle_id="brief-test-2",
    )

    first = await director.enqueue_workflow(workflow)
    second = await director.enqueue_workflow(workflow)

    assert len(first) == 3
    assert [task.id for task in second] == [task.id for task in first]
    assert len(await director.list_director_tasks()) == 3


@pytest.mark.asyncio
async def test_enqueue_workflow_requeues_failed_execution_brief_tasks(
    director: ThinkodynamicDirector,
) -> None:
    await director.init()
    workflow = director.workflow_from_execution_brief(
        brief=type("Brief", (), {
            "brief_id": "execution-semantic-b",
            "title": "Retry semantic bridge build brief",
            "goal": "Retry the hardened semantic bridge execution lane.",
            "readiness_score": 0.91,
            "task_titles": [
                "Map semantic bridge evidence",
                "Implement semantic memory bridge improvements",
            ],
            "acceptance": [
                "Produce a real artifact.",
                "Verify the touched path with evidence.",
            ],
            "evidence_paths": ["dharma_swarm/semantic_memory_bridge.py"],
        })(),
        cycle_id="brief-test-retry-1",
    )

    first = await director.enqueue_workflow(workflow)
    await director._task_board.assign(first[0].id, "worker-loop")
    await director._task_board.start(first[0].id)
    await director._task_board.fail(first[0].id, error="BLOCKED: retry me")

    retried_workflow = director.workflow_from_execution_brief(
        brief=type("Brief", (), {
            "brief_id": "execution-semantic-b",
            "title": "Retry semantic bridge build brief",
            "goal": "Retry the hardened semantic bridge execution lane.",
            "readiness_score": 0.91,
            "task_titles": [
                "Map semantic bridge evidence",
                "Implement semantic memory bridge improvements",
            ],
            "acceptance": [
                "Produce a real artifact.",
                "Verify the touched path with evidence.",
            ],
            "evidence_paths": ["dharma_swarm/semantic_memory_bridge.py"],
        })(),
        cycle_id="brief-test-retry-2",
    )

    retried = await director.enqueue_workflow(retried_workflow)

    assert [task.id for task in retried] == [task.id for task in first]
    refreshed = await director._task_board.get(first[0].id)
    assert refreshed is not None
    assert refreshed.status == TaskStatus.PENDING
    assert refreshed.metadata["director_cycle_id"] == "brief-test-retry-2"
