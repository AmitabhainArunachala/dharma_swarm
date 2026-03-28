"""Canonical API key and endpoint env registry for DHARMA SWARM.

This package-local module is the single source of truth for every named
external API credential and provider endpoint env var used by first-party
code.
"""

from __future__ import annotations

import os
from typing import Iterable, Mapping

ANTHROPIC_API_KEY_ENV = "ANTHROPIC_API_KEY"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
OPENROUTER_API_KEY_ENV = "OPENROUTER_API_KEY"
NVIDIA_NIM_API_KEY_ENV = "NVIDIA_NIM_API_KEY"
OLLAMA_API_KEY_ENV = "OLLAMA_API_KEY"
GROQ_API_KEY_ENV = "GROQ_API_KEY"
CEREBRAS_API_KEY_ENV = "CEREBRAS_API_KEY"
SILICONFLOW_API_KEY_ENV = "SILICONFLOW_API_KEY"
TOGETHER_API_KEY_ENV = "TOGETHER_API_KEY"
FIREWORKS_API_KEY_ENV = "FIREWORKS_API_KEY"
GOOGLE_AI_API_KEY_ENV = "GOOGLE_AI_API_KEY"
SAMBANOVA_API_KEY_ENV = "SAMBANOVA_API_KEY"
MISTRAL_API_KEY_ENV = "MISTRAL_API_KEY"
CHUTES_API_KEY_ENV = "CHUTES_API_KEY"
MOONSHOT_API_KEY_ENV = "MOONSHOT_API_KEY"
NGC_API_KEY_ENV = "NGC_API_KEY"
NVIDIA_API_KEY_ENV = "NVIDIA_API_KEY"

DASHBOARD_API_KEY_ENV = "DASHBOARD_API_KEY"
FRED_API_KEY_ENV = "FRED_API_KEY"
FINNHUB_API_KEY_ENV = "FINNHUB_API_KEY"
DGC_DATA_FLYWHEEL_API_KEY_ENV = "DGC_DATA_FLYWHEEL_API_KEY"
DGC_KAIZENOPS_API_KEY_ENV = "DGC_KAIZENOPS_API_KEY"
DGC_RECIPROCITY_COMMONS_API_KEY_ENV = "DGC_RECIPROCITY_COMMONS_API_KEY"

OPENAI_BASE_URL_ENV = "OPENAI_BASE_URL"
OPENROUTER_BASE_URL_ENV = "OPENROUTER_BASE_URL"
NVIDIA_NIM_BASE_URL_ENV = "NVIDIA_NIM_BASE_URL"
OLLAMA_BASE_URL_ENV = "OLLAMA_BASE_URL"
GROQ_BASE_URL_ENV = "GROQ_BASE_URL"
CEREBRAS_BASE_URL_ENV = "CEREBRAS_BASE_URL"
SILICONFLOW_BASE_URL_ENV = "SILICONFLOW_BASE_URL"
TOGETHER_BASE_URL_ENV = "TOGETHER_BASE_URL"
FIREWORKS_BASE_URL_ENV = "FIREWORKS_BASE_URL"
GOOGLE_AI_BASE_URL_ENV = "GOOGLE_AI_BASE_URL"
SAMBANOVA_BASE_URL_ENV = "SAMBANOVA_BASE_URL"
MISTRAL_BASE_URL_ENV = "MISTRAL_BASE_URL"
CHUTES_BASE_URL_ENV = "CHUTES_BASE_URL"
MOONSHOT_BASE_URL_ENV = "MOONSHOT_BASE_URL"


