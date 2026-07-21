import httpx
from bs4 import BeautifulSoup
import json
import logging
import re
import sys
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse
import asyncio
from datetime import datetime, timezone, timedelta
import hashlib
import os

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# FETCH LAYER CONTROL
# ─────────────────────────────────────────────────────────────────────────────

# On Windows, asyncio uses ProactorEventLoop which cannot spawn subprocesses
# inside an already-running loop — Playwright always fails with NotImplementedError.
# Set the flag to False immediately so the probe is skipped entirely and no
# "Task exception was never retrieved" noise appears in the logs.
_playwright_available: Optional[bool] = False if sys.platform == "win32" else None

# ── Failed URL store ──────────────────────────────────────────────────────────
# Tracks URLs that failed permanently so we never retry within the cooldown.
# Schema: {url: {"reason": str, "failed_at": datetime, "attempts": int}}
_FAILED_URL_COOLDOWN_HOURS = 6   # don't retry a failed URL for 6 hours
_FAILED_URL_MAX_ATTEMPTS   = 3   # mark permanent after 3 consecutive failures

_failed_urls: Dict[str, Dict] = {}

# ── Scan frequency limiter ────────────────────────────────────────────────────
# Prevents hammering the same URL more than once per interval.
# Schema: {url: datetime_of_last_fetch}
_last_fetched: Dict[str, datetime] = {}
_MIN_FETCH_INTERVAL_SECONDS = 300   # 5 minutes between fetches of the same URL


def _is_url_blocked(url: str) -> Optional[str]:
    """
    Return a reason string if the URL should NOT be fetched right now, else None.
    Checks: failed-URL cooldown, scan frequency limit.
    """
    now = datetime.now(timezone.utc)

    # Failed URL cooldown
    fail_entry = _failed_urls.get(url)
    if fail_entry:
        age_hours = (now - fail_entry["failed_at"]).total_seconds() / 3600
        if age_hours < _FAILED_URL_COOLDOWN_HOURS:
            return f"blocked (failed {fail_entry['attempts']}x: {fail_entry['reason']})"

    # Frequency limit
    last = _last_fetched.get(url)
    if last:
        elapsed = (now - last).total_seconds()
        if elapsed < _MIN_FETCH_INTERVAL_SECONDS:
            return f"rate-limited (fetched {int(elapsed)}s ago)"

    return None


def _record_fetch_success(url: str):
    """Mark a successful fetch — resets failure count, updates last-fetched."""
    _last_fetched[url] = datetime.now(timezone.utc)
    _failed_urls.pop(url, None)   # clear any prior failure record


def _record_fetch_failure(url: str, reason: str):
    """Increment failure counter; mark URL as blocked when max attempts reached."""
    entry = _failed_urls.get(url, {"attempts": 0, "reason": "", "failed_at": datetime.now(timezone.utc)})
    entry["attempts"] += 1
    entry["reason"]    = reason
    entry["failed_at"] = datetime.now(timezone.utc)
    _failed_urls[url]  = entry
    if entry["attempts"] >= _FAILED_URL_MAX_ATTEMPTS:
        logger.warning(f"[FETCH] URL marked as failed after {entry['attempts']} attempts: {url} — {reason}")


def get_failed_urls() -> Dict[str, Dict]:
    """Public accessor for monitoring / admin dashboard."""
    return {
        url: {**info, "failed_at": info["failed_at"].isoformat()}
        for url, info in _failed_urls.items()
    }


# ─────────────────────────────────────────────────────────────────────────────
# PLAYWRIGHT FETCH  (default — handles JS-rendered pages)
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_with_playwright(url: str) -> str:
    """
    Fetch a URL using Playwright/Chromium headless browser.
    Waits for network idle so JS-rendered content is fully loaded.
    Returns full HTML string.
    """
    global _playwright_available
    from playwright.async_api import async_playwright, TimeoutError as PWTimeout
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-extensions",
                    "--disable-background-networking",
                ],
            )
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                ignore_https_errors=True,
                java_script_enabled=True,
            )
            page = await context.new_page()
            # Block images/fonts/media to speed up load
            await page.route(
                "**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf,mp4,webp}",
                lambda route: route.abort()
            )
            await page.goto(url, wait_until="domcontentloaded", timeout=12000)
            html = await page.content()
            await browser.close()
            _playwright_available = True
            return html
    except ImportError:
        _playwright_available = False
        raise
    except PWTimeout:
        raise Exception(f"Playwright timeout on {url}")


