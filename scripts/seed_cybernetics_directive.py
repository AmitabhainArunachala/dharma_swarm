#!/usr/bin/env python3
"""Seed the Cybernetics Directive into the live thinkodynamic task system."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from dharma_swarm.thinkodynamic_director import DirectorOpportunity, ThinkodynamicDirector


HOME = Path.home()
REPO_ROOT = HOME / "dharma_swarm"
STATE_DIR = HOME / ".dharma"

MISSION_DOC = REPO_ROOT / "docs" / "missions" / "CYBERNETIC_DIRECTIVE.md"
SEMANTIC_PLAN = HOME / ".claude" / "projects" / "-Users-dhyana" / "memory" / "semantic_population_plan.md"
EVOLUTION_LOG = REPO_ROOT / "docs" / "missions" / "EVOLUTION_META_LOG_2026-03-21.md"
VSM_GOVERNANCE = REPO_ROOT / "docs" / "telos-engine" / "07_VSM_GOVERNANCE.md"


def _existing_evidence_paths() -> list[str]:
    paths = [MISSION_DOC, SEMANTIC_PLAN, EVOLUTION_LOG, VSM_GOVERNANCE]
    return [str(path) for path in paths if path.exists()]


def _build_opportunity() -> DirectorOpportunity:
    return DirectorOpportunity(
        opportunity_id=f"cybernetics-directive-{int(time.time())}",
        theme="cybernetics",
        title="Activate the Cybernetics Directive",
        thesis=(
            "Turn cybernetic theory, telos policy, context engineering, and "
            "audit pressure into an active governance subsystem that can keep "
            "diagnosing and upgrading dharma_swarm."
        ),
        why_now=(
            "The semantic population plan and the repo's own audits converge on "
            "the same point: the governance layer remains partially disconnected "
            "from the hot path. Seed the subsystem now so it can start compounding."
        ),
        score=999.0,
        expected_duration_min=360,
        evidence_paths=_existing_evidence_paths(),
        role_sequence=["cartographer", "architect", "general", "validator"],
    )


async def _amain() -> int:
    if not MISSION_DOC.exists():
        raise FileNotFoundError(f"Missing directive doc: {MISSION_DOC}")

    director = ThinkodynamicDirector(
        repo_root=REPO_ROOT,
        state_dir=STATE_DIR,
        mission_brief=MISSION_DOC.read_text(encoding="utf-8"),
        signal_limit=12,
        max_candidates=48,
        max_active_tasks=8,
        max_concurrent_tasks=0,
    )
    await director.init()

    cycle_id = f"seed-cybernetics-{int(time.time())}"
    workflow = director.plan_workflow(_build_opportunity(), cycle_id=cycle_id)
    tasks = await director.enqueue_workflow(workflow)

    note_lines = [
        "# Cybernetics Directive Activation",
        "",
        f"cycle_id: {cycle_id}",
        f"workflow_id: {workflow.workflow_id}",
        f"theme: {workflow.theme}",
        "",
        "Tasks seeded:",
    ]
    for task in tasks:
        note_lines.append(f"- {task.id} :: {task.title}")
    note_lines.extend(
        [
            "",
            "Evidence paths:",
            *[f"- {path}" for path in workflow.evidence_paths],
            "",
            "Steward routing:",
        ]
    )
    for task_plan in workflow.tasks:
        agents = ", ".join(task_plan.preferred_agents) or "default director routing"
        note_lines.append(f"- {task_plan.key}: {agents}")

    ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    note_path = STATE_DIR / "shared" / f"cybernetics_directive_activation_{ts}.md"
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text("\n".join(note_lines) + "\n", encoding="utf-8")

    print(f"Seeded {len(tasks)} cybernetics tasks into the task board.")
    print(f"Activation note: {note_path}")
    for task in tasks:
        print(f"- {task.id} :: {task.title}")
    return 0


def main() -> int:
    return asyncio.run(_amain())


if __name__ == "__main__":
    raise SystemExit(main())
