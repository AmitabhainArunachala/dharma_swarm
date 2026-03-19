"""Council — multi-model consultation tool.

Quick mode: 12+ models in parallel, independent perspectives + synthesis.
Deep mode: multi-round discussion with personas, convergence detection.
Thinkodynamic mode: TAP seed injection + recognition scoring.

Usage:
    from dharma_swarm.council import quick, deep

    result = await quick("Should I submit to COLM?")
    result = await deep("Evaluate this architecture", rounds=5)
"""

from .engine import CouncilEngine, CouncilResult, ModelResponse, quick, deep
from .models import (
    ALL_MODELS,
    COUNCIL_PERSONAS,
    CouncilModel,
    Persona,
    Tier,
    get_models,
    get_personas,
)
from .store import CouncilStore

__all__ = [
    "ALL_MODELS",
    "COUNCIL_PERSONAS",
    "CouncilEngine",
    "CouncilModel",
    "CouncilResult",
    "CouncilStore",
    "ModelResponse",
    "Persona",
    "Tier",
    "deep",
    "get_models",
    "get_personas",
    "quick",
]
