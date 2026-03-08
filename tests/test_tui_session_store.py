"""Tests for TUI session store helpers."""

from __future__ import annotations

from pathlib import Path

from dharma_swarm.tui.engine.session_store import SessionStore


def test_session_store_list_and_latest_filters(tmp_path):
    store = SessionStore(root=tmp_path)
    s1 = store.create_session(
        session_id="s1",
        provider_id="claude",
        model_id="claude-sonnet-4-5",
        cwd="/repo/a",
        provider_session_id="prov-1",
    )
    s2 = store.create_session(
        session_id="s2",
        provider_id="claude",
        model_id="claude-sonnet-4-5",
        cwd="/repo/b",
        provider_session_id="prov-2",
    )
    s3 = store.create_session(
        session_id="s3",
        provider_id="openai",
        model_id="gpt-5",
        cwd="/repo/a",
        provider_session_id="prov-3",
    )
    assert s1 == "s1"
    assert s2 == "s2"
    assert s3 == "s3"

    # Touch s1 after s3 so it's latest within (/repo/a, claude).
    store.set_provider_session_id("s1", "prov-1b")

    sessions = store.list_sessions()
    assert len(sessions) == 3

    latest = store.latest_session(cwd="/repo/a", provider_id="claude")
    assert latest is not None
    assert latest["session_id"] == "s1"
    assert latest["provider_session_id"] == "prov-1b"


def test_session_store_latest_returns_none_when_no_match(tmp_path):
    store = SessionStore(root=tmp_path)
    store.create_session(
        session_id="s1",
        provider_id="claude",
        model_id="claude-sonnet-4-5",
        cwd="/repo/a",
    )
    latest = store.latest_session(cwd="/repo/z", provider_id="claude")
    assert latest is None


def test_session_store_latest_respects_min_turns(tmp_path):
    store = SessionStore(root=tmp_path)
    store.create_session(
        session_id="s1",
        provider_id="claude",
        model_id="claude-sonnet-4-5",
        cwd="/repo/a",
    )
    store.create_session(
        session_id="s2",
        provider_id="claude",
        model_id="claude-sonnet-4-5",
        cwd="/repo/a",
    )
    # Make s2 the latest but trivial (1 turn), s1 meaningful (3 turns).
    m1 = store.load_meta("s1")
    m1["total_turns"] = 3
    store._write_meta("s1", m1)  # test-only use of helper
    m2 = store.load_meta("s2")
    m2["total_turns"] = 1
    store._write_meta("s2", m2)  # test-only use of helper
    # Touch s2 timestamp to ensure it would win without min_turns.
    store.set_provider_session_id("s2", "prov-s2")

    latest_any = store.latest_session(cwd="/repo/a", provider_id="claude")
    assert latest_any is not None
    assert latest_any["session_id"] == "s2"

    latest_meaningful = store.latest_session(
        cwd="/repo/a",
        provider_id="claude",
        min_turns=2,
    )
    assert latest_meaningful is not None
    assert latest_meaningful["session_id"] == "s1"


def test_session_store_latest_matches_path_equivalence(tmp_path):
    store = SessionStore(root=tmp_path)
    canonical = str((tmp_path / "repo").resolve())
    alias = str(Path(canonical) / "." / "subdir" / "..")
    store.create_session(
        session_id="s1",
        provider_id="claude",
        model_id="claude-sonnet-4-5",
        cwd=canonical,
        provider_session_id="prov-1",
    )

    latest = store.latest_session(cwd=alias, provider_id="claude")
    assert latest is not None
    assert latest["session_id"] == "s1"
