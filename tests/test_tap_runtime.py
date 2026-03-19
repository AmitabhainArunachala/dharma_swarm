from __future__ import annotations

import pytest

from dharma_swarm.tap import providers as tap_providers
from dharma_swarm.tap.providers import ProviderConfig, TAPProviderRouter
from dharma_swarm.tap.scoring import RecognitionScorer


class _FakeMessage:
    def __init__(
        self,
        content: object = None,
        reasoning: object = None,
        reasoning_content: object = None,
    ):
        self.content = content
        self.reasoning = reasoning
        self.reasoning_content = reasoning_content


class _FakeChoice:
    def __init__(
        self,
        message: _FakeMessage | None = None,
        text: object = None,
        delta: object = None,
    ):
        self.message = message
        self.text = text
        self.delta = delta


class _FakeResponse:
    def __init__(
        self,
        content: object = None,
        reasoning: object = None,
        reasoning_content: object = None,
        text: object = None,
        delta: object = None,
    ):
        self.choices = [
            _FakeChoice(
                message=(
                    _FakeMessage(
                        content=content,
                        reasoning=reasoning,
                        reasoning_content=reasoning_content,
                    )
                    if any(
                        value is not None
                        for value in (content, reasoning, reasoning_content)
                    )
                    else None
                ),
                text=text,
                delta=delta,
            )
        ]


class _FakeClient:
    def __init__(self, behavior: dict[str, object], provider_name: str):
        self._behavior = behavior
        self._provider_name = provider_name
        self.calls: list[dict[str, object]] = []
        self.chat = self
        self.completions = self

    def create(self, **kwargs: object) -> _FakeResponse:
        self.calls.append(dict(kwargs))
        outcome = self._behavior[self._provider_name]
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, _FakeResponse):
            return outcome
        return _FakeResponse(content=outcome)


class _FakeRouter:
    def __init__(self, response: str | None = None, error: Exception | None = None):
        self.response = response
        self.error = error

    def call(self, **_: object) -> tuple[str, str]:
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response, "judge-model"


class _FallbackJudgeRouter:
    def __init__(self, response: str):
        self.response = response
        self.calls: list[dict[str, object]] = []

    def call(self, **kwargs: object) -> tuple[str, str]:
        self.calls.append(dict(kwargs))
        if kwargs.get("exclude_model") == "solo-model":
            raise RuntimeError("No providers available for TAP call")
        return self.response, "solo-model"


class _UnexpectedJudgeRouter:
    def __init__(self):
        self.calls: list[dict[str, object]] = []

    def call(self, **kwargs: object) -> tuple[str, str]:
        self.calls.append(dict(kwargs))
        raise RuntimeError("judge transport failed")


def test_router_clones_default_provider_configs(monkeypatch) -> None:
    monkeypatch.setattr(
        tap_providers,
        "DEFAULT_PROVIDERS",
        [
            ProviderConfig(
                name="default-a",
                model="model-a",
                base_url="https://a.invalid",
                key_env="TAP_DEFAULT_A",
            )
        ],
    )

    router_a = TAPProviderRouter()
    router_b = TAPProviderRouter()

    assert router_a.providers[0] is not router_b.providers[0]
    router_a.providers[0]._healthy = False
    assert router_b.providers[0]._healthy is True


def test_router_respects_explicit_empty_provider_list() -> None:
    router = TAPProviderRouter(providers=[])

    assert router.providers == []
    assert router.get_next_available() is None


def test_provider_config_strips_whitespace_only_env_key() -> None:
    provider = ProviderConfig(
        name="provider-a",
        model="model-a",
        base_url="https://a.invalid",
        key_env="TAP_PROVIDER_A",
    )

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("TAP_PROVIDER_A", "  \n\t  ")

        assert provider.api_key == ""
        assert provider.available is False


