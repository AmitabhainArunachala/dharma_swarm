"""Knowledge distillation over shared notes, CLAUDE files, and evaluations."""

from __future__ import annotations

import asyncio
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from dharma_swarm.evaluator import OutputEvaluation, OutputEvaluator

_POSITIVE_MARKERS = ("healthy", "pass", "passing", "ready", "works", "working")
_NEGATIVE_MARKERS = ("blocked", "broken", "fail", "failing", "stuck", "timeout")
_ACTIONABLE_MARKERS = ("next", "need to", "should", "run ", "verify", "blocked", "follow up")


def _normalize_fact(line: str) -> str:
    lowered = re.sub(r"\s+", " ", line.strip().lower())
    return re.sub(r"[^a-z0-9 ./:_-]", "", lowered)


def _extract_candidate_lines(content: str) -> list[str]:
    lines: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("- ", "* ", "+ ")):
            line = line[2:].strip()
        elif re.match(r"^\d+\.\s+", line):
            line = re.sub(r"^\d+\.\s+", "", line)
        if len(line) >= 20:
            lines.append(line)
    return lines


@dataclass(slots=True)
class DistilledKnowledge:
    """Structured distillation result for shared notes."""

    note_count: int
    key_findings: list[str] = field(default_factory=list)
    convergences: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    unacted_items: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [f"# Distilled Knowledge", f"Notes analyzed: {self.note_count}"]
        if self.key_findings:
            lines.append("\n## Key Findings")
            lines.extend(f"- {item}" for item in self.key_findings)
        if self.convergences:
            lines.append("\n## Convergences")
            lines.extend(f"- {item}" for item in self.convergences)
        if self.contradictions:
            lines.append("\n## Contradictions")
            lines.extend(f"- {item}" for item in self.contradictions)
        if self.unacted_items:
            lines.append("\n## Unacted Items")
            lines.extend(f"- {item}" for item in self.unacted_items)
        return "\n".join(lines).strip()


@dataclass(slots=True)
class Pattern:
    """Recurring evaluation pattern extracted from history."""

    name: str
    summary: str
    evidence_count: int


