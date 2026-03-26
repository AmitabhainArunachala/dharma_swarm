"""Report assembly for AutoResearch."""

from __future__ import annotations

from .citation import CitationFormatter
from .models import ClaimRecord, ResearchBrief, ResearchQuery, ResearchReport, SourceDocument


class ResearchReporter:
    def __init__(self, citation_formatter: CitationFormatter | None = None) -> None:
        self.citation_formatter = citation_formatter or CitationFormatter()

    def create_report(
        self,
        *,
        brief: ResearchBrief,
        queries: list[ResearchQuery],
        sources: list[SourceDocument],
        claims: list[ClaimRecord],
    ) -> ResearchReport:
        enriched_claims: list[ClaimRecord] = []
        body_lines: list[str] = []

        for claim in claims:
            citations = claim.citations or self.citation_formatter.format_claim(claim)
            enriched = claim.model_copy(update={"citations": citations})
            enriched_claims.append(enriched)
            citation_suffix = f" {' '.join(citations)}" if citations else ""
            body_lines.append(f"- {enriched.text}{citation_suffix}")

        if not body_lines:
            body_lines.append("- No supported claims extracted.")

        return ResearchReport(
            report_id=f"report-{brief.task_id}",
            task_id=brief.task_id,
            brief=brief,
            summary=f"Research report for {brief.topic} using {len(sources)} source(s).",
            body="\n".join(body_lines),
            claims=enriched_claims,
            source_ids=[source.source_id for source in sources],
            metadata={
                "query_ids": [query.query_id for query in queries],
                "query_intents": [query.intent for query in queries],
                "source_domains": [source.domain for source in sources],
            },
        )
