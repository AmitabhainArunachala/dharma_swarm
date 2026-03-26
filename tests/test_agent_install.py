from __future__ import annotations

from pathlib import Path
import sys

from dharma_swarm.agent_export import CanonicalAgentSpec, ExportTarget, render_agent


def _spec() -> CanonicalAgentSpec:
    return CanonicalAgentSpec(
        name="Workflow Architect",
        description="Designs reliable multi-agent workflows.",
        system_prompt="You design workflows with clear stages and handoffs.",
        color="purple",
        emoji="🧭",
        vibe="Systematic and skeptical.",
        tags=("architecture", "workflow"),
    )


def test_install_planning_is_separate_from_execution_and_render_is_pure(tmp_path) -> None:
    from dharma_swarm.agent_install import plan_agent_install

    sys.modules.pop("dharma_swarm.agent_install", None)
    artifact = render_agent(_spec(), ExportTarget.CLAUDE_CODE)
    before = list(tmp_path.rglob("*"))

    plan = plan_agent_install(
        _spec(),
        targets=[ExportTarget.CLAUDE_CODE],
        destination_root=tmp_path,
    )

    assert artifact.relative_path.as_posix() == "claude-code/workflow-architect.md"
    assert before == list(tmp_path.rglob("*"))
    assert len(plan.entries) == 1
    assert plan.entries[0].destination == tmp_path / ".claude" / "agents" / "workflow-architect.md"


def test_install_planning_supports_supported_targets(tmp_path) -> None:
    from dharma_swarm.agent_install import plan_agent_install

    plan = plan_agent_install(
        _spec(),
        targets=list(ExportTarget),
        destination_root=tmp_path,
    )
    destinations = {entry.target: entry.destination.relative_to(tmp_path).as_posix() for entry in plan.entries}

    assert destinations[ExportTarget.CLAUDE_CODE] == ".claude/agents/workflow-architect.md"
    assert destinations[ExportTarget.COPILOT] == ".github/chatmodes/workflow-architect.md"
    assert destinations[ExportTarget.OPENCODE] == ".opencode/agents/workflow-architect.md"
    assert destinations[ExportTarget.CURSOR] == ".cursor/rules/workflow-architect.mdc"
    assert destinations[ExportTarget.QWEN] == ".qwen/agents/workflow-architect.md"


def test_execute_install_plan_writes_files_and_manifest_with_checksums(tmp_path) -> None:
    from dharma_swarm.agent_install import execute_install_plan, plan_agent_install

    plan = plan_agent_install(
        _spec(),
        targets=[ExportTarget.CLAUDE_CODE, ExportTarget.CURSOR],
        destination_root=tmp_path,
    )
    manifest = execute_install_plan(plan)
    second_manifest = execute_install_plan(plan)

    assert manifest.manifest_path.exists()
    assert all(record.destination.exists() for record in manifest.files)
    assert all(record.checksum for record in manifest.files)
    assert any(record.changed is True for record in manifest.files)
    assert all(record.changed is False for record in second_manifest.files)
