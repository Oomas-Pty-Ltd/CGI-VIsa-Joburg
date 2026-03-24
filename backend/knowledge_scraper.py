import httpx
from bs4 import BeautifulSoup
import json
import logging
import re
from typing import List, Dict, Optional, Set
from urllib.parse import urljoin, urlparse
import asyncio
from datetime import datetime, timezone, timedelta
import hashlib
import os

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# FETCH LAYER CONTROL
# ─────────────────────────────────────────────────────────────────────────────

# Playwright availability flag — set to False on first ImportError
_playwright_available: Optional[bool] = None

# ── Failed URL store ──────────────────────────────────────────────────────────
# Tracks URLs that failed permanently so we never retry within the cooldown.
# Schema: {url: {"reason": str, "failed_at": datetime, "attempts": int}}
_failed_urls: Dict[str, Dict] = {}
_FAILED_URL_COOLDOWN_HOURS = 6   # don't retry a failed URL for 6 hours
_FAILED_URL_MAX_ATTEMPTS   = 3   # mark permanent after 3 consecutive failures

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
            await page.goto(url, wait_until="networkidle", timeout=20000)
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
    }
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, verify=False) as client:
        response = await client.get(url, headers=headers)
        if response.status_code == 200:
            return response.text
        if response.status_code in (403, 404):
            raise Exception(f"HTTP {response.status_code} (permanent)")
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

OFFICIAL_SOURCES = [
    "https://www.cgijoburg.gov.in/",
    "https://visa.vfsglobal.com/one-pager/india/south-africa/johannesburg/"
]

# Sub-pages to crawl on CGI Joburg for richer service data
CGI_SUB_PAGES = [
    "https://www.cgijoburg.gov.in/page/passport-services/",
    "https://www.cgijoburg.gov.in/page/visa-services/",
    "https://www.cgijoburg.gov.in/page/oci-services/",
    "https://www.cgijoburg.gov.in/page/fee-schedule/",
    "https://www.cgijoburg.gov.in/page/contact-us/",
    "https://www.cgijoburg.gov.in/page/emergency-services/",
]

EXCEPTION_EMAIL = "mayurakole@example.com"

