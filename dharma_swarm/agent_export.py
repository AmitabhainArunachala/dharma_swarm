"""Canonical agent schema and pure export adapters.

This module intentionally stops at rendering artifacts. Installation into
tool-specific directories remains a separate concern, mirroring the strongest
architectural lesson from agency-agents: conversion and installation should not
be the same layer.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable


class ExportTarget(str, Enum):
    CLAUDE_CODE = "claude-code"
    COPILOT = "copilot"
    OPENCODE = "opencode"
    CURSOR = "cursor"
    QWEN = "qwen"


@dataclass(frozen=True)
class CanonicalAgentSpec:
    """Canonical source-of-truth agent definition."""

    name: str
    description: str
    system_prompt: str
    color: str = "#6B7280"
    emoji: str = "🤖"
    vibe: str = ""
    slug: str = ""
    tags: tuple[str, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Agent name must not be empty.")
        if not self.description.strip():
            raise ValueError("Agent description must not be empty.")
        if not self.system_prompt.strip():
            raise ValueError("Agent system_prompt must not be empty.")
        if not self.slug:
            object.__setattr__(self, "slug", slugify(self.name))


@dataclass(frozen=True)
class ExportArtifact:
    target: ExportTarget
    relative_path: Path
    content: str


_NAMED_COLORS: dict[str, str] = {
    "blue": "#3498DB",
    "green": "#2ECC71",
    "red": "#E74C3C",
    "purple": "#9B59B6",
    "orange": "#F39C12",
    "cyan": "#00FFFF",
    "teal": "#008080",
    "indigo": "#6366F1",
    "pink": "#E84393",
    "gold": "#EAB308",
    "amber": "#F59E0B",
    "yellow": "#EAB308",
    "gray": "#6B7280",
}


def slugify(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def normalize_hex_color(value: str) -> str:
    color = value.strip().lower()
    mapped = _NAMED_COLORS.get(color, color)
    normalized = mapped.lower()
    if re.fullmatch(r"#[0-9a-f]{6}", normalized):
        return mapped.upper()
    if re.fullmatch(r"[0-9a-f]{6}", normalized):
        return f"#{mapped.upper()}"
    return "#6B7280"


def render_agent(spec: CanonicalAgentSpec, target: ExportTarget) -> ExportArtifact:
    if target in {ExportTarget.CLAUDE_CODE, ExportTarget.COPILOT, ExportTarget.QWEN}:
        return ExportArtifact(target, _raw_relative_path(target, spec), _render_raw_markdown(spec))
    if target is ExportTarget.OPENCODE:
        return ExportArtifact(target, Path("opencode/agents") / f"{spec.slug}.md", _render_opencode(spec))
    if target is ExportTarget.CURSOR:
        return ExportArtifact(target, Path("cursor/rules") / f"{spec.slug}.mdc", _render_cursor_rule(spec))
    raise ValueError(f"Unsupported export target: {target}")


def render_all(
    spec: CanonicalAgentSpec,
    targets: Iterable[ExportTarget] | None = None,
) -> list[ExportArtifact]:
    selected = tuple(targets) if targets is not None else tuple(ExportTarget)
    return [render_agent(spec, target) for target in selected]


def _raw_relative_path(target: ExportTarget, spec: CanonicalAgentSpec) -> Path:
    if target is ExportTarget.CLAUDE_CODE:
        return Path("claude-code") / f"{spec.slug}.md"
    if target is ExportTarget.COPILOT:
        return Path("copilot") / f"{spec.slug}.md"
    return Path("qwen/agents") / f"{spec.slug}.md"


def _render_raw_markdown(spec: CanonicalAgentSpec) -> str:
    frontmatter = {
        "name": spec.name,
        "description": spec.description,
        "color": spec.color,
        "emoji": spec.emoji,
        "vibe": spec.vibe,
    }
    if spec.tags:
        frontmatter["tags"] = list(spec.tags)
    for key, value in spec.metadata.items():
        frontmatter[key] = value
    return f"{_frontmatter(frontmatter)}\n{spec.system_prompt.strip()}\n"


def _render_opencode(spec: CanonicalAgentSpec) -> str:
    frontmatter = {
        "name": spec.name,
        "description": spec.description,
        "mode": "subagent",
        "color": normalize_hex_color(spec.color),
    }
    return f"{_frontmatter(frontmatter)}\n{spec.system_prompt.strip()}\n"


def _render_cursor_rule(spec: CanonicalAgentSpec) -> str:
    frontmatter = {
        "description": spec.description,
        "globs": "",
        "alwaysApply": False,
    }
    return f"{_frontmatter(frontmatter)}\n{spec.system_prompt.strip()}\n"


def _frontmatter(payload: dict[str, object]) -> str:
    lines = ["---"]
    for key, value in payload.items():
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines)
