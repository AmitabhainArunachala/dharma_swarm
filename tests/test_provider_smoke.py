from __future__ import annotations

from dharma_swarm.provider_smoke import run_provider_smoke, strongest_ollama_model


def test_strongest_ollama_model_prefers_largest_model_size() -> None:
    models = ["llama3.2:3b", "qwen2.5:14b", "gpt-oss:120b", "nemotron-mini:4b"]
    assert strongest_ollama_model(models) == "gpt-oss:120b"


def test_run_provider_smoke_reports_success_with_monkeypatched_probes(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_API_KEY", "test-ollama-key")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setattr(
        "dharma_swarm.provider_smoke.list_ollama_manifest_models",
        lambda base_dir=None: ["llama3.2:3b", "gpt-oss:120b"],
    )

    async def _fake_ollama(model: str):
        return {"status": "ok", "model": model, "response_preview": "OK", "usage": {}}

    async def _fake_nim(model: str):
        return {
            "status": "ok",
            "model": model,
            "response_preview": "OK",
            "usage": {},
            "base_url": "https://nim.local/v1",
        }

    async def _fake_openrouter(model: str):
        return {
            "status": "ok",
            "model": model,
            "response_preview": "OK",
            "usage": {},
        }

    monkeypatch.setattr("dharma_swarm.provider_smoke._probe_ollama", _fake_ollama)
    monkeypatch.setattr("dharma_swarm.provider_smoke._probe_nim", _fake_nim)
    monkeypatch.setattr("dharma_swarm.provider_smoke._probe_openrouter", _fake_openrouter)

    payload = run_provider_smoke()

    assert payload["ollama"]["configured_base_url"] == "https://ollama.com"
    assert payload["ollama"]["transport_mode"] == "cloud_api"
    assert payload["ollama"]["strongest_installed"] is None
    assert payload["ollama"]["status"] == "ok"
    assert "kimi-k2.5:cloud" in payload["ollama"]["catalog_models"]
    assert payload["nvidia_nim"]["status"] == "ok"
    assert payload["nvidia_nim"]["deployment_mode"] == "hosted_api"
    assert "moonshotai/kimi-k2.5" in payload["nvidia_nim"]["catalog_models"]["self_hosted"]
    assert payload["nvidia_nim"]["strongest_verified"]
    assert payload["openrouter"]["status"] == "ok"
    assert payload["openrouter"]["strongest_verified"]
