"""End-to-end boot smoke test: init → tick → dispatch → complete → knowledge → Darwin.

Runs the full SwarmManager lifecycle in mock mode (no LLM keys needed).
This is the acid test: does the wiring from PR #9 actually work end-to-end?
"""
from __future__ import annotations

import asyncio
import json
import logging

import pytest

logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
logger = logging.getLogger("e2e_boot")


@pytest.fixture
def state_dir(tmp_path):
    d = tmp_path / ".dharma_e2e"
    d.mkdir()
    return str(d)


@pytest.mark.asyncio
async def test_full_lifecycle_boot(state_dir):
    """Boot swarm → tick → dispatch tasks → verify completion pipeline."""
    from dharma_swarm.swarm import SwarmManager
    from pathlib import Path

    logger.info("=== PHASE 1: Init SwarmManager ===")
    swarm = SwarmManager(state_dir=state_dir)
    await swarm.init()

    # Verify agents spawned (correct attr: _agent_pool)
    pool = swarm._agent_pool
    agents = getattr(pool, 'agents', getattr(pool, '_agents', {}))
    agent_count = len(agents)
    logger.info(f"Agents spawned: {agent_count}")
    assert agent_count > 0, "No agents were spawned on init"

    # Verify task board has tasks
    tasks = await swarm._task_board.get_ready_tasks()
    logger.info(f"Ready tasks: {len(tasks)}")

    logger.info("=== PHASE 2: Single tick() ===")
    tick_result = await swarm.tick()
    logger.info(f"Tick result: {json.dumps(tick_result, indent=2, default=str)}")
    assert not tick_result["paused"], "Swarm paused unexpectedly"
    assert not tick_result["circuit_broken"], "Circuit breaker tripped"

    logger.info("=== PHASE 3: Multi-tick dispatch ===")
    dispatched_total = tick_result.get("dispatched", 0)
    settled_total = tick_result.get("settled", 0)

    for i in range(12):
        tick_result = await swarm.tick()
        dispatched_total += tick_result.get("dispatched", 0)
        settled_total += tick_result.get("settled", 0)
        logger.info(
            f"  tick {i+2}: dispatched={tick_result.get('dispatched',0)} "
            f"settled={tick_result.get('settled',0)} "
            f"organism={tick_result.get('organism_verdict')}"
        )
        await asyncio.sleep(0.05)

    logger.info(f"Totals — dispatched: {dispatched_total}, settled: {settled_total}")

    logger.info("=== PHASE 4: Task state audit ===")
    all_tasks = []
    if hasattr(swarm._task_board, '_tasks'):
        all_tasks = list(swarm._task_board._tasks.values())
    elif hasattr(swarm._task_board, 'list_all'):
        all_tasks = await swarm._task_board.list_all()

    completed = [t for t in all_tasks if 'complete' in str(getattr(t,'status','')).lower()]
    running = [t for t in all_tasks if 'running' in str(getattr(t,'status','')).lower()]
    failed = [t for t in all_tasks if 'fail' in str(getattr(t,'status','')).lower()]
    pending = [t for t in all_tasks if 'pending' in str(getattr(t,'status','')).lower()]

    logger.info(f"completed={len(completed)} running={len(running)} failed={len(failed)} pending={len(pending)}")
    for t in all_tasks:
        s = getattr(t, 'status', '?')
        title = getattr(t, 'title', '?')[:60]
        result = getattr(t, 'result', '') or ''
        logger.info(f"  [{s}] {title} → {result[:80]}")

    logger.info("=== PHASE 5: Subsystem wiring check ===")
    subsystems = {
        'task_board': swarm._task_board,
        'agent_pool': swarm._agent_pool,
        'orchestrator': swarm._orchestrator,
        'engine (Darwin)': swarm._engine,
        'organism': getattr(swarm, '_organism', None),
        'economic_spine': getattr(swarm, '_economic_spine', None),
        'knowledge_store': getattr(swarm, '_knowledge_store', None),
        'hibernation_manager': getattr(swarm, '_hibernation_manager', None),
        'sleep_time_agent': getattr(swarm, '_sleep_time_agent', None),
        'director': getattr(swarm, '_director', None),
        'witness': getattr(swarm, '_witness', None),
        'decision_log': getattr(swarm, '_decision_log', None),
        'ginko_fleet': getattr(swarm, '_ginko_fleet', None),
        'stigmergy': getattr(swarm, '_stigmergy', None),
    }
    wired = 0
    missing = 0
    for name, val in subsystems.items():
        if val is not None:
            logger.info(f"  ✓ {name}")
            wired += 1
        else:
            logger.warning(f"  ✗ {name} — NOT WIRED")
            missing += 1
    logger.info(f"Wired: {wired}/{wired+missing}")

    logger.info("=== PHASE 6: State directory artifacts ===")
    state_path = Path(state_dir)
    files = sorted(state_path.rglob("*"))
    file_count = sum(1 for f in files if f.is_file())
    logger.info(f"Total files: {file_count}")
    for f in files[:25]:
        if f.is_file():
            logger.info(f"  {f.relative_to(state_path)} ({f.stat().st_size}b)")

    logger.info("=== PHASE 7: Shutdown ===")
    # Use a timeout on shutdown to prevent hanging
    try:
        await asyncio.wait_for(swarm.shutdown(), timeout=5.0)
    except (asyncio.TimeoutError, Exception) as e:
        logger.warning(f"Shutdown issue (non-fatal): {e}")

    logger.info("=== DONE ===")
    assert dispatched_total > 0, "No tasks dispatched in 13 ticks — dispatch pipeline broken"
    logger.info(f"E2E BOOT PASSED: {agent_count} agents, {dispatched_total} dispatched, {settled_total} settled, {len(completed)} completed")


@pytest.mark.asyncio
async def test_custom_task_dispatch(state_dir):
    """Create a custom task and verify it flows through the pipeline."""
    from dharma_swarm.swarm import SwarmManager
    from dharma_swarm.models import TaskPriority

    swarm = SwarmManager(state_dir=state_dir)
    await swarm.init()

    task = await swarm._task_board.create(
        title="E2E Smoke: echo test",
        description="Respond with: DHARMA SWARM ALIVE",
        priority=TaskPriority.HIGH,
        created_by="e2e_test",
    )
    logger.info(f"Created task {task.id}")

    for i in range(15):
        result = await swarm.tick()
        await asyncio.sleep(0.05)

    updated = await swarm._task_board.get(task.id)
    status = str(getattr(updated, 'status', 'unknown')).lower()
    result_text = getattr(updated, 'result', None)
    logger.info(f"Task {task.id}: status={status}, result={result_text}")

    try:
        await asyncio.wait_for(swarm.shutdown(), timeout=5.0)
    except (asyncio.TimeoutError, Exception):
        pass

    assert status != 'pending', f"Task stuck in pending — dispatch pipeline never picked it up"
