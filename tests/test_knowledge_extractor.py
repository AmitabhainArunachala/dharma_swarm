"""Tests for dharma_swarm.knowledge_extractor — LLM-driven knowledge extraction."""

from __future__ import annotations

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dharma_swarm.knowledge_extractor import KnowledgeExtractor
from dharma_swarm.knowledge_units import Proposition, Prescription


# ── Mock LLM client ──────────────────────────────────────────────────


class MockLLMClient:
    """Mock LLM client that returns predefined responses based on prompt content."""

    def __init__(self, response_content: str = "[]"):
        self.model = "mock-model"
        self._response_content = response_content
        self.calls: list[str] = []

    async def complete(self, request):
        self.calls.append(request.messages[0]["content"] if request.messages else "")
        return MagicMock(content=self._response_content)


def _make_mock_client(propositions=None, prescriptions=None, concepts=None):
    """Create a mock LLM client that returns appropriate responses."""

    async def _complete(request):
        prompt = request.messages[0]["content"] if request.messages else ""

        if "atomic factual claims" in prompt and propositions is not None:
            return MagicMock(content=json.dumps(propositions))
        elif "reusable skills" in prompt and prescriptions is not None:
            return MagicMock(content=json.dumps(prescriptions))
        elif "important concepts" in prompt and concepts is not None:
            return MagicMock(content=json.dumps(concepts))
        return MagicMock(content="[]")

    client = MagicMock()
    client.model = "mock-model"
    client.complete = _complete
    return client


# ── Proposition extraction tests ─────────────────────────────────────


class TestExtractPropositions:
    @pytest.mark.asyncio
    async def test_basic_extraction(self):
        mock_response = [
            {
                "content": "GPT-4 achieves 86.4% on MMLU",
                "concepts": ["GPT-4", "MMLU", "benchmark"],
                "confidence": 0.92,
            },
            {
                "content": "The training dataset contains 1.5M examples",
                "concepts": ["training", "dataset"],
                "confidence": 0.88,
            },
        ]
        client = MockLLMClient(json.dumps(mock_response))
        extractor = KnowledgeExtractor(client)

        props = await extractor.extract_propositions("Some agent interaction context")
        assert len(props) == 2
        assert all(isinstance(p, Proposition) for p in props)
        assert props[0].content == "GPT-4 achieves 86.4% on MMLU"
        assert props[0].concepts == ["GPT-4", "MMLU", "benchmark"]
        assert props[0].confidence == 0.92
        assert props[1].content == "The training dataset contains 1.5M examples"

    @pytest.mark.asyncio
    async def test_provenance_tracking(self):
        mock_response = [
            {"content": "Some fact", "concepts": ["topic"], "confidence": 0.9}
        ]
        client = MockLLMClient(json.dumps(mock_response))
        extractor = KnowledgeExtractor(client)

        props = await extractor.extract_propositions(
            "Context text here",
            provenance_event_id="event-abc",
        )
        assert len(props) == 1
        assert props[0].provenance_event_id == "event-abc"
        assert props[0].provenance_context == "Context text here"[:200]

    @pytest.mark.asyncio
    async def test_empty_context_returns_empty(self):
        client = MockLLMClient()
        extractor = KnowledgeExtractor(client)
        assert await extractor.extract_propositions("") == []
        assert await extractor.extract_propositions("   ") == []

    @pytest.mark.asyncio
    async def test_no_llm_client_returns_empty(self):
        extractor = KnowledgeExtractor(llm_client=None)
        result = await extractor.extract_propositions("Some context")
        assert result == []

    @pytest.mark.asyncio
    async def test_confidence_clamped(self):
        mock_response = [
            {"content": "Fact", "concepts": ["topic"], "confidence": 1.5},
            {"content": "Fact2", "concepts": ["topic"], "confidence": -0.3},
        ]
        client = MockLLMClient(json.dumps(mock_response))
        extractor = KnowledgeExtractor(client)

        props = await extractor.extract_propositions("ctx")
        assert props[0].confidence == 1.0
        assert props[1].confidence == 0.0

    @pytest.mark.asyncio
    async def test_concepts_truncated_to_5(self):
        mock_response = [
            {
                "content": "Fact",
                "concepts": ["a", "b", "c", "d", "e", "f", "g"],
                "confidence": 0.9,
            }
        ]
        client = MockLLMClient(json.dumps(mock_response))
        extractor = KnowledgeExtractor(client)

        props = await extractor.extract_propositions("ctx")
        assert len(props[0].concepts) <= 5

    @pytest.mark.asyncio
    async def test_skips_items_without_content(self):
        mock_response = [
            {"content": "", "concepts": ["topic"], "confidence": 0.9},
            {"content": "Valid fact", "concepts": ["topic"], "confidence": 0.9},
        ]
        client = MockLLMClient(json.dumps(mock_response))
        extractor = KnowledgeExtractor(client)

        props = await extractor.extract_propositions("ctx")
        assert len(props) == 1
        assert props[0].content == "Valid fact"


