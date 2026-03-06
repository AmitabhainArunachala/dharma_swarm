"""Core DGC engine primitives.

Phase-0 foundation for artifact-centric orchestration:
- Canonical provider-agnostic events
- Artifact references + versioned filesystem storage
- Provenance logging
- Knowledge-store abstraction with a local fallback
"""

from .artifacts import ArtifactRef, ArtifactStore
from .adapters.base import (
    Capability,
    CompletionRequest,
    ModelProfile,
    ProviderAdapter,
    ProviderConfig,
)
from .events import CanonicalEvent, EventType
from .knowledge_store import (
    InMemoryKnowledgeStore,
    KnowledgeRecord,
    KnowledgeStore,
    QdrantKnowledgeStore,
    create_knowledge_store,
)
from .provider_runner import ProviderRunResult, ProviderRunner
from .provenance import ProvenanceEntry, ProvenanceLogger
from .settings import EngineSettings

__all__ = [
    "ArtifactRef",
    "ArtifactStore",
    "Capability",
    "CanonicalEvent",
    "CompletionRequest",
    "EventType",
    "InMemoryKnowledgeStore",
    "KnowledgeStore",
    "KnowledgeRecord",
    "ModelProfile",
    "ProvenanceEntry",
    "ProvenanceLogger",
    "ProviderAdapter",
    "ProviderConfig",
    "ProviderRunResult",
    "ProviderRunner",
    "QdrantKnowledgeStore",
    "EngineSettings",
    "create_knowledge_store",
]
