from dharma_swarm.mode_pack import load_mode_pack


def test_mode_pack_contract_loads() -> None:
    contract = load_mode_pack()
    assert contract.pack_name == "dharma-swarm-mode-pack"
    assert contract.schema_version == "1.0.0"
    assert len(contract.modes) == 9


def test_mode_pack_exposes_expected_runtime_aliases() -> None:
    contract = load_mode_pack()
    ceo_review = contract.get_mode("ceo-review")
    assert ceo_review.runtime_aliases["claude_skill"] == "dharma-ceo-review"
    assert ceo_review.handoff_to == ["eng-review"]

    alias_map = contract.runtime_alias_map("dgc_lane")
    assert alias_map["incident-commander"] == "incident_commander"
    assert alias_map["qa"] == "qa"
