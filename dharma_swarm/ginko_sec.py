"""Ginko SEC EDGAR -- 10-K filing fetcher and analyzer.

SEC EDGAR is free, no API key needed. Rate limited to 10 req/sec.
Fetches 10-K annual filings, extracts key financial sections,
and passes them to LLM agents for analysis.

Data sources:
  - SEC EDGAR full-text search API
  - SEC EDGAR company submissions API
  - SEC EDGAR filing archives

All fetchers return structured dataclasses. Failures are logged,
never raised -- downstream consumers handle None gracefully.

Persistence: ~/.dharma/ginko/sec/{ticker}/
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Awaitable

import httpx

logger = logging.getLogger(__name__)

GINKO_DIR = Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma")) / "ginko"
SEC_DIR = GINKO_DIR / "sec"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_dirs(ticker: str = "") -> Path:
    """Ensure SEC cache directories exist. Returns ticker-specific dir if given."""
    if ticker:
        d = SEC_DIR / ticker.upper()
    else:
        d = SEC_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# SEC EDGAR CONSTANTS
# ---------------------------------------------------------------------------

SEC_USER_AGENT = "DharmicQuant/1.0 (dharmic.quant@proton.me)"

SEC_HEADERS = {
    "User-Agent": SEC_USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
    "Accept": "application/json, text/html, */*",
}

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_path}"

# Max concurrent requests (stay well under 10/sec limit)
_SEMAPHORE_LIMIT = 5
# Delay between requests in seconds (0.15s = ~6.7 req/sec max)
_REQUEST_DELAY = 0.15

# ---------------------------------------------------------------------------
# TICKER -> CIK MAPPING (common tickers, zero-padded to 10 digits)
# ---------------------------------------------------------------------------

TICKER_CIK: dict[str, str] = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "NVDA": "0001045810",
    "GOOG": "0001652044",
    "GOOGL": "0001652044",
    "AMZN": "0001018724",
    "META": "0001326801",
    "TSLA": "0001318605",
    "JPM": "0000019617",
    "GS": "0000886982",
    "BRK": "0001067983",
    "BRK-A": "0001067983",
    "BRK-B": "0001067983",
}


# ---------------------------------------------------------------------------
# DATA MODELS
# ---------------------------------------------------------------------------


@dataclass
class SECFiling:
    """A single SEC filing with metadata and optional raw text."""

    company: str
    ticker: str
    cik: str
    filing_type: str  # "10-K"
    date_filed: str
    accession_number: str
    url: str
    raw_text: str = ""  # Extracted text content (HTML stripped)


@dataclass
class FilingSections:
    """Key sections extracted from a 10-K filing."""

    revenue: str = ""
    net_income: str = ""
    risk_factors: str = ""
    management_discussion: str = ""
    forward_guidance: str = ""
    total_assets: str = ""


@dataclass
class FilingAnalysis:
    """LLM or rule-based analysis of a 10-K filing."""

    ticker: str
    filing_date: str
    sentiment: str  # "bullish", "bearish", "neutral"
    confidence: float  # 0.0 to 1.0
    key_findings: list[str] = field(default_factory=list)
    risk_highlights: list[str] = field(default_factory=list)
    analyzed_at: str = ""


# ---------------------------------------------------------------------------
# HTML STRIPPING
# ---------------------------------------------------------------------------


def _strip_html(raw_html: str) -> str:
    """Remove HTML tags, decode entities, collapse whitespace.

    Args:
        raw_html: Raw HTML string from SEC filing.

    Returns:
        Clean plain text.
    """
    # Remove script and style blocks entirely
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", raw_html, flags=re.DOTALL | re.IGNORECASE)
    # Remove all HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode HTML entities
    text = html.unescape(text)
    # Collapse whitespace: runs of spaces/tabs to single space
    text = re.sub(r"[^\S\n]+", " ", text)
    # Collapse multiple blank lines to at most two newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# RATE-LIMITED HTTP CLIENT
# ---------------------------------------------------------------------------


class _SECClient:
    """Thin wrapper around httpx.AsyncClient with SEC rate limiting."""

    def __init__(self) -> None:
        self._semaphore = asyncio.Semaphore(_SEMAPHORE_LIMIT)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=SEC_HEADERS,
                timeout=30.0,
                follow_redirects=True,
            )
        return self._client

    async def get(self, url: str, params: dict[str, Any] | None = None) -> httpx.Response:
        """Rate-limited GET request to SEC EDGAR."""
        async with self._semaphore:
            client = await self._get_client()
            await asyncio.sleep(_REQUEST_DELAY)
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


# Module-level client instance (reused across calls within a session)
_client = _SECClient()


# ---------------------------------------------------------------------------
# CIK RESOLUTION
# ---------------------------------------------------------------------------


async def _resolve_cik(ticker: str) -> str | None:
    """Resolve a ticker symbol to a zero-padded 10-digit CIK string.

    First checks the built-in TICKER_CIK dict, then falls back to
    the SEC EDGAR company search API.

    Args:
        ticker: Stock ticker symbol (e.g. "AAPL").

    Returns:
        Zero-padded CIK string or None if not found.
    """
    upper = ticker.upper()

    # Check built-in mapping first
    if upper in TICKER_CIK:
        return TICKER_CIK[upper]

    # Fallback: search SEC EDGAR company tickers endpoint
    try:
        url = "https://www.sec.gov/cgi-bin/browse-edgar"
        params = {
            "action": "getcompany",
            "company": upper,
            "CIK": upper,
            "type": "10-K",
            "dateb": "",
            "owner": "include",
            "count": "1",
            "search_text": "",
            "output": "atom",
        }
        resp = await _client.get(url, params=params)
        # Try to extract CIK from the Atom feed response
        cik_match = re.search(r"CIK=(\d{10})", resp.text)
        if cik_match:
            cik = cik_match.group(1)
            # Cache for future lookups
            TICKER_CIK[upper] = cik
            return cik

        # Alternative: try the JSON tickers file
        tickers_url = "https://www.sec.gov/files/company_tickers.json"
        resp = await _client.get(tickers_url)
        tickers_data = resp.json()
        for _key, entry in tickers_data.items():
            if entry.get("ticker", "").upper() == upper:
                cik_raw = str(entry.get("cik_str", ""))
                cik = cik_raw.zfill(10)
                TICKER_CIK[upper] = cik
                return cik

    except Exception as e:
        logger.error("CIK resolution failed for %s: %s", ticker, e)

    return None


# ---------------------------------------------------------------------------
# FILING METADATA FETCHING
# ---------------------------------------------------------------------------


async def fetch_company_filings(
    ticker: str,
    filing_type: str = "10-K",
    limit: int = 1,
) -> list[dict[str, Any]]:
    """Fetch recent filing metadata for a company from SEC EDGAR.

    Args:
        ticker: Stock ticker symbol (e.g. "AAPL").
        filing_type: SEC form type to filter (default "10-K").
        limit: Maximum number of filings to return.

    Returns:
        List of filing metadata dicts with keys:
          accessionNumber, filingDate, primaryDocument, form, etc.
        Empty list on failure.
    """
    cik = await _resolve_cik(ticker)
    if not cik:
        logger.warning("Could not resolve CIK for ticker %s", ticker)
        return []

    url = SUBMISSIONS_URL.format(cik=cik)

    try:
        resp = await _client.get(url)
        data = resp.json()
    except Exception as e:
        logger.error("Failed to fetch submissions for %s (CIK %s): %s", ticker, cik, e)
        return []

    # Company name from response
    company_name = data.get("name", ticker.upper())

    # recent filings are in data["filings"]["recent"]
    recent = data.get("filings", {}).get("recent", {})
    if not recent:
        logger.warning("No recent filings found for %s", ticker)
        return []

    forms = recent.get("form", [])
    accession_numbers = recent.get("accessionNumber", [])
    filing_dates = recent.get("filingDate", [])
    primary_documents = recent.get("primaryDocument", [])

    results: list[dict[str, Any]] = []
    for i, form in enumerate(forms):
        if form != filing_type:
            continue
        if len(results) >= limit:
            break

        accession = accession_numbers[i] if i < len(accession_numbers) else ""
        date_filed = filing_dates[i] if i < len(filing_dates) else ""
        primary_doc = primary_documents[i] if i < len(primary_documents) else ""

        # Build the filing document URL
        accession_path = accession.replace("-", "")
        doc_url = (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{cik.lstrip('0') or '0'}/{accession_path}/{primary_doc}"
        )

        results.append({
            "company": company_name,
            "ticker": ticker.upper(),
            "cik": cik,
            "form": form,
            "accessionNumber": accession,
            "filingDate": date_filed,
            "primaryDocument": primary_doc,
            "url": doc_url,
        })

    return results


# ---------------------------------------------------------------------------
# 10-K FETCHING WITH CACHING
# ---------------------------------------------------------------------------


def _cache_path(ticker: str, date_filed: str) -> Path:
    """Return the cache file path for a filing."""
    safe_date = date_filed.replace("-", "").replace("/", "")
    return SEC_DIR / ticker.upper() / f"10k_{safe_date}.txt"


def _load_cached(ticker: str, date_filed: str) -> str | None:
    """Load cached filing text if it exists."""
    p = _cache_path(ticker, date_filed)
    if p.exists():
        try:
            return p.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("Cache read failed for %s: %s", p, e)
    return None


def _save_cache(ticker: str, date_filed: str, text: str) -> None:
    """Save filing text to cache."""
    _ensure_dirs(ticker)
    p = _cache_path(ticker, date_filed)
    try:
        p.write_text(text, encoding="utf-8")
        logger.info("Cached filing to %s (%d chars)", p, len(text))
    except Exception as e:
        logger.warning("Cache write failed for %s: %s", p, e)


async def fetch_recent_10k(ticker: str) -> SECFiling | None:
    """Fetch the most recent 10-K filing for a ticker.

    Checks local cache first. If not cached, downloads the filing
    HTML from SEC EDGAR, strips HTML, caches the result, and returns
    a populated SECFiling object.

    Args:
        ticker: Stock ticker symbol (e.g. "AAPL").

    Returns:
        SECFiling with raw_text populated, or None on failure.
    """
    filings = await fetch_company_filings(ticker, filing_type="10-K", limit=1)
    if not filings:
        logger.warning("No 10-K filings found for %s", ticker)
        return None

    meta = filings[0]
    date_filed = meta["filingDate"]

    # Check cache
    cached = _load_cached(ticker, date_filed)
    if cached:
        logger.info("Loaded 10-K for %s from cache (%d chars)", ticker, len(cached))
        return SECFiling(
            company=meta["company"],
            ticker=meta["ticker"],
            cik=meta["cik"],
            filing_type="10-K",
            date_filed=date_filed,
            accession_number=meta["accessionNumber"],
            url=meta["url"],
            raw_text=cached,
        )

    # Download the filing document
    try:
        resp = await _client.get(meta["url"])
        raw_html = resp.text
    except Exception as e:
        logger.error("Failed to download 10-K for %s: %s", ticker, e)
        return None

    # Strip HTML and cache
    raw_text = _strip_html(raw_html)
    if not raw_text:
        logger.warning("Empty text after HTML stripping for %s", ticker)
        return None

    _save_cache(ticker, date_filed, raw_text)

    return SECFiling(
        company=meta["company"],
        ticker=meta["ticker"],
        cik=meta["cik"],
        filing_type="10-K",
        date_filed=date_filed,
        accession_number=meta["accessionNumber"],
        url=meta["url"],
        raw_text=raw_text,
    )


# ---------------------------------------------------------------------------
# BATCH FETCHING
# ---------------------------------------------------------------------------


async def fetch_recent_10k_batch(tickers: list[str]) -> list[SECFiling]:
    """Fetch 10-K filings for multiple tickers in parallel.

    Uses asyncio.Semaphore to limit concurrency and respect SEC rate limits.

    Args:
        tickers: List of ticker symbols.

    Returns:
        List of successfully fetched SECFiling objects.
        Failures are logged and omitted from the result.
    """
    sem = asyncio.Semaphore(_SEMAPHORE_LIMIT)

    async def _fetch_one(ticker: str) -> SECFiling | None:
        async with sem:
            return await fetch_recent_10k(ticker)

    tasks = [_fetch_one(t) for t in tickers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    filings: list[SECFiling] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error("Batch fetch failed for %s: %s", tickers[i], result)
        elif result is not None:
            filings.append(result)

    logger.info(
        "Batch fetch complete: %d/%d tickers succeeded",
        len(filings),
        len(tickers),
    )
    return filings


# ---------------------------------------------------------------------------
# SECTION EXTRACTION
# ---------------------------------------------------------------------------

# Regex patterns for common 10-K section headers.
# These match both "Item 1A" and "ITEM 1A" style headers, with or without
# trailing periods, dashes, or em-dashes.

_SECTION_PATTERNS: dict[str, list[str]] = {
    "risk_factors": [
        r"(?:Item\s+1A\.?\s*[-—]?\s*Risk\s+Factors)",
        r"(?:ITEM\s+1A\.?\s*[-—]?\s*RISK\s+FACTORS)",
        r"(?:Risk\s+Factors\s*\n)",
    ],
    "management_discussion": [
        r"(?:Item\s+7\.?\s*[-—]?\s*Management['']?s?\s+Discussion)",
        r"(?:ITEM\s+7\.?\s*[-—]?\s*MANAGEMENT['']?S?\s+DISCUSSION)",
        r"(?:Management['']?s?\s+Discussion\s+and\s+Analysis)",
    ],
    "forward_guidance": [
        r"(?:Forward[- ]Looking\s+Statements?)",
        r"(?:FORWARD[- ]LOOKING\s+STATEMENTS?)",
        r"(?:Cautionary\s+(?:Note|Statement)\s+(?:Regarding|About))",
    ],
}

# Patterns for financial data extraction
_REVENUE_PATTERNS = [
    r"(?:Total\s+(?:net\s+)?(?:revenue|sales))\s*[\$]?\s*([\d,]+(?:\.\d+)?)\s*(?:million|billion)?",
    r"(?:Net\s+(?:revenue|sales))\s*[\$]?\s*([\d,]+(?:\.\d+)?)\s*(?:million|billion)?",
    r"(?:Revenue)\s*[\$]?\s*([\d,]+(?:\.\d+)?)\s*(?:million|billion)?",
]

_NET_INCOME_PATTERNS = [
    r"(?:Net\s+income|Net\s+earnings)\s*[\$]?\s*([\d,]+(?:\.\d+)?)\s*(?:million|billion)?",
    r"(?:Net\s+(?:income|loss)\s+attributable)\s*[\$]?\s*([\d,]+(?:\.\d+)?)",
]

_TOTAL_ASSETS_PATTERNS = [
    r"(?:Total\s+assets)\s*[\$]?\s*([\d,]+(?:\.\d+)?)\s*(?:million|billion)?",
]

_SECTION_MAX_CHARS = 2000


def _extract_section(text: str, patterns: list[str], max_chars: int = _SECTION_MAX_CHARS) -> str:
    """Extract a section from filing text using regex patterns.

    Finds the first matching header and extracts text from that point
    until the next likely section header or max_chars, whichever comes first.

    Args:
        text: Full filing plain text.
        patterns: List of regex patterns to match the section header.
        max_chars: Maximum characters to extract.

    Returns:
        Extracted section text, or empty string if not found.
    """
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            start = match.start()
            # Look for the next section header (Item N or all-caps header)
            remainder = text[start:]
            # Find the next "Item N" header after our section
            next_section = re.search(
                r"\n\s*(?:Item\s+\d+[A-Za-z]?\.?\s*[-—]?\s*[A-Z])",
                remainder[100:],  # skip at least 100 chars to avoid re-matching
                re.IGNORECASE,
            )
            if next_section:
                end = min(start + 100 + next_section.start(), start + max_chars)
            else:
                end = start + max_chars

            section = text[start:end].strip()
            return section[:max_chars]

    return ""


def _extract_financial_value(text: str, patterns: list[str]) -> str:
    """Extract a financial value string from text using patterns.

    Args:
        text: Filing text to search.
        patterns: Regex patterns with a capture group for the value.

    Returns:
        Matched value string (e.g. "394,328") or empty string.
    """
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # Return the surrounding context (100 chars before/after match)
            ctx_start = max(0, match.start() - 100)
            ctx_end = min(len(text), match.end() + 100)
            return text[ctx_start:ctx_end].strip()
    return ""


def extract_financial_sections(filing: SECFiling) -> FilingSections:
    """Parse a 10-K filing's raw text to extract key financial sections.

    Identifies sections by common 10-K headers (Item 1A, Item 7, etc.)
    and extracts financial figures from statements.

    Each section is truncated to 2000 chars max for LLM context management.

    Args:
        filing: SECFiling with raw_text populated.

    Returns:
        FilingSections with available sections populated.
    """
    text = filing.raw_text
    if not text:
        return FilingSections()

    return FilingSections(
        risk_factors=_extract_section(text, _SECTION_PATTERNS["risk_factors"]),
        management_discussion=_extract_section(text, _SECTION_PATTERNS["management_discussion"]),
        forward_guidance=_extract_section(text, _SECTION_PATTERNS["forward_guidance"]),
        revenue=_extract_financial_value(text, _REVENUE_PATTERNS),
        net_income=_extract_financial_value(text, _NET_INCOME_PATTERNS),
        total_assets=_extract_financial_value(text, _TOTAL_ASSETS_PATTERNS),
    )


# ---------------------------------------------------------------------------
# FULL-TEXT SEARCH
# ---------------------------------------------------------------------------


async def search_filings(
    query: str,
    forms: str = "10-K",
    date_range: str = "",
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search SEC EDGAR filings using full-text search.

    Args:
        query: Search query string (e.g. "artificial intelligence revenue").
        forms: SEC form type to filter (default "10-K").
        date_range: Optional date range filter (e.g. "[2024-01-01 TO 2024-12-31]").
        limit: Maximum results to return.

    Returns:
        List of dicts with filing search results (entityName, fileDate, etc.).
        Empty list on failure.
    """
    params: dict[str, Any] = {
        "q": query,
        "forms": forms,
    }
    if date_range:
        params["dateRange"] = date_range

    try:
        resp = await _client.get(SEARCH_URL, params=params)
        data = resp.json()
    except Exception as e:
        logger.error("EDGAR search failed for query '%s': %s", query, e)
        return []

    hits = data.get("hits", {}).get("hits", [])
    results: list[dict[str, Any]] = []
    for hit in hits[:limit]:
        source = hit.get("_source", {})
        results.append({
            "entityName": source.get("entity_name", ""),
            "ticker": source.get("tickers", ""),
            "fileDate": source.get("file_date", ""),
            "form": source.get("form_type", ""),
            "accessionNumber": source.get("file_num", ""),
            "description": source.get("file_description", ""),
        })

    return results


