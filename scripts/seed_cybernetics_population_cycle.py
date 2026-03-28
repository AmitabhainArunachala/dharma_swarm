#!/usr/bin/env python3
"""Seed the first bounded cybernetics population cycle into the task board."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from dharma_swarm.models import TaskPriority, TaskStatus
from dharma_swarm.task_board import TaskBoard


HOME = Path.home()
STATE_DIR = HOME / ".dharma"
REPO_ROOT = HOME / "dharma_swarm"
TASK_DB = STATE_DIR / "db" / "tasks.db"

MISSION_DOC = REPO_ROOT / "docs" / "missions" / "CYBERNETICS_POPULATION_CYCLE_V1.md"
SEMANTIC_PLAN = HOME / ".claude" / "projects" / "-Users-dhyana" / "memory" / "semantic_population_plan.md"
DEEP_READING_FEEDBACK = HOME / ".claude" / "projects" / "-Users-dhyana" / "memory" / "feedback_deep_reading_pipeline.md"
READING_PROTOCOL = REPO_ROOT / "docs" / "RECURSIVE_READING_PROTOCOL.md"
ASHBY_CITATIONS = REPO_ROOT / "scripts" / "seed_ashby_citations.py"
ASHBY_INGEST = REPO_ROOT / "scripts" / "ingest_ashby_claims.py"
CONTRADICTIONS = REPO_ROOT / "scripts" / "seed_contradictions.py"
POLICY_COMPILER = REPO_ROOT / "dharma_swarm" / "policy_compiler.py"

CYCLE_KEY = "cybernetics_population_v1"
BACKENDS = ["provider-fallback", "codex-cli", "claude-cli"]
PROVIDERS = ["ollama"]


def _existing_evidence_paths() -> list[str]:
    paths = [
        MISSION_DOC,
        SEMANTIC_PLAN,
        DEEP_READING_FEEDBACK,
        READING_PROTOCOL,
        ASHBY_CITATIONS,
        ASHBY_INGEST,
        CONTRADICTIONS,
        POLICY_COMPILER,
    ]
    return [str(path) for path in paths if path.exists()]


def _metadata(
    *,
    title: str,
    role_hint: str,
    preferred_agents: list[str],
    cycle_id: str,
    sequence: int,
) -> dict[str, object]:
    return {
        "source": "cybernetics_population_cycle",
        "director_theme": "cybernetics",
        "director_source_kind": "cybernetics_population",
        "director_role_hint": role_hint,
        "director_opportunity_title": "Populate the cybernetics governance stratum",
        "director_cycle_id": cycle_id,
        "population_cycle_key": CYCLE_KEY,
        "population_sequence": sequence,
        "director_preferred_agents": preferred_agents,
        "director_preferred_backends": list(BACKENDS),
        "available_provider_types": list(PROVIDERS),
        "evidence_paths": _existing_evidence_paths(),
        "mission_doc": str(MISSION_DOC),
        "task_title": title,
    }


async def _already_seeded(board: TaskBoard) -> bool:
    for status in (TaskStatus.PENDING, TaskStatus.ASSIGNED, TaskStatus.RUNNING):
        tasks = await board.list_tasks(status=status, limit=500)
        for task in tasks:
            metadata = dict(task.metadata or {})
            if metadata.get("population_cycle_key") == CYCLE_KEY:
                return True
    return False


async def _amain() -> int:
    if not MISSION_DOC.exists():
        raise FileNotFoundError(f"Missing mission doc: {MISSION_DOC}")

    board = TaskBoard(TASK_DB)
    await board.init_db()

    if await _already_seeded(board):
        print(f"{CYCLE_KEY} already seeded; refusing to duplicate.")
        return 0

    cycle_id = f"{CYCLE_KEY}-{int(time.time())}"

    task1 = await board.create(
        title="Build the cybernetics canon packet",
        description=(
            "Map the minimum viable Ashby/Conant/Beer canon for dharma_swarm. "
            "Produce a bounded canon packet that states which passages matter "
            "for PolicyCompiler, telos gates, orchestrator routing, witness/audit, "
            "and the corpus/stigmergy bridge."
        ),
        priority=TaskPriority.HIGH,
        created_by=CYCLE_KEY,
        metadata=_metadata(
            title="Build the cybernetics canon packet",
            role_hint="cartographer",
            preferred_agents=["cyber-glm5", "cyber-kimi25", "cyber-opus"],
            cycle_id=cycle_id,
            sequence=1,
        ),
    )

    task2 = await board.create(
        title="Produce stratified cybernetics extraction",
        description=(
            "Using the canon packet and the recursive reading protocol, produce "
            "a stratified extraction artifact: thesis kernel, load-bearing passages, "
            "structural DAG, and loss manifest. Do not write a generic summary."
        ),
        priority=TaskPriority.HIGH,
        created_by=CYCLE_KEY,
        depends_on=[task1.id],
        metadata=_metadata(
            title="Produce stratified cybernetics extraction",
            role_hint="architect",
            preferred_agents=["cyber-opus", "cyber-glm5", "cyber-kimi25"],
            cycle_id=cycle_id,
            sequence=2,
        ),
    )

    task3 = await board.create(
        title="Ingest cybernetics claims citations and contradictions",
        description=(
            "Convert the extraction packet into live substrate updates. Reuse or "
            "extend scripts for Ashby claim ingestion, citation seeding, and "
            "contradiction seeding so the cybernetics reading changes the "
            "DharmaCorpus and related ledgers."
        ),
        priority=TaskPriority.HIGH,
        created_by=CYCLE_KEY,
        depends_on=[task2.id],
        metadata=_metadata(
            title="Ingest cybernetics claims citations and contradictions",
            role_hint="general",
            preferred_agents=["cyber-codex", "cyber-opus", "cyber-glm5"],
            cycle_id=cycle_id,
            sequence=3,
        ),
    )

    task4 = await board.create(
        title="Force one cybernetics transmission vector into code",
        description=(
            "Choose one bounded governance-path target and push a code delta or "
            "well-specified diff proposal into it. Preferred targets: "
            "policy_compiler.py, provider_policy.py, orchestrator.py, or "
            "telos_gates.py. The reading must cash out as a runtime-facing change."
        ),
        priority=TaskPriority.HIGH,
        created_by=CYCLE_KEY,
        depends_on=[task3.id],
        metadata=_metadata(
            title="Force one cybernetics transmission vector into code",
            role_hint="surgeon",
            preferred_agents=["cyber-codex", "cyber-opus", "cyber-glm5"],
            cycle_id=cycle_id,
            sequence=4,
        ),
    )

    task5 = await board.create(
        title="Audit cybernetics metabolism and reroute",
        description=(
            "Audit whether this cycle increased governance variety or merely "
            "produced prose. Record what entered DharmaCorpus/citations/"
            "contradictions, what changed in code or routing, and what the next "
            "bounded cybernetics slice should be."
        ),
        priority=TaskPriority.NORMAL,
        created_by=CYCLE_KEY,
        depends_on=[task4.id],
        metadata=_metadata(
            title="Audit cybernetics metabolism and reroute",
            role_hint="validator",
            preferred_agents=["cyber-opus", "cyber-glm5", "cyber-kimi25", "cyber-codex"],
            cycle_id=cycle_id,
            sequence=5,
        ),
    )

    tasks = [task1, task2, task3, task4, task5]

    note_lines = [
        "# Cybernetics Population Cycle Activation",
        "",
        f"cycle_id: {cycle_id}",
        f"cycle_key: {CYCLE_KEY}",
        "",
        "Tasks seeded:",
    ]
    for task in tasks:
        note_lines.append(f"- {task.id} :: {task.title}")
    note_lines.extend(
        [
            "",
            "Evidence paths:",
            *[f"- {path}" for path in _existing_evidence_paths()],
            "",
            "Preferred providers:",
            "- ollama",
        ]
    )

    ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    note_path = STATE_DIR / "shared" / f"cybernetics_population_cycle_activation_{ts}.md"
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text("\n".join(note_lines) + "\n", encoding="utf-8")

    latest_path = STATE_DIR / "shared" / "cybernetics_population_cycle_latest.json"
    latest_path.write_text(
        json.dumps(
            {
                "cycle_id": cycle_id,
                "cycle_key": CYCLE_KEY,
                "task_ids": [task.id for task in tasks],
                "note_path": str(note_path),
                "mission_doc": str(MISSION_DOC),
            },
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Seeded {len(tasks)} tasks for {CYCLE_KEY}.")
    print(f"Activation note: {note_path}")
    print(f"Latest receipt: {latest_path}")
    for task in tasks:
        print(f"- {task.id} :: {task.title}")
    return 0


def main() -> int:
    return asyncio.run(_amain())


if __name__ == "__main__":
    raise SystemExit(main())
