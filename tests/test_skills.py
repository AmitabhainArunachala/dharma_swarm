"""Tests for Skill Discovery and Registry system."""

from __future__ import annotations

from pathlib import Path

import pytest

from dharma_swarm.skills import (
    ContextWeights,
    SkillDefinition,
    SkillRegistry,
    _parse_yaml_lite,
    parse_skill_file,
)


# ── YAML Parser Tests ────────────────────────────────────────────────


class TestYamlParser:
    """Tests for the minimal YAML frontmatter parser."""

    def test_simple_key_value(self):
        result = _parse_yaml_lite("name: cartographer\nmodel: claude-code")
        assert result["name"] == "cartographer"
        assert result["model"] == "claude-code"

    def test_array_value(self):
        result = _parse_yaml_lite("tags: [fix, debug, patch]")
        assert result["tags"] == ["fix", "debug", "patch"]

    def test_boolean_values(self):
        result = _parse_yaml_lite("enabled: true\ndisabled: false")
        assert result["enabled"] is True
        assert result["disabled"] is False

    def test_numeric_values(self):
        result = _parse_yaml_lite("priority: 3\nweight: 0.5")
        assert result["priority"] == 3
        assert result["weight"] == 0.5

    def test_nested_dict(self):
        text = "context_weights:\n  vision: 0.3\n  research: 0.5"
        result = _parse_yaml_lite(text)
        assert result["context_weights"]["vision"] == 0.3
        assert result["context_weights"]["research"] == 0.5

    def test_empty_input(self):
        result = _parse_yaml_lite("")
        assert result == {}

    def test_comments_ignored(self):
        result = _parse_yaml_lite("# comment\nname: test")
        assert result["name"] == "test"

    def test_quoted_string(self):
        result = _parse_yaml_lite("name: 'my skill'")
        assert result["name"] == "my skill"


# ── Skill File Parsing Tests ─────────────────────────────────────────


class TestParseSkillFile:
    """Tests for parsing SKILL.md files."""

    def test_parse_valid_skill(self, tmp_path: Path):
        skill_file = tmp_path / "test.skill.md"
        skill_file.write_text(
            "---\n"
            "name: test-skill\n"
            "model: claude-code\n"
            "provider: CLAUDE_CODE\n"
            "autonomy: balanced\n"
            "tags: [test, debug]\n"
            "keywords: [fix, repair]\n"
            "priority: 2\n"
            "---\n"
            "# Test Skill\n\n"
            "This is the system prompt for the skill.\n"
        )
        skill = parse_skill_file(skill_file)
        assert skill is not None
        assert skill.name == "test-skill"
        assert skill.model == "claude-code"
        assert skill.provider == "CLAUDE_CODE"
        assert skill.autonomy == "balanced"
        assert "test" in skill.tags
        assert "fix" in skill.keywords
        assert skill.priority == 2
        assert "Test Skill" in skill.description
        assert "system prompt" in skill.system_prompt

    def test_parse_with_context_weights(self, tmp_path: Path):
        skill_file = tmp_path / "weighted.skill.md"
        skill_file.write_text(
            "---\n"
            "name: weighted\n"
            "context_weights:\n"
            "  vision: 0.5\n"
            "  engineering: 0.4\n"
            "---\n"
            "# Weighted\n"
        )
        skill = parse_skill_file(skill_file)
        assert skill is not None
        assert skill.context_weights.vision == 0.5
        assert skill.context_weights.engineering == 0.4

    def test_parse_missing_frontmatter(self, tmp_path: Path):
        skill_file = tmp_path / "no_frontmatter.md"
        skill_file.write_text("# Just a regular markdown file\n")
        assert parse_skill_file(skill_file) is None

    def test_parse_nonexistent_file(self, tmp_path: Path):
        assert parse_skill_file(tmp_path / "nonexistent.md") is None

    def test_parse_minimal_frontmatter(self, tmp_path: Path):
        skill_file = tmp_path / "minimal.skill.md"
        skill_file.write_text("---\nname: minimal\n---\n# Minimal\n")
        skill = parse_skill_file(skill_file)
        assert skill is not None
        assert skill.name == "minimal"
        assert skill.model == "claude-code"  # default


# ── Skill Registry Tests ─────────────────────────────────────────────


