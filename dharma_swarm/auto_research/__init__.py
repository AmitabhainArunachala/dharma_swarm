"""AutoResearch contracts and engine skeleton."""

from .engine import AutoResearchEngine
from .models import ClaimRecord, ResearchBrief, ResearchQuery, ResearchReport, SourceDocument

__all__ = [
    "AutoResearchEngine",
    "ClaimRecord",
    "ResearchBrief",
    "ResearchQuery",
    "ResearchReport",
    "SourceDocument",
]
