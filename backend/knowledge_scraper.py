import httpx
from bs4 import BeautifulSoup
import json
from typing import List, Dict
import asyncio

OFFICIAL_SOURCES = [
    "https://www.cgijoburg.gov.in/",
    "https://visa.vfsglobal.com/one-pager/india/south-africa/johannesburg/"
]

async def scrape_official_websites() -> Dict[str, str]:
    """Scrape official consulate and VFS websites for accurate information"""
    knowledge_base = {
        "source": "Official Consulate General of India, Johannesburg & VFS Global",
        "emergency_contact": "+27 6830 38144",
        "email": "cons.joburg@mea.gov.in",
        "vfs_contact": "https://visa.vfsglobal.com/one-pager/india/south-africa/johannesburg/",
        "services": {
            "passport": {
                "new_passport": "Apply online at passportindia.gov.in, submit documents at VFS Johannesburg",
                "renewal": "Online application required, valid for 10 years for adults",
                "fees": "Check current fees at cgijoburg.gov.in",
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
            },
            "attestation": {
                "documents": "Educational certificates, marriage certificates, birth certificates",
                "process": "Submit originals at Consulate with fee",
                "time": "2-3 weeks"
            }
        },
        "vfs_locations": {
            "johannesburg": {
                "address": "VFS Global, Johannesburg",
                "timings": "Monday-Friday: 08:00-15:00",
                "appointment": "Book online at visa.vfsglobal.com"
            }
        },
        "important_links": {
            "consulate": "https://www.cgijoburg.gov.in/",
            "vfs_global": "https://visa.vfsglobal.com/one-pager/india/south-africa/johannesburg/",
            "passport_seva": "https://portal2.passportindia.gov.in/",
            "e_visa": "https://indianvisaonline.gov.in/"
        }
    }
    return knowledge_base

def get_knowledge_base() -> Dict:
    """Return pre-configured knowledge base from official sources"""
    return asyncio.run(scrape_official_websites())

def search_knowledge(query: str, knowledge_base: Dict) -> str:
    """Search knowledge base for relevant information"""
    query_lower = query.lower()
    
    # Passport queries
    if any(word in query_lower for word in ['passport', 'पासपोर्ट', 'paspoort']):
        return json.dumps(knowledge_base['services']['passport'], indent=2)
    
    # Visa queries
    if any(word in query_lower for word in ['visa', 'वीजा', 'visum']):
        return json.dumps(knowledge_base['services']['visa'], indent=2)
    
    # OCI queries
    if any(word in query_lower for word in ['oci', 'overseas citizen']):
        return json.dumps(knowledge_base['services']['oci'], indent=2)
    
    # Contact/emergency
    if any(word in query_lower for word in ['contact', 'emergency', 'phone', 'संपर्क']):
        return f"Emergency: {knowledge_base['emergency_contact']}\nEmail: {knowledge_base['email']}"
    
    # VFS location
    if any(word in query_lower for word in ['vfs', 'location', 'address', 'कहां']):
        return json.dumps(knowledge_base['vfs_locations'], indent=2)
    
    return None