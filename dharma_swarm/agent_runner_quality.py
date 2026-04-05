"""Semantic acceptance and honors-checkpoint helpers for AgentRunner."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from dharma_swarm.mission_contract import (
    DefensePacket,
    HonorsCheckpoint,
    JudgeGate,
    JudgePack,
    load_completion_contract,
)
from dharma_swarm.models import AgentConfig, LLMRequest, Task
from dharma_swarm.quality_gates import ContentQualityGate

_REASONING_LEAK_MARKERS = ("<think", "</think>", "<analysis", "</analysis>")
_EXPLORATION_PREAMBLE_MARKERS = (
    "i'll begin by",
    "i will begin by",
    "let me explore",
    "let me check",
    "first, i'll",
)
_FILE_REFERENCE_PATTERN = re.compile(
    r"(?<![\w/])(?:[A-Za-z0-9_.-]+/)+(?:[A-Za-z0-9_.-]+\.(?:py|md|json|yaml|yml|toml|txt|ts|tsx|js|jsx|sh))(?![\w/])"
)
_META_OBSERVATION_HINTS = (
    "system",
    "control plane",
    "orchestrator",
    "router",
    "feedback",
    "active inference",
    "mission contract",
    "evolution",
    "archive",
    "downstream",
    "upstream",
)
_ERROR_PREFIXES = (
    "error:",
    "provider error:",
    "timeout:",
    "failed:",
    "unable to",
    "task execution timed out",
)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _task_metadata(task: Task) -> dict[str, Any]:
    return task.metadata if isinstance(task.metadata, dict) else {}


def _metadata_number(metadata: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key not in metadata:
            continue
        try:
            return float(metadata[key])
        except (TypeError, ValueError):
            continue
    return None


def _looks_like_provider_failure(content: str | None) -> bool:
    normalized = (content or "").strip().lower()
    if not normalized:
        return True
    return any(normalized.startswith(prefix) for prefix in _ERROR_PREFIXES)


@dataclass(slots=True)
class CompletionAssessment:
    accepted: bool
    quality_score: float
    reason: str = ""


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _normalize_bullet_text(line: str) -> str:
    text = str(line or "").strip()
    text = re.sub(r"^[-*]\s+", "", text)
    text = re.sub(r"^\d+\.\s+", "", text)
    return text.strip()


def _extract_named_sections(content: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw_line in (content or "").splitlines():
        stripped = raw_line.strip()
        if re.match(r"^[A-Za-z][A-Za-z ]{1,40}:$", stripped):
            current = stripped[:-1].strip().lower()
            sections.setdefault(current, [])
            continue
        if current is not None and stripped:
            sections[current].append(stripped)
    return sections


def _section_items(sections: dict[str, list[str]], name: str) -> list[str]:
    return [
        item
        for item in (
            _normalize_bullet_text(line)
            for line in sections.get(name.lower(), [])
        )
        if item
    ]


def _extract_file_references(content: str) -> list[str]:
    files = [match.group(0) for match in _FILE_REFERENCE_PATTERN.finditer(content or "")]
    return _dedupe_keep_order(files)


def _extract_test_references(content: str) -> list[str]:
    refs = []
    for path in _extract_file_references(content):
        lowered = path.lower()
        if lowered.startswith("tests/") or "/tests/" in lowered or "/test_" in lowered or lowered.endswith("_test.py"):
            refs.append(path)
    return _dedupe_keep_order(refs)


def _match_required_references(
    required: list[str],
    observed: list[str],
    *,
    lowered_content: str,
) -> tuple[list[str], list[str]]:
    observed_lower = {item.lower() for item in observed if item}
    matched: list[str] = []
    missing: list[str] = []
    for item in required:
        text = str(item or "").strip()
        if not text:
            continue
        lowered_item = text.lower()
        if lowered_item in observed_lower or lowered_item in lowered_content:
            matched.append(text)
        else:
            missing.append(text)
    return _dedupe_keep_order(matched), _dedupe_keep_order(missing)


def _extract_meta_observations(
    content: str,
    *,
    system_effects: list[str],
) -> list[str]:
    observations = list(system_effects)
    for sentence in re.split(r"(?<=[.!?])\s+", content or ""):
        text = sentence.strip()
        lowered = text.lower()
        if text and any(marker in lowered for marker in _META_OBSERVATION_HINTS):
            observations.append(text)
    return _dedupe_keep_order(observations)


def _build_honors_defense_packet(task: Task, content: str) -> DefensePacket:
    contract = load_completion_contract(_task_metadata(task))
    lowered = (content or "").lower()
    sections = _extract_named_sections(content)
    files_listed = [
        path
        for path in _extract_file_references(content)
        if path not in _extract_test_references(content)
    ]
    tests_flagged = _extract_test_references(content)
    context_refs_used = []
    stakeholder_mentions = []
    matched_evidence_paths: list[str] = []
    matched_file_references: list[str] = []
    matched_test_references: list[str] = []
    missing_evidence_paths: list[str] = []
    missing_file_references: list[str] = []
    missing_test_references: list[str] = []
    missing_context_refs: list[str] = []
    missing_stakeholders: list[str] = []
    if contract is not None:
        context_refs_used = [
            ref
            for ref in contract.required_context_refs
            if ref.lower() in lowered
        ]
        stakeholder_mentions = [
            stake
            for stake in contract.stakeholders
            if stake.lower() in lowered
        ]
        missing_context_refs = [
            ref
            for ref in contract.required_context_refs
            if ref not in context_refs_used
        ]
        missing_stakeholders = [
            stake
            for stake in contract.stakeholders
            if stake not in stakeholder_mentions
        ]
    fix_proposals = _section_items(sections, "next actions")
    residual_risks = _section_items(sections, "residual risks")
    system_effects = _section_items(sections, "system effects")
    evidence_paths = _dedupe_keep_order(
        _section_items(sections, "evidence")
        + _extract_file_references("\n".join(sections.get("evidence", [])))
        + files_listed
        + tests_flagged
    )
    if contract is not None:
        matched_evidence_paths, missing_evidence_paths = _match_required_references(
            contract.required_evidence_paths,
            evidence_paths,
            lowered_content=lowered,
        )
        matched_file_references, missing_file_references = _match_required_references(
            contract.required_file_references,
            files_listed + evidence_paths,
            lowered_content=lowered,
        )
        matched_test_references, missing_test_references = _match_required_references(
            contract.required_test_references,
            tests_flagged + evidence_paths,
            lowered_content=lowered,
        )
    findings = _section_items(sections, "findings")
    meta_observations = _extract_meta_observations(
        content,
        system_effects=system_effects,
    )
    strong_claim_count = len(findings) + len(system_effects)
    if strong_claim_count == 0 and any(marker in lowered for marker in ("findings:", "evidence:", "system effects:")):
        strong_claim_count = 1
    support_signals = _dedupe_keep_order(
        evidence_paths
        + context_refs_used
        + matched_evidence_paths
        + matched_file_references
        + matched_test_references
    )
    supported_claim_count = min(
        strong_claim_count,
        len(support_signals),
    )
    unsupported_claim_ratio = (
        0.0
        if strong_claim_count <= 0
        else max(0.0, min(1.0, (strong_claim_count - supported_claim_count) / strong_claim_count))
    )
    return DefensePacket(
        files_listed=files_listed,
        tests_flagged=tests_flagged,
        evidence_paths=evidence_paths,
        context_refs_used=context_refs_used,
        stakeholder_mentions=stakeholder_mentions,
        matched_evidence_paths=matched_evidence_paths,
        matched_file_references=matched_file_references,
        matched_test_references=matched_test_references,
        missing_evidence_paths=missing_evidence_paths,
        missing_file_references=missing_file_references,
        missing_test_references=missing_test_references,
        missing_context_refs=missing_context_refs,
        missing_stakeholders=missing_stakeholders,
        fix_proposals=fix_proposals,
        residual_risks=residual_risks,
        system_effects=system_effects,
        meta_observations=meta_observations,
        strong_claim_count=strong_claim_count,
        supported_claim_count=supported_claim_count,
        unsupported_claim_ratio=unsupported_claim_ratio,
    )


def assess_honors_checkpoint(
    task: Task,
    content: str,
    *,
    semantic_quality_score: float,
) -> tuple[CompletionAssessment, HonorsCheckpoint | None]:
    contract = load_completion_contract(_task_metadata(task))
    if contract is None or contract.mode != "honors":
        return CompletionAssessment(accepted=True, quality_score=semantic_quality_score), None

    packet = _build_honors_defense_packet(task, content)
    lowered = (content or "").lower()

    def _gate(name: str, passed: bool, score: float, reason: str) -> JudgeGate:
        return JudgeGate(name=name, passed=passed, score=max(0.0, min(score, 1.0)), reason=reason)

    def _detail_bits(*groups: tuple[str, list[str] | int | float]) -> list[str]:
        details: list[str] = []
        for label, value in groups:
            if isinstance(value, list):
                if value:
                    details.append(f"{label}: {', '.join(str(item) for item in value[:5])}")
            elif isinstance(value, float):
                details.append(f"{label}: {value:.2f}")
            else:
                details.append(f"{label}: {value}")
        return details

    missing_sections = [
        section
        for section in contract.required_sections
        if f"{section.lower()}:" not in lowered
    ]
    matched_sections = len(contract.required_sections) - len(missing_sections)
    section_score = (
        1.0
        if not contract.required_sections
        else matched_sections / max(len(contract.required_sections), 1)
    )
    responsiveness_passed = not missing_sections
    responsiveness = _gate(
        "responsiveness",
        responsiveness_passed,
        section_score,
        (
            "covered required sections"
            if responsiveness_passed
            else "; ".join(_detail_bits(("missing required sections", missing_sections)))
        ),
    )

    file_score = (
        1.0
        if contract.minimum_file_references <= 0
        else min(len(packet.files_listed) / contract.minimum_file_references, 1.0)
    )
    test_score = (
        1.0
        if contract.minimum_test_references <= 0
        else min(len(packet.tests_flagged) / contract.minimum_test_references, 1.0)
    )
    fix_score = (
        1.0
        if contract.minimum_fix_proposals <= 0
        else min(len(packet.fix_proposals) / contract.minimum_fix_proposals, 1.0)
    )
    required_file_score = (
        1.0
        if not contract.required_file_references
        else min(
            len(packet.matched_file_references) / max(len(contract.required_file_references), 1),
            1.0,
        )
    )
    required_test_score = (
        1.0
        if not contract.required_test_references
        else min(
            len(packet.matched_test_references) / max(len(contract.required_test_references), 1),
            1.0,
        )
    )
    auditability_passed = (
        len(packet.files_listed) >= contract.minimum_file_references
        and len(packet.tests_flagged) >= contract.minimum_test_references
        and len(packet.fix_proposals) >= contract.minimum_fix_proposals
        and not packet.missing_file_references
        and not packet.missing_test_references
    )
    auditability_reason = "completion is auditable"
    if not auditability_passed:
        auditability_reason = "; ".join(
            _detail_bits(
                ("missing file refs", packet.missing_file_references),
                ("missing test refs", packet.missing_test_references),
                ("file refs", len(packet.files_listed)),
                ("test refs", len(packet.tests_flagged)),
                ("fix proposals", len(packet.fix_proposals)),
            )
        )
    auditability = _gate(
        "auditability",
        auditability_passed,
        (file_score + test_score + fix_score + required_file_score + required_test_score) / 5.0,
        auditability_reason,
    )

    context_score = (
        1.0
        if contract.minimum_context_references <= 0
        else min(len(packet.context_refs_used) / contract.minimum_context_references, 1.0)
    )
    evidence_score = (
        1.0
        if not contract.required_evidence_paths
        else min(len(packet.matched_evidence_paths) / max(len(contract.required_evidence_paths), 1), 1.0)
    )
    required_supported_claims = (
        0
        if packet.strong_claim_count <= 0
        else min(packet.strong_claim_count, max(1, contract.minimum_supported_claim_count))
    )
    supported_claim_score = (
        1.0
        if required_supported_claims <= 0
        else min(packet.supported_claim_count / required_supported_claims, 1.0)
    )
    unsupported_ratio_score = (
        1.0
        if packet.unsupported_claim_ratio <= contract.maximum_unsupported_claim_ratio
        else max(
            0.0,
            1.0
            - (
                (packet.unsupported_claim_ratio - contract.maximum_unsupported_claim_ratio)
                / max(1.0 - contract.maximum_unsupported_claim_ratio, 0.01)
            ),
        )
    )
    grounding_passed = (
        packet.supported_claim_count >= required_supported_claims
        and packet.unsupported_claim_ratio <= contract.maximum_unsupported_claim_ratio
        and len(packet.context_refs_used) >= contract.minimum_context_references
        and not packet.missing_context_refs
        and not packet.missing_evidence_paths
    )
    grounding_reason = "claims are grounded in evidence/context"
    if not grounding_passed:
        grounding_reason = "; ".join(
            _detail_bits(
                ("missing evidence paths", packet.missing_evidence_paths),
                ("missing context refs", packet.missing_context_refs),
                ("supported claims", packet.supported_claim_count),
                ("required supported claims", required_supported_claims),
                ("unsupported claim ratio", packet.unsupported_claim_ratio),
            )
        )
    grounding = _gate(
        "grounding",
        grounding_passed,
        (unsupported_ratio_score + context_score + evidence_score + supported_claim_score) / 4.0,
        grounding_reason,
    )

    meta_score = (
        1.0
        if contract.minimum_meta_observations <= 0
        else min(len(packet.meta_observations) / contract.minimum_meta_observations, 1.0)
    )
    system_effect_score = 1.0 if (not contract.require_system_effects or packet.system_effects) else 0.0
    stakeholder_score = (
        1.0
        if not contract.stakeholders
        else min(len(packet.stakeholder_mentions) / max(len(contract.stakeholders), 1), 1.0)
    )
    causal_passed = (
        len(packet.meta_observations) >= contract.minimum_meta_observations
        and (not contract.require_system_effects or len(packet.system_effects) > 0)
        and not packet.missing_stakeholders
    )
    causal_reason = "explains system-level effects"
    if not causal_passed:
        causal_reason = "; ".join(
            _detail_bits(
                ("missing stakeholders", packet.missing_stakeholders),
                ("meta observations", len(packet.meta_observations)),
                ("system effects", len(packet.system_effects)),
            )
        )
    causal_awareness = _gate(
        "causal_awareness",
        causal_passed,
        (meta_score + system_effect_score + stakeholder_score) / 3.0,
        causal_reason,
    )

    gates = [responsiveness, grounding, auditability, causal_awareness]
    gate_failures = [gate.name for gate in gates if not gate.passed]
    final_score = sum(gate.score for gate in gates) / len(gates)
    failure_details = [f"{gate.name}: {gate.reason}" for gate in gates if not gate.passed]
    judge_pack = JudgePack(
        accepted=not gate_failures,
        final_score=final_score,
        gate_failures=gate_failures,
        gates=gates,
        summary=(
            "All honors gates passed"
            if not gate_failures
            else "Failed honors gates: " + "; ".join(failure_details)
        ),
    )
    checkpoint = HonorsCheckpoint(
        contract=contract,
        defense_packet=packet,
        judge_pack=judge_pack,
    )
    quality_score = max(0.0, min((semantic_quality_score + final_score) / 2.0, 1.0))
    if judge_pack.accepted:
        return CompletionAssessment(accepted=True, quality_score=quality_score), checkpoint
    return (
        CompletionAssessment(
            accepted=False,
            quality_score=quality_score,
            reason=judge_pack.summary.replace("Failed honors gates", "Honors checkpoint failed"),
        ),
        checkpoint,
    )


def _semantic_quality_threshold(
    task: Task,
    config: AgentConfig,
    *,
    requires_tooling: bool,
    requires_local_side_effects: bool,
) -> float:
    metadata = _task_metadata(task)
    explicit = _metadata_number(
        metadata,
        "semantic_quality_threshold",
        "completion_quality_threshold",
    )
    if explicit is None:
        explicit = _metadata_number(
            config.metadata,
            "semantic_quality_threshold",
            "completion_quality_threshold",
        )
    if explicit is not None:
        return max(30.0, min(90.0, explicit))

    task_type = str(metadata.get("task_type", "") or "").strip().lower()
    threshold = 45.0
    if task_type in {"analysis", "architectural", "planning", "research"}:
        threshold += 10.0
    if requires_tooling or requires_local_side_effects:
        threshold -= 10.0
    return max(35.0, min(80.0, threshold))


def semantic_repair_attempts(task: Task, config: AgentConfig) -> int:
    metadata = _task_metadata(task)
    task_type = str(metadata.get("task_type", "") or "").strip().lower()
    default_attempts = 2 if task_type in {"analysis", "architectural", "planning", "research"} else 1
    raw = (
        metadata.get("semantic_repair_attempts")
        or config.metadata.get("semantic_repair_attempts")
        or default_attempts
    )
    try:
        return max(0, min(3, int(raw)))
    except (TypeError, ValueError):
        return 1


def semantic_attempt_timeout_seconds(
    task: Task,
    config: AgentConfig,
    *,
    attempts_remaining: int,
) -> float | None:
    metadata = _task_metadata(task)
    explicit = _metadata_number(
        metadata,
        "semantic_attempt_timeout_seconds",
        "completion_attempt_timeout_seconds",
    )
    if explicit is None:
        explicit = _metadata_number(
            config.metadata,
            "semantic_attempt_timeout_seconds",
            "completion_attempt_timeout_seconds",
        )
    if explicit is not None:
        return max(0.01, explicit)

    if attempts_remaining <= 0:
        return None

    total_timeout = _metadata_number(
        metadata,
        "timeout_seconds",
        "run_timeout_seconds",
        "task_timeout_seconds",
    )
    if total_timeout is None or total_timeout <= 0:
        return None

    reserve_floor = max(30.0 * attempts_remaining, total_timeout * 0.25)
    reserve = min(total_timeout * 0.75, reserve_floor)
    attempt_timeout = total_timeout - reserve
    if attempt_timeout <= 0:
        return None
    return max(5.0, attempt_timeout)


async def assess_completion_semantics(
    task: Task,
    config: AgentConfig,
    content: str,
    *,
    requires_tooling: bool,
    requires_local_side_effects: bool,
) -> CompletionAssessment:
    normalized = (content or "").strip()
    if _looks_like_provider_failure(normalized):
        return CompletionAssessment(
            accepted=False,
            quality_score=0.0,
            reason="Semantic acceptance failed: provider returned an invalid completion",
        )

    gate = ContentQualityGate(
        threshold=_semantic_quality_threshold(
            task,
            config,
            requires_tooling=requires_tooling,
            requires_local_side_effects=requires_local_side_effects,
        ),
        use_llm=False,
        cache_enabled=False,
    )
    gate_result = await gate.evaluate(
        normalized,
        {"description": task.description or task.title},
    )
    quality_score = _clamp01(gate_result.score.overall / 100.0)
    threshold_score = _clamp01(gate_result.threshold / 100.0)

    lowered = normalized.lower()
    if len(normalized.split()) >= 60:
        quality_score = _clamp01(quality_score + 0.05)
    if any(marker in lowered for marker in ("evidence:", "finding:", "findings:", "observed", "confirmed")):
        quality_score = _clamp01(quality_score + 0.07)
    if any(marker in lowered for marker in ("next actions:", "next steps:", "action items:", "\n- ", "\n1.")):
        quality_score = _clamp01(quality_score + 0.05)

    # Strip reasoning tags instead of rejecting.
    # Many models (GLM-5, DeepSeek, Qwen) include <think>...</think> blocks
    # as part of their chain-of-thought. The content after stripping is
    # usually valid. Penalize quality slightly but don't reject.
    if any(marker in lowered for marker in _REASONING_LEAK_MARKERS):
        import re
        normalized = re.sub(
            r"<(?:think|analysis)>.*?</(?:think|analysis)>",
            "", normalized, flags=re.DOTALL | re.IGNORECASE,
        ).strip()
        lowered = normalized.lower()
        quality_score = _clamp01(quality_score * 0.85)  # 15% penalty, not rejection
        if not normalized:
            # Nothing left after stripping — THEN reject
            return CompletionAssessment(
                accepted=False,
                quality_score=0.0,
                reason="Semantic acceptance failed: response was entirely reasoning tags with no content",
            )

    if (
        normalized
        and any(lowered.startswith(marker) for marker in _EXPLORATION_PREAMBLE_MARKERS)
        and any(
            marker in lowered
            for marker in (
                "```bash",
                "```sh",
                "before i finalize the answer",
                "before producing the brief",
                "let me explore",
            )
        )
    ):
        return CompletionAssessment(
            accepted=False,
            quality_score=min(quality_score, 0.25),
            reason=(
                "Semantic acceptance failed: response stayed in exploration mode "
                "instead of delivering the final answer"
            ),
        )

    if gate_result.passed or quality_score >= threshold_score:
        return CompletionAssessment(
            accepted=True,
            quality_score=quality_score,
        )

    detail = gate_result.reason or gate_result.score.feedback
    if not detail:
        detail = (
            f"overall score {gate_result.score.overall:.1f} below threshold "
            f"{gate_result.threshold:.1f}"
        )
    return CompletionAssessment(
        accepted=False,
        quality_score=quality_score,
        reason=f"Semantic acceptance failed: {detail}",
    )


def build_semantic_repair_request(
    request: LLMRequest,
    *,
    failed_result: str,
    assessment: CompletionAssessment,
    attempt_index: int,
) -> LLMRequest:
    critique = "\n".join(
        [
            "Your previous response failed the completion acceptance gate.",
            f"Failure reason: {assessment.reason}",
            f"Repair attempt: {attempt_index}",
            "Rewrite the answer for the exact same task.",
            "Requirements:",
            "- No reasoning tags or scratchpad markup.",
            "- Answer the task directly rather than describing the failure.",
            "- Be concrete, context-aware, and action-oriented.",
            "- If the task is analytical, include findings and next actions.",
            "- Do not output shell commands, grep commands, or pseudo-tool plans.",
            "- Do not say you will investigate first; deliver the best bounded final brief now.",
            "- Start directly with the final answer.",
            "",
            "Previous response:",
            failed_result[:6000],
        ]
    )
    updated_messages = list(request.messages)
    updated_messages.append({"role": "assistant", "content": failed_result[:12000]})
    updated_messages.append({"role": "user", "content": critique})
    return request.model_copy(update={"messages": updated_messages})


__all__ = [
    "CompletionAssessment",
    "assess_completion_semantics",
    "assess_honors_checkpoint",
    "build_semantic_repair_request",
    "semantic_attempt_timeout_seconds",
    "semantic_repair_attempts",
]
