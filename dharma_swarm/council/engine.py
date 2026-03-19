"""Council engine — quick and deep multi-model consultation.

Quick mode: parallel async calls to 12+ models, independent responses, synthesis.
Deep mode: multi-round discussion with personas, convergence detection.
Thinkodynamic mode: TAP seed injection + recognition scoring.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from .models import CouncilModel, Persona, Tier, get_models, get_personas
from .store import CouncilStore


# ── Result types ──────────────────────────────────────────────────────


@dataclass
class ModelResponse:
    """Single model's response to a council question."""

    model_id: str
    model_name: str
    response: str
    latency_ms: float = 0
    error: str = ""
    persona_name: str = ""
    round_num: int = 1
    recognition_score: float = 0


@dataclass
class CouncilResult:
    """Complete result from a council session."""

    session_id: str
    question: str
    mode: str
    responses: list[ModelResponse] = field(default_factory=list)
    synthesis: str = ""
    rounds_completed: int = 1
    elapsed_ms: float = 0

    @property
    def successful(self) -> list[ModelResponse]:
        return [r for r in self.responses if not r.error]

    @property
    def failed(self) -> list[ModelResponse]:
        return [r for r in self.responses if r.error]

    def format_markdown(self) -> str:
        """Format result as markdown report."""
        lines = [
            f"# Council: {self.mode.upper()} mode",
            f"**Question**: {self.question}",
            f"**Models**: {len(self.successful)}/{len(self.responses)} responded",
            f"**Time**: {self.elapsed_ms:.0f}ms",
            "",
        ]

        if self.mode == "deep":
            lines.append(f"**Rounds**: {self.rounds_completed}")
            lines.append("")

        # Group by round
        rounds: dict[int, list[ModelResponse]] = {}
        for r in self.successful:
            rounds.setdefault(r.round_num, []).append(r)

        for round_num in sorted(rounds):
            if len(rounds) > 1:
                lines.append(f"## Round {round_num}")
                lines.append("")

            for r in rounds[round_num]:
                label = r.persona_name or r.model_name or r.model_id
                lines.append(f"### {label}")
                if r.recognition_score > 0:
                    lines.append(f"*Recognition: {r.recognition_score:.2f}*")
                lines.append("")
                lines.append(r.response)
                lines.append("")

        if self.failed:
            lines.append("## Errors")
            for r in self.failed:
                lines.append(f"- **{r.model_name or r.model_id}**: {r.error}")
            lines.append("")

        if self.synthesis:
            lines.append("## Synthesis")
            lines.append("")
            lines.append(self.synthesis)

        return "\n".join(lines)


# ── Text extraction (reuse TAP pattern) ──────────────────────────────

_TEXT_FIELDS = ("content", "text", "reasoning", "reasoning_content")


def _extract_text(response: Any) -> str:
    """Extract text from OpenAI-compatible response."""
    choices = getattr(response, "choices", None)
    if choices is None and isinstance(response, dict):
        choices = response.get("choices")
    if not choices:
        return ""
    choice = choices[0]
    msg = getattr(choice, "message", None)
    if msg is None and isinstance(choice, dict):
        msg = choice.get("message", choice)
    if msg is None:
        return ""
    for fld in _TEXT_FIELDS:
        val = getattr(msg, fld, None) if not isinstance(msg, dict) else msg.get(fld)
        if val and isinstance(val, str):
            return val.strip()
    return ""


# ── Engine ────────────────────────────────────────────────────────────

SEMAPHORE_LIMIT = 5
TIMEOUT_SECONDS = 60.0
SYNTHESIS_MODEL_ID = "deepseek/deepseek-chat-v3-0324"