class KnowledgeDistiller:
    """Compress accumulated knowledge into compact actionable briefs."""

    def __init__(
        self,
        *,
        state_dir: Path | None = None,
        evaluations_path: Path | None = None,
    ) -> None:
        self.state_dir = state_dir or (Path.home() / ".dharma")
        self.evaluations_path = evaluations_path or (self.state_dir / "evaluations.jsonl")

    async def distill_notes(self, notes_dir: Path) -> DistilledKnowledge:
        """Read shared notes, deduplicate findings, and surface action items."""

        if not notes_dir.exists():
            return DistilledKnowledge(note_count=0)

        def _scan_sync() -> DistilledKnowledge:
            notes = sorted(notes_dir.glob("*_notes.md"))
            normalized_to_sources: defaultdict[str, set[str]] = defaultdict(set)
            normalized_to_examples: dict[str, str] = {}
            actionable: list[str] = []

            for path in notes:
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                for candidate in _extract_candidate_lines(content):
                    normalized = _normalize_fact(candidate)
                    if not normalized:
                        continue
                    normalized_to_sources[normalized].add(path.stem)
                    normalized_to_examples.setdefault(normalized, candidate)
                    lowered = candidate.lower()
                    if any(marker in lowered for marker in _ACTIONABLE_MARKERS):
                        actionable.append(candidate)

            ranked = sorted(
                normalized_to_sources.items(),
                key=lambda item: (-len(item[1]), -len(item[0]), item[0]),
            )
            key_findings = [
                normalized_to_examples[key]
                for key, _sources in ranked[:8]
            ]
            convergences = [
                f"{normalized_to_examples[key]} ({len(sources)} notes)"
                for key, sources in ranked
                if len(sources) >= 2
            ][:6]

            contradictions: list[str] = []
            normalized_keys = list(normalized_to_sources)
            for idx, left in enumerate(normalized_keys):
                left_words = set(left.split())
                left_positive = any(marker in left for marker in _POSITIVE_MARKERS)
                left_negative = any(marker in left for marker in _NEGATIVE_MARKERS)
                if left_positive == left_negative:
                    continue
                for right in normalized_keys[idx + 1 :]:
                    overlap = left_words & set(right.split())
                    if len(overlap) < 3:
                        continue
                    right_positive = any(marker in right for marker in _POSITIVE_MARKERS)
                    right_negative = any(marker in right for marker in _NEGATIVE_MARKERS)
                    if left_positive and right_negative:
                        contradictions.append(
                            f"{normalized_to_examples[left]} <-> {normalized_to_examples[right]}"
                        )
                    elif left_negative and right_positive:
                        contradictions.append(
                            f"{normalized_to_examples[left]} <-> {normalized_to_examples[right]}"
                        )
                    if len(contradictions) >= 4:
                        break
                if len(contradictions) >= 4:
                    break

            deduped_actionable: list[str] = []
            seen: set[str] = set()
            for item in actionable:
                normalized = _normalize_fact(item)
                if normalized in seen:
                    continue
                seen.add(normalized)
                deduped_actionable.append(item)

            return DistilledKnowledge(
                note_count=len(notes),
                key_findings=key_findings,
                convergences=convergences,
                contradictions=contradictions,
                unacted_items=deduped_actionable[:8],
                sources=[path.name for path in notes],
            )

        return await asyncio.to_thread(_scan_sync)

    async def compress_claude_md(self, claude_files: list[Path]) -> str:
        """Generate a compact combined summary of dense CLAUDE guidance files."""

        if not claude_files:
            return ""

        def _compress_sync() -> str:
            sections: list[str] = []
            seen: set[str] = set()
            for path in claude_files:
                if not path.exists():
                    continue
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue

                selected: list[str] = []
                for line in content.splitlines():
                    stripped = line.strip()
                    if not stripped:
                        continue
                    if stripped.startswith("#"):
                        selected.append(stripped)
                    elif len(selected) < 8 and len(stripped) >= 30:
                        selected.append(stripped)
                    if len(selected) >= 12:
                        break

                block = "\n".join(selected).strip()
                normalized = _normalize_fact(block)
                if not block or normalized in seen:
                    continue
                seen.add(normalized)
                sections.append(f"## {path.name}\n{block}")

            summary = "\n\n".join(sections)
            if len(summary) > 12_000:
                summary = summary[:12_000] + "\n... [CLAUDE summary truncated]"
            return summary

        return await asyncio.to_thread(_compress_sync)

    async def extract_patterns(self, evaluations: list[OutputEvaluation]) -> list[Pattern]:
        """Find recurring success and failure patterns in evaluation history."""

        if not evaluations:
            return []

        patterns: list[Pattern] = []
        by_model: defaultdict[str, list[OutputEvaluation]] = defaultdict(list)
        by_task_type: defaultdict[str, list[OutputEvaluation]] = defaultdict(list)
        failures: list[OutputEvaluation] = []
        for evaluation in evaluations:
            by_model[evaluation.model].append(evaluation)
            by_task_type[evaluation.task_type].append(evaluation)
            if not evaluation.success or evaluation.completeness < 0.45:
                failures.append(evaluation)

        ranked_models = sorted(
            (
                (
                    model,
                    len(entries),
                    sum(entry.quality_score for entry in entries) / len(entries),
                )
                for model, entries in by_model.items()
            ),
            key=lambda item: (-item[2], -item[1], item[0]),
        )
        if ranked_models:
            best_model, count, score = ranked_models[0]
            patterns.append(
                Pattern(
                    name="best_model",
                    summary=f"{best_model} leads quality at {score:.3f} across {count} runs.",
                    evidence_count=count,
                )
            )

        for task_type, entries in sorted(by_task_type.items()):
            ranked = sorted(
                (
                    (
                        model,
                        len(model_entries),
                        sum(entry.quality_score for entry in model_entries) / len(model_entries),
                    )
                    for model, model_entries in defaultdict(
                        list,
                        ((entry.model, [e for e in entries if e.model == entry.model]) for entry in entries),
                    ).items()
                ),
                key=lambda item: (-item[2], -item[1], item[0]),
            )
            if ranked:
                patterns.append(
                    Pattern(
                        name=f"{task_type}_leader",
                        summary=f"For {task_type} tasks, {ranked[0][0]} averages {ranked[0][2]:.3f}.",
                        evidence_count=ranked[0][1],
                    )
                )

        if failures:
            failing_models = Counter(entry.model for entry in failures)
            model, count = failing_models.most_common(1)[0]
            patterns.append(
                Pattern(
                    name="failure_cluster",
                    summary=f"{model} shows the most low-completeness or failed outputs ({count}).",
                    evidence_count=count,
                )
            )

        return patterns

    async def generate_briefing(
        self,
        *,
        notes_dir: Path | None = None,
        claude_files: list[Path] | None = None,
        evaluations_path: Path | None = None,
    ) -> str:
        """Generate a morning-brief style summary of recent system learning."""

        resolved_notes_dir = notes_dir or (self.state_dir / "shared")
        resolved_claude_files = claude_files or self._discover_claude_files()
        evaluator = OutputEvaluator(
            evaluations_path=evaluations_path or self.evaluations_path,
        )
        knowledge = await self.distill_notes(resolved_notes_dir)
        evaluations = await evaluator.read_all()
        patterns = await self.extract_patterns(evaluations)
        claude_summary = await self.compress_claude_md(resolved_claude_files)

        lines = ["# Distilled Briefing"]
        lines.append(f"Shared notes analyzed: {knowledge.note_count}")
        if knowledge.key_findings:
            lines.append("\n## Highest-Signal Findings")
            lines.extend(f"- {item}" for item in knowledge.key_findings[:6])
        if knowledge.convergences:
            lines.append("\n## Converging Signals")
            lines.extend(f"- {item}" for item in knowledge.convergences[:4])
        if knowledge.contradictions:
            lines.append("\n## Contradictions Needing Resolution")
            lines.extend(f"- {item}" for item in knowledge.contradictions[:4])
        if knowledge.unacted_items:
            lines.append("\n## Discovery Debt")
            lines.extend(f"- {item}" for item in knowledge.unacted_items[:4])
        if patterns:
            lines.append("\n## Evaluation Patterns")
            lines.extend(f"- {pattern.summary}" for pattern in patterns[:6])
        if claude_summary:
            lines.append("\n## CLAUDE Compression")
            lines.append(claude_summary[:4000] + ("\n... [briefing truncated]" if len(claude_summary) > 4000 else ""))
        return "\n".join(lines).strip()

    def _discover_claude_files(self) -> list[Path]:
        home = Path.home()
        candidates = {path for path in home.glob("CLAUDE*.md")}
        root_candidate = home / "CLAUDE.md"
        if root_candidate.exists():
            candidates.add(root_candidate)
        return sorted(candidates)
