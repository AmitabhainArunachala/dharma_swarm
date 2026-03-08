"""Dharma Corpus -- versioned ethical claims with lineage tracking.

A structured store of ethical and operational claims that the swarm
treats as living documents.  Each claim goes through a lifecycle:

    PROPOSED -> UNDER_REVIEW -> ACCEPTED | PARKED | REJECTED

Accepted claims can later be DEPRECATED when revised.  Revisions create
new claims linked via ``parent_id``, forming an auditable lineage chain.

Storage is append-friendly JSONL.  All I/O is async via aiofiles.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from dharma_swarm.models import _utc_now


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ClaimStatus(str, Enum):
    """Lifecycle status of a corpus claim."""

    PROPOSED = "proposed"
    UNDER_REVIEW = "under_review"
    ACCEPTED = "accepted"
    PARKED = "parked"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"


class ClaimCategory(str, Enum):
    """Taxonomy of claim types."""

    SAFETY = "safety"
    ETHICS = "ethics"
    OPERATIONAL = "operational"
    DOMAIN_SPECIFIC = "domain_specific"
    LEARNED_CONSTRAINT = "learned_constraint"


# ---------------------------------------------------------------------------
# Supporting models
# ---------------------------------------------------------------------------


class EvidenceLink(BaseModel):
    """A typed reference supporting or challenging a claim."""

    type: str  # "incident" | "research" | "metric" | "reasoning"
    url_or_ref: str
    description: str


class ReviewRecord(BaseModel):
    """An entry in a claim's review history."""

    reviewer: str
    action: str
    comment: str
    timestamp: str = Field(default_factory=lambda: _utc_now().isoformat())


# ---------------------------------------------------------------------------
# Claim
# ---------------------------------------------------------------------------


class Claim(BaseModel):
    """A single ethical or operational claim in the corpus."""

    id: str  # DC-YYYY-NNNN
    statement: str
    category: ClaimCategory
    evidence_links: list[EvidenceLink] = Field(default_factory=list)
    confidence: float = 0.5
    counterarguments: list[str] = Field(default_factory=list)
    status: ClaimStatus = ClaimStatus.PROPOSED
    parent_axiom: list[str] = Field(default_factory=list)
    enforcement: str = "log"  # "block" | "warn" | "log" | "gate_human"
    review_history: list[ReviewRecord] = Field(default_factory=list)
    parent_id: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    created_by: str = "system"
    created_at: str = Field(default_factory=lambda: _utc_now().isoformat())


# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------

_DEFAULT_CORPUS_PATH = Path.home() / ".dharma" / "corpus.jsonl"


