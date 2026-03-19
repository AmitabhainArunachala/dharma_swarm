"""SKILL domain — evaluates SKILL.md files via structure, compression, and behavioral metrics.

Phase functions for skill-level quality assessment. Reads actual SKILL.md files
from ~/.claude/skills/*/SKILL.md, parses YAML frontmatter, and scores across
five dimensions: structure, compression, behavioral, completeness, composability.
"""

from __future__ import annotations

import os
import pwd
import re
import zlib
from pathlib import Path
from typing import Any

from dharma_swarm.metrics import MetricsAnalyzer
from dharma_swarm.models import LoopDomain


def _resolve_login_home() -> Path:
    try:
        return Path(pwd.getpwuid(os.getuid()).pw_dir).expanduser()
    except Exception:
        return Path.home()


LOGIN_HOME = _resolve_login_home()
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILLS_ROOT_CANDIDATES = (
    LOGIN_HOME / ".claude" / "skills",
    _REPO_ROOT / ".claude" / "skills",
)
_ANALYZER = MetricsAnalyzer()


def get_domain(config: dict[str, Any] | None = None) -> LoopDomain:
    """Return the SKILL domain configuration."""
    cfg = config or {}
    return LoopDomain(
        name="skill",
        generate_fn="dharma_swarm.cascade_domains.skill.generate",
        test_fn="dharma_swarm.cascade_domains.common.default_test",
        score_fn="dharma_swarm.cascade_domains.skill.score",
        gate_fn="dharma_swarm.cascade_domains.common.telos_gate",
        mutate_fn="dharma_swarm.cascade_domains.common.default_mutate",
        select_fn="dharma_swarm.cascade_domains.common.default_select",
        max_iterations=cfg.get("max_iterations", 25),
        fitness_threshold=cfg.get("fitness_threshold", 0.55),
    )


