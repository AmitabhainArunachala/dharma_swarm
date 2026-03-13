"""Provider smoke tests with evidence-rich status output."""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Any

from dharma_swarm.models import LLMRequest, ProviderType
from dharma_swarm.ollama_config import (
    OLLAMA_CLOUD_FRONTIER_MODELS,
)
from dharma_swarm.runtime_provider import (
    NVIDIA_NIM_BASE_URL,
    OPENROUTER_BASE_URL,
    create_runtime_provider,
    resolve_runtime_provider_config,
)


_SIZE_RE = re.compile(r"(?P<size>\d+(?:\.\d+)?)\s*(?P<unit>[bkmg]?)", re.I)
_OLLAMA_ROOT_ERROR_MARKERS = (
    "ensure path elements are traversable",
    ".ollama: file exists",
)
_NIM_HOSTED_FRONTIER_MODELS = (
    "nvidia/llama-3.1-nemotron-ultra-253b-v1",
    "meta/llama-3.3-70b-instruct",
    "qwen/qwen2.5-coder-32b-instruct",
)
_NIM_SELF_HOSTED_FRONTIER_MODELS = (
    "moonshotai/kimi-k2.5",
    "zai-org/GLM-5",
    "meta/llama-3.3-70b-instruct",
    "qwen/qwen2.5-coder-32b-instruct",
)
_OPENROUTER_FRONTIER_MODELS = (
    "moonshotai/kimi-k2.5",
    "z-ai/glm-5",
    "openai/gpt-5-codex",
    "deepseek/deepseek-r1",
    "qwen/qwen3-235b-a22b",
)


def _classify_error(exc: Exception | str) -> str:
    text = str(exc).strip().lower()
    if "operation not permitted" in text or "permission denied" in text:
        return "blocked"
    if "unauthorized" in text or "http error 401" in text:
        return "auth_failed"
    if "not set" in text:
        return "missing_config"
    if any(marker in text for marker in _OLLAMA_ROOT_ERROR_MARKERS):
        return "misconfigured"
    if "http error 404" in text or "no endpoints found" in text:
        return "unknown_model"
    if "http error 410" in text:
        return "deprecated"
    if "all connection attempts failed" in text or "connection refused" in text:
        return "unreachable"
    if "timed out" in text or "timeout" in text:
        return "timeout"
    return "error"


def _strength_score(model_name: str) -> tuple[float, int]:
    text = model_name.lower()
    matches = list(_SIZE_RE.finditer(text))
    if not matches:
        return (0.0, len(text))
    scored: list[float] = []
    for match in matches:
        number = float(match.group("size"))
        unit = match.group("unit").lower()
        scale = {"": 0.0, "b": 1.0, "m": 0.001, "k": 0.000001, "g": 1000.0}.get(unit, 0.0)
        scored.append(number * scale)
    best = max(scored) if scored else 0.0
    return (best, len(text))


def _configured_ollama_root(base_dir: str | Path | None = None) -> Path:
    if base_dir is not None:
        return Path(base_dir).expanduser()
    root = os.environ.get("OLLAMA_HOME") or os.environ.get("OLLAMA_ROOT")
    if root:
        return Path(root).expanduser()
    return Path.home() / ".ollama"


def _nim_deployment_mode(base_url: str | None = None) -> str:
    resolved = (
        base_url
        or os.environ.get("NVIDIA_NIM_BASE_URL")
        or NVIDIA_NIM_BASE_URL
    ).rstrip("/")
    return "self_hosted" if resolved != NVIDIA_NIM_BASE_URL else "hosted_api"


def inspect_ollama_root(base_dir: str | Path | None = None) -> dict[str, str]:
    root = _configured_ollama_root(base_dir)
    try:
        resolved = root.resolve(strict=False)
    except OSError:
        resolved = root

    issue = ""
    symlink_target = ""
    try:
        if root.is_symlink():
            symlink_target = str(root.readlink())
            if not root.exists():
                issue = "broken_symlink"
        elif not root.exists():
            issue = "missing"
    except OSError:
        issue = "unreadable"

    return {
        "configured_root": str(root),
        "resolved_root": str(resolved),
        "root_issue": issue,
        "symlink_target": symlink_target,
    }


