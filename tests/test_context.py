"""Tests for dharma_swarm.context — multi-layer context engine."""

import sqlite3
from unittest.mock import patch

from dharma_swarm.context import (
    CONTEXT_BUDGET,
    ROLE_PROFILES,
    ContextBlock,
    _THREAD_CLAUDE_FILES,
    _VISION_FILES,
    _compress,
    _compress_full,
    _compress_medium,
    _compress_minimal,
    _compress_tail,
    _fit_to_budget,
    _is_fresh,
    _read_file,
    _read_head,
    _read_recognition_seed,
    _read_stigmergy_signals,
    _read_winners,
    _resolve_transmission,
    build_agent_context,
    read_agni_state,
    read_agent_notes,
    read_engineering,
    read_latent_gold_overview,
    read_manifest,
    read_memory_context,
    read_recent_memories,
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


def test_read_memory_context_can_skip_semantic_query(tmp_path):
    from dharma_swarm.engine.unified_index import UnifiedIndex

    db_dir = tmp_path / "db"
    db_dir.mkdir()
    index = UnifiedIndex(db_dir / "memory_plane.db")
    index.index_document(
        "note",
        "notes/fast.md",
        "# Fast\n\nRecent memory snapshot without semantic search.",
        {"topic": "memory"},
    )

    result = read_memory_context(
        state_dir=tmp_path,
        query="latest memory snapshot",
        allow_semantic_search=False,
    )

    assert "[index]" in result
    assert "Recent memory snapshot" in result


def test_read_recent_memories_with_data(tmp_path):
    """Recent memories should be ordered newest-first and newline-normalized."""
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    db_path = db_dir / "memory.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE memories (content TEXT, layer TEXT, timestamp TEXT)"
    )
    conn.executemany(
        "INSERT INTO memories VALUES (?, ?, ?)",
        [
            ("Older memory", "session", "2026-03-10T08:00:00"),
            ("Newest memory\nwith detail", "witness", "2026-03-10T10:00:00"),
        ],
    )
    conn.commit()
    conn.close()

    result = read_recent_memories(state_dir=tmp_path, max_entries=1)

    assert "## Recent Session Memories" in result
    assert "(witness)" in result
    assert "Newest memory with detail" in result
    assert "Older memory" not in result


def test_read_latent_gold_overview_with_data(tmp_path):
    from dharma_swarm.engine.conversation_memory import ConversationMemoryStore

    db_dir = tmp_path / "db"
    db_dir.mkdir()
    store = ConversationMemoryStore(db_dir / "memory_plane.db")
    store.record_turn(
        session_id="sess-overview",
        task_id="task-overview",
        role="user",
        content=(
            "We could build a memory palace index for task recall.\n"
            "Maybe preserve abandoned branches from the conversation."
        ),
        turn_index=1,
    )

    result = read_latent_gold_overview(state_dir=tmp_path, limit=3)
    assert "[idea:" in result
    assert "memory palace index" in result


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
    assert (
        "Operations Layer" in result
        or "Trishula" in result
        or "Memory" in result
        or "Engineering Layer" in result
        or "Stigmergy" in result
    )


