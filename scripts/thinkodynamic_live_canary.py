#!/usr/bin/env python3
"""Run the thinkodynamic live canary."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / "dharma_swarm"))

from dharma_swarm.thinkodynamic_canary import main


if __name__ == "__main__":
    raise SystemExit(main())
