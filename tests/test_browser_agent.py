"""Tests for BrowserAgent — web interaction layer for dharma_swarm.

Tests cover:
- URL security (blocked schemes, localhost, private IPs)
- Rate limiting
- Navigation (Playwright and httpx fallback)
- Content extraction
- Search
- Screenshot
- Tool registry integration
- PageContent / SearchResult data models
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dharma_swarm.browser_agent import (
    BrowserAgent,
    PageContent,
    SearchResult,
    ScreenshotResult,
    _RateLimiter,
    _is_url_blocked,
    _strip_html,
    _extract_title,
    _check_browser_available,
)


# ── URL Security Tests ─────────────────────────────────────────────────

class TestURLSecurity:
    """Verify that blocked URLs are correctly rejected."""

    def test_blocks_file_scheme(self):
        assert _is_url_blocked("file:///etc/passwd") is not None

    def test_blocks_ftp_scheme(self):
        assert _is_url_blocked("ftp://example.com/file") is not None

    def test_blocks_data_scheme(self):
        assert _is_url_blocked("data:text/html,<h1>hi</h1>") is not None

    def test_blocks_javascript_scheme(self):
        assert _is_url_blocked("javascript:alert(1)") is not None

    def test_blocks_localhost(self):
        assert _is_url_blocked("http://localhost:8080/") is not None

    def test_blocks_127(self):
        assert _is_url_blocked("http://127.0.0.1:3000/api") is not None

    def test_blocks_zero_zero(self):
        assert _is_url_blocked("http://0.0.0.0/") is not None

    def test_blocks_private_10(self):
        assert _is_url_blocked("http://10.0.0.1/admin") is not None

    def test_blocks_private_172(self):
        assert _is_url_blocked("http://172.16.0.1/") is not None

    def test_blocks_private_192(self):
        assert _is_url_blocked("http://192.168.1.1/") is not None

    def test_allows_public_url(self):
        assert _is_url_blocked("https://example.com") is None

    def test_allows_public_ip(self):
        assert _is_url_blocked("http://8.8.8.8/") is None

    def test_allows_localhost_when_flag_set(self):
        assert _is_url_blocked("http://localhost/", allow_localhost=True) is None

    def test_allows_private_ip_when_flag_set(self):
        assert _is_url_blocked("http://192.168.1.1/", allow_localhost=True) is None


# ── HTML Utility Tests ─────────────────────────────────────────────────

class TestHTMLUtils:
    """Test HTML stripping and title extraction."""

    def test_strip_html_basic(self):
        assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"

    def test_strip_html_whitespace(self):
        assert _strip_html("<p>  Hello   <br>  world  </p>") == "Hello world"

    def test_strip_html_empty(self):
        assert _strip_html("") == ""

    def test_strip_html_no_tags(self):
        assert _strip_html("plain text") == "plain text"

    def test_extract_title(self):
        assert _extract_title("<html><head><title>My Page</title></head></html>") == "My Page"

    def test_extract_title_missing(self):
        assert _extract_title("<html><body>no title</body></html>") == ""

    def test_extract_title_whitespace(self):
        assert _extract_title("<title>  Trimmed  </title>") == "Trimmed"


# ── Data Model Tests ───────────────────────────────────────────────────

class TestDataModels:
    """Test PageContent and SearchResult serialization."""

    def test_page_content_to_dict(self):
        pc = PageContent(
            url="https://example.com",
            title="Example",
            text="Hello world",
            status=200,
            elapsed_ms=123.456,
            method="playwright",
        )
        d = pc.to_dict()
        assert d["url"] == "https://example.com"
        assert d["title"] == "Example"
        assert d["status"] == 200
        assert d["elapsed_ms"] == 123.5
        assert d["method"] == "playwright"
        assert d["error"] is None

    def test_page_content_with_error(self):
        pc = PageContent(
            url="https://fail.com",
            title="",
            text="",
            status=0,
            elapsed_ms=50.0,
            method="httpx",
            error="Connection refused",
        )
        d = pc.to_dict()
        assert d["error"] == "Connection refused"
        assert d["status"] == 0

    def test_page_content_truncates_text(self):
        long_text = "x" * 200_000
        pc = PageContent(
            url="https://example.com", title="", text=long_text,
            status=200, elapsed_ms=0, method="httpx",
        )
        d = pc.to_dict()
        assert len(d["text"]) == 100_000

    def test_search_result_to_dict(self):
        sr = SearchResult(title="Result", url="https://result.com", snippet="A result")
        d = sr.to_dict()
        assert d["title"] == "Result"
        assert d["url"] == "https://result.com"
        assert d["snippet"] == "A result"


# ── Rate Limiter Tests ─────────────────────────────────────────────────

class TestRateLimiter:
    """Test the async rate limiter."""

    @pytest.mark.asyncio
    async def test_rate_limiter_enforces_interval(self):
        limiter = _RateLimiter(requests_per_second=10.0)  # 100ms interval
        t0 = time.monotonic()
        await limiter.acquire()
        await limiter.acquire()
        elapsed = time.monotonic() - t0
        # Second acquire should wait ~100ms
        assert elapsed >= 0.08  # Allow some slack

    @pytest.mark.asyncio
    async def test_rate_limiter_first_request_instant(self):
        limiter = _RateLimiter(requests_per_second=1.0)
        t0 = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - t0
        # First request should be nearly instant
        assert elapsed < 0.1


# ── BrowserAgent Unit Tests (mocked Playwright) ───────────────────────

class TestBrowserAgentInit:
    """Test BrowserAgent initialization and cleanup."""

    def test_default_config(self):
        ba = BrowserAgent()
        assert ba.headless is True
        assert ba.timeout_ms == 30_000
        assert ba.allow_localhost is False
        assert ba._started is False

    def test_custom_config(self):
        ba = BrowserAgent(
            headless=False, rate_limit=2.0, timeout_ms=60_000,
            allow_localhost=True, user_agent="TestBot/1.0",
        )
        assert ba.headless is False
        assert ba.timeout_ms == 60_000
        assert ba.allow_localhost is True
        assert ba._user_agent == "TestBot/1.0"


class TestBrowserAgentSecurity:
    """Test that BrowserAgent enforces URL security."""

    @pytest.mark.asyncio
    async def test_navigate_blocks_file_url(self):
        ba = BrowserAgent()
        ba._started = True
        ba._has_playwright = False
        with pytest.raises(ValueError, match="Blocked scheme"):
            await ba.navigate("file:///etc/passwd")

    @pytest.mark.asyncio
    async def test_navigate_blocks_localhost(self):
        ba = BrowserAgent()
        ba._started = True
        ba._has_playwright = False
        with pytest.raises(ValueError, match="Blocked host"):
            await ba.navigate("http://localhost:8080/secret")

    @pytest.mark.asyncio
    async def test_navigate_blocks_private_ip(self):
        ba = BrowserAgent()
        ba._started = True
        ba._has_playwright = False
        with pytest.raises(ValueError, match="Blocked private IP"):
            await ba.navigate("http://10.0.0.1/admin")

    @pytest.mark.asyncio
    async def test_extract_blocks_file_url(self):
        ba = BrowserAgent()
        ba._started = True
        ba._has_playwright = False
        with pytest.raises(ValueError, match="Blocked scheme"):
            await ba.extract("file:///etc/shadow", "body")

    @pytest.mark.asyncio
    async def test_screenshot_blocks_localhost(self):
        ba = BrowserAgent()
        ba._started = True
        ba._has_playwright = True
        with pytest.raises(ValueError, match="Blocked host"):
            await ba.screenshot("http://127.0.0.1/")

    @pytest.mark.asyncio
    async def test_click_blocks_private_ip(self):
        ba = BrowserAgent()
        ba._started = True
        ba._has_playwright = True
        with pytest.raises(ValueError, match="Blocked private IP"):
            await ba.click("http://192.168.0.1/", "button")


class TestBrowserAgentHttpxFallback:
    """Test that httpx fallback works when Playwright is unavailable."""

    @pytest.mark.asyncio
    async def test_navigate_httpx_fallback(self):
        """Simulate httpx fallback by forcing _has_playwright=False."""
        ba = BrowserAgent()
        ba._started = True
        ba._has_playwright = False

        # Mock httpx
        mock_response = MagicMock()
        mock_response.text = "<html><head><title>Test Page</title></head><body><p>Hello World</p></body></html>"
        mock_response.status_code = 200
        mock_response.url = "https://example.com"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await ba.navigate("https://example.com")

        assert result.method == "httpx"
        assert result.status == 200
        assert result.title == "Test Page"
        assert "Hello World" in result.text
        assert result.error is None

    @pytest.mark.asyncio
    async def test_navigate_httpx_error(self):
        """Test httpx error handling."""
        ba = BrowserAgent()
        ba._started = True
        ba._has_playwright = False

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await ba.navigate("https://unreachable.invalid")

        assert result.method == "httpx"
        assert result.error is not None
        assert "Connection refused" in result.error
        assert result.status == 0

    @pytest.mark.asyncio
    async def test_click_without_playwright(self):
        """Click should return error when Playwright unavailable."""
        ba = BrowserAgent()
        ba._started = True
        ba._has_playwright = False

        result = await ba.click("https://example.com", "button")
        assert result.error is not None
        assert "Playwright" in result.error

    @pytest.mark.asyncio
    async def test_type_without_playwright(self):
        """Type should return error when Playwright unavailable."""
        ba = BrowserAgent()
        ba._started = True
        ba._has_playwright = False

        result = await ba.type_text("https://example.com", "input", "hello")
        assert result.error is not None
        assert "Playwright" in result.error

    @pytest.mark.asyncio
    async def test_screenshot_without_playwright(self):
        """Screenshot should return error when Playwright unavailable."""
        ba = BrowserAgent()
        ba._started = True
        ba._has_playwright = False

        result = await ba.screenshot("https://example.com")
        assert result.error is not None
        assert "Playwright" in result.error
        assert result.png_bytes == b""


# ── Tool Registry Integration ──────────────────────────────────────────

class TestToolRegistryIntegration:
    """Test that browser tools are registered in the tool registry."""

    def test_check_browser_available(self):
        assert _check_browser_available() is True

    def test_tools_registered(self):
        from dharma_swarm.tool_registry import registry
        # browser_agent auto-registers on import
        assert "browser_navigate" in registry
        assert "browser_extract" in registry
        assert "browser_screenshot" in registry
        assert "browser_search" in registry

    def test_toolset_is_browser(self):
        from dharma_swarm.tool_registry import registry
        assert registry.get_toolset_for_tool("browser_navigate") == "browser"
        assert registry.get_toolset_for_tool("browser_extract") == "browser"

    def test_browser_toolset_available(self):
        from dharma_swarm.tool_registry import registry
        assert registry.is_toolset_available("browser") is True


# ── Search Tests (mocked) ─────────────────────────────────────────────

class TestSearch:
    """Test web search with mocked responses."""

    @pytest.mark.asyncio
    async def test_search_unsupported_engine(self):
        ba = BrowserAgent()
        ba._started = True
        ba._has_playwright = False

        with pytest.raises(ValueError, match="Unsupported search engine"):
            await ba.search("test query", engine="bing")

    @pytest.mark.asyncio
    async def test_search_ddg_error(self):
        """DuckDuckGo search should return empty list on error."""
        ba = BrowserAgent()
        ba._started = True
        ba._has_playwright = False

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Network error"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            results = await ba.search("test query")

        assert results == []

    @pytest.mark.asyncio
    async def test_search_ddg_parses_results(self):
        """Test that DDG HTML results are parsed correctly."""
        ba = BrowserAgent()
        ba._started = True
        ba._has_playwright = False

        fake_html = '''
        <div class="result">
            <a class="result__a" href="https://example.com">Example Title</a>
            <td class="result__snippet">This is the snippet text</td>
        </div>
        <div class="result">
            <a class="result__a" href="https://other.com">Other Result</a>
            <td class="result__snippet">Another snippet</td>
        </div>
        '''
        mock_response = MagicMock()
        mock_response.text = fake_html
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            results = await ba.search("test", max_results=5)

        assert len(results) == 2
        assert results[0].title == "Example Title"
        assert results[0].url == "https://example.com"
        assert results[0].snippet == "This is the snippet text"
        assert results[1].title == "Other Result"


# ── Cookie Management Tests ────────────────────────────────────────────

class TestCookieManagement:
    """Test cookie operations."""

    @pytest.mark.asyncio
    async def test_get_cookies_no_playwright(self):
        ba = BrowserAgent()
        ba._started = True
        ba._has_playwright = False
        assert await ba.get_cookies() == []

    @pytest.mark.asyncio
    async def test_clear_cookies_no_playwright(self):
        """Should not raise when Playwright unavailable."""
        ba = BrowserAgent()
        ba._started = True
        ba._has_playwright = False
        await ba.clear_cookies()  # Should not raise

    @pytest.mark.asyncio
    async def test_set_cookies_no_playwright(self):
        """Should not raise when Playwright unavailable."""
        ba = BrowserAgent()
        ba._started = True
        ba._has_playwright = False
        await ba.set_cookies([{"name": "test", "value": "val", "url": "https://example.com"}])


# ── Context Manager Tests ──────────────────────────────────────────────

class TestContextManager:
    """Test async context manager protocol."""

    @pytest.mark.asyncio
    async def test_context_manager_start_stop(self):
        """BrowserAgent should start/stop cleanly as context manager."""
        # Mock the Playwright import inside start() by patching the module lookup
        mock_pw_instance = AsyncMock()
        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_pw_instance.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        mock_pw_cm = AsyncMock()
        mock_pw_cm.start = AsyncMock(return_value=mock_pw_instance)

        with patch("playwright.async_api.async_playwright", return_value=mock_pw_cm):
            async with BrowserAgent() as ba:
                assert ba._started is True
                assert ba._has_playwright is True

            # After exit, stop should have been called
            assert ba._started is False


# ── Integration Tests (require real browser, skip in CI) ───────────────

@pytest.mark.skipif(
    not _check_browser_available(),
    reason="Playwright not installed",
)
class TestBrowserAgentLive:
    """Live integration tests. Run with: pytest -k 'Live' -v

    These hit real URLs so they're slow and can be flaky.
    They prove the full stack works end-to-end.
    """

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_navigate_real_page(self):
        """Navigate to a real page and extract content."""
        async with BrowserAgent(headless=True, rate_limit=2.0) as ba:
            result = await ba.navigate("https://httpbin.org/html")
            assert result.status == 200
            assert result.method == "playwright"
            assert "Herman Melville" in result.text
            assert result.error is None
            assert result.elapsed_ms > 0

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_extract_real_selector(self):
        """Extract content using a real CSS selector."""
        async with BrowserAgent(headless=True, rate_limit=2.0) as ba:
            text = await ba.extract("https://httpbin.org/html", "h1")
            assert "Herman Melville" in text

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_screenshot_real_page(self):
        """Take a real screenshot."""
        async with BrowserAgent(headless=True, rate_limit=2.0) as ba:
            result = await ba.screenshot("https://httpbin.org/html")
            assert result.error is None
            assert len(result.png_bytes) > 1000  # Should be a real PNG
            assert result.png_bytes[:4] == b"\x89PNG"
            assert result.width == 1280
            assert result.height == 720