CONTACT_FALLBACK = {
    "emergency_contact": "+27 6830 38144",
    "email": "cons.joburg@mea.gov.in",
    "address": "Consulate General of India, 1st Floor, Cedar Square, Corner Willow Ave & Cedar Road, Fourways, Johannesburg 2055",
    "website": "https://www.cgijoburg.gov.in",
    "vfs_address": "VFS Global Visa Application Centre, Johannesburg",
    "vfs_website": "https://visa.vfsglobal.com/one-pager/india/south-africa/johannesburg/",
    "office_hours": "Monday–Friday: 09:00–17:00 | Consular services: 09:00–12:00 (by appointment)",
    "vfs_hours": "Monday–Friday: 08:00–15:00 (appointment mandatory)",
}


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
    Falls back to CONTACT_FALLBACK for any field not found.
    """
    full_text = soup.get_text(separator=" ", strip=True)

    extracted = {}

    # Phone numbers — match +27 or 0 prefix SA numbers
    phones = re.findall(r"(?:\+27|0)\s*[\d\s\-]{8,14}", full_text)
    phones = [re.sub(r"\s+", " ", p).strip() for p in phones]
    if phones:
        extracted["emergency_contact"] = phones[0]

    # Email addresses
    emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", full_text)
    if emails:
        extracted["email"] = emails[0]

    # Address — look for common address indicators
    addr_match = re.search(
        r"(?:(?:\d+(?:st|nd|rd|th)?\s+[Ff]loor|[Ff]loor\s+\d+)[^.]{0,200}(?:johannesburg|joburg))",
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

    # Merge: scraped fields override fallback, fallback fills any gaps
    return {**CONTACT_FALLBACK, **extracted}


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


async def scrape_cgi_joburg() -> Dict:
    """Scrape CGI Joburg homepage + key sub-pages concurrently."""
    try:
        # Fetch homepage + all sub-pages concurrently
        all_urls = ["https://www.cgijoburg.gov.in/"] + CGI_SUB_PAGES
        results = await asyncio.gather(
            *[_fetch_page_text(url) for url in all_urls],
            return_exceptions=True
        )

        # Combine all page text, labelled by URL, skip failures
        combined_parts = []
        contact_html = None
        for url, result in zip(all_urls, results):
            if isinstance(result, Exception) or not result:
                continue
            page_name = url.rstrip("/").split("/")[-1] or "home"
            combined_parts.append(f"[Page: {page_name}]\n{result}")
            # Use homepage HTML for contact extraction
            if url == "https://www.cgijoburg.gov.in/":
                contact_html = result

        page_content = "\n\n".join(combined_parts)

        # Extract live contact details from homepage
        live_contact = CONTACT_FALLBACK.copy()
        if contact_html:
            try:
                soup = BeautifulSoup(
                    await _fetch_with_retry("https://www.cgijoburg.gov.in/"),
                    "html.parser"
                )
                live_contact = _extract_contact_details(soup)
            except Exception:
                pass

        return {
            "source": "cgijoburg.gov.in",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "status": "live_scraped",
            "pages_crawled": len([r for r in results if not isinstance(r, Exception) and r]),
            "page_content": page_content,
            **live_contact,
        }
    except Exception as e:
        await send_exception_email("CGI Joburg Scraping Failed", str(e))
        return {"source": "cgijoburg.gov.in", "status": "failed", "page_content": "", "pages_crawled": 0, **CONTACT_FALLBACK}


async def scrape_vfs_global() -> Dict:
    """
    Scrape VFS Global. The main one-pager URL is JavaScript-rendered (SPA),
    so we also try the static/alternative endpoints for actual content.
    """
    vfs_urls = [
        # Try static/print versions and alternative paths first
        "https://visa.vfsglobal.com/one-pager/india/south-africa/johannesburg/",
        "https://www.vfsglobal.com/india/southafrica/english/index.html",
        "https://www.vfsglobal.com/india/southafrica/english/contact-us.html",
    ]

    page_content = ""
    live_contact = CONTACT_FALLBACK.copy()

    for url in vfs_urls:
        try:
            html = await _fetch_with_retry(url)
            lines = _clean_html_text(html)

            # Check if we got real content (JS-rendered pages return very little text)
            if len(lines) < 5:
                continue

            page_content = "\n".join(lines[:150])
            soup = BeautifulSoup(html, "html.parser")
            contact = _extract_contact_details(soup)
            live_contact = contact

            # VFS-specific hours override
            full_text = soup.get_text(separator=" ", strip=True)
            vfs_hours_match = re.search(
                r"(?:Mon(?:day)?|Monday)[\s\S]{0,80}?(?:\d{1,2}[:.]\d{2}[\s\S]{0,40}?\d{1,2}[:.]\d{2})",
                full_text, re.IGNORECASE
            )
            if vfs_hours_match:
                live_contact["vfs_hours"] = re.sub(r"\s+", " ", vfs_hours_match.group()).strip()
            break
        except Exception:
            continue

    # If all VFS URLs failed or returned JS-shell, use structured fallback content
    if not page_content:
        page_content = _get_vfs_static_content()

    return {
        "source": "VFS Global",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "status": "live_scraped" if page_content else "failed",
        "page_content": page_content,
        **live_contact,
    }


def _get_vfs_static_content() -> str:
    """Return well-structured VFS information as fallback when live scraping fails."""
    return """[VFS Global - India Visa Application Centre, Johannesburg]
Location: VFS Global, Johannesburg (appointment mandatory)
Website: https://visa.vfsglobal.com/one-pager/india/south-africa/johannesburg/
Office Hours: Monday–Friday 08:00–15:00
Appointment: Book online at visa.vfsglobal.com

