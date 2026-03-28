"""Canonical API key inventory and live audit helpers.

This module is the canonical place for DHARMA SWARM provider-key auditing.
Runtime auth/model resolution still lives in ``runtime_provider.py``; this file
layers environment inventory, auth probes, and agentic viability checks on top
of that runtime path.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Mapping

import httpx

from dharma_swarm.model_hierarchy import DEFAULT_MODELS
from dharma_swarm.models import LLMRequest, ProviderType
from dharma_swarm.runtime_provider import create_runtime_provider, resolve_runtime_provider_config

CANONICAL_RUNTIME_OWNER = "dharma_swarm/runtime_provider.py"
DOCUMENTED_ENV_PATH = ".env.template"
_AUTH_TIMEOUT_SECONDS = 20.0
_COMPLETION_TIMEOUT_SECONDS = 60.0
_AGENTIC_TIMEOUT_SECONDS = 60.0
_AGENTIC_TOOL_TASK = (
    "Use at least two tools. First use read_file on README.md. Then use grep_search "
    "for resolve_runtime_provider_config inside dharma_swarm/runtime_provider.py. "
    "After both tools, answer in one short sentence that starts with VERIFIED:. "
    "Do not edit anything."
)
_AGENTIC_SYSTEM_PROMPT = (
    "You are a read-only repo auditor. Use tools when explicitly asked."
)


@dataclass(frozen=True, slots=True)
class ApiKeyAuditSpec:
    key_name: str
    provider: ProviderType | None = None
    auth_url: str | None = None
    notes: str = ""
    auth_header_extras: tuple[tuple[str, str], ...] = ()


API_KEY_AUDIT_SPECS: tuple[ApiKeyAuditSpec, ...] = (
    ApiKeyAuditSpec(
        key_name="ANTHROPIC_API_KEY",
        provider=ProviderType.ANTHROPIC,
        auth_url="https://api.anthropic.com/v1/models",
        notes="Direct Anthropic lane.",
    ),
    ApiKeyAuditSpec(
        key_name="OPENAI_API_KEY",
        provider=ProviderType.OPENAI,
        auth_url="https://api.openai.com/v1/models",
        notes="Direct OpenAI lane. Current runtime default is gpt-5.",
    ),
    ApiKeyAuditSpec(
        key_name="OPENROUTER_API_KEY",
        provider=ProviderType.OPENROUTER,
        auth_url="https://openrouter.ai/api/v1/models",
        notes="OpenRouter key also backs the free OpenRouter lane.",
        auth_header_extras=(
            ("HTTP-Referer", "http://localhost"),
            ("X-Title", "DHARMA SWARM api-key audit"),
        ),
    ),
    ApiKeyAuditSpec(
        key_name="NVIDIA_NIM_API_KEY",
        provider=ProviderType.NVIDIA_NIM,
        auth_url="https://integrate.api.nvidia.com/v1/models",
        notes="NVIDIA hosted NIM lane.",
    ),
    ApiKeyAuditSpec(
        key_name="OLLAMA_API_KEY",
        provider=ProviderType.OLLAMA,
        notes="Ollama Cloud lane. Auth check falls back to live completion because the runtime uses the Ollama cloud chat endpoint.",
    ),
    ApiKeyAuditSpec(
        key_name="GROQ_API_KEY",
        provider=ProviderType.GROQ,
        auth_url="https://api.groq.com/openai/v1/models",
        notes="Groq OpenAI-compatible lane.",
    ),
    ApiKeyAuditSpec(
        key_name="CEREBRAS_API_KEY",
        provider=ProviderType.CEREBRAS,
        auth_url="https://api.cerebras.ai/v1/models",
        notes="Cerebras OpenAI-compatible lane.",
    ),
    ApiKeyAuditSpec(
        key_name="SILICONFLOW_API_KEY",
        provider=ProviderType.SILICONFLOW,
        auth_url="https://api.siliconflow.cn/v1/models",
        notes="SiliconFlow OpenAI-compatible lane.",
    ),
    ApiKeyAuditSpec(
        key_name="TOGETHER_API_KEY",
        provider=ProviderType.TOGETHER,
        auth_url="https://api.together.xyz/v1/models",
        notes="Together AI OpenAI-compatible lane.",
    ),
    ApiKeyAuditSpec(
        key_name="FIREWORKS_API_KEY",
        provider=ProviderType.FIREWORKS,
        auth_url="https://api.fireworks.ai/inference/v1/models",
        notes="Fireworks AI OpenAI-compatible lane.",
    ),
    ApiKeyAuditSpec(
        key_name="GOOGLE_AI_API_KEY",
        provider=ProviderType.GOOGLE_AI,
        auth_url="https://generativelanguage.googleapis.com/v1beta/openai/models",
        notes="Google AI Studio OpenAI-compatible lane.",
    ),
    ApiKeyAuditSpec(
        key_name="SAMBANOVA_API_KEY",
        provider=ProviderType.SAMBANOVA,
        auth_url="https://api.sambanova.ai/v1/models",
        notes="SambaNova OpenAI-compatible lane.",
    ),
    ApiKeyAuditSpec(
        key_name="MISTRAL_API_KEY",
        provider=ProviderType.MISTRAL,
        auth_url="https://api.mistral.ai/v1/models",
        notes="Mistral OpenAI-compatible lane.",
    ),
    ApiKeyAuditSpec(
        key_name="CHUTES_API_KEY",
        provider=ProviderType.CHUTES,
        auth_url="https://api.chutes.ai/v1/models",
        notes="Chutes OpenAI-compatible lane.",
    ),
    ApiKeyAuditSpec(
        key_name="MOONSHOT_API_KEY",
        auth_url="https://api.moonshot.cn/v1/models",
        notes="Legacy/adjacent provider. Present in providers_extended.py, not wired into runtime_provider.py.",
    ),
)


def configured_key_names(env: Mapping[str, str] | None = None) -> list[str]:
    env_map = env or os.environ
    return [
        spec.key_name
        for spec in API_KEY_AUDIT_SPECS
        if str(env_map.get(spec.key_name, "")).strip()
    ]


def _probe_preview_from_body(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    items = body.get("data")
    if not isinstance(items, list) or not items:
        return None
    first = items[0]
    if not isinstance(first, dict):
        return str(first)[:120]
    for key in ("id", "name", "model"):
        value = first.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return json.dumps(first, default=str)[:120]


def _summarize_http_body(response: httpx.Response) -> tuple[str, str | None]:
    text = " ".join(response.text.split())[:240]
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return text, None
    return text, _probe_preview_from_body(payload)


def _effective_model(provider: ProviderType, model: str | None) -> str:
    if model:
        return model
    default = DEFAULT_MODELS.get(provider)
    return default or ""


async def _probe_auth_endpoint(
    spec: ApiKeyAuditSpec,
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    env_map = env or os.environ
    token = str(env_map.get(spec.key_name, "")).strip()
    if not token:
        return {"status": "missing_config"}
    if not spec.auth_url:
        return {"status": "skipped", "reason": "no_auth_probe"}

    headers = {"Authorization": f"Bearer {token}"}
    headers.update(dict(spec.auth_header_extras))
    try:
        async with httpx.AsyncClient(timeout=_AUTH_TIMEOUT_SECONDS) as client:
            response = await client.get(spec.auth_url, headers=headers)
        body, preview = _summarize_http_body(response)
        return {
            "status": "ok" if response.status_code == 200 else "error",
            "status_code": response.status_code,
            "preview": preview,
            "body": body,
        }
    except Exception as exc:
        detail = str(exc).strip() or exc.__class__.__name__
        return {"status": "error", "error": detail[:240]}


async def _probe_default_completion(
    spec: ApiKeyAuditSpec,
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if spec.provider is None:
        return {"status": "unwired"}

    cfg = resolve_runtime_provider_config(spec.provider, env=env)
    model = _effective_model(spec.provider, cfg.default_model)
    result = {
        "status": "missing_config" if not cfg.available else "pending",
        "provider": spec.provider.value,
        "model": model,
        "base_url": cfg.base_url,
    }
    if not cfg.available:
        return result

    provider = create_runtime_provider(resolve_runtime_provider_config(spec.provider, model=model, env=env))
    started = time.perf_counter()
    try:
        response = await asyncio.wait_for(
            provider.complete(
                LLMRequest(
                    model=model,
                    messages=[{"role": "user", "content": "Reply with exactly OK."}],
                    max_tokens=16,
                    temperature=0.0,
                )
            ),
            timeout=_COMPLETION_TIMEOUT_SECONDS,
        )
        result.update(
            {
                "status": "ok" if str(response.content or "").strip() else "empty_response",
                "elapsed_sec": round(time.perf_counter() - started, 3),
                "model": getattr(response, "model", None) or model,
                "response_preview": str(response.content or "")[:120],
            }
        )
        return result
    except Exception as exc:
        detail = str(exc).strip() or exc.__class__.__name__
        result.update(
            {
                "status": "error",
                "elapsed_sec": round(time.perf_counter() - started, 3),
                "error": detail[:240],
            }
        )
        return result
    finally:
        close = getattr(provider, "close", None)
        if callable(close):
            try:
                await close()
            except Exception:
                pass
        client = getattr(provider, "_client", None)
        if client is not None:
            for method_name in ("close", "aclose"):
                method = getattr(client, method_name, None)
                if callable(method):
                    try:
                        await method()
                    except Exception:
                        pass


async def _probe_default_agentic(
    spec: ApiKeyAuditSpec,
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if spec.provider is None:
        return {"status": "unwired"}

    from api.routers.chat import ChatRuntimeSettings, _agentic_stream

    cfg = resolve_runtime_provider_config(spec.provider, env=env)
    model = _effective_model(spec.provider, cfg.default_model)
    result = {
        "status": "missing_config" if not (cfg.available and cfg.api_key and cfg.base_url) else "pending",
        "provider": spec.provider.value,
        "model": model,
        "base_url": cfg.base_url,
    }
    if not (cfg.available and cfg.api_key and cfg.base_url):
        return result

    settings = ChatRuntimeSettings(
        provider=spec.provider,
        api_key=cfg.api_key or "",
        base_url=cfg.base_url or "",
        model=model,
        available=True,
        max_tool_rounds=4,
        max_tokens=512,
        timeout_seconds=45.0,
        tool_result_max_chars=4_000,
        history_message_limit=20,
        temperature=0.0,
    )

    tool_names: list[str] = []
    tool_results = 0
    content_parts: list[str] = []
    errors: list[str] = []
    started = time.perf_counter()

    try:
        async def _run() -> None:
            nonlocal tool_results
            async for chunk in _agentic_stream(
                [
                    {"role": "system", "content": _AGENTIC_SYSTEM_PROMPT},
                    {"role": "user", "content": _AGENTIC_TOOL_TASK},
                ],
                settings,
                profile_id="api_key_audit",
            ):
                if not chunk.startswith("data: "):
                    continue
                payload_raw = chunk[6:].strip()
                if payload_raw == "[DONE]":
                    continue
                payload = json.loads(payload_raw)
                if "tool_call" in payload:
                    tool_names.append(str(payload["tool_call"].get("name", "")))
                if "tool_result" in payload:
                    tool_results += 1
                if "content" in payload:
                    content_parts.append(str(payload["content"]))
                if "error" in payload:
                    errors.append(str(payload["error"]))

        await asyncio.wait_for(_run(), timeout=_AGENTIC_TIMEOUT_SECONDS)
    except Exception as exc:
        detail = str(exc).strip() or exc.__class__.__name__
        result.update(
            {
                "status": "error",
                "elapsed_sec": round(time.perf_counter() - started, 3),
                "tool_calls": len(tool_names),
                "tool_results": tool_results,
                "tool_names": tool_names,
                "response_preview": "".join(content_parts)[:180],
                "error": detail[:240],
                "errors": errors[:3],
            }
        )
        return result

    status = "ok"
    if errors:
        status = "error"
    elif not tool_names:
        status = "no_tool_calls"
    elif tool_results < 2:
        status = "partial_tooling"
    elif not "".join(content_parts).strip():
        status = "tool_only"

    result.update(
        {
            "status": status,
            "elapsed_sec": round(time.perf_counter() - started, 3),
            "tool_calls": len(tool_names),
            "tool_results": tool_results,
            "tool_names": tool_names,
            "response_preview": "".join(content_parts)[:180],
            "errors": errors[:3],
        }
    )
    return result


def _auth_ok(record: dict[str, Any]) -> bool:
    auth = record.get("auth", {})
    if auth.get("status") == "ok":
        return True
    if auth.get("status") == "skipped":
        completion = record.get("default_completion", {})
        return completion.get("status") == "ok"
    return False


def summarize_audit_records(records: list[dict[str, Any]]) -> dict[str, int]:
    configured = [record for record in records if record.get("configured")]
    wired = [record for record in configured if record.get("provider")]
    return {
        "configured": len(configured),
        "configured_auth_ok": sum(1 for record in configured if _auth_ok(record)),
        "default_completion_ok": sum(
            1
            for record in wired
            if record.get("default_completion", {}).get("status") == "ok"
        ),
        "default_agentic_ok": sum(
            1
            for record in wired
            if record.get("default_agentic", {}).get("status") == "ok"
        ),
        "wired": len(wired),
        "unwired": sum(1 for record in configured if not record.get("provider")),
    }


async def run_api_key_audit(
    *,
    include_agentic: bool = True,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    env_map = env or os.environ
    records: list[dict[str, Any]] = []
    for spec in API_KEY_AUDIT_SPECS:
        configured = bool(str(env_map.get(spec.key_name, "")).strip())
        record: dict[str, Any] = {
            "key_name": spec.key_name,
            "configured": configured,
            "provider": spec.provider.value if spec.provider else "",
            "notes": spec.notes,
            "canonical_runtime_owner": CANONICAL_RUNTIME_OWNER,
        }
        record["auth"] = await _probe_auth_endpoint(spec, env=env_map)
        record["default_completion"] = await _probe_default_completion(spec, env=env_map)
        if include_agentic:
            record["default_agentic"] = await _probe_default_agentic(spec, env=env_map)
        else:
            record["default_agentic"] = {"status": "skipped"}
        records.append(record)

    return {
        "canonical_runtime_owner": CANONICAL_RUNTIME_OWNER,
        "documented_env_path": DOCUMENTED_ENV_PATH,
        "configured_key_names": configured_key_names(env_map),
        "summary": summarize_audit_records(records),
        "records": records,
    }


def _render_text_report(payload: dict[str, Any]) -> str:
    lines = [
        f"canonical_runtime_owner: {payload['canonical_runtime_owner']}",
        f"documented_env_path: {payload['documented_env_path']}",
        f"configured_keys: {payload['summary']['configured']}",
        f"configured_auth_ok: {payload['summary']['configured_auth_ok']}",
        f"default_completion_ok: {payload['summary']['default_completion_ok']}",
        f"default_agentic_ok: {payload['summary']['default_agentic_ok']}",
        "",
    ]
    for record in payload["records"]:
        if not record["configured"]:
            continue
        lines.append(f"{record['key_name']}:")
        lines.append(f"  provider: {record['provider'] or 'unwired'}")
        lines.append(f"  auth: {record['auth'].get('status')}")
        lines.append(f"  default_completion: {record['default_completion'].get('status')}")
        lines.append(f"  default_agentic: {record['default_agentic'].get('status')}")
        model = record["default_completion"].get("model")
        if model:
            lines.append(f"  model: {model}")
        base_url = record["default_completion"].get("base_url")
        if base_url:
            lines.append(f"  base_url: {base_url}")
        note = record.get("notes")
        if note:
            lines.append(f"  note: {note}")
        error = (
            record["default_agentic"].get("error")
            or record["default_completion"].get("error")
            or record["auth"].get("error")
        )
        if error:
            lines.append(f"  detail: {error}")
        elif record["auth"].get("body") and record["auth"].get("status") != "ok":
            lines.append(f"  detail: {record['auth']['body']}")
        lines.append("")
    return "\n".join(lines).rstrip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit configured API keys against the DHARMA SWARM runtime.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument(
        "--no-agentic",
        action="store_true",
        help="Skip the slower tool-using agentic probe.",
    )
    args = parser.parse_args(argv)

    payload = asyncio.run(run_api_key_audit(include_agentic=not args.no_agentic))
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(_render_text_report(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
