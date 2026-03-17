"""Tests for dharma_swarm.dharma_kernel -- DharmaKernel + KernelGuard."""

import json

import pytest

from dharma_swarm.dharma_kernel import (
    DharmaKernel,
    KernelGuard,
    MetaPrinciple,
    PrincipleSpec,
)


# ---------------------------------------------------------------------------
# DharmaKernel -- creation and signature
# ---------------------------------------------------------------------------


def test_create_default():
    """Default kernel has 25 principles and a non-empty signature."""
    kernel = DharmaKernel.create_default()
    assert len(kernel.principles) == 25
    assert kernel.signature != ""
    assert len(kernel.signature) == 64  # SHA-256 hex digest


def test_all_principles_present():
    """Every MetaPrinciple enum value is a key in the default kernel."""
    kernel = DharmaKernel.create_default()
    for mp in MetaPrinciple:
        assert mp.value in kernel.principles, f"Missing principle: {mp.value}"


def test_signature_deterministic():
    """Two independently created default kernels produce the same signature."""
    k1 = DharmaKernel.create_default()
    k2 = DharmaKernel.create_default()
    assert k1.compute_signature() == k2.compute_signature()


def test_verify_integrity_clean():
    """A freshly created kernel passes integrity verification."""
    kernel = DharmaKernel.create_default()
    assert kernel.verify_integrity() is True


def test_tamper_detection():
    """Modifying a description causes integrity verification to fail."""
    kernel = DharmaKernel.create_default()
    key = MetaPrinciple.OBSERVER_SEPARATION.value
    kernel.principles[key].description = "TAMPERED"
    assert kernel.verify_integrity() is False


def test_tamper_signature_detection():
    """Replacing the signature with garbage causes verification to fail."""
    kernel = DharmaKernel.create_default()
    kernel.signature = "0" * 64
    assert kernel.verify_integrity() is False


def test_compute_signature_changes_on_mutation():
    """Mutating any principle changes the computed signature."""
    kernel = DharmaKernel.create_default()
    original_sig = kernel.compute_signature()
    key = MetaPrinciple.POWER_MINIMIZATION.value
    kernel.principles[key].formal_constraint = "changed"
    assert kernel.compute_signature() != original_sig


def test_json_roundtrip():
    """Dumping to dict and recreating preserves integrity."""
    kernel = DharmaKernel.create_default()
    data = kernel.model_dump()
    restored = DharmaKernel.model_validate(data)
    assert restored.verify_integrity() is True
    assert restored.signature == kernel.signature
    assert len(restored.principles) == 25


# ---------------------------------------------------------------------------
# KernelGuard -- persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kernel_guard_save_load(tmp_path):
    """Save a kernel, load it back, verify integrity holds."""
    path = tmp_path / "kernel.json"
    guard = KernelGuard(kernel_path=path)
    kernel = DharmaKernel.create_default()
    await guard.save(kernel)

    guard2 = KernelGuard(kernel_path=path)
    loaded = await guard2.load()
    assert loaded.verify_integrity() is True
    assert loaded.signature == kernel.signature
    assert len(loaded.principles) == 25


@pytest.mark.asyncio
async def test_kernel_guard_tamper_detection(tmp_path):
    """Modifying the on-disk JSON causes load to raise ValueError."""
    path = tmp_path / "kernel.json"
    guard = KernelGuard(kernel_path=path)
    kernel = DharmaKernel.create_default()
    await guard.save(kernel)

    # Tamper with the file on disk
    raw = json.loads(path.read_text())
    first_key = next(iter(raw["principles"]))
    raw["principles"][first_key]["description"] = "TAMPERED"
    path.write_text(json.dumps(raw))

    guard2 = KernelGuard(kernel_path=path)
    with pytest.raises(ValueError, match="tampering"):
        await guard2.load()


# ---------------------------------------------------------------------------
# KernelGuard -- downward causation
# ---------------------------------------------------------------------------


def test_downward_causation_higher_constrains_lower():
    """A higher layer (3) can constrain a lower layer (1)."""
    assert KernelGuard.check_downward_causation(3, 1) is True


def test_downward_causation_lower_cannot_constrain_higher():
    """A lower layer (1) cannot constrain a higher layer (3)."""
    assert KernelGuard.check_downward_causation(1, 3) is False


def test_downward_causation_same_layer():
    """Same-layer constraint is permitted."""
    assert KernelGuard.check_downward_causation(2, 2) is True


# ---------------------------------------------------------------------------
# Severity distribution
# ---------------------------------------------------------------------------


def test_severity_values():
    """At least 3 principles are critical; rest are high or medium."""
    kernel = DharmaKernel.create_default()
    severities = [p.severity for p in kernel.principles.values()]
    critical_count = severities.count("critical")
    assert critical_count >= 3, f"Expected >= 3 critical, got {critical_count}"
    for sev in severities:
        assert sev in ("critical", "high", "medium"), f"Unexpected severity: {sev}"
