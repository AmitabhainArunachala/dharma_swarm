from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from dharma_swarm.agent_runner import AgentRunner
from dharma_swarm.decision_router import RoutePath
from dharma_swarm.mission_contract import load_honors_checkpoint
from dharma_swarm.models import (
    AgentConfig,
    AgentRole,
    LLMRequest,
    LLMResponse,
    ProviderType,
    Task,
)
from dharma_swarm.provider_policy import ProviderRouteDecision


def _config(tmp_path: Path) -> AgentConfig:
    state_dir = tmp_path / ".dharma"
    state_dir.mkdir(exist_ok=True)
    return AgentConfig(
        name="semantic-agent",
        role=AgentRole.RESEARCHER,
        provider=ProviderType.OPENAI,
        model="gpt-4.1",
        metadata={
            "state_dir": str(state_dir),
            "memory_state_dir": str(state_dir),
        },
    )


class _RecordingProvider:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self.requests: list[LLMRequest] = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("unexpected completion call")
        return self._responses.pop(0)


class _RoutedRecordingProvider:
    def __init__(self, *, content: str) -> None:
        self._content = content
        self.calls: list[tuple[object, LLMRequest, list[ProviderType] | None]] = []
        self.feedback: list[dict[str, object]] = []

    async def complete_for_task(
        self,
        route_request,
        request: LLMRequest,
        *,
        available_provider_types: list[ProviderType] | None = None,
    ) -> tuple[ProviderRouteDecision, LLMResponse]:
        self.calls.append((route_request, request, available_provider_types))
        selected_provider = (
            available_provider_types[0]
            if available_provider_types
            else ProviderType.OPENAI
        )
        return (
            ProviderRouteDecision(
                path=RoutePath.DELIBERATIVE,
                selected_provider=selected_provider,
                selected_model_hint=request.model,
                fallback_providers=[],
                fallback_model_hints=[],
                confidence=0.88,
                requires_human=False,
                reasons=["semantic-test"],
            ),
            LLMResponse(
                content=self._content,
                model=request.model,
                usage={"total_tokens": 321},
            ),
        )

    def record_task_feedback(self, **kwargs) -> str:
        self.feedback.append(kwargs)
        return "sig-semantic"


class _DelayedRecordingProvider:
    def __init__(self, responses: list[tuple[float, LLMResponse]]) -> None:
        self._responses = list(responses)
        self.requests: list[LLMRequest] = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("unexpected completion call")
        delay, response = self._responses.pop(0)
        if delay > 0:
            await asyncio.sleep(delay)
        return response


def _good_operator_brief() -> str:
    return (
        "Operator brief: The CT-VSM live round is now semantically viable. "
        "The agent stayed on the intended provider lane, generated a concrete "
        "operator-facing summary, and grounded the output in runtime evidence "
        "instead of meta commentary. Evidence: the selected seat completed the "
        "task, the provider/model handoff stayed consistent, and the response "
        "contained explicit findings plus next actions. Next actions: keep the "
        "same seat pinned for high-reasoning work, reject leaked reasoning tags "
        "at acceptance time, and route malformed completions back into one "
        "same-seat repair pass before the orchestrator marks the task complete."
    )


def _good_honors_brief() -> str:
    return (
        "Operator brief: The honors checkpoint is now forcing defended analytical output.\n\n"
        "Findings:\n"
        "- dharma_swarm/agent_runner.py now treats unsupported completions as repair candidates rather than silent wins.\n"
        "- dharma_swarm/orchestrator.py only promotes work after it sees a passing checkpoint packet.\n"
        "- tests/test_agent_runner_semantic_acceptance.py and tests/test_orchestrator.py cover the new gate.\n\n"
        "Evidence:\n"
        "- File evidence: dharma_swarm/agent_runner.py, dharma_swarm/orchestrator.py\n"
        "- Test evidence: tests/test_agent_runner_semantic_acceptance.py, tests/test_orchestrator.py\n"
        "- Context evidence: CT-VSM, active inference, mission contract\n\n"
        "System effects:\n"
        "- The local runner now blocks elegant unsupported summaries.\n"
        "- The control plane learns from grounded completions instead of raw strings.\n\n"
        "Residual risks:\n"
        "- Heuristic evidence scoring can still over-credit shallow references.\n\n"
        "Next actions:\n"
        "1. Add citation-path validation for high-stakes research tasks.\n"
        "2. Feed judge-pack scores into the evolution archive.\n"
    )


