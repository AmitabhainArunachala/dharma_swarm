"""Canonical data contracts for the AutoResearch layer."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator


def _strip_text(value: str) -> str:
    return value.strip()


class ResearchBrief(BaseModel):
    task_id: str
    topic: str
    question: str
    audience: str = "internal"
    requires_recency: bool = False
    citation_style: str = "inline"
    time_budget_seconds: int = 300
    source_budget: int = 12
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("task_id", "topic", "question")
    @classmethod
    def _require_text(cls, value: str) -> str:
        text = _strip_text(value)
        if not text:
            raise ValueError("research brief fields must not be empty")
        return text


class ResearchQuery(BaseModel):
    query_id: str
    text: str
    intent: str
    priority: int = 1

    @field_validator("query_id", "text", "intent")
    @classmethod
    def _require_query_text(cls, value: str) -> str:
        text = _strip_text(value)
        if not text:
            raise ValueError("research query fields must not be empty")
        return text


class SourceDocument(BaseModel):
    source_id: str
    url: str
    title: str = ""
    domain: str = ""
    published_at: str = ""
    fetched_at: str = ""
    source_type: str = "web"
    authority_score: float = 0.0
    freshness_score: float = 0.0
    content: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_id", "url")
    @classmethod
    def _require_source_identity(cls, value: str) -> str:
        text = _strip_text(value)
        if not text:
            raise ValueError("source identity fields must not be empty")
        return text

    @model_validator(mode="after")
    def _normalize_text_fields(self) -> "SourceDocument":
        self.title = _strip_text(self.title)
        self.content = _strip_text(self.content)
        self.domain = _strip_text(self.domain).lower() or urlparse(self.url).netloc.lower()
        return self


class ClaimRecord(BaseModel):
    claim_id: str
    text: str
    support_level: str
    supporting_source_ids: list[str] = Field(default_factory=list)
    contradicting_source_ids: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    confidence: float = 0.0

    @field_validator("claim_id", "text", "support_level")
    @classmethod
    def _require_claim_text(cls, value: str) -> str:
        text = _strip_text(value)
        if not text:
            raise ValueError("claim fields must not be empty")
        return text


class ResearchReport(BaseModel):
    report_id: str
    task_id: str
    brief: ResearchBrief
    summary: str
    body: str
    claims: list[ClaimRecord] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    contradictions: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("report_id", "task_id", "summary", "body")
    @classmethod
    def _require_report_text(cls, value: str) -> str:
        text = _strip_text(value)
        if not text:
            raise ValueError("report fields must not be empty")
        return text