# ---------------------------------------------------------------------------
# LLM-POWERED ANALYSIS
# ---------------------------------------------------------------------------

_ANALYSIS_PROMPT_TEMPLATE = """Analyze this 10-K filing for {ticker} (filed {date}).

RISK FACTORS:
{risk_factors}

MANAGEMENT DISCUSSION & ANALYSIS:
{management_discussion}

FINANCIAL HIGHLIGHTS:
Revenue context: {revenue}
Net income context: {net_income}
Total assets context: {total_assets}

FORWARD GUIDANCE:
{forward_guidance}

Provide your analysis in this exact format:
SENTIMENT: [bullish/bearish/neutral]
CONFIDENCE: [0.0-1.0]
KEY FINDINGS:
- [finding 1]
- [finding 2]
- [finding 3]
RISK HIGHLIGHTS:
- [risk 1]
- [risk 2]
- [risk 3]
"""

# Keywords for rule-based sentiment scoring
_BULLISH_KEYWORDS = [
    "growth", "increased revenue", "record revenue", "expansion",
    "strong demand", "exceeded expectations", "accelerating",
    "margin improvement", "increased profitability",
]
_BEARISH_KEYWORDS = [
    "decline", "decreased revenue", "loss", "impairment",
    "restructuring", "headwinds", "below expectations",
    "margin compression", "deteriorating", "uncertainty",
]


