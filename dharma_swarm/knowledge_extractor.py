"""knowledge_extractor.py — LLM-driven extraction of knowledge units.

Decomposes raw agent interaction context into structured Propositions
(factual claims) and Prescriptions (reusable skills) using prompted LLM
calls.  Used by SleepTimeAgent during consolidation.

The extraction follows PlugMem's insight: episodic memory should be
decomposed into semantic knowledge units for concept-centric retrieval.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Any, List, Optional, Tuple

from dharma_swarm.knowledge_units import Proposition, Prescription

logger = logging.getLogger(__name__)


class KnowledgeExtractor:
    """Extracts Propositions and Prescriptions from raw agent context.

    Uses structured LLM prompts to decompose episodic memory into semantic knowledge.
    """

    PROPOSITION_PROMPT = (
        "Analyze the following agent interaction and extract atomic factual claims.\n"
        "For each fact, provide:\n"
        "- content: the fact as a single sentence\n"
        "- concepts: 2-5 concept tags (nouns/topics, not verbs)\n"
        "- confidence: 0.0-1.0 how certain this fact is\n"
        "\n"
        "Return a JSON array of objects with keys: content, concepts, confidence.\n"
        "Only extract facts that would be useful in future tasks.\n"
        "Do NOT extract ephemeral details (timestamps, session IDs, etc.).\n"
        "If there are no extractable facts, return an empty array [].\n"
        "\n"
        "Interaction:\n{context}"
    )

    PRESCRIPTION_PROMPT = (
        "Analyze the following agent interaction and extract reusable skills/procedures.\n"
        "For each skill, provide:\n"
        "- intent: what this skill accomplishes (one sentence)\n"
        "- workflow: ordered list of environment-agnostic steps (no hardcoded paths/names)\n"
        "- concepts: 2-5 concept tags\n"
        "- return_score: 0.0-1.0 based on how well this approach worked in the interaction\n"
        "\n"
        "Return a JSON array of objects with keys: intent, workflow, concepts, return_score.\n"
        "Only extract procedures that generalize beyond this specific interaction.\n"
        "If there are no extractable skills, return an empty array [].\n"
        "\n"
        "Interaction:\n{context}"
    )

    CONCEPT_EXTRACTION_PROMPT = (
        "Extract the 3-7 most important concepts from this task description.\n"
        "Return as a JSON array of strings. Concepts should be nouns/topics, not verbs.\n"
        "If the task is too vague, return the best concepts you can infer.\n"
        "\n"
        "Task: {task_description}"
    )

    def __init__(self, llm_client: Any = None) -> None:
        """Uses the swarm's configured LLM client, or falls back to a no-op."""
        self._llm_client = llm_client

    async def extract_propositions(
        self, context: str, provenance_event_id: Optional[str] = None
    ) -> List[Proposition]:
        """Extract propositional knowledge from raw context."""
        if not context or not context.strip():
            return []

        prompt = self.PROPOSITION_PROMPT.format(context=context[:4000])
        raw = await self._call_llm(prompt)
        return self._parse_propositions(raw, context, provenance_event_id)

    async def extract_prescriptions(
        self, context: str, provenance_event_id: Optional[str] = None
    ) -> List[Prescription]:
        """Extract prescriptive knowledge from raw context."""
        if not context or not context.strip():
            return []

        prompt = self.PRESCRIPTION_PROMPT.format(context=context[:4000])
        raw = await self._call_llm(prompt)
        return self._parse_prescriptions(raw, context, provenance_event_id)

    async def extract_concepts(self, task_description: str) -> List[str]:
        """Extract concept tags from a task description for retrieval routing."""
        if not task_description or not task_description.strip():
            return []

        prompt = self.CONCEPT_EXTRACTION_PROMPT.format(
            task_description=task_description[:2000]
        )
        raw = await self._call_llm(prompt)
        return self._parse_concepts(raw)

    async def extract_all(
        self, context: str, provenance_event_id: Optional[str] = None
    ) -> Tuple[List[Proposition], List[Prescription]]:
        """Extract both knowledge types in parallel."""
        if not context or not context.strip():
            return [], []

        props_task = self.extract_propositions(context, provenance_event_id)
        prescs_task = self.extract_prescriptions(context, provenance_event_id)
        propositions, prescriptions = await asyncio.gather(
            props_task, prescs_task, return_exceptions=True
        )

        if isinstance(propositions, BaseException):
            logger.debug("Proposition extraction failed: %s", propositions)
            propositions = []
        if isinstance(prescriptions, BaseException):
            logger.debug("Prescription extraction failed: %s", prescriptions)
            prescriptions = []

        return propositions, prescriptions

    # ── LLM interaction ───────────────────────────────────────────────

    async def _call_llm(self, prompt: str) -> str:
        """Call the LLM client and return raw text response."""
        if self._llm_client is None:
            return "[]"

        try:
            # Support the swarm's LLMProvider interface (async .complete())
            from dharma_swarm.models import LLMRequest

            request = LLMRequest(
                model=getattr(self._llm_client, "model", "claude-sonnet-4-20250514"),
                messages=[{"role": "user", "content": prompt}],
                system="You are a knowledge extraction assistant. Return only valid JSON.",
                max_tokens=2048,
                temperature=0.2,
            )
            response = await self._llm_client.complete(request)
            return response.content
        except Exception as exc:
            logger.debug("KnowledgeExtractor LLM call failed: %s", exc)
            return "[]"

    # ── Parsing ───────────────────────────────────────────────────────

    def _parse_propositions(
        self,
        raw: str,
        original_context: str,
        provenance_event_id: Optional[str],
    ) -> List[Proposition]:
        """Parse LLM response into Proposition objects."""
        items = self._extract_json_array(raw)
        propositions: List[Proposition] = []

        for item in items:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content", "")).strip()
            if not content:
                continue

            concepts = item.get("concepts", [])
            if isinstance(concepts, str):
                concepts = [concepts]
            concepts = [str(c).strip() for c in concepts if str(c).strip()]

            confidence = item.get("confidence", 0.8)
            try:
                confidence = max(0.0, min(1.0, float(confidence)))
            except (TypeError, ValueError):
                confidence = 0.8

            propositions.append(
                Proposition(
                    id=str(uuid.uuid4()),
                    content=content,
                    concepts=concepts[:5],
                    provenance_event_id=provenance_event_id,
                    provenance_context=original_context[:200],
                    confidence=confidence,
                )
            )

        return propositions

    def _parse_prescriptions(
        self,
        raw: str,
        original_context: str,
        provenance_event_id: Optional[str],
    ) -> List[Prescription]:
        """Parse LLM response into Prescription objects."""
        items = self._extract_json_array(raw)
        prescriptions: List[Prescription] = []

        for item in items:
            if not isinstance(item, dict):
                continue
            intent = str(item.get("intent", "")).strip()
            if not intent:
                continue

            workflow = item.get("workflow", [])
            if isinstance(workflow, str):
                workflow = [workflow]
            workflow = [str(step).strip() for step in workflow if str(step).strip()]

            concepts = item.get("concepts", [])
            if isinstance(concepts, str):
                concepts = [concepts]
            concepts = [str(c).strip() for c in concepts if str(c).strip()]

            return_score = item.get("return_score", 0.5)
            try:
                return_score = max(0.0, min(1.0, float(return_score)))
            except (TypeError, ValueError):
                return_score = 0.5

            prescriptions.append(
                Prescription(
                    id=str(uuid.uuid4()),
                    intent=intent,
                    workflow=workflow[:10],
                    return_score=return_score,
                    concepts=concepts[:5],
                    provenance_event_id=provenance_event_id,
                    provenance_context=original_context[:200],
                )
            )

        return prescriptions

    def _parse_concepts(self, raw: str) -> List[str]:
        """Parse LLM response into a list of concept strings."""
        items = self._extract_json_array(raw)
        concepts: List[str] = []
        for item in items:
            s = str(item).strip()
            if s:
                concepts.append(s)
        return concepts[:7]

    @staticmethod
    def _extract_json_array(text: str) -> list:
        """Extract a JSON array from LLM output, handling markdown fences."""
        text = text.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last lines (fences)
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()

        # Try direct parse first
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return result
            return []
        except json.JSONDecodeError:
            pass

        # Try to find a JSON array in the text
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            try:
                result = json.loads(text[start : end + 1])
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass

        return []


__all__ = ["KnowledgeExtractor"]