def _good_honors_brief_with_explicit_obligations() -> str:
    return (
        "Operator brief: The honors checkpoint now enforces explicit evidence obligations before completion.\n\n"
        "Findings:\n"
        "- dharma_swarm/agent_runner.py computes missing obligations instead of inferring grounding from surface structure alone.\n"
        "- dharma_swarm/mission_contract.py defines the contract fields for required evidence, file, and test references.\n"
        "- tests/test_agent_runner_semantic_acceptance.py and tests/test_mission_contract.py lock the stricter gate into place.\n\n"
        "Evidence:\n"
        "- File evidence: dharma_swarm/agent_runner.py, dharma_swarm/mission_contract.py, dharma_swarm/orchestrator.py\n"
        "- Test evidence: tests/test_agent_runner_semantic_acceptance.py, tests/test_mission_contract.py\n"
        "- Artifact evidence: reports/verification/ctvsm_probe.json\n"
        "- Context evidence: CT-VSM, active inference, mission contract\n\n"
        "System effects:\n"
        "- The runner now fails closed when required obligations are missing.\n"
        "- The orchestrator only learns from defended outputs that cite the expected artifacts.\n\n"
        "Residual risks:\n"
        "- Explicit obligations still need truth-path validation for externally sourced claims.\n\n"
        "Next actions:\n"
        "1. Validate cited artifact paths against the actual filesystem or trace store on high-stakes tasks.\n"
        "2. Persist obligation deficits into router and archive feedback for evolution-time learning.\n"
    )


@pytest.mark.asyncio
async def test_run_task_repairs_semantic_failure_before_success(
    fast_gate,
    tmp_path: Path,
) -> None:
    provider = _RecordingProvider(
        responses=[
            LLMResponse(
                content="</think>\nThere was an issue with the selected model.",
                model="gpt-4.1",
            ),
            LLMResponse(content=_good_operator_brief(), model="gpt-4.1"),
        ]
    )
    runner = AgentRunner(_config(tmp_path), provider=provider)
    await runner.start()

    result = await runner.run_task(
        Task(
            id="task-semantic-repair",
            title="Explain the CT-VSM live round",
            description="Produce an evidence-backed operator brief with concrete findings and next actions.",
            metadata={"task_type": "research"},
        )
    )

    assert result.startswith("Operator brief:")
    assert len(provider.requests) == 2
    assert provider.requests[0].model == "gpt-4.1"
    assert provider.requests[1].model == "gpt-4.1"
    critique_prompt = provider.requests[1].messages[-1]["content"].lower()
    assert "failed the completion acceptance gate" in critique_prompt
    assert "no reasoning tags" in critique_prompt


@pytest.mark.asyncio
async def test_run_task_fails_when_repair_attempt_remains_semantically_invalid(
    fast_gate,
    tmp_path: Path,
) -> None:
    provider = _RecordingProvider(
        responses=[
            LLMResponse(content="</think>\nbad stub", model="gpt-4.1"),
            LLMResponse(content="</think>\nstill bad", model="gpt-4.1"),
        ]
    )
    runner = AgentRunner(_config(tmp_path), provider=provider)
    await runner.start()

    with pytest.raises(RuntimeError, match="Semantic acceptance failed"):
        await runner.run_task(
            Task(
                id="task-semantic-fail",
                title="Explain the CT-VSM live round",
                description="Produce an evidence-backed operator brief with concrete findings and next actions.",
                metadata={"task_type": "research", "semantic_repair_attempts": 1},
            )
        )

    assert len(provider.requests) == 2
    assert runner.state.tasks_completed == 0
    assert "Semantic acceptance failed" in (runner.state.error or "")