def _rule_based_analysis(filing: SECFiling, sections: FilingSections) -> FilingAnalysis:
    """Fallback rule-based analysis when no LLM agent is available.

    Performs simple keyword counting to estimate sentiment.

    Args:
        filing: The SEC filing.
        sections: Extracted financial sections.

    Returns:
        FilingAnalysis with rule-based sentiment.
    """
    combined = " ".join([
        sections.risk_factors,
        sections.management_discussion,
        sections.forward_guidance,
        sections.revenue,
        sections.net_income,
    ]).lower()

    bullish_count = sum(1 for kw in _BULLISH_KEYWORDS if kw in combined)
    bearish_count = sum(1 for kw in _BEARISH_KEYWORDS if kw in combined)

    total = bullish_count + bearish_count
    if total == 0:
        sentiment = "neutral"
        confidence = 0.3
    elif bullish_count > bearish_count:
        sentiment = "bullish"
        confidence = min(0.8, 0.4 + 0.1 * (bullish_count - bearish_count))
    elif bearish_count > bullish_count:
        sentiment = "bearish"
        confidence = min(0.8, 0.4 + 0.1 * (bearish_count - bullish_count))
    else:
        sentiment = "neutral"
        confidence = 0.4

    findings: list[str] = []
    if sections.revenue:
        findings.append(f"Revenue context extracted ({len(sections.revenue)} chars)")
    if sections.net_income:
        findings.append(f"Net income context extracted ({len(sections.net_income)} chars)")
    if sections.management_discussion:
        findings.append("Management discussion section available for review")

    risks: list[str] = []
    if sections.risk_factors:
        risks.append(f"Risk factors section extracted ({len(sections.risk_factors)} chars)")
    else:
        risks.append("Risk factors section not found in filing")
    risks.append(f"Rule-based analysis (keyword match: {bullish_count} bullish, {bearish_count} bearish)")

    return FilingAnalysis(
        ticker=filing.ticker,
        filing_date=filing.date_filed,
        sentiment=sentiment,
        confidence=round(confidence, 2),
        key_findings=findings,
        risk_highlights=risks,
        analyzed_at=_utc_now().isoformat(),
    )


