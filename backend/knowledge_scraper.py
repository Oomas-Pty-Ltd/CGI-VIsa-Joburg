import httpx
from bs4 import BeautifulSoup
import json
import logging
import re
import sys
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
        "Referer": "https://www.cgijoburg.gov.in/",
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

OFFICIAL_SOURCES = [
    "https://www.cgijoburg.gov.in/",
]

# Sub-pages to crawl on CGI Joburg for richer service data
CGI_SUB_PAGES = [
    "https://www.cgijoburg.gov.in/page/passport-services/",
    "https://www.cgijoburg.gov.in/page/visa-services/",
    "https://www.cgijoburg.gov.in/page/oci-services/",
    "https://www.cgijoburg.gov.in/page/fee-schedule/",
    "https://www.cgijoburg.gov.in/page/contact-us/",
    "https://www.cgijoburg.gov.in/page/emergency-contact/",
    "https://www.cgijoburg.gov.in/page/police-clearance-certificate/",
    "https://www.cgijoburg.gov.in/page/services-rendered-at-the-consulate/",
]

EXCEPTION_EMAIL = "mayurakole@example.com"

# Source: www.cgijoburg.gov.in (compiled April 2026)
CONTACT_FALLBACK = {
    "phone_main":        "+27 11-4828484 / +27 11-4828485 / +27 11-4828486",
    "phone_consular":    "+27 11 581 9800",
    "fax":               "+27 11 482 4648 / +27 11 482 8492",
    "emergency_contact": "+27 11 581 9800",
    "email":             "ccom.jburg@mea.gov.in",
    "email_consular":    "cons.jburg@mea.gov.in",
    "address": (
        "Consulate General of India, Johannesburg | "
        "No. 1, Eton Road (Corner Jan Smuts Avenue & Eton Road), "
        "Park Town 2193, PO Box 6805, Johannesburg 2000, South Africa"
    ),
    "website":    "https://www.cgijoburg.gov.in",
    "vfs_address": (
        "Indian Visa and Consular Application Centre, "
        "2nd Floor, Harrow Court 1, Isle of Houghton Office Park, "
        "Boundary Road, Park Town, Johannesburg – 2198"
    ),
    "vfs_phone":  "012 425 3007 / 011 484 0327",
    "vfs_email":  "Info.inza@vfshelpline.com",
    "vfs_website": "https://services.vfsglobal.com/zaf/en/ind/",
    "office_hours": "Monday–Friday: 08:30–17:00 (Lunch: 13:00–13:30)",
    "vfs_hours":    "Submission: 08:00–15:00 | Collection: 11:00–16:00",
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


def _get_cgi_pdf_content() -> str:
    """
    Full content of the CGI Johannesburg official website, sourced from
    www.cgijoburg.gov.in (compiled April 2026).
    Used as fallback when the live website cannot be reached.
    """
    return """
[CONSULATE GENERAL OF INDIA, JOHANNESBURG — OFFICIAL INFORMATION]
Source: www.cgijoburg.gov.in | Compiled: April 2026

=== 1. CONTACT & WORKING HOURS ===
Name: Consulate General of India, Johannesburg
Address: No. 1, Eton Road (Corner Jan Smuts Avenue & Eton Road), Park Town 2193, PO Box 6805, Johannesburg 2000, South Africa
Office Hours: Monday to Friday: 08:30 to 17:00 (Lunch: 13:00 to 13:30)
Telephone: +27 11-4828484 / +27 11-4828485 / +27 11-4828486 / +27 11 581 9800
Facsimile: +27 11 482 4648 / +27 11 482 8492
Fax (CG): +27 11 482 3640
Email: ccom.jburg@mea.gov.in
Consular Services Email: cons.jburg@mea.gov.in
Website: www.cgijoburg.gov.in
Jurisdiction: Gauteng, North West, Limpopo and Mpumalanga provinces of South Africa
Acting Consul General: Mr. Harish Kumar
Twitter/X: @indiainjoburg | Facebook: IndiaInSouthAfricaJohannesburg | Instagram: @indiainjohannesburg | YouTube: @Indiainjoburg

=== 2. CONSULAR SERVICES OVERVIEW ===
Passport Services: Renewal, reissue, lost/stolen/damaged passport, new passport for minors born in South Africa, change of personal particulars.
Visa Services: Regular visa and e-Visa for foreign nationals wishing to visit India.
OCI Services: Fresh OCI card, miscellaneous OCI services, PIO to OCI conversion.
Police Clearance Certificate: Issued for Indian nationals residing in South Africa.
Birth Registration: Registration of births of children born in South Africa to Indian nationals.
Document Attestation: Attestation of academic degrees, general power of attorney, documents for Indian and foreign nationals.
Emergency Travel Document: Issued in cases of lost/stolen passport for emergency travel.
NOC Services: NOC for South African citizenship, NOC for child passport in India.
Non-Impediment Letter: For Indian nationals seeking to marry abroad.
Registration of Indians: Registration of NRIs/PIOs/OCIs residing in South Africa.
Indians in Distress: Consular assistance for Indian nationals in distress.
Tracing the Roots: Programme for persons of Indian origin to trace their ancestral roots in India.
Trade & Commerce: Advisory services, bilateral trade facilitation.
NOTE: Most passport and visa services are processed through VFS Global. Applicants must submit applications at the VFS Global Centre, not directly at the Consulate.

=== 3. PASSPORT SERVICES FOR INDIAN NATIONALS ===
All passport services are outsourced to VFS Global. Applicants must complete online applications and submit at VFS Global Johannesburg.

VFS Global Office (Passport/PCC/Consular):
Address: Indian Visa and Consular Application Centre, 2nd Floor, Harrow Court 1, Isle of Houghton Office Park, Boundary Road, Park Town, Johannesburg - 2198
Telephone: 012 425 3007 / 011 484 0327
Email: Info.inza@vfshelpline.com
Website: https://services.vfsglobal.com/zaf/en/ind/
Submission Hours: 08:00 to 15:00
Collection Hours: 11:00 to 16:00
Processing Time: Up to one month (provided all documents are in order and security status is clear)

RE-ISSUE OF PASSPORT ON EXPIRY:
- Completed online application from https://embassy.passportindia.gov.in/
- 3 passport-sized photographs (5cm x 5cm, coloured, white background)
- Original passport (to be returned after verification)
- Proof of residential address in South Africa
- Fee: Rand 2,280 for 36-page passport (incl. ICWF fee of Rand 30); Rand 2,655 for 60-page

RE-ISSUE FOR LOST/STOLEN PASSPORT:
- Online application form duly completed
- Original FIR/Police Report for lost/stolen passport
- 3 passport-sized photographs
- Proof of Indian citizenship (if original passport not available)
- Proof of residential address in South Africa
- Fee: Rand 2,280 for 36-page; Rand 2,655 for 60-page (incl. ICWF of Rand 30)
- Processing time: Up to one month

RE-ISSUE FOR DAMAGED PASSPORT:
- Online application form
- Original damaged passport
- 3 passport-sized photographs
- Proof of residential address
- Fee: Rand 2,280 for 36-page; Rand 2,655 for 60-page (incl. ICWF of Rand 30)

ISSUE OF PASSPORT TO MINOR CHILD BORN IN SOUTH AFRICA:
- Completed online application
- 3 passport-sized photographs
- Birth registration at the Consulate
- Birth certificate issued by South African Home Department and local hospital
- Both parents to sign the form at the declaration column
- For infants: thumb impression in the box on Page 1 and Page 2 after Serial No. 26
- Fee: Rand 780 (incl. ICWF of Rand 30); Five-year validity passport issued

RE-ISSUE ON CHANGE OF NAME/PASSPORT PARTICULARS:
- Online application + documentary evidence of name change (gazette, court order, marriage certificate)
- Original passport, 3 passport-sized photographs, Proof of residential address
- Fee: Rand 2,280 for 36-page; Rand 2,655 for 60-page

RE-ISSUE ON EXHAUSTION OF PAGES:
- Online application, Original passport, 3 photographs, Proof of residential address
- Fee: Rand 2,280 for 36-page; Rand 2,655 for 60-page

GENERAL NOTES:
- Payment by EFT or Credit/Debit Card. Original proof of payment required; photocopies not accepted.
- Online application at: https://embassy.passportindia.gov.in/
- Applications must be submitted in person at VFS Global. No direct submissions at the Consulate.
- Original documents are returned after verification at VFS.
- Applicants may be called for interview if required by the Consulate.

=== 4. PASSPORT & CONSULAR FEES SCHEDULE ===
(Revised fees as on April 1, 2023. All fees include ICWF component of Rand 30)

PASSPORT FEES:
Re-issue on expiry: 36-page ZAR 2,280 | 60-page ZAR 2,655
Re-issue (lost/stolen): 36-page ZAR 2,280 | 60-page ZAR 2,655
Re-issue (damaged): 36-page ZAR 2,280 | 60-page ZAR 2,655
Re-issue (change of name/particulars): 36-page ZAR 2,280 | 60-page ZAR 2,655
Re-issue (exhaustion of pages): 36-page ZAR 2,280 | 60-page ZAR 2,655
Minor child (new passport): ZAR 780 (N/A for 60-page)
Emergency Travel Document: ZAR 780

OCI & MISCELLANEOUS CONSULAR FEES:
Fresh OCI Card (Adult): As per MEA notification
Fresh OCI Card (Minor): As per MEA notification
OCI Miscellaneous Service: Gratis (free) for qualifying updates
PIO to OCI Conversion: As per MEA notification
Police Clearance Certificate: As per VFS schedule
Attestation of Documents: As per schedule
Birth Registration: Gratis (free)
Non-Impediment Letter: As per schedule
NOC for South African Citizenship: As per schedule
Emergency Travel Document: ZAR 780

ICWF: A fee of Rand 30 is included in all consular, passport and visa services (Gazette of India Notification No. 704 G.S.R. 1027(E) dated 16/08/2017, effective from 01.06.2019).

PAYMENT METHODS:
- EFT (Electronic Funds Transfer) — Original proof of payment required
- Credit Card / Debit Card at VFS Global or the Consulate
- Photocopy, faxed copy or scanned copy of payment proof NOT acceptable

=== 5. VISA SERVICES FOR FOREIGN NATIONALS ===
GENERAL VISA GUIDELINES:
- All foreign nationals, including children, require a visa to enter India.
- Applications submitted online at https://indianvisaonline.gov.in/ — no manual forms accepted.
- South African nationals are issued visas GRATIS (free of charge) to visit India.
- Biometric data is captured at VFS at time of application submission.
- Passport must be valid for a minimum of six months from the date of departure from India.
- Passport must have at least 2 blank pages. Consulate cannot waive this requirement.
- South African nationals holding diplomatic and official passports are exempted from visa for up to 90 days (bilateral agreement).
- The Government of India does not allow Thuraya/Iridium satellite phones in India for security reasons.
- No requirement for HIV/AIDS test for visiting India.

REGULAR VISA — VFS ADDRESS (VISA APPLICATIONS):
Apply Online: https://indianvisaonline.gov.in/visa/index.html
VFS Address: 1st Floor Rivonia Village Office Block, cnr Rivonia Boulevard and Mutual Road, Rivonia, Johannesburg
VFS Phone: 012 425 3007 / 011 484 0327
VFS Email: Info.inza@vfshelpline.com
Biometrics: Mandatory for all regular visa applicants (w.e.f. 17 July 2017)
Important: No visa applications accepted directly at the Consulate. All through VFS only.

VISA TYPES ISSUED: Tourist, Business, Employment, Student, Medical, Research, Journalist, Conference, Transit, Entry (X) Visa, Medical Attendant, Missionary/Religious Worker

Foreigners other than South African Nationals: Foreign nationals from third countries residing in South Africa should contact the Consulate for specific requirements.
Pakistan Nationals and Persons of Pakistan Origin: Special procedures apply. Contact the Consulate directly.

=== 6. E-VISA INFORMATION ===
South African nationals are eligible for e-Visa on a GRATIS basis (no visa fee charged).
Apply online at: https://indianvisaonline.gov.in/evisa/tvoa.html
Apply minimum 5 working days in advance from the date of departure.

E-VISA SUB-CATEGORIES:
e-Tourist Visa: 30 days / 1 year / 5 years — Double/Multiple entry. Tourism, casual visit to meet friends/relatives.
e-Business Visa: 1 year (Multiple entry) — Business-related visits.
e-Medical Visa: 60 days (Triple entry) — For medical treatment in India.
e-Medical Attendant Visa: 60 days (Triple entry) — Max 2 attendants per e-Medical Visa.
e-Conference Visa: 30 days — For attending conferences/seminars. Can club with e-Tourist activities only.

E-VISA RULES:
- e-Visa is linked to specific ports of entry. Must arrive/depart through designated airports/seaports.
- Available for entry through 30+ designated international airports and 5 designated seaports.
- Only two e-Medical Attendant Visas will be granted against one e-Medical Visa.

=== 7. OCI (OVERSEAS CITIZEN OF INDIA) SERVICES ===
The OCI scheme allows persons of Indian origin (other than Pakistan and Bangladesh nationals) to be registered as Overseas Citizens of India. OCI cards provide a multi-purpose, multi-entry life-long visa for India.

ELIGIBILITY:
- A person who was a citizen of India at any time since 26 January 1950 or was eligible to become a citizen of India on 26 January 1950.
- A person who is a citizen of another country but whose parents/grandparents/great-grandparents were citizens of India.
- The spouse of foreign origin of a citizen of India or OCI cardholder (marriage registered and subsisting for not less than 2 years).
- Minor children where both parents are Indian citizens, or one parent is Indian citizen.

OCI APPLICATION PROCEDURE:
- Register online at: https://ociservices.gov.in/
- Submit computer-generated application form (bearing registration number), photo, and signatures.
- For minors: only thumb impression (no signature).
- Two photos: 51mm x 51mm — one pasted on form, one attached separately.
- Submit form with all required documents to the Consulate (appointment required).
- Appointment: Email cons.jburg@mea.gov.in for OCI appointment.

DOCUMENTS REQUIRED (FRESH OCI):
- Proof of present citizenship (current foreign passport)
- Proof of renunciation of Indian citizenship / surrender certificate
- Proof of Indian origin (Indian passport, school certificate, birth certificate, land records)
- For spouse of Indian citizen: marriage certificate and copy of spouse's Indian passport
- Self-attested copy of marriage certificate and copy of foreign passport of spouse (if applicable)
- Proof of residential address in South Africa (utility bill, lease agreement, property papers)
- Proof of payment
- Any other document as specified by the Consular Officer

MISCELLANEOUS OCI SERVICES (RE-ISSUANCE REQUIRED FOR):
- Issuance of new passport (once after completing 20 years of age)
- Change of personal particulars (name, father's name, nationality, etc.)
- Loss or damage of OCI registration certificate
- Gratis services: updating new passport details (each time up to age 20 and once after age 50), change of address/occupation/contact details

IMPORTANT OCI RESTRICTIONS:
- OCI card does NOT entitle holder to undertake missionary work, mountaineering, or research without prior permission from Government of India.
- Fees are not refunded if OCI is not granted.
- Husband and wife must each claim OCI on strength of their own parents/grandparents — not each other.
- Foreign military personnel (serving or retired) of Indian origin are NOT eligible for OCI.
- OCI registration may be cancelled if obtained by fraud or if holder shows disaffection towards the Constitution of India.

PIO TO OCI CONVERSION: PIO card holders should visit https://ociservices.gov.in/ to apply for conversion. PIO card remains valid until its expiry or conversion.

=== 8. POLICE CLEARANCE CERTIFICATE (PCC) ===
PCC is required for immigration, change of nationality, employment abroad, or longer stay in another country.

FOR INDIAN NATIONALS:
- PCC service is outsourced to VFS Global.
- Apply online at: https://portal5.passportindia.gov.in
- Select CGI Johannesburg and submit at VFS Global Johannesburg.
- Applicants in Gauteng, North West, Limpopo and Mpumalanga must apply through CGI Johannesburg.
- VFS Reference: https://www.vfsglobal.com/one-pager/India/SouthAfrica/consular-services/

FOR FOREIGN NATIONALS:
- Foreign nationals requiring PCC from Indian authorities should apply at the nearest Indian Mission/Post.
- Required documents and procedures are available at the VFS Global portal.

=== 9. SERVICES RENDERED AT THE CONSULATE ===
CHILD BIRTH REGISTRATION:
- Registration of children born in South Africa to Indian nationals.
- Required: Birth certificate from South African Home Department and local hospital.
- Service is gratis (free of charge).
- Registered birth certificate used for minor passport applications.

ATTESTATION OF ACADEMIC DEGREES (INDIAN NATIONALS):
- Indian documents must first be apostilled by MEA (Ministry of External Affairs, India).
- MEA Apostille link: http://www.mea.gov.in/apostille.htm

ATTESTATION OF GENERAL POWER OF ATTORNEY (GPA/PoA):
- Original documents and self-attested copies required. Fee as per consular schedule.

ATTESTATION OF DOCUMENTS FOR FOREIGN NATIONALS:
- Foreign nationals requiring attestation of Indian documents for use in South Africa.

EMERGENCY TRAVEL DOCUMENT:
- Issued when a valid Indian passport is not available due to loss/theft/damage.
- Valid for single journey to India only.
- Required: Police report, proof of identity, 2 photographs, proof of travel.
- Fee: ZAR 780 (including ICWF).

NOC FOR CHILD PASSPORT IN INDIA:
- Required when one parent applies for a child's passport in India.
- The other parent (in South Africa) can obtain NOC from the Consulate.
- Required: Passport copies of both parents, child's birth certificate, application form.

NON-IMPEDIMENT LETTER:
- Issued to Indian nationals who wish to marry a foreign national.
- Certifies applicant is not married and is free to marry.
- Required: Indian passport, proof of address, application form.

REGISTRATION OF NRIs/PIOs/OCIs:
- Indian nationals in South Africa are encouraged to register with the Consulate.
- Helps in emergencies, disaster situations, and for consular assistance.

TRANSLATION OF INDIAN DRIVING LICENCE:
- The Consulate provides certified translation of Indian driving licences for use in South Africa.

TRACING THE ROOTS PROGRAMME:
- Programme for persons of Indian origin to trace their ancestral roots in India.
- MEA facilitates visits to villages/districts of origin. Contact the Consulate for details.

OPEN HOUSE TO ADDRESS GRIEVANCES:
- The Consulate periodically holds consular open house sessions.
- Upcoming dates announced on website and social media.
- Applicants can meet Consular Officers and get guidance on pending matters.

ONE AND THE SAME CERTIFICATE:
- Issued when a difference in name spelling exists across documents.
- Self-attested copy of all documents showing name variations required.

=== 10. FREQUENTLY ASKED QUESTIONS (FAQ) ===
Q: How do I apply for a new/renewal/lost/damaged passport?
A: Complete online application at https://embassy.passportindia.gov.in/ and submit at VFS Centre with prior appointment. See: https://www.vfsglobal.com/one-pager/India/SouthAfrica/Passport-services/

Q: What is the timeframe for reissue of passport?
A: Approximately 3-4 weeks, provided all relevant documents are in place and approved by concerned authorities in India.

Q: What is the definition of a damaged passport?
A: Spill over of ink/water mark, scribbling, thread out, torn paper, missing data page, or spine damage.

Q: How can I apply for PCC (Police Clearance Certificate)?
A: PCC service is outsourced to VFS. Apply at https://portal5.passportindia.gov.in. Reference: https://www.vfsglobal.com/one-pager/India/SouthAfrica/consular-services/

Q: How can I get my Indian documents attested?
A: Indian documents must first be apostilled by MEA. See: http://www.mea.gov.in/apostille.htm

Q: My spouse is a foreign national. Is my spouse entitled to an OCI card?
A: Yes, provided the marriage has been registered and subsisted continuously for not less than two years.

Q: Are foreign military personnel of Indian origin eligible for OCI?
A: No. Foreign military personnel, whether in service or retired, are NOT entitled to an OCI card.

Q: What should I do if I find a mistake in my passport?
A: Visit the Consulate immediately and return the passport for rectification. Re-apply for reissue if the error was on your original application form.

Q: What is the difference between minor and major name change?
A: Minor change: spelling discrepancy that does not result in a total phonetic change (e.g., Rakesh vs Rakash). Major change: a complete change of name, or change that is phonetically different.

Q: How do I apply for an emergency visa?
A: Apply online at www.indianvisaonline.gov.in, submit in person at VFS Global Johannesburg with required documents. VFS accepts emergency visa applications on working days and weekends/holidays with prior appointment. Contact: Tel: 012 4253007.

Q: Can a person apply for OCI on the basis of spouse's eligibility?
A: No. Husband and wife must each claim OCI on the strength of their own parents/grandparents.

Q: How do I check the status of my Indian passport or PCC application?
A: Passport: https://www.passportindia.gov.in/AppOnlineProject/welcomeLink | PCC: https://portal5.passportindia.gov.in

=== 11. TRADE & COMMERCE — INDIA–SOUTH AFRICA BILATERAL RELATIONS ===
India and South Africa established diplomatic relations in 1993. Both are members of BRICS and G20.
South Africa population: over 64 million | Area: 1.22 million sq km | Financial capital: Johannesburg.
GDP composition: Services 62.75% | Industry 24.46%. Growth rate (2024): ~1.0%.
Key resources: World's largest producer of platinum, vanadium, chromium, and manganese.
Indian firms have invested approximately USD 10 billion in South Africa.
More than 150 Indian companies operating in South Africa including TATA, Mahindra, Vedanta, Jindal, Cipla, Sun Pharma (Ranbaxy), TCS, WIPRO, Zensar, TechMahindra.
Indian companies employ approximately 18,000 South Africans.
Investment: USD 8–9 billion overall. South Africa seen as platform for broader African engagement via Johannesburg.
Key bilateral sectors: IT, Mining, Infrastructure, Automobiles, Pharmaceuticals, Agriculture, Heavy Machinery.
Double Taxation Avoidance Agreement (DTAA) entered into force on 28 November 1997 (Notification No. GSR 198(E), dated 21-04-1998).
Services for Indian Companies: Trade advisory, business meeting facilitation, partner identification, export/import guidance, exhibition support.
Services for South African Companies: Market entry advisory for India, introduction to Indian counterparts, investment/regulatory information, support for Buyer-Seller Meets (BSM).

=== 12. BANKING DETAILS & TIMINGS ===
Bank Details: Available at https://www.cgijoburg.gov.in/bank-details-and-timings.php
Payment Methods: EFT, Credit Card, Debit Card. Original proof of payment required.
ICWF Fee: ZAR 30 included in all consular/passport/visa fees.
Office Hours: Monday to Friday: 08:30 to 17:00 | Lunch Break: 13:00 to 13:30
VFS Submission: 08:00 to 15:00 | VFS Collection: 11:00 to 16:00
Holidays: https://www.cgijoburg.gov.in/holiday-at-the-consulate-general.php

=== 13. LATEST NEWS & EVENTS (as of April 2026) ===
11 Mar 2026: ACG Mr. Harish Kumar inaugurates the 11th Agritec South Africa with MEC: Agriculture Ms. Vuyiswa Ramokgopa.
27 Jan 2026: India–South Africa A.I. Dialogue brings together 100+ participants in A.I., in preparation for India A.I. Impact Summit.
29 Jan 2026: The Consulate hosts the 77th Republic Day evening reception.
26 Jan 2026: The Post celebrates India's 77th Republic Day with Flag Unfurling at Chancery.
30 Jan 2026: The Post hosts a Hindi Poetry and Costume contest on Vishwa Hindi Diwas.
25 Dec 2025: ACG Mr. Harish Kumar celebrated the spirit of Christmas at St. Thomas Indian Orthodox Church, Midrand.
24 Dec 2025: ACG Mr. Harish Kumar and the Consulate team visited the children of Leratong Joy for One Foundation.
23 Oct 2025: Commercial Representative Shri Harish Kumar addresses Delegates at JCCI Annual Conference 2025.
08 Oct 2025: CG Shri Mahesh Kumar welcomes Shri Harivansh Narayan Singh, Chairman of the Rajya Sabha.
05 Oct 2025: Speaker of Delhi Legislative Assembly, Shri Vijender Gupta, planted a sapling under Ek Ped Maa Ke Naam.
Recent Press Releases: India–South Africa A.I. Dialogue (Jan 2026), Launch of Study in India Portal & e-Student Visa (Sep 2025), Viksit Bharat Run (Sep 2025), All-party Indian Parliamentary delegation visit led by Hon. Ms. Supriya Sule (May 2025), Digitization of Disembarkation Card for Foreign Nationals Visiting India.
Upcoming Notices: Tender for renovation of rooms (Apr 01, 2026), Tender for Security Services (Nov 11, 2025), Tender for Boundary Wall Reconstruction (Nov 01, 2025), Tender for IT Equipment (Sep 19, 2025), 88th Edition of Know India Programme (KIP), 61st IHGF Delhi Fair (Spring 2026), SEPC Buyer-Seller Meet in Johannesburg (09–10 Mar 2026).

=== 14. IMPORTANT LINKS & CONTACTS ===
Consulate Website: www.cgijoburg.gov.in
Passport Application (Online): https://embassy.passportindia.gov.in/
Regular Visa Application: https://indianvisaonline.gov.in/visa/index.html
E-Visa Application: https://indianvisaonline.gov.in/evisa/tvoa.html
OCI Services: https://ociservices.gov.in/
PCC Application: https://portal5.passportindia.gov.in
VFS Global (SA): https://services.vfsglobal.com/zaf/en/ind/
VFS Johannesburg: 2nd Floor, Harrow Court 1, Isle of Houghton, Park Town, JHB — Tel: 012 4253007
MEA Apostille: http://www.mea.gov.in/apostille.htm
Consulate Email: ccom.jburg@mea.gov.in
Consular Services Email: cons.jburg@mea.gov.in
Pravasi Bharatiya Sahayata Kendra: Toll Free (India only): 1800 11 3090 | WhatsApp: +91-7428 3211 44 | helpline@mea.gov.in
Office of Protector General of Emigrants: pge@mea.gov.in | diroe1@mea.gov.in
Passport Status Check: https://www.passportindia.gov.in/AppOnlineProject/welcomeLink
PCC Status Check: https://portal5.passportindia.gov.in
Ministry of External Affairs: www.mea.gov.in
High Commission of India, Pretoria: www.hcipretoria.gov.in
""".strip()


async def scrape_cgi_joburg() -> Dict:
    """
    Returns CGI Joburg knowledge using PDF static content as the primary base,
    then appends any additional live content scraped from the website on top.
    Static PDF (April 2026) is always included — live scrape only adds new info.
    """
    # ── Step 1: Start with the full PDF static content (always reliable) ──
    static_content = _get_cgi_pdf_content()
    logger.info("[SCRAPE] cgijoburg.gov.in — using PDF static content as base")

    # ── Step 2: Attempt live scrape to append any updates ─────────────────
    try:
        all_urls = ["https://www.cgijoburg.gov.in/"] + CGI_SUB_PAGES
        results = await asyncio.gather(
            *[_fetch_page_text(url) for url in all_urls],
            return_exceptions=True
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
            if url == "https://www.cgijoburg.gov.in/":
                contact_html = result

        if combined_parts:
            # Prepend static PDF, then append live content for latest updates
            live_content = "\n\n".join(combined_parts)
            page_content = static_content + "\n\n=== LIVE WEBSITE UPDATE ===\n" + live_content
            live_contact = CONTACT_FALLBACK.copy()
            if contact_html:
                try:
                    soup = BeautifulSoup(contact_html, "html.parser")
                    live_contact = _extract_contact_details(soup)
                except Exception:
                    pass
            logger.info("[SCRAPE] cgijoburg.gov.in — appended %d live page(s) on top of PDF static", pages_ok)
            return {
                "source": "cgijoburg.gov.in (PDF static + live)",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "status": "static_plus_live",
                "pages_crawled": pages_ok,
                "page_content": page_content,
                **live_contact,
            }

    except Exception as e:
        await send_exception_email("CGI Joburg Live Scraping Failed", str(e))
        logger.warning("[SCRAPE] cgijoburg.gov.in live scrape failed: %s — serving PDF static only", e)

    # Live scrape failed or returned nothing — serve static only
    return {
        "source": "cgijoburg.gov.in (PDF static — April 2026)",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "status": "pdf_static",
        "pages_crawled": 0,
        "page_content": static_content,
        **CONTACT_FALLBACK,
    }


async def scrape_vfs_global() -> Dict:
    """
    Scrape VFS Global. The main one-pager URL is JavaScript-rendered (SPA),
    so we also try the static/alternative endpoints for actual content.
    """
    vfs_urls = [
        # Static VFS pages that reliably return 200
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
    """VFS Global information from cgijoburg.gov.in (compiled April 2026)."""
    return """[VFS Global — India Visa & Consular Application Centre, Johannesburg]
Source: www.cgijoburg.gov.in

PASSPORT / PCC / CONSULAR SERVICES (VFS):
Address: 2nd Floor, Harrow Court 1, Isle of Houghton Office Park, Boundary Road, Park Town, Johannesburg - 2198
Telephone: 012 425 3007 / 011 484 0327
Email: Info.inza@vfshelpline.com
Website: https://services.vfsglobal.com/zaf/en/ind/
Submission Hours: 08:00 to 15:00 | Collection Hours: 11:00 to 16:00
Processing Time: Up to one month (passport)

VISA APPLICATIONS (VFS):
Address: 1st Floor Rivonia Village Office Block, cnr Rivonia Boulevard and Mutual Road, Rivonia, Johannesburg
Telephone: 012 425 3007 / 011 484 0327
Email: Info.inza@vfshelpline.com
Biometrics: Mandatory for all regular visa applicants

SERVICES AT VFS:
- Passport submission (reissue on expiry/lost/stolen/damaged/name change/pages exhaustion)
- New passport for minor child born in South Africa
- Visa applications (all types)
- Police Clearance Certificate (PCC)
- Document attestation

VISA FEES (Source: cgijoburg.gov.in):
- South African nationals: GRATIS (free of charge) for all visa types
- South African diplomatic/official passport holders: Exempt from visa up to 90 days
- Other foreign nationals: Contact the Consulate

PASSPORT FEES (Source: cgijoburg.gov.in):
- 36-page passport re-issue: ZAR 2,280 (incl. ICWF ZAR 30)
- 60-page passport re-issue: ZAR 2,655 (incl. ICWF ZAR 30)
- Minor child new passport: ZAR 780
- Emergency Travel Document: ZAR 780

VFS Reference for PCC: https://www.vfsglobal.com/one-pager/India/SouthAfrica/consular-services/
VFS Reference for Passport: https://www.vfsglobal.com/one-pager/India/SouthAfrica/Passport-services/"""


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


async def _fetch_uploaded_docs_content() -> str:
    """
    Fetch all active PDF-uploaded knowledge entries from MongoDB and
    concatenate their text so the scraper cache includes uploaded documents.
    Returns empty string if DB is unavailable.
    """
    try:
        from database import get_database
        db = await get_database()
        cursor = db.knowledge_base.find(
            {"source": {"$regex": "^pdf_upload:"}, "status": "active"},
            {"_id": 0, "title": 1, "answer": 1, "pdf_doc_title": 1}
        ).sort("created_at", -1).limit(200)
        entries = await cursor.to_list(length=200)
        if not entries:
            return ""
        parts = []
        for e in entries:
            doc_title = e.get("pdf_doc_title") or e.get("title", "")
            answer = (e.get("answer") or "").strip()
            if answer:
                parts.append(f"[Uploaded: {doc_title}]\n{answer}")
        logger.info(f"[SCRAPE] Loaded {len(parts)} uploaded-doc sections into scraper cache")
        return "\n\n".join(parts)
    except Exception as exc:
        logger.warning(f"[SCRAPE] Could not load uploaded docs: {exc}")
        return ""


async def _do_scrape() -> Dict:
    """Scrape CGI Joburg (primary source) + VFS (auxiliary) + uploaded docs and return combined knowledge."""
    await _probe_playwright()   # set the flag once before parallel fetches
    cgi_data, vfs_data, uploaded_content = await asyncio.gather(
        scrape_cgi_joburg(),
        scrape_vfs_global(),
        _fetch_uploaded_docs_content(),
    )
    return {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "cgi_joburg": cgi_data,
        "vfs_global": vfs_data,
        "uploaded_docs": {
            "source": "uploaded_documents",
            "page_content": uploaded_content,
        },
        **CONTACT_FALLBACK,
        "official_links": {
            "consulate": "https://www.cgijoburg.gov.in/",
            "passport_application": "https://embassy.passportindia.gov.in/",
            "regular_visa": "https://indianvisaonline.gov.in/visa/index.html",
            "e_visa": "https://indianvisaonline.gov.in/evisa/tvoa.html",
            "oci_services": "https://ociservices.gov.in/",
            "pcc_application": "https://portal5.passportindia.gov.in",
            "vfs_global": "https://services.vfsglobal.com/zaf/en/ind/",
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

    # Return whatever we have right now; use PDF static content if cache is still empty
    if _knowledge_cache is not None:
        return _knowledge_cache
    # Cold start — return PDF static so hybrid_search has page_content immediately
    return {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "source": "cgijoburg.gov.in (PDF static — April 2026)",
        "status": "pdf_static",
        "cgi_joburg": {
            "source": "cgijoburg.gov.in (PDF static — April 2026)",
            "status": "pdf_static",
            "page_content": _get_cgi_pdf_content(),
            **CONTACT_FALLBACK,
        },
        "vfs_global": {
            "source": "vfsglobal.com (fallback)",
            "status": "fallback",
            "page_content": "",
        },
        "uploaded_docs": {
            "source": "uploaded_documents",
            "page_content": "",
        },
        **CONTACT_FALLBACK,
        "official_links": {
            "consulate": "https://www.cgijoburg.gov.in/",
            "passport": "https://embassy.passportindia.gov.in/",
            "visa": "https://indianvisaonline.gov.in/visa/index.html",
            "e_visa": "https://indianvisaonline.gov.in/evisa/tvoa.html",
            "oci_services": "https://ociservices.gov.in/",
            "pcc_application": "https://portal5.passportindia.gov.in",
            "vfs_global": "https://services.vfsglobal.com/zaf/en/ind/",
        },
    }


def invalidate_knowledge_cache():
    """Force the next call to get_realtime_knowledge() to trigger a fresh scrape."""
    global _knowledge_cache_time
    _knowledge_cache_time = None
    logger.info("[SCRAPE] Knowledge cache invalidated — will refresh on next request")


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
    """Comprehensive fallback knowledge base when scraping fails.
    Source: www.cgijoburg.gov.in (compiled April 2026)
    """
    return {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "source": "Fallback - Official Information (www.cgijoburg.gov.in)",
        "emergency_contact": "+27 11 581 9800",
        "email": "ccom.jburg@mea.gov.in",
        "email_consular": "cons.jburg@mea.gov.in",
        "services": {
            "passport": {
                "description": "All passport services processed through VFS Global — not directly at Consulate",
                "apply_online": "https://embassy.passportindia.gov.in/",
                "vfs_address": "2nd Floor, Harrow Court 1, Isle of Houghton Office Park, Boundary Road, Park Town, JHB-2198",
                "vfs_phone": "012 425 3007 / 011 484 0327",
                "submission_hours": "08:00–15:00 | Collection: 11:00–16:00",
                "processing_time": "Up to one month (if all documents are in order)",
                "documents_required": [
                    "Completed online application (embassy.passportindia.gov.in)",
                    "3 passport-sized photos (5cm x 5cm, coloured, white background)",
                    "Original current passport",
                    "Proof of residential address in South Africa",
                    "Original proof of payment (no photocopies)"
                ],
                "fees_zar": "36-page: ZAR 2,280 | 60-page: ZAR 2,655 | Minor child/Emergency: ZAR 780 (all include ICWF ZAR 30)",
                "lost_stolen_extra": "Original FIR/Police Report required for lost/stolen passport"
            },
            "visa": {
                "south_african_nationals": "South African nationals receive Indian visa GRATIS (free of charge)",
                "apply_online": "https://indianvisaonline.gov.in/visa/index.html",
                "vfs_address": "1st Floor, Rivonia Village Office Block, cnr Rivonia Boulevard and Mutual Road, Rivonia, JHB",
                "biometrics": "Mandatory for all regular visa applicants",
                "important": "No visa applications accepted directly at the Consulate — all through VFS only",
                "passport_validity": "Must be valid for minimum 6 months from date of departure from India",
                "blank_pages": "Passport must have at least 2 blank pages",
                "visa_types": "Tourist, Business, Employment, Student, Medical, Research, Journalist, Conference, Transit, Entry (X), Medical Attendant, Missionary/Religious Worker",
                "e_visa_apply": "https://indianvisaonline.gov.in/evisa/tvoa.html",
                "e_visa_note": "Apply minimum 5 working days before departure; available at 30+ airports and 5 seaports"
            },
            "oci": {
                "description": "Multi-purpose, multi-entry, life-long visa for persons of Indian origin",
                "apply_online": "https://ociservices.gov.in/",
                "submit_to": "Consulate General of India, Johannesburg (appointment required)",
                "appointment": "Email cons.jburg@mea.gov.in for OCI appointment",
                "eligibility": "Indian citizen since 26 Jan 1950, or parent/grandparent/great-grandparent was Indian citizen, or spouse of Indian citizen/OCI holder (married ≥2 years)",
                "not_eligible": "Pakistan/Bangladesh nationals; foreign military personnel (serving or retired)",
                "fees_zar": "As per MEA notification — contact Consulate for current rates",
                "documents_required": [
                    "Proof of present citizenship (current foreign passport)",
                    "Proof of renunciation of Indian citizenship / surrender certificate",
                    "Proof of Indian origin (old Indian passport, birth certificate, school certificate)",
                    "Proof of residential address in SA",
                    "2 photos (51mm x 51mm)"
                ]
            },
            "pcc": {
                "description": "Police Clearance Certificate — required for immigration, change of nationality, employment abroad",
                "apply_online": "https://portal5.passportindia.gov.in",
                "submit_to": "VFS Global Johannesburg (select CGI Johannesburg)",
                "vfs_address": "2nd Floor, Harrow Court 1, Isle of Houghton Office Park, Boundary Road, Park Town, JHB-2198",
                "jurisdiction": "Gauteng, North West, Limpopo and Mpumalanga must apply through CGI Johannesburg"
            },
            "attestation": {
                "description": "Attestation of academic degrees, GPA/PoA, and documents for Indian and foreign nationals",
                "indian_documents": "Indian documents must first be apostilled by MEA India — http://www.mea.gov.in/apostille.htm",
                "gpa_poa": "Original documents and self-attested copies required",
                "fees_zar": "As per consular schedule"
            },
            "birth_registration": {
                "description": "Registration of births of children born in South Africa to Indian nationals",
                "fee": "Gratis (free of charge)",
                "documents_required": [
                    "Birth certificate from South African Home Department",
                    "Birth certificate from local hospital",
                    "Indian passport(s) of parent(s)"
                ]
            },
            "emergency_travel": {
                "description": "Emergency Travel Document for single journey to India when passport is lost/stolen/damaged",
                "fees_zar": "ZAR 780 (includes ICWF)",
                "documents_required": [
                    "Police report (FIR) if lost or stolen",
                    "Proof of identity",
                    "2 photographs",
                    "Proof of travel booking"
                ]
            },
            "noc_sa_citizenship": {
                "description": "NOC (No Objection Certificate) for Indian nationals who wish to acquire South African citizenship",
                "submit_to": "Consulate General of India, Johannesburg",
                "documents_required": [
                    "Indian passport (original + copies of all pages)",
                    "Application form",
                    "Proof of residential address in South Africa",
                    "Any supporting document required by the Consulate"
                ],
                "fees_zar": "As per consular schedule"
            },
            "noc_child_passport": {
                "description": "NOC for child passport in India — required when one parent (in South Africa) is not present at the passport office in India",
                "submit_to": "Consulate General of India, Johannesburg",
                "documents_required": [
                    "Passport copies of both parents",
                    "Child's birth certificate",
                    "Application form"
                ],
                "fees_zar": "As per consular schedule"
            },
            "non_impediment_letter": {
                "description": "Non-Impediment Letter issued to Indian nationals who wish to marry a foreign national. Certifies that the applicant is not married and is free to marry.",
                "submit_to": "Consulate General of India, Johannesburg",
                "documents_required": [
                    "Indian passport (original + photocopy)",
                    "Proof of residential address in South Africa",
                    "Application form"
                ],
                "fees_zar": "As per consular schedule"
            },
            "one_and_same_certificate": {
                "description": "One and the Same Certificate issued when a difference in name spelling exists across documents",
                "submit_to": "Consulate General of India, Johannesburg",
                "documents_required": [
                    "Self-attested copies of all documents showing name variations"
                ],
                "fees_zar": "As per consular schedule"
            },
            "driving_licence_translation": {
                "description": "Certified translation of Indian driving licence for use in South Africa",
                "submit_to": "Consulate General of India, Johannesburg",
                "documents_required": [
                    "Original Indian driving licence",
                    "Photocopy of driving licence",
                    "Indian passport (original + copy)"
                ],
                "fees_zar": "As per consular schedule"
            },
            "nri_registration": {
                "description": "Registration of NRIs/PIOs/OCIs residing in South Africa with the Consulate. Helps in emergencies, disaster situations, and for consular assistance.",
                "how_to": "Contact the Consulate at ccom.jburg@mea.gov.in or visit in person",
                "fee": "No fee mentioned — contact Consulate for current procedure"
            },
            "tracing_roots": {
                "description": "Programme for persons of Indian origin to trace their ancestral roots in India. MEA facilitates visits to villages/districts of origin.",
                "contact": "Consulate General of India, Johannesburg — ccom.jburg@mea.gov.in"
            },
            # Keys matching _SERVICE_KEYWORDS for direct fallback lookup
            "noc": {
                "description": "NOC (No Objection Certificate) services — for South African citizenship acquisition OR for child passport application in India",
                "noc_sa_citizenship": "NOC for Indian nationals acquiring South African citizenship. Submit application with Indian passport copies and proof of address.",
                "noc_child_passport": "NOC for child passport in India when one parent is in South Africa. Required: both parents' passport copies, child's birth certificate.",
                "submit_to": "Consulate General of India, Johannesburg",
                "contact": "+27 11-4828484 | ccom.jburg@mea.gov.in",
                "fees_zar": "As per consular schedule"
            },
            "non_impediment": {
                "description": "Non-Impediment Letter issued to Indian nationals who wish to marry a foreign national. Certifies applicant is not currently married and is free to marry.",
                "documents_required": [
                    "Indian passport (original + photocopy of all pages)",
                    "Proof of residential address in South Africa",
                    "Application form"
                ],
                "submit_to": "Consulate General of India, Johannesburg",
                "contact": "+27 11-4828484 | ccom.jburg@mea.gov.in",
                "fees_zar": "As per consular schedule"
            },
            "one_same": {
                "description": "One and the Same Certificate issued when a difference in name spelling exists across documents (e.g. passport vs degree certificate).",
                "documents_required": [
                    "Self-attested copies of all documents showing name variations"
                ],
                "submit_to": "Consulate General of India, Johannesburg",
                "fees_zar": "As per consular schedule"
            },
            "driving": {
                "description": "Certified translation of Indian driving licence for use in South Africa. Provided by the Consulate General.",
                "documents_required": [
                    "Original Indian driving licence",
                    "Photocopy of driving licence",
                    "Indian passport (original + photocopy)"
                ],
                "submit_to": "Consulate General of India, Johannesburg",
                "fees_zar": "As per consular schedule"
            },
            "nri": {
                "description": "Registration of NRIs/PIOs/OCIs residing in South Africa. Helps in emergencies and for consular assistance.",
                "how_to": "Contact the Consulate at ccom.jburg@mea.gov.in or visit in person during office hours.",
                "office_hours": "Mon–Fri 08:30–17:00 (Lunch: 13:00–13:30)",
                "contact": "+27 11-4828484 | ccom.jburg@mea.gov.in"
            },
            "tracing": {
                "description": "Tracing the Roots Programme for persons of Indian origin to trace their ancestral roots in India. MEA facilitates visits to villages/districts of origin.",
                "contact": "Consulate General of India, Johannesburg — ccom.jburg@mea.gov.in | +27 11-4828484"
            },
            "trade": {
                "description": "India–South Africa bilateral trade and commerce. Diplomatic relations established in 1993. Both members of BRICS and G20.",
                "stats": "150+ Indian companies in SA | USD 10 billion investment | ~18,000 South Africans employed | Key sectors: IT, Mining, Autos, Pharma, Agriculture",
                "major_companies": "TATA, Mahindra, Vedanta, Jindal, Cipla, Sun Pharma, TCS, WIPRO, Zensar, TechMahindra",
                "dtaa": "Double Taxation Avoidance Agreement in force since 28 November 1997",
                "services_for_indian_cos": "Trade advisory, business meetings, partner identification, export/import guidance, exhibition support",
                "services_for_sa_cos": "Market entry advisory for India, introduction to Indian counterparts, BSM support",
                "contact": "Commercial Wing, CGI Johannesburg — ccom.jburg@mea.gov.in | +27 11-4828484"
            },
            "emergency_contact": {
                "description": "Emergency consular assistance for Indian nationals in distress in South Africa (Gauteng, North West, Limpopo, Mpumalanga).",
                "emergency_phone": "+27 11 581 9800 (24/7 emergency)",
                "main_phone": "+27 11-4828484 / +27 11-4828485 / +27 11-4828486",
                "email": "ccom.jburg@mea.gov.in",
                "consular_email": "cons.jburg@mea.gov.in",
                "pravasi_helpline": "Toll Free (India only): 1800 11 3090 | WhatsApp: +91-7428 3211 44 | helpline@mea.gov.in",
                "address": "No. 1, Eton Road (Corner Jan Smuts Avenue & Eton Road), Park Town 2193, Johannesburg"
            }
        },
        "trade_commerce": {
            "overview": "India–South Africa diplomatic relations established in 1993. Both members of BRICS and G20.",
            "south_africa_stats": "Population: 64 million+ | Area: 1.22 million sq km | Financial capital: Johannesburg",
            "gdp": "Services: 62.75% | Industry: 24.46% | Growth rate (2024): ~1.0%",
            "key_resources": "World's largest producer of platinum, vanadium, chromium, and manganese",
            "indian_investment": "USD 10 billion invested in South Africa | 150+ Indian companies | ~18,000 South Africans employed",
            "major_indian_companies": "TATA, Mahindra, Vedanta, Jindal, Cipla, Sun Pharma (Ranbaxy), TCS, WIPRO, Zensar, TechMahindra",
            "bilateral_sectors": "IT, Mining, Infrastructure, Automobiles, Pharmaceuticals, Agriculture, Heavy Machinery",
            "dtaa": "Double Taxation Avoidance Agreement in force since 28 November 1997 (Notification No. GSR 198(E), dated 21-04-1998)",
            "services_for_indian_companies": "Trade advisory, business meeting facilitation, partner identification, import/export guidance, exhibition support",
            "services_for_sa_companies": "Market entry advisory for India, introduction to Indian counterparts, investment/regulatory information, BSM support"
        },
        "vfs_locations": {
            "johannesburg_passport": {
                "address": "2nd Floor, Harrow Court 1, Isle of Houghton Office Park, Boundary Road, Park Town, JHB-2198",
                "timings": "Submission: 08:00–15:00 | Collection: 11:00–16:00",
                "phone": "012 425 3007 / 011 484 0327",
                "email": "Info.inza@vfshelpline.com"
            },
            "johannesburg_visa": {
                "address": "1st Floor, Rivonia Village Office Block, cnr Rivonia Boulevard and Mutual Road, Rivonia, JHB",
                "phone": "012 425 3007 / 011 484 0327"
            }
        },
        "official_links": {
            "consulate": "https://www.cgijoburg.gov.in/",
            "passport_application": "https://embassy.passportindia.gov.in/",
            "regular_visa": "https://indianvisaonline.gov.in/visa/index.html",
            "e_visa": "https://indianvisaonline.gov.in/evisa/tvoa.html",
            "oci_services": "https://ociservices.gov.in/",
            "pcc_application": "https://portal5.passportindia.gov.in",
            "vfs_global": "https://services.vfsglobal.com/zaf/en/ind/",
            "mea_apostille": "http://www.mea.gov.in/apostille.htm",
            "passport_status": "https://www.passportindia.gov.in/AppOnlineProject/welcomeLink"
        }
    }


_SERVICE_KEYWORDS = {
    "visa":        ["visa", "vfs", "e-visa", "tourist", "business visa", "application fee", "indianvisaonline",
                    "e_visa", "evisa", "visa fee", "visa fees", "visa cost", "visa price", "visa charges",
                    "visa application", "how much visa", "tourist fee", "business fee"],
    "passport":    ["passport", "renewal", "tatkal", "passportindia", "fresh passport", "travel document",
                    "passport seva", "passport fee", "passport fees", "passport cost", "passport charges",
                    "how much passport", "lost passport", "stolen passport", "damaged passport",
                    "lost", "stolen", "damaged", "reissue", "re-issue", "fir", "police report",
                    "emergency travel", "emergency document"],
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
    "noc":         ["noc", "no objection", "no objection certificate", "south african citizenship",
                    "child passport india", "noc child", "noc citizenship"],
    "non_impediment": ["non-impediment", "non impediment", "impediment", "free to marry", "marriage letter",
                       "marry abroad", "marriage abroad"],
    "one_same":    ["one and the same", "same certificate", "name spelling", "name difference",
                    "name variation", "name discrepancy"],
    "driving":     ["driving licence", "driving license", "drive", "licence translation",
                    "indian driving", "translate licence"],
    "nri":         ["nri", "nri registration", "register nri", "registration", "register with consulate",
                    "indian national registration", "pio registration", "oci registration"],
    "tracing":     ["tracing roots", "trace roots", "ancestral", "roots in india", "indian origin village",
                    "know india", "kip programme"],
    "trade":       ["trade", "commerce", "investment", "business india", "india south africa trade",
                    "brics", "dtaa", "double taxation", "bilateral", "indian companies",
                    "business meeting", "buyer seller", "bsm"],
    "emergency_contact": ["emergency", "distress", "stranded", "arrested", "hospital", "accident",
                          "urgent help", "crisis", "indians in distress", "helpline"],
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

# Flow-control words that are never knowledge queries — skip deep scan entirely
_NO_CRAWL_WORDS = {
    "yes", "yep", "yeah", "nope", "okay", "sure",
    "apply", "start", "begin", "register", "proceed", "confirm",
    "cancel", "stop", "exit", "quit", "back", "next", "done",
    "hello", "hi", "hey", "thanks", "thank", "bye", "goodbye",
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
    Background task: crawl the CGI homepage + relevant sub-pages for the given
    keywords and store results in _deep_scan_cache. Never called on the hot path.
    """
    logger.info(f"[SCAN L2 BG] Starting background deep crawl for '{cache_key}'")
    deep_content = ""
    try:
        homepage_url  = "https://www.cgijoburg.gov.in/"
        homepage_html = await _fetch_with_retry(homepage_url)

        # Extract content from the homepage itself (not just use it for link discovery)
        homepage_lines = _clean_html_text(homepage_html)
        homepage_text  = "\n".join(homepage_lines[:150])

        relevant_urls = _discover_relevant_links(homepage_html, homepage_url, keywords)
        # Add known sub-pages whose path matches a keyword
        for sub in CGI_SUB_PAGES:
            path = urlparse(sub).path.lower()
            if any(k in path for k in keywords) and sub not in relevant_urls:
                relevant_urls.append(sub)

        # Fetch sub-pages in parallel
        page_parts = []

        # Include homepage content first if it has keyword matches
        homepage_matched = _extract_matching_lines(keywords, homepage_text, max_lines=20)
        if homepage_matched:
            page_parts.append("[cgijoburg.gov.in — homepage]\n" + "\n".join(homepage_matched))

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

_CGI_CRAWL_INTERVAL_SECONDS = 6 * 3600   # re-crawl every 6 hours
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


async def _do_cgi_full_crawl():
    """
    Crawl https://www.cgijoburg.gov.in/ and all known sub-pages.
    Store full page text into MongoDB so hybrid_search Layer 1 benefits
    from up-to-date live content on the next query.
    """
    global _cgi_crawl_running
    if _cgi_crawl_running:
        logger.debug("[BGCrawl] Full CGI crawl already in progress — skipping")
        return
    _cgi_crawl_running = True
    try:
        all_urls = ["https://www.cgijoburg.gov.in/"] + list(CGI_SUB_PAGES)
        logger.info(f"[BGCrawl] Starting full CGI crawl ({len(all_urls)} URLs)")

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


async def start_periodic_cgi_crawl():
    """
    Periodic loop: crawl all CGI pages and store to MongoDB every
    _CGI_CRAWL_INTERVAL_SECONDS (default 6 hours).
    Runs one immediate crawl at startup, then loops.
    Call once at server startup via asyncio.create_task().
    """
    logger.info(f"[BGCrawl] Periodic CGI crawl started (interval: {_CGI_CRAWL_INTERVAL_SECONDS // 3600}h)")
    while True:
        await _do_cgi_full_crawl()
        await asyncio.sleep(_CGI_CRAWL_INTERVAL_SECONDS)


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
    if hits >= _HIT_THRESHOLD:
        logger.debug(f"[SCAN L1] '{cache_key}' — {hits} hits, returning from cache")
        # Include the original query phrase as an extra keyword so compound terms
        # like "lost passport" score higher than single-keyword lines
        phrase_kws = keywords + ([query.lower().strip()] if len(keywords) > 1 else [])
        cgi_lines = _extract_matching_lines(phrase_kws, cgi_content)
        vfs_lines = _extract_matching_lines(phrase_kws, vfs_content)
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
        f"CONTACT & LOCATION (Source: www.cgijoburg.gov.in):\n"
        f"- Phone: {CONTACT_FALLBACK['phone_main']} / {CONTACT_FALLBACK['phone_consular']}\n"
        f"- Email: {CONTACT_FALLBACK['email']} | Consular: {CONTACT_FALLBACK['email_consular']}\n"
        f"- Address: {CONTACT_FALLBACK['address']}\n"
        f"- Office Hours: {CONTACT_FALLBACK['office_hours']}\n"
        f"- VFS (Passport/PCC): {CONTACT_FALLBACK['vfs_address']}\n"
        f"- VFS Phone: {CONTACT_FALLBACK['vfs_phone']} | Email: {CONTACT_FALLBACK['vfs_email']}\n"
        f"- VFS Hours: {CONTACT_FALLBACK['vfs_hours']}\n"
        f"- Consulate Website: {CONTACT_FALLBACK['website']}"
    )

    keywords = _extract_keywords(query)
    # Include the original query phrase so compound terms rank above single-keyword lines
    phrase_kws = keywords + ([query.lower().strip()] if len(keywords) > 1 else [])
    scraped_at = cgi.get("scraped_at") or knowledge_base.get("last_updated", "")
    sections = [contact_block]
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