def list_ollama_manifest_models(base_dir: str | Path | None = None) -> list[str]:
    """Best-effort discovery of locally installed Ollama models from manifests."""
    root = _configured_ollama_root(base_dir)
    try:
        resolved = root.resolve(strict=False)
    except OSError:
        resolved = root
    manifests_root = resolved / "models" / "manifests"
    if not manifests_root.exists():
        return []

    found: set[str] = set()
    for path in manifests_root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(manifests_root)
        parts = rel.parts
        if len(parts) < 3:
            continue
        if parts[0] == "registry.ollama.ai" and parts[1] == "library":
            found.add(parts[2])
            continue
        found.add(parts[-2] if len(parts) >= 2 else parts[-1])
    return sorted(found)


def strongest_ollama_model(installed_models: list[str]) -> str | None:
    if not installed_models:
        return None
    ranked = sorted(installed_models, key=_strength_score, reverse=True)
    return ranked[0]


async def _probe_ollama(model: str) -> dict[str, Any]:
    config = resolve_runtime_provider_config(
        ProviderType.OLLAMA,
        model=model,
    )
    provider = create_runtime_provider(config)
    try:
        response = await provider.complete(
            LLMRequest(
                model=model,
                messages=[{"role": "user", "content": "Reply with exactly OK."}],
                max_tokens=16,
                temperature=0.0,
            )
        )
        return {
            "status": "ok",
            "model": response.model or model,
            "response_preview": (response.content or "")[:120],
            "usage": response.usage,
            "base_url": config.base_url,
            "transport_mode": config.transport_mode,
        }
    except Exception as exc:
        return {
            "status": _classify_error(exc),
            "model": model,
            "base_url": config.base_url,
            "transport_mode": config.transport_mode,
            "error": str(exc),
        }
    finally:
        await provider.close()


async def _probe_nim(model: str) -> dict[str, Any]:
    config = resolve_runtime_provider_config(
        ProviderType.NVIDIA_NIM,
        model=model,
    )
    provider = create_runtime_provider(config)
    try:
        response = await provider.complete(
            LLMRequest(
                model=model,
                messages=[{"role": "user", "content": "Reply with exactly OK."}],
                max_tokens=16,
                temperature=0.0,
            )
        )
        return {
            "status": "ok",
            "model": response.model or model,
            "response_preview": (response.content or "")[:120],
            "usage": response.usage,
            "base_url": config.base_url,
        }
    except Exception as exc:
        return {
            "status": _classify_error(exc),
            "model": model,
            "base_url": config.base_url or "",
            "error": str(exc),
        }
    finally:
        await provider.close()


async def _probe_openrouter(model: str) -> dict[str, Any]:
    config = resolve_runtime_provider_config(
        ProviderType.OPENROUTER,
        model=model,
    )
    provider = create_runtime_provider(config)
    try:
        response = await provider.complete(
            LLMRequest(
                model=model,
                messages=[{"role": "user", "content": "Reply with exactly OK."}],
                max_tokens=16,
                temperature=0.0,
            )
        )
        return {
            "status": "ok",
            "model": response.model or model,
            "response_preview": (response.content or "")[:120],
            "usage": response.usage,
            "base_url": config.base_url,
        }
    except Exception as exc:
        return {
            "status": _classify_error(exc),
            "model": model,
            "base_url": config.base_url,
            "error": str(exc),
        }
    finally:
        client = getattr(provider, "_client", None)
        if client is not None:
            await client.close()