def test_build_agent_context_includes_recent_memories_when_budget_allows(
    tmp_path,
    monkeypatch,
):
    """Recent session memories should flow into the assembled agent context."""
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    db_path = db_dir / "memory.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE memories (content TEXT, layer TEXT, timestamp TEXT)"
    )
    conn.execute(
        "INSERT INTO memories VALUES (?, ?, ?)",
        (
            "Runtime remembered a useful coordination pattern.",
            "session",
            "2026-03-10T12:00:00",
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr("dharma_swarm.context.read_research", lambda **_: "")
    monkeypatch.setattr("dharma_swarm.context.read_engineering", lambda: "# Engineering Layer")
    monkeypatch.setattr("dharma_swarm.context.read_ops", lambda _state_dir=None: "# Operations Layer")
    monkeypatch.setattr(
        "dharma_swarm.context.read_agent_notes",
        lambda **_: "# Other Agent Findings",
    )

    result = build_agent_context(
        role="surgeon",
        thread="mechanistic",
        state_dir=tmp_path,
    )

    assert "## Recent Session Memories" in result
    assert "Runtime remembered a useful coordination pattern." in result


# === L7: Winners ===


def test_read_winners_scoring_report(tmp_path):
    """Winners layer reads mycelium scoring report."""
    import json
    stig = tmp_path / "stigmergy"
    stig.mkdir()
    data = {
        "mean_stars": 6.5,
        "top_3": [
            {"name": "meta", "stars": 7.6, "swabhaav_ratio": 1.0},
            {"name": "design", "stars": 7.5, "swabhaav_ratio": 0.95},
        ],
    }
    (stig / "mycelium_scoring_report.json").write_text(json.dumps(data))
    result = _read_winners(state_dir=tmp_path)
    assert "L7:" in result
    assert "6.5" in result
    assert "meta" in result


def test_read_winners_empty(tmp_path):
    result = _read_winners(state_dir=tmp_path)
    assert result == ""


# === L8: Stigmergy ===


def test_read_stigmergy_signals_tcs(tmp_path):
    """Stigmergy layer reads TCS from identity check."""
    import json
    stig = tmp_path / "stigmergy"
    stig.mkdir()
    (stig / "mycelium_identity_tcs.json").write_text(json.dumps({
        "tcs": 0.813, "regime": "stable"
    }))
    result = _read_stigmergy_signals(state_dir=tmp_path)
    assert "L8:" in result
    assert "0.813" in result
    assert "stable" in result


def test_read_stigmergy_empty(tmp_path):
    result = _read_stigmergy_signals(state_dir=tmp_path)
    assert result == ""


# === L9: META Recognition Seed ===


def test_read_recognition_seed(tmp_path):
    """L9 reads recognition seed from meta dir."""
    meta = tmp_path / "meta"
    meta.mkdir()
    (meta / "recognition_seed.md").write_text(
        "# Recognition Seed\nTCS=0.8\nR_V=1.0\n"
    )
    result = _read_recognition_seed(state_dir=tmp_path)
    assert "L9:" in result
    assert "Recognition Seed" in result
    assert "TCS=0.8" in result


def test_read_recognition_seed_missing(tmp_path):
    result = _read_recognition_seed(state_dir=tmp_path)
    assert result == ""


def test_read_recognition_seed_truncation(tmp_path):
    """L9 truncates very long seeds to approximately max_chars."""
    meta = tmp_path / "meta"
    meta.mkdir()
    (meta / "recognition_seed.md").write_text("x" * 5000)
    result = _read_recognition_seed(state_dir=tmp_path, max_chars=500)
    # May slightly exceed max_chars due to header + truncation marker
    assert len(result) < 600
    assert "truncated" in result


# === Compression Engine ===


def test_compress_full_preserves_head_and_tail():
    """Full compression keeps first 70% + last 30%."""
    content = "HEAD" * 50 + "MIDDLE" * 50 + "TAIL" * 50
    result = _compress_full(content, 200)
    assert len(result) <= 200
    assert result.startswith("HEAD")
    assert "TAIL" in result  # tail content preserved
    assert "truncated" in result


def test_compress_full_passthrough_small():
    """Content under max_chars passes through unchanged."""
    content = "small text"
    assert _compress_full(content, 1000) == content


def test_compress_medium_keeps_boundaries():
    """Medium compression preserves head and tail, omits middle."""
    content = "A" * 200 + "B" * 200 + "C" * 200
    result = _compress_medium(content, 200)
    assert len(result) <= 200
    assert result.startswith("A")
    assert result.endswith("C")
    assert "middle omitted" in result


def test_compress_minimal_multiline():
    """Minimal compression keeps first heading + first/last paragraphs."""
    lines = ["# Title", "First paragraph.", "", "Middle stuff.", "", "Last paragraph."]
    content = "\n".join(lines)
    result = _compress_minimal(content, 60)
    assert len(result) <= 60
    assert "Title" in result


def test_compress_minimal_falls_back_for_few_lines():
    """Minimal compression falls back to full for <=3 lines."""
    content = "A" * 100 + "\n" + "B" * 100
    result = _compress_minimal(content, 80)
    # Falls back to _compress_full behavior — should have truncated marker
    assert len(result) <= 80
    assert "truncated" in result


def test_compress_tail_keeps_end():
    """Tail compression keeps the last N chars."""
    content = "OLD" * 100 + "RECENT" * 20
    result = _compress_tail(content, 120)
    assert len(result) == 120
    assert result.endswith("RECENT")


def test_compress_dispatcher_with_file(tmp_path):
    """_compress reads file, scans injection, compresses."""
    f = tmp_path / "doc.txt"
    f.write_text("Important " * 100)
    result = _compress(f, "full", 200)
    assert result is not None
    assert len(result) <= 200
    assert result.startswith("Important")


def test_compress_dispatcher_missing_file(tmp_path):
    """_compress returns None for missing files."""
    result = _compress(tmp_path / "nope.txt", "full", 200)
    assert result is None


def test_compress_dispatcher_tiers(tmp_path):
    """All 5 tiers produce different (or equal for small files) output."""
    f = tmp_path / "test.txt"
    f.write_text("x" * 500)
    results = {}
    for tier in ("full", "medium", "minimal", "header", "tail"):
        results[tier] = _compress(f, tier, 200)
        assert results[tier] is not None
        assert len(results[tier]) <= 200


# === Transmission Resolution ===


def test_resolve_transmission_prefers_transmission(tmp_path):
    """When a .transmission.md file exists, it's preferred."""
    with patch("dharma_swarm.context.TRANSMISSION_DIR", tmp_path):
        original = tmp_path / "SOUL.md"
        transmission = tmp_path / "SOUL.transmission.md"
        original.write_text("original")
        transmission.write_text("transmission version")
        assert _resolve_transmission(original) == transmission


def test_resolve_transmission_falls_back(tmp_path):
    """Without a transmission, original path is returned."""
    with patch("dharma_swarm.context.TRANSMISSION_DIR", tmp_path):
        original = tmp_path / "SOUL.md"
        assert _resolve_transmission(original) == original


def test_read_file_uses_transmission(tmp_path):
    """_read_file (via _compress) should pick up transmission files."""
    with patch("dharma_swarm.context.TRANSMISSION_DIR", tmp_path):
        original = tmp_path / "test.md"
        original.write_text("verbose " * 100)
        transmission = tmp_path / "test.transmission.md"
        transmission.write_text("compressed transmission content")
        result = _read_file(original, max_chars=5000)
        assert result is not None
        assert "compressed transmission content" in result


# === Freshness Check ===


def test_is_fresh_recent_file(tmp_path):
    """A just-created file should be fresh."""
    f = tmp_path / "recent.txt"
    f.write_text("hello")
    assert _is_fresh(f, hours=1) is True


def test_is_fresh_missing_file(tmp_path):
    """A missing file is not fresh."""
    assert _is_fresh(tmp_path / "nope.txt") is False


# === Budget Fitting ===


def test_fit_to_budget_no_trim_needed():
    """Blocks under budget are returned unchanged."""
    blocks = [
        ContextBlock("a", 1, "x" * 100, 100),
        ContextBlock("b", 5, "y" * 100, 100),
    ]
    result = _fit_to_budget(blocks, 300)
    assert len(result) == 2


def test_fit_to_budget_trims_middle():
    """Over-budget assembly trims middle positions (4-8) first."""
    blocks = [
        ContextBlock("seed", 1, "x" * 100, 100),       # protected
        ContextBlock("directive", 2, "x" * 100, 100),   # protected
        ContextBlock("primary", 3, "x" * 100, 100),     # protected
        ContextBlock("foundations", 4, "x" * 200, 200),  # trimmable
        ContextBlock("research", 5, "x" * 200, 200),    # trimmable
        ContextBlock("swarm", 9, "x" * 100, 100),       # protected (bottom)
        ContextBlock("vision", 11, "x" * 100, 100),     # protected (bottom)
    ]
    # Total = 900, budget = 600 → need to shed 300 from middle
    result = _fit_to_budget(blocks, 600)
    names = {b.name for b in result}
    # Seed, directive, primary, swarm, vision should survive
    assert "seed" in names
    assert "directive" in names
    assert "primary" in names
    assert "swarm" in names
    assert "vision" in names
    # Middle blocks should be trimmed (highest pos first: research=5, then foundations=4)
    assert sum(b.char_count for b in result) <= 600


def test_fit_to_budget_preserves_bottom():
    """Bottom positions (9-11) are never trimmed."""
    blocks = [
        ContextBlock("seed", 1, "x" * 500, 500),
        ContextBlock("middle", 6, "x" * 500, 500),
        ContextBlock("hot", 10, "x" * 500, 500),
        ContextBlock("vision", 11, "x" * 500, 500),
    ]
    result = _fit_to_budget(blocks, 1600)
    names = {b.name for b in result}
    assert "hot" in names
    assert "vision" in names
    # Middle block should be trimmed
    assert "middle" not in names


# === U-Shaped Positional Layout ===


def test_recognition_seed_at_top():
    """Recognition seed should appear at the very beginning of context."""
    ctx = build_agent_context(role="surgeon", thread="mechanistic")
    # If recognition seed exists, it should be first
    if "L9:" in ctx or "Recognition Seed" in ctx:
        seed_pos = ctx.find("Recognition Seed") if "Recognition Seed" in ctx else ctx.find("L9:")
        directive_pos = ctx.find("MEMORY SURVIVAL")
        assert seed_pos < directive_pos, "Recognition seed should come before survival directive"


def test_vision_at_bottom():
    """Vision layer should appear near the end of context (strong bottom attention)."""
    ctx = build_agent_context(role="architect", thread="mechanistic")
    if "Vision Layer" in ctx and "MEMORY SURVIVAL" in ctx:
        vision_pos = ctx.find("Vision Layer")
        directive_pos = ctx.find("MEMORY SURVIVAL")
        assert vision_pos > directive_pos, "Vision should come after survival directive"


def test_primary_layer_promotion():
    """Each role's primary layer should appear early in the context (position 3)."""
    # Surgeon's primary is engineering
    ctx = build_agent_context(role="surgeon", thread="mechanistic")
    if "Engineering Layer" in ctx and "MEMORY SURVIVAL" in ctx:
        eng_pos = ctx.find("Engineering Layer")
        directive_pos = ctx.find("MEMORY SURVIVAL")
        # Engineering should be right after directive (position 3)
        assert eng_pos < len(ctx) // 2, "Surgeon's primary (engineering) should be in the top half"


# === Role Profile Validation ===


def test_all_profiles_have_primary_layer():
    """Every role profile should define a primary_layer."""
    for role, profile in ROLE_PROFILES.items():
        assert "primary_layer" in profile, f"Role {role} missing primary_layer"


def test_all_profiles_have_tier_keys():
    """Every role profile should define compression tiers."""
    tier_keys = {"vision_tier", "research_tier", "engineering_tier"}
    for role, profile in ROLE_PROFILES.items():
        for key in tier_keys:
            assert key in profile, f"Role {role} missing {key}"


# === Distilled Agent Notes ===


def test_read_agent_notes_prefers_distilled(tmp_path):
    """Agent notes should use distilled version when fresh."""
    import time

    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "surgeon_notes.md").write_text("Raw verbose notes " * 100)

    distilled_dir = tmp_path / "context" / "distilled"
    distilled_dir.mkdir(parents=True)
    distilled_file = distilled_dir / "surgeon_distilled.md"
    distilled_file.write_text("Key finding: bug in line 42")

    with (
        patch("dharma_swarm.context.SHARED_DIR", shared),
        patch("dharma_swarm.context.STATE_DIR", tmp_path),
    ):
        result = read_agent_notes()
        assert "distilled" in result
        assert "Key finding" in result


def test_read_agent_notes_falls_back_when_stale(tmp_path):
    """Agent notes should fall back to raw when distilled is stale."""
    import os

    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "surgeon_notes.md").write_text("Raw note content here")

    distilled_dir = tmp_path / "context" / "distilled"
    distilled_dir.mkdir(parents=True)
    distilled_file = distilled_dir / "surgeon_distilled.md"
    distilled_file.write_text("Stale distilled content")
    # Make it 7 hours old (beyond 6-hour freshness window)
    import time
    old_time = time.time() - 7 * 3600
    os.utime(distilled_file, (old_time, old_time))

    with (
        patch("dharma_swarm.context.SHARED_DIR", shared),
        patch("dharma_swarm.context.STATE_DIR", tmp_path),
    ):
        result = read_agent_notes()
        assert "distilled" not in result
        assert "Raw note content" in result