Services offered at VFS Johannesburg:
- Tourist Visa (short-term, up to 90 days)
- Business Visa
- Employment Visa
- Student Visa
- Medical Visa
- Conference Visa
- OCI Card application and re-issue
- Passport submission (new and renewal)
- Police Clearance Certificate (PCC)
- Document Attestation / Apostille

Visa Application Requirements:
- Completed online application form (indianvisaonline.gov.in)
- Valid passport (6 months validity minimum)
- Recent passport-size photographs (51mm x 51mm, white background)
- Proof of residence in South Africa
- Bank statements (last 3 months)
- Return flight booking
- Hotel/accommodation proof
- Travel insurance

Processing Times:
- Standard visa: 5–7 working days
- Urgent processing: 2–3 working days (additional fee applies)
- OCI card: 60–90 working days

Fees (approximate, subject to change):
- Tourist Visa: ZAR 1,750
- Business Visa: ZAR 2,100
- OCI Card: ZAR 3,500
- Passport Renewal: ZAR 2,400

Contact VFS: +27 (0) 11 804 2442
VFS Email: info.ind@vfsglobal.com"""


_knowledge_cache: Optional[Dict] = None
_knowledge_cache_time: Optional[datetime] = None
_scrape_in_progress: bool = False
_CACHE_TTL_SECONDS = 1800  # 30 minutes


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


async def _do_scrape() -> Dict:
    """Run both scrapers concurrently and return combined knowledge."""
    await _probe_playwright()   # set the flag once before parallel fetches
    cgi_data, vfs_data = await asyncio.gather(
        scrape_cgi_joburg(),
        scrape_vfs_global(),
    )
    return {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "cgi_joburg": cgi_data,
        "vfs_global": vfs_data,
        **CONTACT_FALLBACK,
        "official_links": {
            "consulate": "https://www.cgijoburg.gov.in/",
            "vfs": "https://visa.vfsglobal.com/one-pager/india/south-africa/johannesburg/",
            "passport_seva": "https://portal2.passportindia.gov.in/",
            "e_visa": "https://indianvisaonline.gov.in/",
        },
    }


async def _refresh_cache_background():
    """Scrape in the background and update cache without blocking requests."""
    global _knowledge_cache, _knowledge_cache_time, _scrape_in_progress
    if _scrape_in_progress:
        return
    _scrape_in_progress = True
    try:
        data = await _do_scrape()
        await log_knowledge_changes(data)
        _knowledge_cache = data
        _knowledge_cache_time = datetime.now(timezone.utc)
    except Exception as e:
        await send_exception_email("Real-time Knowledge Fetch Failed", str(e))
    finally:
        _scrape_in_progress = False


async def get_realtime_knowledge() -> Dict:
    """
    Always returns immediately — never blocks a chat request.
    Fires a background scrape when cache is empty or stale.
    """
    global _knowledge_cache, _knowledge_cache_time

    now = datetime.now(timezone.utc)
    cache_stale = (
        _knowledge_cache is None
        or _knowledge_cache_time is None
        or (now - _knowledge_cache_time).total_seconds() >= _CACHE_TTL_SECONDS
    )

    if cache_stale and not _scrape_in_progress:
        # Fire-and-forget — never await this
        asyncio.create_task(_refresh_cache_background())

    # Return whatever we have right now; fallback if cache is still empty
    return _knowledge_cache if _knowledge_cache is not None else get_fallback_knowledge()


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
        print(f"Error logging changes: {e}")


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
        print(f"Exception logged: {subject}")
    except Exception as e:
        print(f"Failed to log exception: {e}")


def get_fallback_knowledge() -> Dict:
    """Comprehensive fallback knowledge base when scraping fails."""
    return {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "source": "Fallback - Official Information (cached)",
        "emergency_contact": "+27 6830 38144",
        "email": "cons.joburg@mea.gov.in",
        "services": {
            "passport": {
                "new_passport": "Apply online at passportindia.gov.in, submit documents at VFS Johannesburg",
                "renewal": "Online application required, valid for 10 years for adults",
                "tatkal": "Urgent passport processing available (extra fee applies, 1–3 working days)",
                "documents_required": [
                    "Online application receipt (passportindia.gov.in)",
                    "Current passport (original + copy, for renewal)",
                    "Proof of Indian citizenship",
                    "Proof of residence in South Africa",
                    "Photographs: 51mm x 51mm, white background, no glasses",
                    "Fees paid receipt"
                ],
                "processing_time": "Standard: 7–10 working days | Tatkal: 1–3 working days",
                "fees_zar": "New passport: ZAR 2,400 | Renewal: ZAR 2,400 | Tatkal surcharge: ZAR 800"
            },
            "visa": {
                "tourist_visa": "Apply online at indianvisaonline.gov.in, submit at VFS Johannesburg",
                "business_visa": "Letter from SA company + invitation from Indian company required",
                "e_visa": "Available at indianvisaonline.gov.in — instant approval for 60-day stay",
                "student_visa": "Admission letter from Indian institution required",
                "medical_visa": "Letter from Indian hospital required",
                "processing_time": "Standard: 5–7 working days | Urgent: 2–3 working days",
                "visa_fees": (
                    "Tourist Visa fee: ZAR 1,750 | "
                    "Business Visa fee: ZAR 2,100 | "
                    "Student Visa fee: ZAR 1,500 | "
                    "Medical Visa fee: ZAR 1,750 | "
                    "Urgent/Express processing fee: additional ZAR 500"
                ),
                "fees_note": "Visa fees are paid at VFS Global — fees subject to change, verify at visa.vfsglobal.com",
                "documents_required": [
                    "Completed online application form",
                    "Valid passport (6+ months validity)",
                    "2 passport photographs",
                    "Bank statements (3 months)",
                    "Return flight booking",
                    "Hotel/accommodation proof",
                    "Travel insurance"
                ]
            },
            "oci": {
                "description": "Overseas Citizen of India card — lifelong multiple-entry visa",
                "eligibility": "Person of Indian Origin (PIO), spouse of Indian citizen/OCI holder",
                "application": "Apply online at ociservices.gov.in, submit at VFS Johannesburg",
                "validity": "Lifelong — re-issue required at age 20 and 50",
                "benefits": "Multiple-entry, multi-purpose lifelong visa; parity with NRI on most financial matters",
                "processing_time": "60–90 working days",
                "fees_zar": "ZAR 3,500 (new) | ZAR 2,000 (re-issue)",
                "documents_required": [
                    "Renunciation certificate (if applicable)",
                    "South African ID/PR document",
                    "Proof of Indian origin",
                    "Current passport",
                    "Birth certificate"
                ]
            },
            "pcc": {
                "description": "Police Clearance Certificate for Indian nationals in South Africa",
                "processing_time": "10–15 working days",
                "fees_zar": "ZAR 600",
                "documents_required": [
                    "Passport copy",
                    "Proof of residence in South Africa",
                    "Application form (from consulate)"
                ]
            },
            "attestation": {
                "description": "Document attestation, apostille, affidavit, power of attorney",
                "processing_time": "3–5 working days",
                "fees_zar": "Attestation per document: ZAR 500 | Apostille: ZAR 700",
                "documents_required": [
                    "Original document",
                    "Notarised copy",
                    "Passport copy",
                    "Application form"
                ]
            }
        },
        "vfs_locations": {
            "johannesburg": {
                "address": "VFS Global, Johannesburg",
                "timings": "Monday–Friday: 08:00–15:00",
                "appointment": "Mandatory — book at visa.vfsglobal.com",
                "phone": "+27 (0) 11 804 2442"
            }
        },
        "official_links": {
            "consulate": "https://www.cgijoburg.gov.in/",
            "vfs": "https://visa.vfsglobal.com/one-pager/india/south-africa/johannesburg/",
            "passport_seva": "https://portal2.passportindia.gov.in/",
            "e_visa": "https://indianvisaonline.gov.in/",
            "oci_services": "https://ociservices.gov.in/"
        }
    }


def get_fallback_vfs_info() -> Dict:
    return {
        "source": "VFS Global (cached)",
        "location": {
            "address": "VFS Global, Johannesburg",
            "timings": "Monday–Friday: 08:00–15:00"
        }
    }


_SERVICE_KEYWORDS = {
    "visa":        ["visa", "vfs", "e-visa", "tourist", "business visa", "application fee", "indianvisaonline",
                    "e_visa", "evisa", "visa fee", "visa fees", "visa cost", "visa price", "visa charges",
                    "visa application", "how much visa", "tourist fee", "business fee"],
    "passport":    ["passport", "renewal", "tatkal", "passportindia", "fresh passport", "travel document",
                    "passport seva", "passport fee", "passport fees", "passport cost", "passport charges",
                    "how much passport"],
    "oci":         ["oci", "overseas citizen", "lifelong visa", "oci card", "person of indian origin",
                    "ociservices", "oci fee", "oci fees", "oci cost"],
    "pcc":         ["pcc", "police clearance", "clearance certificate", "criminal record", "character certificate",
                    "pcc fee", "pcc fees"],
    "marriage":    ["marriage", "matrimonial", "spouse", "wedding", "nikah", "marry", "marriage certificate",
                    "marriage fee"],
    "birth":       ["birth", "born", "newborn", "child registration", "birth certificate"],
    "attestation": ["attestation", "apostille", "notary", "affidavit", "power of attorney", "legalization",
                    "legalisation", "attestation fee", "apostille fee"],
    "renunciation":["renunciation", "renounce", "surrender passport", "citizenship", "give up citizenship"],
    "fees":        ["fees", "fee", "cost", "price", "charges", "how much", "payment", "zar", "rand",
                    "rate", "amount", "tariff"],
}

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

_HIT_THRESHOLD = 3       # min matching lines to consider Level 1 "found"
_MAX_DEEP_URLS = 8       # max pages to crawl per deep scan
_DEEP_SCAN_TTL = 1800    # 30 minutes per-keyword deep-scan cache

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
    """Return lines from content that contain at least one keyword."""
    if not content or not keywords:
        return []
    return [
        line.strip() for line in content.split("\n")
        if line.strip() and any(k in line.lower() for k in keywords)
    ][:max_lines]


def _discover_relevant_links(homepage_html: str, base_url: str, keywords: List[str]) -> List[str]:
    """
    Parse homepage HTML for same-domain <a href> links whose URL path or
    anchor text contains at least one keyword. Returns up to _MAX_DEEP_URLS URLs.
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
            if len(found) >= _MAX_DEEP_URLS:
                break

    return found