@pytest.mark.asyncio
async def test_run_task_repairs_exploration_preamble_into_final_answer(
    fast_gate,
    tmp_path: Path,
) -> None:
    provider = _RecordingProvider(
        responses=[
            LLMResponse(
                content=(
                    "I'll begin by reading existing context, then I'll produce the brief.\n\n"
                    "```bash\nfind ~/.dharma -type f -name \"*.md\"\n```"
                ),
                model="gpt-4.1",
            ),
            LLMResponse(content=_good_operator_brief(), model="gpt-4.1"),
        ]
    )
    runner = AgentRunner(_config(tmp_path), provider=provider)
    await runner.start()

    result = await runner.run_task(
        Task(
            id="task-semantic-preamble",
            title="Explain the CT-VSM live round",
            description="Produce an evidence-backed operator brief with concrete findings and next actions.",
            metadata={"task_type": "research"},
        )
    )

    assert result.startswith("Operator brief:")
    assert len(provider.requests) == 2


@pytest.mark.asyncio
async def test_run_task_rejects_long_roleplayed_exploration_preamble(
    fast_gate,
    tmp_path: Path,
) -> None:
    provider = _RecordingProvider(
        responses=[
            LLMResponse(
                content=(
                    "I'll begin by reading existing context to understand CT-VSM, then I'll produce the brief.\n\n"
                    "```bash\nfind ~/.dharma -type f -name \"*.md\" | head\n```\n\n"
                    "Let me explore the system state first before I finalize the answer.\n\n"
                    "## CT-VSM Live Round: Operator Brief\n\n"
                    "### Executive Summary\n"
                    "CT-VSM refers to Cybernetic Theory and the Viable System Model. "
                    "The live round is an active deployment with real agents. "
                    "Evidence: the colony has completed tasks and the organism is flowing. "
                    "Next actions: keep the lane pinned, add semantic repair, and reject malformed completions."
                ),
                model="gpt-4.1",
            ),
            LLMResponse(content=_good_operator_brief(), model="gpt-4.1"),
        ]
    )
    runner = AgentRunner(_config(tmp_path), provider=provider)
    await runner.start()

    result = await runner.run_task(
        Task(
            id="task-semantic-long-preamble",
            title="Explain the CT-VSM live round",
            description="Produce an evidence-backed operator brief with concrete findings and next actions.",
            metadata={"task_type": "research"},
        )
    )

    assert result.startswith("Operator brief:")
    assert len(provider.requests) == 2


@pytest.mark.asyncio
async def test_run_task_records_semantic_quality_into_router_feedback_and_active_inference(
    fast_gate,
    monkeypatch,
    tmp_path: Path,
) -> None:
    provider = _RoutedRecordingProvider(content=_good_operator_brief())
    fake_engine = SimpleNamespace()
    fake_engine.predictions = []
    fake_engine.observations = []

    def _predict(agent_id: str, task_id: str, task_type: str = "general"):
        prediction = SimpleNamespace(
            agent_id=agent_id,
            task_id=task_id,
            task_type=task_type,
            predicted_quality=0.5,
        )
        fake_engine.predictions.append(prediction)
        return prediction

    def _observe(prediction, observed_quality: float, *, persist: bool = True):
        fake_engine.observations.append((prediction, observed_quality, persist))
        return SimpleNamespace()

    fake_engine.predict = _predict
    fake_engine.observe = _observe
    monkeypatch.setattr(
        "dharma_swarm.active_inference.get_engine",
        lambda state_dir=None: fake_engine,
        raising=True,
    )

    runner = AgentRunner(_config(tmp_path), provider=provider)
    await runner.start()

    await runner.run_task(
        Task(
            id="task-semantic-feedback",
            title="Explain the CT-VSM live round",
            description="Produce an evidence-backed operator brief with concrete findings and next actions.",
            metadata={"task_type": "research"},
        )
    )

    assert len(fake_engine.predictions) == 1
    assert fake_engine.predictions[0].task_type == "research"
    assert len(fake_engine.observations) == 1
    feedback = provider.feedback[0]
    assert feedback["quality_score"] > 0.6
    assert fake_engine.observations[0][1] == pytest.approx(feedback["quality_score"])


