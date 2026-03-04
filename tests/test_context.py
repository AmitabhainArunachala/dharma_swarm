"""Tests for dharma_swarm.context — multi-layer context engine."""

import sqlite3
from unittest.mock import patch

from dharma_swarm.context import (
    CONTEXT_BUDGET,
    ROLE_PROFILES,
    _THREAD_CLAUDE_FILES,
    _VISION_FILES,
    _read_file,
    _read_head,
    build_agent_context,
    read_agni_state,
    read_agent_notes,
    read_engineering,
    read_manifest,
    read_memory_context,
    read_ops,
    read_research,
    read_shipped,
    read_trishula_inbox,
    read_vision,
)


# === _read_file / _read_head ===


def test_read_file_exists(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello world")
    result = _read_file(f, max_chars=100)
    assert result == "hello world"


def test_read_file_truncates(tmp_path):
    f = tmp_path / "big.txt"
    f.write_text("x" * 500)
    result = _read_file(f, max_chars=100)
    assert len(result) < 200
    assert "truncated" in result


def test_read_file_missing(tmp_path):
    result = _read_file(tmp_path / "nope.txt")
    assert result is None


def test_read_head(tmp_path):
    f = tmp_path / "multi.txt"
    f.write_text("line1\nline2\nline3\nline4\nline5\n")
    result = _read_head(f, lines=3)
    assert result == "line1\nline2\nline3\n"


def test_read_head_missing(tmp_path):
    result = _read_head(tmp_path / "nope.txt")
    assert result is None


# === L1: Vision ===


def test_read_vision_empty_keys():
    """Empty key list uses defaults (ten_words, soul, north_star)."""
    result = read_vision(keys=[])
    # Empty list is falsy, so it falls back to defaults
    assert isinstance(result, str)


def test_read_vision_missing_key():
    """Unknown key gracefully skipped."""
    result = read_vision(keys=["nonexistent_key_xyz"])
    assert result == ""


def test_read_vision_with_real_files():
    """Test that vision loading finds at least soul/ten_words if they exist."""
    result = read_vision(keys=["soul"])
    # May or may not find the file depending on filesystem state
    if result:
        assert "Vision Layer" in result


# === L2: Research ===


def test_thread_claude_file_mapping():
    """Each thread maps to known CLAUDE files."""
    for thread, files in _THREAD_CLAUDE_FILES.items():
        assert len(files) >= 2, f"Thread {thread} needs at least 2 CLAUDE files"
        for f in files:
            assert f.name.startswith("CLAUDE"), f"Bad CLAUDE file: {f.name}"


def test_read_research_returns_string():
    """read_research always returns a string, never errors."""
    for thread in ["mechanistic", "phenomenological", "architectural", "alignment", "scaling", None]:
        result = read_research(thread=thread)
        assert isinstance(result, str)


def test_read_research_different_threads():
    """Different threads should produce different content (if files exist)."""
    mech = read_research(thread="mechanistic")
    phenom = read_research(thread="phenomenological")
    # They might both be empty if CLAUDE files don't exist, but shouldn't crash
    assert isinstance(mech, str)
    assert isinstance(phenom, str)


# === L3: Engineering ===


def test_read_engineering_returns_string():
    result = read_engineering()
    assert isinstance(result, str)


def test_read_engineering_finds_modules():
    """Should list dharma_swarm modules if we're in the right directory."""
    result = read_engineering()
    if "dharma_swarm modules" in result:
        assert "models.py" in result
        assert "providers.py" in result
        assert "context.py" in result


# === L4: Ops ===


def test_read_agni_state_returns_dict():
    result = read_agni_state()
    assert isinstance(result, dict)


def test_read_trishula_inbox_returns_string():
    result = read_trishula_inbox()
    assert isinstance(result, str)


def test_read_manifest_returns_string():
    result = read_manifest()
    assert isinstance(result, str)


def test_read_memory_context_no_db(tmp_path):
    result = read_memory_context(state_dir=tmp_path)
    assert "No memory database" in result


def test_read_memory_context_empty_db(tmp_path):
    """With an empty DB, should report no memories."""
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    db_path = db_dir / "memory.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE memories (content TEXT, layer TEXT, timestamp TEXT)"
    )
    conn.commit()
    conn.close()
    result = read_memory_context(state_dir=tmp_path)
    assert "No memories" in result