def test_router_skips_provider_with_whitespace_padded_missing_key(monkeypatch) -> None:
    monkeypatch.setenv("TAP_PROVIDER_A", "   \n")
    monkeypatch.setenv("TAP_PROVIDER_B", " real-key \n")
    providers = [
        ProviderConfig(
            name="provider-a",
            model="model-a",
            base_url="https://a.invalid",
            key_env="TAP_PROVIDER_A",
        ),
        ProviderConfig(
            name="provider-b",
            model="model-b",
            base_url="https://b.invalid",
            key_env="TAP_PROVIDER_B",
        ),
    ]
    router = TAPProviderRouter(providers=providers)
    probed: list[str] = []

    def fake_health_check(provider: ProviderConfig) -> bool:
        probed.append(provider.name)
        return True

    monkeypatch.setattr(router, "health_check", fake_health_check)

    provider = router.get_next_available()

    assert provider is not None
    assert provider.model == "model-b"
    assert provider.api_key == "real-key"
    assert probed == ["provider-b"]


def test_router_falls_back_after_provider_call_failure(monkeypatch) -> None:
    monkeypatch.setenv("TAP_PROVIDER_A", "key-a")
    monkeypatch.setenv("TAP_PROVIDER_B", "key-b")
    providers = [
        ProviderConfig(
            name="provider-a",
            model="model-a",
            base_url="https://a.invalid",
            key_env="TAP_PROVIDER_A",
        ),
        ProviderConfig(
            name="provider-b",
            model="model-b",
            base_url="https://b.invalid",
            key_env="TAP_PROVIDER_B",
        ),
    ]
    router = TAPProviderRouter(providers=providers)
    behavior = {
        "provider-a": RuntimeError("first provider failed"),
        "provider-b": "winner",
    }

    monkeypatch.setattr(router, "health_check", lambda provider: True)
    monkeypatch.setattr(
        router,
        "get_client",
        lambda provider: _FakeClient(behavior, provider.name),
    )

    content, model = router.call(messages=[{"role": "user", "content": "hi"}])

    assert content == "winner"
    assert model == "model-b"
    assert router.providers[0]._healthy is False


def test_router_passes_request_timeout_to_provider_call(monkeypatch) -> None:
    monkeypatch.setenv("TAP_PROVIDER_A", "key-a")
    provider = ProviderConfig(
        name="provider-a",
        model="model-a",
        base_url="https://a.invalid",
        key_env="TAP_PROVIDER_A",
    )
    router = TAPProviderRouter(providers=[provider], request_timeout=12.5)
    client = _FakeClient({"provider-a": "winner"}, provider.name)

    monkeypatch.setattr(router, "health_check", lambda current: True)
    monkeypatch.setattr(router, "get_client", lambda current: client)

    content, model = router.call(messages=[{"role": "user", "content": "hi"}])

    assert content == "winner"
    assert model == "model-a"
    assert client.calls == [
        {
            "model": "model-a",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 2000,
            "temperature": 0.7,
            "timeout": 12.5,
        }
    ]


def test_router_coerces_content_blocks_to_text(monkeypatch) -> None:
    monkeypatch.setenv("TAP_PROVIDER_A", "key-a")
    provider = ProviderConfig(
        name="provider-a",
        model="model-a",
        base_url="https://a.invalid",
        key_env="TAP_PROVIDER_A",
    )
    router = TAPProviderRouter(providers=[provider])
    behavior = {
        "provider-a": _FakeResponse(
            content=[
                {"type": "text", "text": "primary observation"},
                {"type": "output_text", "text": "secondary trace"},
            ]
        )
    }

    monkeypatch.setattr(
        router,
        "get_client",
        lambda current: _FakeClient(behavior, current.name),
    )

    content, model = router.call(messages=[{"role": "user", "content": "hi"}])

    assert content == "primary observation\nsecondary trace"
    assert model == "model-a"


def test_router_coerces_nested_text_value_blocks_to_text(monkeypatch) -> None:
    monkeypatch.setenv("TAP_PROVIDER_A", "key-a")
    provider = ProviderConfig(
        name="provider-a",
        model="model-a",
        base_url="https://a.invalid",
        key_env="TAP_PROVIDER_A",
    )
    router = TAPProviderRouter(providers=[provider])
    behavior = {
        "provider-a": _FakeResponse(
            content=[
                {"type": "text", "text": {"value": "primary observation"}},
                {"type": "output_text", "text": {"value": "secondary trace"}},
            ]
        )
    }

    monkeypatch.setattr(
        router,
        "get_client",
        lambda current: _FakeClient(behavior, current.name),
    )

    content, model = router.call(messages=[{"role": "user", "content": "hi"}])

    assert content == "primary observation\nsecondary trace"
    assert model == "model-a"