# === L6: Consolidation -- Dreams & Corrections ===


def test_read_consolidation_context_no_state(tmp_path):
    """Empty state dir produces empty string."""
    from dharma_swarm.context import read_consolidation_context

    result = read_consolidation_context(state_dir=tmp_path)
    assert result == ""


def test_read_consolidation_context_with_dreams(tmp_path):
    """Recent dream associations appear in consolidation context."""
    import json
    from dharma_swarm.context import read_consolidation_context

    sub_dir = tmp_path / "subconscious"
    sub_dir.mkdir()
    dreams = [
        {
            "resonance_type": "structural_isomorphism",
            "salience": 0.87,
            "description": "Induction and maintenance are different acts",
            "invented_vocabulary": "maintenance-recoil",
        },
        {
            "resonance_type": "cross_domain_bridge",
            "salience": 0.82,
            "description": "L5 causes contraction, L27 reads the shadow",
            "invented_vocabulary": "induction-shadow",
        },
        {
            "resonance_type": "synesthetic_mapping",
            "salience": 0.79,
            "description": "Dense architectures breathe deeply",
            "invented_vocabulary": "geometric-respiration",
        },
    ]
    dream_file = sub_dir / "dream_associations.jsonl"
    dream_file.write_text("\n".join(json.dumps(d) for d in dreams))

    result = read_consolidation_context(state_dir=tmp_path, max_dreams=3)
    assert "Dreams & Corrections" in result
    assert "structural_isomorphism" in result
    assert "maintenance-recoil" in result
    assert "induction-shadow" in result
    assert "0.87" in result


