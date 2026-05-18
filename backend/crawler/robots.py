"""robots.txt + sitemap.xml discovery.

Per-host cache populated lazily. Uses stdlib `urllib.robotparser` for the
allow/deny rules (fed bytes we fetch ourselves via httpx — robotparser's
sync `read()` would block the event loop).

Sitemap discovery: every robots.txt's `Sitemap:` directives, plus the
conventional `/sitemap.xml` fallback. Handles sitemap-index files (lists
of sitemaps) one level deep.
"""
from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree as ET

import httpx

logger = logging.getLogger("crawler.robots")

SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


class RobotsCache:
    """One instance per crawl run. Owns its own httpx client."""

    def __init__(self, user_agent: str, timeout_seconds: int = 15) -> None:
        self._user_agent = user_agent
        self._client = httpx.AsyncClient(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": user_agent},
        )
        # host -> RobotFileParser | None (None = robots.txt unreachable; allow all)
        self._parsers: dict[str, Optional[RobotFileParser]] = {}
        # host -> list[str] of sitemap URLs declared in robots.txt
        self._declared_sitemaps: dict[str, list[str]] = {}

    async def close(self) -> None:
        await self._client.aclose()

    async def _load(self, host_url: str) -> None:
        """Fetch robots.txt for the host of `host_url` and populate cache."""
        parsed = urlparse(host_url)
        host = parsed.netloc
        if host in self._parsers:
            return

        robots_url = f"{parsed.scheme}://{host}/robots.txt"
        try:
            resp = await self._client.get(robots_url)
        except Exception as exc:
            logger.warning("robots.txt unreachable for %s: %s", host, exc)
            self._parsers[host] = None
            self._declared_sitemaps[host] = []
            return

        if resp.status_code >= 400:
            # No robots.txt = allow all (per RFC 9309).
            self._parsers[host] = None
            self._declared_sitemaps[host] = []
            return

        rp = RobotFileParser()
        try:
            rp.parse(resp.text.splitlines())
        except Exception as exc:
            logger.warning("Failed to parse robots.txt for %s: %s", host, exc)
            self._parsers[host] = None
            self._declared_sitemaps[host] = []
            return

        self._parsers[host] = rp
        # Sitemap directives — RobotFileParser exposes them via .site_maps()
        try:
            sitemaps = rp.site_maps() or []
        except Exception:
            sitemaps = []
        self._declared_sitemaps[host] = list(sitemaps)
        logger.info("Loaded robots.txt for %s (sitemaps=%d)", host, len(sitemaps))

    async def is_allowed(self, url: str) -> bool:
        await self._load(url)
        host = urlparse(url).netloc
        rp = self._parsers.get(host)
        if rp is None:
            return True
        try:
            return rp.can_fetch(self._user_agent, url)
        except Exception:
            return True

    async def sitemap_urls(self, seed_url: str) -> list[str]:
        """Return all URLs found in sitemap(s) for the seed's host.

        Walks one level of sitemap-index files. Returns a deduplicated list,
        capped at 10000 entries to keep memory bounded.
        """
        await self._load(seed_url)
        parsed = urlparse(seed_url)
        host = parsed.netloc
        sitemap_urls = list(self._declared_sitemaps.get(host) or [])
        # Conventional fallback if robots.txt didn't declare one.
        if not sitemap_urls:
            sitemap_urls = [f"{parsed.scheme}://{host}/sitemap.xml"]

        discovered: set[str] = set()
        for sm_url in sitemap_urls:
            await self._collect_from_sitemap(sm_url, discovered, depth=0)
            if len(discovered) >= 10000:
                break
        return list(discovered)[:10000]

    async def _collect_from_sitemap(self, sm_url: str, out: set[str], depth: int) -> None:
        if depth > 1:
            return   # Don't recurse beyond one level of sitemap-index.
        try:
            resp = await self._client.get(sm_url)
            if resp.status_code >= 400:
                return
            root = ET.fromstring(resp.content)
        except Exception as exc:
            logger.debug("Sitemap fetch/parse failed for %s: %s", sm_url, exc)
            return

        tag = root.tag.lower()
        # <sitemapindex> -> list of <sitemap><loc>...</loc></sitemap>
        if tag.endswith("sitemapindex"):
            for child in root.findall(f"{SITEMAP_NS}sitemap"):
                loc = child.find(f"{SITEMAP_NS}loc")
                if loc is not None and loc.text:
                    await self._collect_from_sitemap(loc.text.strip(), out, depth + 1)
                    if len(out) >= 10000:
                        return
            return

        # <urlset> -> list of <url><loc>...</loc></url>
        for child in root.findall(f"{SITEMAP_NS}url"):
            loc = child.find(f"{SITEMAP_NS}loc")
            if loc is not None and loc.text:
                out.add(loc.text.strip())
                if len(out) >= 10000:
                    return