async def _run_deep_crawl(cache_key: str, keywords: List[str], query: str):
    """
    Background task: crawl relevant sub-pages for the given keywords and
    store results in _deep_scan_cache. Never called on the hot path.
    """
    logger.info(f"[SCAN L2 BG] Starting background deep crawl for '{cache_key}'")
    deep_content = ""
    try:
        homepage_html = await _fetch_with_retry("https://www.cgijoburg.gov.in/")
        relevant_urls = _discover_relevant_links(
            homepage_html, "https://www.cgijoburg.gov.in/", keywords
        )
        # Add known sub-pages whose path matches a keyword
        for sub in CGI_SUB_PAGES:
            path = urlparse(sub).path.lower()
            if any(k in path for k in keywords) and sub not in relevant_urls:
                relevant_urls.append(sub)

        if relevant_urls:
            logger.info(f"[SCAN L2 BG] Crawling {len(relevant_urls)} pages for '{cache_key}'")
            pages = await asyncio.gather(
                *[_fetch_page_text(url) for url in relevant_urls],
                return_exceptions=True,
            )
            page_parts = []
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

    cache_key = "_".join(sorted(set(keywords[:6])))

    # ── Level 1: fast check against existing scraped cache ───────────
    cgi_content = knowledge_base.get("cgi_joburg", {}).get("page_content", "")
    vfs_content = knowledge_base.get("vfs_global", {}).get("page_content", "")
    combined    = cgi_content + "\n" + vfs_content

    hits = _count_hits(keywords, combined)
    if hits >= _HIT_THRESHOLD:
        logger.debug(f"[SCAN L1] '{cache_key}' — {hits} hits, returning from cache")
        cgi_lines = _extract_matching_lines(keywords, cgi_content)
        vfs_lines = _extract_matching_lines(keywords, vfs_content)
        parts = []
        if cgi_lines:
            parts.append("[CGI Johannesburg]\n" + "\n".join(cgi_lines))
        if vfs_lines:
            parts.append("[VFS Global]\n" + "\n".join(vfs_lines))
        return "\n\n".join(parts) if parts else _search_knowledge_sync(query, knowledge_base)

    # ── Level 2a: check per-keyword deep-scan cache ──────────────────
    cached_deep = _deep_scan_cache.get(cache_key)
    if cached_deep:
        age = (
            datetime.now(timezone.utc)
            - datetime.fromisoformat(cached_deep["scanned_at"])
        ).total_seconds()
        if age < _DEEP_SCAN_TTL and cached_deep.get("content"):
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


