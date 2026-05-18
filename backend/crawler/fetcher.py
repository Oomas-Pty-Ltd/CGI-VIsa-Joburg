"""HTTP fetcher with Playwright primary + httpx fallback.

One Fetcher instance per crawl run. Owns its own httpx client and (if
enabled) a Playwright browser. Enforces:
  - per-host politeness delay (cfg.fetch_delay_ms)
  - per-fetch timeout (cfg.fetch_timeout_seconds)
  - simple retry once on 5xx / network error
  - robots.txt allow check via RobotsCache

JavaScript-rendered sites need Playwright; static sites should set
cfg.use_playwright=False for ~10x lower memory.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import httpx

from .robots import RobotsCache

logger = logging.getLogger("crawler.fetcher")

# Allow Playwright import to fail without breaking imports of this module.
try:
    from playwright.async_api import async_playwright   # type: ignore
    _PLAYWRIGHT_IMPORT_OK = True
except Exception:
    async_playwright = None   # type: ignore
    _PLAYWRIGHT_IMPORT_OK = False


@dataclass
class FetchResult:
    url: str                      # the URL requested
    final_url: str                # post-redirect
    html: Optional[str]           # response body if 2xx and content-type is HTML
    http_status: Optional[int]
    error: Optional[str]
    elapsed_ms: int

    @property
    def ok(self) -> bool:
        return self.html is not None and (self.http_status or 0) < 400


class Fetcher:
    def __init__(
        self,
        user_agent: str,
        timeout_seconds: int,
        fetch_delay_ms: int,
        use_playwright: bool,
        robots: RobotsCache,
        respect_robots: bool = True,
    ) -> None:
        self._user_agent = user_agent
        self._timeout_seconds = timeout_seconds
        self._fetch_delay_seconds = max(fetch_delay_ms, 0) / 1000.0
        self._use_playwright = use_playwright and _PLAYWRIGHT_IMPORT_OK
        self._robots = robots
        self._respect_robots = respect_robots

        self._http_client: Optional[httpx.AsyncClient] = None
        self._pw = None             # async_playwright context
        self._browser = None
        # host -> last fetch timestamp (monotonic) for politeness
        self._host_last_fetch: dict[str, float] = {}
        self._host_locks: dict[str, asyncio.Lock] = {}

        if use_playwright and not _PLAYWRIGHT_IMPORT_OK:
            logger.warning("use_playwright=True but Playwright import failed — falling back to httpx only")

    async def __aenter__(self) -> "Fetcher":
        # Browser-like headers — many WAFs (Cloudflare, ModSecurity) reject
        # requests that are missing Accept / Accept-Language, regardless of UA.
        self._http_client = httpx.AsyncClient(
            timeout=self._timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent":      self._user_agent,
                "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Cache-Control":   "no-cache",
                "Pragma":          "no-cache",
                "Sec-Fetch-Dest":  "document",
                "Sec-Fetch-Mode":  "navigate",
                "Sec-Fetch-Site":  "none",
                "Sec-Fetch-User":  "?1",
                "Upgrade-Insecure-Requests": "1",
            },
        )
        if self._use_playwright:
            try:
                self._pw = await async_playwright().start()
                self._browser = await self._pw.chromium.launch(headless=True)
                logger.info("Playwright browser launched")
            except Exception as exc:
                logger.warning("Playwright launch failed (%s) — falling back to httpx only", exc)
                self._use_playwright = False
                self._browser = None
                if self._pw:
                    try:
                        await self._pw.stop()
                    except Exception:
                        pass
                    self._pw = None
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._http_client:
            await self._http_client.aclose()
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass

    async def _wait_polite(self, host: str) -> None:
        """Sleep so we don't hammer one host. Per-host lock keeps concurrent
        workers from racing past the delay."""
        if self._fetch_delay_seconds <= 0:
            return
        lock = self._host_locks.setdefault(host, asyncio.Lock())
        async with lock:
            last = self._host_last_fetch.get(host)
            now = time.monotonic()
            if last is not None:
                wait = self._fetch_delay_seconds - (now - last)
                if wait > 0:
                    await asyncio.sleep(wait)
            self._host_last_fetch[host] = time.monotonic()

    async def fetch(self, url: str) -> FetchResult:
        """Fetch one URL. Returns FetchResult with .ok set based on outcome.

        Caller decides what to do with non-ok results (failed vs skipped).
        """
        started = time.monotonic()

        if self._respect_robots and not await self._robots.is_allowed(url):
            return FetchResult(
                url=url, final_url=url, html=None,
                http_status=None, error="robots_disallow",
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )

        host = urlparse(url).netloc
        await self._wait_polite(host)

        # Try Playwright first (if available and enabled); httpx as fallback.
        if self._use_playwright and self._browser is not None:
            result = await self._fetch_playwright(url)
            if result.ok or result.error == "robots_disallow":
                result.elapsed_ms = int((time.monotonic() - started) * 1000)
                return result
            # Fall through to httpx on Playwright failure.
            logger.info("Playwright failed for %s (status=%s error=%s) — trying httpx",
                        url, result.http_status, result.error)

        result = await self._fetch_httpx(url)
        result.elapsed_ms = int((time.monotonic() - started) * 1000)
        return result

    async def _fetch_httpx(self, url: str) -> FetchResult:
        assert self._http_client is not None
        for attempt in (1, 2):
            try:
                resp = await self._http_client.get(url)
            except httpx.TimeoutException:
                if attempt == 2:
                    return FetchResult(url, url, None, None, "timeout", 0)
                await asyncio.sleep(1.0)
                continue
            except Exception as exc:
                if attempt == 2:
                    return FetchResult(url, url, None, None, f"network:{exc}", 0)
                await asyncio.sleep(1.0)
                continue

            final_url = str(resp.url)
            ctype = resp.headers.get("content-type", "").lower()

            if resp.status_code >= 500 and attempt == 1:
                await asyncio.sleep(1.0)
                continue

            if resp.status_code >= 400:
                return FetchResult(url, final_url, None, resp.status_code,
                                   f"http_{resp.status_code}", 0)

            if "html" not in ctype:
                return FetchResult(url, final_url, None, resp.status_code,
                                   f"non_html:{ctype.split(';')[0]}", 0)

            return FetchResult(url, final_url, resp.text, resp.status_code, None, 0)

        # Unreachable but keeps type checkers happy.
        return FetchResult(url, url, None, None, "exhausted_retries", 0)

    async def _fetch_playwright(self, url: str) -> FetchResult:
        assert self._browser is not None
        context = None
        page = None
        try:
            context = await self._browser.new_context(user_agent=self._user_agent)
            page = await context.new_page()
            response = await page.goto(
                url,
                timeout=self._timeout_seconds * 1000,
                wait_until="domcontentloaded",
            )
            status = response.status if response else None
            final_url = page.url

            if status is None:
                return FetchResult(url, final_url, None, None, "playwright_no_response", 0)
            if status >= 400:
                return FetchResult(url, final_url, None, status, f"http_{status}", 0)

            html = await page.content()
            return FetchResult(url, final_url, html, status, None, 0)
        except Exception as exc:
            return FetchResult(url, url, None, None, f"playwright:{exc.__class__.__name__}", 0)
        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass
            if context:
                try:
                    await context.close()
                except Exception:
                    pass