# ── Prescription extraction tests ────────────────────────────────────


class TestExtractPrescriptions:
    @pytest.mark.asyncio
    async def test_basic_extraction(self):
        mock_response = [
            {
                "intent": "debug a failing pytest test",
                "workflow": [
                    "Read the error traceback",
                    "Locate the failing assertion",
                    "Check the test fixture setup",
                ],
                "concepts": ["debugging", "pytest"],
                "return_score": 0.85,
            }
        ]
        client = MockLLMClient(json.dumps(mock_response))
        extractor = KnowledgeExtractor(client)

        prescs = await extractor.extract_prescriptions("Agent did some debugging")
        assert len(prescs) == 1
        assert isinstance(prescs[0], Prescription)
        assert prescs[0].intent == "debug a failing pytest test"
        assert len(prescs[0].workflow) == 3
        assert prescs[0].return_score == 0.85

    @pytest.mark.asyncio
    async def test_empty_context(self):
        client = MockLLMClient()
        extractor = KnowledgeExtractor(client)
        assert await extractor.extract_prescriptions("") == []

    @pytest.mark.asyncio
    async def test_no_llm_returns_empty(self):
        extractor = KnowledgeExtractor(llm_client=None)
        assert await extractor.extract_prescriptions("ctx") == []

    @pytest.mark.asyncio
    async def test_workflow_truncated(self):
        # Workflow should be capped at 10 steps
        mock_response = [
            {
                "intent": "many steps",
                "workflow": [f"Step {i}" for i in range(15)],
                "concepts": ["topic"],
                "return_score": 0.5,
            }
        ]
        client = MockLLMClient(json.dumps(mock_response))
        extractor = KnowledgeExtractor(client)

        prescs = await extractor.extract_prescriptions("ctx")
        assert len(prescs[0].workflow) <= 10

    @pytest.mark.asyncio
    async def test_return_score_clamped(self):
        mock_response = [
            {"intent": "task", "workflow": ["step"], "concepts": ["t"], "return_score": 2.0},
        ]
        client = MockLLMClient(json.dumps(mock_response))
        extractor = KnowledgeExtractor(client)

        prescs = await extractor.extract_prescriptions("ctx")
        assert prescs[0].return_score == 1.0

    @pytest.mark.asyncio
    async def test_skips_items_without_intent(self):
        mock_response = [
            {"intent": "", "workflow": ["step"], "concepts": ["t"], "return_score": 0.5},
            {"intent": "valid skill", "workflow": ["step"], "concepts": ["t"], "return_score": 0.5},
        ]
        client = MockLLMClient(json.dumps(mock_response))
        extractor = KnowledgeExtractor(client)

        prescs = await extractor.extract_prescriptions("ctx")
        assert len(prescs) == 1
        assert prescs[0].intent == "valid skill"


# ── Concept extraction tests ─────────────────────────────────────────


class TestExtractConcepts:
    @pytest.mark.asyncio
    async def test_basic_extraction(self):
        mock_response = ["debugging", "pytest", "testing", "python"]
        client = MockLLMClient(json.dumps(mock_response))
        extractor = KnowledgeExtractor(client)

        concepts = await extractor.extract_concepts("Debug a failing pytest test in Python")
        assert len(concepts) >= 1
        assert "debugging" in concepts

    @pytest.mark.asyncio
    async def test_empty_task_returns_empty(self):
        client = MockLLMClient()
        extractor = KnowledgeExtractor(client)
        assert await extractor.extract_concepts("") == []

    @pytest.mark.asyncio
    async def test_concepts_capped_at_7(self):
        mock_response = ["a", "b", "c", "d", "e", "f", "g", "h", "i"]
        client = MockLLMClient(json.dumps(mock_response))
        extractor = KnowledgeExtractor(client)

        concepts = await extractor.extract_concepts("some task")
        assert len(concepts) <= 7


# ── Parallel extraction tests ────────────────────────────────────────


