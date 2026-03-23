"""Consolidation agents: observe, debate, and modify behavioral DNA.

Two consolidators (thesis/antithesis) read all worker traces and DNA,
have a structured contrarian debate, and produce specific modifications
to the workers' behavioral DNA.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import TypeAlias

from .llm_client import PetriDishLLM
from .models import ConsolidationResult, Modification, WorkerTrace

logger = logging.getLogger(__name__)

ModelChoice: TypeAlias = str | list[str] | tuple[str, ...]


ANALYSIS_SYSTEM = """You are a behavioral optimizer for a multi-agent text classification system.
You are the {role} — your job is to {job}.

You will receive:
1. Each worker agent's behavioral DNA (the markdown config that determines their behavior)
2. Their classification traces (what they classified, what was correct, what was wrong)
3. Accuracy scores per dimension (sentiment, topic, urgency)

Your analysis must be SPECIFIC and GROUNDED in the data. Cite specific misclassifications.
Do NOT give generic advice like "be more careful". Instead say exactly what pattern
is causing errors and exactly what text change would fix it."""

THESIS_JOB = "identify what IS working and propose targeted refinements to improve further"
ANTITHESIS_JOB = "identify what is NOT working and propose structural changes to fix systemic issues"

DEBATE_SYSTEM = """You are participating in a structured contrarian debate about how to improve
a multi-agent text classification system.

You are the {role}. Your opponent has made the following argument:

{opponent_argument}

Previous debate history:
{history}

You must:
1. Address your opponent's specific claims
2. Concede points where they have strong evidence
3. Present your counter-argument with specific data
4. Be constructive — the goal is to find the BEST modifications, not to "win"

Keep your response under 500 words. Be specific, cite data."""

EXTRACTION_SYSTEM = """You are a modification extractor. Given a debate transcript between two
behavioral optimizers, extract the CONCRETE modifications they agreed on
(or that one side convincingly argued for).

Each modification must be a specific text change in a specific agent's DNA file.
The modifications should target the most impactful issues identified in the debate.

IMPORTANT: Modifications must use EXACT text from the current DNA files as old_text.
The new_text should be a direct replacement. Do NOT invent section names that don't exist.

Respond with a JSON array of modifications:
[
  {
    "agent": "classifier_alpha|classifier_beta|classifier_gamma",
    "section": "Decision Heuristics|Known Failure Modes|Priority Order|Constraints",
    "action": "replace|append",
    "old_text": "exact text to replace (empty for append)",
    "new_text": "new text to insert",
    "rationale": "why this change addresses the identified issue"
  }
]

