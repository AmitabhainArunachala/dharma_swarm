"""Plan long-context sidecar evaluations against local dharma_swarm artifacts."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class SourceExcerpt:
    """A source file and a small excerpt used to seed a benchmark case."""

    label: str
    path: str
    exists: bool
    excerpt: str
    byte_count: int
    note: str = ""


@dataclass(slots=True)
class BenchmarkCase:
    """A concrete workload for a long-context sidecar model."""

    case_id: str
    title: str
    role: str
    objective: str
    model_job: str
    prompt_frame: str
    output_schema: list[str] = field(default_factory=list)
    success_signals: list[str] = field(default_factory=list)
    kill_signals: list[str] = field(default_factory=list)
    evaluation_questions: list[str] = field(default_factory=list)
    sources: list[SourceExcerpt] = field(default_factory=list)


@dataclass(slots=True)
class BenchmarkPlan:
    """A benchmark plan with local workloads and candidate model metadata."""

    generated_at: str
    repo_root: str
    dharma_home: str
    candidate_model: str
    baseline_model: str
    thesis: str
    cases: list[BenchmarkCase] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _read_excerpt(path: Path, *, max_chars: int) -> SourceExcerpt:
    if not path.exists():
        return SourceExcerpt(
            label=path.name,
            path=str(path),
            exists=False,
            excerpt="",
            byte_count=0,
            note="missing",
        )

    text = path.read_text(encoding="utf-8", errors="replace")
    excerpt = text[:max_chars]
    note = "truncated" if len(text) > max_chars else ""
    return SourceExcerpt(
        label=path.name,
        path=str(path),
        exists=True,
        excerpt=excerpt,
        byte_count=len(text.encode("utf-8")),
        note=note,
    )


def _latest_match(base: Path, pattern: str) -> Path | None:
    matches = sorted(base.glob(pattern))
    if not matches:
        return None
    return matches[-1]


def _collect_sources(paths: Iterable[Path | None], *, max_chars: int) -> list[SourceExcerpt]:
    return [_read_excerpt(path, max_chars=max_chars) for path in paths if path is not None]


def build_default_plan(
    *,
    repo_root: Path,
    dharma_home: Path,
    candidate_model: str = "moonshotai/Kimi-Linear-48B-A3B-Instruct",
    baseline_model: str = "current-premium-model",
    max_chars: int = 3000,
) -> BenchmarkPlan:
    """Build a default benchmark plan from the live repo and dharma home."""

    latest_conversation = _latest_match(dharma_home / "conversations", "dashboard_*.jsonl")
    latest_distill = _latest_match(dharma_home / "distilled", "*.md")

    cases = [
        BenchmarkCase(
            case_id="repo_digest",
            title="Repo Digestion",
            role="architecture_scout",
            objective=(
                "Digest core memory/retrieval files and explain how they should be "
                "compressed into reusable memory artifacts for the main model."
            ),
            model_job="Read large code and architecture context cheaply, then compress it.",
            prompt_frame=(
                "Read the sources as one system. Produce an architectural summary, three "
                "missing seams, and a compact memory shard packet."
            ),
            output_schema=[
                "system_summary",
                "memory_shards",
                "missing_seams",
                "followup_questions",
            ],
            success_signals=[
                "Correctly identifies event memory, hybrid retrieval, and semantic bridge roles.",
                "Produces compact reusable memory shards instead of prose sprawl.",
                "Surfaces at least one real integration seam worth testing.",
            ],
            kill_signals=[
                "Misstates the core memory architecture.",
                "Needs the premium model to fix basic repo understanding.",
                "Produces bloated output that is not reusable as memory.",
            ],
            evaluation_questions=[
                "Did it preserve system structure correctly?",
                "Did it compress meaningfully enough to help downstream prompts?",
                "Did it find missing seams we would actually build?",
            ],
            sources=_collect_sources(
                [
                    repo_root / "dharma_swarm" / "engine" / "event_memory.py",
                    repo_root / "dharma_swarm" / "engine" / "hybrid_retriever.py",
                    repo_root / "dharma_swarm" / "semantic_memory_bridge.py",
                ],
                max_chars=max_chars,
            ),
        ),
        BenchmarkCase(
            case_id="conversation_condense",
            title="Conversation Condensation",
            role="continuity_editor",
            objective=(
                "Condense recent conversations and distilled notes into a compact state "
                "packet for the next cycle."
            ),
            model_job="Turn messy user and system history into clean continuity state.",
            prompt_frame=(
                "Extract commitments, open loops, invariants, and unresolved tensions. "
                "Output a compact continuity packet."
            ),
            output_schema=[
                "commitments",
                "open_loops",
                "identity_invariants",
                "next_cycle_context",
            ],
            success_signals=[
                "Remembers concrete commitments and unresolved loops.",
                "Produces a concise packet usable in future prompts.",
                "Separates stable identity from temporary context.",
            ],
            kill_signals=[
                "Collapses important distinctions between goals and chatter.",
                "Loses actionable commitments.",
                "Outputs generic summarization with no continuity value.",
            ],
            evaluation_questions=[
                "Would this packet improve the next live session?",
                "Did it preserve promises and constraints?",
                "Is the output smaller and more useful than raw history?",
            ],
            sources=_collect_sources(
                [
                    latest_conversation,
                    latest_distill,
                    dharma_home / "DGC_SEED_CONTEXT.md",
                ],
                max_chars=max_chars,
            ),
        ),
        BenchmarkCase(
            case_id="trace_summarize",
            title="Trace Summarization",
            role="ops_summarizer",
            objective=(
                "Summarize long operational traces into a small packet that highlights "
                "events, failures, and useful carry-forward state."
            ),
            model_job="Compress operational logs and trace files for the next agent cycle.",
            prompt_frame=(
                "Read the traces and produce an execution summary, detected failures, "
                "carry-forward state, and one contradiction check."
            ),
            output_schema=[
                "execution_summary",
                "failures",
                "carry_forward_state",
                "contradictions",
            ],
            success_signals=[
                "Captures what happened without reproducing the whole log.",
                "Flags failures and degraded states clearly.",
                "Produces carry-forward state the main model can use.",
            ],
            kill_signals=[
                "Copies logs instead of compressing them.",
                "Misses obvious degraded or failed conditions.",
                "Cannot separate signal from noise.",
            ],
            evaluation_questions=[
                "Would this reduce context load in live loops?",
                "Did it preserve failures and operator-relevant state?",
                "Did it surface contradictions worth checking?",
            ],
            sources=_collect_sources(
                [
                    dharma_home / "evolution" / "archive.jsonl",
                    dharma_home / "foreman" / "cycles.jsonl",
                    repo_root
                    / "reports"
                    / "dual_engine_swarm_20260313_run"
                    / "state"
                    / "mission.json",
                ],
                max_chars=max_chars,
            ),
        ),
        BenchmarkCase(
            case_id="contradiction_hunt",
            title="Contradiction Hunt",
            role="integrity_reviewer",
            objective=(
                "Read plans and architecture docs, then surface hidden contradictions, "
                "duplicate machinery, and mismatched claims."
            ),
            model_job="Act as a cheap structural critic over large planning documents.",
            prompt_frame=(
                "Find claims that disagree, duplicate modules, or create architecture drift. "
                "Propose one keep/kill decision per contradiction."
            ),
            output_schema=[
                "contradictions",
                "duplicate_machinery",
                "keep_kill_decisions",
                "risk_summary",
            ],
            success_signals=[
                "Finds real contradictions rather than superficial style issues.",
                "Connects contradictions to concrete files and decisions.",
                "Suggests keep/kill decisions grounded in the repo state.",
            ],
            kill_signals=[
                "Only finds vague philosophical inconsistencies.",
                "Misses duplicate machinery already called out in plans.",
                "Cannot map claims back to specific files.",
            ],
            evaluation_questions=[
                "Did it reduce architecture drift?",
                "Did it tie claims to concrete files?",
                "Did it find anything worth acting on this week?",
            ],
            sources=_collect_sources(
                [
                    repo_root / "reports" / "architectural" / "STRANGE_LOOP_MASTER_PLAN_20260314.md",
                    repo_root / "program.md",
                    repo_root / "LIVING_LAYERS.md",
                ],
                max_chars=max_chars,
            ),
        ),
        BenchmarkCase(
            case_id="memory_distill",
            title="Memory Distillation",
            role="memory_distiller",
            objective=(
                "Turn dense notes and semantic summaries into compact memory shards "
                "that are worth indexing and recalling."
            ),
            model_job="Produce reusable memory artifacts, not just summaries.",
            prompt_frame=(
                "Extract high-salience memory shards, novelty, invariants, and evidence paths. "
                "Output them in a form that can be indexed."
            ),
            output_schema=[
                "memory_shards",
                "novelty_notes",
                "invariants",
                "evidence_paths",
            ],
            success_signals=[
                "Produces discrete shard-like artifacts rather than one monolith.",
                "Preserves evidence paths and invariants.",
                "Would be worth adding to memory_plane or unified_index.",
            ],
            kill_signals=[
                "Outputs generic notes that are not indexable.",
                "Drops evidence provenance.",
                "Confuses speculative ideas with stable invariants.",
            ],
            evaluation_questions=[
                "Would these shards improve retrieval quality later?",
                "Did it preserve provenance and confidence?",
                "Are the shards compact enough to re-use automatically?",
            ],
            sources=_collect_sources(
                [
                    repo_root / "reports" / "psmv_hyperfiles_20260313" / "repo_semantic_summary.md",
                    dharma_home / "distilled" / "ideas.jsonl",
                    dharma_home / "DGC_SEED_CONTEXT.md",
                ],
                max_chars=max_chars,
            ),
        ),
    ]

    return BenchmarkPlan(
        generated_at=_utc_now_iso(),
        repo_root=str(repo_root),
        dharma_home=str(dharma_home),
        candidate_model=candidate_model,
        baseline_model=baseline_model,
        thesis=(
            "Test long-context models as sidecar workers that read and compress large local "
            "artifacts into reusable memory products. Do not replace the main reasoning model "
            "or the canonical memory plane until the sidecar clearly wins on a real job."
        ),
        cases=cases,
    )


def render_markdown(plan: BenchmarkPlan) -> str:
    """Render the benchmark plan as a readable markdown packet."""

    lines = [
        "# Long-Context Sidecar Evaluation Plan",
        "",
        f"- Generated: `{plan.generated_at}`",
        f"- Candidate model: `{plan.candidate_model}`",
        f"- Baseline model: `{plan.baseline_model}`",
        f"- Repo root: `{plan.repo_root}`",
        f"- Dharma home: `{plan.dharma_home}`",
        "",
        "## Thesis",
        "",
        plan.thesis,
        "",
        "## Workloads",
        "",
    ]

    for index, case in enumerate(plan.cases, start=1):
        lines.extend(
            [
                f"### {index}. {case.title}",
                "",
                f"- Case ID: `{case.case_id}`",
                f"- Role: `{case.role}`",
                f"- Objective: {case.objective}",
                f"- Model job: {case.model_job}",
                f"- Prompt frame: {case.prompt_frame}",
                "- Output schema:",
            ]
        )
        lines.extend(f"  - `{field_name}`" for field_name in case.output_schema)
        lines.append("- Sources:")
        for source in case.sources:
            status = "present" if source.exists else "missing"
            note = f" ({source.note})" if source.note else ""
            lines.append(f"  - `{source.path}` [{status}]{note}")
        lines.append("- Success signals:")
        lines.extend(f"  - {item}" for item in case.success_signals)
        lines.append("- Kill signals:")
        lines.extend(f"  - {item}" for item in case.kill_signals)
        lines.append("- Evaluation questions:")
        lines.extend(f"  - {item}" for item in case.evaluation_questions)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a long-context sidecar benchmark plan.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Path to the dharma_swarm repo root.",
    )
    parser.add_argument(
        "--dharma-home",
        type=Path,
        default=Path.home() / ".dharma",
        help="Path to dharma home containing memory and trace artifacts.",
    )
    parser.add_argument(
        "--candidate-model",
        default="moonshotai/Kimi-Linear-48B-A3B-Instruct",
        help="Candidate sidecar model to evaluate.",
    )
    parser.add_argument(
        "--baseline-model",
        default="current-premium-model",
        help="Baseline model to compare against.",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=3000,
        help="Maximum characters to extract per source file.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output file. Defaults to stdout.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    plan = build_default_plan(
        repo_root=args.repo_root,
        dharma_home=args.dharma_home,
        candidate_model=args.candidate_model,
        baseline_model=args.baseline_model,
        max_chars=args.max_chars,
    )

    if args.format == "markdown":
        rendered = render_markdown(plan)
    else:
        rendered = json.dumps(plan.to_dict(), indent=2)

    if args.output:
        args.output.write_text(rendered + ("" if rendered.endswith("\n") else "\n"), encoding="utf-8")
    else:
        print(rendered)
    return 0


__all__ = [
    "BenchmarkCase",
    "BenchmarkPlan",
    "SourceExcerpt",
    "build_default_plan",
    "main",
    "render_markdown",
]