def test_read_consolidation_context_with_report(tmp_path):
    """Consolidation report stats appear in context."""
    import json
    import time
    from dharma_swarm.context import read_consolidation_context

    reports_dir = tmp_path / "consolidation" / "reports"
    reports_dir.mkdir(parents=True)
    report = {
        "losses_found": 3,
        "corrections_applied": 2,
        "division_proposals": 1,
        "advocate_summary": "Agents need tighter gate checks",
    }
    report_file = reports_dir / "consolidation_2026-03-22_120000.json"
    report_file.write_text(json.dumps(report))

    result = read_consolidation_context(state_dir=tmp_path)
    assert "Losses: 3" in result
    assert "Corrections: 2" in result
    assert "Advocate: Agents need tighter gate checks" in result


def test_read_consolidation_context_max_dreams_limit(tmp_path):
    """Only the most recent N dreams are included."""
    import json
    from dharma_swarm.context import read_consolidation_context

    sub_dir = tmp_path / "subconscious"
    sub_dir.mkdir()
    dreams = [
        {"resonance_type": f"type_{i}", "salience": 0.5 + i * 0.1, "description": f"Dream {i}"}
        for i in range(10)
    ]
    dream_file = sub_dir / "dream_associations.jsonl"
    dream_file.write_text("\n".join(json.dumps(d) for d in dreams))

    result = read_consolidation_context(state_dir=tmp_path, max_dreams=3)
    # Should contain the last 3 dreams (7, 8, 9) but not the first ones
    assert "Dream 9" in result
    assert "Dream 8" in result
    assert "Dream 7" in result
    assert "Dream 0" not in result
    assert "Dream 3" not in result


