"""Worker agent: classifies text snippets using behavioral DNA as system prompt."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TypeAlias

from .dna import BehavioralDNA
from .llm_client import PetriDishLLM
from .models import Classification, SnippetResult, TextSnippet, WorkerTrace

logger = logging.getLogger(__name__)

ModelChoice: TypeAlias = str | list[str] | tuple[str, ...]

# Valid values for classification
VALID_SENTIMENTS = {"positive", "negative", "neutral"}
VALID_TOPICS = {"technology", "science", "politics", "culture", "other"}
VALID_URGENCIES = {"high", "medium", "low"}

CLASSIFY_USER_PROMPT = """Classify the following text. Respond ONLY with valid JSON.

Text: "{text}"

Required format: {{"sentiment": "positive|negative|neutral", "topic": "technology|science|politics|culture|other", "urgency": "high|medium|low", "confidence": 0.0-1.0}}"""

CLASSIFY_BATCH_USER_PROMPT = """Classify each text snippet below. Respond ONLY with valid JSON.

Return a JSON array with one object per snippet in the SAME ORDER.

Required format:
[
  {{"sentiment": "positive|negative|neutral", "topic": "technology|science|politics|culture|other", "urgency": "high|medium|low", "confidence": 0.0-1.0}},
  ...
]

Snippets:
{indexed_snippets}
"""


class WorkerAgent:
    """A worker that classifies text using its behavioral DNA as system prompt."""

    def __init__(
        self,
        name: str,
        dna: BehavioralDNA,
        llm: PetriDishLLM,
        model: ModelChoice,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> None:
        self.name = name
        self.dna = dna
        self.llm = llm
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def classify_one(self, snippet: TextSnippet) -> Classification:
        """Classify a single text snippet."""
        system_prompt = self.dna.load()
        user_msg = CLASSIFY_USER_PROMPT.format(text=snippet.text)

        try:
            raw = await self._complete_with_model_fallback(
                system=system_prompt,
                user_message=user_msg,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            return self._parse_response(raw)
        except Exception as e:
            logger.error("[%s] Classification failed: %s", self.name, e)
            return Classification(raw_response=str(e))

    async def classify_batch(
        self,
        snippets: list[TextSnippet],
        cycle_id: int,
        generation: int,
    ) -> WorkerTrace:
        """Classify all snippets, compare to ground truth, return trace.

        The primary path is a single batched LLM request per worker cycle to
        stay within free-tier rate limits. If the model returns malformed batch
        output, fall back to single-snippet classification for correctness.
        """
        results: list[SnippetResult] = []
        classifications = await self._classify_batch_once(snippets)
        if len(classifications) != len(snippets):
            logger.warning(
                "[%s] Batch response count mismatch (%d != %d); falling back",
                self.name,
                len(classifications),
                len(snippets),
            )
            classifications = [await self.classify_one(snippet) for snippet in snippets]

        for snippet, classification in zip(snippets, classifications, strict=False):
            result = SnippetResult(
                snippet_text=snippet.text,
                classification=classification,
                true_sentiment=snippet.true_sentiment,
                true_topic=snippet.true_topic,
                true_urgency=snippet.true_urgency,
                sentiment_correct=(
                    classification.sentiment.lower() == snippet.true_sentiment.lower()
                ),
                topic_correct=(
                    classification.topic.lower() == snippet.true_topic.lower()
                ),
                urgency_correct=(
                    classification.urgency.lower() == snippet.true_urgency.lower()
                ),
            )
            results.append(result)

        trace = WorkerTrace(
            agent_name=self.name,
            cycle_id=cycle_id,
            generation=generation,
            results=results,
        )
        trace.compute_accuracy()

        logger.info(
            "[%s] Cycle %d: sentiment=%.2f topic=%.2f urgency=%.2f overall=%.2f",
            self.name, cycle_id,
            trace.sentiment_accuracy, trace.topic_accuracy,
            trace.urgency_accuracy, trace.overall_accuracy,
        )
        return trace

    async def _classify_batch_once(
        self,
        snippets: list[TextSnippet],
    ) -> list[Classification]:
        """Classify one worker batch in a single LLM call."""
        if not snippets:
            return []

        indexed_snippets = "\n".join(
            f"{idx + 1}. {snippet.text}"
            for idx, snippet in enumerate(snippets)
        )
        raw = await self._complete_with_model_fallback(
            system=self.dna.load(),
            user_message=CLASSIFY_BATCH_USER_PROMPT.format(
                indexed_snippets=indexed_snippets,
            ),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return self._parse_batch_response(raw)

    async def _complete_with_model_fallback(
        self,
        *,
        system: str,
        user_message: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Try candidate models in order until one succeeds."""
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
                        self.name,
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

    def _parse_response(self, raw: str) -> Classification:
        """Parse LLM response into a Classification, with fallbacks."""
        raw = raw.strip()

        # Try direct JSON parse
        try:
            data = json.loads(raw)
            return self._validate_classification(data, raw)
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from markdown code block
        import re
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                return self._validate_classification(data, raw)
            except json.JSONDecodeError:
                pass

        # Try finding any JSON object in the response
        brace_match = re.search(r"\{[^{}]*\}", raw)
        if brace_match:
            try:
                data = json.loads(brace_match.group())
                return self._validate_classification(data, raw)
            except json.JSONDecodeError:
                pass

        logger.warning("[%s] Failed to parse response: %.100s", self.name, raw)
        return Classification(raw_response=raw)

    def _parse_batch_response(self, raw: str) -> list[Classification]:
        """Parse a JSON array of classifications from the model output."""
        raw = raw.strip()
        payload: object | None = None

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            pass

        if payload is None:
            json_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw, re.DOTALL)
            if json_match:
                try:
                    payload = json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    payload = None

        if payload is None:
            bracket_match = re.search(r"\[[\s\S]*\]", raw)
            if bracket_match:
                try:
                    payload = json.loads(bracket_match.group())
                except json.JSONDecodeError:
                    payload = None

        if isinstance(payload, dict):
            candidate = payload.get("results")
            if isinstance(candidate, list):
                payload = candidate

        if not isinstance(payload, list):
            logger.warning("[%s] Failed to parse batch response: %.120s", self.name, raw)
            return []

        classifications: list[Classification] = []
        for item in payload:
            if not isinstance(item, dict):
                classifications.append(Classification(raw_response=raw))
                continue
            classifications.append(self._validate_classification(item, json.dumps(item)))
        return classifications

    def _validate_classification(self, data: dict, raw: str) -> Classification:
        """Validate and normalize parsed classification data."""
        sentiment = str(data.get("sentiment", "")).lower().strip()
        topic = str(data.get("topic", "")).lower().strip()
        urgency = str(data.get("urgency", "")).lower().strip()

        # Normalize to valid values
        if sentiment not in VALID_SENTIMENTS:
            sentiment = ""
        if topic not in VALID_TOPICS:
            topic = ""
        if urgency not in VALID_URGENCIES:
            urgency = ""

        try:
            confidence = float(data.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))
        except (ValueError, TypeError):
            confidence = 0.5

        return Classification(
            sentiment=sentiment,
            topic=topic,
            urgency=urgency,
            confidence=confidence,
            raw_response=raw,
        )


def save_trace(trace: WorkerTrace, traces_dir: Path) -> Path:
    """Save a worker trace to disk."""
    traces_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{trace.agent_name}_gen{trace.generation}_cycle{trace.cycle_id}.json"
    path = traces_dir / filename
    path.write_text(trace.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_traces(traces_dir: Path, generation: int | None = None) -> list[WorkerTrace]:
    """Load all traces, optionally filtered by generation."""
    if not traces_dir.exists():
        return []
    traces = []
    for f in sorted(traces_dir.glob("*.json")):
        try:
            trace = WorkerTrace.model_validate_json(f.read_text(encoding="utf-8"))
            if generation is None or trace.generation == generation:
                traces.append(trace)
        except Exception as e:
            logger.warning("Failed to load trace %s: %s", f, e)
    return traces