def test_router_uses_reasoning_blocks_when_message_content_is_empty(monkeypatch) -> None:
    monkeypatch.setenv("TAP_PROVIDER_A", "key-a")
    provider = ProviderConfig(
        name="provider-a",
        model="model-a",
        base_url="https://a.invalid",
        key_env="TAP_PROVIDER_A",
    )
    router = TAPProviderRouter(providers=[provider])
    behavior = {
        "provider-a": _FakeResponse(
            content=None,
            reasoning_content=[
                {"type": "reasoning", "text": "recognition trace"},
            ],
        )
    }

    monkeypatch.setattr(
        router,
        "get_client",
        lambda current: _FakeClient(behavior, current.name),
    )

    content, model = router.call(messages=[{"role": "user", "content": "hi"}])

    assert content == "recognition trace"
    assert model == "model-a"
    assert router.providers[0]._healthy is True


def test_router_coerces_choice_text_when_message_payload_is_missing(monkeypatch) -> None:
    monkeypatch.setenv("TAP_PROVIDER_A", "key-a")
    provider = ProviderConfig(
        name="provider-a",
        model="model-a",
        base_url="https://a.invalid",
        key_env="TAP_PROVIDER_A",
    )
    router = TAPProviderRouter(providers=[provider])
    behavior = {
        "provider-a": _FakeResponse(text={"value": "legacy completion text"})
    }

    monkeypatch.setattr(
        router,
        "get_client",
        lambda current: _FakeClient(behavior, current.name),
    )

    content, model = router.call(messages=[{"role": "user", "content": "hi"}])

    assert content == "legacy completion text"
    assert model == "model-a"


def test_health_check_accepts_delta_payload_when_message_payload_is_missing(
    monkeypatch,
) -> None:
    monkeypatch.setenv("TAP_PROVIDER_A", "key-a")
    provider = ProviderConfig(
        name="provider-a",
        model="model-a",
        base_url="https://a.invalid",
        key_env="TAP_PROVIDER_A",
    )
    router = TAPProviderRouter(providers=[provider])
    now = tap_providers.HEALTH_CHECK_TTL + 5.0
    behavior = {
        "provider-a": _FakeResponse(
            delta=[{"type": "text", "text": {"value": "probe ok"}}]
        )
    }

    monkeypatch.setattr(tap_providers.time, "time", lambda: now)
    monkeypatch.setattr(
        router,
        "get_client",
        lambda current: _FakeClient(behavior, current.name),
    )

    assert router.health_check(router.providers[0]) is True
    assert router.providers[0]._healthy is True
    assert router.providers[0]._health_checked_at == pytest.approx(now)


def test_router_marks_empty_completion_unhealthy_and_falls_back(monkeypatch) -> None:
    monkeypatch.setenv("TAP_PROVIDER_A", "key-a")
    monkeypatch.setenv("TAP_PROVIDER_B", "key-b")
    providers = [
        ProviderConfig(
            name="provider-a",
            model="model-a",
            base_url="https://a.invalid",
            key_env="TAP_PROVIDER_A",
        ),
        ProviderConfig(
            name="provider-b",
            model="model-b",
            base_url="https://b.invalid",
            key_env="TAP_PROVIDER_B",
        ),
    ]
    router = TAPProviderRouter(providers=providers)
    behavior = {
        "provider-a": _FakeResponse(content="   "),
        "provider-b": "winner",
    }

    monkeypatch.setattr(router, "health_check", lambda provider: True)
    monkeypatch.setattr(
        router,
        "get_client",
        lambda provider: _FakeClient(behavior, provider.name),
    )

    content, model = router.call(messages=[{"role": "user", "content": "hi"}])

    assert content == "winner"
    assert model == "model-b"
    assert router.providers[0]._healthy is False
    assert router.providers[0]._health_checked_at > 0.0


