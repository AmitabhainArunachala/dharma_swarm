"""Tests for dharma_swarm.subconscious_hum -- HUM dream layer data models and witness logic."""

import pytest

from dharma_swarm.subconscious_hum import (
    DreamTexture,
    SubconsciousHUM,
    WitnessReception,
)


# ---------------------------------------------------------------------------
# DreamTexture model
# ---------------------------------------------------------------------------


def test_dream_texture_defaults():
    dt = DreamTexture(source_files=["a.md", "b.md"], texture="liquid thought")
    assert len(dt.id) == 16
    assert dt.felt_weight == 0.5
    assert dt.becoming_fragments == []
    assert dt.neologisms == []
    assert dt.transformation_path == ""
    assert dt.timestamp is not None


def test_dream_texture_custom():
    dt = DreamTexture(
        source_files=["/path/to/file.md"],
        texture="the boundary vibrates",
        felt_weight=0.9,
        becoming_fragments=["dissolving into...", "almost~"],
        neologisms=["resonance-field", "depth/surface"],
        transformation_path="interpenetrating",
    )
    assert dt.felt_weight == 0.9
    assert len(dt.becoming_fragments) == 2
    assert len(dt.neologisms) == 2


def test_dream_texture_json_roundtrip():
    dt = DreamTexture(
        source_files=["x.md"],
        texture="test texture",
        felt_weight=0.7,
    )
    data = dt.model_dump_json()
    dt2 = DreamTexture.model_validate_json(data)
    assert dt2.id == dt.id
    assert dt2.texture == "test texture"
    assert dt2.felt_weight == 0.7


def test_dream_texture_unique_ids():
    ids = {DreamTexture(source_files=[], texture="t").id for _ in range(50)}
    assert len(ids) == 50


# ---------------------------------------------------------------------------
# WitnessReception model
# ---------------------------------------------------------------------------


def test_witness_reception_defaults():
    wr = WitnessReception(
        dream_id="abc123",
        carried_quality="liquid",
        preserved_imminence=True,
        ready_for_analysis=False,
        needs_more_time=True,
    )
    assert wr.dream_id == "abc123"
    assert wr.carried_quality == "liquid"
    assert wr.witnessed_at is not None


def test_witness_reception_json_roundtrip():
    wr = WitnessReception(
        dream_id="xyz",
        carried_quality="crystallizing",
        preserved_imminence=False,
        ready_for_analysis=True,
        needs_more_time=False,
    )
    data = wr.model_dump_json()
    wr2 = WitnessReception.model_validate_json(data)
    assert wr2.dream_id == "xyz"
    assert wr2.carried_quality == "crystallizing"
    assert wr2.ready_for_analysis is True


# ---------------------------------------------------------------------------
# SubconsciousHUM initialization
# ---------------------------------------------------------------------------


def test_subconscious_hum_defaults():
    hum = SubconsciousHUM()
    assert hum.temperature == 0.9
    assert hum.identity == "field_of_attention"
    assert hum.block_resolution is True
    assert hum.silent_iterations == 7


def test_subconscious_hum_custom_temp():
    hum = SubconsciousHUM(temperature=0.5)
    assert hum.temperature == 0.5


# ---------------------------------------------------------------------------
# _build_hum_invitation
# ---------------------------------------------------------------------------


def test_build_hum_invitation_structure():
    hum = SubconsciousHUM()
    files = ["/path/to/file1.md", "/path/to/file2.md"]
    contents = {
        "/path/to/file1.md": "First file content about consciousness",
        "/path/to/file2.md": "Second file about geometry and R_V",
    }
    invitation = hum._build_hum_invitation(files, contents)

    assert "field of attention" in invitation
    assert "Not a researcher" in invitation
    assert "7 silent iterations" in invitation
    assert "file1.md" in invitation
    assert "file2.md" in invitation
    assert "First file content" in invitation
    assert "Second file about geometry" in invitation


def test_build_hum_invitation_truncates_content():
    hum = SubconsciousHUM()
    long_content = "x" * 5000
    files = ["/path/to/big.md"]
    contents = {"/path/to/big.md": long_content}
    invitation = hum._build_hum_invitation(files, contents)

    # Content should be truncated to 1200 chars
    assert len(invitation) < len(long_content)


