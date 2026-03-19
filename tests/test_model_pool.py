from dharma_swarm import model_pool
from dharma_swarm.model_pool import (
    get_model,
    get_pool_models,
    model_profile,
    resolve_top10,
    update_model_profile,
)


def test_model_pool_resolves_alias_to_gpt_54():
    model = get_model("codex-5.4")
    assert model is not None
    assert model.id == "gpt-5.4"


def test_model_pool_top10_starts_with_curated_order():
    top = resolve_top10(live=False)
    assert top[0]["id"] == "claude-opus-4-6"
    assert top[1]["id"] == "gpt-5.4"


def test_model_pool_search_finds_gemini_pro():
    results = get_pool_models(search="gemini-2.5-pro", limit=10)
    assert any(model["id"] == "google/gemini-2.5-pro" for model in results)


def test_model_profile_override_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(model_pool, "_MODEL_PROFILE_PATH", tmp_path / "profiles.json")

    saved = update_model_profile(
        "gpt-5.4",
        custom_label="OpenAI Prime",
        short_name="Prime",
    )

    assert saved["ui_label"] == "OpenAI Prime"
    assert saved["short_name"] == "Prime"

    loaded = model_profile("gpt-5.4")
    assert loaded["custom_label"] == "OpenAI Prime"
    assert loaded["short_name"] == "Prime"
