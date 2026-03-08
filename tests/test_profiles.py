"""Tests for Agent Profile System."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dharma_swarm.profiles import (
    AgentProfile,
    AutonomyLevel,
    ProfileManager,
)


class TestAgentProfile:
    """Tests for the AgentProfile model."""

    def test_create_default(self):
        p = AgentProfile(name="test")
        assert p.name == "test"
        assert p.autonomy == AutonomyLevel.BALANCED
        assert p.model == "claude-code"
        assert p.context_budget == 30_000

    def test_permissions_check(self):
        p = AgentProfile(
            name="restricted",
            permissions=["read", "search"],
            denied=["delete", "rm"],
        )
        assert p.is_allowed("read file") is True
        assert p.is_allowed("search code") is True
        assert p.is_allowed("delete file") is False
        assert p.is_allowed("rm -rf /") is False
        assert p.is_allowed("write code") is False  # not in permissions

    def test_empty_permissions_allows_all(self):
        p = AgentProfile(name="open")
        assert p.is_allowed("anything") is True

    def test_denied_overrides_permissions(self):
        p = AgentProfile(
            name="mixed",
            permissions=["read", "write", "delete"],
            denied=["delete"],
        )
        assert p.is_allowed("delete file") is False
        assert p.is_allowed("read file") is True


class TestProfileManager:
    """Tests for loading and saving profiles."""

    def test_save_and_load(self, tmp_path: Path):
        mgr = ProfileManager(profile_dir=tmp_path)
        profile = AgentProfile(
            name="test-agent",
            model="codex",
            autonomy=AutonomyLevel.AGGRESSIVE,
        )
        saved_path = mgr.save(profile)
        assert saved_path.exists()

        # Load from fresh manager
        mgr2 = ProfileManager(profile_dir=tmp_path)
        loaded = mgr2.get("test-agent")
        assert loaded is not None
        assert loaded.model == "codex"
        assert loaded.autonomy == AutonomyLevel.AGGRESSIVE

    def test_list_all(self, tmp_path: Path):
        mgr = ProfileManager(profile_dir=tmp_path)
        for name in ["agent1", "agent2", "agent3"]:
            mgr.save(AgentProfile(name=name))
        all_profiles = mgr.list_all()
        assert len(all_profiles) == 3

    def test_remove(self, tmp_path: Path):
        mgr = ProfileManager(profile_dir=tmp_path)
        mgr.save(AgentProfile(name="deleteme"))
        assert mgr.remove("deleteme") is True
        assert mgr.get("deleteme") is None
        assert not (tmp_path / "deleteme.json").exists()

    def test_remove_nonexistent(self, tmp_path: Path):
        mgr = ProfileManager(profile_dir=tmp_path)
        assert mgr.remove("ghost") is False

    def test_get_nonexistent(self, tmp_path: Path):
        mgr = ProfileManager(profile_dir=tmp_path)
        assert mgr.get("ghost") is None

    def test_create_from_skill(self, tmp_path: Path):
        from dharma_swarm.skills import SkillDefinition
        skill = SkillDefinition(
            name="test-skill",
            model="codex",
            provider="CODEX",
            autonomy="aggressive",
            thread="mechanistic",
            tags=["test"],
        )
        mgr = ProfileManager(profile_dir=tmp_path)
        profile = mgr.create_from_skill(skill)
        assert profile.name == "test-skill"
        assert profile.model == "codex"
        assert profile.autonomy == AutonomyLevel.AGGRESSIVE
        assert profile.thread == "mechanistic"

    def test_create_from_skill_with_overrides(self, tmp_path: Path):
        from dharma_swarm.skills import SkillDefinition
        skill = SkillDefinition(name="base", model="claude-code")
        mgr = ProfileManager(profile_dir=tmp_path)
        profile = mgr.create_from_skill(
            skill,
            overrides={"model": "codex", "autonomy": "cautious", "timeout": 600},
        )
        assert profile.model == "codex"
        assert profile.autonomy == AutonomyLevel.CAUTIOUS
        assert profile.timeout == 600

    def test_invalid_json_ignored(self, tmp_path: Path):
        (tmp_path / "bad.json").write_text("not json")
        mgr = ProfileManager(profile_dir=tmp_path)
        profiles = mgr.load_all()
        assert len(profiles) == 0


# ── Additional profile tests ─────────────────────────────────────────


class TestAutonomyLevelEnum:
    """Tests for AutonomyLevel enum values and membership."""

    def test_all_enum_values(self):
        assert AutonomyLevel.LOCKED.value == "locked"
        assert AutonomyLevel.CAUTIOUS.value == "cautious"
        assert AutonomyLevel.BALANCED.value == "balanced"
        assert AutonomyLevel.AGGRESSIVE.value == "aggressive"
        assert AutonomyLevel.FULL.value == "full"

    def test_enum_member_count(self):
        assert len(AutonomyLevel) == 5

    def test_enum_is_str(self):
        """AutonomyLevel inherits from str, so values should be usable as strings."""
        level = AutonomyLevel.BALANCED
        assert isinstance(level, str)
        assert level == "balanced"

    def test_enum_from_value(self):
        assert AutonomyLevel("locked") == AutonomyLevel.LOCKED
        assert AutonomyLevel("full") == AutonomyLevel.FULL

    def test_invalid_enum_value_raises(self):
        with pytest.raises(ValueError):
            AutonomyLevel("nonexistent")


class TestIsAllowedEdgeCases:
    """Additional edge-case tests for AgentProfile.is_allowed()."""

    def test_denied_only_no_permissions(self):
        """Denied list without permissions: everything except denied is allowed."""
        p = AgentProfile(name="partial-deny", denied=["delete", "destroy"])
        assert p.is_allowed("read file") is True
        assert p.is_allowed("write code") is True
        assert p.is_allowed("delete record") is False
        assert p.is_allowed("destroy evidence") is False

    def test_permissions_only_no_denied(self):
        """Permissions list without denied: only permitted actions pass."""
        p = AgentProfile(name="permit-only", permissions=["read", "list"])
        assert p.is_allowed("read data") is True
        assert p.is_allowed("list files") is True
        assert p.is_allowed("write code") is False
        assert p.is_allowed("execute cmd") is False

    def test_case_insensitive_denied(self):
        p = AgentProfile(name="ci-deny", denied=["DELETE"])
        assert p.is_allowed("delete file") is False
        assert p.is_allowed("DELETE FILE") is False
        assert p.is_allowed("Delete File") is False

    def test_case_insensitive_permissions(self):
        p = AgentProfile(name="ci-perm", permissions=["READ"])
        assert p.is_allowed("read file") is True
        assert p.is_allowed("READ FILE") is True
        assert p.is_allowed("Read File") is True
        assert p.is_allowed("write code") is False

    def test_case_insensitive_denied_overrides_permissions(self):
        p = AgentProfile(
            name="ci-mixed",
            permissions=["Read", "Write"],
            denied=["WRITE"],
        )
        assert p.is_allowed("read data") is True
        assert p.is_allowed("write data") is False

    def test_empty_action_string(self):
        """Empty action string should be allowed if no permissions set."""
        p = AgentProfile(name="empty-action")
        assert p.is_allowed("") is True

    def test_empty_action_with_permissions(self):
        """Empty action cannot match any permission."""
        p = AgentProfile(name="empty-perm", permissions=["read"])
        assert p.is_allowed("") is False

    def test_substring_matching(self):
        """Denied/permitted entries match as substrings within the action string."""
        p = AgentProfile(name="substr", denied=["rm"])
        assert p.is_allowed("rm -rf /") is False
        # 'rm' appears as substring in 'format' and 'alarm' -- both blocked
        assert p.is_allowed("format disk") is False   # fo'rm'at contains 'rm'
        assert p.is_allowed("alarm clock") is False    # ala'rm' contains 'rm'
        # Strings without the substring pass
        assert p.is_allowed("read file") is True
        assert p.is_allowed("list items") is True

    def test_both_lists_empty(self):
        p = AgentProfile(name="wide-open", permissions=[], denied=[])
        assert p.is_allowed("anything goes") is True


class TestProfileManagerExtended:
    """Extended tests for ProfileManager save/load/remove operations."""

    def test_save_load_roundtrip_all_fields(self, tmp_path: Path):
        """Round-trip preserves every field of a fully-populated profile."""
        original = AgentProfile(
            name="full-profile",
            skill_name="my-skill",
            model="gpt-4",
            provider="OPENAI",
            autonomy=AutonomyLevel.FULL,
            max_tokens=8192,
            temperature=0.3,
            context_budget=50_000,
            timeout=600,
            permissions=["read", "write"],
            denied=["delete"],
            thread="mechanistic",
            system_prompt_extra="You are a specialist.",
            tags=["test", "full"],
        )
        mgr = ProfileManager(profile_dir=tmp_path)
        mgr.save(original)

        mgr2 = ProfileManager(profile_dir=tmp_path)
        loaded = mgr2.get("full-profile")
        assert loaded is not None
        assert loaded.name == original.name
        assert loaded.skill_name == original.skill_name
        assert loaded.model == original.model
        assert loaded.provider == original.provider
        assert loaded.autonomy == original.autonomy
        assert loaded.max_tokens == original.max_tokens
        assert loaded.temperature == original.temperature
        assert loaded.context_budget == original.context_budget
        assert loaded.timeout == original.timeout
        assert loaded.permissions == original.permissions
        assert loaded.denied == original.denied
        assert loaded.thread == original.thread
        assert loaded.system_prompt_extra == original.system_prompt_extra
        assert loaded.tags == original.tags

    def test_load_all_returns_all_saved(self, tmp_path: Path):
        """load_all() returns the full dict of saved profiles."""
        mgr = ProfileManager(profile_dir=tmp_path)
        names = ["alpha", "bravo", "charlie", "delta"]
        for n in names:
            mgr.save(AgentProfile(name=n))

        mgr2 = ProfileManager(profile_dir=tmp_path)
        loaded = mgr2.load_all()
        assert set(loaded.keys()) == set(names)
        for n in names:
            assert loaded[n].name == n

    def test_save_overwrites_existing(self, tmp_path: Path):
        """Saving a profile with the same name overwrites the old one."""
        mgr = ProfileManager(profile_dir=tmp_path)
        mgr.save(AgentProfile(name="agent", model="model-v1"))
        mgr.save(AgentProfile(name="agent", model="model-v2"))

        mgr2 = ProfileManager(profile_dir=tmp_path)
        loaded = mgr2.get("agent")
        assert loaded is not None
        assert loaded.model == "model-v2"

    def test_remove_existing_returns_true_and_deletes(self, tmp_path: Path):
        mgr = ProfileManager(profile_dir=tmp_path)
        mgr.save(AgentProfile(name="ephemeral"))
        json_path = tmp_path / "ephemeral.json"
        assert json_path.exists()

        result = mgr.remove("ephemeral")
        assert result is True
        assert not json_path.exists()
        assert mgr.get("ephemeral") is None

    def test_remove_cached_but_no_file(self, tmp_path: Path):
        """Remove a profile that is in the cache but whose file was already deleted."""
        mgr = ProfileManager(profile_dir=tmp_path)
        mgr.save(AgentProfile(name="phantom"))
        # Manually delete the file behind the manager's back
        (tmp_path / "phantom.json").unlink()
        # remove should still return True (was in cache) and not crash
        result = mgr.remove("phantom")
        assert result is True

    def test_remove_nonexistent_returns_false(self, tmp_path: Path):
        mgr = ProfileManager(profile_dir=tmp_path)
        mgr.load_all()  # force _loaded = True
        assert mgr.remove("does-not-exist") is False

    def test_get_triggers_load_all(self, tmp_path: Path):
        """get() on an unloaded manager auto-loads from disk."""
        mgr1 = ProfileManager(profile_dir=tmp_path)
        mgr1.save(AgentProfile(name="lazy-loaded"))

        mgr2 = ProfileManager(profile_dir=tmp_path)
        assert mgr2._loaded is False
        result = mgr2.get("lazy-loaded")
        assert mgr2._loaded is True
        assert result is not None

    def test_list_all_triggers_load_all(self, tmp_path: Path):
        """list_all() on an unloaded manager auto-loads from disk."""
        mgr1 = ProfileManager(profile_dir=tmp_path)
        mgr1.save(AgentProfile(name="listed"))

        mgr2 = ProfileManager(profile_dir=tmp_path)
        assert mgr2._loaded is False
        items = mgr2.list_all()
        assert mgr2._loaded is True
        assert len(items) == 1

    def test_default_profile_dir(self):
        """ProfileManager with no args uses ~/.dharma/profiles."""
        mgr = ProfileManager()
        expected = Path.home() / ".dharma" / "profiles"
        assert mgr._dir == expected

    def test_ensure_dir_creates_nested(self, tmp_path: Path):
        """_ensure_dir creates parent directories if needed."""
        deep_path = tmp_path / "a" / "b" / "c" / "profiles"
        mgr = ProfileManager(profile_dir=deep_path)
        mgr._ensure_dir()
        assert deep_path.exists()
        assert deep_path.is_dir()

    def test_load_all_mixed_valid_and_invalid_json(self, tmp_path: Path):
        """Valid profiles are loaded even when invalid files exist alongside."""
        (tmp_path / "good.json").write_text(
            json.dumps({"name": "good-agent", "model": "good-model"})
        )
        (tmp_path / "bad.json").write_text("{totally broken json")
        (tmp_path / "missing_name.json").write_text("{}")

        mgr = ProfileManager(profile_dir=tmp_path)
        loaded = mgr.load_all()
        # Only the fully valid one should load
        assert "good-agent" in loaded
        assert loaded["good-agent"].model == "good-model"

    def test_load_all_empty_directory(self, tmp_path: Path):
        """load_all on an empty directory returns empty dict."""
        mgr = ProfileManager(profile_dir=tmp_path)
        loaded = mgr.load_all()
        assert loaded == {}

    def test_save_returns_correct_path(self, tmp_path: Path):
        mgr = ProfileManager(profile_dir=tmp_path)
        path = mgr.save(AgentProfile(name="pathcheck"))
        assert path == tmp_path / "pathcheck.json"

    def test_saved_json_is_valid(self, tmp_path: Path):
        """Saved file contains valid JSON parseable back to a profile."""
        mgr = ProfileManager(profile_dir=tmp_path)
        mgr.save(AgentProfile(name="json-valid", model="test-model"))
        raw = (tmp_path / "json-valid.json").read_text()
        data = json.loads(raw)
        assert data["name"] == "json-valid"
        assert data["model"] == "test-model"


class TestCreateFromSkillExtended:
    """Extended tests for ProfileManager.create_from_skill()."""

    def test_create_from_mock_skill(self, tmp_path: Path):
        """create_from_skill works with any object that has the right attributes."""

        class MockSkill:
            name = "mock-skill"
            model = "mock-model"
            provider = "MOCK"
            autonomy = "cautious"
            thread = "alignment"
            system_prompt = "Be careful."
            tags = ["mock", "test"]

        mgr = ProfileManager(profile_dir=tmp_path)
        profile = mgr.create_from_skill(MockSkill())
        assert profile.name == "mock-skill"
        assert profile.model == "mock-model"
        assert profile.provider == "MOCK"
        assert profile.autonomy == AutonomyLevel.CAUTIOUS
        assert profile.thread == "alignment"
        assert profile.system_prompt_extra == "Be careful."
        assert profile.tags == ["mock", "test"]

    def test_create_from_skill_alias_autonomy_low(self, tmp_path: Path):
        """Autonomy alias 'low' maps to CAUTIOUS."""

        class MockSkill:
            name = "low-auto"
            model = "x"
            provider = "X"
            autonomy = "low"
            thread = None
            system_prompt = ""
            tags = []

        mgr = ProfileManager(profile_dir=tmp_path)
        profile = mgr.create_from_skill(MockSkill())
        assert profile.autonomy == AutonomyLevel.CAUTIOUS

    def test_create_from_skill_alias_autonomy_medium(self, tmp_path: Path):
        """Autonomy alias 'medium' maps to BALANCED."""

        class MockSkill:
            name = "med-auto"
            model = "x"
            provider = "X"
            autonomy = "medium"
            thread = None
            system_prompt = ""
            tags = []

        mgr = ProfileManager(profile_dir=tmp_path)
        profile = mgr.create_from_skill(MockSkill())
        assert profile.autonomy == AutonomyLevel.BALANCED

    def test_create_from_skill_alias_autonomy_high(self, tmp_path: Path):
        """Autonomy alias 'high' maps to AGGRESSIVE."""

        class MockSkill:
            name = "high-auto"
            model = "x"
            provider = "X"
            autonomy = "high"
            thread = None
            system_prompt = ""
            tags = []

        mgr = ProfileManager(profile_dir=tmp_path)
        profile = mgr.create_from_skill(MockSkill())
        assert profile.autonomy == AutonomyLevel.AGGRESSIVE

    def test_create_from_skill_unknown_autonomy_defaults(self, tmp_path: Path):
        """Unknown autonomy string falls back to BALANCED."""

        class MockSkill:
            name = "unknown-auto"
            model = "x"
            provider = "X"
            autonomy = "turbo-yolo"
            thread = None
            system_prompt = ""
            tags = []

        mgr = ProfileManager(profile_dir=tmp_path)
        profile = mgr.create_from_skill(MockSkill())
        assert profile.autonomy == AutonomyLevel.BALANCED

    def test_create_from_skill_overrides_ignore_nonexistent_attrs(self, tmp_path: Path):
        """Overrides with keys that don't exist on AgentProfile are silently skipped."""

        class MockSkill:
            name = "skip-test"
            model = "x"
            provider = "X"
            autonomy = "balanced"
            thread = None
            system_prompt = ""
            tags = []

        mgr = ProfileManager(profile_dir=tmp_path)
        profile = mgr.create_from_skill(
            MockSkill(),
            overrides={"nonexistent_field": "value", "model": "overridden"},
        )
        assert profile.model == "overridden"
        assert not hasattr(profile, "nonexistent_field")

    def test_create_from_skill_override_autonomy_string(self, tmp_path: Path):
        """Autonomy override as string is mapped through _AUTONOMY_MAP."""

        class MockSkill:
            name = "override-auto"
            model = "x"
            provider = "X"
            autonomy = "balanced"
            thread = None
            system_prompt = ""
            tags = []

        mgr = ProfileManager(profile_dir=tmp_path)
        profile = mgr.create_from_skill(
            MockSkill(),
            overrides={"autonomy": "full"},
        )
        assert profile.autonomy == AutonomyLevel.FULL

    def test_create_from_skill_with_none_overrides(self, tmp_path: Path):
        """Passing overrides=None should not crash."""

        class MockSkill:
            name = "none-overrides"
            model = "x"
            provider = "X"
            autonomy = "balanced"
            thread = None
            system_prompt = ""
            tags = []

        mgr = ProfileManager(profile_dir=tmp_path)
        profile = mgr.create_from_skill(MockSkill(), overrides=None)
        assert profile.name == "none-overrides"

    def test_create_from_skill_with_empty_overrides(self, tmp_path: Path):
        """Passing overrides={} applies no changes."""

        class MockSkill:
            name = "empty-overrides"
            model = "original"
            provider = "X"
            autonomy = "balanced"
            thread = None
            system_prompt = ""
            tags = []

        mgr = ProfileManager(profile_dir=tmp_path)
        profile = mgr.create_from_skill(MockSkill(), overrides={})
        assert profile.model == "original"
