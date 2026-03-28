"""Compatibility aliases for dashboard-facing agent identifiers."""

from __future__ import annotations

AGENT_ALIASES: dict[str, str] = {
    "glm5-researcher": "glm-researcher",
    "glm5_researcher": "glm-researcher",
    "glm5-cartographer": "glm-researcher",
    "glm5_cartographer": "glm-researcher",
    "ecosystem-synthesizer": "glm-researcher",
    "ecosystem_synthesizer": "glm-researcher",
    "agent_identity_ecosystem_synthesizer": "glm-researcher",
    "kimi-k25-scout": "kimi-scout",
    "kimi_k25_scout": "kimi-scout",
    "cyber-kimi25": "kimi-scout",
    "sonnet46-operator": "sonnet-relay",
    "sonnet46_operator": "sonnet-relay",
    "qwen35-surgeon": "qwen-builder",
    "qwen35_surgeon": "qwen-builder",
    "qwen35-surgical-coder": "qwen-builder",
    "qwen35_surgical_coder": "qwen-builder",
    "qwen3.5_surgical_coder": "qwen-builder",
    "qwen3_5_surgical_coder": "qwen-builder",
    "qwen-surgeon": "qwen-builder",
}


def alias_candidates(agent_id: str) -> tuple[str, ...]:
    queue = [agent_id]
    seen: set[str] = set()
    ordered: list[str] = []

    while queue:
        current = queue.pop(0)
        if not current or current in seen:
            continue
        seen.add(current)
        ordered.append(current)

        hyphenated = current.replace("_", "-")
        underscored = current.replace("-", "_")
        mapped = AGENT_ALIASES.get(current)

        for candidate in (hyphenated, underscored, mapped):
            if candidate and candidate not in seen:
                queue.append(candidate)

    return tuple(ordered)


def matches_agent_alias(value: str | None, query: str) -> bool:
    if not value:
        return False
    left = set(alias_candidates(value))
    right = set(alias_candidates(query))
    return bool(left & right)