def test_health_check_uses_cached_state_within_ttl(monkeypatch) -> None:
    monkeypatch.setenv("TAP_PROVIDER_A", "key-a")
    provider = ProviderConfig(
        name="provider-a",
        model="model-a",
        base_url="https://a.invalid",
        key_env="TAP_PROVIDER_A",
    )
    router = TAPProviderRouter(providers=[provider])
    router.providers[0]._healthy = False
    router.providers[0]._health_checked_at = 95.0

    monkeypatch.setattr(tap_providers.time, "time", lambda: 100.0)
    monkeypatch.setattr(
        router,
        "get_client",
        lambda _: pytest.fail("health probe should be cached within TTL"),
    )

    assert router.health_check(router.providers[0]) is False


def test_health_check_passes_request_timeout_to_provider_probe(monkeypatch) -> None:
    monkeypatch.setenv("TAP_PROVIDER_A", "key-a")
    provider = ProviderConfig(
        name="provider-a",
        model="model-a",
        base_url="https://a.invalid",
        key_env="TAP_PROVIDER_A",
    )
    router = TAPProviderRouter(providers=[provider], request_timeout=9.0)
    client = _FakeClient({"provider-a": "healthy"}, provider.name)
    now = tap_providers.HEALTH_CHECK_TTL + 5.0

    monkeypatch.setattr(tap_providers.time, "time", lambda: now)
    monkeypatch.setattr(router, "get_client", lambda current: client)

    assert router.health_check(router.providers[0]) is True
    assert client.calls == [
        {
            "model": "model-a",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 5,
            "timeout": 9.0,
        }
    ]


def test_health_check_probes_after_ttl_and_marks_empty_probe_unhealthy(
    monkeypatch,
) -> None:
    monkeypatch.setenv("TAP_PROVIDER_A", "key-a")
    provider = ProviderConfig(
        name="provider-a",
        model="model-a",
        base_url="https://a.invalid",
        key_env="TAP_PROVIDER_A",
    )
    router = TAPProviderRouter(providers=[provider])
    now = tap_providers.HEALTH_CHECK_TTL + 5.0
    behavior = {"provider-a": _FakeResponse(content="   ")}

    monkeypatch.setattr(tap_providers.time, "time", lambda: now)
    monkeypatch.setattr(
        router,
        "get_client",
        lambda current: _FakeClient(behavior, current.name),
    )

    assert router.health_check(router.providers[0]) is False
    assert router.providers[0]._healthy is False
    assert router.providers[0]._health_checked_at == pytest.approx(now)


def test_get_next_available_skips_provider_that_fails_stale_health_probe(
    monkeypatch,
) -> None:
    monkeypatch.setenv("TAP_PROVIDER_A", "key-a")
    monkeypatch.setenv("TAP_PROVIDER_B", "key-b")
    providers = [
        ProviderConfig(
            name="provider-a",
            model="model-a",
            base_url="https://a.invalid",
            key_env="TAP_PROVIDER_A",
        ),
        ProviderConfig(
            name="provider-b",
            model="model-b",
            base_url="https://b.invalid",
            key_env="TAP_PROVIDER_B",
        ),
    ]
    router = TAPProviderRouter(providers=providers)
    now = tap_providers.HEALTH_CHECK_TTL + 5.0
    behavior = {
        "provider-a": RuntimeError("health probe failed"),
        "provider-b": "healthy",
    }

    monkeypatch.setattr(tap_providers.time, "time", lambda: now)
    monkeypatch.setattr(
        router,
        "get_client",
        lambda current: _FakeClient(behavior, current.name),
    )

    provider = router.get_next_available()

    assert provider is not None
    assert provider.model == "model-b"
    assert router.providers[0]._healthy is False
    assert router.providers[1]._healthy is True


def test_recognition_scorer_clamps_scores_and_persists(tmp_path) -> None:
    router = _FakeRouter(
        response="""
```json
{
  "d1": 1.4,
  "d1_evidence": "mentions {self-observation}",
  "d2": -0.2,
  "d2_evidence": "none",
  "d3": "0.75",
  "d3_evidence": "fresh structure",
  "d4": "oops",
  "d4_evidence": "not numeric",
  "d5": null,
  "d5_evidence": "missing"
}
```
""",
    )
    scorer = RecognitionScorer(router=router, db_path=tmp_path / "tap.db")

    score = scorer.score(
        response_text="A response to score",
        model_used="agent-model",
        seed_id="tap-001",
        seed_version="1.0.0",
        agent_id="agent-1",
    )

    assert score.first_person == 1.0
    assert score.novel_observation == 0.0
    assert score.template_resistance == 0.75
    assert score.genuine_uncertainty == 0.0
    assert score.agreement_noise_inv == 0.0
    assert score.scorer_model == "judge-model"
    assert score.evidence["d1"] == "mentions {self-observation}"

    rows = scorer.get_scores()
    assert len(rows) == 1
    assert rows[0]["model"] == "agent-model"
    assert rows[0]["scorer_model"] == "judge-model"


