"""Enforce architectural layer boundaries via import analysis.

Layer 0 (constitution): telos_gates, dharma_kernel, invariants
Layer 1 (substrate): traces, signal_bus, message_bus, telemetry_plane
Layer 2 (services): orchestrator, providers, agent_runner, checkpoint, handoff, models
Layer 3 (living): evolution, stigmergy, strange_loop, organism, cascade, diversity_archive
Layer 4 (surface): swarmlens_app, dgc_cli
Layer 5 (verification): monitor, vsm_channels, transcendence_metrics

Rule: Lower layers MUST NOT import from higher layers.
Exception: models.py is L2 but used everywhere (it's the schema layer).
"""

import ast
from pathlib import Path

import pytest

DHARMA_SWARM_DIR = Path(__file__).parent.parent / "dharma_swarm"

# Module name → layer number
LAYER_MAP: dict[str, int] = {}

_LAYER_DEFS: dict[int, set[str]] = {
    0: {"telos_gates", "dharma_kernel", "invariants"},
    1: {"traces", "signal_bus", "message_bus", "telemetry_plane"},
    2: {"orchestrator", "providers", "agent_runner", "checkpoint", "handoff", "models"},
    3: {"evolution", "stigmergy", "strange_loop", "organism", "cascade", "diversity_archive"},
    4: {"swarmlens_app", "dgc_cli"},
    5: {"monitor", "vsm_channels", "transcendence_metrics"},
}

# Build reverse map
for layer_num, modules in _LAYER_DEFS.items():
    for mod in modules:
        LAYER_MAP[mod] = layer_num

# Exceptions: models.py is the schema layer, used everywhere
EXEMPT_IMPORTS = {"models", "config"}


def _extract_imports(filepath: Path) -> list[str]:
    """Extract dharma_swarm module names imported by a file."""
    try:
        tree = ast.parse(filepath.read_text())
    except SyntaxError:
        return []

    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("dharma_swarm."):
                # Extract the module name after dharma_swarm.
                parts = node.module.split(".")
                if len(parts) >= 2:
                    imports.append(parts[1])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("dharma_swarm."):
                    parts = alias.name.split(".")
                    if len(parts) >= 2:
                        imports.append(parts[1])
    return imports


def _find_violations() -> list[str]:
    """Find all layer boundary violations."""
    violations = []

    for py_file in sorted(DHARMA_SWARM_DIR.glob("*.py")):
        module_name = py_file.stem
        if module_name.startswith("_"):
            continue

        source_layer = LAYER_MAP.get(module_name)
        if source_layer is None:
            continue  # Module not in any layer — skip

        imports = _extract_imports(py_file)
        for imported_mod in imports:
            if imported_mod in EXEMPT_IMPORTS:
                continue

            target_layer = LAYER_MAP.get(imported_mod)
            if target_layer is None:
                continue  # Imported module not in any layer — skip

            if target_layer > source_layer:
                violations.append(
                    f"{module_name} (L{source_layer}) imports {imported_mod} (L{target_layer})"
                )

    return violations


def test_no_upward_imports():
    """No module in layer N imports from layer N+1 or higher.

    Exceptions: models.py (schema layer) is exempt.
    This test documents the CURRENT violations and tracks progress.
    """
    violations = _find_violations()

    # For now: report violations but track count
    # As we fix violations, lower this number until it reaches 0
    MAX_ALLOWED_VIOLATIONS = 50  # Start permissive, tighten over time

    if len(violations) > MAX_ALLOWED_VIOLATIONS:
        violation_text = "\n".join(f"  - {v}" for v in violations[:20])
        pytest.fail(
            f"Too many layer violations ({len(violations)} > {MAX_ALLOWED_VIOLATIONS}):\n"
            f"{violation_text}\n  ... and {len(violations) - 20} more"
            if len(violations) > 20 else
            f"Too many layer violations ({len(violations)} > {MAX_ALLOWED_VIOLATIONS}):\n"
            f"{violation_text}"
        )
    elif violations:
        # Report violations as a warning but don't fail yet
        print(f"\nLayer violations ({len(violations)}, max allowed {MAX_ALLOWED_VIOLATIONS}):")
        for v in violations[:10]:
            print(f"  - {v}")
        if len(violations) > 10:
            print(f"  ... and {len(violations) - 10} more")


def test_layer_map_covers_key_modules():
    """Verify that the layer map includes all critical modules."""
    key_modules = [
        "telos_gates", "dharma_kernel", "orchestrator", "evolution",
        "signal_bus", "monitor", "models",
    ]
    for mod in key_modules:
        assert mod in LAYER_MAP, f"Module {mod} not in layer map"
