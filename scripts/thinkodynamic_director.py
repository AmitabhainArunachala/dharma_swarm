#!/usr/bin/env python3
"""Run the thinkodynamic director as a standalone script."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / "dharma_swarm"))

from dharma_swarm.thinkodynamic_director import main


if __name__ == "__main__":
    raise SystemExit(main())