# ─────────────────────────────────────────────────────────────────────────────
# HTTPX FETCH  (fallback — fast, no JS rendering)
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_with_httpx(url: str) -> str:
    """Fetch a URL with httpx (no JS rendering). Fast fallback."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, verify=False) as client:
        response = await client.get(url, headers=headers)
        if response.status_code == 200:
            return response.text
        if response.status_code == 404:
            raise Exception(f"HTTP 404 (permanent)")
        if response.status_code == 403:
            raise Exception(f"HTTP 403 — WAF blocked")
        raise Exception(f"HTTP {response.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# UNIFIED FETCH  (Playwright → httpx fallback, with rate-limit + failure guard)
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_with_retry(url: str, retries: int = 1) -> str:
    """
    Fetch a URL using the best available method:
      1. Check rate-limit and failed-URL store — skip if blocked.
      2. Try Playwright (JS-rendered, full DOM).
      3. On Playwright failure → fall back to httpx.
      4. Track failures; give up after _FAILED_URL_MAX_ATTEMPTS.
    Returns HTML string. Raises on unrecoverable failure.
    """
    global _playwright_available

    # Guard: don't fetch if URL is rate-limited or in cooldown
    block_reason = _is_url_blocked(url)
    if block_reason:
        raise Exception(f"Fetch skipped — {block_reason}: {url}")

    last_error: Exception = Exception("no attempts made")

    for attempt in range(retries):
        try:
            # ── Try Playwright first (unless we know it's unavailable) ──
            if _playwright_available is not False:
                try:
                    html = await _fetch_with_playwright(url)
                    _record_fetch_success(url)
                    logger.debug(f"[FETCH] Playwright OK: {url}")
                    return html
                except (ImportError, NotImplementedError):
                    _playwright_available = False
                    logger.info("[FETCH] Playwright unavailable on this platform — switching to httpx permanently")
                except Exception as pw_err:
                    # Empty error string usually means NotImplementedError from internal asyncio task
                    if not str(pw_err):
                        _playwright_available = False
                        logger.info("[FETCH] Playwright subprocess failed — switching to httpx permanently")
                    else:
                        logger.info(f"[FETCH] Playwright failed ({pw_err}) — trying httpx: {url}")
                    # Fall through to httpx below

            # ── Fallback: httpx ──────────────────────────────────────────
            html = await _fetch_with_httpx(url)
            _record_fetch_success(url)
            logger.debug(f"[FETCH] httpx OK: {url}")
            return html

        except Exception as e:
            last_error = e
            reason = str(e)
            is_permanent = "(permanent)" in reason or "HTTP 403" in reason or "HTTP 404" in reason
            if is_permanent or attempt >= retries - 1:
                _record_fetch_failure(url, reason)
                raise
            await asyncio.sleep(1.5 * (attempt + 1))

    _record_fetch_failure(url, str(last_error))
    raise last_error

# Scrape sources are tenant-driven via bot_config.knowledge_sources — read
# per-tenant via ``_load_scrape_sources()`` below.
EXCEPTION_EMAIL = os.environ.get("EXCEPTION_EMAIL", "")


async def _load_scrape_sources(company_id: Optional[str] = None) -> Dict[str, Any]:
    """Return the scrape configuration for ``company_id`` from bot_config.

    Expected shape on ``tenant_bot_config.knowledge_sources``::

        {
          "primary_url":     "https://example.gov.in/",
          "sub_pages":       ["https://example.gov.in/page/...", ...],
          "secondary_urls":  ["https://partner.example.com/", ...]
        }

    All keys optional. Missing keys yield empty lists so the scrape is a
    no-op for a tenant that hasn't configured sources yet.
    """
    if not company_id:
        return {"primary_url": "", "sub_pages": [], "secondary_urls": []}
    try:
        from services.bot_config import get_bot_config
        cfg = await get_bot_config(company_id)
        ks = (cfg.raw or {}).get("knowledge_sources") or {}
        return {
            "primary_url":    ks.get("primary_url") or "",
            "sub_pages":      list(ks.get("sub_pages") or []),
            "secondary_urls": list(ks.get("secondary_urls") or []),
        }
    except Exception as exc:
        logger.debug("[_load_scrape_sources] %s: %s", company_id, exc)
        return {"primary_url": "", "sub_pages": [], "secondary_urls": []}


def _clean_html_text(html: str) -> List[str]:
    """
    Parse HTML and extract only meaningful text lines.
    Removes script/style/nav/footer noise and avoids nested-element duplication
    by only extracting leaf-level content nodes.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove noise elements entirely
    for tag in soup.find_all(["script", "style", "noscript", "nav", "footer",
                               "header", "meta", "link", "iframe", "svg", "img"]):
        tag.decompose()

    # Extract text only from leaf-level meaningful elements
    # Avoid div/span which cause duplicate text with nested p/li
    leaf_tags = ["p", "li", "h1", "h2", "h3", "h4", "h5", "td", "th", "dt", "dd", "caption", "label"]
    texts = []
    seen = set()

    for el in soup.find_all(leaf_tags):
        text = el.get_text(separator=" ", strip=True)
        # Skip short/empty/duplicate
        if len(text) < 15 or text in seen:
            continue
        # Skip lines that are pure navigation/UI noise
        if re.match(r'^(home|menu|search|login|logout|back|next|previous|close|click here)$', text, re.IGNORECASE):
            continue
        seen.add(text)
        texts.append(text)

    return texts


def _extract_contact_details(soup: BeautifulSoup) -> Dict:
    """
    Extract contact details from scraped HTML using targeted selectors and regex.
    Returns only the fields that could be matched; callers can layer their
    own tenant defaults on top (bot_config.contact).
    """
    full_text = soup.get_text(separator=" ", strip=True)

    extracted = {}

    # Phone numbers — match +27 or 0 prefix SA numbers
    # Phone numbers — generic international format: optional "+" then 1-3
    # digits (country code), then more digits with optional spaces/dashes.
    # Replaces the previous "+27|0" SA-only pattern.
    phones = re.findall(r"\+?\d{1,3}[\s\-]?\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{3,4}", full_text)
    phones = [re.sub(r"\s+", " ", p).strip() for p in phones]
    if phones:
        extracted["emergency_contact"] = phones[0]

    # Email addresses
    emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", full_text)
    if emails:
        extracted["email"] = emails[0]

    # Address — generic Floor-prefix heuristic. Previously biased to
    # "johannesburg|joburg"; now matches any city name (or none) after the
    # floor anchor. Less precise but tenant-agnostic.
    addr_match = re.search(
        r"(?:\d+(?:st|nd|rd|th)?\s+[Ff]loor|[Ff]loor\s+\d+)[^.\n]{10,200}",
        full_text, re.IGNORECASE
    )
    if addr_match:
        extracted["address"] = re.sub(r"\s+", " ", addr_match.group()).strip()

    # Office hours — look for Mon–Fri / Monday–Friday patterns
    hours_match = re.search(
        r"(?:Mon(?:day)?|Monday)[\s\S]{0,80}?(?:\d{1,2}[:.]\d{2}[\s\S]{0,40}?\d{1,2}[:.]\d{2})",
        full_text, re.IGNORECASE
    )
    if hours_match:
        extracted["office_hours"] = re.sub(r"\s+", " ", hours_match.group()).strip()

    return extracted


async def _fetch_page_text(url: str) -> str:
    """
    Fetch a page and return clean extracted text.
    Returns empty string if the URL is blocked, rate-limited, or fails.
    """
    block_reason = _is_url_blocked(url)
    if block_reason:
        logger.debug(f"[FETCH] Skipping {url} — {block_reason}")
        return ""
    try:
        html = await _fetch_with_retry(url)
        lines = _clean_html_text(html)
        return "\n".join(lines[:150])
    except Exception as e:
        logger.warning(f"[FETCH] _fetch_page_text failed for {url}: {e}")
        return ""


async def scrape_cgi_joburg(company_id=None):
    """Scrape this tenant's *primary* knowledge source.

    URL list comes from ``bot_config.knowledge_sources`` (see
    ``_load_scrape_sources``). The dict key (``cgi_joburg``) is kept for
    back-compat with callers; the content is tenant-driven, not CGI-specific.
    """
    sources = await _load_scrape_sources(company_id)
    primary = sources.get("primary_url") or ""
    sub_pages = sources.get("sub_pages") or []
    if not primary and not sub_pages:
        return {
            "source": "primary (unconfigured)",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "status": "no_sources_configured",
            "pages_crawled": 0,
            "page_content": "",
        }
    try:
        all_urls = ([primary] if primary else []) + list(sub_pages)
        results = await asyncio.gather(
            *[_fetch_page_text(url) for url in all_urls],
            return_exceptions=True,
        )
        combined_parts = []
        contact_html = None
        pages_ok = 0
        for url, result in zip(all_urls, results):
            if isinstance(result, Exception) or not result:
                continue
            pages_ok += 1
            page_name = url.rstrip("/").split("/")[-1] or "home"
            combined_parts.append(f"[Page: {page_name}]\n{result}")
            if url == primary:
                contact_html = result
        live_contact = {}
        if contact_html:
            try:
                soup = BeautifulSoup(contact_html, "html.parser")
                live_contact = _extract_contact_details(soup) or {}
            except Exception:
                pass
        return {
            "source": primary or (sub_pages[0] if sub_pages else "primary"),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "status": "live_scraped" if pages_ok else "no_pages",
            "pages_crawled": pages_ok,
            "page_content": "\n\n".join(combined_parts),
            **live_contact,
        }
    except Exception as exc:
        await send_exception_email("Primary source scrape failed", str(exc))
        logger.warning("[SCRAPE] primary scrape failed: %s", exc)
        return {
            "source": primary or "primary",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "status": "failed",
            "pages_crawled": 0,
            "page_content": "",
        }


