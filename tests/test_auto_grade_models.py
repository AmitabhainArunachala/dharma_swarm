from __future__ import annotations

import importlib

import pytest


def _load_module(name: str):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised in red phase
        pytest.fail(f"expected module {name!r} to exist: {exc}")


def test_grade_card_contract_exposes_phase_two_defaults() -> None:
    models = _load_module("dharma_swarm.auto_grade.models")

    card = models.GradeCard(task_id="task-1", report_id="report-1", groundedness=0.9, citation_precision=0.9, citation_coverage=0.9, source_quality=0.8, source_diversity=0.7, topical_coverage=0.8, contradiction_handling=1.0, freshness=0.9, structure=0.8, actionability=0.7, novelty=0.6, traceability=0.9)

    assert card.latency_ms == 0
    assert card.token_cost_usd == 0.0
    assert card.gate_failures == []
    assert card.final_score == 0.0
    assert card.promotion_state == "candidate"
    assert card.metadata == {}


def test_reward_signal_defaults_to_attribution_ready() -> None:
    models = _load_module("dharma_swarm.auto_grade.models")

    card = models.GradeCard(task_id="task-1", report_id="report-1", groundedness=0.9, citation_precision=0.9, citation_coverage=0.9, source_quality=0.8, source_diversity=0.7, topical_coverage=0.8, contradiction_handling=1.0, freshness=0.9, structure=0.8, actionability=0.7, novelty=0.6, traceability=0.9)
    reward = models.RewardSignal(task_id="task-1", report_id="report-1", grade_card=card, scalar_reward=0.3, gate_multiplier=1.0)

    assert reward.penalties == {}
    assert reward.attribution_ready is True