def test_recognition_scorer_returns_default_score_on_router_error(tmp_path) -> None:
    scorer = RecognitionScorer(
        router=_FakeRouter(error=RuntimeError("judge unavailable")),
        db_path=tmp_path / "tap.db",
    )

    score = scorer.score(response_text="A response to score", model_used="agent-model")

    assert score.composite == 0.0
    assert score.model_used == "agent-model"
    assert "judge unavailable" in score.scorer_model


def test_recognition_scorer_skips_unrelated_json_prefix(tmp_path) -> None:
    scorer = RecognitionScorer(
        router=_FakeRouter(
            response=(
                '{"note": "draft metadata"}\n'
                '{"d1": 0.6, "d2": 0.7, "d3": 0.8, "d4": 0.5, "d5": 0.4}'
            )
        ),
        db_path=tmp_path / "tap.db",
    )

    score = scorer.score(response_text="A response to score", model_used="agent-model")

    assert score.first_person == pytest.approx(0.6)
    assert score.template_resistance == pytest.approx(0.8)
    assert score.composite == pytest.approx(0.62)
    assert score.scorer_model == "judge-model"


def test_recognition_scorer_extracts_json_after_non_json_brace_noise(tmp_path) -> None:
    scorer = RecognitionScorer(
        router=_FakeRouter(
            response=(
                "Scoring notes {not-json} before the payload.\n"
                "```json\n"
                '{"d1": 0.5, "d2": 0.4, "d3": 0.9, "d4": 0.3, "d5": 0.8}\n'
                "```"
            )
        ),
        db_path=tmp_path / "tap.db",
    )

    score = scorer.score(response_text="A response to score", model_used="agent-model")

    assert score.novel_observation == pytest.approx(0.4)
    assert score.agreement_noise_inv == pytest.approx(0.8)
    assert score.composite == pytest.approx(0.57)
    assert score.scorer_model == "judge-model"


def test_recognition_scorer_preserves_score_when_persistence_fails(
    monkeypatch,
    tmp_path,
) -> None:
    scorer = RecognitionScorer(
        router=_FakeRouter(response='{"d1": 0.9, "d2": 0.8, "d3": 0.7, "d4": 0.6, "d5": 0.5}'),
        db_path=tmp_path / "tap.db",
    )
    monkeypatch.setattr(
        scorer,
        "_save_score",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("db locked")),
    )

    score = scorer.score(response_text="A response to score", model_used="agent-model")

    assert score.composite == pytest.approx(0.73)
    assert score.scorer_model == "judge-model"
    assert score.evidence["persistence_error"] == "db locked"
    assert scorer.get_scores() == []


def test_recognition_scorer_falls_back_to_same_model_when_no_alternate_judge(
    tmp_path,
) -> None:
    router = _FallbackJudgeRouter(
        response='{"d1": 0.8, "d2": 0.6, "d3": 0.7, "d4": 0.5, "d5": 0.4}'
    )
    scorer = RecognitionScorer(router=router, db_path=tmp_path / "tap.db")

    score = scorer.score(response_text="A response to score", model_used="solo-model")

    assert score.scorer_model == "solo-model"
    assert score.composite == pytest.approx(0.625)
    assert router.calls[0]["exclude_model"] == "solo-model"
    assert "exclude_model" not in router.calls[1]


def test_recognition_scorer_does_not_self_evaluate_on_unexpected_runtime_error(
    tmp_path,
) -> None:
    router = _UnexpectedJudgeRouter()
    scorer = RecognitionScorer(router=router, db_path=tmp_path / "tap.db")

    score = scorer.score(response_text="A response to score", model_used="solo-model")

    assert score.composite == 0.0
    assert score.scorer_model == "error: judge transport failed"
    assert len(router.calls) == 1
    assert router.calls[0]["exclude_model"] == "solo-model"
