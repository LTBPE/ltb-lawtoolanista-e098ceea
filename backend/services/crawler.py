"""
Page crawler using HTTPX (primary) with Playwright fallback for JS-heavy sites.
"""

import asyncio
import logging
import time

import httpx
from shared.config import config

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (compatible; CourtMonitor/1.0; +https://lawtoolbox.com)"
)

# Minimum extracted content length to consider HTTPX fetch adequate
_MIN_CONTENT_LENGTH = 500


class CrawlError(Exception):
    """Raised when a page cannot be fetched."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


async def fetch_page(
    url: str,
    js_required: bool = False,
    css_selector: str | None = None,
) -> tuple[str, int]:
    """
    Fetch a web page and return (html_content, response_time_ms).

    Tries HTTPX first unless js_required=True.  Falls back to Playwright if
    HTTPX returns too little content (< _MIN_CONTENT_LENGTH chars).

    Args:
        url: The URL to fetch.
        js_required: Force Playwright regardless of HTTPX result.
        css_selector: Optional CSS selector; if provided, return only that
                      element's innerHTML (Playwright only).

    Returns:
        Tuple of (html_string, response_time_ms).

    Raises:
        CrawlError: On network error, timeout, or bad status code.
    """
    await asyncio.sleep(config.CRAWL_DELAY_SECONDS)

    if not js_required:
        try:
            html, elapsed = await _fetch_with_httpx(url)
            # Check if we got meaningful content
            from services import content_extractor
            extracted = content_extractor.extract_and_clean(html, url)
            if len(extracted) >= _MIN_CONTENT_LENGTH:
                logger.debug("HTTPX fetch succeeded for %s (%dms)", url, elapsed)
                return html, elapsed
            logger.debug(
                "HTTPX returned short content (%d chars) for %s, trying Playwright",
                len(extracted),
                url,
            )
        except CrawlError:
            if not js_required:
                raise
            # If js_required will be tried anyway, continue to Playwright

    return await _fetch_with_playwright(url, css_selector)


async def _fetch_with_httpx(url: str) -> tuple[str, int]:
    """Fetch using HTTPX. Returns (html, elapsed_ms). Raises CrawlError on failure."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    timeout = httpx.Timeout(config.CRAWL_TIMEOUT_SECONDS)
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout,
            headers=headers,
        ) as client:
            response = await client.get(url)
            elapsed_ms = int((time.monotonic() - start) * 1000)

            if response.status_code == 404:
                raise CrawlError(
                    f"HTTP 404 for {url}", status_code=404
                )
            if response.status_code >= 400:
                raise CrawlError(
                    f"HTTP {response.status_code} for {url}",
                    status_code=response.status_code,
                )

            return response.text, elapsed_ms

    except httpx.TimeoutException as exc:
        raise CrawlError(f"Timeout fetching {url}: {exc}") from exc
    except httpx.RequestError as exc:
        raise CrawlError(f"Request error fetching {url}: {exc}") from exc


def _ensure_playwright_browsers() -> None:
    """Install Chromium to PLAYWRIGHT_BROWSERS_PATH if not already present."""
    import os
    import subprocess
    browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/tmp/playwright-browsers")
    marker = os.path.join(browsers_path, ".installed")
    if not os.path.exists(marker):
        logger.info("Installing Playwright Chromium to %s (first use)", browsers_path)
        os.makedirs(browsers_path, exist_ok=True)
        subprocess.run(["playwright", "install", "chromium"], check=True, capture_output=True)
        open(marker, "w").close()
        logger.info("Playwright Chromium ready.")


async def _fetch_with_playwright(
    url: str,
    css_selector: str | None = None,
) -> tuple[str, int]:
    """Fetch using Playwright (headless Chromium). Returns (html, elapsed_ms)."""
    try:
        from playwright.async_api import TimeoutError as PWTimeout
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise CrawlError(
            "Playwright is not installed. Run: playwright install chromium"
        ) from exc

    _ensure_playwright_browsers()

    start = time.monotonic()
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent=USER_AGENT,
                    java_script_enabled=True,
                )
                page = await context.new_page()
                await page.goto(
                    url,
                    wait_until="networkidle",
                    timeout=config.CRAWL_TIMEOUT_SECONDS * 1000,
                )

                if css_selector:
                    element = await page.query_selector(css_selector)
                    if element:
                        html = await element.inner_html()
                    else:
                        logger.warning(
                            "CSS selector %r not found on %s; returning full page",
                            css_selector,
                            url,
                        )
                        html = await page.content()
                else:
                    html = await page.content()

                elapsed_ms = int((time.monotonic() - start) * 1000)
                return html, elapsed_ms

            finally:
                await browser.close()

    except PWTimeout as exc:
        raise CrawlError(f"Playwright timeout for {url}: {exc}") from exc
    except Exception as exc:
        raise CrawlError(f"Playwright error for {url}: {exc}") from exc
