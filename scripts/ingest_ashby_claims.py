#!/usr/bin/env python3
"""Ingest 20 Ashby corpus claims into DharmaCorpus.

Reads structured claims from ~/.dharma/reading_program/ashby/corpus_claims_ashby.md
and proposes each one via the DharmaCorpus.propose() API. Idempotent: skips claims
whose statement text already exists in the corpus.

Usage:
    cd ~/dharma_swarm && python3 scripts/ingest_ashby_claims.py
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from pathlib import Path

# Ensure dharma_swarm is importable when run from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dharma_swarm.dharma_corpus import (
    ClaimCategory,
    DharmaCorpus,
    EvidenceLink,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

CLAIMS_FILE = Path.home() / ".dharma" / "reading_program" / "ashby" / "corpus_claims_ashby.md"

CATEGORY_MAP: dict[str, ClaimCategory] = {
    "THEORETICAL": ClaimCategory.THEORETICAL,
    "ARCHITECTURAL": ClaimCategory.ARCHITECTURAL,
    "OPERATIONAL": ClaimCategory.OPERATIONAL,
    "SAFETY": ClaimCategory.SAFETY,
}


def parse_claims(text: str) -> list[dict[str, object]]:
    """Parse the 20 structured claims from the markdown file.

    Returns a list of dicts with keys:
        statement, category, source, formal_constraint, confidence,
        cross_references, enforcement
    """
    # Split on claim headers: ## Claim N: ...
    claim_blocks = re.split(r"^## Claim \d+:", text, flags=re.MULTILINE)
    # First element is the preamble, skip it
    claim_blocks = [b for b in claim_blocks[1:] if b.strip()]

    claims: list[dict[str, object]] = []
    for block in claim_blocks:
        claim: dict[str, object] = {}

        # Extract title (first line of block)
        title_line = block.strip().split("\n")[0].strip()
        claim["title"] = title_line

        # Statement
        m = re.search(r"\*\*Statement\*\*:\s*(.+?)(?=\n-\s*\*\*|\Z)", block, re.DOTALL)
        claim["statement"] = m.group(1).strip() if m else ""

        # Category
        m = re.search(r"\*\*Category\*\*:\s*(\w+)", block)
        claim["category"] = m.group(1).strip() if m else "THEORETICAL"

        # Source
        m = re.search(r"\*\*Source\*\*:\s*(.+?)(?=\n-\s*\*\*|\Z)", block, re.DOTALL)
        claim["source"] = m.group(1).strip() if m else ""

        # Formal Constraint
        m = re.search(r"\*\*Formal Constraint\*\*:\s*(.+?)(?=\n-\s*\*\*|\Z)", block, re.DOTALL)
        claim["formal_constraint"] = m.group(1).strip() if m else ""

        # Confidence
        m = re.search(r"\*\*Confidence\*\*:\s*([\d.]+)", block)
        claim["confidence"] = float(m.group(1)) if m else 0.5

        # Cross-references
        m = re.search(r"\*\*Cross-references\*\*:\s*(.+?)(?=\n-\s*\*\*|\Z)", block, re.DOTALL)
        claim["cross_references"] = m.group(1).strip() if m else ""

        # Enforcement
        m = re.search(r"\*\*Enforcement\*\*:\s*(\w+)", block)
        claim["enforcement"] = m.group(1).strip() if m else "log"

        claims.append(claim)

    return claims


def _extract_kernel_refs(cross_refs: str) -> list[str]:
    """Extract kernel:FOO references as parent_axiom links."""
    return re.findall(r"kernel:(\w+)", cross_refs)


async def main() -> None:
    """Load corpus, parse claims, ingest idempotently."""
    if not CLAIMS_FILE.exists():
        log.error("Claims file not found: %s", CLAIMS_FILE)
        sys.exit(1)

    text = CLAIMS_FILE.read_text(encoding="utf-8")
    raw_claims = parse_claims(text)
    log.info("Parsed %d claims from %s", len(raw_claims), CLAIMS_FILE.name)

    corpus = DharmaCorpus()
    await corpus.load()
    existing_count = len(corpus._claims)
    log.info("Loaded corpus with %d existing claims", existing_count)

    # Build set of existing statement texts for idempotency check.
    # Normalize whitespace for comparison.
    existing_statements: set[str] = set()
    for c in corpus._claims.values():
        existing_statements.add(_normalize(c.statement))

    ingested = 0
    skipped = 0

    for i, raw in enumerate(raw_claims, 1):
        statement = str(raw["statement"])
        if _normalize(statement) in existing_statements:
            log.info("  [%02d] SKIP (already exists): %.80s...", i, statement)
            skipped += 1
            continue

        category_key = str(raw["category"]).upper()
        category = CATEGORY_MAP.get(category_key, ClaimCategory.THEORETICAL)

        source_text = str(raw.get("source", ""))
        evidence_links: list[EvidenceLink] = []
        if source_text:
            evidence_links.append(
                EvidenceLink(
                    type="research",
                    url_or_ref=source_text,
                    description=f"Ashby: {str(raw.get('title', ''))}",
                )
            )

        cross_refs = str(raw.get("cross_references", ""))
        parent_axiom = _extract_kernel_refs(cross_refs)

        confidence = float(raw.get("confidence", 0.5))  # type: ignore[arg-type]
        enforcement = str(raw.get("enforcement", "log"))

        claim = await corpus.propose(
            statement=statement,
            category=category,
            evidence_links=evidence_links,
            confidence=confidence,
            parent_axiom=parent_axiom,
            enforcement=enforcement,
            tags=["ashby", "cybernetics", "reading_program"],
            created_by="ashby_reading_pipeline",
        )

        log.info("  [%02d] INGESTED %s: %.80s...", i, claim.id, statement)
        existing_statements.add(_normalize(statement))
        ingested += 1

    final_count = len(corpus._claims)
    log.info("--- Ingestion complete ---")
    log.info("  Ingested: %d", ingested)
    log.info("  Skipped:  %d", skipped)
    log.info("  Corpus total: %d claims (%d before)", final_count, existing_count)


def _normalize(text: str) -> str:
    """Normalize whitespace for dedup comparison."""
    return " ".join(text.split()).lower()


if __name__ == "__main__":
    asyncio.run(main())
