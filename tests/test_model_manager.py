"""Tests for model manager shortcut resolution."""

from __future__ import annotations

import json

import dharma_swarm.model_manager as model_manager


def test_resolve_model_request_claude_prefers_existing_46_config(
    monkeypatch,
    tmp_path,
) -> None:
    config_path = tmp_path / ".claude" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({"model": "claude-opus-4-6"}), encoding="utf-8")
    monkeypatch.setattr(model_manager.Path, "home", lambda: tmp_path)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("CLAUDE_MODEL", raising=False)
    monkeypatch.delenv("DGC_CLAUDE_DEFAULT_MODEL", raising=False)

    model, note = model_manager.resolve_model_request("claude")

    assert model is not None
    assert model.id == "claude-opus-4-6"
    assert note is not None
    assert "claude-opus-4-6" in note


def test_switch_model_claude_defaults_to_sonnet_46_when_unset(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(model_manager.Path, "home", lambda: tmp_path)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("CLAUDE_MODEL", raising=False)
    monkeypatch.delenv("DGC_CLAUDE_DEFAULT_MODEL", raising=False)

    success, message = model_manager.switch_model("claude")

    assert success is True
    assert "claude-sonnet-4-6" in message
    config_path = tmp_path / ".claude" / "config.json"
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["model"] == "claude-sonnet-4-6"


def test_get_model_info_accepts_46_alias_variants() -> None:
    assert model_manager.get_model_info("opus-4.6") is not None
    assert model_manager.get_model_info("sonnet 4.6") is not None