def _dedupe_models(models: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for model in models:
        name = str(model).strip()
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


async def _probe_model_pack(
    probe_fn,
    models: list[str],
) -> dict[str, Any]:
    verified: list[dict[str, Any]] = []
    first_success: dict[str, Any] | None = None

    for model in _dedupe_models(models):
        result = await probe_fn(model)
        verified.append(result)
        if first_success is None and result.get("status") == "ok":
            first_success = result

    if first_success is not None:
        return {
            **first_success,
            "verified_models": verified,
            "strongest_verified": first_success.get("model"),
        }

    if verified:
        return {
            **verified[0],
            "verified_models": verified,
            "strongest_verified": None,
        }

    return {
        "status": "missing_config",
        "model": "",
        "verified_models": [],
        "strongest_verified": None,
        "error": "No models configured for probe pack.",
    }


def run_provider_smoke(
    *,
    ollama_model: str | None = None,
    nim_model: str | None = None,
) -> dict[str, Any]:
    """Run best-effort smoke tests for cloud and external provider lanes."""
    ollama_config = resolve_runtime_provider_config(ProviderType.OLLAMA)
    nim_config = resolve_runtime_provider_config(ProviderType.NVIDIA_NIM)
    openrouter_config = resolve_runtime_provider_config(ProviderType.OPENROUTER)

    nim_base_url = nim_config.base_url or NVIDIA_NIM_BASE_URL
    nim_mode = _nim_deployment_mode(nim_base_url)
    ollama_base_url = ollama_config.base_url or ""
    ollama_mode = ollama_config.transport_mode or "local_api"
    ollama_root = (
        inspect_ollama_root()
        if ollama_mode == "local_api"
        else {
            "configured_root": "",
            "resolved_root": "",
            "root_issue": "",
            "symlink_target": "",
        }
    )
    installed = list_ollama_manifest_models() if ollama_mode == "local_api" else []
    strongest_local = strongest_ollama_model(installed)
    resolved_ollama = _dedupe_models(
        [
            ollama_model or "",
            ollama_config.default_model or "",
            *(OLLAMA_CLOUD_FRONTIER_MODELS if ollama_mode == "cloud_api" else ()),
            strongest_local or "",
        ]
    )
    resolved_nim = _dedupe_models(
        [
            nim_model or "",
            os.environ.get("NVIDIA_NIM_MODEL", ""),
            *(
                _NIM_SELF_HOSTED_FRONTIER_MODELS
                if nim_mode == "self_hosted"
                else _NIM_HOSTED_FRONTIER_MODELS
            ),
        ]
    )
    resolved_openrouter = _dedupe_models(
        [
            os.environ.get("OPENROUTER_MODEL", ""),
            *_OPENROUTER_FRONTIER_MODELS,
        ]
    )

    ollama = asyncio.run(_probe_model_pack(_probe_ollama, resolved_ollama))
    nim = asyncio.run(_probe_model_pack(_probe_nim, resolved_nim))
    openrouter = asyncio.run(_probe_model_pack(_probe_openrouter, resolved_openrouter))

    return {
        "ollama": {
            "configured_base_url": ollama_base_url,
            "transport_mode": ollama_mode,
            "api_key_configured": bool(os.environ.get("OLLAMA_API_KEY", "").strip()),
            "installed_models": installed,
            "strongest_installed": strongest_local,
            "catalog_models": list(OLLAMA_CLOUD_FRONTIER_MODELS),
            "configured_model": resolved_ollama[0] if resolved_ollama else "",
            **ollama_root,
            **ollama,
        },
        "nvidia_nim": {
            "configured_base_url": nim_base_url,
            "configured_model": resolved_nim[0] if resolved_nim else "",
            "deployment_mode": nim_mode,
            "catalog_models": {
                "hosted_api": list(_NIM_HOSTED_FRONTIER_MODELS),
                "self_hosted": list(_NIM_SELF_HOSTED_FRONTIER_MODELS),
            },
            **nim,
        },
        "openrouter": {
            "configured_base_url": openrouter_config.base_url or OPENROUTER_BASE_URL,
            "configured_model": resolved_openrouter[0] if resolved_openrouter else "",
            **openrouter,
        },
    }


__all__ = [
    "inspect_ollama_root",
    "list_ollama_manifest_models",
    "run_provider_smoke",
    "strongest_ollama_model",
]