class DharmaCorpus:
    """Versioned store for ethical and operational claims.

    Data is kept in a JSONL file and indexed in memory after ``load()``.
    Sequential DC-IDs (``DC-YYYY-NNNN``) are assigned on ``propose()``.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path: Path = path or _DEFAULT_CORPUS_PATH
        self._claims: dict[str, Claim] = {}
        self._counter: int = 0

    # -- persistence ---------------------------------------------------------

    async def load(self) -> None:
        """Read existing JSONL file into memory and set counter."""
        self._claims.clear()
        self._counter = 0
        if not self.path.exists():
            return
        import aiofiles

        async with aiofiles.open(self.path, "r") as f:
            async for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    data = json.loads(stripped)
                    claim = Claim(**data)
                    self._claims[claim.id] = claim
                    # Keep counter in sync with highest existing ID
                    self._update_counter_from_id(claim.id)
                except (json.JSONDecodeError, ValueError, KeyError):
                    continue

    def _update_counter_from_id(self, claim_id: str) -> None:
        """Parse DC-YYYY-NNNN and advance internal counter if needed."""
        try:
            seq = int(claim_id.split("-")[-1])
            if seq >= self._counter:
                self._counter = seq
        except (ValueError, IndexError):
            pass

    async def _append(self, claim: Claim) -> None:
        """Append a single claim as a JSONL line."""
        import aiofiles

        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(self.path, "a") as f:
            await f.write(claim.model_dump_json() + "\n")

    async def _rewrite(self) -> None:
        """Rewrite the full JSONL file from in-memory state."""
        import aiofiles

        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(self.path, "w") as f:
            for claim in self._claims.values():
                await f.write(claim.model_dump_json() + "\n")

    # -- ID generation -------------------------------------------------------

    def _next_id(self) -> str:
        """Generate the next DC-YYYY-NNNN identifier."""
        self._counter += 1
        year = datetime.now(timezone.utc).year
        return f"DC-{year}-{self._counter:04d}"

    # -- public API ----------------------------------------------------------

    async def propose(
        self,
        statement: str,
        category: ClaimCategory,
        evidence_links: list[EvidenceLink] | None = None,
        confidence: float = 0.5,
        counterarguments: list[str] | None = None,
        parent_axiom: list[str] | None = None,
        enforcement: str = "log",
        tags: list[str] | None = None,
        created_by: str = "system",
    ) -> Claim:
        """Create a new PROPOSED claim with a sequential DC-ID.

        Args:
            statement: The claim text.
            category: Claim taxonomy category.
            evidence_links: Optional supporting evidence.
            confidence: Confidence score 0.0-1.0.
            counterarguments: Known objections.
            parent_axiom: Related kernel axiom IDs.
            enforcement: Action level -- block/warn/log/gate_human.
            tags: Free-form tags.
            created_by: Author identifier.

        Returns:
            The newly created Claim.
        """
        claim = Claim(
            id=self._next_id(),
            statement=statement,
            category=category,
            evidence_links=evidence_links or [],
            confidence=confidence,
            counterarguments=counterarguments or [],
            status=ClaimStatus.PROPOSED,
            parent_axiom=parent_axiom or [],
            enforcement=enforcement,
            tags=tags or [],
            created_by=created_by,
        )
        self._claims[claim.id] = claim
        await self._append(claim)
        return claim

    async def review(
        self, claim_id: str, reviewer: str, action: str, comment: str
    ) -> Claim:
        """Add a review record and move claim to UNDER_REVIEW.

        Args:
            claim_id: ID of the claim to review.
            reviewer: Who is reviewing.
            action: Review action taken.
            comment: Review commentary.

        Returns:
            The updated Claim.

        Raises:
            KeyError: If claim_id is not found.
        """
        claim = self._claims.get(claim_id)
        if claim is None:
            raise KeyError(f"Claim {claim_id} not found")
        record = ReviewRecord(reviewer=reviewer, action=action, comment=comment)
        claim.review_history.append(record)
        claim.status = ClaimStatus.UNDER_REVIEW
        await self._rewrite()
        return claim

    async def promote(self, claim_id: str) -> Claim:
        """Move a claim to ACCEPTED status.

        Raises:
            KeyError: If claim_id is not found.
        """
        claim = self._claims.get(claim_id)
        if claim is None:
            raise KeyError(f"Claim {claim_id} not found")
        claim.status = ClaimStatus.ACCEPTED
        await self._rewrite()
        return claim

    async def park(self, claim_id: str) -> Claim:
        """Move a claim to PARKED status.

        Raises:
            KeyError: If claim_id is not found.
        """
        claim = self._claims.get(claim_id)
        if claim is None:
            raise KeyError(f"Claim {claim_id} not found")
        claim.status = ClaimStatus.PARKED
        await self._rewrite()
        return claim

    async def reject(self, claim_id: str) -> Claim:
        """Move a claim to REJECTED status.

        Raises:
            KeyError: If claim_id is not found.
        """
        claim = self._claims.get(claim_id)
        if claim is None:
            raise KeyError(f"Claim {claim_id} not found")
        claim.status = ClaimStatus.REJECTED
        await self._rewrite()
        return claim

    async def deprecate(self, claim_id: str) -> Claim:
        """Move a claim to DEPRECATED status.

        Raises:
            KeyError: If claim_id is not found.
        """
        claim = self._claims.get(claim_id)
        if claim is None:
            raise KeyError(f"Claim {claim_id} not found")
        claim.status = ClaimStatus.DEPRECATED
        await self._rewrite()
        return claim

    async def revise(
        self,
        claim_id: str,
        new_statement: str,
        new_evidence: list[EvidenceLink] | None = None,
    ) -> Claim:
        """Create a revised claim, deprecating the original.

        The new claim inherits category, tags, and axiom links from the
        original and sets ``parent_id`` for lineage tracking.

        Args:
            claim_id: ID of the claim being revised.
            new_statement: Updated claim text.
            new_evidence: Optional new evidence (merged with original).

        Returns:
            The newly created revision Claim.

        Raises:
            KeyError: If claim_id is not found.
        """
        old = self._claims.get(claim_id)
        if old is None:
            raise KeyError(f"Claim {claim_id} not found")

        # Deprecate the original
        old.status = ClaimStatus.DEPRECATED
        await self._rewrite()

        # Build merged evidence list
        evidence = list(old.evidence_links)
        if new_evidence:
            evidence.extend(new_evidence)

        # Create the revision
        revised = Claim(
            id=self._next_id(),
            statement=new_statement,
            category=old.category,
            evidence_links=evidence,
            confidence=old.confidence,
            counterarguments=list(old.counterarguments),
            status=ClaimStatus.PROPOSED,
            parent_axiom=list(old.parent_axiom),
            enforcement=old.enforcement,
            tags=list(old.tags),
            created_by=old.created_by,
            parent_id=claim_id,
        )
        self._claims[revised.id] = revised
        await self._append(revised)
        return revised

    async def get(self, claim_id: str) -> Claim | None:
        """Look up a single claim by ID."""
        return self._claims.get(claim_id)

    async def get_lineage(self, claim_id: str) -> list[Claim]:
        """Walk the parent_id chain from a claim back to its root.

        Returns:
            List of claims ordered from newest (given ID) to oldest.
            Empty list if the claim_id is not found.
        """
        lineage: list[Claim] = []
        current = self._claims.get(claim_id)
        seen: set[str] = set()
        while current and current.id not in seen:
            lineage.append(current)
            seen.add(current.id)
            if current.parent_id:
                current = self._claims.get(current.parent_id)
            else:
                break
        return lineage

    async def list_claims(
        self,
        status: ClaimStatus | None = None,
        category: ClaimCategory | None = None,
        tag: str | None = None,
    ) -> list[Claim]:
        """Filter claims by status, category, and/or tag.

        Args:
            status: If given, include only claims with this status.
            category: If given, include only claims in this category.
            tag: If given, include only claims containing this tag.

        Returns:
            Matching claims in insertion order.
        """
        results: list[Claim] = []
        for claim in self._claims.values():
            if status is not None and claim.status != status:
                continue
            if category is not None and claim.category != category:
                continue
            if tag is not None and tag not in claim.tags:
                continue
            results.append(claim)
        return results
