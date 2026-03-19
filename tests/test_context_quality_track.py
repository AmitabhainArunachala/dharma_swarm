"""Additional quality-track tests for dharma_swarm.context."""

from __future__ import annotations

import builtins
import os
import sqlite3
from pathlib import Path

import pytest

import dharma_swarm.context as ctx


def test_read_vision_prefers_first_existing_path(tmp_path, monkeypatch):
    first = tmp_path / "missing.md"
    second = tmp_path / "present.md"
    second.write_text("VISION2")
    monkeypatch.setitem(ctx._VISION_FILES, "probe", [first, second])

    out = ctx.read_vision(keys=["probe"], max_per_file=100)
    assert "VISION2" in out
    assert "present.md" in out


def test_read_research_unknown_thread_skips_thread_specific_claude(monkeypatch):
    calls: list[str | None] = []

    def fake_read_file(path: Path, max_chars: int = 2000) -> str | None:
        calls.append(path.name)
        return f"{path.name}:{max_chars}"

    monkeypatch.setattr(ctx, "_read_file", fake_read_file)
    out = ctx.read_research(thread="unknown-thread", max_per_file=900)

    assert "# Research Layer" in out
    # Unknown thread currently skips thread-specific CLAUDE files.
    assert all(name.startswith("CLAUDE") is False for name in calls)


def test_read_ecosystem_domains_pass_through(monkeypatch):
    monkeypatch.setattr(
        "dharma_swarm.ecosystem_map.get_context_for",
        lambda d: f"CTX:{d}",
        raising=True,
    )
    assert ctx.read_ecosystem_domains("ops") == "CTX:ops"


def test_read_ecosystem_domains_import_error(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "dharma_swarm.ecosystem_map":
            raise ImportError("no map")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    try:
        assert ctx.read_ecosystem_domains("all") == ""
    finally:
        monkeypatch.setattr(builtins, "__import__", real_import)


def test_read_agni_state_marks_stale_priorities(tmp_path, monkeypatch):
    ws = tmp_path / "agni"
    ws.mkdir()
    (ws / "WORKING.md").write_text("work")
    p = ws / "PRIORITIES.md"
    p.write_text("prio")
    stale = 60 * 60 * 72  # 72h old
    os.utime(p, (p.stat().st_atime - stale, p.stat().st_mtime - stale))
    monkeypatch.setattr(ctx, "AGNI_WORKSPACE", ws)

    state = ctx.read_agni_state()
    assert state["working"] == "work"
    assert state["priorities_stale"] is True
    assert state["priorities_age_hours"] >= 48


def test_read_manifest_unreadable_json(tmp_path, monkeypatch):
    fake_home = tmp_path
    (fake_home / ".dharma_manifest.json").write_text("{bad json")
    monkeypatch.setattr(ctx, "HOME", fake_home)

    assert ctx.read_manifest() == "Manifest unreadable."


@pytest.mark.real_memory
def test_read_memory_context_returns_error_when_table_missing(tmp_path):
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    db_path = db_dir / "memory.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE other_table (x TEXT)")
    conn.commit()
    conn.close()

    out = ctx.read_memory_context(state_dir=tmp_path)
    assert out.startswith("Memory unavailable:")


def test_read_agent_notes_tail_and_role_exclusion(tmp_path, monkeypatch):
    shared = tmp_path / "shared"
    shared.mkdir()
    long_text = "A" * 1000
    (shared / "alpha_notes.md").write_text(long_text)
    (shared / "beta_notes.md").write_text("BETA")
    monkeypatch.setattr(ctx, "SHARED_DIR", shared)

    out = ctx.read_agent_notes(exclude_role="alpha", max_per_agent=10)
    assert "alpha" not in out.lower()
    assert "beta" in out.lower()


def test_build_agent_context_hard_cap_truncates(monkeypatch):
    huge = "X" * (ctx.CONTEXT_BUDGET // 2)
    monkeypatch.setattr(ctx, "read_vision", lambda **_: huge)
    monkeypatch.setattr(ctx, "read_research", lambda **_: huge)
    monkeypatch.setattr(ctx, "read_engineering", lambda: huge)
    monkeypatch.setattr(ctx, "read_ops", lambda *_, **__: huge)
    monkeypatch.setattr(ctx, "read_agent_notes", lambda **_: huge)
    monkeypatch.setitem(
        ctx.ROLE_PROFILES,
        "qa-hardcap",
        {
            "vision": ["ten_words"],
            "research_weight": 0.4,
            "engineering_weight": 0.4,
            "ops_weight": 0.4,
            "notes_weight": 0.4,
        },
    )

    out = ctx.build_agent_context(role="qa-hardcap", thread="mechanistic")
    assert len(out) <= ctx.CONTEXT_BUDGET + 60
    assert "context budget exceeded" in out


def test_build_agent_context_skips_small_weight_layers(monkeypatch):
    calls = {"research": 0, "eng": 0, "ops": 0, "notes": 0}

    monkeypatch.setattr(ctx, "read_vision", lambda **_: "VISION")
    monkeypatch.setattr(
        ctx,
        "read_research",
        lambda **_: calls.__setitem__("research", calls["research"] + 1) or "R",
    )
    monkeypatch.setattr(
        ctx,
        "read_engineering",
        lambda: calls.__setitem__("eng", calls["eng"] + 1) or "E",
    )
    monkeypatch.setattr(
        ctx,
        "read_ops",
        lambda *_args, **_kw: calls.__setitem__("ops", calls["ops"] + 1) or "O",
    )
    monkeypatch.setattr(
        ctx,
        "read_agent_notes",
        lambda **_: calls.__setitem__("notes", calls["notes"] + 1) or "N",
    )
    monkeypatch.setitem(
        ctx.ROLE_PROFILES,
        "qa-low",
        {
            "vision": ["ten_words"],
            "research_weight": 0.0,
            "engineering_weight": 0.0,
            "ops_weight": 0.0,
            "notes_weight": 0.0,
        },
    )

    out = ctx.build_agent_context(role="qa-low", thread="alignment")
    assert "VISION" in out
    assert calls == {"research": 0, "eng": 0, "ops": 0, "notes": 0}


def test_build_agent_context_unknown_role_uses_defaults(monkeypatch):
    monkeypatch.setattr(ctx, "read_vision", lambda **_: "V")
    monkeypatch.setattr(ctx, "read_research", lambda **_: "R")
    monkeypatch.setattr(ctx, "read_engineering", lambda: "E")
    monkeypatch.setattr(ctx, "read_ops", lambda *_args, **_kw: "O")
    monkeypatch.setattr(ctx, "read_agent_notes", lambda **_: "N")

    out = ctx.build_agent_context(role="unknown-role", thread="mechanistic")
    # Unknown role profile falls back to default weights and default vision keys.
    assert all(mark in out for mark in ["V", "R", "E", "O", "N"])