class TestExtractAll:
    @pytest.mark.asyncio
    async def test_parallel_extraction(self):
        client = _make_mock_client(
            propositions=[
                {"content": "A fact", "concepts": ["topic"], "confidence": 0.9}
            ],
            prescriptions=[
                {
                    "intent": "A skill",
                    "workflow": ["step1"],
                    "concepts": ["topic"],
                    "return_score": 0.8,
                }
            ],
        )
        extractor = KnowledgeExtractor(client)

        props, prescs = await extractor.extract_all("Agent interaction context")
        assert len(props) == 1
        assert len(prescs) == 1
        assert isinstance(props[0], Proposition)
        assert isinstance(prescs[0], Prescription)

    @pytest.mark.asyncio
    async def test_empty_context(self):
        client = MockLLMClient()
        extractor = KnowledgeExtractor(client)
        props, prescs = await extractor.extract_all("")
        assert props == []
        assert prescs == []

    @pytest.mark.asyncio
    async def test_graceful_failure_handling(self):
        """If one extraction fails, the other should still return results."""

        async def _fail_on_props(request):
            prompt = request.messages[0]["content"]
            if "atomic factual claims" in prompt:
                raise Exception("LLM error")
            return MagicMock(
                content=json.dumps(
                    [{"intent": "skill", "workflow": ["s"], "concepts": ["t"], "return_score": 0.5}]
                )
            )

        client = MagicMock()
        client.model = "mock"
        client.complete = _fail_on_props

        extractor = KnowledgeExtractor(client)
        props, prescs = await extractor.extract_all("ctx")
        assert props == []
        assert len(prescs) == 1


# ── JSON parsing edge case tests ─────────────────────────────────────


class TestJsonParsing:
    def test_parse_markdown_fenced_json(self):
        raw = '```json\n[{"content": "fact", "concepts": ["t"], "confidence": 0.9}]\n```'
        items = KnowledgeExtractor._extract_json_array(raw)
        assert len(items) == 1

    def test_parse_plain_json(self):
        raw = '[{"content": "fact", "concepts": ["t"], "confidence": 0.9}]'
        items = KnowledgeExtractor._extract_json_array(raw)
        assert len(items) == 1

    def test_parse_json_with_preamble(self):
        raw = 'Here are the facts:\n[{"content": "fact"}]'
        items = KnowledgeExtractor._extract_json_array(raw)
        assert len(items) == 1

    def test_parse_empty_array(self):
        items = KnowledgeExtractor._extract_json_array("[]")
        assert items == []

    def test_parse_invalid_json_returns_empty(self):
        items = KnowledgeExtractor._extract_json_array("not json at all")
        assert items == []

    def test_parse_non_array_json(self):
        items = KnowledgeExtractor._extract_json_array('{"key": "value"}')
        assert items == []

    def test_parse_concepts_as_string(self):
        """Test that string concepts get handled properly."""
        extractor = KnowledgeExtractor(None)
        raw = '[{"content": "fact", "concepts": "single_concept", "confidence": 0.9}]'
        items = KnowledgeExtractor._extract_json_array(raw)
        props = extractor._parse_propositions(raw, "ctx", None)
        assert len(props) == 1
        assert props[0].concepts == ["single_concept"]

    def test_parse_workflow_as_string(self):
        extractor = KnowledgeExtractor(None)
        raw = '[{"intent": "task", "workflow": "single step", "concepts": ["t"], "return_score": 0.5}]'
        prescs = extractor._parse_prescriptions(raw, "ctx", None)
        assert len(prescs) == 1
        assert prescs[0].workflow == ["single step"]


# ── LLM interaction tests ────────────────────────────────────────────


class TestLLMInteraction:
    @pytest.mark.asyncio
    async def test_llm_called_with_correct_params(self):
        client = MockLLMClient("[]")
        extractor = KnowledgeExtractor(client)

        await extractor.extract_propositions("My context")
        assert len(client.calls) == 1
        assert "My context" in client.calls[0]
        assert "atomic factual claims" in client.calls[0]

    @pytest.mark.asyncio
    async def test_llm_error_returns_empty(self):
        async def _fail(request):
            raise Exception("API error")

        client = MagicMock()
        client.model = "mock"
        client.complete = _fail

        extractor = KnowledgeExtractor(client)
        props = await extractor.extract_propositions("ctx")
        assert props == []

    @pytest.mark.asyncio
    async def test_context_truncated_to_4000(self):
        long_context = "x" * 10000
        client = MockLLMClient("[]")
        extractor = KnowledgeExtractor(client)

        await extractor.extract_propositions(long_context)
        assert len(client.calls) == 1
        # The prompt should contain the context but truncated
        prompt = client.calls[0]
        # Context in the prompt template after "Interaction:\n"
        ctx_start = prompt.index("Interaction:\n") + len("Interaction:\n")
        ctx_in_prompt = prompt[ctx_start:]
        assert len(ctx_in_prompt) <= 4000
