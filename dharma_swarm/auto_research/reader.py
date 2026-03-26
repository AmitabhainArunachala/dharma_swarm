"""Source normalization utilities for AutoResearch."""

from __future__ import annotations

from .models import SourceDocument
from .search import RawSourceDocument


class SourceReader:
    def normalize(self, source: RawSourceDocument) -> SourceDocument:
        if isinstance(source, SourceDocument):
            return source
        return SourceDocument.model_validate(source)

    def normalize_all(self, sources: list[RawSourceDocument]) -> list[SourceDocument]:
        return [self.normalize(source) for source in sources]