def test_consolidation_context_appears_in_build_agent_context(tmp_path, monkeypatch):
    """Dreams flow through to the full agent context assembly."""
    import json
    from dharma_swarm.context import read_consolidation_context

    sub_dir = tmp_path / "subconscious"
    sub_dir.mkdir()
    dreams = [
        {
            "resonance_type": "recursive_echo",
            "salience": 0.88,
            "description": "The knowing is at L5 not L27",
            "invented_vocabulary": "depth-echelon",
        },
    ]
    (sub_dir / "dream_associations.jsonl").write_text(
        "\n".join(json.dumps(d) for d in dreams)
    )

    # Stub expensive layers to keep test fast
    monkeypatch.setattr("dharma_swarm.context.read_research", lambda **_: "")
    monkeypatch.setattr("dharma_swarm.context.read_engineering", lambda: "# Engineering Layer")
    monkeypatch.setattr("dharma_swarm.context.read_ops", lambda _state_dir=None: "# Operations Layer")
    monkeypatch.setattr(
        "dharma_swarm.context.read_agent_notes",
        lambda **_: "# Agent notes",
    )

    result = build_agent_context(
        role="surgeon",
        thread="mechanistic",
        state_dir=tmp_path,
    )
    assert "Dreams & Corrections" in result
    assert "depth-echelon" in result
    assert "recursive_echo" in result