def _parse_frontmatter(content: str) -> dict[str, Any]:
    """Extract YAML frontmatter from a SKILL.md file.

    Args:
        content: Raw file content with optional --- delimited frontmatter.

    Returns:
        Dict of frontmatter key-value pairs. Empty dict if no frontmatter.
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return {}

    fm: dict[str, Any] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            # Strip surrounding quotes if present.
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            fm[key] = value
    return fm


def _resolve_skill_path(skill_name: str) -> Path | None:
    seen: set[Path] = set()
    for root in _SKILLS_ROOT_CANDIDATES:
        if root in seen:
            continue
        seen.add(root)
        path = root / skill_name / "SKILL.md"
        if path.is_file():
            return path
    return None


def generate(seed: dict[str, Any] | None, context: dict[str, Any]) -> dict[str, Any]:
    """Generate a skill artifact by reading a SKILL.md file or using provided content.

    Args:
        seed: Optional dict with 'skill_name' (reads from disk) or 'content' (uses directly).
        context: Context dict, may contain 'skill_name' as fallback.

    Returns:
        Artifact dict with content, skill_name, skill_path, and fitness stub.
    """
    seed = seed or {}
    skill_name = seed.get("skill_name") or context.get("skill_name", "")
    content = seed.get("content", "")
    skill_path: str | None = None

    # Read from disk if we have a skill name and no content provided.
    if skill_name and not content:
        path = _resolve_skill_path(skill_name)
        if path is not None:
            content = path.read_text(encoding="utf-8")
            skill_path = str(path)

    # If still no content, use whatever is in seed.
    if not content:
        content = seed.get("content", "")

    return {
        "content": content,
        "skill_name": skill_name or "unknown",
        "skill_path": skill_path,
        "fitness": {},
    }


def _score_structure(content: str, frontmatter: dict[str, Any]) -> float:
    """Score structural quality of a skill file.

    Checks: has frontmatter, has description, has allowed-tools,
    has markdown headers, has code blocks.

    Args:
        content: Full skill file content.
        frontmatter: Parsed YAML frontmatter dict.

    Returns:
        Float in [0, 1].
    """
    has_frontmatter = bool(frontmatter)
    has_description = bool(frontmatter.get("description"))
    has_allowed_tools = bool(frontmatter.get("allowed-tools"))
    has_headers = bool(re.search(r"^#{1,4}\s+\S", content, re.MULTILINE))
    has_code = bool(re.search(r"```", content))

    # Weighted sum: frontmatter and description matter most.
    return (
        0.30 * has_frontmatter
        + 0.25 * has_description
        + 0.15 * has_allowed_tools
        + 0.20 * has_headers
        + 0.10 * has_code
    )


def _score_compression(content: str) -> float:
    """Score information density via zlib compression ratio.

    Good skills have a compression ratio around 0.45 (not too repetitive,
    not random noise). Score peaks at 0.45 and falls off symmetrically.

    Args:
        content: Raw text content.

    Returns:
        Float in [0, 1].
    """
    if not content:
        return 0.0

    raw = content.encode("utf-8")
    if len(raw) == 0:
        return 0.0

    ratio = len(zlib.compress(raw)) / len(raw)
    # Peak at 0.45, linearly penalize deviation. Clamp to [0, 1].
    return max(0.0, min(1.0, 1.0 - abs(ratio - 0.45) * 3.0))


def _score_behavioral(content: str) -> float:
    """Score behavioral quality using MetricsAnalyzer.

    Skills should be operational (high swabhaav = witness/observer stance),
    not performative. Also penalizes mimicry.

    Args:
        content: Raw text content.

    Returns:
        Float in [0, 1].
    """
    if not content:
        return 0.0

    sig = _ANALYZER.analyze(content)

    # Skills are instructional, so a moderate swabhaav_ratio is fine.
    # Default 0.5 (no stance markers) is neutral and acceptable.
    swabhaav_score = min(1.0, sig.swabhaav_ratio + 0.3)

    # Penalize mimicry (performative words).
    mimicry_penalty = 0.3 if _ANALYZER.detect_mimicry(content) else 0.0

    return max(0.0, swabhaav_score - mimicry_penalty)


def _score_completeness(content: str) -> float:
    """Score based on word count -- too short is incomplete, too long is bloated.

    Args:
        content: Raw text content.

    Returns:
        Float in [0, 1].
    """
    word_count = len(content.split())

    if word_count < 50:
        base = 0.2
    elif word_count < 200:
        base = 0.6
    elif word_count < 1000:
        base = 0.9
    else:
        base = 1.0

    # Penalize bloat beyond 3000 words.
    if word_count > 3000:
        bloat_penalty = min(0.5, (word_count - 3000) / 4000.0)
        base -= bloat_penalty

    return max(0.0, base)


def _score_composability(content: str) -> float:
    """Score how well a skill composes with other skills.

    Checks for: references to other skills (/skill-name patterns),
    clear input/output contracts (arguments, returns, output sections),
    and integration signals (mentions of other tools or workflows).

    Args:
        content: Raw text content.

    Returns:
        Float in [0, 1].
    """
    score = 0.3  # Baseline -- a skill that exists is somewhat composable.

    # Cross-references to other skills (e.g., /context-engineer, /rv-paper).
    skill_refs = re.findall(r"(?<!\w)/[a-z][a-z0-9-]+(?!\w)", content)
    if skill_refs:
        score += min(0.25, len(skill_refs) * 0.05)

    # Input/output contract signals.
    contract_patterns = [
        r"(?i)\bargument",
        r"(?i)\binput\b",
        r"(?i)\boutput\b",
        r"(?i)\breturn",
        r"(?i)\bproduce",
        r"(?i)\bemit",
    ]
    contract_hits = sum(1 for p in contract_patterns if re.search(p, content))
    score += min(0.25, contract_hits * 0.05)

    # Integration signals (references to tools, files, other systems).
    integration_patterns = [
        r"(?i)\bRead\b",
        r"(?i)\bGrep\b",
        r"(?i)\bGlob\b",
        r"(?i)\bBash\b",
        r"(?i)\bWrite\b",
        r"(?i)CLAUDE\.md",
        r"(?i)\.dharma/",
    ]
    integration_hits = sum(1 for p in integration_patterns if re.search(p, content))
    score += min(0.20, integration_hits * 0.04)

    return min(1.0, score)


def score(artifact: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Score a skill artifact across five dimensions.

    Dimensions and weights:
        - structure (0.25): YAML frontmatter, headers, code blocks.
        - compression (0.20): Information density via zlib ratio.
        - behavioral (0.25): Witness stance vs performative language.
        - completeness (0.15): Word count (too short or too long penalized).
        - composability (0.15): Cross-references, contracts, integration.

    Args:
        artifact: Dict with at least 'content' key.
        context: Scoring context (unused currently).

    Returns:
        Artifact with 'fitness' (sub-scores) and 'score' (weighted total) populated.
    """
    content = artifact.get("content", "")
    frontmatter = _parse_frontmatter(content)

    # Strip frontmatter for body-only analysis where appropriate.
    body = re.sub(r"^---\s*\n.*?\n---\s*\n", "", content, count=1, flags=re.DOTALL)

    structure = _score_structure(content, frontmatter)
    compression = _score_compression(body)
    behavioral = _score_behavioral(body)
    completeness = _score_completeness(body)
    composability = _score_composability(content)

    artifact["fitness"] = {
        "structure": round(structure, 4),
        "compression": round(compression, 4),
        "behavioral": round(behavioral, 4),
        "completeness": round(completeness, 4),
        "composability": round(composability, 4),
    }

    artifact["score"] = round(
        0.25 * structure
        + 0.20 * compression
        + 0.25 * behavioral
        + 0.15 * completeness
        + 0.15 * composability,
        4,
    )

    return artifact
