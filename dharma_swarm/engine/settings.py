"""Runtime settings for engine backends and infrastructure toggles."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class EngineSettings:
    """Environment-driven settings for infrastructure adapters."""

    knowledge_backend: str = "local"  # local|qdrant
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_collection: str = "dgc_artifacts"
    qdrant_vector_size: int = 256

    @classmethod
    def from_env(cls) -> "EngineSettings":
        backend = os.getenv("DGC_KNOWLEDGE_BACKEND", "local").strip().lower()
        if backend not in {"local", "qdrant"}:
            backend = "local"

        vector_size_raw = os.getenv("DGC_QDRANT_VECTOR_SIZE", "256")
        try:
            vector_size = max(8, int(vector_size_raw))
        except ValueError:
            vector_size = 256

        return cls(
            knowledge_backend=backend,
            qdrant_url=os.getenv("DGC_QDRANT_URL", "http://127.0.0.1:6333"),
            qdrant_collection=os.getenv("DGC_QDRANT_COLLECTION", "dgc_artifacts"),
            qdrant_vector_size=vector_size,
        )

