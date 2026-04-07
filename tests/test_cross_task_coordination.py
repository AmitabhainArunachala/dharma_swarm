"""Tests for Phase 3: Cross-task composability (shared artifact coordination).

Validates:
1. _persist_result creates a shared artifact with a predictable name
2. The shared artifact contains the task title, ID, and result content
3. A second task can discover the first task's output via the shared dir
4. The shared artifact slug is deterministic (same task → same path)
"""

import asyncio
import json
import re
import time
from pathlib import Path

import pytest

from dharma_swarm.models import (
    AgentRole,
    AgentState,
    AgentStatus,
    GateDecision,
    Task,
    TaskStatus,
)
from dharma_swarm.orchestrator import Orchestrator


# ---------- helpers ----------

def _slugify(title: str) -> str:
    """Mirror the slug logic from orchestrator._persist_result."""
    return re.sub(r'[^a-z0-9]+', '_', (title or 'task').lower()).strip('_')[:40]


class _MinimalBoard:
    async def get_ready_tasks(self):
        return []

    async def update_task(self, task_id, **fields):
        pass

    async def get(self, task_id):
        return None

    async def list_tasks(self, **kw):
        return []


class _MinimalPool:
    async def get_idle_agents(self):
        return []

    async def assign(self, aid, tid):
        pass

    async def release(self, aid):
        pass

    async def get_result(self, aid):
        return None

    async def get(self, aid):
        return None


# ---------- fixtures ----------

@pytest.fixture(autouse=True)
def fast_dispatch_gate():
    """Default orchestrator dispatch gates to ALLOW for non-gate tests."""
    from unittest.mock import patch
    from dharma_swarm.telos_gates import ReflectiveGateOutcome
    from dharma_swarm.models import GateCheckResult

    allow = ReflectiveGateOutcome(
        result=GateCheckResult(
            decision=GateDecision.ALLOW,
            reason="All gates passed (test mock)",
        ),
    )
    with patch(
        "dharma_swarm.orchestrator.check_with_reflective_reroute",
        return_value=allow,
    ):
        yield allow


@pytest.fixture
def tmp_orchestrator(tmp_path):
    """Build a lightweight Orchestrator with tmp_path as its ledger root."""
    ledger_dir = tmp_path / "ledgers"
    ledger_dir.mkdir()
    orch = Orchestrator(
        task_board=_MinimalBoard(),
        agent_pool=_MinimalPool(),
        ledger_dir=ledger_dir,
        session_id="test_cross_task",
    )
    return orch


# ---------- PART 1: _persist_result creates shared artifact ----------

@pytest.mark.asyncio
async def test_persist_result_creates_shared_artifact(tmp_orchestrator):
    """After _persist_result, a shared artifact file with a predictable slug
    name must exist in the shared directory."""
    orch = tmp_orchestrator
    task = Task(
        id="abcdef1234567890",
        title="Map the self-evolving AI landscape",
        description="Research companies building self-modifying AI systems.",
    )
    result_text = "Found 12 companies building self-evolving AI systems."

    await orch._persist_result(
        agent_name="researcher-1",
        model_name="claude-sonnet",
        provider_name="anthropic",
        task=task,
        result=result_text,
    )

    shared_dir = orch._shared_dir
    slug = _slugify(task.title)
    expected_name = f"{task.id[:8]}_{slug}.md"
    artifact_path = shared_dir / expected_name

    assert artifact_path.exists(), (
        f"Expected shared artifact at {artifact_path}, "
        f"but only found: {list(shared_dir.iterdir())}"
    )


# ---------- PART 2: artifact contains title, ID, and result ----------

@pytest.mark.asyncio
async def test_shared_artifact_content(tmp_orchestrator):
    """The shared artifact must contain the task title, task ID, and full result."""
    orch = tmp_orchestrator
    task = Task(
        id="deadbeef00001111",
        title="Analyze Sakana DGM architecture",
        description="Deep dive into the Darwin Gödel Machine.",
    )
    result_text = (
        "Sakana AI released DGM in March 2025. It combines:\n"
        "1. Neural Architecture Search\n"
        "2. Self-referential code modification\n"
        "3. Automated proof verification"
    )

    await orch._persist_result(
        agent_name="viveka",
        model_name="claude-sonnet",
        provider_name="anthropic",
        task=task,
        result=result_text,
    )

    shared_dir = orch._shared_dir
    slug = _slugify(task.title)
    artifact_path = shared_dir / f"{task.id[:8]}_{slug}.md"
    content = artifact_path.read_text(encoding="utf-8")

    assert "# Analyze Sakana DGM architecture" in content, "Missing task title header"
    assert task.id in content, "Missing full task ID"
    assert "viveka" in content, "Missing agent name"
    assert "Neural Architecture Search" in content, "Missing result body"
    assert "Self-referential code modification" in content, "Missing result content"