async def analyze_filing_with_agent(
    filing: SECFiling,
    sections: FilingSections,
    agent_fn: Callable[[str], Awaitable[str]] | None = None,
) -> FilingAnalysis:
    """Analyze a 10-K filing using an LLM agent or rule-based fallback.

    Builds an analysis prompt from extracted sections and passes it to
    the provided agent function. If agent_fn is None, falls back to
    simple keyword-based sentiment analysis.

    Args:
        filing: The SEC filing to analyze.
        sections: Extracted financial sections.
        agent_fn: Async callable that takes a prompt string and returns
                  the LLM's response string. If None, uses rule-based analysis.

    Returns:
        FilingAnalysis with sentiment, confidence, and findings.
    """
    if agent_fn is None:
        return _rule_based_analysis(filing, sections)

    prompt = _ANALYSIS_PROMPT_TEMPLATE.format(
        ticker=filing.ticker,
        date=filing.date_filed,
        risk_factors=sections.risk_factors[:_SECTION_MAX_CHARS] or "(not found)",
        management_discussion=sections.management_discussion[:_SECTION_MAX_CHARS] or "(not found)",
        revenue=sections.revenue or "(not found)",
        net_income=sections.net_income or "(not found)",
        total_assets=sections.total_assets or "(not found)",
        forward_guidance=sections.forward_guidance[:_SECTION_MAX_CHARS] or "(not found)",
    )

    try:
        response = await agent_fn(prompt)
    except Exception as e:
        logger.error("Agent analysis failed for %s: %s", filing.ticker, e)
        return _rule_based_analysis(filing, sections)

    # Parse structured response
    return _parse_agent_response(filing, response)


