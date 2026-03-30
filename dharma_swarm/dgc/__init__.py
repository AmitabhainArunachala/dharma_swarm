"""Modular DGC command package.

This package will gradually absorb the implementation currently living in
``dharma_swarm.dgc_cli`` while preserving the public ``dgc`` entrypoint.
"""

from .main import main

__all__ = ["main"]
