"""Tests for SANKALPA accountability concierge."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

# Redirect DHARMA_HOME to temp dir BEFORE any dharma_swarm imports
# so that _SANKALPA_DIR, _WITNESS_DIR, and GINKO_DIR all resolve under tmp.
_test_dharma_home = tempfile.mkdtemp()
os.environ["DHARMA_HOME"] = _test_dharma_home

import dharma_swarm.sankalpa as sankalpa_mod
from dharma_swarm.sankalpa import (
    SankalpaHandle,
    SankalpaScorecard,
    _append_jsonl,
    _read_jsonl,
    audit_agent,
    audit_fleet,
    onboard_agent,
)

# Point module-level paths to the temp DHARMA_HOME so tests are isolated.
sankalpa_mod._DHARMA_HOME = Path(_test_dharma_home)
sankalpa_mod._SANKALPA_DIR = Path(_test_dharma_home) / "sankalpa"
sankalpa_mod._WITNESS_DIR = Path(_test_dharma_home) / "witness"


@pytest.fixture(autouse=True)
def _clean_test_dirs():
    """Ensure clean state for each test."""
    import shutil

    sankalpa_dir = Path(_test_dharma_home) / "sankalpa"
    witness_dir = Path(_test_dharma_home) / "witness"
    ginko_dir = Path(_test_dharma_home) / "ginko"
    stigmergy_dir = Path(_test_dharma_home) / "stigmergy"

    for d in [sankalpa_dir, witness_dir, ginko_dir, stigmergy_dir]:
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)

    yield

    # cleanup after
    for d in [sankalpa_dir, witness_dir, ginko_dir, stigmergy_dir]:
        if d.exists():
            shutil.rmtree(d)


def _ginko_agents_dir() -> Path:
    return Path(_test_dharma_home) / "ginko" / "agents"


def _stigmergy_dir() -> Path:
    return Path(_test_dharma_home) / "stigmergy"


# ---------------------------------------------------------------------------
# Onboarding tests
# ---------------------------------------------------------------------------


class TestOnboard:
    async def test_onboard_creates_directories_and_files(self):
        handle = await onboard_agent(
            name="test-alpha",
            role="researcher",
            model="test/model-1",
            system_prompt="You are a test agent.",
            sankalpa_statement="Deliver high-quality research.",
            registry_dir=_ginko_agents_dir(),
            stigmergy_dir=_stigmergy_dir(),
        )

        # Agent dir in ginko
        assert handle.agent_dir.exists()
        assert (handle.agent_dir / "identity.json").exists()
        assert (handle.agent_dir / "prompt_variants" / "active.txt").exists()

        # Sankalpa dir
        assert handle.sankalpa_dir.exists()
        assert (handle.sankalpa_dir / "metadata.json").exists()

        # Metadata contents
        meta = json.loads((handle.sankalpa_dir / "metadata.json").read_text())
        assert meta["name"] == "test-alpha"
        assert meta["role"] == "researcher"
        assert meta["sankalpa_statement"] == "Deliver high-quality research."

    async def test_onboard_registers_in_agent_registry(self):
        from dharma_swarm.agent_registry import AgentRegistry

        handle = await onboard_agent(
            name="test-beta",
            role="coder",
            model="test/model-2",
            system_prompt="You write code.",
            registry_dir=_ginko_agents_dir(),
            stigmergy_dir=_stigmergy_dir(),
        )

        registry = AgentRegistry(agents_dir=_ginko_agents_dir())
        identity = registry.load_agent("test-beta")
        assert identity is not None
        assert identity["name"] == "test-beta"
        assert identity["role"] == "coder"
        assert identity["model"] == "test/model-2"

    async def test_onboard_leaves_stigmergy_mark(self):
        from dharma_swarm.stigmergy import StigmergyStore

        await onboard_agent(
            name="test-gamma",
            role="researcher",
            model="test/model-3",
            sankalpa_statement="Map the ecosystem.",
            registry_dir=_ginko_agents_dir(),
            stigmergy_dir=_stigmergy_dir(),
        )

        store = StigmergyStore(base_path=_stigmergy_dir())
        marks = await store.read_marks(include_test=True)
        assert len(marks) >= 1
        mark = marks[0]
        assert mark.agent == "test-gamma"
        assert "onboarded" in mark.observation.lower() or "test-gamma" in mark.observation

    async def test_onboard_writes_witness_log(self):
        await onboard_agent(
            name="test-delta",
            role="tester",
            registry_dir=_ginko_agents_dir(),
            stigmergy_dir=_stigmergy_dir(),
        )

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        witness_path = Path(_test_dharma_home) / "witness" / f"{today}.jsonl"
        assert witness_path.exists()
        entries = _read_jsonl(witness_path)
        onboard_entries = [e for e in entries if e.get("event") == "onboarded"]
        assert len(onboard_entries) >= 1
        assert onboard_entries[0]["agent"] == "test-delta"

    async def test_onboard_initializes_fitness_baseline(self):
        from dharma_swarm.agent_registry import AgentRegistry

        await onboard_agent(
            name="test-epsilon",
            role="coder",
            registry_dir=_ginko_agents_dir(),
            stigmergy_dir=_stigmergy_dir(),
        )

        registry = AgentRegistry(agents_dir=_ginko_agents_dir())
        history = registry.get_fitness_history("test-epsilon")
        assert len(history) >= 1
        assert "composite_fitness" in history[0]


# ---------------------------------------------------------------------------
# Commitment tests
# ---------------------------------------------------------------------------


class TestCommitments:
    async def _onboard(self, name: str = "commit-agent") -> SankalpaHandle:
        return await onboard_agent(
            name=name,
            role="researcher",
            registry_dir=_ginko_agents_dir(),
            stigmergy_dir=_stigmergy_dir(),
        )

    async def test_commit_creates_commitment_entry(self):
        handle = await self._onboard()
        cid = await handle.commit("Finish the report by end of day.", deadline_hours=8.0)

        assert cid.startswith("cmt_")
        commitments = _read_jsonl(handle._commitments_path)
        assert len(commitments) == 1
        assert commitments[0]["commitment_id"] == cid
        assert commitments[0]["status"] == "active"
        assert commitments[0]["promise"] == "Finish the report by end of day."

    async def test_fulfill_marks_commitment_complete(self):
        handle = await self._onboard("fulfill-agent")
        cid = await handle.commit("Write tests for sankalpa module.")
        await handle.fulfill(cid, evidence="14 tests passing in test_sankalpa.py")

        commitments = _read_jsonl(handle._commitments_path)
        assert len(commitments) == 1
        assert commitments[0]["status"] == "fulfilled"
        assert commitments[0]["evidence"] == "14 tests passing in test_sankalpa.py"
        assert commitments[0]["progress_pct"] == 100.0

    async def test_fulfill_nonexistent_raises(self):
        handle = await self._onboard("error-agent")
        with pytest.raises(ValueError, match="not found"):
            await handle.fulfill("cmt_nonexistent")

    async def test_report_progress(self):
        handle = await self._onboard("progress-agent")
        cid = await handle.commit("Build the entire pipeline.")
        await handle.report_progress(cid, "Schema designed.", pct=25.0)
        await handle.report_progress(cid, "Core logic done.", pct=75.0)

        commitments = _read_jsonl(handle._commitments_path)
        assert commitments[0]["progress_pct"] == 75.0
        notes = commitments[0]["progress_notes"]
        assert len(notes) == 2
        assert notes[0]["pct"] == 25.0
        assert notes[1]["pct"] == 75.0

    async def test_overdue_commitments_detected(self):
        handle = await self._onboard("overdue-agent")
        # Create a commitment with a deadline in the past
        cid = await handle.commit("This is already late.", deadline_hours=0.0)

        # Small hack: rewrite the deadline to the past
        entries = _read_jsonl(handle._commitments_path)
        past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        entries[0]["deadline"] = past
        handle._rewrite_commitments(entries)

        overdue = await handle.get_own_commitments(status="overdue")
        assert len(overdue) == 1
        assert overdue[0]["commitment_id"] == cid

    async def test_get_own_commitments_filters_by_status(self):
        handle = await self._onboard("filter-agent")
        cid1 = await handle.commit("Task A")
        cid2 = await handle.commit("Task B")
        await handle.fulfill(cid1, evidence="Done.")

        active = await handle.get_own_commitments(status="active")
        fulfilled = await handle.get_own_commitments(status="fulfilled")
        all_c = await handle.get_own_commitments(status="all")

        assert len(fulfilled) == 1
        assert fulfilled[0]["commitment_id"] == cid1
        assert len(active) == 1
        assert active[0]["commitment_id"] == cid2
        assert len(all_c) == 2


# ---------------------------------------------------------------------------
# Action logging and history tests
# ---------------------------------------------------------------------------


class TestActionLogging:
    async def test_log_action_wraps_registry(self):
        from dharma_swarm.agent_registry import AgentRegistry

        handle = await onboard_agent(
            name="action-agent",
            role="coder",
            registry_dir=_ginko_agents_dir(),
            stigmergy_dir=_stigmergy_dir(),
        )

        await handle.log_action("Refactored module X", success=True, tokens=500)
        await handle.log_action("Failed to parse config", success=False, tokens=100)

        registry = AgentRegistry(agents_dir=_ginko_agents_dir())
        identity = registry.load_agent("action-agent")
        assert identity["tasks_completed"] == 1
        assert identity["tasks_failed"] == 1

    async def test_get_own_history_returns_actions(self):
        handle = await onboard_agent(
            name="history-agent",
            role="general",
            registry_dir=_ginko_agents_dir(),
            stigmergy_dir=_stigmergy_dir(),
        )

        await handle.log_action("Task 1", success=True)
        await handle.log_action("Task 2", success=True)
        await handle.log_action("Task 3", success=False)

        history = await handle.get_own_history(limit=2)
        assert len(history) == 2
        # Should return the last 2
        assert history[0]["task"] == "Task 2"
        assert history[1]["task"] == "Task 3"


# ---------------------------------------------------------------------------
# Stigmergy and witness tests
# ---------------------------------------------------------------------------


class TestStigmeryAndWitness:
    async def test_leave_trace_creates_stigmergy_mark(self):
        from dharma_swarm.stigmergy import StigmergyStore

        handle = await onboard_agent(
            name="trace-agent",
            role="researcher",
            registry_dir=_ginko_agents_dir(),
            stigmergy_dir=_stigmergy_dir(),
        )

        # Patch the store's base_path to use our test dir
        with patch.object(
            sankalpa_mod,
            "_SANKALPA_DIR",
            Path(_test_dharma_home) / "sankalpa",
        ):
            # leave_trace constructs the store path from sankalpa_dir
            # We need to ensure it goes to our test stigmergy dir
            handle_stigmergy_base = handle.sankalpa_dir.parent.parent / "stigmergy"
            handle_stigmergy_base.mkdir(parents=True, exist_ok=True)

            await handle.leave_trace(
                "Discovered interesting pattern in swarm coordination dynamics.",
                salience=0.8,
            )

        store = StigmergyStore(base_path=handle.sankalpa_dir.parent.parent / "stigmergy")
        marks = await store.read_marks(include_test=True)
        trace_marks = [m for m in marks if m.agent == "trace-agent"]
        assert len(trace_marks) >= 1
        assert "pattern" in trace_marks[0].observation.lower()

    async def test_witness_appends_to_log(self):
        handle = await onboard_agent(
            name="witness-agent",
            role="tester",
            registry_dir=_ginko_agents_dir(),
            stigmergy_dir=_stigmergy_dir(),
        )

        await handle.witness("test_completed", "All 14 tests passed.")

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        witness_path = Path(_test_dharma_home) / "witness" / f"{today}.jsonl"
        entries = _read_jsonl(witness_path)
        witness_entries = [
            e for e in entries
            if e.get("agent") == "witness-agent" and e.get("event") == "test_completed"
        ]
        assert len(witness_entries) == 1
        assert witness_entries[0]["detail"] == "All 14 tests passed."


# ---------------------------------------------------------------------------
# Scorecard and audit tests
# ---------------------------------------------------------------------------


class TestScorecard:
    async def test_scorecard_accuracy(self):
        handle = await onboard_agent(
            name="score-agent",
            role="researcher",
            sankalpa_statement="I will score perfectly.",
            registry_dir=_ginko_agents_dir(),
            stigmergy_dir=_stigmergy_dir(),
        )

        # Make some commitments
        cid1 = await handle.commit("Task A", deadline_hours=24.0)
        cid2 = await handle.commit("Task B", deadline_hours=24.0)
        await handle.fulfill(cid1, evidence="Done A")

        # Log some actions
        await handle.log_action("Action 1", success=True, tokens=100)
        await handle.log_action("Action 2", success=True, tokens=200)
        await handle.log_action("Action 3", success=False, tokens=50)

        scorecard = await handle.get_scorecard()

        assert isinstance(scorecard, SankalpaScorecard)
        assert scorecard.agent_name == "score-agent"
        assert scorecard.total_actions == 3
        # 2 success out of 3 -> ~0.6667
        assert 0.6 < scorecard.success_rate < 0.7
        assert scorecard.commitments_made == 2
        assert scorecard.commitments_fulfilled == 1
        assert scorecard.commitments_overdue == 0
        assert scorecard.fulfillment_rate == 0.5
        assert scorecard.sankalpa_statement == "I will score perfectly."

    async def test_audit_agent_without_handle(self):
        await onboard_agent(
            name="audit-target",
            role="coder",
            sankalpa_statement="Will write clean code.",
            registry_dir=_ginko_agents_dir(),
            stigmergy_dir=_stigmergy_dir(),
        )

        scorecard = await audit_agent("audit-target", registry_dir=_ginko_agents_dir())
        assert scorecard.agent_name == "audit-target"
        assert scorecard.sankalpa_statement == "Will write clean code."

    async def test_audit_fleet_sorts_by_fulfillment(self):
        # Onboard two agents, give one better fulfillment
        h1 = await onboard_agent(
            name="fleet-a",
            role="researcher",
            registry_dir=_ginko_agents_dir(),
            stigmergy_dir=_stigmergy_dir(),
        )
        h2 = await onboard_agent(
            name="fleet-b",
            role="coder",
            registry_dir=_ginko_agents_dir(),
            stigmergy_dir=_stigmergy_dir(),
        )

        # fleet-a: 1/2 fulfilled
        cid_a1 = await h1.commit("A task 1")
        cid_a2 = await h1.commit("A task 2")
        await h1.fulfill(cid_a1, evidence="Done")

        # fleet-b: 2/2 fulfilled
        cid_b1 = await h2.commit("B task 1")
        cid_b2 = await h2.commit("B task 2")
        await h2.fulfill(cid_b1, evidence="Done")
        await h2.fulfill(cid_b2, evidence="Done")

        fleet = await audit_fleet(registry_dir=_ginko_agents_dir())
        assert len(fleet) == 2
        # fleet-b (100%) should be first, fleet-a (50%) second
        assert fleet[0].agent_name == "fleet-b"
        assert fleet[0].fulfillment_rate == 1.0
        assert fleet[1].agent_name == "fleet-a"
        assert fleet[1].fulfillment_rate == 0.5