def _parse_agent_response(filing: SECFiling, response: str) -> FilingAnalysis:
    """Parse an LLM agent's structured response into FilingAnalysis.

    Expects the format defined in _ANALYSIS_PROMPT_TEMPLATE.
    Falls back gracefully if parsing fails.

    Args:
        filing: The source filing.
        response: Raw LLM response text.

    Returns:
        FilingAnalysis populated from the response.
    """
    sentiment = "neutral"
    confidence = 0.5
    key_findings: list[str] = []
    risk_highlights: list[str] = []

    # Extract sentiment
    sent_match = re.search(r"SENTIMENT:\s*(bullish|bearish|neutral)", response, re.IGNORECASE)
    if sent_match:
        sentiment = sent_match.group(1).lower()

    # Extract confidence
    conf_match = re.search(r"CONFIDENCE:\s*([\d.]+)", response)
    if conf_match:
        try:
            confidence = max(0.0, min(1.0, float(conf_match.group(1))))
        except ValueError:
            pass

    # Extract key findings (lines starting with "- " after KEY FINDINGS:)
    findings_section = re.search(
        r"KEY FINDINGS:\s*\n((?:\s*-\s*.+\n?)+)",
        response,
        re.IGNORECASE,
    )
    if findings_section:
        for line in findings_section.group(1).strip().split("\n"):
            line = line.strip().lstrip("- ").strip()
            if line:
                key_findings.append(line)

    # Extract risk highlights
    risks_section = re.search(
        r"RISK HIGHLIGHTS:\s*\n((?:\s*-\s*.+\n?)+)",
        response,
        re.IGNORECASE,
    )
    if risks_section:
        for line in risks_section.group(1).strip().split("\n"):
            line = line.strip().lstrip("- ").strip()
            if line:
                risk_highlights.append(line)

    return FilingAnalysis(
        ticker=filing.ticker,
        filing_date=filing.date_filed,
        sentiment=sentiment,
        confidence=round(confidence, 2),
        key_findings=key_findings or ["Analysis completed but no structured findings extracted"],
        risk_highlights=risk_highlights or ["No structured risk highlights extracted"],
        analyzed_at=_utc_now().isoformat(),
    )