@pytest.mark.asyncio
async def test_run_task_allows_second_repair_attempt_for_semantic_failures(
    fast_gate,
    tmp_path: Path,
) -> None:
    provider = _RecordingProvider(
        responses=[
            LLMResponse(
                content=(
                    "I'll investigate the CT-VSM live round by first reading existing context, "
                    "then produce an operator brief.\n\n"
                    "```bash\ngrep -r \"CT-VSM\" ~/.dharma/\n```"
                ),
                model="gpt-4.1",
            ),
            LLMResponse(
                content='grep -r "CT-VSM" ~/.dharma/ 2>/dev/null | head -100',
                model="gpt-4.1",
            ),
            LLMResponse(content=_good_operator_brief(), model="gpt-4.1"),
        ]
    )
    runner = AgentRunner(_config(tmp_path), provider=provider)
    await runner.start()

    result = await runner.run_task(
        Task(
            id="task-semantic-second-repair",
            title="Explain the CT-VSM live round",
            description="Produce an evidence-backed operator brief with concrete findings and next actions.",
            metadata={"task_type": "research"},
        )
    )

    assert result.startswith("Operator brief:")
    assert len(provider.requests) == 3


@pytest.mark.asyncio
async def test_run_task_repairs_timed_out_completion_attempt_before_terminal_failure(
    fast_gate,
    tmp_path: Path,
) -> None:
    provider = _DelayedRecordingProvider(
        responses=[
            (0.05, LLMResponse(content=_good_operator_brief(), model="gpt-4.1")),
            (0.0, LLMResponse(content=_good_operator_brief(), model="gpt-4.1")),
        ]
    )
    runner = AgentRunner(_config(tmp_path), provider=provider)
    await runner.start()

    result = await runner.run_task(
        Task(
            id="task-semantic-timeout-repair",
            title="Explain the CT-VSM live round",
            description="Produce an evidence-backed operator brief with concrete findings and next actions.",
            metadata={
                "task_type": "research",
                "semantic_repair_attempts": 1,
                "semantic_attempt_timeout_seconds": 0.01,
            },
        )
    )

    assert result.startswith("Operator brief:")
    assert len(provider.requests) == 2
    critique_prompt = provider.requests[1].messages[-1]["content"].lower()
    assert "timed out" in critique_prompt
    assert "attempt timeout" in critique_prompt


