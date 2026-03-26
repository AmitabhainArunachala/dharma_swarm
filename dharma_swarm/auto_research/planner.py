"""Query planning for the AutoResearch layer."""

from __future__ import annotations

from .models import ResearchBrief, ResearchQuery


class ResearchPlanner:
    """Expand a research brief into a small deterministic query plan."""

    def plan(self, brief: ResearchBrief) -> list[ResearchQuery]:
        entries = [
            ("discovery", f"{brief.topic} {brief.question}", 3),
            ("validation", f"verify {brief.topic} {brief.question}", 2),
            ("contradiction", f"contradictions {brief.topic} {brief.question}", 2),
        ]
        if brief.requires_recency:
            entries.append(("update", f"latest updates {brief.topic} {brief.question}", 3))

        return [
            ResearchQuery(
                query_id=f"{brief.task_id}:{intent}:{index}",
                text=text,
                intent=intent,
                priority=priority,
            )
            for index, (intent, text, priority) in enumerate(entries, start=1)
        ]
