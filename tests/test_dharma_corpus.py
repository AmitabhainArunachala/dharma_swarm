"""Tests for dharma_swarm.dharma_corpus -- DharmaCorpus claim lifecycle."""

import re

import pytest

from dharma_swarm.dharma_corpus import (
    Claim,
    ClaimCategory,
    ClaimStatus,
    DharmaCorpus,
    EvidenceLink,
    ReviewRecord,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DC_ID_PATTERN = re.compile(r"^DC-\d{4}-\d{4}$")


@pytest.fixture
async def corpus(tmp_path):
    """Provide a fresh DharmaCorpus backed by a temp file."""
    c = DharmaCorpus(path=tmp_path / "corpus.jsonl")
    await c.load()
    return c


# ---------------------------------------------------------------------------
# Propose & ID format
# ---------------------------------------------------------------------------


async def test_propose_creates_claim(corpus):
    claim = await corpus.propose(
        statement="Do no harm",
        category=ClaimCategory.SAFETY,
    )
    assert claim.statement == "Do no harm"
    assert claim.category == ClaimCategory.SAFETY
    assert claim.status == ClaimStatus.PROPOSED
    assert claim.confidence == 0.5
    assert claim.enforcement == "log"
    assert claim.created_by == "system"


async def test_dc_id_format(corpus):
    claim = await corpus.propose(
        statement="Test claim",
        category=ClaimCategory.ETHICS,
    )
    assert DC_ID_PATTERN.match(claim.id), f"ID {claim.id!r} does not match DC-YYYY-NNNN"


async def test_sequential_ids(corpus):
    c1 = await corpus.propose(statement="First", category=ClaimCategory.SAFETY)
    c2 = await corpus.propose(statement="Second", category=ClaimCategory.SAFETY)

    seq1 = int(c1.id.split("-")[-1])
    seq2 = int(c2.id.split("-")[-1])
    assert seq2 == seq1 + 1


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------


async def test_review_adds_record(corpus):
    claim = await corpus.propose(statement="Review me", category=ClaimCategory.ETHICS)
    updated = await corpus.review(claim.id, reviewer="alice", action="comment", comment="Looks good")

    assert updated.status == ClaimStatus.UNDER_REVIEW
    assert len(updated.review_history) == 1
    assert updated.review_history[0].reviewer == "alice"
    assert updated.review_history[0].action == "comment"
    assert updated.review_history[0].comment == "Looks good"


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------


async def test_promote_sets_accepted(corpus):
    claim = await corpus.propose(statement="Promote me", category=ClaimCategory.OPERATIONAL)
    updated = await corpus.promote(claim.id)
    assert updated.status == ClaimStatus.ACCEPTED


async def test_park_sets_parked(corpus):
    claim = await corpus.propose(statement="Park me", category=ClaimCategory.OPERATIONAL)
    updated = await corpus.park(claim.id)
    assert updated.status == ClaimStatus.PARKED


async def test_reject_sets_rejected(corpus):
    claim = await corpus.propose(statement="Reject me", category=ClaimCategory.SAFETY)
    updated = await corpus.reject(claim.id)
    assert updated.status == ClaimStatus.REJECTED


async def test_deprecate_sets_deprecated(corpus):
    claim = await corpus.propose(statement="Deprecate me", category=ClaimCategory.SAFETY)
    updated = await corpus.deprecate(claim.id)
    assert updated.status == ClaimStatus.DEPRECATED


# ---------------------------------------------------------------------------
# Revise & lineage
# ---------------------------------------------------------------------------


async def test_revise_creates_new_claim_deprecates_old(corpus):
    original = await corpus.propose(statement="Version 1", category=ClaimCategory.ETHICS)
    revised = await corpus.revise(original.id, new_statement="Version 2")

    assert revised.statement == "Version 2"
    assert revised.parent_id == original.id
    assert revised.status == ClaimStatus.PROPOSED
    assert revised.id != original.id

    # Original is now deprecated
    old = await corpus.get(original.id)
    assert old is not None
    assert old.status == ClaimStatus.DEPRECATED


async def test_revise_lineage(corpus):
    v1 = await corpus.propose(statement="v1", category=ClaimCategory.SAFETY)
    v2 = await corpus.revise(v1.id, new_statement="v2")
    v3 = await corpus.revise(v2.id, new_statement="v3")

    lineage = await corpus.get_lineage(v3.id)
    assert len(lineage) == 3
    assert lineage[0].id == v3.id
    assert lineage[1].id == v2.id
    assert lineage[2].id == v1.id


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------


async def test_get_returns_none_for_missing(corpus):
    result = await corpus.get("DC-9999-0000")
    assert result is None


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


async def test_list_by_status(corpus):
    await corpus.propose(statement="A", category=ClaimCategory.SAFETY)
    c2 = await corpus.propose(statement="B", category=ClaimCategory.SAFETY)
    await corpus.promote(c2.id)

    proposed = await corpus.list_claims(status=ClaimStatus.PROPOSED)
    accepted = await corpus.list_claims(status=ClaimStatus.ACCEPTED)
    assert len(proposed) == 1
    assert len(accepted) == 1
    assert accepted[0].id == c2.id


async def test_list_by_category(corpus):
    await corpus.propose(statement="Safety claim", category=ClaimCategory.SAFETY)
    await corpus.propose(statement="Ethics claim", category=ClaimCategory.ETHICS)

    safety_claims = await corpus.list_claims(category=ClaimCategory.SAFETY)
    assert len(safety_claims) == 1
    assert safety_claims[0].statement == "Safety claim"


async def test_list_by_tag(corpus):
    await corpus.propose(statement="Tagged", category=ClaimCategory.SAFETY, tags=["critical"])
    await corpus.propose(statement="Untagged", category=ClaimCategory.SAFETY)

    tagged = await corpus.list_claims(tag="critical")
    assert len(tagged) == 1
    assert tagged[0].statement == "Tagged"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


async def test_persistence_save_reload(tmp_path):
    path = tmp_path / "persist.jsonl"

    # Write
    corpus1 = DharmaCorpus(path=path)
    await corpus1.load()
    claim = await corpus1.propose(
        statement="Persists across reloads",
        category=ClaimCategory.OPERATIONAL,
        tags=["durability"],
    )

    # Reload from disk
    corpus2 = DharmaCorpus(path=path)
    await corpus2.load()
    reloaded = await corpus2.get(claim.id)
    assert reloaded is not None
    assert reloaded.statement == "Persists across reloads"
    assert reloaded.tags == ["durability"]


# ---------------------------------------------------------------------------
# Full lifecycle
# ---------------------------------------------------------------------------


async def test_full_lifecycle(corpus):
    claim = await corpus.propose(
        statement="Lifecycle test",
        category=ClaimCategory.SAFETY,
        confidence=0.8,
    )
    assert claim.status == ClaimStatus.PROPOSED

    reviewed = await corpus.review(claim.id, "bob", "approve", "LGTM")
    assert reviewed.status == ClaimStatus.UNDER_REVIEW

    promoted = await corpus.promote(claim.id)
    assert promoted.status == ClaimStatus.ACCEPTED


# ---------------------------------------------------------------------------
# Evidence & counterarguments
# ---------------------------------------------------------------------------


async def test_evidence_links_typed(corpus):
    evidence = [
        EvidenceLink(type="research", url_or_ref="arxiv:2401.00001", description="Key paper"),
        EvidenceLink(type="incident", url_or_ref="INC-42", description="Production failure"),
    ]
    claim = await corpus.propose(
        statement="Evidence test",
        category=ClaimCategory.DOMAIN_SPECIFIC,
        evidence_links=evidence,
    )
    assert len(claim.evidence_links) == 2
    assert claim.evidence_links[0].type == "research"
    assert claim.evidence_links[1].url_or_ref == "INC-42"


async def test_counterarguments_stored(corpus):
    claim = await corpus.propose(
        statement="Contested claim",
        category=ClaimCategory.LEARNED_CONSTRAINT,
        counterarguments=["May not scale", "Needs more data"],
    )
    assert len(claim.counterarguments) == 2
    assert "May not scale" in claim.counterarguments
    assert "Needs more data" in claim.counterarguments
