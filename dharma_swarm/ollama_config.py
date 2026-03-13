"""Canonical Ollama endpoint and model resolution helpers."""

from __future__ import annotations

import os


OLLAMA_LOCAL_BASE_URL = "http://localhost:11434"
OLLAMA_CLOUD_BASE_URL = "https://ollama.com"
OLLAMA_DEFAULT_LOCAL_MODEL = "llama3.2"
OLLAMA_DEFAULT_CLOUD_MODEL = "kimi-k2.5:cloud"
OLLAMA_CLOUD_FRONTIER_MODELS = (
    "kimi-k2.5:cloud",
    "glm-5:cloud",
)

_LOCAL_BASE_URLS = {
    OLLAMA_LOCAL_BASE_URL,
    "http://127.0.0.1:11434",
    "http://0.0.0.0:11434",
}


def _normalize_base_url(base_url: str | None) -> str:
    return (base_url or "").strip().rstrip("/")


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def is_ollama_cloud_base_url(base_url: str | None) -> bool:
    normalized = _normalize_base_url(base_url)
    return normalized.startswith(OLLAMA_CLOUD_BASE_URL)


def ollama_prefers_cloud(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
) -> bool:
    if _env_flag("OLLAMA_FORCE_LOCAL"):
        return False
    if _env_flag("OLLAMA_USE_CLOUD"):
        return True

    resolved_key = (api_key if api_key is not None else os.environ.get("OLLAMA_API_KEY", "")).strip()
    if not resolved_key:
        return False

    candidate = _normalize_base_url(
        base_url if base_url is not None else os.environ.get("OLLAMA_BASE_URL")
    )
    if not candidate or candidate in _LOCAL_BASE_URLS:
        return True
    return is_ollama_cloud_base_url(candidate)


def resolve_ollama_base_url(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
) -> str:
    explicit = _normalize_base_url(base_url)
    if explicit:
        return explicit

    configured = _normalize_base_url(os.environ.get("OLLAMA_BASE_URL"))
    if ollama_prefers_cloud(base_url=configured or None, api_key=api_key):
        return OLLAMA_CLOUD_BASE_URL
    return configured or OLLAMA_LOCAL_BASE_URL


def ollama_transport_mode(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
) -> str:
    resolved = resolve_ollama_base_url(base_url=base_url, api_key=api_key)
    return "cloud_api" if is_ollama_cloud_base_url(resolved) else "local_api"


def resolve_ollama_model(
    model: str | None = None,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
) -> str:
    explicit = (model or "").strip()
    if explicit:
        return explicit

    configured = os.environ.get("OLLAMA_MODEL", "").strip()
    if configured:
        return configured

    if ollama_transport_mode(base_url=base_url, api_key=api_key) == "cloud_api":
        return OLLAMA_DEFAULT_CLOUD_MODEL
    return OLLAMA_DEFAULT_LOCAL_MODEL


def build_ollama_headers(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, str]:
    resolved = resolve_ollama_base_url(base_url=base_url, api_key=api_key)
    if not is_ollama_cloud_base_url(resolved):
        return {}

    token = (api_key if api_key is not None else os.environ.get("OLLAMA_API_KEY", "")).strip()
    if not token:
        raise RuntimeError("OLLAMA_API_KEY not set")
    return {"Authorization": f"Bearer {token}"}


__all__ = [
    "OLLAMA_CLOUD_BASE_URL",
    "OLLAMA_CLOUD_FRONTIER_MODELS",
    "OLLAMA_DEFAULT_CLOUD_MODEL",
    "OLLAMA_DEFAULT_LOCAL_MODEL",
    "OLLAMA_LOCAL_BASE_URL",
    "build_ollama_headers",
    "is_ollama_cloud_base_url",
    "ollama_prefers_cloud",
    "ollama_transport_mode",
    "resolve_ollama_base_url",
    "resolve_ollama_model",
]
