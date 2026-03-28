from __future__ import annotations

import sys

from dharma_swarm.agent_export import (
    CanonicalAgentSpec,
    ExportTarget,
    normalize_hex_color,
    render_agent,
    render_all,
)


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


def test_raw_markdown_export_contains_canonical_frontmatter() -> None:
    artifact = render_agent(_spec(), ExportTarget.CLAUDE_CODE)

    assert artifact.relative_path.as_posix() == "claude-code/workflow-architect.md"
    assert 'name: "Workflow Architect"' in artifact.content
    assert 'description: "Designs reliable multi-agent workflows."' in artifact.content
    assert 'color: "purple"' in artifact.content
    assert 'emoji: "🧭"' in artifact.content
    assert 'vibe: "Systematic and skeptical."' in artifact.content
    assert 'tags: ["architecture", "workflow"]' in artifact.content
    assert "You design workflows with clear stages and handoffs." in artifact.content


def test_opencode_export_normalizes_named_colors() -> None:
    artifact = render_agent(_spec(), ExportTarget.OPENCODE)

    assert artifact.relative_path.as_posix() == "opencode/agents/workflow-architect.md"
    assert 'mode: "subagent"' in artifact.content
    assert 'color: "#9B59B6"' in artifact.content


def test_cursor_export_uses_rule_frontmatter() -> None:
    artifact = render_agent(_spec(), ExportTarget.CURSOR)

    assert artifact.relative_path.as_posix() == "cursor/rules/workflow-architect.mdc"
    assert 'description: "Designs reliable multi-agent workflows."' in artifact.content
    assert 'globs: ""' in artifact.content
    assert "alwaysApply: false" in artifact.content


def test_render_all_defaults_to_all_targets() -> None:
    artifacts = render_all(_spec())

    assert {artifact.target for artifact in artifacts} == set(ExportTarget)


def test_color_normalization_accepts_named_and_hex_values() -> None:
    assert normalize_hex_color("purple") == "#9B59B6"
    assert normalize_hex_color("#abcdef") == "#ABCDEF"
    assert normalize_hex_color("bad-color") == "#6B7280"


def test_render_agent_remains_pure_and_does_not_import_installer(tmp_path) -> None:
    sys.modules.pop("dharma_swarm.agent_install", None)

    artifact = render_agent(_spec(), ExportTarget.CLAUDE_CODE)

    assert artifact.relative_path.as_posix() == "claude-code/workflow-architect.md"
    assert list(tmp_path.rglob("*")) == []
    assert "dharma_swarm.agent_install" not in sys.modules