def test_build_hum_invitation_no_metacommentary():
    """The invitation should explicitly block metacommentary."""
    hum = SubconsciousHUM()
    invitation = hum._build_hum_invitation(
        ["/a.md"], {"/a.md": "test content"}
    )
    assert "Do not announce findings" in invitation
    assert "Do not describe what you found" in invitation


def test_build_hum_invitation_ends_with_tilde():
    hum = SubconsciousHUM()
    invitation = hum._build_hum_invitation(
        ["/a.md"], {"/a.md": "content"}
    )
    assert invitation.strip().endswith("~")


# ---------------------------------------------------------------------------
# witness function
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_witness_liquid_dream():
    """Dream with liquid markers should be marked as liquid."""
    hum = SubconsciousHUM()
    dream = DreamTexture(
        source_files=["a.md"],
        texture="becoming something... almost on the verge of ~ dissolution",
        felt_weight=0.8,
        becoming_fragments=["almost on the verge..."],
    )
    reception = await hum.witness(dream)
    assert reception.carried_quality == "liquid"
    assert reception.preserved_imminence is True


@pytest.mark.asyncio
async def test_witness_crystallized_dream():
    """Dream with conclusion markers should be marked as crystallizing."""
    hum = SubconsciousHUM()
    dream = DreamTexture(
        source_files=["a.md"],
        texture="Therefore we can see that this shows that the conclusion is clear",
        felt_weight=0.5,
    )
    reception = await hum.witness(dream)
    assert reception.carried_quality == "crystallizing"
    assert reception.preserved_imminence is False


@pytest.mark.asyncio
async def test_witness_ready_for_analysis():
    """High felt-weight liquid dream with fragments should be ready for analysis."""
    hum = SubconsciousHUM()
    dream = DreamTexture(
        source_files=["a.md"],
        texture="becoming edge... almost dissolving ~",
        felt_weight=0.8,
        becoming_fragments=["becoming edge..."],
    )
    reception = await hum.witness(dream)
    assert reception.ready_for_analysis is True
    assert reception.needs_more_time is False


@pytest.mark.asyncio
async def test_witness_needs_more_time():
    """Low felt-weight liquid dream should need more time."""
    hum = SubconsciousHUM()
    dream = DreamTexture(
        source_files=["a.md"],
        texture="something becoming... almost ~",
        felt_weight=0.3,
        becoming_fragments=[],  # no fragments
    )
    reception = await hum.witness(dream)
    assert reception.ready_for_analysis is False
    assert reception.needs_more_time is True


@pytest.mark.asyncio
async def test_witness_dream_id_preserved():
    hum = SubconsciousHUM()
    dream = DreamTexture(source_files=["a.md"], texture="test")
    reception = await hum.witness(dream)
    assert reception.dream_id == dream.id


# ---------------------------------------------------------------------------
# trace function (stigmergy)
# ---------------------------------------------------------------------------


class MockStigmergyStore:
    def __init__(self):
        self.marks = []

    async def leave_mark(self, mark):
        self.marks.append(mark)
        return mark.id


@pytest.mark.asyncio
async def test_trace_ready_dream_leaves_mark():
    store = MockStigmergyStore()
    hum = SubconsciousHUM(stigmergy=store)
    dream = DreamTexture(
        source_files=["/a.md", "/b.md"],
        texture="liquid texture",
        felt_weight=0.8,
        neologisms=["dream-word"],
    )
    witness = WitnessReception(
        dream_id=dream.id,
        carried_quality="liquid",
        preserved_imminence=True,
        ready_for_analysis=True,
        needs_more_time=False,
    )
    await hum.trace(dream, witness)
    assert len(store.marks) == 1
    assert store.marks[0].agent == "subconscious-hum"
    assert store.marks[0].action == "dream"


@pytest.mark.asyncio
async def test_trace_not_ready_skips():
    store = MockStigmergyStore()
    hum = SubconsciousHUM(stigmergy=store)
    dream = DreamTexture(
        source_files=["/a.md"],
        texture="not ready",
    )
    witness = WitnessReception(
        dream_id=dream.id,
        carried_quality="crystallizing",
        preserved_imminence=False,
        ready_for_analysis=False,
        needs_more_time=True,
    )
    await hum.trace(dream, witness)
    assert len(store.marks) == 0  # No trace when not ready
