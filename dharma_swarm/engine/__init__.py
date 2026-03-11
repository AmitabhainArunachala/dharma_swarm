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
from .chunker import Chunk, chunk_markdown
from .conversation_memory import ConversationMemoryStore, ConversationTurn, IdeaShard
from .event_memory import EventMemoryStore
from .events import CanonicalEvent, EventType
from .hybrid_retriever import (
    HybridRetriever,
    RetrievalHit,
    TemporalQuery,
    infer_temporal_query,
)
from .knowledge_store import (
    InMemoryKnowledgeStore,
    KnowledgeRecord,
    KnowledgeStore,
    QdrantKnowledgeStore,
    create_knowledge_store,
)
from .provider_runner import ProviderRunResult, ProviderRunner
from .provenance import ProvenanceEntry, ProvenanceLogger
from .retrieval_feedback import FeedbackProfile, RetrievalFeedbackStore
from .settings import EngineSettings
from .unified_index import UnifiedIndex

__all__ = [
    "ArtifactRef",
    "ArtifactStore",
    "Capability",
    "CanonicalEvent",
    "Chunk",
    "CompletionRequest",
    "ConversationMemoryStore",
    "ConversationTurn",
    "EventMemoryStore",
    "EventType",
    "HybridRetriever",
    "InMemoryKnowledgeStore",
    "IdeaShard",
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
    "FeedbackProfile",
    "RetrievalFeedbackStore",
    "RetrievalHit",
    "TemporalQuery",
    "EngineSettings",
    "UnifiedIndex",
    "chunk_markdown",
    "create_knowledge_store",
    "infer_temporal_query",
]