async def scrape_vfs_global(company_id=None):
    """Scrape this tenant's *secondary* knowledge sources (auxiliary URLs).

    URL list comes from ``bot_config.knowledge_sources.secondary_urls``. The
    dict key (``vfs_global``) is kept for back-compat; the content is
    tenant-driven, not VFS-specific.
    """
    sources = await _load_scrape_sources(company_id)
    urls = sources.get("secondary_urls") or []
    if not urls:
        return {
            "source": "secondary (unconfigured)",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "status": "no_sources_configured",
            "page_content": "",
        }
    page_content = ""
    live_contact = {}
    for url in urls:
        try:
            html = await _fetch_with_retry(url)
            lines = _clean_html_text(html)
            if len(lines) < 5:
                continue
            page_content = "\n".join(lines[:150])
            soup = BeautifulSoup(html, "html.parser")
            live_contact = _extract_contact_details(soup) or {}
            break
        except Exception:
            continue
    return {
        "source": urls[0],
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "status": "live_scraped" if page_content else "failed",
        "page_content": page_content,
        **live_contact,
    }


# Per-tenant cache slots: ``{company_id_or_empty: scraped_dict}``. The empty-
# string key is used by legacy callers that didn't pass a company_id.
_knowledge_cache: Dict[str, Dict] = {}
_knowledge_cache_time: Dict[str, datetime] = {}
_scrape_in_progress: bool = False
# Knowledge-base cache + tuning are now platform_config knobs. The
# constants below are kept as platform fallbacks; the resolvers next to
# each consumer read the live value at request time so admin tuning
# applies without a restart.
def _kb_cache_ttl_seconds() -> int:
    try:
        from services import platform_config
        return int(platform_config.get("kb_cache_ttl_seconds", 1800))
    except Exception:
        return 1800


def _kb_blocked_kw_ttl() -> int:
    try:
        from services import platform_config
        return int(platform_config.get("kb_blocked_kw_ttl_seconds", 60))
    except Exception:
        return 60


def _kb_deep_scan_ttl() -> int:
    try:
        from services import platform_config
        return int(platform_config.get("kb_deep_scan_ttl_seconds", 1800))
    except Exception:
        return 1800


def _kb_hit_threshold() -> int:
    try:
        from services import platform_config
        return int(platform_config.get("kb_hit_threshold", 3))
    except Exception:
        return 3


def _kb_max_deep_urls() -> int:
    try:
        from services import platform_config
        return int(platform_config.get("kb_max_deep_urls", 8))
    except Exception:
        return 8


def _kb_crawl_interval() -> int:
    try:
        from services import platform_config
        return int(platform_config.get("kb_crawl_interval_seconds", 6 * 3600))
    except Exception:
        return 6 * 3600


async def _probe_playwright() -> None:
    """
    One-shot check: can Playwright actually launch a browser on this platform?
    Sets _playwright_available to True/False before any concurrent fetch runs,
    preventing N duplicate failures (and noisy 'Task exception never retrieved'
    logs) when all fetches attempt Playwright simultaneously at startup.
    """
    global _playwright_available
    if _playwright_available is not None:
        return  # Already probed — skip
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            )
            await browser.close()
        _playwright_available = True
        logger.info("[FETCH] Playwright probe OK — using Playwright for JS-rendered pages")
    except Exception as e:
        _playwright_available = False
        logger.info(f"[FETCH] Playwright unavailable ({type(e).__name__}) — using httpx only")


BLOCKED_SENTINEL = "__BLOCKED__"


def filter_blocked_lines(text: str, blocked: set) -> str:
    """Remove every line that contains any blocked keyword (case-insensitive)."""
    if not blocked or not text:
        return text
    result = []
    for line in text.splitlines():
        line_lower = line.lower()
        if not any(bk in line_lower for bk in blocked):
            result.append(line)
    return "\n".join(result)


def blocked_prohibition(blocked: set) -> str:
    """Return an LLM instruction that forbids mentioning blocked topics."""
    if not blocked:
        return ""
    topics = ", ".join(sorted(blocked))
    return (
        f"\nSTRICT RESTRICTION — ADMINISTRATOR OVERRIDE: Do NOT mention, reference, "
        f"or provide any information about the following topics under any circumstances, "
        f"even if the user asks directly or the information appears elsewhere in this prompt: "
        f"{topics}. If the user asks about these topics, reply: "
        f"\"I'm sorry, I don't have information on that topic. Please contact support for assistance.\"\n"
    )

_blocked_kw_cache: Set[str] = set()
_blocked_kw_cache_time: Optional[datetime] = None


async def _get_blocked_keywords() -> Set[str]:
    """Return the current set of blocked keywords from MongoDB (lowercased), with in-memory cache."""
    global _blocked_kw_cache, _blocked_kw_cache_time
    now = datetime.now(timezone.utc)
    if _blocked_kw_cache_time is not None and (now - _blocked_kw_cache_time).total_seconds() < _kb_blocked_kw_ttl():
        return _blocked_kw_cache
    try:
        from database import get_database
        db = await get_database()
        docs = await db.blocked_keywords.find({}, {"_id": 0, "keyword": 1}).to_list(500)
        _blocked_kw_cache = {d["keyword"].lower() for d in docs if d.get("keyword")}
        _blocked_kw_cache_time = now
        return _blocked_kw_cache
    except Exception:
        return _blocked_kw_cache  # return stale cache on DB error


def _entry_matches_blocked(entry: dict, blocked: Set[str]) -> bool:
    """Return True if any blocked keyword appears in entry title, keywords, or answer."""
    if not blocked:
        return False
    title = (entry.get("title") or "").lower()
    answer = (entry.get("answer") or "").lower()
    kws = [k.lower() for k in (entry.get("keywords") or [])]
    for bk in blocked:
        if bk in title or bk in answer or any(bk in k for k in kws):
            return True
    return False


