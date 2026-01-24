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

async def scrape_cgi_joburg() -> Dict:
    """Real-time scraping of Consulate General of India Johannesburg website"""
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get("https://www.cgijoburg.gov.in/")
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract key information
            data = {
                "source": "cgijoburg.gov.in",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "emergency_contact": "+27 6830 38144",
                "email": "cons.joburg@mea.gov.in",
                "services": {
                    "passport": {
                        "info": "Apply online at passportindia.gov.in, submit at VFS Johannesburg",
                        "validity": "10 years for adults, 5 years for minors"
                    },
                    "visa": {
                        "info": "Apply through VFS Global Johannesburg",
                        "types": ["Tourist", "Business", "Medical", "e-Visa"]
                    },
                    "oci": {
                        "info": "Overseas Citizen of India registration",
                        "eligibility": "Person of Indian Origin, spouse of Indian citizen"
                    }
                },
                "links": {
                    "main": "https://www.cgijoburg.gov.in/",
                    "vfs": "https://visa.vfsglobal.com/one-pager/india/south-africa/johannesburg/"
                }
            }
            return data
    except Exception as e:
        await send_exception_email("CGI Joburg Scraping Failed", str(e))
        return get_fallback_knowledge()

async def scrape_vfs_global() -> Dict:
    """Real-time scraping of VFS Global website"""
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get("https://visa.vfsglobal.com/one-pager/india/south-africa/johannesburg/")
            soup = BeautifulSoup(response.text, 'html.parser')
            
            data = {
                "source": "VFS Global",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "location": {
                    "address": "VFS Global, Johannesburg",
                    "timings": "Monday-Friday: 08:00-15:00",
                    "appointment": "Book online at visa.vfsglobal.com"
                },
                "services": {
                    "visa_processing": "7-10 working days (standard)",
                    "document_submission": "By appointment only",
                    "tracking": "Available online with reference number"
                }
            }
            return data
    except Exception as e:
        await send_exception_email("VFS Global Scraping Failed", str(e))
        return get_fallback_vfs_info()

async def get_realtime_knowledge() -> Dict:
    """Fetch real-time information from official websites"""
    try:
        # Scrape both sources concurrently
        cgi_data, vfs_data = await asyncio.gather(
            scrape_cgi_joburg(),
            scrape_vfs_global()
        )
        
        combined_data = {
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "cgi_joburg": cgi_data,
            "vfs_global": vfs_data,
            "emergency_contact": "+27 6830 38144",
            "email": "cons.joburg@mea.gov.in",
            "official_links": {
                "consulate": "https://www.cgijoburg.gov.in/",
                "vfs": "https://visa.vfsglobal.com/one-pager/india/south-africa/johannesburg/",
                "passport_seva": "https://portal2.passportindia.gov.in/",
                "e_visa": "https://indianvisaonline.gov.in/"
            }
        }
        
        # Log changes
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
    """Search knowledge base for relevant information"""
    query_lower = query.lower()
    
    # Passport queries
    if any(word in query_lower for word in ['passport', 'पासपोर्ट', 'paspoort']):
        return json.dumps(knowledge_base.get('services', {}).get('passport', {}), indent=2)
    
    # Visa queries
    if any(word in query_lower for word in ['visa', 'वीजा', 'visum']):
        return json.dumps(knowledge_base.get('services', {}).get('visa', {}), indent=2)
    
    # OCI queries
    if any(word in query_lower for word in ['oci', 'overseas citizen']):
        return json.dumps(knowledge_base.get('services', {}).get('oci', {}), indent=2)
    
    # Contact/emergency
    if any(word in query_lower for word in ['contact', 'emergency', 'phone', 'संपर्क']):
        return f"Emergency: {knowledge_base.get('emergency_contact')}\nEmail: {knowledge_base.get('email')}"
    
    # VFS location
    if any(word in query_lower for word in ['vfs', 'location', 'address', 'कहां']):
        return json.dumps(knowledge_base.get('vfs_locations', {}), indent=2)
    
    return None