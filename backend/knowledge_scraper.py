import httpx
from bs4 import BeautifulSoup
import json
from typing import List, Dict, Optional
import asyncio
from datetime import datetime, timezone
import hashlib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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
    """Fetch a URL, retrying once on failure. Returns HTML text or None."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; SevaSetuBot/1.0)"}
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, verify=False) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    return response.text
                raise Exception(f"HTTP {response.status_code}")
        except Exception as e:
            if attempt < retries - 1:
                await asyncio.sleep(2)
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

async def get_realtime_knowledge() -> Dict:
    """Fetch real-time information from both official websites concurrently with retry."""
    try:
        cgi_data, vfs_data = await asyncio.gather(
            scrape_cgi_joburg(),
            scrape_vfs_global()
        )

        combined_data = {
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "cgi_joburg": cgi_data,
            "vfs_global": vfs_data,
            **CONTACT_FALLBACK,
            "official_links": {
                "consulate": "https://www.cgijoburg.gov.in/",
                "vfs": "https://visa.vfsglobal.com/one-pager/india/south-africa/johannesburg/",
                "passport_seva": "https://portal2.passportindia.gov.in/",
                "e_visa": "https://indianvisaonline.gov.in/"
            }
        }

        await log_knowledge_changes(combined_data)
        return combined_data
    except Exception as e:
        await send_exception_email("Real-time Knowledge Fetch Failed", str(e))
        return get_fallback_knowledge()

async def log_knowledge_changes(new_data: Dict):
    """Log changes in scraped data"""
    log_file = "/app/logs/knowledge_changes.log"
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    try:
        # Calculate hash of new data
        new_hash = hashlib.md5(json.dumps(new_data, sort_keys=True).encode()).hexdigest()
        
        # Read previous hash if exists
        hash_file = "/app/logs/last_knowledge_hash.txt"
        previous_hash = None
        if os.path.exists(hash_file):
            with open(hash_file, 'r') as f:
                previous_hash = f.read().strip()
        
        # If data changed, log it
        if previous_hash != new_hash:
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "previous_hash": previous_hash,
                "new_hash": new_hash,
                "change_detected": True,
                "data_snapshot": new_data
            }
            
            with open(log_file, 'a') as f:
                f.write(json.dumps(log_entry) + "\n")
            
            # Save new hash
            with open(hash_file, 'w') as f:
                f.write(new_hash)
            
            # Send notification email about changes
            await send_change_notification(log_entry)
    except Exception as e:
        print(f"Error logging changes: {e}")

async def send_exception_email(subject: str, error_details: str):
    """Send exception report to mayurakole"""
    try:
        msg = MIMEMultipart()
        msg['From'] = "sevasetu-bot@consulate.gov.in"
        msg['To'] = "mayurakole@example.com"
        msg['Subject'] = f"[Seva Setu Bot] Exception: {subject}"
        
        body = f"""
        Seva Setu Bot Exception Report
        ================================
        
        Timestamp: {datetime.now(timezone.utc).isoformat()}
        Subject: {subject}
        
        Error Details:
        {error_details}
        
        System: Consulate General of India Johannesburg
        Bot: Seva Setu
        
        This is an automated alert from the consular bot system.
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Log to file instead of actual email (for demo)
        log_file = "/app/logs/exception_emails.log"
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        with open(log_file, 'a') as f:
            f.write(f"\n{'='*50}\n")
            f.write(f"TO: mayurakole@example.com\n")
            f.write(f"SUBJECT: {subject}\n")
            f.write(f"BODY:\n{body}\n")
        
        print(f"Exception email logged: {subject}")
    except Exception as e:
        print(f"Failed to send exception email: {e}")

async def send_change_notification(change_log: Dict):
    """Send notification when website content changes"""
    try:
        subject = "Website Content Change Detected"
        body = f"""
        Seva Setu Bot Change Notification
        ==================================
        
        A change has been detected in the official consulate website content.
        
        Timestamp: {change_log['timestamp']}
        Previous Hash: {change_log['previous_hash']}
        New Hash: {change_log['new_hash']}
        
        The knowledge base has been updated with the latest information.
        Please review the changes in /app/logs/knowledge_changes.log
        
        This is an automated notification from Seva Setu Bot.
        """
        
        await send_exception_email(subject, body)
    except Exception as e:
        print(f"Failed to send change notification: {e}")

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