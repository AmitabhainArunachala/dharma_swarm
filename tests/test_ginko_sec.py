"""Tests for Ginko SEC EDGAR pipeline (dharma_swarm.ginko_sec)."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

_temp_dir = tempfile.mkdtemp()
os.environ.setdefault("DHARMA_HOME", _temp_dir)

from dharma_swarm.ginko_sec import (
    FilingAnalysis,
    FilingSections,
    SECFiling,
    TICKER_CIK,
    SEC_USER_AGENT,
    _strip_html,
    analyze_filing_with_agent,
    extract_financial_sections,
    fetch_company_filings,
    fetch_recent_10k,
    fetch_recent_10k_batch,
    search_filings,
)

# ---------------------------------------------------------------------------
# Shared fixtures / constants
# ---------------------------------------------------------------------------

SAMPLE_SUBMISSIONS: dict = {
    "cik": "320193",
    "entityType": "operating",
    "name": "Apple Inc",
    "tickers": ["AAPL"],
    "filings": {
        "recent": {
            "form": ["10-K", "10-Q", "8-K"],
            "filingDate": ["2025-11-01", "2025-08-01", "2025-06-15"],
            "accessionNumber": [
                "0000320193-25-000001",
                "0000320193-25-000002",
                "0000320193-25-000003",
            ],
            "primaryDocument": [
                "aapl-20250928.htm",
                "aapl-q3.htm",
                "aapl-8k.htm",
            ],
        }
    },
}

SAMPLE_10K_HTML: str = """
<html><body>
<h2>Item 1A. Risk Factors</h2>
<p>The company faces risks related to global economic conditions,
supply chain disruptions, and foreign currency fluctuations.</p>
<h2>Item 7. Management's Discussion and Analysis</h2>
<p>Revenue increased 12% year over year driven by iPhone sales
and the services segment achieving record quarterly revenue.</p>
<h2>Item 8. Financial Statements</h2>
<p>Total revenue: $394.3 billion. Net income: $97.0 billion.</p>
</body></html>
"""


def _make_filing(
    *,
    raw_text: str = "",
    ticker: str = "AAPL",
) -> SECFiling:
    """Build a minimal SECFiling for testing."""
    return SECFiling(
        company="Apple Inc",
        ticker=ticker,
        cik="0000320193",
        filing_type="10-K",
        date_filed="2025-11-01",
        accession_number="0000320193-25-000001",
        url="https://www.sec.gov/Archives/edgar/data/320193/0000320193-25-000001/aapl-20250928.htm",
        raw_text=raw_text,
    )


def _mock_httpx_response(
    *,
    json_data: dict | None = None,
    text: str = "",
    status_code: int = 200,
) -> MagicMock:
    """Build a mock httpx.Response with sync .json() and .text property.

    The _SECClient.get() calls raise_for_status() on the response, then
    callers access resp.json() (sync) and resp.text (property). This helper
    produces a mock that satisfies both patterns.
    """
    mock = MagicMock(spec=httpx.Response)
    mock.status_code = status_code
    mock.text = text
    if json_data is not None:
        mock.json.return_value = json_data
    else:
        mock.json.return_value = {}
    mock.raise_for_status.return_value = None
    return mock


# ===================================================================
# TestSECDataModels
# ===================================================================


class TestSECDataModels:
    """Verify dataclass construction and defaults."""

    def test_sec_filing_creation(self):
        filing = _make_filing(raw_text="hello")
        assert filing.company == "Apple Inc"
        assert filing.ticker == "AAPL"
        assert filing.cik == "0000320193"
        assert filing.filing_type == "10-K"
        assert filing.date_filed == "2025-11-01"
        assert filing.accession_number == "0000320193-25-000001"
        assert filing.url.startswith("https://")
        assert filing.raw_text == "hello"

    def test_filing_sections_defaults(self):
        sections = FilingSections()
        assert sections.revenue == ""
        assert sections.net_income == ""
        assert sections.risk_factors == ""
        assert sections.management_discussion == ""
        assert sections.forward_guidance == ""
        assert sections.total_assets == ""

    def test_filing_analysis_creation(self):
        analysis = FilingAnalysis(
            ticker="AAPL",
            filing_date="2025-11-01",
            sentiment="bullish",
            confidence=0.85,
            key_findings=["Revenue grew 12%", "Services at record high"],
            risk_highlights=["Supply chain risk", "FX exposure"],
            analyzed_at="2026-03-17T04:30:00Z",
        )
        assert analysis.ticker == "AAPL"
        assert analysis.sentiment == "bullish"
        assert analysis.confidence == 0.85
        assert len(analysis.key_findings) == 2
        assert len(analysis.risk_highlights) == 2
        assert analysis.analyzed_at.endswith("Z")


# ===================================================================
# TestTickerCIKMapping
# ===================================================================


class TestTickerCIKMapping:
    """Validate the hardcoded ticker -> CIK lookup table."""

    def test_known_ticker_lookup(self):
        assert TICKER_CIK["AAPL"] == "0000320193"
        assert TICKER_CIK["MSFT"] == "0000789019"
        assert TICKER_CIK["NVDA"] == "0001045810"

    def test_unknown_ticker(self):
        result = TICKER_CIK.get("ZZZZZZ_FAKE")
        assert result is None


# ===================================================================
# TestFetchCompanyFilings
# ===================================================================


class TestFetchCompanyFilings:
    """Test SEC submissions API integration."""

    @pytest.mark.asyncio
    async def test_fetch_filings_success(self):
        """Mock _client.get to return a successful SEC submissions response."""
        mock_resp = _mock_httpx_response(json_data=SAMPLE_SUBMISSIONS)

        mock_get = AsyncMock(return_value=mock_resp)

        with patch("dharma_swarm.ginko_sec._client") as mock_client:
            mock_client.get = mock_get
            filings = await fetch_company_filings("AAPL", filing_type="10-K", limit=1)

        assert isinstance(filings, list)
        assert len(filings) >= 1
        first = filings[0]
        assert first["form"] == "10-K"

    @pytest.mark.asyncio
    async def test_fetch_filings_not_found(self):
        """CIK resolution failure for unknown ticker returns empty list."""
        # Patch _resolve_cik to return None (unknown ticker, no network)
        with patch("dharma_swarm.ginko_sec._resolve_cik", new_callable=AsyncMock, return_value=None):
            filings = await fetch_company_filings("ZZZZZZ_FAKE", filing_type="10-K")

        assert filings == []

    @pytest.mark.asyncio
    async def test_fetch_filings_network_error(self):
        """httpx error during fetch should return empty list, not raise."""
        mock_get = AsyncMock(side_effect=httpx.HTTPError("connection refused"))

        with patch("dharma_swarm.ginko_sec._client") as mock_client:
            mock_client.get = mock_get
            filings = await fetch_company_filings("AAPL")

        assert filings == []


# ===================================================================
# TestFetchRecent10K
# ===================================================================


class TestFetchRecent10K:
    """Test high-level 10-K fetch with doc download."""

    @pytest.mark.asyncio
    async def test_fetch_10k_success(self):
        """Mock submissions + doc fetch, verify SECFiling with raw_text."""
        # First call: submissions endpoint -> JSON with filing metadata
        mock_submissions_resp = _mock_httpx_response(json_data=SAMPLE_SUBMISSIONS)

        # Second call: actual filing document -> HTML text
        mock_doc_resp = _mock_httpx_response(text=SAMPLE_10K_HTML)

        call_count = 0

        async def mock_get(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_submissions_resp
            return mock_doc_resp

        with (
            patch("dharma_swarm.ginko_sec._client") as mock_client,
            patch("dharma_swarm.ginko_sec._load_cached", return_value=None),
        ):
            mock_client.get = mock_get
            filing = await fetch_recent_10k("AAPL")

        assert filing is not None
        assert isinstance(filing, SECFiling)
        assert filing.ticker == "AAPL"
        assert filing.filing_type == "10-K"
        assert len(filing.raw_text) > 0

    @pytest.mark.asyncio
    async def test_fetch_10k_cached(self):
        """When _load_cached returns content, no HTTP call should be made for the doc."""
        # Submissions call still needed to get metadata
        mock_submissions_resp = _mock_httpx_response(json_data=SAMPLE_SUBMISSIONS)
        mock_get = AsyncMock(return_value=mock_submissions_resp)

        with (
            patch("dharma_swarm.ginko_sec._client") as mock_client,
            patch("dharma_swarm.ginko_sec._load_cached", return_value="cached filing content"),
        ):
            mock_client.get = mock_get
            filing = await fetch_recent_10k("AAPL")

        assert filing is not None
        assert isinstance(filing, SECFiling)
        assert filing.raw_text == "cached filing content"
        # Only 1 call (submissions), not 2 (no doc fetch needed)
        assert mock_get.call_count == 1


# ===================================================================
# TestExtractSections
# ===================================================================


class TestExtractSections:
    """Test section extraction from raw 10-K text."""

    def test_extract_risk_factors(self):
        filing = _make_filing(raw_text=(
            "Some preamble text.\n"
            "Item 1A. Risk Factors\n"
            "The company faces risks related to global economic conditions, "
            "supply chain disruptions, and regulatory changes.\n"
            "Item 1B. Unresolved Staff Comments\n"
            "None.\n"
        ))
        sections = extract_financial_sections(filing)
        assert sections.risk_factors != ""
        assert "economic conditions" in sections.risk_factors.lower() or \
               "risk" in sections.risk_factors.lower()

    def test_extract_management_discussion(self):
        filing = _make_filing(raw_text=(
            "Item 6. Selected Financial Data\n"
            "Omitted per updated SEC rules.\n"
            "Item 7. Management's Discussion and Analysis\n"
            "Revenue increased 12% year over year driven by iPhone sales "
            "and the services segment. Operating expenses grew 8%.\n"
            "Item 7A. Quantitative and Qualitative Disclosures\n"
            "Foreign currency risk remains material.\n"
        ))
        sections = extract_financial_sections(filing)
        assert sections.management_discussion != ""
        assert "revenue" in sections.management_discussion.lower() or \
               "discussion" in sections.management_discussion.lower()

    def test_extract_empty_filing(self):
        filing = _make_filing(raw_text="")
        sections = extract_financial_sections(filing)
        assert sections.revenue == ""
        assert sections.net_income == ""
        assert sections.risk_factors == ""
        assert sections.management_discussion == ""
        assert sections.forward_guidance == ""
        assert sections.total_assets == ""


# ===================================================================
# TestAnalyzeWithAgent
# ===================================================================


class TestAnalyzeWithAgent:
    """Test LLM-backed analysis of SEC filings."""

    @pytest.mark.asyncio
    async def test_analyze_with_mock_agent(self):
        """Agent returns a structured bullish analysis."""
        filing = _make_filing(raw_text=SAMPLE_10K_HTML)
        sections = FilingSections(
            revenue="$394.3 billion",
            net_income="$97.0 billion",
            risk_factors="Supply chain disruptions, FX exposure.",
            management_discussion="Revenue increased 12% YoY.",
        )

        async def mock_agent(prompt: str) -> str:
            return (
                "SENTIMENT: bullish\n"
                "CONFIDENCE: 0.88\n"
                "KEY FINDINGS:\n"
                "- Revenue up 12%\n"
                "- Services record quarter\n"
                "RISK HIGHLIGHTS:\n"
                "- Supply chain risk\n"
            )

        analysis = await analyze_filing_with_agent(filing, sections, agent_fn=mock_agent)
        assert isinstance(analysis, FilingAnalysis)
        assert analysis.ticker == "AAPL"
        assert analysis.sentiment == "bullish"
        assert analysis.confidence == pytest.approx(0.88, abs=0.01)
        assert len(analysis.key_findings) >= 1
        assert len(analysis.risk_highlights) >= 1

    @pytest.mark.asyncio
    async def test_analyze_without_agent(self):
        """With agent_fn=None, should return a basic/heuristic analysis."""
        filing = _make_filing(raw_text=SAMPLE_10K_HTML)
        sections = FilingSections(
            revenue="$394.3 billion",
            risk_factors="Significant regulatory risk.",
        )

        analysis = await analyze_filing_with_agent(filing, sections, agent_fn=None)
        assert isinstance(analysis, FilingAnalysis)
        assert analysis.ticker == "AAPL"
        assert analysis.sentiment in ("bullish", "bearish", "neutral")
        assert 0.0 <= analysis.confidence <= 1.0
        assert isinstance(analysis.key_findings, list)
        assert isinstance(analysis.risk_highlights, list)


# ===================================================================
# TestStripHTML
# ===================================================================


class TestStripHTML:
    """Test HTML tag stripping utility."""

    def test_strip_basic_html(self):
        html = "<p>Hello <b>world</b></p>"
        result = _strip_html(html)
        assert "Hello" in result
        assert "world" in result
        assert "<p>" not in result
        assert "<b>" not in result

    def test_strip_complex_html(self):
        html = (
            "<html><head><title>Test</title>"
            "<script>var x = 1;</script>"
            "<style>.foo { color: red; }</style>"
            "</head><body>"
            "<div class='section'>"
            "<p>Revenue was &amp; profit grew &gt; 10%.</p>"
            "<table><tr><td>$100M</td></tr></table>"
            "</div></body></html>"
        )
        result = _strip_html(html)
        assert "Revenue was" in result
        assert "profit grew" in result
        assert "$100M" in result
        # Script and style content should be stripped
        assert "var x" not in result
        assert ".foo" not in result
        # Tags should be gone
        assert "<div" not in result
        assert "<table" not in result


# ===================================================================
# TestBatchFetch
# ===================================================================


class TestBatchFetch:
    """Test concurrent batch fetching of 10-K filings."""

    @pytest.mark.asyncio
    async def test_batch_fetch(self):
        """Mock 3 tickers, verify all resolved concurrently."""
        tickers = ["AAPL", "MSFT", "NVDA"]
        call_log: list[str] = []

        async def mock_fetch_10k(ticker: str) -> SECFiling | None:
            call_log.append(ticker)
            return _make_filing(ticker=ticker, raw_text=f"{ticker} filing content")

        with patch("dharma_swarm.ginko_sec.fetch_recent_10k", side_effect=mock_fetch_10k):
            results = await fetch_recent_10k_batch(tickers)

        assert len(results) == 3
        assert set(call_log) == {"AAPL", "MSFT", "NVDA"}
        for filing in results:
            assert isinstance(filing, SECFiling)
            assert filing.ticker in tickers
            assert filing.raw_text.endswith("filing content")


# ===================================================================
# TestSearchFilings
# ===================================================================


class TestSearchFilings:
    """Test EDGAR full-text search endpoint."""

    @pytest.mark.asyncio
    async def test_search_filings_success(self):
        """Mock _client.get for EFTS response with matching results."""
        mock_efts_response = {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "file_num": "001-36743",
                            "entity_name": "Apple Inc",
                            "tickers": "AAPL",
                            "form_type": "10-K",
                            "file_date": "2025-11-01",
                        }
                    },
                ]
            }
        }

        mock_resp = _mock_httpx_response(json_data=mock_efts_response)
        mock_get = AsyncMock(return_value=mock_resp)

        with patch("dharma_swarm.ginko_sec._client") as mock_client:
            mock_client.get = mock_get
            results = await search_filings("Apple revenue growth", forms="10-K")

        assert isinstance(results, list)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_search_filings_empty(self):
        """No results should return empty list."""
        mock_resp = _mock_httpx_response(json_data={"hits": {"hits": []}})
        mock_get = AsyncMock(return_value=mock_resp)

        with patch("dharma_swarm.ginko_sec._client") as mock_client:
            mock_client.get = mock_get
            results = await search_filings("zzzzz nonexistent query")

        assert results == []


# ===================================================================
# TestSECUserAgent
# ===================================================================


class TestSECUserAgent:
    """SEC requires a descriptive User-Agent; verify it is set."""

    def test_user_agent_format(self):
        assert "DharmicQuant" in SEC_USER_AGENT
        assert "@" in SEC_USER_AGENT  # Must contain contact email