# ---------- PART 3: second task can find first task's output ----------

@pytest.mark.asyncio
async def test_dependent_task_finds_predecessor_output(tmp_orchestrator):
    """Simulate Task A completing and Task B discovering Task A's artifact
    by listing the shared directory."""
    orch = tmp_orchestrator

    # Task A: research phase
    task_a = Task(
        id="aaaa111122223333",
        title="Research landscape companies",
        description="Find all companies in the self-evolving AI space.",
    )
    result_a = "Companies found: Sakana AI, Cognition Labs, Imbue, Adept."

    await orch._persist_result(
        agent_name="researcher-1",
        model_name="claude-sonnet",
        provider_name="anthropic",
        task=task_a,
        result=result_a,
    )

    # Task B: synthesis phase — searches shared dir for task A output
    shared_dir = orch._shared_dir
    md_files = list(shared_dir.glob("*.md"))

    # Filter to find task A's artifact (not agent notes)
    task_a_artifacts = [
        f for f in md_files
        if f.name.startswith(task_a.id[:8]) and f.name != "researcher-1_notes.md"
    ]
    assert len(task_a_artifacts) == 1, (
        f"Expected exactly 1 artifact from task A, found: {[f.name for f in md_files]}"
    )

    # Task B reads the content and verifies it can extract task A's findings
    content = task_a_artifacts[0].read_text(encoding="utf-8")
    assert "Sakana AI" in content
    assert "Cognition Labs" in content


# ---------- PART 4: slug is deterministic ----------

@pytest.mark.asyncio
async def test_shared_artifact_slug_deterministic(tmp_orchestrator):
    """Given the same task title and ID, the artifact path must be identical."""
    title = "Map the self-evolving AI landscape"
    task_id = "beef0000deadcafe"

    slug1 = _slugify(title)
    slug2 = _slugify(title)
    assert slug1 == slug2, "Slug must be deterministic"

    path1 = f"{task_id[:8]}_{slug1}.md"
    path2 = f"{task_id[:8]}_{slug2}.md"
    assert path1 == path2, "Full artifact filename must be deterministic"

    # Verify the expected value
    assert slug1 == "map_the_self_evolving_ai_landscape", f"Unexpected slug: {slug1}"
    assert path1 == "beef0000_map_the_self_evolving_ai_landscape.md"


def test_slug_strips_special_chars():
    """Slugify must handle special characters, leading/trailing separators."""
    assert _slugify("  Hello, World!  ") == "hello_world"
    assert _slugify("AI/ML — Research (2026)") == "ai_ml_research_2026"
    assert _slugify("") == "task"  # empty string falls back to 'task'
    assert _slugify(None) == "task"  # None falls back to 'task'


def test_slug_truncates_long_titles():
    """Slug must be truncated to 40 characters."""
    long_title = "a" * 100
    slug = _slugify(long_title)
    assert len(slug) <= 40


# ---------- PART 5: notes file still created alongside artifact ----------

@pytest.mark.asyncio
async def test_notes_file_and_artifact_both_created(tmp_orchestrator):
    """_persist_result must create BOTH the agent notes file and the shared artifact."""
    orch = tmp_orchestrator
    task = Task(
        id="1234abcd00005678",
        title="Compile funding data",
        description="Gather recent funding rounds.",
    )

    await orch._persist_result(
        agent_name="analyst-1",
        model_name="claude-sonnet",
        provider_name="anthropic",
        task=task,
        result="Total funding: $2.3B across 15 rounds.",
    )

    shared_dir = orch._shared_dir

    # Agent notes file
    notes = shared_dir / "analyst-1_notes.md"
    assert notes.exists(), "Agent notes file missing"

    # Shared artifact
    slug = _slugify(task.title)
    artifact = shared_dir / f"{task.id[:8]}_{slug}.md"
    assert artifact.exists(), "Shared artifact missing"

    # Both should have content
    assert len(notes.read_text()) > 0
    assert len(artifact.read_text()) > 0


# ---------- PART 6: None result skips everything ----------

@pytest.mark.asyncio
async def test_persist_result_none_skips_artifact(tmp_orchestrator):
    """When result is None, no shared artifact should be created."""
    orch = tmp_orchestrator
    task = Task(id="0000000011111111", title="Failed task")

    await orch._persist_result(
        agent_name="agent-x",
        model_name="claude-sonnet",
        provider_name="anthropic",
        task=task,
        result=None,
    )

    shared_dir = orch._shared_dir
    # shared_dir might not even exist, or be empty except maybe provenance dir
    artifacts = list(shared_dir.glob("*.md")) if shared_dir.exists() else []
    assert len(artifacts) == 0, f"No artifacts expected for None result, found: {artifacts}"