async def _fetch_uploaded_docs_content() -> str:
    """
    Fetch all active PDF-uploaded knowledge entries from MongoDB and
    concatenate their text so the scraper cache includes uploaded documents.
    Entries matching any blocked keyword are silently excluded.
    Returns empty string if DB is unavailable.
    """
    try:
        from database import get_database
        db = await get_database()
        blocked = await _get_blocked_keywords()
        cursor = db.knowledge_base.find(
            {"source": {"$regex": "^pdf_upload:"}, "status": "active"},
            {"_id": 0, "title": 1, "answer": 1, "pdf_doc_title": 1, "keywords": 1}
        ).sort("created_at", -1).limit(200)
        entries = await cursor.to_list(length=200)
        if not entries:
            return ""
        parts = []
        skipped = 0
        for e in entries:
            if _entry_matches_blocked(e, blocked):
                skipped += 1
                continue
            doc_title = e.get("pdf_doc_title") or e.get("title", "")
            answer = (e.get("answer") or "").strip()
            if answer:
                parts.append(f"[Uploaded: {doc_title}]\n{answer}")
        if skipped:
            logger.info(f"[SCRAPE] Skipped {skipped} blocked-keyword entries from uploaded docs")
        logger.info(f"[SCRAPE] Loaded {len(parts)} uploaded-doc sections into scraper cache")
        return "\n\n".join(parts)
    except Exception as exc:
        logger.warning(f"[SCRAPE] Could not load uploaded docs: {exc}")
        return ""


async def _do_scrape(company_id: Optional[str] = None) -> Dict:
    """Scrape this tenant's primary + secondary sources + uploaded docs.

    Cache key includes ``company_id`` (see ``_knowledge_cache``) so each
    tenant gets its own scrape pipeline.
    """
    await _probe_playwright()
    primary, secondary, uploaded_content = await asyncio.gather(
        scrape_cgi_joburg(company_id),
        scrape_vfs_global(company_id),
        _fetch_uploaded_docs_content(),
    )
    return {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        # Back-compat keys (no longer brand-specific): "cgi_joburg" = primary,
        # "vfs_global" = secondary. Callers that read these keys still work;
        # new callers should treat them as opaque source slots.
        "cgi_joburg": primary,
        "vfs_global": secondary,
        "uploaded_docs": {
            "source": "uploaded_documents",
            "page_content": uploaded_content,
        },
    }


async def _refresh_cache_background(company_id: Optional[str] = None):
    """Scrape in the background and update the per-tenant cache slot."""
    global _scrape_in_progress
    if _scrape_in_progress:
        return
    _scrape_in_progress = True
    try:
        data = await _do_scrape(company_id)
        await log_knowledge_changes(data)
        _knowledge_cache[company_id or ""] = data
        _knowledge_cache_time[company_id or ""] = datetime.now(timezone.utc)
    except Exception as e:
        await send_exception_email("Real-time Knowledge Fetch Failed", str(e))
    finally:
        _scrape_in_progress = False


async def get_realtime_knowledge(company_id: Optional[str] = None) -> Dict:
    """Always returns immediately — never blocks a chat request.

    ``company_id`` selects the tenant whose scrape sources are used (and
    whose cache slot is read). When omitted, falls back to an unscoped
    cache slot (legacy callers).
    """
    key = company_id or ""
    now = datetime.now(timezone.utc)
    cache_stale = (
        key not in _knowledge_cache
        or _knowledge_cache_time.get(key) is None
        or (now - _knowledge_cache_time[key]).total_seconds() >= _kb_cache_ttl_seconds()
    )

    if cache_stale and not _scrape_in_progress:
        asyncio.create_task(_refresh_cache_background(company_id))

    if key in _knowledge_cache:
        return _knowledge_cache[key]

    # Cold start — return a minimal envelope so hybrid_search has something
    # to operate on. No CGI-specific static content is shipped any more.
    return {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "source": "primary (unconfigured)",
        "status": "no_sources_configured",
        "cgi_joburg":   {"source": "", "status": "cold_start", "page_content": ""},
        "vfs_global":   {"source": "", "status": "cold_start", "page_content": ""},
        "uploaded_docs": {"source": "uploaded_documents", "page_content": ""},
    }


def invalidate_knowledge_cache(company_id: Optional[str] = None):
    """Force the next call to ``get_realtime_knowledge`` to refresh.

    Pass ``company_id`` to invalidate just one tenant; omit to clear all.
    """
    global _blocked_kw_cache_time
    if company_id is None:
        _knowledge_cache.clear()
        _knowledge_cache_time.clear()
    else:
        _knowledge_cache.pop(company_id, None)
        _knowledge_cache_time.pop(company_id, None)
    _blocked_kw_cache_time = None  # also clear blocked-keywords cache
    logger.info("[SCRAPE] Knowledge cache invalidated (company_id=%s)", company_id or "ALL")


_LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")


