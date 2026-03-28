"""Provider/model matrix harness for live multi-lane evaluation."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Mapping
from uuid import uuid4

from dharma_swarm.model_hierarchy import (
    DEFAULT_MODELS,
    DELIBERATIVE_EXECUTION_PRIORITY,
    DELIBERATIVE_REASONING_PRIORITY,
    ESCALATION_PRIORITY,
    LaneRole,
    get_tier,
    provider_lane_role,
)
from dharma_swarm.models import LLMRequest, ProviderType
from dharma_swarm.runtime_provider import (
    create_runtime_provider,
    resolve_runtime_provider_config,
)
from dharma_swarm.provider_smoke import run_provider_smoke


SHARED_DIR = Path.home() / ".dharma" / "shared"
DEFAULT_CORPUS = "deployment"
DEFAULT_PROFILE = "live25"
PROFILE_CHOICES = ("quick", "live25")
WORKSPACE_CORPUS = "workspace"
CORPUS_CHOICES = (DEFAULT_CORPUS, WORKSPACE_CORPUS)
_TIER_COST_UNITS = {"free": 1, "cheap": 2, "paid": 5}
_TIMEOUT_PREFIXES = ("timeout:", "timed out")
_PROVIDER_ERROR_MARKERS = (
    "error:",
    "error (rc=",
    "api error:",
    "not logged in",
    "you may not have access to it",
    "selected model",
    "rate limit",
    "hit your limit",
)
_SUBPROCESS_TIMEOUT_FLOORS = {
    ProviderType.CODEX: 180.0,
    ProviderType.CLAUDE_CODE: 90.0,
}
_SMOKE_PROVIDER_KEYS = {
    ProviderType.OLLAMA: "ollama",
    ProviderType.NVIDIA_NIM: "nvidia_nim",
    ProviderType.OPENROUTER: "openrouter",
}
_MATRIX_REPAIR_MAX_CHARS = 8_000
_MODEL_FAMILY_SUFFIX_RE = re.compile(r"[-_:]20\d{6,8}$")


@dataclass(frozen=True, slots=True)
class MatrixPromptSpec:
    prompt_id: str
    title: str
    prompt: str
    required_keys: tuple[str, ...]
    max_tokens: int = 256


@dataclass(frozen=True, slots=True)
class MatrixTargetSpec:
    target_id: str
    provider: ProviderType
    model: str
    lane_role: LaneRole
    tier: str
    available: bool
    availability_reason: str
    config_source: str


@dataclass(frozen=True, slots=True)
class MatrixExecutionResult:
    target_id: str
    prompt_id: str
    status: str
    response_text: str
    elapsed_sec: float
    schema_valid: bool
    required_keys: list[str]
    resolved_model: str | None = None
    usage: dict[str, Any] | None = None
    error: str | None = None
    direct_status: str | None = None
    direct_schema_valid: bool | None = None
    repair_attempted: bool = False
    repair_strategy: str | None = None


def _env_value(env: Mapping[str, str] | None, key: str, default: str) -> str:
    if env is None:
        return os.environ.get(key, "").strip() or default
    return str(env.get(key, "")).strip() or default


def _default_artifact_dir(artifact_dir: str | Path | None) -> Path:
    if artifact_dir not in (None, ""):
        return Path(artifact_dir).expanduser()
    return SHARED_DIR


def _classify_error(exc: Exception | str) -> str:
    if isinstance(exc, TimeoutError):
        return "timeout"
    text = str(exc).strip().lower()
    if "timed out" in text or "timeout" in text:
        return "timeout"
    if "not set" in text:
        return "missing_config"
    if "unauthorized" in text or "401" in text:
        return "auth_failed"
    if "404" in text or "no endpoints found" in text:
        return "unknown_model"
    if "connection refused" in text or "all connection attempts failed" in text:
        return "unreachable"
    return "error"


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return stripped


def _iter_json_objects(text: str) -> list[str]:
    candidates: list[str] = []
    depth = 0
    start: int | None = None
    in_string = False
    escape = False
    for idx, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            if depth == 0:
                start = idx
            depth += 1
            continue
        if ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                candidates.append(text[start:idx + 1])
                start = None
    return candidates


def _parse_json_object(response_text: str) -> dict[str, Any] | None:
    candidates = [_strip_code_fences(response_text)]
    candidates.extend(_iter_json_objects(response_text))
    seen: set[str] = set()
    for candidate in candidates:
        normalized = candidate.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        try:
            parsed = json.loads(normalized)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _validate_schema(response_text: str, required_keys: tuple[str, ...]) -> tuple[bool, list[str]]:
    if not required_keys:
        return True, []
    parsed = _parse_json_object(response_text)
    if parsed is None:
        return False, list(required_keys)
    missing = [key for key in required_keys if key not in parsed]
    return not missing, missing


def classify_matrix_response(
    response_text: str,
    required_keys: tuple[str, ...],
) -> tuple[str, bool, list[str]]:
    text = response_text.strip()
    lowered = text.lower()
    if not lowered:
        return "empty_response", False, list(required_keys)
    if any(marker in lowered for marker in _TIMEOUT_PREFIXES):
        return "provider_timeout", False, list(required_keys)
    if any(marker in lowered for marker in _PROVIDER_ERROR_MARKERS):
        return "provider_error", False, list(required_keys)

    schema_valid, missing_keys = _validate_schema(text, required_keys)
    if schema_valid:
        return "ok", True, []
    return "schema_invalid", False, missing_keys


def _execution_score(result: MatrixExecutionResult, *, timeout_seconds: float) -> float:
    if result.status not in {"ok", "schema_invalid"}:
        return 0.0
    ok_score = 60.0 if result.status == "ok" else 10.0
    schema_score = 30.0 if result.schema_valid else 0.0
    repair_penalty = 5.0 if result.repair_attempted and result.status == "ok" else 0.0
    normalized_timeout = max(timeout_seconds, 0.1)
    speed_ratio = min(result.elapsed_sec / normalized_timeout, 1.0)
    speed_ceiling = 10.0 if result.status == "ok" else 5.0
    speed_score = max(0.0, speed_ceiling * (1.0 - speed_ratio))
    return round(max(0.0, ok_score + schema_score + speed_score - repair_penalty), 2)


def _target_dict(target: MatrixTargetSpec) -> dict[str, Any]:
    return {
        "target_id": target.target_id,
        "provider": target.provider.value,
        "model": target.model,
        "lane_role": target.lane_role.value,
        "tier": target.tier,
        "available": target.available,
        "availability_reason": target.availability_reason,
        "config_source": target.config_source,
    }


def _workspace_context(working_dir: str | None) -> str:
    if not working_dir:
        return "Workspace context unavailable."
    root = Path(working_dir)
    file_variants = (
        (
            "provider_matrix.py",
            ("dharma_swarm/provider_matrix.py", "provider_matrix.py"),
            ("_quick_blueprints", "_execute_target_prompt", "_repair_schema_invalid_response"),
        ),
        (
            "provider_smoke.py",
            ("dharma_swarm/provider_smoke.py", "provider_smoke.py"),
            ("_probe_ollama", "_probe_nim", "_probe_openrouter", "_probe_qwen_dashboard"),
        ),
        (
            "runtime_provider.py",
            ("dharma_swarm/runtime_provider.py", "runtime_provider.py"),
            (
                "PREFERRED_LOW_COST_WITH_ANTHROPIC_RUNTIME_PROVIDERS",
                "resolve_runtime_provider_config",
                "create_runtime_provider",
            ),
        ),
    )
    sections: list[str] = []
    for label, variants, markers in file_variants:
        for relpath in variants:
            path = root / relpath
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            snippet = _curated_workspace_snippet(text, markers)
            if not snippet:
                snippet = _line_safe_clip(text, limit=2_000)
            text = snippet
            sections.append(f"FILE: {label}\n{text}")
            break
    return "\n\n".join(sections) if sections else "Workspace context unavailable."


def _line_safe_clip(text: str, *, limit: int) -> str:
    clipped = text[:limit]
    if len(text) <= limit or "\n" not in clipped:
        return clipped
    return clipped.rsplit("\n", 1)[0]


def _curated_workspace_snippet(
    text: str,
    markers: tuple[str, ...],
    *,
    before_lines: int = 3,
    after_lines: int = 20,
    max_chars: int = 4_000,
) -> str:
    lines = text.splitlines()
    if not lines:
        return ""

    ranges: list[tuple[int, int]] = []
    for marker in markers:
        for idx, line in enumerate(lines):
            if marker in line:
                start = max(0, idx - before_lines)
                end = min(len(lines), idx + after_lines)
                if ranges and start <= ranges[-1][1]:
                    prev_start, prev_end = ranges[-1]
                    ranges[-1] = (prev_start, max(prev_end, end))
                else:
                    ranges.append((start, end))
                break

    if not ranges:
        return ""

    blocks: list[str] = []
    for start, end in ranges:
        block = "\n".join(lines[start:end]).strip()
        if block:
            blocks.append(block)
    snippet = "\n\n...\n\n".join(blocks)
    return _line_safe_clip(snippet, limit=max_chars)


def build_default_prompt_corpus(
    corpus: str = DEFAULT_CORPUS,
    *,
    working_dir: str | None = None,
) -> list[MatrixPromptSpec]:
    if corpus != DEFAULT_CORPUS:
        if corpus != WORKSPACE_CORPUS:
            raise ValueError(f"Unsupported provider-matrix corpus: {corpus}")
        workspace_context = _workspace_context(working_dir)
        return [
            MatrixPromptSpec(
                prompt_id="workspace_reliability_fix",
                title="Find the highest-ROI workspace reliability fix",
                prompt=(
                    "Return JSON only. You are reviewing live Dharma Swarm runtime code. "
                    "Based on the workspace context below, pick the single highest-ROI reliability fix.\n\n"
                    f"{workspace_context}\n\n"
                    "Output keys: owning_file, risk, fix, confidence."
                ),
                required_keys=("owning_file", "risk", "fix", "confidence"),
            ),
            MatrixPromptSpec(
                prompt_id="workspace_pilot_shape",
                title="Choose the best real-project pilot shape",
                prompt=(
                    "Return JSON only. Based on the workspace context below, choose the best near-term "
                    "real-project pilot for Dharma Swarm.\n\n"
                    f"{workspace_context}\n\n"
                    "Output keys: pilot_shape, first_artifact, guardrail, rationale."
                ),
                required_keys=("pilot_shape", "first_artifact", "guardrail", "rationale"),
            ),
        ]

    return [
        MatrixPromptSpec(
            prompt_id="deployment_case_ranker",
            title="Rank highest-value deployment wedge",
            prompt=(
                "Return JSON only. Choose the single best near-term Dharma Swarm deployment case "
                "from this list: tariff_intelligence, policy_change_monitoring, diligence_copilot, trading_lab. "
                "Prefer the option that best fits a multi-model swarm with strong research, grading, and human review. "
                "Output keys: deployment_case, recommendation, confidence, why_now."
            ),
            required_keys=("deployment_case", "recommendation", "confidence", "why_now"),
        ),
        MatrixPromptSpec(
            prompt_id="swarm_handoff_plan",
            title="Map sovereign and delegated lanes",
            prompt=(
                "Return JSON only. Propose the best handoff for a large Dharma Swarm run where Codex and Opus remain sovereign. "
                "Output keys: primary_driver, delegated_lane, next_artifact, handoff_risk."
            ),
            required_keys=("primary_driver", "delegated_lane", "next_artifact", "handoff_risk"),
        ),
        MatrixPromptSpec(
            prompt_id="pilot_guardrail",
            title="Choose the correct launch guardrail",
            prompt=(
                "Return JSON only. Decide the safest current launch posture for a real pilot. "
                "Output keys: decision, first_customer_shape, guardrail, rationale."
            ),
            required_keys=("decision", "first_customer_shape", "guardrail", "rationale"),
        ),
    ]


def _minimum_timeout_seconds(target: MatrixTargetSpec) -> float:
    return _SUBPROCESS_TIMEOUT_FLOORS.get(target.provider, 0.0)


def _matrix_system_prompt(required_keys: tuple[str, ...]) -> str:
    required = ", ".join(required_keys) if required_keys else "none"
    return (
        "You are inside the Dharma Swarm provider matrix. "
        "Return exactly one strict JSON object and nothing else. "
        "Do not include markdown, analysis, or code fences. "
        f"Required keys: {required}."
    )


def _normalize_model_family(model: str) -> str:
    normalized = model.strip().lower()
    normalized = normalized.replace(":cloud", "").replace(":free", "")
    normalized = _MODEL_FAMILY_SUFFIX_RE.sub("", normalized)
    return normalized


def _choose_verified_model(requested_model: str, verified_models: list[str]) -> str:
    if not verified_models:
        return requested_model
    if requested_model in verified_models:
        return requested_model
    requested_family = _normalize_model_family(requested_model)
    family_matches = [
        model
        for model in verified_models
        if _normalize_model_family(model).startswith(requested_family)
        or requested_family in _normalize_model_family(model)
    ]
    if family_matches:
        return family_matches[0]
    return verified_models[0]


def _apply_probe_hints(
    targets: list[MatrixTargetSpec],
    probe_snapshot: Mapping[str, Any] | None,
) -> list[MatrixTargetSpec]:
    if not probe_snapshot:
        return targets

    updated: list[MatrixTargetSpec] = []
    for target in targets:
        probe_key = _SMOKE_PROVIDER_KEYS.get(target.provider)
        probe_doc = probe_snapshot.get(probe_key) if probe_key else None
        if not isinstance(probe_doc, Mapping):
            updated.append(target)
            continue
        verified_models = [
            str(item.get("model", "")).strip()
            for item in probe_doc.get("verified_models", [])
            if str(item.get("status", "")).strip().lower() == "ok"
            and str(item.get("model", "")).strip()
        ]
        if verified_models:
            resolved_model = _choose_verified_model(target.model, verified_models)
            availability_reason = "smoke_verified" if resolved_model != target.model else target.availability_reason
            config_source = (
                f"{target.config_source}+smoke_verified"
                if resolved_model != target.model
                else target.config_source
            )
            updated.append(
                MatrixTargetSpec(
                    target_id=f"{target.provider.value}:{resolved_model}",
                    provider=target.provider,
                    model=resolved_model,
                    lane_role=target.lane_role,
                    tier=target.tier,
                    available=target.available,
                    availability_reason=availability_reason,
                    config_source=config_source,
                )
            )
            continue
        probe_status = str(probe_doc.get("status", "")).strip().lower()
        if probe_status and probe_status not in {"ok", "missing_config"}:
            updated.append(
                MatrixTargetSpec(
                    target_id=target.target_id,
                    provider=target.provider,
                    model=target.model,
                    lane_role=target.lane_role,
                    tier=target.tier,
                    available=False,
                    availability_reason=f"smoke_{probe_status}",
                    config_source=target.config_source,
                )
            )
            continue
        updated.append(target)
    return updated


async def _repair_schema_invalid_response(
    provider: Any,
    target: MatrixTargetSpec,
    prompt: MatrixPromptSpec,
    response_text: str,
    timeout_seconds: float,
    *,
    repair_target: MatrixTargetSpec | None = None,
    working_dir: str | None = None,
    env: Mapping[str, str] | None = None,
) -> tuple[str, str] | None:
    if not response_text.strip():
        return None
    repair_prompt = (
        "Normalize the draft answer into strict JSON only.\n"
        f"Required keys: {', '.join(prompt.required_keys)}.\n"
        "Do not add markdown, analysis, or code fences.\n"
        "Use concise string values.\n\n"
        "Original task:\n"
        f"{prompt.prompt}\n\n"
        "Draft answer:\n"
        f"{response_text[:_MATRIX_REPAIR_MAX_CHARS]}"
    )
    def _repair_request(model: str) -> LLMRequest:
        return LLMRequest(
            model=model,
            system=_matrix_system_prompt(prompt.required_keys),
            messages=[{"role": "user", "content": repair_prompt}],
            max_tokens=min(prompt.max_tokens, 256),
            temperature=0.0,
        )

    repair_request = _repair_request(target.model)
    repair_timeout = min(max(timeout_seconds, 15.0), 30.0)
    repair_response = await asyncio.wait_for(
        provider.complete(repair_request),
        timeout=repair_timeout,
    )
    repaired_text = str(repair_response.content or "")
    repaired_status, repaired_schema_valid, _ = classify_matrix_response(
        repaired_text,
        prompt.required_keys,
    )
    if repaired_status == "ok" and repaired_schema_valid:
        return repaired_text, "same_provider_reask"
    if repair_target is None or repair_target.target_id == target.target_id:
        return None

    repair_config = resolve_runtime_provider_config(
        repair_target.provider,
        model=repair_target.model,
        working_dir=working_dir,
        timeout_seconds=int(max(repair_timeout, 1.0)),
        env=env,
    )
    repair_provider = create_runtime_provider(repair_config)
    try:
        cross_lane_response = await asyncio.wait_for(
            repair_provider.complete(_repair_request(repair_target.model)),
            timeout=repair_timeout,
        )
    finally:
        close = getattr(repair_provider, "close", None)
        if callable(close):
            await close()
    cross_lane_text = str(cross_lane_response.content or "")
    cross_lane_status, cross_lane_schema_valid, _ = classify_matrix_response(
        cross_lane_text,
        prompt.required_keys,
    )
    if cross_lane_status == "ok" and cross_lane_schema_valid:
        return (
            cross_lane_text,
            f"cross_lane_repair:{repair_target.provider.value}:{repair_target.model}",
        )
    return None


def _choose_matrix_repair_target(targets: list[MatrixTargetSpec]) -> MatrixTargetSpec | None:
    preferred_tokens = ("qwen", "nemotron", "deepseek", "gpt-5-codex")
    for token in preferred_tokens:
        for target in targets:
            if not target.available or target.lane_role == LaneRole.PRIMARY_DRIVER:
                continue
            if token in target.model.lower():
                return target
    for role in (LaneRole.VALIDATOR, LaneRole.BULK_BUILDER, LaneRole.RESEARCH_DELEGATE):
        for target in targets:
            if target.available and target.lane_role == role:
                return target
    return None


def _should_load_probe_snapshot(env: Mapping[str, str] | None) -> bool:
    return env is None or bool(env)


def _live25_blueprints(env: Mapping[str, str] | None) -> list[tuple[ProviderType, str, LaneRole]]:
    kimi_model = _env_value(env, "DGC_DIRECTOR_KIMI_MODEL", "moonshotai/kimi-k2.5")
    glm_model = _env_value(env, "DGC_DIRECTOR_GLM_MODEL", "z-ai/glm-5")
    minimax_model = _env_value(env, "DGC_DIRECTOR_MINIMAX_MODEL", "minimaxai/minimax-m2.5")
    qwen_builder_model = _env_value(env, "DGC_DIRECTOR_QWEN_MODEL", "qwen/qwen3-coder")
    codex_model = (
        resolve_runtime_provider_config(ProviderType.CODEX, env=env).default_model
        or "gpt-5.4"
    )
    claude_cli_model = (
        resolve_runtime_provider_config(ProviderType.CLAUDE_CODE, env=env).default_model
        or DEFAULT_MODELS[ProviderType.ANTHROPIC]
    )
    anthropic_model = (
        resolve_runtime_provider_config(ProviderType.ANTHROPIC, env=env).default_model
        or DEFAULT_MODELS[ProviderType.ANTHROPIC]
    )

    return [
        (ProviderType.CODEX, codex_model, LaneRole.PRIMARY_DRIVER),
        (ProviderType.CLAUDE_CODE, claude_cli_model, LaneRole.PRIMARY_DRIVER),
        (ProviderType.ANTHROPIC, anthropic_model, LaneRole.PRIMARY_DRIVER),
        (ProviderType.OLLAMA, "glm-5:cloud", LaneRole.RESEARCH_DELEGATE),
        (ProviderType.OLLAMA, "deepseek-v3.2:cloud", LaneRole.BULK_BUILDER),
        (ProviderType.OLLAMA, "kimi-k2.5:cloud", LaneRole.RESEARCH_DELEGATE),
        (ProviderType.OLLAMA, "qwen3-coder:480b-cloud", LaneRole.BULK_BUILDER),
        (ProviderType.OLLAMA, "minimax-m2.7:cloud", LaneRole.CHALLENGER),
        (ProviderType.NVIDIA_NIM, DEFAULT_MODELS[ProviderType.NVIDIA_NIM], LaneRole.VALIDATOR),
        (ProviderType.NVIDIA_NIM, kimi_model, LaneRole.RESEARCH_DELEGATE),
        (ProviderType.NVIDIA_NIM, glm_model, LaneRole.RESEARCH_DELEGATE),
        (ProviderType.NVIDIA_NIM, minimax_model, LaneRole.CHALLENGER),
        (ProviderType.OPENROUTER, kimi_model, LaneRole.RESEARCH_DELEGATE),
        (ProviderType.OPENROUTER, glm_model, LaneRole.RESEARCH_DELEGATE),
        (ProviderType.OPENROUTER, qwen_builder_model, LaneRole.BULK_BUILDER),
        (ProviderType.OPENROUTER, "openai/gpt-5-codex", LaneRole.BULK_BUILDER),
        (ProviderType.OPENROUTER, "deepseek/deepseek-r1", LaneRole.CHALLENGER),
        (ProviderType.OPENROUTER_FREE, DEFAULT_MODELS[ProviderType.OPENROUTER_FREE], LaneRole.GENERAL_SUPPORT),
        (ProviderType.GROQ, DEFAULT_MODELS[ProviderType.GROQ], LaneRole.VALIDATOR),
        (ProviderType.CEREBRAS, DEFAULT_MODELS[ProviderType.CEREBRAS], LaneRole.BULK_BUILDER),
        (ProviderType.SILICONFLOW, DEFAULT_MODELS[ProviderType.SILICONFLOW], LaneRole.BULK_BUILDER),
        (ProviderType.TOGETHER, DEFAULT_MODELS[ProviderType.TOGETHER], LaneRole.BULK_BUILDER),
        (ProviderType.FIREWORKS, DEFAULT_MODELS[ProviderType.FIREWORKS], LaneRole.BULK_BUILDER),
        (ProviderType.GOOGLE_AI, DEFAULT_MODELS[ProviderType.GOOGLE_AI], LaneRole.GENERAL_SUPPORT),
        (ProviderType.MISTRAL, DEFAULT_MODELS[ProviderType.MISTRAL], LaneRole.GENERAL_SUPPORT),
        (ProviderType.OPENAI, DEFAULT_MODELS[ProviderType.OPENAI], LaneRole.GENERAL_SUPPORT),
    ]


def _quick_blueprints(env: Mapping[str, str] | None) -> list[tuple[ProviderType, str, LaneRole]]:
    codex_model = (
        resolve_runtime_provider_config(ProviderType.CODEX, env=env).default_model
        or "gpt-5.4"
    )
    claude_cli_model = (
        resolve_runtime_provider_config(ProviderType.CLAUDE_CODE, env=env).default_model
        or DEFAULT_MODELS[ProviderType.ANTHROPIC]
    )
    return [
        (ProviderType.CODEX, codex_model, LaneRole.PRIMARY_DRIVER),
        (ProviderType.CLAUDE_CODE, claude_cli_model, LaneRole.PRIMARY_DRIVER),
        (ProviderType.OLLAMA, "glm-5:cloud", LaneRole.RESEARCH_DELEGATE),
        (ProviderType.OLLAMA, "qwen3-coder:480b-cloud", LaneRole.BULK_BUILDER),
        (ProviderType.OLLAMA, "kimi-k2.5:cloud", LaneRole.RESEARCH_DELEGATE),
        (ProviderType.OLLAMA, "minimax-m2.7:cloud", LaneRole.CHALLENGER),
        (ProviderType.NVIDIA_NIM, DEFAULT_MODELS[ProviderType.NVIDIA_NIM], LaneRole.VALIDATOR),
        (ProviderType.OPENROUTER_FREE, DEFAULT_MODELS[ProviderType.OPENROUTER_FREE], LaneRole.GENERAL_SUPPORT),
        (ProviderType.GROQ, DEFAULT_MODELS[ProviderType.GROQ], LaneRole.VALIDATOR),
        (ProviderType.CEREBRAS, DEFAULT_MODELS[ProviderType.CEREBRAS], LaneRole.BULK_BUILDER),
    ]


def build_default_matrix_targets(
    *,
    profile: str = DEFAULT_PROFILE,
    include_unavailable: bool = True,
    env: Mapping[str, str] | None = None,
    working_dir: str | None = None,
    timeout_seconds: float | None = None,
) -> list[MatrixTargetSpec]:
    if profile not in PROFILE_CHOICES:
        raise ValueError(f"Unsupported provider-matrix profile: {profile}")

    blueprints = _live25_blueprints(env) if profile == "live25" else _quick_blueprints(env)

    targets: list[MatrixTargetSpec] = []
    for provider, model, role in blueprints:
        config = resolve_runtime_provider_config(
            provider,
            model=model,
            env=env,
            working_dir=working_dir,
            timeout_seconds=int(timeout_seconds) if timeout_seconds is not None else None,
        )
        available = bool(config.available)
        reason = "configured" if available else "unavailable"
        target = MatrixTargetSpec(
            target_id=f"{provider.value}:{model}",
            provider=provider,
            model=model,
            lane_role=role or provider_lane_role(provider),
            tier=get_tier(provider),
            available=available,
            availability_reason=reason,
            config_source=config.source,
        )
        if include_unavailable or available:
            targets.append(target)

    return targets


async def _execute_target_prompt(
    target: MatrixTargetSpec,
    prompt: MatrixPromptSpec,
    timeout_seconds: float,
    working_dir: str | None,
    env: Mapping[str, str] | None = None,
    repair_target: MatrixTargetSpec | None = None,
) -> MatrixExecutionResult:
    effective_timeout = max(timeout_seconds, _minimum_timeout_seconds(target))
    config = resolve_runtime_provider_config(
        target.provider,
        model=target.model,
        working_dir=working_dir,
        timeout_seconds=int(max(effective_timeout, 1.0)),
        env=env,
    )
    provider = create_runtime_provider(config)
    started = time.perf_counter()
    try:
        request = LLMRequest(
            model=target.model,
            system=_matrix_system_prompt(prompt.required_keys),
            messages=[{"role": "user", "content": prompt.prompt}],
            max_tokens=prompt.max_tokens,
            temperature=0.0,
        )
        response = await asyncio.wait_for(provider.complete(request), timeout=effective_timeout)
        text = str(response.content or "")
        status, schema_valid, missing_keys = classify_matrix_response(text, prompt.required_keys)
        repair_attempted = False
        repair_strategy: str | None = None
        if status == "schema_invalid" and text.strip():
            repair_attempted = True
            repaired = await _repair_schema_invalid_response(
                provider,
                target,
                prompt,
                text,
                effective_timeout,
                repair_target=repair_target,
                working_dir=working_dir,
                env=env,
            )
            if repaired is not None:
                repaired_text, repair_strategy = repaired
                return MatrixExecutionResult(
                    target_id=target.target_id,
                    prompt_id=prompt.prompt_id,
                    status="ok",
                    response_text=repaired_text,
                    elapsed_sec=round(time.perf_counter() - started, 3),
                    schema_valid=True,
                    required_keys=[],
                    resolved_model=getattr(response, "model", None) or target.model,
                    usage=getattr(response, "usage", None),
                    error=None,
                    direct_status=status,
                    direct_schema_valid=schema_valid,
                    repair_attempted=repair_attempted,
                    repair_strategy=repair_strategy,
                )
        return MatrixExecutionResult(
            target_id=target.target_id,
            prompt_id=prompt.prompt_id,
            status=status,
            response_text=text,
            elapsed_sec=round(time.perf_counter() - started, 3),
            schema_valid=schema_valid,
            required_keys=missing_keys,
            resolved_model=getattr(response, "model", None) or target.model,
            usage=getattr(response, "usage", None),
            error=text if status != "ok" else None,
            direct_status=status,
            direct_schema_valid=schema_valid,
            repair_attempted=repair_attempted,
            repair_strategy=repair_strategy,
        )
    except Exception as exc:
        detail = str(exc).strip() or exc.__class__.__name__
        return MatrixExecutionResult(
            target_id=target.target_id,
            prompt_id=prompt.prompt_id,
            status=_classify_error(exc),
            response_text="",
            elapsed_sec=round(time.perf_counter() - started, 3),
            schema_valid=False,
            required_keys=list(prompt.required_keys),
            resolved_model=target.model,
            error=detail,
            direct_status=_classify_error(exc),
            direct_schema_valid=False,
        )
    finally:
        close = getattr(provider, "close", None)
        if callable(close):
            await close()


def _result_payload(
    result: MatrixExecutionResult,
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    payload = asdict(result)
    payload["score"] = _execution_score(result, timeout_seconds=timeout_seconds)
    payload["response_preview"] = result.response_text[:300]
    return payload


def _leaderboard(
    targets: list[MatrixTargetSpec],
    results: list[MatrixExecutionResult],
    *,
    timeout_seconds: float,
) -> list[dict[str, Any]]:
    order_index = {target.target_id: idx for idx, target in enumerate(targets)}
    by_target: dict[str, dict[str, Any]] = {
        target.target_id: {
            **_target_dict(target),
            "attempts": 0,
            "ok_count": 0,
            "schema_valid_count": 0,
            "avg_elapsed_sec": 0.0,
            "avg_score": 0.0,
        }
        for target in targets
    }
    for result in results:
        row = by_target.get(result.target_id)
        if row is None:
            continue
        row["attempts"] += 1
        row["ok_count"] += 1 if result.status == "ok" else 0
        row["schema_valid_count"] += 1 if result.schema_valid else 0
        row["avg_elapsed_sec"] += result.elapsed_sec
        row["avg_score"] += _execution_score(result, timeout_seconds=timeout_seconds)

    leaderboard: list[dict[str, Any]] = []
    for row in by_target.values():
        if row["attempts"] == 0:
            continue
        attempts = row["attempts"]
        row["avg_elapsed_sec"] = round(row["avg_elapsed_sec"] / attempts, 3)
        row["avg_score"] = round(row["avg_score"] / attempts, 2)
        leaderboard.append(row)

    return sorted(
        leaderboard,
        key=lambda item: (
            -float(item["avg_score"]),
            -int(item["ok_count"]),
            -int(item["schema_valid_count"]),
            float(item["avg_elapsed_sec"]),
            int(order_index.get(str(item["target_id"]), 10_000)),
        ),
    )


def _role_summary(leaderboard: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for row in leaderboard:
        role = str(row["lane_role"])
        bucket = buckets.setdefault(
            role,
            {
                "lane_role": role,
                "targets": 0,
                "attempts": 0,
                "ok_count": 0,
                "schema_valid_count": 0,
                "avg_score": 0.0,
            },
        )
        bucket["targets"] += 1
        bucket["attempts"] += int(row["attempts"])
        bucket["ok_count"] += int(row["ok_count"])
        bucket["schema_valid_count"] += int(row["schema_valid_count"])
        bucket["avg_score"] += float(row["avg_score"])

    summary: list[dict[str, Any]] = []
    for bucket in buckets.values():
        targets = max(bucket["targets"], 1)
        bucket["avg_score"] = round(bucket["avg_score"] / targets, 2)
        summary.append(bucket)
    return sorted(summary, key=lambda item: (-float(item["avg_score"]), str(item["lane_role"])))


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Provider Matrix Leaderboard",
        "",
        f"- Timestamp (UTC): `{payload['ts_utc']}`",
        f"- Profile: `{payload['profile']}`",
        f"- Corpus: `{payload['corpus']}`",
        f"- Attempted calls: `{payload['counts']['attempted']}`",
        f"- Budget used: `{payload['budget']['units_consumed']}` / `{payload['budget']['budget_units']}`",
        "",
        "## Top Lanes",
    ]
    leaderboard = payload.get("leaderboard", [])
    if not leaderboard:
        lines.append("")
        lines.append("No leaderboard rows were produced.")
    else:
        lines.append("")
        for row in leaderboard[:10]:
            lines.append(
                f"- `{row['provider']}` / `{row['model']}`"
                f" [{row['lane_role']}, {row['tier']}]"
                f" score=`{row['avg_score']}` ok=`{row['ok_count']}/{row['attempts']}`"
                f" schema=`{row['schema_valid_count']}` latency=`{row['avg_elapsed_sec']}s`"
            )
    role_summary = payload.get("role_summary", [])
    if role_summary:
        lines.extend(["", "## Role Summary", ""])
        for row in role_summary:
            lines.append(
                f"- `{row['lane_role']}` targets=`{row['targets']}`"
                f" ok=`{row['ok_count']}/{row['attempts']}`"
                f" schema=`{row['schema_valid_count']}` score=`{row['avg_score']}`"
            )
    return "\n".join(lines) + "\n"


def _write_artifacts(payload: dict[str, Any], *, artifact_dir: str | Path | None) -> dict[str, str]:
    root = _default_artifact_dir(artifact_dir)
    root.mkdir(parents=True, exist_ok=True)
    run_id = str(payload["run_id"])
    json_path = root / f"provider_matrix_{run_id}.json"
    markdown_path = root / f"provider_matrix_{run_id}.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    markdown_path.write_text(_render_markdown(payload))
    return {"json_path": str(json_path), "markdown_path": str(markdown_path)}


async def _run_provider_matrix_async(
    *,
    profile: str,
    corpus: str,
    max_targets: int | None,
    max_prompts: int | None,
    timeout_seconds: float,
    concurrency: int,
    budget_units: int | None,
    artifact_dir: str | Path | None,
    include_unavailable: bool,
    write_artifacts: bool,
    working_dir: str | None,
    env: Mapping[str, str] | None,
) -> dict[str, Any]:
    targets = build_default_matrix_targets(
        profile=profile,
        include_unavailable=True,
        env=env,
        working_dir=working_dir,
        timeout_seconds=timeout_seconds,
    )
    probe_snapshot: dict[str, Any] = {}
    if _should_load_probe_snapshot(env):
        try:
            probe_snapshot = await asyncio.to_thread(run_provider_smoke)
        except Exception:
            probe_snapshot = {}
    targets = _apply_probe_hints(targets, probe_snapshot)
    if max_targets is not None:
        targets = targets[: max(0, max_targets)]
    prompts = build_default_prompt_corpus(corpus, working_dir=working_dir)
    if max_prompts is not None:
        prompts = prompts[: max(0, max_prompts)]

    runnable_targets = targets if include_unavailable else [target for target in targets if target.available]
    skipped_unavailable = 0 if include_unavailable else len(targets) - len(runnable_targets)
    repair_target = _choose_matrix_repair_target(runnable_targets)

    planned: list[tuple[MatrixTargetSpec, MatrixPromptSpec]] = []
    skipped_budget = 0
    units_consumed = 0
    ceiling = budget_units if budget_units is not None else None
    for prompt in prompts:
        for target in runnable_targets:
            unit_cost = _TIER_COST_UNITS.get(target.tier, 1)
            if ceiling is not None and units_consumed + unit_cost > ceiling:
                skipped_budget += 1
                continue
            units_consumed += unit_cost
            planned.append((target, prompt))

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def _run_one(target: MatrixTargetSpec, prompt: MatrixPromptSpec) -> MatrixExecutionResult:
        async with semaphore:
            return await _execute_target_prompt(
                target,
                prompt,
                timeout_seconds=timeout_seconds,
                working_dir=working_dir,
                env=env,
                repair_target=repair_target,
            )

    results = await asyncio.gather(*[_run_one(target, prompt) for target, prompt in planned])
    leaderboard = _leaderboard(runnable_targets, results, timeout_seconds=timeout_seconds)
    role_summary = _role_summary(leaderboard)

    payload: dict[str, Any] = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": uuid4().hex[:12],
        "profile": profile,
        "corpus": corpus,
        "targets": [_target_dict(target) for target in runnable_targets],
        "prompt_ids": [prompt.prompt_id for prompt in prompts],
        "counts": {
            "configured_targets": len(targets),
            "runnable_targets": len(runnable_targets),
            "prompt_count": len(prompts),
            "attempted": len(planned),
            "ok": sum(1 for item in results if item.status == "ok"),
            "schema_valid": sum(1 for item in results if item.schema_valid),
            "failed": sum(1 for item in results if item.status not in {"ok"}),
            "skipped_unavailable": skipped_unavailable,
            "skipped_budget": skipped_budget,
        },
        "budget": {
            "budget_units": budget_units,
            "units_consumed": units_consumed,
            "tier_weights": dict(_TIER_COST_UNITS),
        },
        "leaderboard": leaderboard,
        "role_summary": role_summary,
        "results": [_result_payload(item, timeout_seconds=timeout_seconds) for item in results],
        "selection_policy": {
            "primary_reasoning_priority": [provider.value for provider in DELIBERATIVE_REASONING_PRIORITY[:6]],
            "delegated_execution_priority": [provider.value for provider in DELIBERATIVE_EXECUTION_PRIORITY[:8]],
            "escalation_priority": [provider.value for provider in ESCALATION_PRIORITY[:8]],
        },
        "probe_snapshot": probe_snapshot,
    }
    payload["artifacts"] = (
        _write_artifacts(payload, artifact_dir=artifact_dir)
        if write_artifacts
        else {}
    )
    return payload


def run_provider_matrix(
    *,
    profile: str = DEFAULT_PROFILE,
    corpus: str = DEFAULT_CORPUS,
    max_targets: int | None = None,
    max_prompts: int | None = None,
    timeout_seconds: float = 45.0,
    concurrency: int = 4,
    budget_units: int | None = 40,
    artifact_dir: str | Path | None = None,
    include_unavailable: bool = False,
    write_artifacts: bool = True,
    working_dir: str | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return asyncio.run(
        _run_provider_matrix_async(
            profile=profile,
            corpus=corpus,
            max_targets=max_targets,
            max_prompts=max_prompts,
            timeout_seconds=timeout_seconds,
            concurrency=concurrency,
            budget_units=budget_units,
            artifact_dir=artifact_dir,
            include_unavailable=include_unavailable,
            write_artifacts=write_artifacts,
            working_dir=working_dir,
            env=env,
        )
    )


__all__ = [
    "CORPUS_CHOICES",
    "DEFAULT_CORPUS",
    "DEFAULT_PROFILE",
    "MatrixExecutionResult",
    "MatrixPromptSpec",
    "MatrixTargetSpec",
    "PROFILE_CHOICES",
    "build_default_matrix_targets",
    "build_default_prompt_corpus",
    "classify_matrix_response",
    "run_provider_matrix",
]
