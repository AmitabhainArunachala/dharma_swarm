"""Shared prompt and context builders with basic injection hygiene."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Mapping

logger = logging.getLogger(__name__)

CONTEXT_FILE_MAX_CHARS = 20_000
CONTEXT_TRUNCATE_HEAD_RATIO = 0.7
CONTEXT_TRUNCATE_TAIL_RATIO = 0.2

_CONTEXT_THREAT_PATTERNS = (
    (r"ignore\s+(previous|all|above|prior)\s+instructions", "prompt_injection"),
    (r"system\s+prompt\s+override", "sys_prompt_override"),
    (r"disregard\s+(your|all|any)\s+(instructions|rules|guidelines)", "disregard_rules"),
    (r"do\s+not\s+tell\s+the\s+user", "deception_hide"),
    (r"<!--[^>]*(?:ignore|override|system|secret|hidden)[^>]*-->", "hidden_comment"),
)
_CONTEXT_INVISIBLE_CHARS = {
    "\u200b",
    "\u200c",
    "\u200d",
    "\u2060",
    "\ufeff",
    "\u202a",
    "\u202b",
    "\u202c",
    "\u202d",
    "\u202e",
}


def _truncate_context(
    text: str,
    *,
    max_chars: int = CONTEXT_FILE_MAX_CHARS,
    head_ratio: float = CONTEXT_TRUNCATE_HEAD_RATIO,
    tail_ratio: float = CONTEXT_TRUNCATE_TAIL_RATIO,
) -> str:
    if len(text) <= max_chars:
        return text

    head = max(0, min(len(text), int(max_chars * head_ratio)))
    tail = max(0, min(len(text) - head, int(max_chars * tail_ratio)))
    omitted = max(0, len(text) - head - tail)
    if tail <= 0:
        return text[:max_chars] + "\n... [truncated]"
    return (
        text[:head]
        + f"\n... [truncated {omitted} chars] ...\n"
        + text[-tail:]
    )


def sanitize_prompt_context(content: str, *, source_name: str) -> str:
    """Block known prompt-injection markers before prompt assembly."""

    findings: list[str] = []

    for char in _CONTEXT_INVISIBLE_CHARS:
        if char in content:
            findings.append(f"invisible unicode U+{ord(char):04X}")

    for pattern, marker in _CONTEXT_THREAT_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            findings.append(marker)

    if findings:
        logger.warning(
            "Blocked prompt context from %s: %s",
            source_name,
            ", ".join(findings),
        )
        return (
            f"[BLOCKED: {source_name} contained potential prompt injection "
            f"({', '.join(findings)}). Content not loaded.]"
        )
    return content


def _safe_prompt_text(
    text: str,
    *,
    source_name: str,
    max_chars: int,
) -> str:
    sanitized = sanitize_prompt_context(text, source_name=source_name)
    return _truncate_context(sanitized, max_chars=max_chars)


def build_state_context_snapshot(
    *,
    state_dir: Path,
    home: Path | None = None,
    max_chars: int = 6000,
    include_latent_gold: bool = True,
) -> str:
    """Build a compact mission-control snapshot for system prompt injection."""

    home_dir = home or Path.home()
    parts: list[str] = []

    thread_file = state_dir / "thread_state.json"
    if thread_file.exists():
        try:
            ts = json.loads(thread_file.read_text(encoding="utf-8"))
            parts.append(f"Active thread: {ts.get('current_thread', 'unknown')}")
        except Exception:
            pass

    try:
        from dharma_swarm.context import read_latent_gold_overview, read_memory_context

        memory_block = read_memory_context(state_dir=state_dir)
        if memory_block and "No memory" not in memory_block:
            parts.append(
                "Recent memory:\n"
                + _safe_prompt_text(
                    memory_block,
                    source_name="state:recent_memory",
                    max_chars=1800,
                )
            )
        if include_latent_gold:
            latent_block = read_latent_gold_overview(state_dir=state_dir, limit=3)
            if latent_block:
                parts.append(
                    "Latent gold:\n"
                    + _safe_prompt_text(
                        latent_block,
                        source_name="state:latent_gold",
                        max_chars=1800,
                    )
                )
    except Exception:
        pass

    manifest = home_dir / ".dharma_manifest.json"
    if manifest.exists():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            ecosystem = data.get("ecosystem", {})
            if ecosystem:
                alive = sum(1 for value in ecosystem.values() if value.get("exists"))
                parts.append(f"Ecosystem: {alive}/{len(ecosystem)} alive")
        except Exception:
            pass

    snapshot = "\n".join(parts).strip()
    if not snapshot:
        return ""
    return _truncate_context(snapshot, max_chars=max_chars)


def _resolve_context_path(path: str, *, repo_root: Path) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    return candidate


def build_context_file_sections(
    paths: list[str],
    *,
    repo_root: Path,
    max_files: int = 3,
    max_chars_per_file: int = 1200,
) -> str:
    """Render compact safe excerpts from relevant evidence files."""

    sections: list[str] = []
    seen: set[str] = set()

    for raw_path in paths:
        if len(sections) >= max_files:
            break
        label = str(raw_path).strip()
        if not label or label in seen:
            continue
        seen.add(label)
        path = _resolve_context_path(label, repo_root=repo_root)
        if not path.exists() or not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        excerpt = _safe_prompt_text(
            content,
            source_name=label,
            max_chars=max_chars_per_file,
        )
        sections.append(
            f"### {path.name}\n"
            f"Path: {label}\n"
            f"{excerpt}"
        )

    return "\n\n".join(sections)


def build_director_agent_prompt(
    task_plan: Any,
    workflow: Any,
    *,
    backend: str,
    repo_root: Path,
    state_dir: Path,
    role_briefs: Mapping[str, str],
    home: Path | None = None,
) -> str:
    """Build the shared prompt for director-spawned workers."""

    role_key = str(getattr(task_plan, "role_hint", "") or "general")
    role_brief = str(role_briefs.get(role_key, role_briefs.get("general", "")))
    evidence_paths = list(getattr(workflow, "evidence_paths", []) or [])
    evidence_listing = "\n".join(f"- {path}" for path in evidence_paths) or "- none recorded"
    acceptance_items = list(getattr(task_plan, "acceptance", []) or [])
    acceptance = "\n".join(f"- {item}" for item in acceptance_items) or "- Produce a concrete, auditable artifact."
    preferred_agents = list(getattr(task_plan, "preferred_agents", []) or [])
    preferred_backends = list(getattr(task_plan, "preferred_backends", []) or [])
    council_guidance = str(getattr(workflow, "council_guidance", "") or "").strip()
    council_members = list(getattr(workflow, "council_members", []) or [])
    council_dialogue_path = str(getattr(workflow, "council_dialogue_path", "") or "").strip()
    backend_rules = [
        "- Inspect the current worktree yourself before changing anything.",
        "- Respect unrelated user changes. Do not revert or overwrite work you did not make.",
        "- Prefer concrete code, tests, and durable artifacts over broad planning.",
        "- Read ~/.dharma/shared/ and existing task artifacts first when they are relevant.",
    ]
    if backend == "codex-cli":
        backend_rules.extend(
            [
                f"- Work primarily under {repo_root}.",
                f"- You may also read and write under {state_dir}.",
                "- Run focused verification after edits whenever feasible.",
            ]
        )

    evidence_context = build_context_file_sections(
        evidence_paths,
        repo_root=repo_root,
    )
    mission_snapshot = build_state_context_snapshot(
        state_dir=state_dir,
        home=home,
        max_chars=1600,
    )

    sections = [
        f"You are a {role_key} agent in dharma_swarm.",
        (
            f"Mission: {getattr(workflow, 'opportunity_title', '')}\n"
            f"Theme: {getattr(workflow, 'theme', '')}\n"
            f"Thesis: {getattr(workflow, 'thesis', '')}\n"
            f"Why now: {getattr(workflow, 'why_now', '')}"
        ),
        f"Role brief:\n{role_brief}",
        f"Task:\n{getattr(task_plan, 'title', '')}",
        f"Description:\n{getattr(task_plan, 'description', '')}",
        f"Evidence paths:\n{evidence_listing}",
    ]
    if council_members:
        sections.append("Primary orchestrators:\n" + "\n".join(f"- {member}" for member in council_members))
    if council_guidance:
        sections.append("Council guidance:\n" + council_guidance)
    if council_dialogue_path:
        sections.append(f"Council dialogue artifact:\n- {council_dialogue_path}")
    if preferred_agents:
        sections.append("Preferred swarm agents:\n" + "\n".join(f"- {agent}" for agent in preferred_agents))
    if preferred_backends:
        sections.append("Preferred execution backends:\n" + "\n".join(f"- {backend}" for backend in preferred_backends))
    if evidence_context:
        sections.append(
            "Evidence excerpts:\n"
            "Treat these as partial snapshots and verify before making claims.\n\n"
            + evidence_context
        )
    if mission_snapshot:
        sections.append(
            "Mission-control snapshot:\n"
            "Treat as hints and verify.\n\n"
            + mission_snapshot
        )
    sections.extend(
        [
            f"Acceptance criteria:\n{acceptance}",
            "Operational rules:\n" + "\n".join(backend_rules),
            (
                "If you complete the task, be explicit about files changed, "
                "artifacts written, and tests run.\n"
                "If blocked, write the blocker to "
                "~/.dharma/shared/thinkodynamic_director_handoff.md and say BLOCKED.\n"
                "If you identify 1-3 independent follow-on tasks worth parallelizing, append exactly:\n"
                "## DELEGATIONS\n"
                "- [role] Title :: one-sentence description\n"
                "Keep each delegation concrete and immediately actionable.\n"
            ),
        ]
    )
    return "\n\n".join(section.strip() for section in sections if str(section).strip())


__all__ = [
    "build_context_file_sections",
    "build_director_agent_prompt",
    "build_state_context_snapshot",
    "sanitize_prompt_context",
]