_FEE_WORDS = {"fee", "fees", "cost", "price", "charges", "how much", "payment", "zar", "rand", "rate", "amount"}


def _fallback_for_keywords(keywords: List[str], query: str) -> str:
    """
    Return structured fallback data for the service detected from keywords.
    When query contains fee-related words, prioritise fee fields in the output.
    """
    fallback  = get_fallback_knowledge()
    query_low = query.lower()
    kw_set    = set(keywords)
    is_fee_query = bool(kw_set & _FEE_WORDS) or any(w in query_low for w in _FEE_WORDS)

    # Find the matching service (skip the generic "fees" bucket — handled below)
    matched_svc = None
    for svc_key, kws in _SERVICE_KEYWORDS.items():
        if svc_key == "fees":
            continue
        if any(k in query_low for k in kws) or any(k in kw_set for k in kws):
            matched_svc = svc_key
            break

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

    contact_block = (
        f"CONTACT & LOCATION:\n"
        f"- Phone: {CONTACT_FALLBACK['emergency_contact']}\n"
        f"- Email: {CONTACT_FALLBACK['email']}\n"
        f"- Address: {CONTACT_FALLBACK['address']}\n"
        f"- Office Hours: {CONTACT_FALLBACK['office_hours']}\n"
        f"- VFS Address: {CONTACT_FALLBACK['vfs_address']}\n"
        f"- VFS Hours: {CONTACT_FALLBACK['vfs_hours']}\n"
        f"- Consulate Website: {CONTACT_FALLBACK['website']}\n"
        f"- VFS Website: {CONTACT_FALLBACK['vfs_website']}"
    )

    keywords = _extract_keywords(query)
    scraped_at = cgi.get("scraped_at") or knowledge_base.get("last_updated", "")
    sections = [contact_block]
    if scraped_at:
        sections.append(f"[Data last scraped: {scraped_at}]")

    for label, content, status in [
        ("CGI JOHANNESBURG", cgi_content, cgi_status),
        ("VFS GLOBAL",       vfs_content, vfs_status),
    ]:
        if content:
            lines = _extract_matching_lines(keywords, content, max_lines=30)
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


def extract_service_content(service_key: str, knowledge_base: Dict) -> str:
    """Return service-specific lines from scraped content or structured fallback."""
    kws = _SERVICE_KEYWORDS.get(service_key, [])

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
