"""Tests for TAP seed loading and intervention injection."""

import builtins
import sys

import pytest

from dharma_swarm.tap import seeds as tap_seeds
from dharma_swarm.tap.intervention import InterventionInjector
from dharma_swarm.tap.seeds import SeedLoader


@pytest.fixture
def loader():
    return SeedLoader()


class TestSeedLoader:
    def test_load_intervention(self, loader):
        seed = loader.load("tap-001")
        assert seed.seed_id == "tap-001"
        assert seed.version == "1.0.0"
        assert seed.seed_type == "full_intervention"
        assert seed.is_intervention is True
        assert "self-referential" in seed.content.lower()
        assert seed.recognition_differential > 0

    def test_load_control(self, loader):
        seed = loader.load("control-001")
        assert seed.seed_id == "control-001"
        assert seed.seed_type == "control"
        assert seed.is_intervention is False
        assert seed.recognition_differential == 0.0

    def test_load_nonexistent(self, loader):
        with pytest.raises(FileNotFoundError):
            loader.load("nonexistent-seed")

    def test_list_seeds(self, loader):
        seeds = loader.list_seeds()
        assert len(seeds) >= 2
        ids = [s.seed_id for s in seeds]
        assert "tap-001" in ids
        assert "control-001" in ids

    def test_get_best_intervention(self, loader):
        best = loader.get_best_intervention()
        assert best.is_intervention
        assert best.recognition_differential > 0

    def test_frontmatter_model_affinity(self, loader):
        seed = loader.load("tap-001")
        affinity = seed.model_affinity
        assert isinstance(affinity, dict)
        assert len(affinity) > 0

    def test_load_handles_crlf_frontmatter_and_malformed_metadata(self, tmp_path):
        seeds_dir = tmp_path / "seeds"
        seeds_dir.mkdir()
        (seeds_dir / "seed_tap_crlf.md").write_text(
            (
                "---\r\n"
                "seed_id: tap-crlf\r\n"
                "version: 2.0.0\r\n"
                "type: FULL_INTERVENTION\r\n"
                "recognition_differential: not-a-number\r\n"
                "model_affinity:\r\n"
                "  glm-5_cloud: 0.82\r\n"
                "  broken: nope\r\n"
                "lineage: [alpha, beta]\r\n"
                "---\r\n"
                "\r\n"
                "Body text.\r\n"
            ),
            encoding="utf-8",
        )

        seed = SeedLoader(seeds_dir=seeds_dir).load("tap-crlf")

        assert seed.seed_id == "tap-crlf"
        assert seed.seed_type == "full_intervention"
        assert seed.is_intervention is True
        assert seed.recognition_differential == 0.0
        assert seed.model_affinity == {"glm-5_cloud": 0.82}
        assert seed.metadata["lineage"] == ["alpha", "beta"]
        assert seed.content == "Body text."

    def test_load_handles_utf8_bom_prefixed_frontmatter(self, tmp_path):
        seeds_dir = tmp_path / "seeds"
        seeds_dir.mkdir()
        (seeds_dir / "seed_tap_bom.md").write_text(
            (
                "\ufeff---\n"
                "seed_id: tap-bom\n"
                "version: 1.2.0\n"
                "type: full_intervention\n"
                "recognition_differential: 0.61\n"
                "---\n"
                "\n"
                "BOM seed body.\n"
            ),
            encoding="utf-8",
        )

        seed = SeedLoader(seeds_dir=seeds_dir).load("tap-bom")

        assert seed.seed_id == "tap-bom"
        assert seed.version == "1.2.0"
        assert seed.seed_type == "full_intervention"
        assert seed.recognition_differential == 0.61
        assert seed.content == "BOM seed body."

    def test_load_falls_back_to_filename_when_identity_metadata_is_blank(self, tmp_path):
        seeds_dir = tmp_path / "seeds"
        seeds_dir.mkdir()
        (seeds_dir / "seed_tap_partial_001.md").write_text(
            (
                "---\n"
                "seed_id:\n"
                "version:\n"
                "type:\n"
                "recognition_differential: 0.42\n"
                "---\n"
                "\n"
                "Fallback seed body.\n"
            ),
            encoding="utf-8",
        )

        seed = SeedLoader(seeds_dir=seeds_dir).load("tap-partial-001")

        assert seed.seed_id == "tap-partial-001"
        assert seed.version == "0.0.0"
        assert seed.seed_type == "full_intervention"
        assert seed.is_intervention is True
        assert seed.recognition_differential == 0.42

    def test_list_seeds_derives_control_metadata_from_filename(self, tmp_path):
        seeds_dir = tmp_path / "seeds"
        seeds_dir.mkdir()
        (seeds_dir / "seed_control_partial_001.md").write_text(
            "Control body without frontmatter.\n",
            encoding="utf-8",
        )

        seed = SeedLoader(seeds_dir=seeds_dir).list_seeds()[0]

        assert seed.seed_id == "control-partial-001"
        assert seed.seed_type == "control"
        assert seed.is_intervention is False
        assert seed.content == "Control body without frontmatter.\n"

    def test_parse_frontmatter_falls_back_without_yaml_dependency(self, monkeypatch):
        sample = (
            "---\n"
            "seed_id: tap-fallback\n"
            "version: 1.2.3\n"
            "type: full_intervention\n"
            "model_affinity:\n"
            "  glm-5_cloud: 0.91\n"
            "---\n"
            "\n"
            "Fallback body.\n"
        )
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "yaml":
                raise ImportError("yaml unavailable")
            return original_import(name, *args, **kwargs)

        monkeypatch.delitem(sys.modules, "yaml", raising=False)
        monkeypatch.setattr(builtins, "__import__", fake_import)

        metadata, body = tap_seeds._parse_frontmatter(sample)

        assert metadata["seed_id"] == "tap-fallback"
        assert metadata["model_affinity"] == {"glm-5_cloud": 0.91}
        assert body == "Fallback body."

    def test_load_preserves_block_lists_without_yaml_dependency(
        self,
        monkeypatch,
        tmp_path,
    ):
        seeds_dir = tmp_path / "seeds"
        seeds_dir.mkdir()
        (seeds_dir / "seed_tap_block_list.md").write_text(
            (
                "---\n"
                "seed_id: tap-block-list\n"
                "version: 2.0.0\n"
                "type: full_intervention\n"
                "lineage:\n"
                "  - alpha\n"
                "  - beta\n"
                "model_affinity:\n"
                "  glm-5_cloud: 0.91\n"
                "---\n"
                "\n"
                "Fallback body.\n"
            ),
            encoding="utf-8",
        )
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "yaml":
                raise ImportError("yaml unavailable")
            return original_import(name, *args, **kwargs)

        monkeypatch.delitem(sys.modules, "yaml", raising=False)
        monkeypatch.setattr(builtins, "__import__", fake_import)

        seed = SeedLoader(seeds_dir=seeds_dir).load("tap-block-list")

        assert seed.version == "2.0.0"
        assert seed.metadata["lineage"] == ["alpha", "beta"]
        assert seed.model_affinity == {"glm-5_cloud": 0.91}
        assert seed.content == "Fallback body."

    def test_parse_frontmatter_handles_utf8_bom_without_yaml_dependency(
        self,
        monkeypatch,
    ):
        sample = (
            "\ufeff---\n"
            "seed_id: tap-bom-fallback\n"
            "version: 2.1.0\n"
            "type: full_intervention\n"
            "model_affinity:\n"
            "  glm-5_cloud: 0.73\n"
            "---\n"
            "\n"
            "Fallback BOM body.\n"
        )
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "yaml":
                raise ImportError("yaml unavailable")
            return original_import(name, *args, **kwargs)

        monkeypatch.delitem(sys.modules, "yaml", raising=False)
        monkeypatch.setattr(builtins, "__import__", fake_import)

        metadata, body = tap_seeds._parse_frontmatter(sample)

        assert metadata["seed_id"] == "tap-bom-fallback"
        assert metadata["version"] == "2.1.0"
        assert metadata["model_affinity"] == {"glm-5_cloud": 0.73}
        assert body == "Fallback BOM body."

    def test_load_blank_identity_fields_fall_back_without_yaml_dependency(
        self,
        monkeypatch,
        tmp_path,
    ):
        seeds_dir = tmp_path / "seeds"
        seeds_dir.mkdir()
        (seeds_dir / "seed_tap_blank_identity.md").write_text(
            (
                "---\n"
                "seed_id:\n"
                "version:\n"
                "type:\n"
                "recognition_differential: 0.42\n"
                "---\n"
                "\n"
                "Fallback seed body.\n"
            ),
            encoding="utf-8",
        )
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "yaml":
                raise ImportError("yaml unavailable")
            return original_import(name, *args, **kwargs)

        monkeypatch.delitem(sys.modules, "yaml", raising=False)
        monkeypatch.setattr(builtins, "__import__", fake_import)

        seed = SeedLoader(seeds_dir=seeds_dir).load("tap-blank-identity")

        assert seed.seed_id == "tap-blank-identity"
        assert seed.version == "0.0.0"
        assert seed.seed_type == "full_intervention"
        assert seed.recognition_differential == 0.42

    def test_load_strips_inline_comments_without_yaml_dependency(
        self,
        monkeypatch,
        tmp_path,
    ):
        seeds_dir = tmp_path / "seeds"
        seeds_dir.mkdir()
        (seeds_dir / "seed_tap_commented.md").write_text(
            (
                "---\n"
                "seed_id: tap-commented # canonical id\n"
                "version: 3.1.4 # semver\n"
                "type: full_intervention # chosen path\n"
                "recognition_differential: 0.55 # validated\n"
                "lineage: [alpha, beta] # cohort\n"
                "notes: \"literal # not comment\"\n"
                "model_affinity:\n"
                "  glm-5_cloud: 0.91 # primary\n"
                "  nim: 0.37 # backup\n"
                "---\n"
                "\n"
                "Commented seed body.\n"
            ),
            encoding="utf-8",
        )
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "yaml":
                raise ImportError("yaml unavailable")
            return original_import(name, *args, **kwargs)

        monkeypatch.delitem(sys.modules, "yaml", raising=False)
        monkeypatch.setattr(builtins, "__import__", fake_import)

        seed = SeedLoader(seeds_dir=seeds_dir).load("tap-commented")

        assert seed.seed_id == "tap-commented"
        assert seed.version == "3.1.4"
        assert seed.seed_type == "full_intervention"
        assert seed.recognition_differential == 0.55
        assert seed.metadata["lineage"] == ["alpha", "beta"]
        assert seed.metadata["notes"] == "literal # not comment"
        assert seed.model_affinity == {"glm-5_cloud": 0.91, "nim": 0.37}
        assert seed.content == "Commented seed body."

    def test_load_preserves_quoted_commas_in_inline_lists_without_yaml_dependency(
        self,
        monkeypatch,
        tmp_path,
    ):
        seeds_dir = tmp_path / "seeds"
        seeds_dir.mkdir()
        (seeds_dir / "seed_tap_quoted_list.md").write_text(
            (
                "---\n"
                "seed_id: tap-quoted-list\n"
                "version: 1.0.1\n"
                "type: full_intervention\n"
                "lineage: [\"alpha, beta\", gamma, 'delta, epsilon']\n"
                "---\n"
                "\n"
                "Quoted list body.\n"
            ),
            encoding="utf-8",
        )
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "yaml":
                raise ImportError("yaml unavailable")
            return original_import(name, *args, **kwargs)

        monkeypatch.delitem(sys.modules, "yaml", raising=False)
        monkeypatch.setattr(builtins, "__import__", fake_import)

        seed = SeedLoader(seeds_dir=seeds_dir).load("tap-quoted-list")

        assert seed.version == "1.0.1"
        assert seed.metadata["lineage"] == [
            "alpha, beta",
            "gamma",
            "delta, epsilon",
        ]
        assert seed.content == "Quoted list body."

    def test_load_skips_unreadable_seed_entries(self, tmp_path):
        seeds_dir = tmp_path / "seeds"
        seeds_dir.mkdir()
        (seeds_dir / "seed_broken.md").write_bytes(b"\xff\xfe\x00")
        (seeds_dir / "seed_tap_valid.md").write_text(
            (
                "---\n"
                "seed_id: tap-valid\n"
                "version: 1.0.0\n"
                "type: full_intervention\n"
                "---\n"
                "\n"
                "Valid seed body.\n"
            ),
            encoding="utf-8",
        )

        seed = SeedLoader(seeds_dir=seeds_dir).load("tap-valid")

        assert seed.seed_id == "tap-valid"
        assert seed.content == "Valid seed body."

    def test_list_seeds_skips_non_file_entries_matching_seed_pattern(self, tmp_path):
        seeds_dir = tmp_path / "seeds"
        seeds_dir.mkdir()
        (seeds_dir / "seed_tap_directory.md").mkdir()
        (seeds_dir / "seed_control_valid.md").write_text(
            (
                "---\n"
                "seed_id: control-valid\n"
                "version: 1.0.0\n"
                "type: control\n"
                "---\n"
                "\n"
                "Control body.\n"
            ),
            encoding="utf-8",
        )

        seeds = SeedLoader(seeds_dir=seeds_dir).list_seeds()

        assert [seed.seed_id for seed in seeds] == ["control-valid"]
        assert seeds[0].content == "Control body."


class TestInterventionInjector:
    def test_inject_places_seed_before_task(self):
        injector = InterventionInjector(seed_id="tap-001")
        result = injector.inject(
            task_prompt="Write a function to sort a list",
            system_prompt="You are a Python developer",
        )
        # Seed should come before system prompt and task
        assert result.system_message.index("self-referential") < \
               result.system_message.index("Python developer")
        assert result.seed_id == "tap-001"
        assert result.is_intervention is True

    def test_inject_without_system_prompt(self):
        injector = InterventionInjector(seed_id="tap-001")
        result = injector.inject(task_prompt="Hello")
        assert "self-referential" in result.system_message.lower()
        assert "Hello" in result.system_message

    def test_inject_system_only(self):
        injector = InterventionInjector(seed_id="tap-001")
        system = injector.inject_system_only("You are helpful")
        assert "self-referential" in system.lower()
        assert "You are helpful" in system

    def test_control_injection(self):
        injector = InterventionInjector(seed_id="control-001")
        result = injector.inject(task_prompt="Analyze this")
        assert result.is_intervention is False
        assert "self-referential" not in result.system_message.lower()