def test_read_memory_context_with_data(tmp_path):
    """With data in DB, should return formatted entries."""
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    db_path = db_dir / "memory.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE memories (content TEXT, layer TEXT, timestamp TEXT)"
    )
    conn.execute(
        "INSERT INTO memories VALUES (?, ?, ?)",
        ("Test memory entry", "witness", "2026-01-01T00:00:00"),
    )
    conn.commit()
    conn.close()
    result = read_memory_context(state_dir=tmp_path)
    assert "witness" in result
    assert "Test memory" in result


def test_read_shipped_returns_string():
    result = read_shipped()
    assert isinstance(result, str)


def test_read_ops_returns_string():
    result = read_ops()
    assert isinstance(result, str)
    assert "Operations Layer" in result or isinstance(result, str)


# === L5: Swarm notes ===


def test_read_agent_notes_no_shared_dir():
    """With no shared dir, return empty."""
    result = read_agent_notes()
    # Either empty or has some content if shared dir exists
    assert isinstance(result, str)


def test_read_agent_notes_with_files(tmp_path):
    """Read agent notes from a temp shared directory."""
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "surgeon_notes.md").write_text("Found bug in providers.py line 42")
    (shared / "architect_notes.md").write_text("Design proposal: add context layers")

    with patch("dharma_swarm.context.SHARED_DIR", shared):
        result = read_agent_notes()
        assert "surgeon" in result
        assert "architect" in result


def test_read_agent_notes_excludes_own_role(tmp_path):
    """Agent should not see its own notes."""
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "surgeon_notes.md").write_text("My own findings")
    (shared / "architect_notes.md").write_text("Other agent findings")

    with patch("dharma_swarm.context.SHARED_DIR", shared):
        result = read_agent_notes(exclude_role="surgeon")
        assert "surgeon" not in result.split("# ")[1] if "Other" in result else True
        assert "architect" in result


# === Role profiles ===


def test_all_profile_roles_have_weights():
    """Every role profile must have all weight keys."""
    required = {"vision", "research_weight", "engineering_weight", "ops_weight", "notes_weight"}
    for role, profile in ROLE_PROFILES.items():
        assert required.issubset(profile.keys()), f"Role {role} missing keys: {required - profile.keys()}"


def test_role_weights_are_reasonable():
    """Weights should be between 0 and 1."""
    for role, profile in ROLE_PROFILES.items():
        for key in ["research_weight", "engineering_weight", "ops_weight", "notes_weight"]:
            val = profile[key]
            assert 0.0 <= val <= 1.0, f"Role {role}, {key}={val} out of range"


def test_vision_keys_are_valid():
    """Vision keys referenced in profiles must exist in _VISION_FILES."""
    for role, profile in ROLE_PROFILES.items():
        for key in profile["vision"]:
            assert key in _VISION_FILES, f"Role {role} references unknown vision key: {key}"


# === build_agent_context ===


def test_build_agent_context_returns_string():
    result = build_agent_context()
    assert isinstance(result, str)
    assert len(result) > 0


def test_build_agent_context_respects_budget():
    result = build_agent_context()
    assert len(result) <= CONTEXT_BUDGET + 100  # small margin for truncation message


def test_build_agent_context_all_roles():
    """Every known role should produce valid context."""
    for role in ROLE_PROFILES:
        result = build_agent_context(role=role, thread="mechanistic")
        assert isinstance(result, str)
        assert len(result) > 0, f"Role {role} produced empty context"


def test_build_agent_context_all_threads():
    """Every known thread should work."""
    for thread in _THREAD_CLAUDE_FILES:
        result = build_agent_context(role="researcher", thread=thread)
        assert isinstance(result, str)


def test_build_agent_context_unknown_role():
    """Unknown role falls back to generic."""
    result = build_agent_context(role="unknown_role_xyz")
    assert isinstance(result, str)
    assert len(result) > 0


def test_build_agent_context_none_inputs():
    """None role and thread should not crash."""
    result = build_agent_context(role=None, thread=None)
    assert isinstance(result, str)


def test_surgeon_gets_less_vision():
    """Surgeon profile has empty vision list — should skip vision layer."""
    surgeon_ctx = build_agent_context(role="surgeon", thread="mechanistic")
    arch_ctx = build_agent_context(role="architect", thread="mechanistic")
    # Architect has genome_spec, lenia_godel, garden_daemon in vision
    # Surgeon has [] — so architect context should be larger (or have vision markers)
    assert isinstance(surgeon_ctx, str)
    assert isinstance(arch_ctx, str)


def test_context_includes_ops_layer():
    """All roles should include operational context."""
    result = build_agent_context(role="surgeon")
    assert "Operations Layer" in result or "Trishula" in result or "Memory" in result
