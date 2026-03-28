"""Browser Agent: Web interaction for dharma_swarm.

Provides agents with browsing capabilities:
- navigate(url) — go to a page, return cleaned text
- extract(url, selector) — get text/data from elements
- click(selector) — interact with page elements
- screenshot(url) — capture page state as PNG bytes
- search(query) — web search and result extraction

Uses Playwright for full browser automation (headless Chromium).
Falls back to httpx for simple GET requests if Playwright unavailable.

Security: blocks file:// URLs, localhost/private IPs by default.
Rate limiting: 1 request/sec default, configurable.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ── Security ───────────────────────────────────────────────────────────

_BLOCKED_SCHEMES = {"file", "ftp", "data", "javascript"}
_BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "[::1]"}

_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# Max content length to return (prevent memory blowouts)
_MAX_TEXT_LENGTH = 100_000
_MAX_SCREENSHOT_BYTES = 5_000_000  # 5MB


def _is_url_blocked(url: str, allow_localhost: bool = False) -> str | None:
    """Return a reason string if the URL is blocked, else None."""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    host = parsed.hostname or ""

    if scheme in _BLOCKED_SCHEMES:
        return f"Blocked scheme: {scheme}://"

    if not allow_localhost:
        if host in _BLOCKED_HOSTS:
            return f"Blocked host: {host}"
        try:
            addr = ipaddress.ip_address(host)
            for net in _PRIVATE_NETWORKS:
                if addr in net:
                    return f"Blocked private IP: {host}"
        except ValueError:
            pass  # Not an IP, that's fine (it's a hostname)

    return None


# ── Data Models ────────────────────────────────────────────────────────

@dataclass
class PageContent:
    """Result of navigating to a page."""
    url: str
    title: str
    text: str
    status: int
    elapsed_ms: float
    method: str  # "playwright" or "httpx"
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "text": self.text[:_MAX_TEXT_LENGTH],
            "status": self.status,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "method": self.method,
            "error": self.error,
        }


@dataclass
class SearchResult:
    """A single search result."""
    title: str
    url: str
    snippet: str

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "url": self.url, "snippet": self.snippet}


@dataclass
class ScreenshotResult:
    """Result of taking a screenshot."""
    url: str
    png_bytes: bytes
    width: int
    height: int
    elapsed_ms: float
    error: str | None = None


# ── Rate Limiter ───────────────────────────────────────────────────────

class _RateLimiter:
    """Token-bucket rate limiter. Async-safe."""

    def __init__(self, requests_per_second: float = 1.0):
        self._interval = 1.0 / requests_per_second
        self._last_request = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._interval - (now - self._last_request)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request = time.monotonic()


# ── Browser Agent ──────────────────────────────────────────────────────

class BrowserAgent:
    """Web browsing capability for dharma_swarm agents.

    Usage::

        async with BrowserAgent() as browser:
            page = await browser.navigate("https://example.com")
            print(page.text)

    Falls back to httpx if Playwright is not available.
    """

    def __init__(
        self,
        headless: bool = True,
        rate_limit: float = 1.0,
        timeout_ms: int = 30_000,
        allow_localhost: bool = False,
        user_agent: str | None = None,
    ):
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.allow_localhost = allow_localhost
        self._user_agent = user_agent or _USER_AGENTS[0]
        self._rate_limiter = _RateLimiter(rate_limit)
        self._playwright = None
        self._browser = None
        self._context = None
        self._has_playwright = False
        self._started = False

    async def start(self) -> None:
        """Initialize the browser. Call once before using."""
        if self._started:
            return
        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
            )
            self._context = await self._browser.new_context(
                user_agent=self._user_agent,
                viewport={"width": 1280, "height": 720},
                ignore_https_errors=False,
            )
            self._has_playwright = True
            logger.info("BrowserAgent started with Playwright (Chromium headless=%s)", self.headless)
        except Exception as e:
            logger.warning("Playwright unavailable (%s), falling back to httpx", e)
            self._has_playwright = False
        self._started = True

    async def stop(self) -> None:
        """Close browser and clean up."""
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        self._started = False
        self._has_playwright = False

    async def __aenter__(self) -> "BrowserAgent":
        await self.start()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.stop()

    def _check_url(self, url: str) -> None:
        """Raise ValueError if URL is blocked."""
        reason = _is_url_blocked(url, allow_localhost=self.allow_localhost)
        if reason:
            raise ValueError(reason)

    # ── Core operations ────────────────────────────────────────────────

    async def navigate(self, url: str) -> PageContent:
        """Navigate to a URL and return page content as cleaned text."""
        self._check_url(url)
        await self._rate_limiter.acquire()

        if not self._started:
            await self.start()

        if self._has_playwright:
            return await self._navigate_playwright(url)
        return await self._navigate_httpx(url)

    async def _navigate_playwright(self, url: str) -> PageContent:
        """Navigate using Playwright browser."""
        t0 = time.monotonic()
        page = await self._context.new_page()
        try:
            response = await page.goto(url, timeout=self.timeout_ms, wait_until="domcontentloaded")
            status = response.status if response else 0
            title = await page.title()
            # Get visible text content, stripping script/style
            text = await page.evaluate("""() => {
                const clone = document.cloneNode(true);
                clone.querySelectorAll('script, style, noscript, svg, img').forEach(el => el.remove());
                return clone.body ? clone.body.innerText : document.documentElement.innerText;
            }""")
            elapsed = (time.monotonic() - t0) * 1000
            return PageContent(
                url=page.url,
                title=title,
                text=(text or "")[:_MAX_TEXT_LENGTH],
                status=status,
                elapsed_ms=elapsed,
                method="playwright",
            )
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            return PageContent(
                url=url,
                title="",
                text="",
                status=0,
                elapsed_ms=elapsed,
                method="playwright",
                error=str(e),
            )
        finally:
            await page.close()

    async def _navigate_httpx(self, url: str) -> PageContent:
        """Fallback: navigate using httpx (no JS execution)."""
        import httpx

        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=self.timeout_ms / 1000,
                headers={"User-Agent": self._user_agent},
            ) as client:
                resp = await client.get(url)
                elapsed = (time.monotonic() - t0) * 1000
                text = resp.text[:_MAX_TEXT_LENGTH]
                # Strip HTML tags for a rough text extraction
                text = _strip_html(text)
                title = _extract_title(resp.text)
                return PageContent(
                    url=str(resp.url),
                    title=title,
                    text=text,
                    status=resp.status_code,
                    elapsed_ms=elapsed,
                    method="httpx",
                )
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            return PageContent(
                url=url,
                title="",
                text="",
                status=0,
                elapsed_ms=elapsed,
                method="httpx",
                error=str(e),
            )

    async def extract(self, url: str, selector: str) -> str:
        """Navigate to URL and extract text from elements matching CSS selector."""
        self._check_url(url)
        await self._rate_limiter.acquire()

        if not self._started:
            await self.start()

        if not self._has_playwright:
            # httpx fallback can't do CSS selectors meaningfully
            page = await self.navigate(url)
            return page.text if not page.error else f"Error: {page.error}"

        page = await self._context.new_page()
        try:
            await page.goto(url, timeout=self.timeout_ms, wait_until="domcontentloaded")
            elements = await page.query_selector_all(selector)
            texts = []
            for el in elements:
                text = await el.inner_text()
                if text.strip():
                    texts.append(text.strip())
            return "\n".join(texts)[:_MAX_TEXT_LENGTH]
        except Exception as e:
            return f"Error extracting '{selector}' from {url}: {e}"
        finally:
            await page.close()

    async def click(self, url: str, selector: str) -> PageContent:
        """Navigate to URL, click an element, and return resulting page content."""
        self._check_url(url)
        await self._rate_limiter.acquire()

        if not self._started:
            await self.start()

        if not self._has_playwright:
            return PageContent(
                url=url, title="", text="", status=0, elapsed_ms=0,
                method="httpx", error="Click requires Playwright (not available)",
            )

        t0 = time.monotonic()
        page = await self._context.new_page()
        try:
            await page.goto(url, timeout=self.timeout_ms, wait_until="domcontentloaded")
            await page.click(selector, timeout=self.timeout_ms)
            # Wait for navigation or network idle after click
            await page.wait_for_load_state("domcontentloaded", timeout=self.timeout_ms)
            title = await page.title()
            text = await page.evaluate("""() => {
                const clone = document.cloneNode(true);
                clone.querySelectorAll('script, style, noscript, svg, img').forEach(el => el.remove());
                return clone.body ? clone.body.innerText : document.documentElement.innerText;
            }""")
            elapsed = (time.monotonic() - t0) * 1000
            return PageContent(
                url=page.url, title=title, text=(text or "")[:_MAX_TEXT_LENGTH],
                status=200, elapsed_ms=elapsed, method="playwright",
            )
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            return PageContent(
                url=url, title="", text="", status=0, elapsed_ms=elapsed,
                method="playwright", error=str(e),
            )
        finally:
            await page.close()

    async def type_text(self, url: str, selector: str, text: str) -> PageContent:
        """Navigate to URL, type text into an input element."""
        self._check_url(url)
        await self._rate_limiter.acquire()

        if not self._started:
            await self.start()

        if not self._has_playwright:
            return PageContent(
                url=url, title="", text="", status=0, elapsed_ms=0,
                method="httpx", error="Type requires Playwright (not available)",
            )

        t0 = time.monotonic()
        page = await self._context.new_page()
        try:
            await page.goto(url, timeout=self.timeout_ms, wait_until="domcontentloaded")
            await page.fill(selector, text, timeout=self.timeout_ms)
            title = await page.title()
            page_text = await page.evaluate("""() => {
                const clone = document.cloneNode(true);
                clone.querySelectorAll('script, style, noscript, svg, img').forEach(el => el.remove());
                return clone.body ? clone.body.innerText : document.documentElement.innerText;
            }""")
            elapsed = (time.monotonic() - t0) * 1000
            return PageContent(
                url=page.url, title=title, text=(page_text or "")[:_MAX_TEXT_LENGTH],
                status=200, elapsed_ms=elapsed, method="playwright",
            )
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            return PageContent(
                url=url, title="", text="", status=0, elapsed_ms=elapsed,
                method="playwright", error=str(e),
            )
        finally:
            await page.close()

    async def screenshot(self, url: str, full_page: bool = False) -> ScreenshotResult:
        """Navigate to URL and take a screenshot."""
        self._check_url(url)
        await self._rate_limiter.acquire()

        if not self._started:
            await self.start()

        if not self._has_playwright:
            return ScreenshotResult(
                url=url, png_bytes=b"", width=0, height=0, elapsed_ms=0,
                error="Screenshot requires Playwright (not available)",
            )

        t0 = time.monotonic()
        page = await self._context.new_page()
        try:
            await page.goto(url, timeout=self.timeout_ms, wait_until="domcontentloaded")
            png = await page.screenshot(full_page=full_page, type="png")
            viewport = page.viewport_size or {"width": 1280, "height": 720}
            elapsed = (time.monotonic() - t0) * 1000
            if len(png) > _MAX_SCREENSHOT_BYTES:
                return ScreenshotResult(
                    url=url, png_bytes=b"", width=viewport["width"],
                    height=viewport["height"], elapsed_ms=elapsed,
                    error=f"Screenshot too large: {len(png)} bytes (max {_MAX_SCREENSHOT_BYTES})",
                )
            return ScreenshotResult(
                url=url, png_bytes=png, width=viewport["width"],
                height=viewport["height"], elapsed_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            return ScreenshotResult(
                url=url, png_bytes=b"", width=0, height=0,
                elapsed_ms=elapsed, error=str(e),
            )
        finally:
            await page.close()

    async def search(
        self, query: str, engine: str = "duckduckgo", max_results: int = 10,
    ) -> list[SearchResult]:
        """Perform a web search and return structured results.

        Uses DuckDuckGo HTML (no API key needed). Falls back to httpx parsing.
        """
        if engine == "duckduckgo":
            return await self._search_duckduckgo(query, max_results)
        raise ValueError(f"Unsupported search engine: {engine}")

    async def _search_duckduckgo(self, query: str, max_results: int) -> list[SearchResult]:
        """Search DuckDuckGo HTML version (no JS required)."""
        import httpx
        from urllib.parse import quote_plus, unquote

        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        await self._rate_limiter.acquire()

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=self.timeout_ms / 1000,
                headers={"User-Agent": self._user_agent},
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()

            results = []
            # Parse DDG HTML results - they use class="result__a" for links
            # and class="result__snippet" for descriptions
            html = resp.text

            # Extract result blocks
            link_pattern = re.compile(
                r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
                re.DOTALL,
            )
            snippet_pattern = re.compile(
                r'class="result__snippet"[^>]*>(.*?)</(?:a|td|div|span)',
                re.DOTALL,
            )

            links = link_pattern.findall(html)
            snippets = snippet_pattern.findall(html)

            for i, (href, title_html) in enumerate(links[:max_results]):
                title = _strip_html(title_html).strip()
                snippet = _strip_html(snippets[i]).strip() if i < len(snippets) else ""
                # DDG wraps URLs in a redirect; extract the real URL
                if "uddg=" in href:
                    real_url = unquote(href.split("uddg=")[-1].split("&")[0])
                else:
                    real_url = href
                if title and real_url:
                    results.append(SearchResult(title=title, url=real_url, snippet=snippet))

            return results

        except Exception as e:
            logger.error("DuckDuckGo search failed: %s", e)
            return []

    # ── Session / Cookie management ────────────────────────────────────

    async def get_cookies(self) -> list[dict]:
        """Return cookies from the current browser context."""
        if not self._has_playwright or not self._context:
            return []
        return await self._context.cookies()

    async def set_cookies(self, cookies: list[dict]) -> None:
        """Set cookies on the current browser context."""
        if self._has_playwright and self._context:
            await self._context.add_cookies(cookies)

    async def clear_cookies(self) -> None:
        """Clear all cookies from the current browser context."""
        if self._has_playwright and self._context:
            await self._context.clear_cookies()


# ── Utility functions ──────────────────────────────────────────────────

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def _strip_html(html: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = _TAG_RE.sub(" ", html)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def _extract_title(html: str) -> str:
    """Extract <title> content from HTML."""
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


# ── Tool Registry Integration ─────────────────────────────────────────

def _check_browser_available() -> bool:
    """Check if browser automation is available."""
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _register_browser_tools() -> None:
    """Register browser tools with the dharma_swarm tool registry."""
    try:
        from dharma_swarm.tool_registry import registry
    except ImportError:
        return

    _toolset = "browser"

    async def _handle_navigate(args: dict, **kw: Any) -> str:
        import json as _json
        url = args.get("url", "")
        async with BrowserAgent(headless=True) as ba:
            result = await ba.navigate(url)
            return _json.dumps(result.to_dict(), indent=2)

    async def _handle_extract(args: dict, **kw: Any) -> str:
        import json as _json
        url = args.get("url", "")
        selector = args.get("selector", "body")
        async with BrowserAgent(headless=True) as ba:
            text = await ba.extract(url, selector)
            return _json.dumps({"url": url, "selector": selector, "text": text[:_MAX_TEXT_LENGTH]})

    async def _handle_screenshot(args: dict, **kw: Any) -> str:
        import json as _json
        import base64
        url = args.get("url", "")
        async with BrowserAgent(headless=True) as ba:
            result = await ba.screenshot(url)
            if result.error:
                return _json.dumps({"error": result.error})
            return _json.dumps({
                "url": result.url,
                "width": result.width,
                "height": result.height,
                "png_base64": base64.b64encode(result.png_bytes).decode(),
                "elapsed_ms": round(result.elapsed_ms, 1),
            })

    async def _handle_search(args: dict, **kw: Any) -> str:
        import json as _json
        query = args.get("query", "")
        max_results = args.get("max_results", 10)
        async with BrowserAgent(headless=True) as ba:
            results = await ba.search(query, max_results=max_results)
            return _json.dumps([r.to_dict() for r in results], indent=2)

    registry.register(
        name="browser_navigate",
        toolset=_toolset,
        schema={
            "name": "browser_navigate",
            "description": "Navigate to a URL and return the page text content",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to navigate to"},
                },
                "required": ["url"],
            },
        },
        handler=_handle_navigate,
        check_fn=_check_browser_available,
        is_async=True,
        description="Navigate to a URL and return page text content",
    )

    registry.register(
        name="browser_extract",
        toolset=_toolset,
        schema={
            "name": "browser_extract",
            "description": "Extract text from a page using a CSS selector",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to navigate to"},
                    "selector": {"type": "string", "description": "CSS selector"},
                },
                "required": ["url", "selector"],
            },
        },
        handler=_handle_extract,
        check_fn=_check_browser_available,
        is_async=True,
        description="Extract text from a page using CSS selector",
    )

    registry.register(
        name="browser_screenshot",
        toolset=_toolset,
        schema={
            "name": "browser_screenshot",
            "description": "Take a screenshot of a web page (returns base64 PNG)",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to screenshot"},
                },
                "required": ["url"],
            },
        },
        handler=_handle_screenshot,
        check_fn=_check_browser_available,
        is_async=True,
        description="Take a screenshot of a web page",
    )

    registry.register(
        name="browser_search",
        toolset=_toolset,
        schema={
            "name": "browser_search",
            "description": "Search the web and return structured results",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "default": 10, "description": "Max results"},
                },
                "required": ["query"],
            },
        },
        handler=_handle_search,
        check_fn=_check_browser_available,
        is_async=True,
        description="Search the web via DuckDuckGo",
    )

    logger.debug("Registered 4 browser tools in toolset '%s'", _toolset)


# Auto-register on import
_register_browser_tools()