def _unique_in_order(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return tuple(ordered)


PROVIDER_API_KEY_ENV_KEYS: dict[str, str] = {
    "anthropic": ANTHROPIC_API_KEY_ENV,
    "openai": OPENAI_API_KEY_ENV,
    "openrouter": OPENROUTER_API_KEY_ENV,
    "openrouter_free": OPENROUTER_API_KEY_ENV,
    "nvidia_nim": NVIDIA_NIM_API_KEY_ENV,
    "ollama": OLLAMA_API_KEY_ENV,
    "groq": GROQ_API_KEY_ENV,
    "cerebras": CEREBRAS_API_KEY_ENV,
    "siliconflow": SILICONFLOW_API_KEY_ENV,
    "together": TOGETHER_API_KEY_ENV,
    "fireworks": FIREWORKS_API_KEY_ENV,
    "google_ai": GOOGLE_AI_API_KEY_ENV,
    "sambanova": SAMBANOVA_API_KEY_ENV,
    "mistral": MISTRAL_API_KEY_ENV,
    "chutes": CHUTES_API_KEY_ENV,
}

CHAT_PROVIDER_API_KEY_ENV_KEYS: dict[str, str] = {
    "openrouter": OPENROUTER_API_KEY_ENV,
    "openrouter_free": OPENROUTER_API_KEY_ENV,
    "openai": OPENAI_API_KEY_ENV,
    "groq": GROQ_API_KEY_ENV,
    "siliconflow": SILICONFLOW_API_KEY_ENV,
    "together": TOGETHER_API_KEY_ENV,
    "fireworks": FIREWORKS_API_KEY_ENV,
    "nvidia_nim": NVIDIA_NIM_API_KEY_ENV,
}

PROVIDER_BASE_URL_ENV_KEYS: dict[str, str] = {
    "openai": OPENAI_BASE_URL_ENV,
    "openrouter": OPENROUTER_BASE_URL_ENV,
    "openrouter_free": OPENROUTER_BASE_URL_ENV,
    "nvidia_nim": NVIDIA_NIM_BASE_URL_ENV,
    "ollama": OLLAMA_BASE_URL_ENV,
    "groq": GROQ_BASE_URL_ENV,
    "cerebras": CEREBRAS_BASE_URL_ENV,
    "siliconflow": SILICONFLOW_BASE_URL_ENV,
    "together": TOGETHER_BASE_URL_ENV,
    "fireworks": FIREWORKS_BASE_URL_ENV,
    "google_ai": GOOGLE_AI_BASE_URL_ENV,
    "sambanova": SAMBANOVA_BASE_URL_ENV,
    "mistral": MISTRAL_BASE_URL_ENV,
    "chutes": CHUTES_BASE_URL_ENV,
}

GINKO_API_KEY_ENV_VARS: dict[str, str] = {
    "openrouter": OPENROUTER_API_KEY_ENV,
    "fred": FRED_API_KEY_ENV,
    "finnhub": FINNHUB_API_KEY_ENV,
    "ollama": OLLAMA_API_KEY_ENV,
}

SERVICE_API_KEY_ENV_KEYS: dict[str, str] = {
    "dashboard": DASHBOARD_API_KEY_ENV,
    "fred": FRED_API_KEY_ENV,
    "finnhub": FINNHUB_API_KEY_ENV,
    "data_flywheel": DGC_DATA_FLYWHEEL_API_KEY_ENV,
    "kaizen_ops": DGC_KAIZENOPS_API_KEY_ENV,
    "reciprocity_commons": DGC_RECIPROCITY_COMMONS_API_KEY_ENV,
    "moonshot": MOONSHOT_API_KEY_ENV,
    "ngc": NGC_API_KEY_ENV,
    "nvidia": NVIDIA_API_KEY_ENV,
}

RUNTIME_PROVIDER_API_KEY_ENV_KEYS: tuple[str, ...] = _unique_in_order(
    PROVIDER_API_KEY_ENV_KEYS.values()
)

ALL_API_KEY_ENV_KEYS: tuple[str, ...] = _unique_in_order(
    (
        DASHBOARD_API_KEY_ENV,
        *PROVIDER_API_KEY_ENV_KEYS.values(),
        *SERVICE_API_KEY_ENV_KEYS.values(),
    )
)


def _provider_key(provider: object) -> str:
    value = getattr(provider, "value", provider)
    return str(value)


def provider_api_key_env(provider: object) -> str | None:
    return PROVIDER_API_KEY_ENV_KEYS.get(_provider_key(provider))


def provider_base_url_env(provider: object) -> str | None:
    return PROVIDER_BASE_URL_ENV_KEYS.get(_provider_key(provider))


def service_api_key_env(name: str) -> str:
    return SERVICE_API_KEY_ENV_KEYS[name]


def env_value(env_var: str, env: Mapping[str, str] | None = None) -> str | None:
    source = env or os.environ
    value = str(source.get(env_var, "")).strip()
    return value or None


def env_has_value(env_var: str, env: Mapping[str, str] | None = None) -> bool:
    return env_value(env_var, env) is not None


def present_api_key_envs(
    env_vars: Iterable[str] | None = None,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    ordered = env_vars or ALL_API_KEY_ENV_KEYS
    return [env_var for env_var in ordered if env_has_value(env_var, env)]


def provider_available(provider: str, env: Mapping[str, str] | None = None) -> bool:
    """Return True if the named provider has a configured API key."""
    env_var = PROVIDER_API_KEY_ENV_KEYS.get(provider)
    if env_var is None:
        return False
    return env_has_value(env_var, env)


__all__ = [
    "ALL_API_KEY_ENV_KEYS",
    "ANTHROPIC_API_KEY_ENV",
    "CEREBRAS_API_KEY_ENV",
    "CEREBRAS_BASE_URL_ENV",
    "CHAT_PROVIDER_API_KEY_ENV_KEYS",
    "CHUTES_API_KEY_ENV",
    "CHUTES_BASE_URL_ENV",
    "DASHBOARD_API_KEY_ENV",
    "DGC_DATA_FLYWHEEL_API_KEY_ENV",
    "DGC_KAIZENOPS_API_KEY_ENV",
    "DGC_RECIPROCITY_COMMONS_API_KEY_ENV",
    "FINNHUB_API_KEY_ENV",
    "FIREWORKS_API_KEY_ENV",
    "FIREWORKS_BASE_URL_ENV",
    "FRED_API_KEY_ENV",
    "GINKO_API_KEY_ENV_VARS",
    "GOOGLE_AI_API_KEY_ENV",
    "GOOGLE_AI_BASE_URL_ENV",
    "GROQ_API_KEY_ENV",
    "GROQ_BASE_URL_ENV",
    "MISTRAL_API_KEY_ENV",
    "MISTRAL_BASE_URL_ENV",
    "MOONSHOT_API_KEY_ENV",
    "MOONSHOT_BASE_URL_ENV",
    "NGC_API_KEY_ENV",
    "NVIDIA_API_KEY_ENV",
    "NVIDIA_NIM_API_KEY_ENV",
    "NVIDIA_NIM_BASE_URL_ENV",
    "OLLAMA_API_KEY_ENV",
    "OLLAMA_BASE_URL_ENV",
    "OPENAI_API_KEY_ENV",
    "OPENAI_BASE_URL_ENV",
    "OPENROUTER_API_KEY_ENV",
    "OPENROUTER_BASE_URL_ENV",
    "PROVIDER_API_KEY_ENV_KEYS",
    "PROVIDER_BASE_URL_ENV_KEYS",
    "RUNTIME_PROVIDER_API_KEY_ENV_KEYS",
    "SAMBANOVA_API_KEY_ENV",
    "SAMBANOVA_BASE_URL_ENV",
    "SERVICE_API_KEY_ENV_KEYS",
    "SILICONFLOW_API_KEY_ENV",
    "SILICONFLOW_BASE_URL_ENV",
    "TOGETHER_API_KEY_ENV",
    "TOGETHER_BASE_URL_ENV",
    "env_has_value",
    "env_value",
    "present_api_key_envs",
    "provider_api_key_env",
    "provider_available",
    "provider_base_url_env",
    "service_api_key_env",
]
