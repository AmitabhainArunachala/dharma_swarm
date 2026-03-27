"""Tests for the hibernate-and-wake state machine (dharma_swarm.hibernation)."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dharma_swarm.hibernation import (
    HibernateableJob,
    HibernationManager,
    JobState,
    WakeCondition,
    _VALID_TRANSITIONS,
    _default_check,
    register_condition,
)


# ── JobState transition tests ──────────────────────────────────────────


class TestJobStateTransitions:
    """Validate the state machine transition rules."""

    def test_pending_to_running(self):
        assert JobState.RUNNING in _VALID_TRANSITIONS[JobState.PENDING]

    def test_pending_to_cancelled(self):
        assert JobState.CANCELLED in _VALID_TRANSITIONS[JobState.PENDING]

    def test_running_to_waiting_external(self):
        assert JobState.WAITING_EXTERNAL in _VALID_TRANSITIONS[JobState.RUNNING]

    def test_running_to_completed(self):
        assert JobState.COMPLETED in _VALID_TRANSITIONS[JobState.RUNNING]

    def test_running_to_failed(self):
        assert JobState.FAILED in _VALID_TRANSITIONS[JobState.RUNNING]

    def test_waiting_to_ready(self):
        assert JobState.READY_TO_RESUME in _VALID_TRANSITIONS[JobState.WAITING_EXTERNAL]

    def test_waiting_to_failed(self):
        assert JobState.FAILED in _VALID_TRANSITIONS[JobState.WAITING_EXTERNAL]

    def test_ready_to_running(self):
        assert JobState.RUNNING in _VALID_TRANSITIONS[JobState.READY_TO_RESUME]

    def test_completed_is_terminal(self):
        assert len(_VALID_TRANSITIONS[JobState.COMPLETED]) == 0

    def test_failed_is_terminal(self):
        assert len(_VALID_TRANSITIONS[JobState.FAILED]) == 0

    def test_cancelled_is_terminal(self):
        assert len(_VALID_TRANSITIONS[JobState.CANCELLED]) == 0

    def test_invalid_transition_pending_to_completed(self):
        assert JobState.COMPLETED not in _VALID_TRANSITIONS[JobState.PENDING]

    def test_invalid_transition_waiting_to_running(self):
        assert JobState.RUNNING not in _VALID_TRANSITIONS[JobState.WAITING_EXTERNAL]


# ── WakeCondition tests ────────────────────────────────────────────────


class TestWakeCondition:
    def test_to_dict_roundtrip(self):
        wc = WakeCondition(
            condition_type="time",
            params={"wait_seconds": 3600},
            poll_interval_seconds=30,
        )
        d = wc.to_dict()
        restored = WakeCondition.from_dict(d)
        assert restored.condition_type == "time"
        assert restored.params["wait_seconds"] == 3600
        assert restored.poll_interval_seconds == 30

    def test_from_dict_defaults(self):
        wc = WakeCondition.from_dict({})
        assert wc.condition_type == "custom"
        assert wc.check_fn is None
        assert wc.poll_interval_seconds == 60

    def test_custom_with_check_fn(self):
        wc = WakeCondition(
            condition_type="custom",
            check_fn="my_checker",
            params={"key": "value"},
        )
        assert wc.check_fn == "my_checker"
        d = wc.to_dict()
        assert d["check_fn"] == "my_checker"


# ── HibernateableJob tests ─────────────────────────────────────────────


class TestHibernateableJob:
    def test_default_state(self):
        job = HibernateableJob(agent_id="test-agent")
        assert job.state == JobState.PENDING
        assert job.agent_id == "test-agent"
        assert len(job.job_id) == 16
        assert job.context_snapshot == {}
        assert job.max_wait_seconds == 86400

    def test_to_dict_roundtrip(self):
        wc = WakeCondition(condition_type="file_exists", params={"path": "/tmp/done"})
        job = HibernateableJob(
            job_id="abc123",
            state=JobState.WAITING_EXTERNAL,
            agent_id="agent-1",
            context_snapshot={"history": ["hello"]},
            wake_condition=wc,
            hibernated_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
            max_wait_seconds=7200,
            retry_count=2,
            metadata={"key": "val"},
        )
        d = job.to_dict()
        restored = HibernateableJob.from_dict(d)
        assert restored.job_id == "abc123"
        assert restored.state == JobState.WAITING_EXTERNAL
        assert restored.agent_id == "agent-1"
        assert restored.context_snapshot == {"history": ["hello"]}
        assert restored.wake_condition.condition_type == "file_exists"
        assert restored.max_wait_seconds == 7200
        assert restored.retry_count == 2
        assert restored.metadata == {"key": "val"}

    def test_to_dict_none_wake_condition(self):
        job = HibernateableJob(agent_id="a")
        d = job.to_dict()
        assert d["wake_condition"] is None

    def test_from_dict_minimal(self):
        d = {
            "job_id": "x",
            "state": "pending",
        }
        job = HibernateableJob.from_dict(d)
        assert job.job_id == "x"
        assert job.state == JobState.PENDING


# ── Condition checker tests ────────────────────────────────────────────


class TestConditionCheckers:
    def test_time_condition_not_elapsed(self):
        job = HibernateableJob(
            agent_id="a",
            hibernated_at=datetime.now(timezone.utc),
        )
        wc = WakeCondition(condition_type="time", params={"wait_seconds": 3600})
        assert _default_check(wc, job) is False

    def test_time_condition_elapsed(self):
        job = HibernateableJob(
            agent_id="a",
            hibernated_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        wc = WakeCondition(condition_type="time", params={"wait_seconds": 3600})
        assert _default_check(wc, job) is True

    def test_time_condition_no_hibernated_at(self):
        job = HibernateableJob(agent_id="a")
        wc = WakeCondition(condition_type="time", params={"wait_seconds": 1})
        assert _default_check(wc, job) is False

    def test_file_exists_condition_true(self, tmp_path):
        path = tmp_path / "marker.txt"
        path.write_text("done")
        job = HibernateableJob(agent_id="a")
        wc = WakeCondition(condition_type="file_exists", params={"path": str(path)})
        assert _default_check(wc, job) is True

    def test_file_exists_condition_false(self, tmp_path):
        job = HibernateableJob(agent_id="a")
        wc = WakeCondition(
            condition_type="file_exists",
            params={"path": str(tmp_path / "nonexistent")},
        )
        assert _default_check(wc, job) is False

    def test_custom_registered_checker(self):
        register_condition("always_true", lambda params, **kw: True)
        job = HibernateableJob(agent_id="a")
        wc = WakeCondition(condition_type="custom", check_fn="always_true")
        assert _default_check(wc, job) is True

    def test_custom_unregistered_checker(self):
        job = HibernateableJob(agent_id="a")
        wc = WakeCondition(condition_type="custom", check_fn="nonexistent_fn_xyz")
        assert _default_check(wc, job) is False

    def test_unknown_condition_type(self):
        job = HibernateableJob(agent_id="a")
        wc = WakeCondition(condition_type="unknown_type_xyz")
        assert _default_check(wc, job) is False

    def test_custom_checker_exception(self):
        def bad_fn(params, **kw):
            raise RuntimeError("boom")
        register_condition("bad_fn", bad_fn)
        job = HibernateableJob(agent_id="a")
        wc = WakeCondition(condition_type="custom", check_fn="bad_fn")
        assert _default_check(wc, job) is False


# ── HibernationManager tests ──────────────────────────────────────────


class TestHibernationManager:
    @pytest.fixture
    def mgr(self, tmp_path):
        return HibernationManager(state_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_create_job(self, mgr):
        job = await mgr.create_job(agent_id="agent-1")
        assert job.state == JobState.PENDING
        assert job.agent_id == "agent-1"

        fetched = await mgr.get_job(job.job_id)
        assert fetched is not None
        assert fetched.job_id == job.job_id

    @pytest.mark.asyncio
    async def test_hibernate_and_wake(self, mgr):
        job = await mgr.create_job(agent_id="agent-1")
        # Must transition to RUNNING first
        await mgr.transition(job.job_id, JobState.RUNNING)

        # Hibernate
        wc = WakeCondition(condition_type="time", params={"wait_seconds": 1})
        hibernated = await mgr.hibernate(
            job.job_id,
            context_snapshot={"conversation": ["hello", "world"]},
            wake_condition=wc,
        )
        assert hibernated.state == JobState.WAITING_EXTERNAL
        assert hibernated.hibernated_at is not None
        assert hibernated.context_snapshot == {"conversation": ["hello", "world"]}

        # Wake
        woken = await mgr.wake(job.job_id)
        assert woken.state == JobState.READY_TO_RESUME
        assert woken.resumed_at is not None

    @pytest.mark.asyncio
    async def test_invalid_transition_raises(self, mgr):
        job = await mgr.create_job(agent_id="agent-1")
        with pytest.raises(ValueError, match="Invalid state transition"):
            await mgr.transition(job.job_id, JobState.COMPLETED)

    @pytest.mark.asyncio
    async def test_hibernate_nonexistent_job(self, mgr):
        await mgr.init_db()
        with pytest.raises(ValueError, match="not found"):
            await mgr.hibernate(
                "nonexistent",
                context_snapshot={},
                wake_condition=WakeCondition(condition_type="time"),
            )

    @pytest.mark.asyncio
    async def test_check_conditions_wakes_ready_jobs(self, mgr):
        # Create and hibernate a job with an already-met time condition
        job = await mgr.create_job(agent_id="agent-1")
        await mgr.transition(job.job_id, JobState.RUNNING)

        wc = WakeCondition(condition_type="time", params={"wait_seconds": 0})
        await mgr.hibernate(
            job.job_id,
            context_snapshot={"data": "test"},
            wake_condition=wc,
        )

        woken = await mgr.check_conditions()
        assert woken == 1

        updated = await mgr.get_job(job.job_id)
        assert updated.state == JobState.READY_TO_RESUME

    @pytest.mark.asyncio
    async def test_check_conditions_no_wake_when_not_met(self, mgr):
        job = await mgr.create_job(agent_id="agent-1")
        await mgr.transition(job.job_id, JobState.RUNNING)

        wc = WakeCondition(condition_type="time", params={"wait_seconds": 99999})
        await mgr.hibernate(
            job.job_id,
            context_snapshot={},
            wake_condition=wc,
        )

        woken = await mgr.check_conditions()
        assert woken == 0

    @pytest.mark.asyncio
    async def test_timeout_check(self, mgr):
        job = await mgr.create_job(
            agent_id="agent-1",
            max_wait_seconds=1,
        )
        await mgr.transition(job.job_id, JobState.RUNNING)

        wc = WakeCondition(condition_type="time", params={"wait_seconds": 99999})
        await mgr.hibernate(
            job.job_id,
            context_snapshot={},
            wake_condition=wc,
        )

        # Manually backdate hibernated_at to trigger timeout
        fetched = await mgr.get_job(job.job_id)
        fetched.hibernated_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        await mgr._save_job(fetched)

        timed_out = await mgr.timeout_check()
        assert timed_out == 1

        updated = await mgr.get_job(job.job_id)
        assert updated.state == JobState.FAILED
        assert updated.metadata.get("failure_reason") == "timeout"

    @pytest.mark.asyncio
    async def test_get_ready_jobs(self, mgr):
        # Create two jobs, only one reaches READY_TO_RESUME
        job1 = await mgr.create_job(agent_id="agent-1")
        job2 = await mgr.create_job(agent_id="agent-2")

        await mgr.transition(job1.job_id, JobState.RUNNING)
        wc = WakeCondition(condition_type="time", params={"wait_seconds": 0})
        await mgr.hibernate(job1.job_id, context_snapshot={}, wake_condition=wc)
        await mgr.wake(job1.job_id)

        ready = await mgr.get_ready_jobs()
        assert len(ready) == 1
        assert ready[0].job_id == job1.job_id

    @pytest.mark.asyncio
    async def test_list_jobs_filter_by_state(self, mgr):
        await mgr.create_job(agent_id="a")
        job2 = await mgr.create_job(agent_id="b")
        await mgr.transition(job2.job_id, JobState.RUNNING)

        pending = await mgr.list_jobs(state=JobState.PENDING)
        running = await mgr.list_jobs(state=JobState.RUNNING)
        assert len(pending) == 1
        assert len(running) == 1

    @pytest.mark.asyncio
    async def test_list_jobs_filter_by_agent(self, mgr):
        await mgr.create_job(agent_id="alpha")
        await mgr.create_job(agent_id="beta")
        await mgr.create_job(agent_id="alpha")

        alpha_jobs = await mgr.list_jobs(agent_id="alpha")
        assert len(alpha_jobs) == 2

    @pytest.mark.asyncio
    async def test_count_jobs(self, mgr):
        await mgr.create_job(agent_id="a")
        await mgr.create_job(agent_id="b")

        total = await mgr.count_jobs()
        assert total == 2

        pending = await mgr.count_jobs(state=JobState.PENDING)
        assert pending == 2

    @pytest.mark.asyncio
    async def test_context_snapshot_persistence(self, mgr):
        """Verify that complex context snapshots survive serialisation."""
        snapshot = {
            "conversation_history": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there"},
            ],
            "working_memory": {"key": [1, 2, 3]},
            "intermediate_results": None,
            "nested": {"deep": {"value": True}},
        }
        job = await mgr.create_job(agent_id="a", context_snapshot=snapshot)
        await mgr.transition(job.job_id, JobState.RUNNING)

        wc = WakeCondition(condition_type="time", params={"wait_seconds": 0})
        await mgr.hibernate(job.job_id, context_snapshot=snapshot, wake_condition=wc)

        fetched = await mgr.get_job(job.job_id)
        assert fetched.context_snapshot == snapshot


# ── Full lifecycle integration test ────────────────────────────────────


class TestHibernationFullCycle:
    @pytest.mark.asyncio
    async def test_full_hibernate_wake_cycle(self, tmp_path):
        """End-to-end: create → run → hibernate → check → wake → resume → complete."""
        mgr = HibernationManager(state_dir=tmp_path)

        # 1. Create
        job = await mgr.create_job(
            agent_id="agent-full-cycle",
            context_snapshot={"initial": True},
            metadata={"original_description": "Test task"},
        )
        assert job.state == JobState.PENDING

        # 2. Start running
        job = await mgr.transition(job.job_id, JobState.RUNNING)
        assert job.state == JobState.RUNNING

        # 3. Hibernate (agent is waiting for something)
        snapshot = {"conversation": ["step1", "step2"], "working": {"partial_result": 42}}
        wc = WakeCondition(
            condition_type="time",
            params={"wait_seconds": 0},  # instant wake for test
            poll_interval_seconds=1,
        )
        job = await mgr.hibernate(job.job_id, snapshot, wc)
        assert job.state == JobState.WAITING_EXTERNAL
        assert job.hibernated_at is not None

        # 4. Check conditions (should wake immediately since wait_seconds=0)
        woken = await mgr.check_conditions()
        assert woken == 1

        # 5. Verify state
        job = await mgr.get_job(job.job_id)
        assert job.state == JobState.READY_TO_RESUME
        assert job.resumed_at is not None
        assert job.context_snapshot == snapshot

        # 6. Resume (transition back to running)
        job = await mgr.transition(job.job_id, JobState.RUNNING)
        assert job.state == JobState.RUNNING

        # 7. Complete
        job = await mgr.transition(job.job_id, JobState.COMPLETED)
        assert job.state == JobState.COMPLETED

        # 8. Terminal — can't go anywhere
        with pytest.raises(ValueError, match="Invalid state transition"):
            await mgr.transition(job.job_id, JobState.RUNNING)

        await mgr.close()

    @pytest.mark.asyncio
    async def test_file_based_wake_cycle(self, tmp_path):
        """Hibernate waiting for a file, create it, then check."""
        mgr = HibernationManager(state_dir=tmp_path)
        marker = tmp_path / "ready.flag"

        job = await mgr.create_job(agent_id="file-waiter")
        await mgr.transition(job.job_id, JobState.RUNNING)

        wc = WakeCondition(
            condition_type="file_exists",
            params={"path": str(marker)},
        )
        await mgr.hibernate(job.job_id, {"state": "waiting"}, wc)

        # File doesn't exist yet
        assert await mgr.check_conditions() == 0

        # Create the marker file
        marker.write_text("ready")

        # Now it should wake
        assert await mgr.check_conditions() == 1
        job = await mgr.get_job(job.job_id)
        assert job.state == JobState.READY_TO_RESUME

        await mgr.close()
