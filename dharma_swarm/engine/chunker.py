"""Deterministic markdown chunking for the Memory Palace substrate."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


@dataclass(frozen=True, slots=True)
class Chunk:
    """A deterministic text chunk with structural metadata."""

    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _strip_frontmatter(text: str) -> str:
    normalized = text.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        return normalized
    end = normalized.find("\n---\n", 4)
    if end == -1:
        return normalized
    return normalized[end + 5 :]


def _split_paragraphs(section_text: str) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", section_text) if part.strip()]
    if paragraphs:
        return paragraphs
    stripped = section_text.strip()
    return [stripped] if stripped else []


def _emit_chunk(chunks: list[Chunk], header_path: list[str], text: str) -> None:
    stripped = text.strip()
    if not stripped:
        return
    metadata = {
        "header_path": list(header_path),
        "section_title": header_path[-1] if header_path else "",
        "section_depth": len(header_path),
        "word_count": len(stripped.split()),
    }
    chunks.append(Chunk(text=stripped, metadata=metadata))


def chunk_markdown(text: str, *, max_words: int = 180) -> list[Chunk]:
    """Split markdown into header-aware deterministic chunks."""

    body = _strip_frontmatter(text)
    lines = body.replace("\r\n", "\n").splitlines()
    sections: list[tuple[list[str], str]] = []
    header_stack: list[tuple[int, str]] = []
    current_path: list[str] = []
    current_lines: list[str] = []

    def flush_section() -> None:
        section_text = "\n".join(current_lines).strip()
        if section_text:
            sections.append((list(current_path), section_text))

    for raw_line in lines:
        line = raw_line.rstrip()
        match = _HEADER_RE.match(line.strip())
        if match:
            flush_section()
            level = len(match.group(1))
            title = match.group(2).strip()
            header_stack[:] = header_stack[: level - 1]
            header_stack.append((level, title))
            current_path = [item[1] for item in header_stack]
            current_lines = []
            continue
        current_lines.append(line)
    flush_section()

    if not sections and body.strip():
        sections = [([], body.strip())]

    chunks: list[Chunk] = []
    for header_path, section_text in sections:
        paragraphs = _split_paragraphs(section_text)
        current_parts: list[str] = []
        current_words = 0
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            if current_parts and current_words + para_words > max_words:
                _emit_chunk(chunks, header_path, "\n\n".join(current_parts))
                current_parts = []
                current_words = 0
            current_parts.append(paragraph)
            current_words += para_words
        if current_parts:
            _emit_chunk(chunks, header_path, "\n\n".join(current_parts))

    return chunks