class TestSkillRegistry:
    """Tests for skill discovery and matching."""

    @pytest.fixture
    def skill_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "skills"
        d.mkdir()
        # Create two test skills
        (d / "alpha.skill.md").write_text(
            "---\nname: alpha\ntags: [scan, map]\n"
            "keywords: [discover, explore]\npriority: 1\n---\n"
            "# Alpha Skill\n\nScans things.\n"
        )
        (d / "beta.skill.md").write_text(
            "---\nname: beta\ntags: [fix, debug]\n"
            "keywords: [bug, error, repair]\npriority: 2\n---\n"
            "# Beta Skill\n\nFixes things.\n"
        )
        return d

    def test_discover(self, skill_dir: Path):
        registry = SkillRegistry(skill_dirs=[skill_dir])
        skills = registry.discover()
        assert len(skills) == 2
        assert "alpha" in skills
        assert "beta" in skills

    def test_get_by_name(self, skill_dir: Path):
        registry = SkillRegistry(skill_dirs=[skill_dir])
        skill = registry.get("alpha")
        assert skill is not None
        assert skill.name == "alpha"
        assert registry.get("nonexistent") is None

    def test_list_all(self, skill_dir: Path):
        registry = SkillRegistry(skill_dirs=[skill_dir])
        all_skills = registry.list_all()
        assert len(all_skills) == 2

    def test_match_by_keyword(self, skill_dir: Path):
        registry = SkillRegistry(skill_dirs=[skill_dir])
        matches = registry.match("fix the bug in the code")
        assert len(matches) > 0
        assert matches[0].name == "beta"  # bug + fix → beta

    def test_match_by_name(self, skill_dir: Path):
        registry = SkillRegistry(skill_dirs=[skill_dir])
        matches = registry.match("use alpha to scan")
        assert len(matches) > 0
        assert matches[0].name == "alpha"

    def test_match_best(self, skill_dir: Path):
        registry = SkillRegistry(skill_dirs=[skill_dir])
        best = registry.match_best("explore the ecosystem")
        assert best is not None
        assert best.name == "alpha"  # explore keyword

    def test_match_no_results(self, skill_dir: Path):
        registry = SkillRegistry(skill_dirs=[skill_dir])
        assert registry.match("completely unrelated quantum physics") == []

    def test_hot_reload(self, skill_dir: Path):
        registry = SkillRegistry(skill_dirs=[skill_dir])
        registry.discover()
        # Modify a skill file
        import time
        time.sleep(0.05)
        skill_file = skill_dir / "alpha.skill.md"
        skill_file.write_text(
            "---\nname: alpha\ntags: [updated]\n---\n# Alpha Updated\n"
        )
        reloaded = registry.hot_reload()
        assert "alpha" in reloaded
        assert "updated" in registry.get("alpha").tags

    def test_empty_directory(self, tmp_path: Path):
        empty = tmp_path / "empty_skills"
        empty.mkdir()
        registry = SkillRegistry(skill_dirs=[empty])
        assert registry.discover() == {}

    def test_multiple_directories(self, tmp_path: Path):
        d1 = tmp_path / "skills1"
        d1.mkdir()
        d2 = tmp_path / "skills2"
        d2.mkdir()
        (d1 / "s1.skill.md").write_text("---\nname: s1\n---\n# S1\n")
        (d2 / "s2.skill.md").write_text("---\nname: s2\n---\n# S2\n")
        registry = SkillRegistry(skill_dirs=[d1, d2])
        skills = registry.discover()
        assert len(skills) == 2


# ── Built-in Skills Tests ────────────────────────────────────────────


class TestBuiltinSkills:
    """Test that the built-in skill files parse correctly."""

    def test_builtin_skills_exist(self):
        skills_dir = Path(__file__).parent.parent / "dharma_swarm" / "skills"
        skill_files = list(skills_dir.glob("*.skill.md"))
        assert len(skill_files) >= 7  # 7 built-in roles

    def test_all_builtins_parse(self):
        skills_dir = Path(__file__).parent.parent / "dharma_swarm" / "skills"
        for path in skills_dir.glob("*.skill.md"):
            skill = parse_skill_file(path)
            assert skill is not None, f"Failed to parse {path.name}"
            assert skill.name, f"No name in {path.name}"

    def test_builtin_registry_discovery(self):
        skills_dir = Path(__file__).parent.parent / "dharma_swarm" / "skills"
        registry = SkillRegistry(skill_dirs=[skills_dir])
        skills = registry.discover()
        assert len(skills) >= 7
        assert "cartographer" in skills
        assert "surgeon" in skills
        assert "architect" in skills
