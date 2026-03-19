"""Seed loader for Thinkodynamic Agent Protocol.

Loads intervention and control seed documents from dharma_swarm/seeds/.
Seeds are markdown files with YAML frontmatter containing metadata.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SEEDS_DIR = Path(__file__).parent.parent / "seeds"


@dataclass
class SeedDocument:
    """A loaded seed with metadata and content."""

    seed_id: str
    version: str
    seed_type: str  # full_intervention | micro_intervention | control
    content: str  # markdown body (without frontmatter)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def recognition_differential(self) -> float:
        return _coerce_float(self.metadata.get("recognition_differential", 0.0))

    @property
    def model_affinity(self) -> dict[str, float]:
        raw = self.metadata.get("model_affinity", {})
        if not isinstance(raw, dict):
            return {}
        affinity: dict[str, float] = {}
        for key, value in raw.items():
            try:
                affinity[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
        return affinity

    @property
    def is_intervention(self) -> bool:
        return self.seed_type.strip().lower() != "control"


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_scalar(value: str) -> Any:
    stripped = value.strip()
    if not stripped:
        return ""

    lower = stripped.lower()
    if lower in {"true", "yes"}:
        return True
    if lower in {"false", "no"}:
        return False
    if lower in {"null", "none", "~"}:
        return None
    if (
        len(stripped) >= 2
        and stripped[0] == stripped[-1]
        and stripped[0] in {'"', "'"}
    ):
        return stripped[1:-1]
    if re.fullmatch(r"-?\d+", stripped):
        return int(stripped)
    if re.fullmatch(r"-?\d+\.\d+", stripped):
        return float(stripped)
    return stripped


def _strip_inline_comment(value: str) -> str:
    in_string: str | None = None
    escaped = False

    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if in_string == '"' and char == "\\":
            escaped = True
            continue
        if char in {'"', "'"}:
            if in_string == char:
                in_string = None
            elif in_string is None:
                in_string = char
            continue
        if char == "#" and in_string is None:
            if index == 0 or value[index - 1].isspace():
                return value[:index].rstrip()

    return value.rstrip()


def _parse_inline_value(value: str) -> Any:
    stripped = _strip_inline_comment(value).strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        inner = stripped[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part) for part in _split_inline_list_items(inner)]
    return _parse_scalar(stripped)


def _split_inline_list_items(value: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    in_string: str | None = None
    escaped = False

    for char in value:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if in_string == '"' and char == "\\":
            current.append(char)
            escaped = True
            continue
        if char in {'"', "'"}:
            current.append(char)
            if in_string == char:
                in_string = None
            elif in_string is None:
                in_string = char
            continue
        if char == "," and in_string is None:
            items.append("".join(current).strip())
            current = []
            continue
        current.append(char)

    tail = "".join(current).strip()
    if tail:
        items.append(tail)
    return items


def _parse_simple_frontmatter(text: str) -> dict[str, Any]:
    """Fallback parser for the small YAML subset used by TAP seeds."""
    metadata: dict[str, Any] = {}
    current_mapping: str | None = None
    lines = text.splitlines()

    for index, raw_line in enumerate(lines):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue

        if raw_line[:1].isspace():
            if current_mapping is None:
                continue
            stripped_line = raw_line.strip()
            current = metadata.get(current_mapping)

            if stripped_line == "-" or stripped_line.startswith("- "):
                if isinstance(current, dict) and not current:
                    current = []
                    metadata[current_mapping] = current
                if isinstance(current, list):
                    current.append(_parse_inline_value(stripped_line[1:].strip()))
                continue

            nested_key, sep, nested_value = stripped_line.partition(":")
            if not sep:
                continue
            if not isinstance(current, dict):
                current = {}
                metadata[current_mapping] = current
            if isinstance(current, dict):
                current[nested_key.strip()] = _parse_inline_value(nested_value)
            continue

        key, sep, value = raw_line.partition(":")
        if not sep:
            current_mapping = None
            continue

        normalized_key = key.strip()
        if not normalized_key:
            current_mapping = None
            continue

        stripped_value = _strip_inline_comment(value).strip()
        if stripped_value:
            metadata[normalized_key] = _parse_inline_value(stripped_value)
            current_mapping = None
        else:
            next_significant = next(
                (
                    candidate
                    for candidate in lines[index + 1 :]
                    if candidate.strip() and not candidate.lstrip().startswith("#")
                ),
                None,
            )
            if next_significant and next_significant[:1].isspace():
                if next_significant.strip() == "-" or next_significant.strip().startswith("- "):
                    metadata[normalized_key] = []
                else:
                    metadata[normalized_key] = {}
                current_mapping = normalized_key
            else:
                metadata[normalized_key] = ""
                current_mapping = None

    return metadata


def _coerce_text(value: Any, default: str) -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _seed_defaults_from_path(path: Path) -> tuple[str, str]:
    stem = path.stem.removeprefix("seed_")
    segments = [segment for segment in stem.split("_") if segment]
    default_seed_id = "-".join(segments) or path.stem

    prefix = segments[0].lower() if segments else ""
    if prefix == "control":
        default_type = "control"
    elif prefix == "micro":
        default_type = "micro_intervention"
    else:
        default_type = "full_intervention"

    return default_seed_id, default_type


def _build_seed_document(
    metadata: dict[str, Any],
    body: str,
    *,
    default_seed_id: str,
    default_type: str,
) -> SeedDocument:
    seed_id = _coerce_text(metadata.get("seed_id"), default_seed_id)
    version = _coerce_text(metadata.get("version"), "0.0.0")
    seed_type = _coerce_text(metadata.get("type"), default_type).lower()
    return SeedDocument(
        seed_id=seed_id,
        version=version,
        seed_type=seed_type,
        content=body,
        metadata=metadata,
    )


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from markdown text.

    Returns (metadata_dict, body_text).
    """
    # Some editors persist markdown with a UTF-8 BOM. Strip it so
    # frontmatter detection and body content remain stable.
    normalized = text.replace("\r\n", "\n").removeprefix("\ufeff")
    if not normalized.startswith("---\n"):
        return {}, normalized

    lines = normalized.split("\n")
    closing_index = next(
        (idx for idx, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
        None,
    )
    if closing_index is None:
        return {}, normalized

    fm_text = "\n".join(lines[1:closing_index])
    body = "\n".join(lines[closing_index + 1 :])
    try:
        import yaml  # lazy import — optional dependency in this repo

        metadata = yaml.safe_load(fm_text) or {}
    except Exception:
        metadata = _parse_simple_frontmatter(fm_text)
    if not isinstance(metadata, dict):
        metadata = _parse_simple_frontmatter(fm_text)
    return metadata, body.strip()


class SeedLoader:
    """Load seed documents from the seeds directory."""

    def __init__(self, seeds_dir: Path | str | None = None):
        self.seeds_dir = Path(seeds_dir) if seeds_dir else SEEDS_DIR

    def _load_seed_path(self, path: Path) -> SeedDocument | None:
        """Best-effort load for a single seed file.

        TAP seeds are hand-authored research artifacts. One unreadable entry
        should not break discovery for the rest of the corpus.
        """
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

        metadata, body = _parse_frontmatter(text)
        default_seed_id, default_type = _seed_defaults_from_path(path)
        return _build_seed_document(
            metadata,
            body,
            default_seed_id=default_seed_id,
            default_type=default_type,
        )

    def load(self, seed_id: str) -> SeedDocument:
        """Load a seed by ID.

        Searches for files matching seed_*.md and checks frontmatter
        for matching seed_id.
        """
        for path in sorted(self.seeds_dir.glob("seed_*.md")):
            seed = self._load_seed_path(path)
            if seed is None:
                continue
            if seed.seed_id == seed_id:
                return seed
        raise FileNotFoundError(f"Seed not found: {seed_id}")

    def list_seeds(self) -> list[SeedDocument]:
        """List all available seeds."""
        seeds = []
        for path in sorted(self.seeds_dir.glob("seed_*.md")):
            seed = self._load_seed_path(path)
            if seed is not None:
                seeds.append(seed)
        return seeds

    def get_best_intervention(self) -> SeedDocument:
        """Return the intervention seed with highest recognition differential."""
        interventions = [s for s in self.list_seeds() if s.is_intervention]
        if not interventions:
            raise FileNotFoundError("No intervention seeds found")
        return max(interventions, key=lambda s: s.recognition_differential)