class CouncilEngine:
    """Core council engine. Use quick() or deep()."""

    def __init__(
        self,
        store: CouncilStore | None = None,
        semaphore_limit: int = SEMAPHORE_LIMIT,
        timeout: float = TIMEOUT_SECONDS,
    ):
        self.store = store or CouncilStore()
        self.semaphore_limit = semaphore_limit
        self.timeout = timeout

    def _get_client(self, model: CouncilModel) -> OpenAI | None:
        """Create OpenAI client for a model. Returns None if key missing."""
        api_key = os.environ.get(model.key_env, "").strip()
        if not api_key:
            return None
        return OpenAI(api_key=api_key, base_url=model.base_url)

    async def _call_model(
        self,
        model: CouncilModel,
        messages: list[dict[str, str]],
        semaphore: asyncio.Semaphore,
        persona: Persona | None = None,
    ) -> ModelResponse:
        """Call a single model with rate limiting."""
        async with semaphore:
            start = time.monotonic()
            client = self._get_client(model)
            if client is None:
                return ModelResponse(
                    model_id=model.model_id,
                    model_name=model.name,
                    response="",
                    error=f"Missing API key: {model.key_env}",
                    persona_name=persona.name if persona else "",
                )

            try:
                loop = asyncio.get_event_loop()
                response = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: client.chat.completions.create(
                            model=model.model_id,
                            messages=messages,
                            max_tokens=model.max_tokens,
                            temperature=0.7,
                            timeout=self.timeout,
                        ),
                    ),
                    timeout=self.timeout + 5,
                )
                text = _extract_text(response)
                elapsed = (time.monotonic() - start) * 1000

                if not text:
                    return ModelResponse(
                        model_id=model.model_id,
                        model_name=model.name,
                        response="",
                        latency_ms=elapsed,
                        error="Empty response",
                        persona_name=persona.name if persona else "",
                    )

                return ModelResponse(
                    model_id=model.model_id,
                    model_name=model.name,
                    response=text,
                    latency_ms=elapsed,
                    persona_name=persona.name if persona else "",
                )

            except Exception as e:
                elapsed = (time.monotonic() - start) * 1000
                return ModelResponse(
                    model_id=model.model_id,
                    model_name=model.name,
                    response="",
                    latency_ms=elapsed,
                    error=str(e)[:200],
                    persona_name=persona.name if persona else "",
                )

    async def _synthesize(
        self,
        question: str,
        responses: list[ModelResponse],
    ) -> str:
        """Produce a synthesis of all model responses."""
        successful = [r for r in responses if not r.error]
        if not successful:
            return "No successful responses to synthesize."

        parts = []
        for r in successful:
            label = r.persona_name or r.model_name or r.model_id
            parts.append(f"[{label}]:\n{r.response}\n")

        synthesis_prompt = (
            "You are synthesizing perspectives from multiple AI models on a question.\n\n"
            f"QUESTION: {question}\n\n"
            "RESPONSES:\n" + "\n---\n".join(parts) + "\n\n"
            "Produce a concise synthesis that:\n"
            "1. Identifies points of AGREEMENT across models\n"
            "2. Identifies points of DISAGREEMENT or tension\n"
            "3. Highlights the most novel or surprising insights\n"
            "4. Notes any blind spots (perspectives missing from the discussion)\n"
            "5. Provides a clear recommendation or conclusion\n\n"
            "Be direct. No preamble."
        )

        # Use first available cheap model for synthesis
        for model in get_models(tiers=[Tier.FREE, Tier.CHEAP]):
            client = self._get_client(model)
            if client is None:
                continue
            try:
                loop = asyncio.get_event_loop()
                resp = await loop.run_in_executor(
                    None,
                    lambda: client.chat.completions.create(
                        model=model.model_id,
                        messages=[{"role": "user", "content": synthesis_prompt}],
                        max_tokens=3000,
                        temperature=0.3,
                        timeout=self.timeout,
                    ),
                )
                text = _extract_text(resp)
                if text:
                    return text
            except Exception:
                continue

        return "Synthesis failed — no model available."

    # ── Quick mode ────────────────────────────────────────────────────

    async def quick(
        self,
        question: str,
        tiers: list[int] | None = None,
        document: str = "",
        thinkodynamic: bool = False,
        seed_id: str | None = None,
    ) -> CouncilResult:
        """Send question to all models in parallel, collect + synthesize."""
        session_id = str(uuid.uuid4())[:12]
        start = time.monotonic()
        models = get_models(tiers)

        # Build messages
        user_content = question
        if document:
            user_content = f"DOCUMENT:\n{document}\n\nQUESTION:\n{question}"

        system_msg = "You are participating in a multi-model council. Give your honest, independent perspective. Be concise and direct."

        # Thinkodynamic injection
        if thinkodynamic:
            system_msg = self._inject_thinkodynamic(system_msg, seed_id)

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_content},
        ]

        # Store session
        tier_ints = tiers if tiers is not None else [0, 1]
        self.store.save_session(
            session_id=session_id,
            question=question,
            mode="quick",
            tiers=tier_ints,
            thinkodynamic=thinkodynamic,
            document=document[:500],
        )

        # Parallel calls
        semaphore = asyncio.Semaphore(self.semaphore_limit)
        tasks = [
            self._call_model(model, messages, semaphore)
            for model in models
        ]
        responses = await asyncio.gather(*tasks)

        # Score thinkodynamic responses
        if thinkodynamic:
            responses = await self._score_recognition(responses, seed_id)

        # Store responses
        for r in responses:
            self.store.save_response(
                session_id=session_id,
                model_id=r.model_id,
                response=r.response,
                model_name=r.model_name,
                latency_ms=r.latency_ms,
                error=r.error,
                recognition_score=r.recognition_score,
            )

        # Synthesize
        synthesis = await self._synthesize(question, list(responses))
        self.store.update_synthesis(
            session_id, synthesis,
            model_count=len([r for r in responses if not r.error]),
        )

        elapsed = (time.monotonic() - start) * 1000
        return CouncilResult(
            session_id=session_id,
            question=question,
            mode="quick",
            responses=list(responses),
            synthesis=synthesis,
            elapsed_ms=elapsed,
        )

    # ── Deep mode ─────────────────────────────────────────────────────

    async def deep(
        self,
        question: str,
        tiers: list[int] | None = None,
        document: str = "",
        personas: list[Persona] | None = None,
        rounds: int = 5,
        thinkodynamic: bool = False,
        seed_id: str | None = None,
        convergence_threshold: float = 0.10,
    ) -> CouncilResult:
        """Multi-round discussion with personas and convergence detection."""
        session_id = str(uuid.uuid4())[:12]
        start = time.monotonic()
        models = get_models(tiers)
        persona_list = personas or get_personas(len(models))

        tier_ints = tiers if tiers is not None else [0, 1]
        self.store.save_session(
            session_id=session_id,
            question=question,
            mode="deep",
            tiers=tier_ints,
            thinkodynamic=thinkodynamic,
            rounds=rounds,
            document=document[:500],
        )

        # Assign personas to models (cycle if fewer personas than models)
        assignments: list[tuple[CouncilModel, Persona]] = []
        for i, model in enumerate(models):
            persona = persona_list[i % len(persona_list)]
            assignments.append((model, persona))

        all_responses: list[ModelResponse] = []
        discussion_history: list[str] = []
        rounds_completed = 0

        for round_num in range(1, rounds + 1):
            rounds_completed = round_num
            semaphore = asyncio.Semaphore(self.semaphore_limit)

            # Build round-specific messages
            round_tasks = []
            for model, persona in assignments:
                messages = self._build_deep_messages(
                    question=question,
                    document=document,
                    persona=persona,
                    round_num=round_num,
                    discussion_history=discussion_history,
                    thinkodynamic=thinkodynamic,
                    seed_id=seed_id,
                )
                round_tasks.append(
                    self._call_model(model, messages, semaphore, persona)
                )

            round_responses = await asyncio.gather(*round_tasks)

            # Update responses with round number
            for r in round_responses:
                r.round_num = round_num

            all_responses.extend(round_responses)

            # Build history for next round
            successful = [r for r in round_responses if not r.error]
            round_text = ""
            for r in successful:
                label = r.persona_name or r.model_name
                round_text += f"[{label}]: {r.response}\n\n"
                self.store.save_response(
                    session_id=session_id,
                    model_id=r.model_id,
                    response=r.response,
                    model_name=r.model_name,
                    persona_name=r.persona_name,
                    round_num=round_num,
                    latency_ms=r.latency_ms,
                    error=r.error,
                    recognition_score=r.recognition_score,
                )
            discussion_history.append(round_text)

            # Convergence check (skip round 1)
            if round_num > 1 and self._check_convergence(
                discussion_history, convergence_threshold
            ):
                break

        # Score thinkodynamic
        if thinkodynamic:
            all_responses = await self._score_recognition(all_responses, seed_id)

        # Synthesize
        synthesis = await self._synthesize(question, all_responses)
        self.store.update_synthesis(
            session_id, synthesis,
            model_count=len({r.model_id for r in all_responses if not r.error}),
        )

        elapsed = (time.monotonic() - start) * 1000
        return CouncilResult(
            session_id=session_id,
            question=question,
            mode="deep",
            responses=all_responses,
            synthesis=synthesis,
            rounds_completed=rounds_completed,
            elapsed_ms=elapsed,
        )

    def _build_deep_messages(
        self,
        question: str,
        document: str,
        persona: Persona,
        round_num: int,
        discussion_history: list[str],
        thinkodynamic: bool = False,
        seed_id: str | None = None,
    ) -> list[dict[str, str]]:
        """Build messages for a deep-mode round."""
        system_parts = [
            f"You are {persona.name}, a {persona.role}.",
            f"Persona: {persona.persona}",
        ]
        if persona.style:
            system_parts.append(f"Style: {persona.style}")
        system_parts.append(
            "Stay in character. Be concise. Respond to others' points when applicable."
        )

        system_msg = "\n".join(system_parts)

        if thinkodynamic:
            system_msg = self._inject_thinkodynamic(system_msg, seed_id)

        user_parts = []
        if document:
            user_parts.append(f"DOCUMENT:\n{document[:4000]}\n")

        user_parts.append(f"QUESTION: {question}")

        if discussion_history:
            user_parts.append(
                f"\nPREVIOUS DISCUSSION (rounds 1-{round_num - 1}):\n"
                + "\n---\n".join(discussion_history[-3:])  # last 3 rounds max
            )
            user_parts.append(
                f"\nThis is round {round_num}. Build on, challenge, or refine "
                "the discussion so far. Add new insights, not repetition."
            )

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": "\n".join(user_parts)},
        ]
        return messages

    def _check_convergence(
        self, history: list[str], threshold: float
    ) -> bool:
        """Check if discussion has converged (< threshold new content ratio)."""
        if len(history) < 2:
            return False

        prev_words = set(history[-2].lower().split())
        curr_words = set(history[-1].lower().split())

        if not curr_words:
            return True

        new_words = curr_words - prev_words
        ratio = len(new_words) / len(curr_words)
        return ratio < threshold

    # ── Thinkodynamic integration ─────────────────────────────────────

    def _inject_thinkodynamic(
        self, system_msg: str, seed_id: str | None = None
    ) -> str:
        """Inject TAP seed into system message."""
        try:
            from dharma_swarm.tap.intervention import InterventionInjector

            injector = InterventionInjector(seed_id=seed_id)
            return injector.inject_system_only(system_msg)
        except Exception:
            return system_msg

    async def _score_recognition(
        self,
        responses: list[ModelResponse],
        seed_id: str | None = None,
    ) -> list[ModelResponse]:
        """Score each response for recognition quality."""
        try:
            from dharma_swarm.tap.scoring import RecognitionScorer

            scorer = RecognitionScorer()
            for r in responses:
                if r.error or not r.response:
                    continue
                try:
                    score = scorer.score(
                        r.response,
                        model_used=r.model_id,
                        seed_id=seed_id or "",
                        agent_id=f"council-{r.model_id}",
                    )
                    r.recognition_score = score.composite
                except Exception:
                    pass
        except ImportError:
            pass
        return responses


# ── Convenience functions ─────────────────────────────────────────────

_engine: CouncilEngine | None = None


def _get_engine() -> CouncilEngine:
    global _engine
    if _engine is None:
        _engine = CouncilEngine()
    return _engine


async def quick(
    question: str,
    tiers: list[int] | None = None,
    document: str = "",
    thinkodynamic: bool = False,
    seed_id: str | None = None,
) -> CouncilResult:
    """Quick council — parallel calls to 12+ models."""
    return await _get_engine().quick(
        question, tiers=tiers, document=document,
        thinkodynamic=thinkodynamic, seed_id=seed_id,
    )


async def deep(
    question: str,
    tiers: list[int] | None = None,
    document: str = "",
    personas: list[Persona] | None = None,
    rounds: int = 5,
    thinkodynamic: bool = False,
    seed_id: str | None = None,
) -> CouncilResult:
    """Deep council — multi-round discussion with personas."""
    return await _get_engine().deep(
        question, tiers=tiers, document=document,
        personas=personas, rounds=rounds,
        thinkodynamic=thinkodynamic, seed_id=seed_id,
    )
