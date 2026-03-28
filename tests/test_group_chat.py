"""Tests for dharma_swarm.group_chat -- multi-agent group discussion."""

from __future__ import annotations

import pytest

from dharma_swarm.group_chat import ChatMessage, GroupChat, GroupChatConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_provider(responses: dict[str, str] | None = None):
    """Return an async provider_fn that echoes back the participant name.

    If *responses* is given, returns the mapped string for each participant
    whose name appears in the user_prompt.  Falls back to a generic echo.
    """
    call_log: list[tuple[str, str]] = []

    async def provider_fn(system_prompt: str, user_prompt: str) -> str:
        call_log.append((system_prompt, user_prompt))
        if responses:
            for name, text in responses.items():
                if name in system_prompt:
                    return text
        # Default: echo the participant name from the system prompt
        return f"Response from provider ({len(call_log)})"

    provider_fn.call_log = call_log  # type: ignore[attr-defined]
    return provider_fn


# ---------------------------------------------------------------------------
# ChatMessage
# ---------------------------------------------------------------------------


def test_chat_message_creation():
    msg = ChatMessage(speaker="Alice", content="Hello", round_num=1, timestamp=100.0)
    assert msg.speaker == "Alice"
    assert msg.content == "Hello"
    assert msg.round_num == 1
    assert msg.timestamp == 100.0


def test_chat_message_default_timestamp():
    msg = ChatMessage(speaker="Bob", content="Hi", round_num=2)
    assert msg.timestamp > 0


# ---------------------------------------------------------------------------
# GroupChatConfig
# ---------------------------------------------------------------------------


def test_config_defaults():
    cfg = GroupChatConfig()
    assert cfg.max_rounds == 5
    assert cfg.max_tokens_per_turn == 2000
    assert cfg.moderator_name is None


def test_config_custom():
    cfg = GroupChatConfig(max_rounds=3, max_tokens_per_turn=500, moderator_name="Mod")
    assert cfg.max_rounds == 3
    assert cfg.moderator_name == "Mod"


# ---------------------------------------------------------------------------
# GroupChat construction
# ---------------------------------------------------------------------------


def test_empty_participants_raises():
    with pytest.raises(ValueError, match="non-empty"):
        GroupChat(participants=[], config=GroupChatConfig(), provider_fn=_make_provider())


# ---------------------------------------------------------------------------
# GroupChat.run — basic
# ---------------------------------------------------------------------------


async def test_run_chat_basic():
    provider = _make_provider()
    chat = GroupChat(
        participants=["Alice", "Bob"],
        config=GroupChatConfig(max_rounds=2),
        provider_fn=provider,
    )
    result = await chat.run("What is the meaning of life?")

    # 2 participants * 2 rounds = 4 messages
    assert len(result) == 4
    assert all(isinstance(m, ChatMessage) for m in result)
    # Round numbers are correct
    assert [m.round_num for m in result] == [1, 1, 2, 2]
    # Speakers alternate
    assert [m.speaker for m in result] == ["Alice", "Bob", "Alice", "Bob"]
    # Provider was called 4 times
    assert len(provider.call_log) == 4


# ---------------------------------------------------------------------------
# Moderator speaks last in each round
# ---------------------------------------------------------------------------


async def test_moderator_speaks_last():
    responses = {
        "Alice": "Alice's thought",
        "Bob": "Bob's thought",
        "Moderator": "Moderator synthesis",
    }
    provider = _make_provider(responses)
    chat = GroupChat(
        participants=["Alice", "Bob", "Moderator"],
        config=GroupChatConfig(max_rounds=2, moderator_name="Moderator"),
        provider_fn=provider,
    )
    result = await chat.run("Debate topic")

    # Each round: Alice, Bob, then Moderator = 3 per round, 2 rounds = 6
    assert len(result) == 6
    # Moderator is last in each round
    round_1 = [m for m in result if m.round_num == 1]
    round_2 = [m for m in result if m.round_num == 2]
    assert round_1[-1].speaker == "Moderator"
    assert round_2[-1].speaker == "Moderator"
    assert round_1[-1].content == "Moderator synthesis"


# ---------------------------------------------------------------------------
# History accumulation
# ---------------------------------------------------------------------------


async def test_history_accumulates():
    provider = _make_provider()
    chat = GroupChat(
        participants=["A", "B", "C"],
        config=GroupChatConfig(max_rounds=3),
        provider_fn=provider,
    )
    await chat.run("Topic")

    # 3 participants * 3 rounds = 9
    assert len(chat.history) == 9
    # Second run should clear and restart
    await chat.run("New topic")
    assert len(chat.history) == 9  # fresh, not 18


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


async def test_to_dict():
    provider = _make_provider()
    chat = GroupChat(
        participants=["X", "Y"],
        config=GroupChatConfig(max_rounds=1),
        provider_fn=provider,
    )
    await chat.run("Serialize me")
    d = chat.to_dict()

    assert d["participants"] == ["X", "Y"]
    assert d["config"]["max_rounds"] == 1
    assert d["config"]["moderator_name"] is None
    assert d["total_messages"] == 2
    assert len(d["messages"]) == 2
    assert d["messages"][0]["speaker"] == "X"


# ---------------------------------------------------------------------------
# Summarize
# ---------------------------------------------------------------------------


def test_summarize_empty():
    chat = GroupChat(
        participants=["A"],
        config=GroupChatConfig(),
        provider_fn=_make_provider(),
    )
    assert chat.summarize() == "No discussion has taken place."


async def test_summarize_with_history():
    provider = _make_provider()
    chat = GroupChat(
        participants=["A", "B"],
        config=GroupChatConfig(max_rounds=1),
        provider_fn=provider,
    )
    await chat.run("Topic")
    summary = chat.summarize()
    assert "Round 1" in summary
    assert "[A]:" in summary
    assert "[B]:" in summary


# ---------------------------------------------------------------------------
# Provider error resilience
# ---------------------------------------------------------------------------


async def test_provider_error_resilience():
    """When the provider raises, the chat continues with an error message."""

    call_count = 0

    async def failing_provider(system: str, user: str) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("LLM down")
        return "OK"

    chat = GroupChat(
        participants=["A", "B"],
        config=GroupChatConfig(max_rounds=1),
        provider_fn=failing_provider,
    )
    result = await chat.run("Test")
    assert len(result) == 2
    assert "provider error" in result[0].content.lower()
    assert result[1].content == "OK"