# ---------------------------------------------------------------------------
# PERSISTENCE HELPERS
# ---------------------------------------------------------------------------


def save_analysis(analysis: FilingAnalysis) -> Path:
    """Save a FilingAnalysis to disk as JSON.

    Args:
        analysis: The analysis to persist.

    Returns:
        Path to the saved JSON file.
    """
    d = _ensure_dirs(analysis.ticker)
    safe_date = analysis.filing_date.replace("-", "")
    p = d / f"analysis_{safe_date}.json"
    p.write_text(json.dumps(asdict(analysis), indent=2), encoding="utf-8")
    logger.info("Saved analysis to %s", p)
    return p


def load_analysis(ticker: str, filing_date: str) -> FilingAnalysis | None:
    """Load a previously saved FilingAnalysis from disk.

    Args:
        ticker: Stock ticker symbol.
        filing_date: Filing date (YYYY-MM-DD format).

    Returns:
        FilingAnalysis or None if not found.
    """
    safe_date = filing_date.replace("-", "")
    p = SEC_DIR / ticker.upper() / f"analysis_{safe_date}.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return FilingAnalysis(**data)
    except Exception as e:
        logger.error("Failed to load analysis from %s: %s", p, e)
        return None


# ---------------------------------------------------------------------------
# CONVENIENCE: END-TO-END PIPELINE
# ---------------------------------------------------------------------------