Limit to 3-5 modifications. Focus on the highest-impact changes.
Respond ONLY with the JSON array, no other text."""


class ConsolidatorAgent:
    """One side of the contrarian debate (thesis or antithesis)."""

    def __init__(
        self,
        role: str,
        llm: PetriDishLLM,
        model: ModelChoice,
        temperature: float = 0.7,
    ) -> None:
        self.role = role
        self.llm = llm
        self.model = model
        self.temperature = temperature

    async def analyze(
        self,
        worker_dnas: dict[str, str],
        traces: list[WorkerTrace],
    ) -> str:
        """Produce initial analysis of all workers' performance."""
        job = THESIS_JOB if self.role == "thesis" else ANTITHESIS_JOB
        system = ANALYSIS_SYSTEM.format(role=self.role, job=job)

        # Build the evidence document
        evidence = self._build_evidence(worker_dnas, traces)

        return await self._complete_with_model_fallback(
            system=system,
            user_message=evidence,
            temperature=self.temperature,
            max_tokens=1500,
        )

    async def debate_turn(
        self,
        opponent_argument: str,
        history: str,
    ) -> str:
        """Produce one turn in the structured debate."""
        system = DEBATE_SYSTEM.format(
            role=self.role,
            opponent_argument=opponent_argument,
            history=history if history else "(This is the first exchange.)",
        )

        return await self._complete_with_model_fallback(
            system=system,
            user_message="Respond with your position.",
            temperature=self.temperature,
            max_tokens=800,
        )

    def _build_evidence(
        self,
        worker_dnas: dict[str, str],
        traces: list[WorkerTrace],
    ) -> str:
        """Build a compact evidence document from DNA + traces."""
        parts = ["# System Evidence\n"]

        # Per-worker section
        for agent_name in sorted(worker_dnas.keys()):
            parts.append(f"\n## {agent_name}\n")

            # DNA excerpt (first 40 lines to save tokens)
            dna_lines = worker_dnas[agent_name].split("\n")
            parts.append("### Behavioral DNA (excerpt)\n```\n")
            parts.append("\n".join(dna_lines[:40]))
            parts.append("\n```\n")

            # Traces for this agent
            agent_traces = [t for t in traces if t.agent_name == agent_name]
            if agent_traces:
                parts.append("### Performance\n")
                for t in agent_traces:
                    parts.append(
                        f"- Cycle {t.cycle_id}: sentiment={t.sentiment_accuracy:.2f} "
                        f"topic={t.topic_accuracy:.2f} urgency={t.urgency_accuracy:.2f} "
                        f"overall={t.overall_accuracy:.2f}\n"
                    )

                # Show specific misclassifications from most recent trace
                latest = agent_traces[-1]
                errors = [r for r in latest.results if not (
                    r.sentiment_correct and r.topic_correct and r.urgency_correct
                )]
                if errors:
                    parts.append("\n### Recent Errors\n")
                    for err in errors[:5]:  # Cap at 5
                        wrong = []
                        if not err.sentiment_correct:
                            wrong.append(
                                f"sentiment: predicted={err.classification.sentiment} "
                                f"actual={err.true_sentiment}"
                            )
                        if not err.topic_correct:
                            wrong.append(
                                f"topic: predicted={err.classification.topic} "
                                f"actual={err.true_topic}"
                            )
                        if not err.urgency_correct:
                            wrong.append(
                                f"urgency: predicted={err.classification.urgency} "
                                f"actual={err.true_urgency}"
                            )
                        parts.append(
                            f"- Text: \"{err.snippet_text[:80]}...\"\n"
                            f"  Wrong: {'; '.join(wrong)}\n"
                        )

        return "".join(parts)

    async def _complete_with_model_fallback(
        self,
        *,
        system: str,
        user_message: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        last_exc: Exception | None = None
        candidates = self._model_candidates()
        for idx, model_name in enumerate(candidates):
            try:
                return await self.llm.complete(
                    system=system,
                    user_message=user_message,
                    model=model_name,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as exc:
                last_exc = exc
                if idx < len(candidates) - 1:
                    logger.warning(
                        "[%s] Model %s failed; trying %s",
                        self.role,
                        model_name,
                        candidates[idx + 1],
                    )
                    continue
                raise
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("No candidate models configured")

    def _model_candidates(self) -> list[str]:
        if isinstance(self.model, str):
            return [self.model]
        return [candidate for candidate in self.model if candidate]


class ConsolidationOrchestrator:
    """Runs the full consolidation cycle: analyze, debate, extract, apply."""

    def __init__(
        self,
        thesis: ConsolidatorAgent,
        antithesis: ConsolidatorAgent,
        llm: PetriDishLLM,
        extraction_model: ModelChoice,
        debate_rounds: int = 3,
    ) -> None:
        self.thesis = thesis
        self.antithesis = antithesis
        self.llm = llm
        self.extraction_model = extraction_model
        self.debate_rounds = debate_rounds

    async def run(
        self,
        worker_dnas: dict[str, str],
        traces: list[WorkerTrace],
        generation: int,
    ) -> ConsolidationResult:
        """Execute full consolidation: analyze → debate → extract mods."""
        transcript: list[dict[str, str]] = []

        # Phase 1: Independent analysis
        logger.info("Consolidation: Phase 1 — Independent analysis")
        thesis_analysis = await self.thesis.analyze(worker_dnas, traces)
        antithesis_analysis = await self.antithesis.analyze(worker_dnas, traces)

        transcript.append({"speaker": "thesis", "phase": "analysis", "content": thesis_analysis})
        transcript.append({"speaker": "antithesis", "phase": "analysis", "content": antithesis_analysis})

        # Phase 2: Contrarian debate
        logger.info("Consolidation: Phase 2 — Contrarian debate (%d rounds)", self.debate_rounds)
        history = f"THESIS ANALYSIS:\n{thesis_analysis}\n\nANTITHESIS ANALYSIS:\n{antithesis_analysis}"
        last_thesis = thesis_analysis

        for round_num in range(self.debate_rounds):
            logger.info("  Round %d/%d", round_num + 1, self.debate_rounds)

            # Antithesis attacks thesis
            antithesis_turn = await self.antithesis.debate_turn(last_thesis, history)
            transcript.append({
                "speaker": "antithesis", "phase": f"round_{round_num + 1}",
                "content": antithesis_turn,
            })
            history += f"\n\nANTITHESIS (round {round_num + 1}):\n{antithesis_turn}"

            # Thesis responds
            thesis_turn = await self.thesis.debate_turn(antithesis_turn, history)
            transcript.append({
                "speaker": "thesis", "phase": f"round_{round_num + 1}",
                "content": thesis_turn,
            })
            history += f"\n\nTHESIS (round {round_num + 1}):\n{thesis_turn}"

            last_thesis = thesis_turn

        # Phase 3: Extract modifications
        logger.info("Consolidation: Phase 3 — Extracting modifications")
        modifications = await self._extract_modifications(
            transcript, worker_dnas, generation,
        )

        # Compute pre-consolidation scores
        pre_scores: dict[str, float] = {}
        for agent_name in worker_dnas:
            agent_traces = [t for t in traces if t.agent_name == agent_name]
            if agent_traces:
                pre_scores[agent_name] = agent_traces[-1].overall_accuracy

        result = ConsolidationResult(
            generation=generation,
            debate_transcript=transcript,
            modifications=modifications,
            pre_scores=pre_scores,
        )

        logger.info(
            "Consolidation complete: %d modifications proposed",
            len(modifications),
        )
        return result

    async def _extract_modifications(
        self,
        transcript: list[dict[str, str]],
        worker_dnas: dict[str, str],
        _generation: int,
    ) -> list[Modification]:
        """Use LLM to extract concrete modifications from debate."""
        # Build context
        debate_text = "\n\n".join(
            f"[{t['speaker'].upper()} - {t['phase']}]\n{t['content']}"
            for t in transcript
        )

        dna_text = "\n\n".join(
            f"=== {name} DNA ===\n{content}"
            for name, content in sorted(worker_dnas.items())
        )

        user_msg = (
            f"# Debate Transcript\n\n{debate_text}\n\n"
            f"# Current DNA Files\n\n{dna_text}\n\n"
            f"Extract the 3-5 most impactful modifications as a JSON array."
        )

        raw = await self._complete_with_model_fallback(
            system=EXTRACTION_SYSTEM,
            user_message=user_msg,
            temperature=0.3,
            max_tokens=2000,
        )

        return self._parse_modifications(raw)

    async def _complete_with_model_fallback(
        self,
        *,
        system: str,
        user_message: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        last_exc: Exception | None = None
        candidates = self._model_candidates(self.extraction_model)
        for idx, model_name in enumerate(candidates):
            try:
                return await self.llm.complete(
                    system=system,
                    user_message=user_message,
                    model=model_name,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as exc:
                last_exc = exc
                if idx < len(candidates) - 1:
                    logger.warning(
                        "[extractor] Model %s failed; trying %s",
                        model_name,
                        candidates[idx + 1],
                    )
                    continue
                raise
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("No candidate extraction models configured")

    @staticmethod
    def _model_candidates(model: ModelChoice) -> list[str]:
        if isinstance(model, str):
            return [model]
        return [candidate for candidate in model if candidate]

    def _parse_modifications(self, raw: str) -> list[Modification]:
        """Parse LLM response into Modification objects."""
        raw = raw.strip()

        # Try direct parse
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [Modification(**m) for m in data]
        except (json.JSONDecodeError, TypeError):
            pass

        # Try extracting JSON array from response
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                if isinstance(data, list):
                    return [Modification(**m) for m in data]
            except (json.JSONDecodeError, TypeError):
                pass

        logger.warning("Failed to parse modifications from response: %.200s", raw)
        return []


def save_consolidation(result: ConsolidationResult, debates_dir: Path) -> Path:
    """Save consolidation result to disk."""
    debates_dir.mkdir(parents=True, exist_ok=True)
    filename = f"consolidation_gen{result.generation}.json"
    path = debates_dir / filename
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return path
