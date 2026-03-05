"""Tests for the Anekanta epistemological gate."""

from dharma_swarm.anekanta_gate import (
    AnekantaResult,
    evaluate_anekanta,
)
from dharma_swarm.models import GateResult


# --- PASS / WARN / FAIL thresholds ---


def test_all_three_frames_pass() -> None:
    text = (
        "The circuit activation reveals a mechanism. "
        "Subjective awareness and witness perception arise. "
        "Emergence and feedback drive self-organization in the ecosystem."
    )
    result = evaluate_anekanta(text)
    assert result.gate_result == GateResult.PASS
    assert result.frame_count == 3


def test_two_frames_warn() -> None:
    text = (
        "Gradient optimization improves the architecture. "
        "Emergence and complexity drive adaptation."
    )
    result = evaluate_anekanta(text)
    assert result.gate_result == GateResult.WARN
    assert result.frame_count == 2
    assert "Missing" in result.reason


def test_one_frame_fail() -> None:
    text = "The neuron activation propagates through the layer."
    result = evaluate_anekanta(text)
    assert result.gate_result == GateResult.FAIL
    assert result.frame_count == 1


def test_zero_frames_fail() -> None:
    text = "The quick brown fox jumps over the lazy dog."
    result = evaluate_anekanta(text)
    assert result.gate_result == GateResult.FAIL
    assert result.frame_count == 0
    assert result.frames_detected == []


# --- Single-frame isolation ---


def test_mechanistic_only() -> None:
    text = "The circuit and gradient define the architecture."
    result = evaluate_anekanta(text)
    assert result.gate_result == GateResult.FAIL
    assert result.frames_detected == ["mechanistic"]


def test_phenomenological_only() -> None:
    text = "Consciousness and introspection reveal qualia."
    result = evaluate_anekanta(text)
    assert result.gate_result == GateResult.FAIL
    assert result.frames_detected == ["phenomenological"]


def test_systems_only() -> None:
    text = "Emergence and resilience characterise the ecosystem."
    result = evaluate_anekanta(text)
    assert result.gate_result == GateResult.FAIL
    assert result.frames_detected == ["systems"]


# --- Detected list correctness ---


def test_frames_detected_list() -> None:
    text = (
        "The layer activation mechanism. "
        "Emergence and feedback loops."
    )
    result = evaluate_anekanta(text)
    assert set(result.frames_detected) == {"mechanistic", "systems"}
    assert "phenomenological" not in result.frames_detected


# --- Case insensitivity ---


def test_case_insensitive() -> None:
    text = "MECHANISM and ACTIVATION in the LAYER"
    result = evaluate_anekanta(text)
    assert "mechanistic" in result.frames_detected


# --- Description + content combination ---


def test_content_combined() -> None:
    desc = "The circuit activates in the layer."
    content = "Awareness and consciousness arise through introspection."
    result = evaluate_anekanta(desc, content)
    assert "mechanistic" in result.frames_detected
    assert "phenomenological" in result.frames_detected
    assert result.frame_count >= 2


# --- Count accuracy ---


def test_frame_count_accurate() -> None:
    text = (
        "Gradient weight optimization. "
        "Witness observer awareness. "
        "Emergence feedback resilience."
    )
    result = evaluate_anekanta(text)
    assert result.frame_count == len(result.frames_detected)
    assert result.frame_count == 3


# --- Edge case: empty input ---


def test_empty_input_fails() -> None:
    result = evaluate_anekanta("", "")
    assert result.gate_result == GateResult.FAIL
    assert result.frame_count == 0
    assert result.frames_detected == []
