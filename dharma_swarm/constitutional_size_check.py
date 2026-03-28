"""Constitutional size enforcement — Layer 0 must be smaller than Layer 3.

Power prompt commandment #3: "The constitution must be smaller than the metabolism."

This module provides a runtime gate that checks the Line-of-Code ratio between:
- **Layer 0 (Constitutional Kernel)**: dharma_kernel.py, telos_gates.py
- **Layer 3 (Living Adaptive Layers)**: stigmergy.py, shakti.py, subconscious.py, 
  evolution.py, organism.py, strange_loop.py

The check runs at boot and fails if Layer 0 > Layer 3.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def count_lines_of_code(file_path: Path) -> int:
    """Count non-empty, non-comment lines in a Python file."""
    if not file_path.exists():
        return 0
    
    count = 0
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    count += 1
    except Exception as e:
        logger.debug(f"Failed to count lines in {file_path}: {e}")
        return 0
    
    return count


def check_constitutional_size() -> tuple[bool, str]:
    """Verify Layer 0 < Layer 3 in LOC.
    
    Returns:
        (passed, message): True if Layer 0 < Layer 3, False otherwise.
    """
    # Assume we're running from installed package or repo root
    try:
        from dharma_swarm import __file__ as swarm_init
        base = Path(swarm_init).parent
    except Exception:
        # Fallback: assume CWD is dharma_swarm root
        base = Path.cwd() / "dharma_swarm"
    
    # Layer 0: Constitutional Kernel
    layer0_files = [
        base / "dharma_kernel.py",
        base / "telos_gates.py",
    ]
    
    # Layer 3: Living Adaptive Layers
    layer3_files = [
        base / "stigmergy.py",
        base / "shakti.py",
        base / "subconscious.py",
        base / "evolution.py",
        base / "organism.py",
        base / "strange_loop.py",
    ]
    
    layer0_loc = sum(count_lines_of_code(f) for f in layer0_files)
    layer3_loc = sum(count_lines_of_code(f) for f in layer3_files)
    
    ratio = layer0_loc / layer3_loc if layer3_loc > 0 else float("inf")
    
    passed = layer0_loc < layer3_loc
    
    if passed:
        message = (
            f"✅ Constitutional size check PASSED\n"
            f"   Layer 0 (Kernel): {layer0_loc} LOC\n"
            f"   Layer 3 (Living): {layer3_loc} LOC\n"
            f"   Ratio: {ratio:.2%} (constitution is {ratio:.1%} of metabolism)"
        )
    else:
        message = (
            f"❌ Constitutional size check FAILED\n"
            f"   Layer 0 (Kernel): {layer0_loc} LOC\n"
            f"   Layer 3 (Living): {layer3_loc} LOC\n"
            f"   VIOLATION: Constitution is larger than metabolism!\n"
            f"   The kernel must remain small and sacred."
        )
    
    return passed, message


def enforce_constitutional_size() -> None:
    """Run constitutional size check and raise if violated.
    
    This should be called at system boot (orchestrate_live.py, swarm.py).
    """
    passed, message = check_constitutional_size()
    logger.info(message)
    
    if not passed:
        raise RuntimeError(
            "Constitutional size violation detected. "
            "Layer 0 must be smaller than Layer 3. "
            "See dharma_swarm/constitutional_size_check.py for details."
        )


if __name__ == "__main__":
    # CLI test
    passed, message = check_constitutional_size()
    print(message)
    if not passed:
        exit(1)
