"""Typed loader for the shared Dharma Swarm mode pack contract."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field


MODE_PACK_CONTRACT = (
    Path(__file__).resolve().parents[1]
    / "mode_pack"
    / "contracts"
    / "mode_pack.v1.json"
)


class ModeContract(BaseModel):
    slug: str
    title: str
    summary: str
    runtime_aliases: dict[str, str] = Field(default_factory=dict)
    allowed_tools: list[str] = Field(default_factory=list)
    required_outputs: list[str] = Field(default_factory=list)
    required_artifacts: list[str] = Field(default_factory=list)
    escalation_triggers: list[str] = Field(default_factory=list)
    handoff_to: list[str] = Field(default_factory=list)
    non_goals: list[str] = Field(default_factory=list)


class ModePackContract(BaseModel):
    schema_version: str
    pack_name: str
    generated_for: list[str] = Field(default_factory=list)
    modes: list[ModeContract] = Field(default_factory=list)

    def get_mode(self, slug: str) -> ModeContract:
        for mode in self.modes:
            if mode.slug == slug:
                return mode
        raise KeyError(f"Unknown mode slug: {slug}")

    def runtime_alias_map(self, runtime: str) -> dict[str, str]:
        alias_map: dict[str, str] = {}
        for mode in self.modes:
            alias = mode.runtime_aliases.get(runtime)
            if alias:
                alias_map[mode.slug] = alias
        return alias_map


@lru_cache(maxsize=1)
def load_mode_pack(path: str | Path | None = None) -> ModePackContract:
    contract_path = Path(path) if path is not None else MODE_PACK_CONTRACT
    payload = json.loads(contract_path.read_text())
    return ModePackContract.model_validate(payload)