async def analyze_ticker(
    ticker: str,
    agent_fn: Callable[[str], Awaitable[str]] | None = None,
) -> FilingAnalysis | None:
    """Full pipeline: fetch 10-K, extract sections, analyze.

    Convenience function that chains fetch_recent_10k -> extract_financial_sections
    -> analyze_filing_with_agent and persists the result.

    Args:
        ticker: Stock ticker symbol.
        agent_fn: Optional async LLM agent callable.

    Returns:
        FilingAnalysis or None if filing could not be fetched.
    """
    filing = await fetch_recent_10k(ticker)
    if not filing:
        return None

    sections = extract_financial_sections(filing)
    analysis = await analyze_filing_with_agent(filing, sections, agent_fn)
    save_analysis(analysis)
    return analysis


async def analyze_tickers_batch(
    tickers: list[str],
    agent_fn: Callable[[str], Awaitable[str]] | None = None,
) -> list[FilingAnalysis]:
    """Full pipeline for multiple tickers.

    Args:
        tickers: List of ticker symbols.
        agent_fn: Optional async LLM agent callable.

    Returns:
        List of FilingAnalysis results (failures omitted).
    """
    filings = await fetch_recent_10k_batch(tickers)
    results: list[FilingAnalysis] = []

    for filing in filings:
        try:
            sections = extract_financial_sections(filing)
            analysis = await analyze_filing_with_agent(filing, sections, agent_fn)
            save_analysis(analysis)
            results.append(analysis)
        except Exception as e:
            logger.error("Analysis pipeline failed for %s: %s", filing.ticker, e)

    return results


# ---------------------------------------------------------------------------
# CLEANUP
# ---------------------------------------------------------------------------


async def close() -> None:
    """Close the shared HTTP client. Call on shutdown."""
    await _client.close()
