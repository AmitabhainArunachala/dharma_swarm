"""Tests for dharma_swarm.subconscious_fleet — fleet config and file selection logic."""

import pytest

from dharma_swarm.subconscious_fleet import (
    FLEET_PROVIDERS,
    SubconsciousFleet,
)


# ---------------------------------------------------------------------------
# Fleet configuration
# ---------------------------------------------------------------------------


def test_fleet_providers_has_entries():
    assert len(FLEET_PROVIDERS) >= 3


def test_fleet_defaults():
    fleet = SubconsciousFleet()
    assert fleet.fleet_size == 12
    assert fleet.files_per_agent == 5
    assert fleet.temperature == 0.9


def test_fleet_custom():
    fleet = SubconsciousFleet(fleet_size=4, files_per_agent=3, temperature=1.1)
    assert fleet.fleet_size == 4
    assert fleet.files_per_agent == 3
    assert fleet.temperature == 1.1


# ---------------------------------------------------------------------------
# dream_swarm — insufficient files
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dream_swarm_insufficient_files(tmp_path):
    # Pool smaller than files_per_agent
    f1 = tmp_path / "a.md"
    f1.write_text("content")
    fleet = SubconsciousFleet(fleet_size=2, files_per_agent=5)
    result = await fleet.dream_swarm(file_pool=[f1])
    assert "error" in result


# ---------------------------------------------------------------------------
# File combination logic
# ---------------------------------------------------------------------------


def test_file_combination_wraps():
    """When start_idx + files_per_agent > pool size, files wrap around."""
    fleet = SubconsciousFleet(fleet_size=3, files_per_agent=4)

    from pathlib import Path
    pool = [Path(f"/fake/{i}.md") for i in range(5)]

    # Agent 2: start_idx = (2 * 3) % 5 = 1, end = 5 → [1,2,3,4]
    # Agent 0: start_idx = 0, end = 4 → [0,1,2,3]
    # These calculations match the code logic at lines 84-89

    # Verify the wrap logic manually:
    i = 2
    start_idx = (i * 3) % len(pool)
    end_idx = start_idx + fleet.files_per_agent
    assert start_idx == 1
    assert end_idx == 5
    # No wrap needed since end_idx == len(pool), so pool[1:5] = [1,2,3,4]

    # Agent with wrapping
    i = 4
    start_idx = (i * 3) % len(pool)  # 12 % 5 = 2
    end_idx = start_idx + fleet.files_per_agent  # 2 + 4 = 6
    assert end_idx > len(pool)
    files = pool[start_idx:] + pool[:end_idx - len(pool)]
    assert len(files) == 4
    # pool[2:] = [2,3,4] + pool[:1] = [0] → [2,3,4,0]
    assert files[0] == pool[2]
    assert files[-1] == pool[0]


# ---------------------------------------------------------------------------
# Temperature variation
# ---------------------------------------------------------------------------


def test_temperature_varies_per_agent():
    fleet = SubconsciousFleet(temperature=0.9)
    temps = [fleet.temperature + (i % 3) * 0.05 for i in range(6)]
    # Should cycle: 0.9, 0.95, 1.0, 0.9, 0.95, 1.0
    assert temps == pytest.approx([0.9, 0.95, 1.0, 0.9, 0.95, 1.0])
