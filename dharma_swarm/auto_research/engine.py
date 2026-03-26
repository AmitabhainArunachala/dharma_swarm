"""AutoResearch engine skeleton."""

from __future__ import annotations

from .claim_graph import ClaimGraphBuilder
from .models import ResearchBrief, ResearchQuery, ResearchReport
from .planner import ResearchPlanner
from .reader import SourceReader
from .reporter import ResearchReporter
from .search import NullSearchBackend, SearchBackend


class AutoResearchEngine:
    """Deterministic Phase 1 AutoResearch skeleton.

    The engine intentionally stops at query planning, source normalization,
    metadata-driven claim extraction, and report assembly. Retrieval quality,
    contradiction reasoning, and evaluation hooks land in later phases.
    """

    def __init__(
        self,
        *,
        planner: ResearchPlanner | None = None,
        search_backend: SearchBackend | None = None,
        reader: SourceReader | None = None,
        claim_graph: ClaimGraphBuilder | None = None,
        reporter: ResearchReporter | None = None,
    ) -> None:
        self.planner = planner or ResearchPlanner()
        self.search_backend = search_backend or NullSearchBackend()
        self.reader = reader or SourceReader()
        self.claim_graph = claim_graph or ClaimGraphBuilder()
        self.reporter = reporter or ResearchReporter()

    def plan(self, brief: ResearchBrief) -> list[ResearchQuery]:
        return self.planner.plan(brief)

    def run(self, brief: ResearchBrief) -> ResearchReport:
        queries = self.plan(brief)
        raw_sources = self.search_backend.search(brief, queries)
        sources = self.reader.normalize_all(list(raw_sources))
        claims = self.claim_graph.build(brief, sources)
        return self.reporter.create_report(
            brief=brief,
            queries=queries,
            sources=sources,
            claims=claims,
        )
