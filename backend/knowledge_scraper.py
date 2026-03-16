import httpx
from bs4 import BeautifulSoup
import json
from typing import List, Dict, Optional
import asyncio
from datetime import datetime, timezone
import hashlib
import os

OFFICIAL_SOURCES = [
    "https://www.cgijoburg.gov.in/",
    "https://visa.vfsglobal.com/one-pager/india/south-africa/johannesburg/"
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


async def _fetch_with_retry(url: str, retries: int = 2) -> Optional[str]:
    """Fetch a URL, retrying once on transient failure. Returns HTML text or None."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=True, verify=False) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    return response.text
                # 403/404/5xx — no point retrying with same request
                raise Exception(f"HTTP {response.status_code}")
        except Exception as e:
            err = str(e)
            # Don't retry permanent blocks (403, 404, SSL errors)
            if attempt < retries - 1 and "HTTP 4" not in err and "HTTP 5" not in err:
                await asyncio.sleep(0.5)
            else:
                raise


async def scrape_cgi_joburg() -> Dict:
    """Scrape Consulate General of India Johannesburg website with retry."""
    try:
        html = await _fetch_with_retry("https://www.cgijoburg.gov.in/")
        soup = BeautifulSoup(html, "html.parser")

        # Extract visible text paragraphs
        texts = [p.get_text(separator=" ", strip=True) for p in soup.find_all(["p", "li", "h1", "h2", "h3"]) if p.get_text(strip=True)]
        page_content = "\n".join(texts[:80])  # limit to first 80 elements

        return {
            "source": "cgijoburg.gov.in",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "status": "live_scraped",
            "page_content": page_content,
            **CONTACT_FALLBACK,
        }
    except Exception as e:
        await send_exception_email("CGI Joburg Scraping Failed", str(e))
        return {"source": "cgijoburg.gov.in", "status": "failed", "page_content": "", **CONTACT_FALLBACK}


async def scrape_vfs_global() -> Dict:
    """Scrape VFS Global website with retry."""
    try:
        html = await _fetch_with_retry("https://visa.vfsglobal.com/one-pager/india/south-africa/johannesburg/")
        soup = BeautifulSoup(html, "html.parser")

        texts = [p.get_text(separator=" ", strip=True) for p in soup.find_all(["p", "li", "h1", "h2", "h3"]) if p.get_text(strip=True)]
        page_content = "\n".join(texts[:80])

        return {
            "source": "VFS Global",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "status": "live_scraped",
            "page_content": page_content,
            **CONTACT_FALLBACK,
        }
    except Exception as e:
        await send_exception_email("VFS Global Scraping Failed", str(e))
        return {"source": "VFS Global", "status": "failed", "page_content": "", **CONTACT_FALLBACK}

_knowledge_cache: Optional[Dict] = None
_knowledge_cache_time: Optional[datetime] = None
_scrape_in_progress: bool = False
_CACHE_TTL_SECONDS = 1800  # 30 minutes


async def _do_scrape() -> Dict:
    """Run both scrapers concurrently and return combined knowledge."""
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
    """Return cached knowledge immediately. Trigger background refresh when cache is stale."""
    global _knowledge_cache, _knowledge_cache_time

    now = datetime.now(timezone.utc)
    cache_stale = (
        _knowledge_cache is None
        or _knowledge_cache_time is None
        or (now - _knowledge_cache_time).total_seconds() >= _CACHE_TTL_SECONDS
    )

    if cache_stale and not _scrape_in_progress:
        # Fire-and-forget — don't await, so the request is never blocked by scraping
        asyncio.create_task(_refresh_cache_background())

    # Return cache immediately (may be stale on first request — falls back below)
    if _knowledge_cache is not None:
        return _knowledge_cache

    # Absolute first startup — wait for the scrape just this once (no cache at all)
    try:
        data = await _do_scrape()
        await log_knowledge_changes(data)
        _knowledge_cache = data
        _knowledge_cache_time = now
        return data
    except Exception as e:
        await send_exception_email("Real-time Knowledge Fetch Failed", str(e))
        return get_fallback_knowledge()

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
    """Log exception to local file (email not configured in dev)."""
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
    """Fallback knowledge base when scraping fails"""
    return {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "source": "Fallback - Official Information (cached)",
        "emergency_contact": "+27 6830 38144",
        "email": "cons.joburg@mea.gov.in",
        "services": {
            "passport": {
                "new_passport": "Apply online at passportindia.gov.in, submit documents at VFS Johannesburg",
                "renewal": "Online application required, valid for 10 years for adults",
                "documents_required": [
                    "Online application receipt",
                    "Current passport (for renewal)",
                    "Proof of residence in South Africa",
                    "Photographs as per specifications"
                ]
            },
            "visa": {
                "tourist_visa": "Apply at VFS Global Johannesburg",
                "business_visa": "Letter from SA company + invitation from Indian company required",
                "e_visa": "Available online at indianvisaonline.gov.in",
                "processing_time": "7-10 working days (standard)"
            },
            "oci": {
                "description": "Overseas Citizen of India card for eligible persons",
                "eligibility": "Person of Indian Origin, spouse of Indian citizen",
                "application": "Apply online, submit at VFS Johannesburg",
                "validity": "Lifelong (re-issue required at age 20 and 50)"
            }
        },
        "vfs_locations": {
            "johannesburg": {
                "address": "VFS Global, Johannesburg",
                "timings": "Monday-Friday: 08:00-15:00",
                "appointment": "Book online at visa.vfsglobal.com"
            }
        },
        "official_links": {
            "consulate": "https://www.cgijoburg.gov.in/",
            "vfs": "https://visa.vfsglobal.com/one-pager/india/south-africa/johannesburg/",
            "passport_seva": "https://portal2.passportindia.gov.in/",
            "e_visa": "https://indianvisaonline.gov.in/"
        }
    }

def get_fallback_vfs_info() -> Dict:
    return {
        "source": "VFS Global (cached)",
        "location": {
            "address": "VFS Global, Johannesburg",
            "timings": "Monday-Friday: 08:00-15:00"
        }
    }

_SERVICE_KEYWORDS = {
    "visa":        ["visa", "vfs", "e-visa", "tourist", "business visa", "application fee", "indianvisaonline"],
    "passport":    ["passport", "renewal", "tatkal", "passportindia", "fresh passport", "travel document"],
    "oci":         ["oci", "overseas citizen", "lifelong visa", "oci card", "person of indian origin"],
    "pcc":         ["pcc", "police clearance", "clearance certificate", "criminal record"],
    "marriage":    ["marriage", "matrimonial", "spouse", "wedding", "nikah", "marry"],
    "birth":       ["birth", "born", "newborn", "child registration", "birth certificate"],
    "attestation": ["attestation", "apostille", "notary", "affidavit", "power of attorney", "legalization"],
    "renunciation":["renunciation", "renounce", "surrender passport", "citizenship"],
}


def extract_service_content(service_key: str, knowledge_base: Dict) -> str:
    """Return service-specific lines extracted from scraped website content.
    Falls back to structured data from the fallback knowledge base."""
    kws = _SERVICE_KEYWORDS.get(service_key, [])

    # Try live scraped pages first
    cgi_content = knowledge_base.get("cgi_joburg", {}).get("page_content", "")
    vfs_content = knowledge_base.get("vfs_global", {}).get("page_content", "")

    parts = []
    for source, content in [("CGI Johannesburg website", cgi_content), ("VFS Global website", vfs_content)]:
        if not content:
            continue
        lines = [l.strip() for l in content.split("\n") if l.strip()]
        relevant = [l for l in lines if any(k in l.lower() for k in kws)]
        if relevant:
            parts.append(f"From {source}:\n" + "\n".join(relevant[:12]))

    if parts:
        return "\n\n".join(parts)

    # Websites blocked — use fallback structured data
    fallback = get_fallback_knowledge()
    svc_data = fallback.get("services", {}).get(service_key)
    if not svc_data:
        return ""

    lines = []
    for k, v in svc_data.items():
        if isinstance(v, list):
            lines.append(f"{k.replace('_', ' ').title()}: " + ", ".join(v))
        else:
            lines.append(f"{k.replace('_', ' ').title()}: {v}")
    return "From official knowledge base (live websites temporarily unavailable):\n" + "\n".join(lines)


def search_knowledge(query: str, knowledge_base: Dict) -> str:
    """Return all scraped website content plus contact info as context for the LLM."""
    cgi = knowledge_base.get("cgi_joburg", {})
    vfs = knowledge_base.get("vfs_global", {})

    cgi_content = cgi.get("page_content", "").strip()
    vfs_content = vfs.get("page_content", "").strip()

    cgi_status = cgi.get("status", "unknown")
    vfs_status = vfs.get("status", "unknown")

    contact_block = f"""
CONTACT & ADDRESS (always show if information not found):
- Phone: {CONTACT_FALLBACK['emergency_contact']}
- Email: {CONTACT_FALLBACK['email']}
- Address: {CONTACT_FALLBACK['address']}
- Office hours: {CONTACT_FALLBACK['office_hours']}
- VFS address: {CONTACT_FALLBACK['vfs_address']}
- VFS hours: {CONTACT_FALLBACK['vfs_hours']}
- Website: {CONTACT_FALLBACK['website']}
- VFS website: {CONTACT_FALLBACK['vfs_website']}
""".strip()

    sections = [contact_block]

    if cgi_content:
        sections.append(f"=== CGI JOHANNESBURG WEBSITE (live) ===\n{cgi_content}")
    else:
        sections.append(f"=== CGI JOHANNESBURG WEBSITE: scraping failed ({cgi_status}) ===")

    if vfs_content:
        sections.append(f"=== VFS GLOBAL WEBSITE (live) ===\n{vfs_content}")
    else:
        sections.append(f"=== VFS GLOBAL WEBSITE: scraping failed ({vfs_status}) ===")

    return "\n\n".join(sections)