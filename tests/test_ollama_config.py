"""Tests for ollama_config.py — Ollama endpoint and model resolution."""

from __future__ import annotations

import pytest

from dharma_swarm.model_hierarchy import DEFAULT_MODELS
from dharma_swarm.models import ProviderType
from dharma_swarm.ollama_config import (
    OLLAMA_CLOUD_BASE_URL,
    OLLAMA_CLOUD_FRONTIER_MODELS,
    OLLAMA_DEFAULT_CLOUD_MODEL,
    OLLAMA_DEFAULT_LOCAL_MODEL,
    OLLAMA_LOCAL_BASE_URL,
    _env_flag,
    _normalize_base_url,
    build_ollama_headers,
    is_ollama_cloud_base_url,
    ollama_prefers_cloud,
    ollama_transport_mode,
    resolve_ollama_base_url,
    resolve_ollama_model,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_local_base_url(self):
        assert OLLAMA_LOCAL_BASE_URL == "http://localhost:11434"

    def test_cloud_base_url(self):
        assert OLLAMA_CLOUD_BASE_URL == "https://ollama.com"

    def test_default_local_model(self):
        assert OLLAMA_DEFAULT_LOCAL_MODEL == "llama3.2"

    def test_default_cloud_model(self):
        assert OLLAMA_DEFAULT_CLOUD_MODEL == DEFAULT_MODELS[ProviderType.OLLAMA]

    def test_frontier_models_tuple(self):
        assert isinstance(OLLAMA_CLOUD_FRONTIER_MODELS, tuple)
        assert len(OLLAMA_CLOUD_FRONTIER_MODELS) >= 2
        assert "minimax-m2.7:cloud" in OLLAMA_CLOUD_FRONTIER_MODELS


# ---------------------------------------------------------------------------
# _normalize_base_url
# ---------------------------------------------------------------------------


class TestNormalizeBaseUrl:
    def test_none(self):
        assert _normalize_base_url(None) == ""

    def test_empty_string(self):
        assert _normalize_base_url("") == ""

    def test_strips_whitespace(self):
        assert _normalize_base_url("  http://localhost  ") == "http://localhost"

    def test_strips_trailing_slash(self):
        assert _normalize_base_url("http://localhost:11434/") == "http://localhost:11434"

    def test_strips_multiple_trailing_slashes(self):
        assert _normalize_base_url("http://localhost:11434///") == "http://localhost:11434"

    def test_passthrough(self):
        assert _normalize_base_url("http://localhost:11434") == "http://localhost:11434"


# ---------------------------------------------------------------------------
# _env_flag
# ---------------------------------------------------------------------------


class TestEnvFlag:
    def test_true_values(self, monkeypatch):
        for val in ("1", "true", "yes", "on", "TRUE", "Yes", " 1 "):
            monkeypatch.setenv("TEST_FLAG", val)
            assert _env_flag("TEST_FLAG") is True

    def test_false_values(self, monkeypatch):
        for val in ("0", "false", "no", "off", "", "random"):
            monkeypatch.setenv("TEST_FLAG", val)
            assert _env_flag("TEST_FLAG") is False

    def test_missing_env(self, monkeypatch):
        monkeypatch.delenv("TEST_FLAG", raising=False)
        assert _env_flag("TEST_FLAG") is False


# ---------------------------------------------------------------------------
# is_ollama_cloud_base_url
# ---------------------------------------------------------------------------


class TestIsOllamaCloudBaseUrl:
    def test_cloud_url(self):
        assert is_ollama_cloud_base_url("https://ollama.com") is True

    def test_cloud_url_with_path(self):
        assert is_ollama_cloud_base_url("https://ollama.com/v1/chat") is True

    def test_local_url(self):
        assert is_ollama_cloud_base_url("http://localhost:11434") is False

    def test_none(self):
        assert is_ollama_cloud_base_url(None) is False

    def test_empty(self):
        assert is_ollama_cloud_base_url("") is False


# ---------------------------------------------------------------------------
# ollama_prefers_cloud
# ---------------------------------------------------------------------------


class TestOllamaPrefersCloud:
    def test_force_local_overrides(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_FORCE_LOCAL", "1")
        monkeypatch.setenv("OLLAMA_API_KEY", "sk-test")
        assert ollama_prefers_cloud() is False

    def test_use_cloud_flag(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_FORCE_LOCAL", raising=False)
        monkeypatch.setenv("OLLAMA_USE_CLOUD", "1")
        assert ollama_prefers_cloud() is True

    def test_api_key_with_local_url_prefers_cloud(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_FORCE_LOCAL", raising=False)
        monkeypatch.delenv("OLLAMA_USE_CLOUD", raising=False)
        monkeypatch.setenv("OLLAMA_API_KEY", "sk-test")
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        assert ollama_prefers_cloud() is True

    def test_no_api_key_no_cloud(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_FORCE_LOCAL", raising=False)
        monkeypatch.delenv("OLLAMA_USE_CLOUD", raising=False)
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        assert ollama_prefers_cloud() is False

    def test_explicit_api_key_param(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_FORCE_LOCAL", raising=False)
        monkeypatch.delenv("OLLAMA_USE_CLOUD", raising=False)
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        assert ollama_prefers_cloud(api_key="sk-test") is True

    def test_explicit_cloud_base_url(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_FORCE_LOCAL", raising=False)
        monkeypatch.delenv("OLLAMA_USE_CLOUD", raising=False)
        monkeypatch.setenv("OLLAMA_API_KEY", "sk-test")
        assert ollama_prefers_cloud(base_url="https://ollama.com") is True

    def test_explicit_non_local_non_cloud_url(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_FORCE_LOCAL", raising=False)
        monkeypatch.delenv("OLLAMA_USE_CLOUD", raising=False)
        monkeypatch.setenv("OLLAMA_API_KEY", "sk-test")
        # Custom URL that's neither local nor cloud
        assert ollama_prefers_cloud(base_url="http://custom-ollama:11434") is False


# ---------------------------------------------------------------------------
# resolve_ollama_base_url
# ---------------------------------------------------------------------------


class TestResolveOllamaBaseUrl:
    def test_explicit_url_wins(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        result = resolve_ollama_base_url(base_url="http://my-server:11434")
        assert result == "http://my-server:11434"

    def test_defaults_to_local(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_FORCE_LOCAL", raising=False)
        monkeypatch.delenv("OLLAMA_USE_CLOUD", raising=False)
        result = resolve_ollama_base_url()
        assert result == OLLAMA_LOCAL_BASE_URL

    def test_cloud_when_api_key(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        monkeypatch.delenv("OLLAMA_FORCE_LOCAL", raising=False)
        monkeypatch.delenv("OLLAMA_USE_CLOUD", raising=False)
        monkeypatch.setenv("OLLAMA_API_KEY", "sk-test")
        result = resolve_ollama_base_url()
        assert result == OLLAMA_CLOUD_BASE_URL

    def test_env_base_url_used(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://remote:11434")
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_FORCE_LOCAL", raising=False)
        monkeypatch.delenv("OLLAMA_USE_CLOUD", raising=False)
        result = resolve_ollama_base_url()
        assert result == "http://remote:11434"


# ---------------------------------------------------------------------------
# ollama_transport_mode
# ---------------------------------------------------------------------------


class TestOllamaTransportMode:
    def test_local_mode(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_FORCE_LOCAL", raising=False)
        monkeypatch.delenv("OLLAMA_USE_CLOUD", raising=False)
        assert ollama_transport_mode() == "local_api"

    def test_cloud_mode(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        monkeypatch.delenv("OLLAMA_FORCE_LOCAL", raising=False)
        monkeypatch.delenv("OLLAMA_USE_CLOUD", raising=False)
        monkeypatch.setenv("OLLAMA_API_KEY", "sk-test")
        assert ollama_transport_mode() == "cloud_api"

    def test_explicit_cloud_url(self):
        assert ollama_transport_mode(base_url="https://ollama.com") == "cloud_api"

    def test_explicit_local_url(self):
        assert ollama_transport_mode(base_url="http://localhost:11434") == "local_api"


# ---------------------------------------------------------------------------
# resolve_ollama_model
# ---------------------------------------------------------------------------


class TestResolveOllamaModel:
    def test_explicit_model(self):
        assert resolve_ollama_model("mistral") == "mistral"

    def test_explicit_model_stripped(self):
        assert resolve_ollama_model("  mistral  ") == "mistral"

    def test_env_model(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_MODEL", "phi3")
        assert resolve_ollama_model() == "phi3"

    def test_default_local_model(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_FORCE_LOCAL", raising=False)
        monkeypatch.delenv("OLLAMA_USE_CLOUD", raising=False)
        assert resolve_ollama_model() == OLLAMA_DEFAULT_LOCAL_MODEL

    def test_default_cloud_model(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        monkeypatch.delenv("OLLAMA_FORCE_LOCAL", raising=False)
        monkeypatch.delenv("OLLAMA_USE_CLOUD", raising=False)
        monkeypatch.setenv("OLLAMA_API_KEY", "sk-test")
        assert resolve_ollama_model() == OLLAMA_DEFAULT_CLOUD_MODEL

    def test_none_model(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_FORCE_LOCAL", raising=False)
        monkeypatch.delenv("OLLAMA_USE_CLOUD", raising=False)
        result = resolve_ollama_model(None)
        assert result == OLLAMA_DEFAULT_LOCAL_MODEL


# ---------------------------------------------------------------------------
# build_ollama_headers
# ---------------------------------------------------------------------------


class TestBuildOllamaHeaders:
    def test_local_returns_empty(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        monkeypatch.delenv("OLLAMA_FORCE_LOCAL", raising=False)
        monkeypatch.delenv("OLLAMA_USE_CLOUD", raising=False)
        headers = build_ollama_headers()
        assert headers == {}

    def test_cloud_with_key(self):
        headers = build_ollama_headers(
            base_url="https://ollama.com",
            api_key="sk-my-token",
        )
        assert headers == {"Authorization": "Bearer sk-my-token"}

    def test_cloud_env_key(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_API_KEY", "sk-env-token")
        headers = build_ollama_headers(base_url="https://ollama.com")
        assert headers["Authorization"] == "Bearer sk-env-token"

    def test_cloud_no_key_raises(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="OLLAMA_API_KEY not set"):
            build_ollama_headers(base_url="https://ollama.com")

    def test_explicit_key_overrides_env(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_API_KEY", "sk-env")
        headers = build_ollama_headers(
            base_url="https://ollama.com",
            api_key="sk-explicit",
        )
        assert headers["Authorization"] == "Bearer sk-explicit"
