"""Tests for dharma_swarm.subconscious_v2 — data models, dream prompt, file selection."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from dharma_swarm.models import LLMResponse, ProviderType
from dharma_swarm.subconscious_v2 import (
    DreamAssociation,
    ResonanceType,
    SubconsciousAgent,
    WakeTrigger,
)


# ---------------------------------------------------------------------------
# ResonanceType enum
# ---------------------------------------------------------------------------


def test_resonance_type_values():
    assert ResonanceType.STRUCTURAL_ISOMORPHISM == "structural_isomorphism"
    assert ResonanceType.UNKNOWN_RESONANCE == "unknown_resonance"
    assert len(ResonanceType) == 9


def test_resonance_type_from_string():
    assert ResonanceType("cross_domain_bridge") is ResonanceType.CROSS_DOMAIN_BRIDGE


# ---------------------------------------------------------------------------
# WakeTrigger enum
# ---------------------------------------------------------------------------


def test_wake_trigger_values():
    assert WakeTrigger.DENSITY_THRESHOLD == "density_threshold"
    assert WakeTrigger.EXPLICIT_CALL == "explicit_call"
    assert WakeTrigger.SCHEDULED == "scheduled"


# ---------------------------------------------------------------------------
# DreamAssociation model
# ---------------------------------------------------------------------------


def test_dream_association_defaults():
    da = DreamAssociation(
        source_files=["a.md", "b.md"],
        resonance_type=ResonanceType.STRUCTURAL_ISOMORPHISM,
        description="test connection",
    )
    assert len(da.id) == 16
    assert da.salience == 0.5
    assert da.evidence_fragments == []
    assert da.reasoning == ""
    assert da.timestamp is not None


def test_dream_association_custom():
    da = DreamAssociation(
        source_files=["/path/to/a.md"],
        resonance_type=ResonanceType.RECURSIVE_ECHO,
        description="recursive pattern",
        salience=0.9,
        evidence_fragments=["fragment1", "fragment2"],
        reasoning="deep recursion detected",
    )
    assert da.salience == 0.9
    assert len(da.evidence_fragments) == 2
    assert da.resonance_type is ResonanceType.RECURSIVE_ECHO


def test_dream_association_json_roundtrip():
    da = DreamAssociation(
        source_files=["x.md"],
        resonance_type=ResonanceType.CROSS_DOMAIN_BRIDGE,
        description="bridge",
        salience=0.7,
    )
    data = da.model_dump_json()
    da2 = DreamAssociation.model_validate_json(data)
    assert da2.id == da.id
    assert da2.resonance_type is ResonanceType.CROSS_DOMAIN_BRIDGE
    assert da2.salience == 0.7


def test_dream_association_unique_ids():
    ids = {
        DreamAssociation(
            source_files=[],
            resonance_type=ResonanceType.UNKNOWN_RESONANCE,
            description="t",
        ).id
        for _ in range(50)
    }
    assert len(ids) == 50


# ---------------------------------------------------------------------------
# SubconsciousAgent init + wake/sleep
# ---------------------------------------------------------------------------


def test_subconscious_agent_defaults():
    agent = SubconsciousAgent()
    assert agent.temperature == 0.9
    assert agent.mode == "dreamstate"
    assert agent.alignment == "lateral_association"
    assert agent.energy == "mahakali_liminal"


def test_subconscious_agent_custom_temp():
    agent = SubconsciousAgent(temperature=1.2, mode="deep")
    assert agent.temperature == 1.2
    assert agent.mode == "deep"


@pytest.mark.asyncio
async def test_wake():
    agent = SubconsciousAgent()
    state = await agent.wake(WakeTrigger.EXPLICIT_CALL)
    assert state["trigger"] == "explicit_call"
    assert state["mode"] == "dreamstate"
    assert state["temperature"] == 0.9
    assert "timestamp" in state


@pytest.mark.asyncio
async def test_sleep():
    agent = SubconsciousAgent()
    state = await agent.sleep()
    assert state["state"] == "dormant"
    assert "timestamp" in state


@pytest.mark.asyncio
async def test_find_dream_connection_uses_runtime_provider_stack():
    agent = SubconsciousAgent()

    with patch(
        "dharma_swarm.subconscious_v2.complete_via_preferred_runtime_providers",
        new=AsyncMock(
            side_effect=[
                (
                    LLMResponse(content="A hidden bridge appears ~", model="nim-local"),
                    SimpleNamespace(provider=ProviderType.NVIDIA_NIM),
                ),
                (
                    LLMResponse(
                        content='{"resonance_type":"cross_domain_bridge","description":"A hidden bridge appears","salience":0.8,"evidence_fragments":["hidden bridge"],"dream_prose":"A hidden bridge appears ~","reasoning":"deep pattern"}',
                        model="nim-local",
                    ),
                    SimpleNamespace(provider=ProviderType.NVIDIA_NIM),
                ),
            ]
        ),
    ):
        result = await agent._find_dream_connection(
            ["/tmp/a.md", "/tmp/b.md"],
            {
                "/tmp/a.md": "R_V collapse",
                "/tmp/b.md": "structural bridge",
            },
            "dream prompt",
        )

    assert result is not None
    assert result.resonance_type is ResonanceType.CROSS_DOMAIN_BRIDGE
    assert result.description == "A hidden bridge appears"


# ---------------------------------------------------------------------------
# _build_dream_prompt
# ---------------------------------------------------------------------------


def test_build_dream_prompt_structure():
    agent = SubconsciousAgent()
    files = ["/path/to/file1.md", "/path/to/file2.md"]
    contents = {
        "/path/to/file1.md": "Content about consciousness and collapse",
        "/path/to/file2.md": "Content about R_V and contraction",
    }
    prompt = agent._build_dream_prompt(files, contents)

    assert "file1.md" in prompt
    assert "file2.md" in prompt
    assert "Content about consciousness" in prompt
    assert "Content about R_V" in prompt
    assert "Dream 3-5 distinct associations" in prompt


def test_build_dream_prompt_truncates_long_content():
    agent = SubconsciousAgent()
    long_content = "x" * 30_000
    files = ["/path/to/big.md"]
    contents = {"/path/to/big.md": long_content}
    prompt = agent._build_dream_prompt(files, contents)

    # Should truncate to FILE_BUDGET (20K) or less
    assert len(prompt) < len(long_content)


def test_build_dream_prompt_truncates_at_paragraph_boundary():
    agent = SubconsciousAgent()
    # Build content with a paragraph break within the last 20% of budget
    budget = agent._FILE_BUDGET
    # Place a paragraph break at 85% of budget
    break_pos = int(budget * 0.85)
    content = "a" * break_pos + "\n\n" + "b" * (budget - break_pos + 5000)
    files = ["/path/to/file.md"]
    contents = {"/path/to/file.md": content}
    prompt = agent._build_dream_prompt(files, contents)

    # Should have truncated at the paragraph boundary
    assert "bbbbb" not in prompt


# ---------------------------------------------------------------------------
# _extract_concepts (dead code but still testable)
# ---------------------------------------------------------------------------


def test_extract_concepts_detects_patterns():
    agent = SubconsciousAgent()
    content = """
    The R_V metric shows collapse in dimensional space.
    A fixed point emerges under recursive self-observation.
    The L4 protocol witnesses contraction.
    """
    concepts = agent._extract_concepts(content, "test.md")

    assert concepts["filename"] == "test.md"
    assert concepts["has_R_V"] is True
    assert concepts["has_collapse"] is True
    assert concepts["has_dimensional"] is True
    assert concepts["has_fixed_point"] is True
    assert concepts["has_recursive"] is True
    assert concepts["has_witness"] is True
    assert concepts["has_L4_protocol"] is True
    assert concepts["has_contraction"] is True


def test_extract_concepts_minimal():
    agent = SubconsciousAgent()
    concepts = agent._extract_concepts("just some plain text", "plain.md")
    assert concepts["filename"] == "plain.md"
    assert "has_R_V" not in concepts
    assert "has_collapse" not in concepts


# ---------------------------------------------------------------------------
# _detect_structural_isomorphism (dead code but testable)
# ---------------------------------------------------------------------------


def test_detect_isomorphism_found():
    agent = SubconsciousAgent()
    files = ["pheno.md", "mech.md"]
    contents = {
        "pheno.md": "The L4 collapse happens when the witness observes itself. Dimensional reduction occurs.",
        "mech.md": "R_V contraction shows dimensional collapse under self-observation. Fixed point reached.",
    }
    file_concepts = {f: agent._extract_concepts(c, f) for f, c in contents.items()}
    result = agent._detect_structural_isomorphism(files, file_concepts, contents)

    assert result is not None
    assert result.resonance_type is ResonanceType.STRUCTURAL_ISOMORPHISM
    assert result.salience == 0.85
    assert len(result.evidence_fragments) > 0


def test_detect_isomorphism_not_found():
    agent = SubconsciousAgent()
    files = ["a.md", "b.md"]
    contents = {
        "a.md": "Just some plain text about cooking recipes.",
        "b.md": "Weather forecast for tomorrow looks sunny.",
    }
    file_concepts = {f: agent._extract_concepts(c, f) for f, c in contents.items()}
    result = agent._detect_structural_isomorphism(files, file_concepts, contents)

    assert result is None


# ---------------------------------------------------------------------------
# feed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feed_reads_files(tmp_path):
    f1 = tmp_path / "a.md"
    f2 = tmp_path / "b.md"
    f1.write_text("content a")
    f2.write_text("content b")

    agent = SubconsciousAgent()
    state = await agent.feed([f1, f2])

    assert state["files_loaded"] == 2
    assert state["total_chars"] == len("content a") + len("content b")
    assert str(f1) in state["contents"]
    assert str(f2) in state["contents"]


@pytest.mark.asyncio
async def test_feed_skips_missing_files(tmp_path):
    f1 = tmp_path / "exists.md"
    f1.write_text("hello")
    missing = tmp_path / "nope.md"

    agent = SubconsciousAgent()
    state = await agent.feed([f1, missing])

    assert state["files_loaded"] == 1


# ---------------------------------------------------------------------------
# dream with empty input
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dream_empty_contents():
    agent = SubconsciousAgent()
    result = await agent.dream({})
    assert result == []


# ---------------------------------------------------------------------------
# trace (stigmergy)
# ---------------------------------------------------------------------------


class MockStigmergyStore:
    def __init__(self):
        self.marks = []

    async def leave_mark(self, mark):
        self.marks.append(mark)
        return mark.id


@pytest.mark.asyncio
async def test_trace_high_salience():
    store = MockStigmergyStore()
    agent = SubconsciousAgent(stigmergy=store)

    associations = [
        DreamAssociation(
            source_files=["a.md", "b.md"],
            resonance_type=ResonanceType.STRUCTURAL_ISOMORPHISM,
            description="high salience dream",
            salience=0.8,
        ),
    ]
    await agent.trace(associations)
    assert len(store.marks) == 1
    assert store.marks[0].agent == "subconscious-v2"
    assert store.marks[0].action == "dream"


@pytest.mark.asyncio
async def test_trace_low_salience_skipped():
    store = MockStigmergyStore()
    agent = SubconsciousAgent(stigmergy=store)

    associations = [
        DreamAssociation(
            source_files=["a.md"],
            resonance_type=ResonanceType.UNKNOWN_RESONANCE,
            description="low salience noise",
            salience=0.3,
        ),
    ]
    await agent.trace(associations)
    assert len(store.marks) == 0


# ---------------------------------------------------------------------------
# HUM system prompt
# ---------------------------------------------------------------------------


def test_hum_system_prompt_content():
    assert "field of attention" in SubconsciousAgent._HUM_SYSTEM_PROMPT
    assert "Not a researcher" in SubconsciousAgent._HUM_SYSTEM_PROMPT
    assert "seven times" in SubconsciousAgent._HUM_SYSTEM_PROMPT
    assert "~" in SubconsciousAgent._HUM_SYSTEM_PROMPT
