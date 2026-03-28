"""Integration test for the organism's canonical pulse.

This is the GOLDEN PATH test. If this passes, the spine works.
"""

import pytest

from dharma_swarm.models import ProviderType
from dharma_swarm.organism_pulse import PulseResult, run_pulse
from dharma_swarm.signal_bus import SignalBus
from dharma_swarm.transcendence import AgentConfig


# ---------------------------------------------------------------------------
# Mock agents
# ---------------------------------------------------------------------------

MOCK_AGENTS = [
    AgentConfig(name="mock_a", provider=ProviderType.OLLAMA, model="test-model-a"),
    AgentConfig(name="mock_b", provider=ProviderType.GROQ, model="test-model-b"),
]

DIVERSE_MOCK_AGENTS = [
    AgentConfig(name="div_a", provider=ProviderType.OLLAMA, model="glm-5"),
    AgentConfig(name="div_b", provider=ProviderType.GROQ, model="qwen3-32b"),
    AgentConfig(name="div_c", provider=ProviderType.NVIDIA_NIM, model="llama-3.3"),
]


async def mock_call_fn(config: AgentConfig, prompt: str) -> str:
    """Mock LLM call returning distinct content per agent."""
    responses = {
        "mock_a": "Analysis from agent A: The market shows positive trends with probability 0.65",
        "mock_b": "Agent B assessment: Mixed signals, estimate probability at 0.55",
        "div_a": "GLM analysis: Strong macro indicators suggest upward probability 0.72",
        "div_b": "Qwen analysis: Technical patterns indicate probability of 0.58",
        "div_c": "Llama analysis: Fundamental data points to probability 0.63",
    }
    return responses.get(config.name, f"Response from {config.name}: probability 0.5")


def mock_scorer(content: str, _task) -> float:
    """Simple mock scorer based on content length."""
    if not content:
        return 0.0
    return min(len(content) / 100.0, 1.0)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOrganismPulse:
    @pytest.mark.asyncio
    async def test_pulse_completes_end_to_end(self):
        """The Rf1 test: one task, mock agents, full cycle, structured result."""
        result = await run_pulse(
            task="Summarize market outlook",
            agent_configs=MOCK_AGENTS,
            call_fn=mock_call_fn,
            scorer=mock_scorer,
            persist=False,
        )
        assert isinstance(result, PulseResult)
        assert result.duration_ms > 0
        assert result.duration_ms < 60_000  # Under 60 seconds
        assert len(result.stage_timings) == 9
        assert all(v >= 0 for v in result.stage_timings.values())
        assert result.overall_health in ("healthy", "degraded", "critical", "subcritical", "supercritical", "unknown")

    @pytest.mark.asyncio
    async def test_pulse_produces_invariant_snapshot(self):
        result = await run_pulse(
            task="Test",
            agent_configs=MOCK_AGENTS,
            call_fn=mock_call_fn,
            persist=False,
        )
        assert result.invariants is not None
        assert result.invariants.criticality_status in (
            "healthy", "subcritical", "supercritical"
        )

    @pytest.mark.asyncio
    async def test_pulse_generates_prediction(self):
        result = await run_pulse(
            task="Predict something",
            agent_configs=MOCK_AGENTS,
            call_fn=mock_call_fn,
            persist=False,
        )
        assert result.prediction is not None
        assert result.prediction.predicted_duration_ms > 0

    @pytest.mark.asyncio
    async def test_pulse_with_diverse_agents(self):
        """3 diverse agents from different model families."""
        result = await run_pulse(
            task="Analyze trends",
            agent_configs=DIVERSE_MOCK_AGENTS,
            call_fn=mock_call_fn,
            scorer=mock_scorer,
            persist=False,
        )
        assert result.agent_count == 3
        assert result.transcendence_metrics is not None
        assert result.transcendence_metrics.n_model_families == 3

    @pytest.mark.asyncio
    async def test_pulse_emits_signals(self):
        bus = SignalBus()
        result = await run_pulse(
            task="Signal test",
            agent_configs=DIVERSE_MOCK_AGENTS,
            call_fn=mock_call_fn,
            scorer=mock_scorer,
            signal_bus=bus,
            persist=False,
        )
        # Should have emitted diversity health and transcendence margin signals
        signals = bus.peek()
        assert len(signals) >= 2

    @pytest.mark.asyncio
    async def test_health_only_pulse(self):
        """Pulse with no task — just health check."""
        result = await run_pulse(persist=False)
        assert result.invariants is not None
        assert result.task_result == ""
        assert result.agent_count == 0

    @pytest.mark.asyncio
    async def test_pulse_without_call_fn(self):
        """Task provided but no call_fn — records but doesn't execute."""
        result = await run_pulse(
            task="Do something",
            agent_configs=MOCK_AGENTS,
            persist=False,
        )
        assert "not executed" in result.task_result

    @pytest.mark.asyncio
    async def test_all_nine_stages_timed(self):
        result = await run_pulse(
            task="Timing test",
            agent_configs=MOCK_AGENTS,
            call_fn=mock_call_fn,
            persist=False,
        )
        expected_stages = [
            "sense", "interpret", "constrain", "propose",
            "execute", "trace", "evaluate", "archive", "adapt",
        ]
        for stage in expected_stages:
            assert stage in result.stage_timings, f"Missing stage: {stage}"