@pytest.mark.asyncio
async def test_run_task_repairs_honors_checkpoint_failure_before_success(
    fast_gate,
    tmp_path: Path,
) -> None:
    provider = _RecordingProvider(
        responses=[
            LLMResponse(
                content=(
                    "Operator brief: The result looks much better now. "
                    "Findings: the route is stable. Next actions: keep monitoring."
                ),
                model="gpt-4.1",
            ),
            LLMResponse(content=_good_honors_brief(), model="gpt-4.1"),
        ]
    )
    runner = AgentRunner(_config(tmp_path), provider=provider)
    await runner.start()
    task = Task(
        id="task-honors-repair",
        title="Explain the honors checkpoint rollout",
        description="Produce a defended operator brief with evidence, tests, system effects, and concrete fixes.",
        metadata={
            "task_type": "research",
            "completion_contract": {
                "mode": "honors",
                "stakeholders": ["operator", "orchestrator"],
                "required_sections": [
                    "Findings",
                    "Evidence",
                    "System effects",
                    "Residual risks",
                    "Next actions",
                ],
                "required_context_refs": ["CT-VSM", "active inference", "mission contract"],
                "minimum_file_references": 2,
                "minimum_test_references": 1,
                "minimum_fix_proposals": 2,
                "minimum_context_references": 2,
                "minimum_meta_observations": 1,
                "require_system_effects": True,
            },
        },
    )

    result = await runner.run_task(task)

    assert result.startswith("Operator brief:")
    assert len(provider.requests) == 2
    critique_prompt = provider.requests[1].messages[-1]["content"].lower()
    assert "honors checkpoint failed" in critique_prompt
    checkpoint = load_honors_checkpoint(task.metadata)
    assert checkpoint is not None
    assert checkpoint.judge_pack.accepted is True
    assert checkpoint.defense_packet.files_listed[:2] == [
        "dharma_swarm/agent_runner.py",
        "dharma_swarm/orchestrator.py",
    ]
    assert "tests/test_orchestrator.py" in checkpoint.defense_packet.tests_flagged
    assert checkpoint.defense_packet.supported_claim_count >= 2
    assert checkpoint.defense_packet.unsupported_claim_ratio < 0.5


@pytest.mark.asyncio
async def test_run_task_repairs_missing_explicit_honors_obligations(
    fast_gate,
    tmp_path: Path,
) -> None:
    provider = _RecordingProvider(
        responses=[
            LLMResponse(content=_good_honors_brief(), model="gpt-4.1"),
            LLMResponse(content=_good_honors_brief_with_explicit_obligations(), model="gpt-4.1"),
        ]
    )
    runner = AgentRunner(_config(tmp_path), provider=provider)
    await runner.start()
    task = Task(
        id="task-honors-explicit-obligations",
        title="Explain the stricter honors evidence contract",
        description="Produce a defended operator brief with explicit evidence, file, and test obligations.",
        metadata={
            "task_type": "research",
            "completion_contract": {
                "mode": "honors",
                "stakeholders": ["operator", "orchestrator"],
                "required_sections": [
                    "Findings",
                    "Evidence",
                    "System effects",
                    "Residual risks",
                    "Next actions",
                ],
                "required_context_refs": ["CT-VSM", "active inference", "mission contract"],
                "required_evidence_paths": ["reports/verification/ctvsm_probe.json"],
                "required_file_references": [
                    "dharma_swarm/agent_runner.py",
                    "dharma_swarm/mission_contract.py",
                ],
                "required_test_references": ["tests/test_mission_contract.py"],
                "minimum_file_references": 2,
                "minimum_test_references": 1,
                "minimum_fix_proposals": 2,
                "minimum_context_references": 2,
                "minimum_meta_observations": 1,
                "minimum_supported_claim_count": 2,
                "maximum_unsupported_claim_ratio": 0.34,
                "require_system_effects": True,
            },
        },
    )

    result = await runner.run_task(task)

    assert result.startswith("Operator brief:")
    assert len(provider.requests) == 2
    critique_prompt = provider.requests[1].messages[-1]["content"]
    assert "reports/verification/ctvsm_probe.json" in critique_prompt
    assert "dharma_swarm/mission_contract.py" in critique_prompt
    assert "tests/test_mission_contract.py" in critique_prompt
    checkpoint = load_honors_checkpoint(task.metadata)
    assert checkpoint is not None
    assert checkpoint.judge_pack.accepted is True
    assert checkpoint.defense_packet.missing_evidence_paths == []
    assert checkpoint.defense_packet.missing_file_references == []
    assert checkpoint.defense_packet.missing_test_references == []
    assert checkpoint.defense_packet.missing_context_refs == []
    assert checkpoint.defense_packet.missing_stakeholders == []
