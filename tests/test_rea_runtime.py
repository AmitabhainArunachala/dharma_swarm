from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from dharma_swarm.rea_runtime import (
    EconomicSpoke,
    TemporalRunStore,
    WaitState,
    WaitStateKind,
    get_run_profile,
)


def test_get_all_night_build_profile_has_primary_and_secondary_spokes() -> None:
    profile = get_run_profile("all_night_build")

    assert profile.profile_id == "all_night_build"
    assert profile.primary_spoke is EconomicSpoke.CODING
    assert EconomicSpoke.RESEARCH_SERVICES in profile.secondary_spokes
    assert EconomicSpoke.CONTENT_OPS in profile.secondary_spokes
    assert profile.hibernate_enabled is True


def test_get_self_evolution_72h_profile_is_long_horizon() -> None:
    profile = get_run_profile("self_evolution_72h")

    assert profile.profile_id == "self_evolution_72h"
    assert profile.horizon_hours == 72.0
    assert profile.primary_spoke is EconomicSpoke.CODING
    assert profile.self_evolution_interval_cycles == 2
    assert EconomicSpoke.QUANT_EXPERIMENTAL in profile.secondary_spokes


def test_temporal_store_persists_manifest_and_ready_wait_states(tmp_path: Path) -> None:
    store = TemporalRunStore(tmp_path)
    profile = get_run_profile("all_night_build")
    manifest = store.start_run("run-1", profile=profile)

    assert manifest.run_id == "run-1"
    assert store.load_manifest("run-1").profile.profile_id == "all_night_build"

    wake_at = datetime.now(timezone.utc) + timedelta(seconds=5)
    wait = WaitState(
        kind=WaitStateKind.EXTERNAL_JOB,
        reason="Await benchmark completion",
        wake_at=wake_at,
        resume_task_id="benchmark_resume",
        resume_goal="Collect benchmark results",
        payload={"job_id": "job-123"},
    )
    store.add_wait_state("run-1", wait)

    ready_now = store.ready_wait_states("run-1", now=datetime.now(timezone.utc))
    assert ready_now == []

    ready_later = store.ready_wait_states("run-1", now=wake_at + timedelta(seconds=1))
    assert [item.wait_id for item in ready_later] == [wait.wait_id]

    store.mark_resumed("run-1", wait.wait_id, reason="job finished")
    ready_after_resume = store.ready_wait_states("run-1", now=wake_at + timedelta(seconds=2))
    assert ready_after_resume == []
