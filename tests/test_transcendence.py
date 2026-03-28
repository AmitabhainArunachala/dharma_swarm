"""Tests for transcendence.py — the core protocol engine."""

import asyncio

import pytest

from dharma_swarm.models import ProviderType
from dharma_swarm.transcendence import (
    AgentConfig,
    AggregationMethod,
    EnsembleResult,
    TranscendenceProtocol,
    TranscendenceTask,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DIVERSE_AGENTS = [
    AgentConfig(name="agent_a", provider=ProviderType.OLLAMA, model="glm-5"),
    AgentConfig(name="agent_b", provider=ProviderType.GROQ, model="qwen3-32b"),
    AgentConfig(name="agent_c", provider=ProviderType.NVIDIA_NIM, model="llama-3.3"),
]

HOMOGENEOUS_AGENTS = [
    AgentConfig(name="clone_1", provider=ProviderType.OLLAMA, model="glm-5"),
    AgentConfig(name="clone_2", provider=ProviderType.OLLAMA, model="glm-5"),
]


async def mock_call_diverse(config: AgentConfig, prompt: str) -> str:
    """Mock LLM call that returns different content per agent."""
    responses = {
        "agent_a": "The market shows bullish signals with probability 0.72 based on macro trends",
        "agent_b": "Bearish indicators dominate, estimate probability at 0.45 for upward movement",
        "agent_c": "Mixed signals, probability 0.60 of positive outcome given current volatility",
    }
    return responses.get(config.name, "Unknown agent response")


async def mock_call_homogeneous(config: AgentConfig, prompt: str) -> str:
    """Mock LLM call where all agents return similar content."""
    return "The probability is 0.65 based on standard analysis"


def prediction_scorer(content: str, task: TranscendenceTask) -> float:
    """Score based on content quality (mock)."""
    if not content:
        return 0.0
    # More specific content scores higher
    keywords = ["probability", "based on", "signals", "trends", "analysis"]
    hits = sum(1 for k in keywords if k in content.lower())
    return min(hits / len(keywords), 1.0)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTranscendenceProtocol:
    @pytest.mark.asyncio
    async def test_basic_execution(self):
        protocol = TranscendenceProtocol(
            call_fn=mock_call_diverse,
            scorer=prediction_scorer,
            persist=False,
        )
        task = TranscendenceTask(prompt="Will gold prices rise?", task_type="prediction")

        result = await protocol.execute(task, DIVERSE_AGENTS)

        assert isinstance(result, EnsembleResult)
        assert len(result.agent_outputs) == 3
        assert result.metrics.n_agents == 3
        assert result.metrics.n_model_families == 3

    @pytest.mark.asyncio
    async def test_diversity_measured(self):
        protocol = TranscendenceProtocol(
            call_fn=mock_call_diverse,
            scorer=prediction_scorer,
            persist=False,
        )
        task = TranscendenceTask(prompt="Test", task_type="prediction")

        result = await protocol.execute(task, DIVERSE_AGENTS)

        # Diverse agents should produce measurable behavioral diversity
        assert result.metrics.behavioral_div > 0.0

    @pytest.mark.asyncio
    async def test_homogeneous_low_diversity(self):
        protocol = TranscendenceProtocol(
            call_fn=mock_call_homogeneous,
            scorer=prediction_scorer,
            persist=False,
        )
        task = TranscendenceTask(prompt="Test", task_type="prediction")

        result = await protocol.execute(task, HOMOGENEOUS_AGENTS)

        # Homogeneous agents should have zero behavioral diversity
        assert result.metrics.behavioral_div == 0.0

    @pytest.mark.asyncio
    async def test_probability_extraction(self):
        protocol = TranscendenceProtocol(
            call_fn=mock_call_diverse,
            scorer=prediction_scorer,
            persist=False,
        )
        task = TranscendenceTask(prompt="Test", task_type="prediction")

        result = await protocol.execute(task, DIVERSE_AGENTS)

        # All diverse agents have probability values in their responses
        probs = [o.probability for o in result.agent_outputs if o.probability is not None]
        assert len(probs) >= 2
        assert all(0.0 <= p <= 1.0 for p in probs)

    @pytest.mark.asyncio
    async def test_ensemble_probability_computed(self):
        protocol = TranscendenceProtocol(
            call_fn=mock_call_diverse,
            scorer=prediction_scorer,
            aggregation=AggregationMethod.QUALITY_WEIGHTED,
            persist=False,
        )
        task = TranscendenceTask(prompt="Test", task_type="prediction")

        result = await protocol.execute(task, DIVERSE_AGENTS)

        assert result.ensemble_probability is not None
        assert 0.0 <= result.ensemble_probability <= 1.0

    @pytest.mark.asyncio
    async def test_temperature_concentrate_method(self):
        protocol = TranscendenceProtocol(
            call_fn=mock_call_diverse,
            scorer=prediction_scorer,
            aggregation=AggregationMethod.TEMPERATURE_CONCENTRATE,
            temperature=0.3,
            persist=False,
        )
        task = TranscendenceTask(prompt="Test", task_type="prediction")

        result = await protocol.execute(task, DIVERSE_AGENTS)

        assert result.ensemble_probability is not None
        assert result.aggregation_method == AggregationMethod.TEMPERATURE_CONCENTRATE

    @pytest.mark.asyncio
    async def test_majority_vote_method(self):
        protocol = TranscendenceProtocol(
            call_fn=mock_call_diverse,
            scorer=prediction_scorer,
            aggregation=AggregationMethod.MAJORITY_VOTE,
            persist=False,
        )
        task = TranscendenceTask(prompt="Test", task_type="general")

        result = await protocol.execute(task, DIVERSE_AGENTS)

        assert result.ensemble_output != ""

    @pytest.mark.asyncio
    async def test_metrics_complete(self):
        protocol = TranscendenceProtocol(
            call_fn=mock_call_diverse,
            scorer=prediction_scorer,
            persist=False,
        )
        task = TranscendenceTask(prompt="Test", task_type="prediction")

        result = await protocol.execute(task, DIVERSE_AGENTS)

        m = result.metrics
        assert m.n_agents == 3
        assert m.ensemble_score >= 0.0
        assert m.best_individual_score >= 0.0
        assert m.mean_individual_score >= 0.0
        assert isinstance(m.transcendence_margin, float)
        assert isinstance(m.aggregation_lift, float)
        assert isinstance(m.kv_diversity_term, float)
        assert m.diversity_status in ("healthy", "degraded", "critical", "unknown")


class TestProbabilityExtraction:
    def test_extract_decimal(self):
        prob = TranscendenceProtocol._extract_probability("probability 0.72")
        assert prob == pytest.approx(0.72)

    def test_extract_percentage(self):
        prob = TranscendenceProtocol._extract_probability("85% probability of success")
        assert prob == pytest.approx(0.85)

    def test_extract_from_text(self):
        prob = TranscendenceProtocol._extract_probability(
            "Based on my analysis, the estimate is 0.63"
        )
        assert prob == pytest.approx(0.63)

    def test_no_probability(self):
        prob = TranscendenceProtocol._extract_probability("no numbers here")
        assert prob is None


class TestAgentFailureHandling:
    @pytest.mark.asyncio
    async def test_one_agent_fails(self):
        call_count = 0

        async def failing_call(config: AgentConfig, prompt: str) -> str:
            nonlocal call_count
            call_count += 1
            if config.name == "agent_b":
                raise RuntimeError("LLM provider down")
            return f"Response from {config.name} with probability 0.65"

        protocol = TranscendenceProtocol(
            call_fn=failing_call,
            persist=False,
        )
        task = TranscendenceTask(prompt="Test", task_type="prediction")

        result = await protocol.execute(task, DIVERSE_AGENTS)

        # Should still produce a result with the remaining agents
        assert len(result.agent_outputs) == 2
        assert result.metrics.n_agents == 2