async def log_knowledge_changes(new_data: Dict):
    """Log changes in scraped data."""
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        log_file  = os.path.join(_LOG_DIR, "knowledge_changes.log")
        hash_file = os.path.join(_LOG_DIR, "last_knowledge_hash.txt")

        new_hash = hashlib.md5(json.dumps(new_data, sort_keys=True).encode()).hexdigest()

        previous_hash = None
        if os.path.exists(hash_file):
            with open(hash_file, "r") as f:
                previous_hash = f.read().strip()

        if previous_hash != new_hash:
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "previous_hash": previous_hash,
                "new_hash": new_hash,
                "change_detected": True,
            }
            with open(log_file, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
            with open(hash_file, "w") as f:
                f.write(new_hash)
    except Exception as e:
        logger.warning("Error logging knowledge changes: %s", e)


async def send_exception_email(subject: str, error_details: str):
    """Log exception to local file."""
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        log_file = os.path.join(_LOG_DIR, "exception_emails.log")
        with open(log_file, "a") as f:
            f.write(f"\n{'='*50}\n")
            f.write(f"TIMESTAMP: {datetime.now(timezone.utc).isoformat()}\n")
            f.write(f"SUBJECT: {subject}\n")
            f.write(f"DETAILS: {error_details}\n")
        logger.info("Exception logged: %s", subject)
    except Exception as e:
        logger.warning("Failed to log exception: %s", e)


def get_fallback_knowledge() -> Dict:
    """Minimal fallback envelope returned when live scraping fails.

    Previously contained a 250-line CGI Johannesburg-specific dict of
    services, fees, addresses, and contact info — that's all been moved
    to per-tenant configuration (bot_config + tenant_services + the
    Knowledge Base tab). Returns a generic shape so callers that read
    ``services`` / ``official_links`` keys don't crash.
    """
    return {
        "last_updated":    datetime.now(timezone.utc).isoformat(),
        "source":          "fallback (no scrape sources configured)",
        "services":        {},
        "official_links":  {},
    }

# Platform-default keyword sets used by KB content extraction + fallback
# search routing. The four generic buckets (``fees``, ``emergency_contact``,
# ``process_guide``, plus a passthrough for any tenant service) are used
# by ``extract_service_content`` and ``_fallback_for_keywords``. Tenant
# services contribute their own keywords automatically — see
# ``_tenant_kb_keywords`` below.
#
# The India-specific buckets (``noc``, ``nri``, ``tracing``, ``trade``,
# ``one_same``, ``non_impediment``, ``driving``) have been removed; they
# only made sense for the CGI Joburg use case. The CGI-specific brand
# tokens (``passportindia``, ``ociservices``, ``vfs``, ``tatkal``,
# ``brics``, ``dtaa``, ``kip programme``, ``fir``) have been stripped from
# the remaining buckets.
_DEFAULT_KB_SERVICE_KEYWORDS = {
    "visa":        ["visa", "e-visa", "evisa", "tourist visa", "business visa",
                    "visa fee", "visa fees", "visa cost", "visa application",
                    "visa process", "visa procedure", "apply visa"],
    "passport":    ["passport", "renewal", "fresh passport", "travel document",
                    "passport fee", "passport fees", "passport cost",
                    "lost passport", "stolen passport", "damaged passport",
                    "reissue", "re-issue", "police report",
                    "emergency travel", "emergency document",
                    "passport process", "apply passport"],
    "oci":         ["oci", "overseas citizen", "lifelong visa", "oci card",
                    "person of indian origin", "oci fee", "oci process"],
    "pcc":         ["pcc", "police clearance", "clearance certificate",
                    "criminal record", "character certificate", "pcc fee"],
    "marriage":    ["marriage", "matrimonial", "spouse", "wedding",
                    "marry", "marriage certificate", "marriage fee"],
    "birth":       ["birth", "born", "newborn", "child registration", "birth certificate"],
    "attestation": ["attestation", "apostille", "notary", "affidavit",
                    "power of attorney", "poa", "gpa", "general power of attorney",
                    "legalization", "legalisation"],
    "renunciation":["renunciation", "renounce", "surrender passport",
                    "citizenship", "give up citizenship"],
    # Generic topic-routers (currency-neutral, tenant-neutral)
    "fees":        ["fees", "fee", "cost", "price", "charges", "how much",
                    "payment", "rate", "amount", "tariff", "pricing",
                    "price list", "service charges", "fee schedule",
                    "fee structure", "what does it cost"],
    "emergency_contact": ["emergency", "distress", "stranded", "arrested",
                          "hospital", "accident", "urgent help", "crisis",
                          "helpline"],
    "process_guide": ["step by step", "walk me through", "entire process",
                      "from start to finish", "how do i start", "get started",
                      "guide me", "beginning to end", "full process",
                      "complete process", "walkthrough", "procedure",
                      "how to apply", "how to begin", "first step",
                      "next step", "use this bot", "how does this work",
                      "explain the process", "what are the steps"],
}

# Back-compat alias — existing call sites in this module + hybrid_retrieval
# + application_flow import ``_SERVICE_KEYWORDS``. Keep as alias so we
# don't have to chase every read site. Tenant-aware enrichment happens
# via ``_resolve_kb_service_keywords()`` (see below).
_SERVICE_KEYWORDS = _DEFAULT_KB_SERVICE_KEYWORDS


async def _resolve_kb_service_keywords(company_id: Optional[str]) -> Dict[str, list]:
    """Return service→keyword map enriched with this tenant's
    ``tenant_services[].keywords`` so KB extraction recognises the
    tenant's own services + still understands generic topics like
    ``fees`` and ``process_guide``.
    """
    out: Dict[str, list] = {k: list(v) for k, v in _DEFAULT_KB_SERVICE_KEYWORDS.items()}
    if not company_id:
        return out
    try:
        from services.service_registry import list_services
        services = await list_services(company_id)
        for s in services:
            if not s.enabled:
                continue
            kws = [str(k).lower() for k in (s.raw.get("keywords") or []) if k]
            if s.service_key:
                kws.append(s.service_key.lower())
            if s.name:
                kws.append(s.name.lower())
            # Merge with the existing bucket if the tenant's key matches a
            # built-in topic (e.g. tenant has a "visa" service → enrich
            # the platform "visa" bucket); otherwise add a new bucket.
            existing = out.get(s.service_key, [])
            out[s.service_key] = sorted(set(existing + kws), key=len, reverse=True)
    except Exception as exc:
        logger.debug("[_resolve_kb_service_keywords] %s: %s", company_id, exc)
    return out

# ─────────────────────────────────────────────────────────────────────────────
# KEYWORD-DRIVEN SELECTIVE SCANNING
#
# Two-level lookup:
#   Level 1 (fast):  Check already-scraped content in the 30-min cache.
#                    If keyword hits ≥ HIT_THRESHOLD → return immediately.
#   Level 2 (deep):  Keyword NOT found (or sparse) in cache →
#                    Discover relevant sub-page links from homepage,
#                    crawl them concurrently, extract matching content,
#                    cache per-keyword result for 30 min.
#   Level 3 (fallback): Everything above failed → return structured
#                    fallback knowledge base data.
# ─────────────────────────────────────────────────────────────────────────────

_STOP_WORDS = {
    "what", "when", "where", "how", "can", "the", "a", "an", "is", "are",
    "my", "me", "you", "to", "for", "of", "in", "on", "at", "do", "does",
    "will", "would", "could", "should", "with", "from", "this", "that",
    "and", "or", "but", "not", "have", "has", "had", "been", "being", "i",
}

# Flow-control words that are never knowledge queries — skip deep scan entirely
_NO_CRAWL_WORDS = {
    "yes", "yep", "yeah", "nope", "okay", "sure",
    "apply", "start", "begin", "register", "proceed", "confirm",
    "cancel", "stop", "exit", "quit", "back", "next", "done",
    "hello", "hi", "hey", "thanks", "thank", "bye", "goodbye",
}


# Per-keyword deep-scan cache: {cache_key → {"content": str, "scanned_at": str}}
_deep_scan_cache: Dict[str, Dict] = {}


def _extract_keywords(query: str) -> List[str]:
    """Extract meaningful search keywords from a query string."""
    words = re.findall(r'\b[a-zA-Z]{3,}\b', query.lower())
    return [w for w in words if w not in _STOP_WORDS]


def _count_hits(keywords: List[str], content: str) -> int:
    """Count how many non-empty lines in content match at least one keyword."""
    if not content or not keywords:
        return 0
    return sum(
        1 for line in content.split("\n")
        if line.strip() and any(k in line.lower() for k in keywords)
    )


def _extract_matching_lines(keywords: List[str], content: str, max_lines: int = 25) -> List[str]:
    """Return lines from content that contain at least one keyword.

    Lines matching more keywords rank higher so compound queries like
    'lost passport' surface specific content before generic single-keyword lines.
    """
    if not content or not keywords:
        return []
    scored = []
    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        low = stripped.lower()
        count = sum(1 for k in keywords if k in low)
        if count > 0:
            scored.append((count, stripped))
    # Stable sort: higher match count first, original order preserved within same score
    scored.sort(key=lambda x: x[0], reverse=True)
    return [line for _, line in scored][:max_lines]


def _discover_relevant_links(homepage_html: str, base_url: str, keywords: List[str]) -> List[str]:
    """
    Parse homepage HTML for same-domain <a href> links whose URL path or
    anchor text contains at least one keyword. Returns up to
    ``platform_config.kb_max_deep_urls`` (default 8) URLs.
    """
    soup = BeautifulSoup(homepage_html, "html.parser")
    base_domain = urlparse(base_url).netloc
    found: List[str] = []
    seen: set = set()

    for tag in soup.find_all("a", href=True):
        href = tag.get("href", "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)

        if parsed.scheme not in ("http", "https"):
            continue
        if parsed.netloc != base_domain:
            continue
        if full_url in seen:
            continue

        url_path = parsed.path.lower()
        anchor_text = tag.get_text(strip=True).lower()

        if any(k in url_path or k in anchor_text for k in keywords):
            seen.add(full_url)
            found.append(full_url)
            if len(found) >= _kb_max_deep_urls():
                break

    return found


async def _run_deep_crawl(cache_key: str, keywords: List[str], query: str):
    """
    Background task: crawl the CGI homepage + relevant sub-pages for the given
    keywords and store results in _deep_scan_cache. Never called on the hot path.
    """
    logger.info(f"[SCAN L2 BG] Starting background deep crawl for '{cache_key}'")
    deep_content = ""
    try:
        # Source URLs are tenant-scoped via bot_config — caller passes
        # company_id through the cache_key by convention "<company_id>:<query>".
        _co_id = cache_key.split(":", 1)[0] if ":" in cache_key else ""
        sources = await _load_scrape_sources(_co_id)
        homepage_url = sources.get("primary_url") or ""
        sub_pages    = sources.get("sub_pages") or []
        if not homepage_url:
            logger.info("[SCAN L2 BG] No primary_url configured for company_id=%s — skipping deep crawl", _co_id)
            return
        homepage_html = await _fetch_with_retry(homepage_url)

        # Extract content from the homepage itself (not just use it for link discovery)
        homepage_lines = _clean_html_text(homepage_html)
        homepage_text  = "\n".join(homepage_lines[:150])

        relevant_urls = _discover_relevant_links(homepage_html, homepage_url, keywords)
        # Add known sub-pages whose path matches a keyword
        for sub in sub_pages:
            path = urlparse(sub).path.lower()
            if any(k in path for k in keywords) and sub not in relevant_urls:
                relevant_urls.append(sub)

        # Fetch sub-pages in parallel
        page_parts = []

        # Include homepage content first if it has keyword matches
        homepage_matched = _extract_matching_lines(keywords, homepage_text, max_lines=20)
        if homepage_matched:
            page_parts.append(f"[{urlparse(homepage_url).netloc or 'primary'} — homepage]\n" + "\n".join(homepage_matched))

        if relevant_urls:
            logger.info(f"[SCAN L2 BG] Crawling {len(relevant_urls)} sub-pages for '{cache_key}'")
            pages = await asyncio.gather(
                *[_fetch_page_text(url) for url in relevant_urls],
                return_exceptions=True,
            )
            for url, page_text in zip(relevant_urls, pages):
                if isinstance(page_text, Exception) or not page_text:
                    continue
                matched = _extract_matching_lines(keywords, page_text, max_lines=20)
                if matched:
                    page_label = url.rstrip("/").split("/")[-1] or "page"
                    page_parts.append(f"[{page_label}]\n" + "\n".join(matched))

        if page_parts:
            deep_content = "\n\n".join(page_parts)
            logger.info(f"[SCAN L2 BG] Found content in {len(page_parts)} pages for '{cache_key}'")
    except Exception as e:
        logger.warning(f"[SCAN L2 BG] Crawl failed for '{cache_key}': {e}")

    if not deep_content:
        deep_content = _fallback_for_keywords(keywords, query)

    _deep_scan_cache[cache_key] = {
        "content": deep_content,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }
    logger.info(f"[SCAN L2 BG] Cache updated for '{cache_key}'")


# ─────────────────────────────────────────────────────────────────────────────
# PERIODIC BACKGROUND CRAWL — stores full CGI site into MongoDB
# ─────────────────────────────────────────────────────────────────────────────

_cgi_crawl_running = False


async def _store_crawl_to_mongodb(url: str, content: str, category: str = "general"):
    """Write a crawled page's content back to MongoDB knowledge_base."""
    try:
        from database import get_database
        db = await get_database()
        title = f"[BGCrawl] {url}"
        await db.knowledge_base.update_one(
            {"title": title},
            {
                "$set": {
                    "title":           title,
                    "category":        category,
                    "question":        f"Information from {url}",
                    "answer":          content,
                    "keywords":        [],
                    "source":          f"background_crawl:{url}",
                    "source_verified": False,
                    "status":          "active",
                    "auto_generated":  True,
                    "updated_at":      datetime.now(timezone.utc).isoformat(),
                },
                "$setOnInsert": {
                    "id":         f"bgcrawl_{hashlib.md5(url.encode()).hexdigest()[:12]}",
                    "version":    1,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "created_by": "periodic_crawl",
                },
            },
            upsert=True,
        )
        logger.info(f"[BGCrawl] Stored {len(content)} chars from {url} → MongoDB")
    except Exception as exc:
        logger.warning(f"[BGCrawl] Failed to store {url}: {exc}")


_CGI_URL_CATEGORY = {
    "passport":  "passport",
    "visa":      "visa",
    "oci":       "oci",
    "fee":       "fees",
    "contact":   "office",
    "emergency": "emergency",
    "consular":  "consular",
    "police":    "consular",
}


async def _do_cgi_full_crawl(company_id: Optional[str] = None):
    """Crawl this tenant's primary site + sub-pages and store full page text
    into MongoDB so hybrid_search Layer 1 benefits from up-to-date live
    content on the next query.

    Note: function name kept (``_do_cgi_full_crawl``) for back-compat with
    any caller; URLs are tenant-driven, not CGI-specific.
    """
    global _cgi_crawl_running
    if _cgi_crawl_running:
        logger.debug("[BGCrawl] Full crawl already in progress — skipping")
        return
    _cgi_crawl_running = True
    try:
        sources = await _load_scrape_sources(company_id)
        primary = sources.get("primary_url") or ""
        sub_pages = sources.get("sub_pages") or []
        all_urls = ([primary] if primary else []) + list(sub_pages)
        if not all_urls:
            logger.info("[BGCrawl] No scrape sources configured for company_id=%s — skipping", company_id)
            return
        logger.info(f"[BGCrawl] Starting full crawl ({len(all_urls)} URLs)")

        # Use _fetch_with_retry directly so the 5-min rate limiter doesn't block
        # an intentional periodic crawl (rate limiter is for the hot query path only)
        results = await asyncio.gather(
            *[_fetch_with_retry(url) for url in all_urls],
            return_exceptions=True,
        )
        stored = 0
        for url, html in zip(all_urls, results):
            if isinstance(html, Exception) or not html:
                continue
            lines = _clean_html_text(html)
            text  = "\n".join(lines[:150])
            if len(text.strip()) < 50:
                continue
            _record_fetch_success(url)   # update last-fetched so rate limiter stays accurate
            # Derive category from URL path
            path = urlparse(url).path.lower()
            category = next(
                (cat for seg, cat in _CGI_URL_CATEGORY.items() if seg in path),
                "general",
            )
            await _store_crawl_to_mongodb(url, text, category)
            stored += 1

        logger.info(f"[BGCrawl] Full CGI crawl complete — {stored}/{len(all_urls)} pages stored")
    except Exception as exc:
        logger.warning(f"[BGCrawl] Full CGI crawl failed: {exc}")
    finally:
        _cgi_crawl_running = False


async def start_periodic_cgi_crawl(company_id: Optional[str] = None):
    """Periodic loop: crawl this tenant's pages and store to MongoDB every
    ``platform_config.kb_crawl_interval_seconds`` (default 6 hours).

    Pass ``company_id`` to scope the crawl to one tenant. Call once at
    server startup via ``asyncio.create_task()``.
    """
    _interval = _kb_crawl_interval()
    logger.info(f"[BGCrawl] Periodic crawl started (interval: {_interval // 3600}h, company_id={company_id})")
    while True:
        await _do_cgi_full_crawl(company_id)
        # Resolve fresh each iteration so a super-admin tuning change
        # applies on the next cycle without restarting the task.
        await asyncio.sleep(_kb_crawl_interval())


# Tracks which cache keys have a background crawl already in flight
_deep_scan_in_progress: set = set()


async def deep_scan_for_keyword(query: str, knowledge_base: Dict) -> str:
    """
    Keyword-driven selective scanner — non-blocking, always returns immediately.

    Level 1 (instant):  Check already-scraped 30-min cache for keyword hits.
                        → hits ≥ threshold → return matching lines right away.

    Level 2 (deferred): Keyword sparse/missing in cache:
                        a. If a fresh per-keyword deep-scan cache exists → return it.
                        b. Otherwise → fire background crawl (fire-and-forget),
                           return Level 3 fallback NOW so the chat is never blocked.

    Level 3 (instant):  Structured fallback data — always available, zero latency.
    """
    keywords = _extract_keywords(query)
    if not keywords:
        return _search_knowledge_sync(query, knowledge_base)

    # Skip deep scan entirely for flow-control words (yes/no/apply/hello etc.)
    # They are never knowledge queries — crawling for them wastes resources
    query_words = set(re.findall(r'\b[a-zA-Z]+\b', query.lower()))
    if query_words and query_words.issubset(_NO_CRAWL_WORDS | _STOP_WORDS):
        return _search_knowledge_sync(query, knowledge_base)

    cache_key = "_".join(sorted(set(keywords[:6])))

    # ── Level 1: fast check against existing scraped cache ───────────
    cgi_content = knowledge_base.get("cgi_joburg", {}).get("page_content", "")
    vfs_content = knowledge_base.get("vfs_global", {}).get("page_content", "")
    combined    = cgi_content + "\n" + vfs_content

    hits = _count_hits(keywords, combined)
    if hits >= _kb_hit_threshold():
        logger.debug(f"[SCAN L1] '{cache_key}' — {hits} hits, returning from cache")
        # Include the original query phrase as an extra keyword so compound terms
        # like "lost passport" score higher than single-keyword lines
        phrase_kws = keywords + ([query.lower().strip()] if len(keywords) > 1 else [])
        cgi_lines = _extract_matching_lines(phrase_kws, cgi_content)
        vfs_lines = _extract_matching_lines(phrase_kws, vfs_content)
        parts = []
        if cgi_lines:
            parts.append("[Primary source]\n" + "\n".join(cgi_lines))
        if vfs_lines:
            parts.append("[Secondary source]\n" + "\n".join(vfs_lines))
        return "\n\n".join(parts) if parts else _search_knowledge_sync(query, knowledge_base)

    # ── Level 2a: check per-keyword deep-scan cache ──────────────────
    cached_deep = _deep_scan_cache.get(cache_key)
    if cached_deep:
        age = (
            datetime.now(timezone.utc)
            - datetime.fromisoformat(cached_deep["scanned_at"])
        ).total_seconds()
        if age < _kb_deep_scan_ttl() and cached_deep.get("content"):
            logger.debug(f"[SCAN L2] '{cache_key}' — deep-scan cache hit (age {int(age)}s)")
            return cached_deep["content"]

    # ── Level 2b: fire background crawl, return fallback immediately ─
    # The crawl result will be available for the NEXT request for this keyword.
    if cache_key not in _deep_scan_in_progress:
        _deep_scan_in_progress.add(cache_key)
        logger.info(f"[SCAN L2] '{cache_key}' — not cached, firing background crawl")

        async def _crawl_and_cleanup():
            try:
                await _run_deep_crawl(cache_key, keywords, query)
            finally:
                _deep_scan_in_progress.discard(cache_key)

        asyncio.create_task(_crawl_and_cleanup())
    else:
        logger.debug(f"[SCAN L2] '{cache_key}' — crawl already in progress, serving fallback")

    # ── Level 3: return structured fallback instantly ────────────────
    fallback = _fallback_for_keywords(keywords, query)
    logger.info(f"[SCAN L3] '{cache_key}' — serving fallback while background crawl runs")
    return fallback if fallback else _search_knowledge_sync(query, knowledge_base)


_FEE_WORDS = {"fee", "fees", "cost", "price", "charges", "how much", "payment", "zar", "rand", "rate", "amount",
              "pricing", "plan", "plans", "tariff", "schedule"}


def _fallback_for_keywords(keywords: List[str], query: str) -> str:
    """
    Return structured fallback data for the service detected from keywords.
    When query contains fee-related words, prioritise fee fields in the output.
    """
    fallback  = get_fallback_knowledge()
    query_low = query.lower()
    kw_set    = set(keywords)
    is_fee_query = bool(kw_set & _FEE_WORDS) or any(w in query_low for w in _FEE_WORDS)

    # Find the matching service (skip generic buckets — handled specially below)
    _SKIP_GENERIC = {"fees", "process_guide"}
    matched_svc = None
    for svc_key, kws in _SERVICE_KEYWORDS.items():
        if svc_key in _SKIP_GENERIC:
            continue
        if any(k in query_low for k in kws) or any(k in kw_set for k in kws):
            matched_svc = svc_key
            break

    # process_guide: return all services summary so the LLM can walk through them
    _is_process_query = any(k in query_low for k in _SERVICE_KEYWORDS.get("process_guide", []))
    if _is_process_query and not matched_svc:
        all_svcs = fallback.get("services", {})
        summary_lines = ["[All Services — Process Overview]"]
        for svc_key, svc_data in all_svcs.items():
            desc = svc_data.get("description", "")
            online = svc_data.get("apply_online", "")
            fee = svc_data.get("fees_zar", svc_data.get("fee", ""))
            proc = svc_data.get("processing_time", "")
            line = f"\n{svc_key.upper().replace('_',' ')}: {desc}"
            if online:
                line += f" | Apply: {online}"
            if fee:
                line += f" | Fee: {fee}"
            if proc:
                line += f" | Time: {proc}"
            summary_lines.append(line)
        return "\n".join(summary_lines)

    parts = []

    # If it's a fee query, lead with the fee field from the matched service
    if is_fee_query and matched_svc:
        svc_data = fallback.get("services", {}).get(matched_svc, {})
        # Collect all fee-related fields first
        fee_lines = []
        other_lines = []
        for k, v in svc_data.items():
            label = k.replace("_", " ").title()
            if isinstance(v, list):
                other_lines.append(label + ":\n" + "\n".join(f"  • {item}" for item in v))
            elif any(w in k.lower() for w in ("fee", "cost", "price", "zar", "charge")):
                fee_lines.append(f"{label}: {v}")
            else:
                other_lines.append(f"{label}: {v}")

        if fee_lines:
            parts.append(f"[{matched_svc.title()} Fees]\n" + "\n".join(fee_lines))
        if other_lines:
            parts.append(f"[{matched_svc.title()} Details]\n" + "\n".join(other_lines))
        return "\n\n".join(parts) if parts else ""

    # Non-fee query — return full service data
    if matched_svc:
        svc_data = fallback.get("services", {}).get(matched_svc, {})
        lines = []
        for k, v in svc_data.items():
            label = k.replace("_", " ").title()
            if isinstance(v, list):
                lines.append(label + ":\n" + "\n".join(f"  • {item}" for item in v))
            else:
                lines.append(f"{label}: {v}")
        return f"[Official knowledge base — {matched_svc}]\n" + "\n".join(lines)

    return ""


def _search_knowledge_sync(query: str, knowledge_base: Dict) -> str:
    """
    Synchronous fallback: return keyword-filtered scraped content + contact block.
    Used when async deep scan is not needed or as a last resort.
    """
    cgi    = knowledge_base.get("cgi_joburg", {})
    vfs    = knowledge_base.get("vfs_global", {})
    cgi_content = cgi.get("page_content", "").strip()
    vfs_content = vfs.get("page_content", "").strip()
    cgi_status  = cgi.get("status", "unknown")
    vfs_status  = vfs.get("status", "unknown")

    # Contact block: built from the contact fields extracted off the
    # scraped homepage (cgi.get(...)). Tenants supply richer contact info
    # via bot_config.contact, which is rendered into the system prompt
    # separately; this block is just what the scraper found.
    contact_lines: list[str] = []
    contact_src: dict = cgi or {}
    for label, key in (
        ("Phone",   "phone_main"), ("Consular", "phone_consular"),
        ("Email",   "email"),       ("Consular email", "email_consular"),
        ("Address", "address"),     ("Office Hours",   "office_hours"),
        ("Website", "website"),
    ):
        val = contact_src.get(key) or ""
        if val:
            contact_lines.append(f"- {label}: {val}")
    contact_block = (
        "CONTACT & LOCATION:\n" + "\n".join(contact_lines)
        if contact_lines else ""
    )

    keywords = _extract_keywords(query)
    # Include the original query phrase so compound terms rank above single-keyword lines
    phrase_kws = keywords + ([query.lower().strip()] if len(keywords) > 1 else [])
    scraped_at = cgi.get("scraped_at") or knowledge_base.get("last_updated", "")
    sections = [contact_block] if contact_block else []
    if scraped_at:
        sections.append(f"[Data last scraped: {scraped_at}]")

    for label, content, status in [
        ("CGI JOHANNESBURG", cgi_content, cgi_status),
        ("VFS GLOBAL",       vfs_content, vfs_status),
    ]:
        if content:
            lines = _extract_matching_lines(phrase_kws, content, max_lines=30)
            if not lines:
                lines = [l.strip() for l in content.split("\n") if l.strip()][:15]
            sections.append(f"=== {label} (live) ===\n" + "\n".join(lines))
        else:
            sections.append(f"=== {label}: scraping failed ({status}) ===")
            fallback_text = _fallback_for_keywords(keywords, query)
            if fallback_text:
                sections.append(fallback_text)

    return "\n\n".join(sections)


# Public alias kept for callers that only need the sync fast path
def search_knowledge(query: str, knowledge_base: Dict) -> str:
    return _search_knowledge_sync(query, knowledge_base)


def extract_service_content(service_key: str, knowledge_base: Dict, user_query: str = "") -> str:
    """Return service-specific lines from scraped content or structured fallback.

    When user_query is provided, the original query phrase is appended as an
    extra keyword so compound terms (e.g. 'lost passport') rank above generic lines.
    """
    kws = list(_SERVICE_KEYWORDS.get(service_key, []))
    if user_query:
        phrase = user_query.lower().strip()
        if phrase and phrase not in kws:
            kws = kws + [phrase]

    cgi_content = knowledge_base.get("cgi_joburg", {}).get("page_content", "")
    vfs_content = knowledge_base.get("vfs_global", {}).get("page_content", "")

    parts = []
    for label, content in [("CGI Johannesburg", cgi_content), ("VFS Global", vfs_content)]:
        if not content:
            continue
        matched = _extract_matching_lines(kws, content, max_lines=15)
        if matched:
            parts.append(f"[{label}]\n" + "\n".join(matched))

    if parts:
        return "\n\n".join(parts)

    # Websites blocked/empty — use structured fallback
    fallback = get_fallback_knowledge()
    svc_data = fallback.get("services", {}).get(service_key)
    if not svc_data:
        return ""

    lines = []
    for k, v in svc_data.items():
        if isinstance(v, list):
            lines.append(f"{k.replace('_', ' ').title()}:\n" + "\n".join(f"  • {item}" for item in v))
        else:
            lines.append(f"{k.replace('_', ' ').title()}: {v}")
    return "[Official knowledge base (live websites temporarily unavailable)]\n" + "\n".join(lines)
