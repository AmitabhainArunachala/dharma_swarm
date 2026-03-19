"""Additional quality-track tests for dharma_swarm.ecosystem_map."""

from __future__ import annotations

from pathlib import Path

import pytest

import dharma_swarm.ecosystem_map as em


def test_every_domain_has_description_and_paths():
    for domain, info in em.ECOSYSTEM.items():
        assert isinstance(domain, str) and domain
        assert isinstance(info["description"], str) and info["description"]
        assert isinstance(info["paths"], list) and info["paths"]


def test_every_path_entry_is_two_tuple_with_tilde_path():
    for info in em.ECOSYSTEM.values():
        for entry in info["paths"]:
            assert isinstance(entry, tuple)
            assert len(entry) == 2
            path_str, desc = entry
            assert (
                path_str.startswith("~/")
                or path_str.startswith("~.")
                or ":" in path_str  # remote paths like agni:/home/...
                or path_str.startswith("http")  # URL paths
            )
            assert isinstance(desc, str) and desc


def test_get_context_for_invalid_domain_lists_available_domains():
    out = em.get_context_for("invalid-domain")
    assert out.startswith("Unknown domain")
    for key in em.ECOSYSTEM.keys():
        assert key in out


def test_get_context_for_has_header_and_generated_line():
    out = em.get_context_for("research")
    lines = out.splitlines()
    assert lines[0].startswith("# Dhyana's Filesystem")
    assert any(line.startswith("Generated:") for line in lines)


def test_get_context_for_single_domain_does_not_emit_other_domain_headers():
    out = em.get_context_for("ops")
    assert "## OPS:" in out
    assert "## RESEARCH:" not in out
    assert "## CONTENT:" not in out


def test_get_context_for_all_emits_all_domain_headers():
    out = em.get_context_for("all")
    for key in em.ECOSYSTEM.keys():
        assert f"## {key.upper()}:" in out


def test_get_context_for_marker_output_is_ok_when_exists(monkeypatch):
    monkeypatch.setattr(Path, "exists", lambda self: True)
    out = em.get_context_for("identity")
    assert "[OK]" in out
    assert "[MISSING]" not in out


def test_get_context_for_marker_output_is_missing_when_absent(monkeypatch):
    monkeypatch.setattr(Path, "exists", lambda self: False)
    out = em.get_context_for("identity")
    assert "[MISSING]" in out


def test_check_health_all_ok(monkeypatch):
    monkeypatch.setattr(Path, "exists", lambda self: True)
    h = em.check_health()
    assert h["missing"] == 0
    assert h["ok"] > 0
    assert h["details"] == {}


def test_check_health_all_missing(monkeypatch):
    monkeypatch.setattr(Path, "exists", lambda self: False)
    h = em.check_health()
    total_paths = sum(len(v["paths"]) for v in em.ECOSYSTEM.values())
    assert h["ok"] == 0
    # missing counts all entries (including duplicates across domains)
    assert h["ok"] + h["missing"] == total_paths
    # details dict deduplicates by path string
    assert len(h["details"]) > 0


def test_check_health_details_include_missing_prefix(monkeypatch):
    monkeypatch.setattr(Path, "exists", lambda self: False)
    h = em.check_health()
    assert all(str(v).startswith("MISSING --") for v in h["details"].values())
