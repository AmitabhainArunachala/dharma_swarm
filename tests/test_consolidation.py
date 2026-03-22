"""Tests for the Consolidation Cycle (behavioral backpropagation).

Tests the four phases: observation, contrarian dialogue,
behavioral backprop, and differentiation check.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dharma_swarm.consolidation import (
    AgentStateSnapshot,
    BehavioralBackprop,
    BehavioralCorrection,
    ConsolidationCycle,
    ConsolidationOutcome,
    ContrarianDialogue,
    DebateTurn,
    DifferentiationCheck,
    DifferentiationProposal,
    LossItem,
    SystemLossReport,
    SystemObserver,
    SystemStateReport,
)
from dharma_swarm.models import LLMRequest, ProviderType
from dharma_swarm.runtime_provider import RuntimeProviderConfig


# ---------------------------------------------------------------------------
# Data model tests
# ---------------------------------------------------------------------------


class TestModels:
    def test_system_state_report_defaults(self):
        r = SystemStateReport(consolidator_id="alpha")
        assert r.consolidator_id == "alpha"
        assert r.agent_snapshots == []
        assert r.stigmergy_density == 0

    def test_loss_item_validation(self):
        item = LossItem(
            category="fitness_gap",
            severity=0.8,
            affected_agents=["operator"],
            description="Operator fitness below threshold",
        )
        assert item.severity == 0.8

    def test_loss_item_severity_bounds(self):
        with pytest.raises(Exception):
            LossItem(category="test", severity=1.5, description="invalid")

    def test_behavioral_correction_defaults(self):
        c = BehavioralCorrection(
            correction_type="prompt_update",
            target_agent="operator",
            description="test",
            rationale="test",
        )
        assert c.severity == 0.5
        assert c.applied is False
        assert c.veto_required is False

    def test_consolidation_outcome_serialization(self):
        o = ConsolidationOutcome(
            cycle_number=1,
            corrections_proposed=3,
            corrections_applied=2,
            system_loss_score=0.4,
        )
        data = o.model_dump_json()
        o2 = ConsolidationOutcome.model_validate_json(data)
        assert o2.cycle_number == 1
        assert o2.corrections_applied == 2

    def test_debate_turn_structure(self):
        t = DebateTurn(
            speaker="alpha", round_number=1,
            position="thesis", content="test content",
        )
        assert t.speaker == "alpha"

    def test_differentiation_proposal(self):
        p = DifferentiationProposal(
            proposed_role="specialist_sarcasm",
            justification="persistent gap",
            capability_gap="sarcasm detection",
            evidence_cycles=[1, 2, 3],
        )
        assert p.status == "proposed"


# ---------------------------------------------------------------------------
# SystemObserver tests
# ---------------------------------------------------------------------------


class TestSystemObserver:
    @pytest.mark.asyncio
    async def test_observe_empty_state(self, tmp_path: Path):
        observer = SystemObserver(tmp_path)
        report = await observer.observe("alpha")
        assert report.consolidator_id == "alpha"
        assert report.agent_snapshots == []
        assert report.stigmergy_density == 0

    @pytest.mark.asyncio
    async def test_observe_reads_agent_memory(self, tmp_path: Path):
        # Create agent memory directory with working memory
        agent_dir = tmp_path / "agent_memory" / "operator"
        agent_dir.mkdir(parents=True)
        (agent_dir / "working.json").write_text(json.dumps({
            "key1": {"key": "key1", "value": "test", "category": "working"},
            "key2": {"key": "key2", "value": "test2", "category": "working"},
        }))

        observer = SystemObserver(tmp_path)
        report = await observer.observe("alpha")
        assert len(report.agent_snapshots) == 1
        assert report.agent_snapshots[0].name == "operator"
        assert "key1" in report.agent_snapshots[0].working_memory_keys

    @pytest.mark.asyncio
    async def test_observe_reads_stigmergy(self, tmp_path: Path):
        marks_dir = tmp_path / "stigmergy"
        marks_dir.mkdir(parents=True)
        (marks_dir / "marks.jsonl").write_text(
            '{"id": "1", "agent": "op"}\n'
            '{"id": "2", "agent": "arch"}\n'
        )

        observer = SystemObserver(tmp_path)
        report = await observer.observe("beta")
        assert report.stigmergy_density == 2

    def test_compress_for_llm_respects_budget(self, tmp_path: Path):
        observer = SystemObserver(tmp_path)
        report = SystemStateReport(
            consolidator_id="alpha",
            agent_snapshots=[
                AgentStateSnapshot(name=f"agent_{i}") for i in range(20)
            ],
        )
        text = observer.compress_for_llm(report, max_chars=500)
        assert len(text) <= 500


# ---------------------------------------------------------------------------
# ContrarianDialogue tests
# ---------------------------------------------------------------------------


class TestContrarianDialogue:
    @pytest.mark.asyncio
    async def test_dialogue_produces_loss_report(self):
        dialogue = ContrarianDialogue(rounds=1)

        # Mock provider
        mock_provider = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Test analysis response"
        mock_provider.complete = AsyncMock(return_value=mock_response)

        # For the loss extraction, return valid JSON
        loss_json = json.dumps({
            "agreed_issues": [
                {"category": "fitness_gap", "severity": 0.6,
                 "affected_agents": ["operator"],
                 "description": "test issue",
                 "proposed_correction": "fix it"}
            ],
            "alpha_only_issues": [],
            "beta_only_issues": [],
            "system_loss_score": 0.4,
        })

        # Make the provider return different things for analysis vs extraction
        responses = [
            MagicMock(content="Alpha analysis"),   # Alpha analysis
            MagicMock(content="Beta analysis"),     # Beta analysis
            MagicMock(content="Beta round 1"),      # Beta debate
            MagicMock(content="Alpha round 1"),     # Alpha debate
            MagicMock(content=loss_json),            # Loss extraction
        ]
        mock_provider.complete = AsyncMock(side_effect=responses)

        report = await dialogue.run("state alpha", "state beta", mock_provider)
        assert isinstance(report, SystemLossReport)
        assert len(report.debate_transcript) > 0

    def test_parse_loss_report_valid_json(self):
        dialogue = ContrarianDialogue()
        raw = json.dumps({
            "agreed_issues": [
                {"category": "fitness_gap", "severity": 0.5,
                 "affected_agents": ["op"], "description": "test"}
            ],
            "alpha_only_issues": [],
            "beta_only_issues": [],
            "system_loss_score": 0.3,
        })
        report = dialogue._parse_loss_report(raw)
        assert len(report.agreed_issues) == 1
        assert report.system_loss_score == 0.3

    def test_parse_loss_report_invalid_json(self):
        dialogue = ContrarianDialogue()
        report = dialogue._parse_loss_report("not json at all")
        assert report.system_loss_score == 0.5  # default fallback


# ---------------------------------------------------------------------------
# BehavioralBackprop tests
# ---------------------------------------------------------------------------


class TestBehavioralBackprop:
    @pytest.mark.asyncio
    async def test_high_severity_requires_veto(self, tmp_path: Path):
        backprop = BehavioralBackprop(tmp_path)
        loss_report = SystemLossReport(
            agreed_issues=[
                LossItem(
                    category="telos_drift",
                    severity=0.9,
                    affected_agents=["operator"],
                    description="Major telos drift detected",
                ),
            ],
            system_loss_score=0.9,
        )
        corrections = await backprop.apply(loss_report)
        assert len(corrections) == 1
        assert corrections[0].veto_required is True
        assert corrections[0].applied is False

        # Check pending veto file was written
        veto_file = tmp_path / "consolidation" / "pending_veto.jsonl"
        assert veto_file.exists()

    @pytest.mark.asyncio
    async def test_low_severity_auto_applies(self, tmp_path: Path):
        backprop = BehavioralBackprop(tmp_path)
        loss_report = SystemLossReport(
            agreed_issues=[
                LossItem(
                    category="fitness_gap",
                    severity=0.2,
                    affected_agents=["operator"],
                    description="Minor fitness gap",
                    proposed_correction="Adjust priority",
                ),
            ],
        )
        corrections = await backprop.apply(loss_report)
        assert len(corrections) == 1
        # Low severity prompt_update writes to shared notes
        assert corrections[0].applied is True

    @pytest.mark.asyncio
    async def test_empty_loss_report(self, tmp_path: Path):
        backprop = BehavioralBackprop(tmp_path)
        loss_report = SystemLossReport()
        corrections = await backprop.apply(loss_report)
        assert corrections == []

    def test_categorize_correction(self, tmp_path: Path):
        backprop = BehavioralBackprop(tmp_path)
        assert backprop._categorize_correction(
            LossItem(category="fitness_gap", severity=0.5, description="t")
        ) == "prompt_update"
        assert backprop._categorize_correction(
            LossItem(category="memory_debt", severity=0.5, description="t")
        ) == "memory_adjustment"
        assert backprop._categorize_correction(
            LossItem(category="telos_drift", severity=0.5, description="t")
        ) == "corpus_claim"


# ---------------------------------------------------------------------------
# DifferentiationCheck tests
# ---------------------------------------------------------------------------


class TestDifferentiationCheck:
    def test_no_proposal_on_first_cycle(self, tmp_path: Path):
        check = DifferentiationCheck(tmp_path)
        loss = SystemLossReport(
            agreed_issues=[
                LossItem(category="capability_gap", severity=0.6,
                         description="Missing sarcasm detection",
                         affected_agents=["operator"]),
            ],
        )
        proposal = check.check(loss, cycle_number=1)
        assert proposal is None  # Only 1 occurrence, needs 3

    def test_proposal_after_persistent_gap(self, tmp_path: Path):
        check = DifferentiationCheck(tmp_path, gap_threshold=3)

        # Simulate 3 cycles with the same gap
        gap_dir = tmp_path / "consolidation"
        gap_dir.mkdir(parents=True)
        gap_file = gap_dir / "capability_gaps.jsonl"
        for cycle in range(2):
            with open(gap_file, "a") as f:
                f.write(json.dumps({
                    "cycle": cycle + 1,
                    "description": "sarcasm detection",
                    "affected_agents": ["operator"],
                }) + "\n")

        # Third cycle triggers proposal
        loss = SystemLossReport(
            agreed_issues=[
                LossItem(category="capability_gap", severity=0.6,
                         description="sarcasm detection",
                         affected_agents=["operator"]),
            ],
        )
        proposal = check.check(loss, cycle_number=3)
        assert proposal is not None
        assert "sarcasm" in proposal.capability_gap

    def test_no_proposal_without_capability_gap(self, tmp_path: Path):
        check = DifferentiationCheck(tmp_path)
        loss = SystemLossReport(
            agreed_issues=[
                LossItem(category="fitness_gap", severity=0.5,
                         description="Low fitness", affected_agents=["op"]),
            ],
        )
        proposal = check.check(loss, cycle_number=5)
        assert proposal is None


# ---------------------------------------------------------------------------
# ConsolidationCycle integration tests
# ---------------------------------------------------------------------------


class TestConsolidationCycle:
    def test_cycle_number_persistence(self, tmp_path: Path):
        cycle = ConsolidationCycle(state_dir=tmp_path)
        assert cycle._cycle_number == 0

        cycle._cycle_number = 5
        cycle._save_cycle_number()

        cycle2 = ConsolidationCycle(state_dir=tmp_path)
        assert cycle2._cycle_number == 5

    def test_signal_emission_does_not_crash(self, tmp_path: Path):
        cycle = ConsolidationCycle(state_dir=tmp_path)
        outcome = ConsolidationOutcome(
            cycle_number=1, system_loss_score=0.3,
        )
        # Should not raise even without signal bus
        cycle._emit_signal(outcome)

    @pytest.mark.asyncio
    async def test_default_provider_prefers_ollama_then_nim_before_openrouter(
        self,
        tmp_path: Path,
        monkeypatch,
    ):
        calls: list[tuple[str, str]] = []

        class _FakeProvider:
            def __init__(self, label: str, *, fail: bool = False):
                self.label = label
                self.fail = fail

            async def complete(self, request):
                calls.append((self.label, request.model))
                if self.fail:
                    raise RuntimeError(f"{self.label} failed")
                return SimpleNamespace(content=f"{self.label} ok")

            async def close(self):
                return None

        def _fake_preferred_configs(**kwargs):
            return [
                RuntimeProviderConfig(
                    provider=ProviderType.OLLAMA,
                    available=True,
                    default_model="ollama-local",
                ),
                RuntimeProviderConfig(
                    provider=ProviderType.NVIDIA_NIM,
                    available=True,
                    default_model="nim-local",
                ),
                RuntimeProviderConfig(
                    provider=ProviderType.OPENROUTER,
                    available=True,
                    default_model="openrouter-fallback",
                ),
            ]

        def _fake_create_provider(config):
            return _FakeProvider(
                config.provider.value,
                fail=config.provider == ProviderType.OLLAMA,
            )

        monkeypatch.setattr(
            "dharma_swarm.consolidation.preferred_runtime_provider_configs",
            _fake_preferred_configs,
        )
        monkeypatch.setattr(
            "dharma_swarm.consolidation.create_runtime_provider",
            _fake_create_provider,
        )

        cycle = ConsolidationCycle(state_dir=tmp_path)
        provider = cycle._get_default_provider()
        response = await provider.complete(
            LLMRequest(
                model="meta-llama/llama-3.3-70b-instruct:free",
                system="sys",
                messages=[{"role": "user", "content": "hello"}],
            )
        )

        assert response.content == "nvidia_nim ok"
        assert calls == [
            ("ollama", "ollama-local"),
            ("nvidia_nim", "nim-local"),
        ]
