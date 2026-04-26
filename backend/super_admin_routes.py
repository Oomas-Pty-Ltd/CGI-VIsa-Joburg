from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr
from typing import Dict, List, Optional
import uuid
import csv
import io
import re
from datetime import datetime, timezone, date
import bcrypt
from database import get_database
from auth_utils import verify_super_admin
from knowledge_scraper import invalidate_knowledge_cache

router = APIRouter(prefix="/super-admin", tags=["super-admin"])

class CompanyCreate(BaseModel):
    name: str
    email: EmailStr
    admin_password: str
    llm_model: str = "gpt-5.2"
    features: dict = {"voice": True, "camera": True}

class Company(BaseModel):
    id: str
    name: str
    email: str
    llm_model: str
    features: dict
    created_at: str
    status: str

class LLMConfig(BaseModel):
    company_id: str
    model: str
    provider: str = "openai"

@router.post("/companies", response_model=Company)
async def create_company(company: CompanyCreate, payload: dict = Depends(verify_super_admin)):
    db = await get_database()
    
    existing = await db.companies.find_one({"email": company.email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company with this email already exists"
        )
    
    company_id = str(uuid.uuid4())
    admin_id = str(uuid.uuid4())
    
    company_doc = {
        "id": company_id,
        "name": company.name,
        "email": company.email,
        "llm_model": company.llm_model,
        "features": company.features,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "active"
    }
    
    await db.companies.insert_one(company_doc)
    
    hashed_password = bcrypt.hashpw(company.admin_password.encode('utf-8'), bcrypt.gensalt())
    admin_doc = {
        "id": admin_id,
        "company_id": company_id,
        "email": company.email,
        "password": hashed_password.decode('utf-8'),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.local_admins.insert_one(admin_doc)
    
    return Company(**company_doc)

@router.get("/companies", response_model=List[Company])
async def get_companies(limit: int = 100, payload: dict = Depends(verify_super_admin)):
    db = await get_database()
    companies = await db.companies.find(
        {}, 
        {"_id": 0, "id": 1, "name": 1, "email": 1, "llm_model": 1, "features": 1, "created_at": 1, "status": 1}
    ).limit(limit).to_list(limit)
    return [Company(**company) for company in companies]

@router.get("/companies/{company_id}", response_model=Company)
async def get_company(company_id: str, payload: dict = Depends(verify_super_admin)):
    db = await get_database()
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found"
        )
    
    return Company(**company)

@router.put("/companies/{company_id}/llm-config")
async def update_llm_config(company_id: str, config: LLMConfig, payload: dict = Depends(verify_super_admin)):
    db = await get_database()
    
    result = await db.companies.update_one(
        {"id": company_id},
        {"$set": {"llm_model": config.model}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found"
        )
    
    return {"success": True, "message": "LLM config updated"}

@router.get("/analytics/overview")
async def get_analytics_overview(payload: dict = Depends(verify_super_admin)):
    db = await get_database()

    total_companies = await db.companies.count_documents({})
    total_sessions = await db.chat_sessions.count_documents({})
    total_documents = await db.documents.count_documents({})

    return {
        "total_companies": total_companies,
        "total_sessions": total_sessions,
        "total_documents": total_documents
    }


# ─── Sessions / Conversations ────────────────────────────────────────────────

@router.get("/sessions")
async def list_sessions(
    company_id: Optional[str] = None,
    channel: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    payload: dict = Depends(verify_super_admin),
):
    db = await get_database()
    query = {}
    if company_id:
        query["company_id"] = company_id
    if channel:
        query["channel"] = channel

    skip = (page - 1) * limit
    total = await db.chat_sessions.count_documents(query)
    raw = await (
        db.chat_sessions.find(query, {"_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )

    sessions = []
    for s in raw:
        msgs = s.get("messages", [])
        first_user = next((m["content"] for m in msgs if m.get("role") == "user"), "—")
        sessions.append({
            "id": s.get("id", ""),
            "channel": s.get("channel", "—"),
            "company_id": s.get("company_id") or s.get("metadata", {}).get("company_id", "—"),
            "user_identifier": s.get("user_identifier", "—"),
            "message_count": len(msgs),
            "first_message": first_user[:100],
            "created_at": s.get("created_at", ""),
            "last_activity": s.get("last_activity", ""),
            "is_active": s.get("is_active", False),
        })

    return {"sessions": sessions, "total": total, "page": page, "limit": limit}


@router.get("/sessions/export/csv")
async def export_sessions_csv(
    company_id: Optional[str] = None,
    channel: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    payload: dict = Depends(verify_super_admin),
):
    db = await get_database()
    query = {}
    if company_id:
        query["company_id"] = company_id
    if channel:
        query["channel"] = channel
    if from_date or to_date:
        query["created_at"] = {}
        if from_date:
            query["created_at"]["$gte"] = from_date
        if to_date:
            query["created_at"]["$lte"] = to_date + "T23:59:59Z"

    raw = await db.chat_sessions.find(query, {"_id": 0}).sort("created_at", -1).to_list(10000)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Session ID", "Channel", "Company ID", "User Identifier",
        "Total Messages", "First Message", "Created At", "Last Activity", "Active",
        "Role", "Message", "Timestamp"
    ])

    for s in raw:
        msgs = s.get("messages", [])
        first_user = next((m["content"] for m in msgs if m.get("role") == "user"), "—")
        # Summary row
        writer.writerow([
            s.get("id", ""), s.get("channel", ""),
            s.get("company_id") or s.get("metadata", {}).get("company_id", ""),
            s.get("user_identifier", ""), len(msgs), first_user[:200],
            s.get("created_at", ""), s.get("last_activity", ""), s.get("is_active", False),
            "", "", ""
        ])
        # One row per message
        for m in msgs:
            writer.writerow([
                s.get("id", ""), "", "", "", "", "", "", "", "",
                m.get("role", ""), m.get("content", "")[:500], m.get("timestamp", "")
            ])

    output.seek(0)
    filename = f"sessions_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/sessions/{session_id}")
async def get_session_detail(session_id: str, payload: dict = Depends(verify_super_admin)):
    db = await get_database()
    session = await db.chat_sessions.find_one({"id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


# ─── Audit Logs ──────────────────────────────────────────────────────────────

@router.get("/audit-logs")
async def list_audit_logs(
    company_id: Optional[str] = None,
    category: Optional[str] = None,
    severity: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    payload: dict = Depends(verify_super_admin),
):
    db = await get_database()
    query = {}
    if company_id:
        query["company_id"] = company_id
    if category:
        query["category"] = category
    if severity:
        query["severity"] = severity

    skip = (page - 1) * limit
    total = await db.audit_logs.count_documents(query)
    logs = await (
        db.audit_logs.find(query, {"_id": 0})
        .sort("timestamp", -1)
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )

    return {"logs": logs, "total": total, "page": page, "limit": limit}


@router.get("/audit-logs/export/csv")
async def export_audit_logs_csv(
    company_id: Optional[str] = None,
    category: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    payload: dict = Depends(verify_super_admin),
):
    db = await get_database()
    query = {}
    if company_id:
        query["company_id"] = company_id
    if category:
        query["category"] = category
    if from_date or to_date:
        query["timestamp"] = {}
        if from_date:
            query["timestamp"]["$gte"] = from_date
        if to_date:
            query["timestamp"]["$lte"] = to_date + "T23:59:59Z"

    logs = await db.audit_logs.find(query, {"_id": 0}).sort("timestamp", -1).to_list(10000)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Timestamp", "Category", "Severity", "Action",
        "User ID", "User Type", "Company ID", "Resource Type", "Resource ID",
        "Success", "IP Address", "Error Message"
    ])

    for log in logs:
        writer.writerow([
            log.get("id", ""), log.get("timestamp", ""), log.get("category", ""),
            log.get("severity", ""), log.get("action", ""), log.get("user_id", ""),
            log.get("user_type", ""), log.get("company_id", ""), log.get("resource_type", ""),
            log.get("resource_id", ""), log.get("success", ""), log.get("ip_address", ""),
            log.get("error_message", ""),
        ])

    output.seek(0)
    filename = f"audit_logs_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# PDF → KNOWLEDGE BASE
# ─────────────────────────────────────────────────────────────────────────────

_MONTHS = {
    "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
    "july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
    "jan":1,"feb":2,"mar":3,"apr":4,"jun":6,"jul":7,"aug":8,
    "sep":9,"oct":10,"nov":11,"dec":12,
}

_KB_STOP_WORDS = {
    "the","and","or","but","in","on","at","to","for","of","a","an","is","are",
    "was","were","be","been","being","have","has","had","do","does","did","will",
    "would","could","should","may","might","shall","can","this","that","these",
    "those","with","from","by","as","into","through","during","above","below",
    "between","each","further","then","once","here","there","all","both","few",
    "more","most","other","some","such","no","nor","not","only","same","than",
    "too","very","just","also","about","after","before","under","over","its",
    "it","if","we","you","he","she","they","our","their","your","his","her",
}


def _extract_pdf_text(file_bytes: bytes) -> str:
    """
    Extract plain text from PDF bytes.
    Tries three engines in order of capability:
      1. PyMuPDF (fitz)   — handles complex/compressed layouts best
      2. pdfplumber       — great for tables and unusual encodings
      3. pypdf            — lightweight fallback
    Returns empty string if the PDF has no text layer (scanned/image PDF).
    """
    # ── 1. PyMuPDF ────────────────────────────────────────────────────
    try:
        import fitz
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        parts = []
        for page in doc:
            text = page.get_text("text").strip()
            if text:
                parts.append(text)
        doc.close()
        result = "\n\n".join(parts)
        if result.strip():
            return result
    except ImportError:
        pass
    except Exception:
        pass

    # ── 2. pdfplumber ─────────────────────────────────────────────────
    try:
        import pdfplumber
        parts = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text and text.strip():
                    parts.append(text.strip())
        result = "\n\n".join(parts)
        if result.strip():
            return result
    except ImportError:
        pass
    except Exception:
        pass

    # ── 3. pypdf ──────────────────────────────────────────────────────
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text and text.strip():
                parts.append(text.strip())
        result = "\n\n".join(parts)
        if result.strip():
            return result
    except ImportError:
        pass
    except Exception:
        pass

    return ""  # Scanned/image PDF — caller should try OCR


_OCR_MAX_PAGES = 30   # safety cap for vision-API cost
_OCR_RENDER_DPI = 150  # good OCR quality without huge images


async def _ocr_pdf_with_vision(file_bytes: bytes) -> str:
    """
    OCR a scanned (image-based) PDF using GPT-4o vision.
    Renders each page with PyMuPDF → sends as base64 PNG → extracts text.
    Returns combined text or empty string on failure.
    """
    import fitz
    import base64
    import os
    from openai import AsyncOpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return ""

    client = AsyncOpenAI(api_key=api_key)
    scale = _OCR_RENDER_DPI / 72.0
    mat = fitz.Matrix(scale, scale)

    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        page_count = min(len(doc), _OCR_MAX_PAGES)
        pages_text: List[str] = []

        for page_num in range(page_count):
            pix = doc[page_num].get_pixmap(matrix=mat, alpha=False)
            img_b64 = base64.b64encode(pix.tobytes("png")).decode()

            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Extract all text from this document page exactly as it appears. "
                                "Preserve headings, dates, lists, and table structure. "
                                "Return only the extracted text with no commentary."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{img_b64}",
                                "detail": "high",
                            },
                        },
                    ],
                }],
                max_tokens=2000,
            )
            text = response.choices[0].message.content.strip()
            if text:
                pages_text.append(f"[Page {page_num + 1}]\n{text}")

        doc.close()
        return "\n\n".join(pages_text)

    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(f"[OCR] Vision OCR failed: {exc}")
        return ""


def _find_dates_in_text(text: str) -> List[date]:
    """Parse every recognisable date from free-form text. Returns sorted unique dates."""
    found: List[date] = []
    text_lower = text.lower()

    # ISO: 2024-04-15
    for m in re.finditer(r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b', text):
        try:
            found.append(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            pass

    # DD/MM/YYYY or DD-MM-YYYY
    for m in re.finditer(r'\b(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})\b', text):
        try:
            found.append(date(int(m.group(3)), int(m.group(2)), int(m.group(1))))
        except ValueError:
            pass

    # "15 April 2026" / "15th April 2026"
    for m in re.finditer(
        r'\b(\d{1,2})(?:st|nd|rd|th)?\s+'
        r'(january|february|march|april|may|june|july|august|september|october|november|december'
        r'|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\s+(\d{4})\b',
        text_lower,
    ):
        try:
            found.append(date(int(m.group(3)), _MONTHS[m.group(2)], int(m.group(1))))
        except ValueError:
            pass

    # "April 15, 2026" / "April 15 2026"
    for m in re.finditer(
        r'\b(january|february|march|april|may|june|july|august|september|october|november|december'
        r'|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b',
        text_lower,
    ):
        try:
            found.append(date(int(m.group(3)), _MONTHS[m.group(1)], int(m.group(2))))
        except ValueError:
            pass

    # "April 2026" (month + year only → first of month)
    for m in re.finditer(
        r'\b(january|february|march|april|may|june|july|august|september|october|november|december'
        r'|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\s+(\d{4})\b',
        text_lower,
    ):
        try:
            found.append(date(int(m.group(2)), _MONTHS[m.group(1)], 1))
        except ValueError:
            pass

    return sorted(set(found))


def _classify_event_status(dates: List[date]) -> str:
    """Return 'past' | 'present' | 'future' | 'general'."""
    if not dates:
        return "general"
    today = date.today()
    if any(d == today for d in dates):
        return "present"
    if any(d > today for d in dates):
        return "future"
    return "past"


def _enrich_with_date_context(text: str, dates: List[date], status: str) -> str:
    """Prepend a date-awareness header so the LLM answers correctly."""
    if status == "general" or not dates:
        return text
    try:
        date_strs = ", ".join(d.strftime("%d %B %Y") for d in dates[:3])
    except Exception:
        date_strs = ", ".join(d.isoformat() for d in dates[:3])

    if status == "past":
        header = (
            f"[HISTORICAL — Event/information dated {date_strs}. "
            "This has already occurred. When asked, inform the user it has passed.]"
        )
    elif status == "present":
        header = f"[CURRENT — This event is happening today ({date_strs}).]"
    else:
        header = f"[UPCOMING — This event is scheduled for {date_strs}. Inform the user it is in the future.]"
    return f"{header}\n\n{text}"


def _split_into_sections(text: str, max_chars: int = 1500) -> List[str]:
    """Chunk PDF text into knowledge-base-sized pieces."""
    raw = re.split(r'\n\s*\n', text)
    sections: List[str] = []
    current = ""
    for s in raw:
        s = s.strip()
        if not s:
            continue
        if len(current) + len(s) + 2 <= max_chars:
            current = (current + "\n\n" + s).strip() if current else s
        else:
            if current:
                sections.append(current)
            if len(s) > max_chars:
                for i in range(0, len(s), max_chars):
                    sections.append(s[i : i + max_chars])
                current = ""
            else:
                current = s
    if current:
        sections.append(current)
    return [s for s in sections if len(s.strip()) > 60]


def _extract_keywords(text: str) -> List[str]:
    """Top-20 non-stop-word tokens from text.

    Also captures hyphenated compound terms (e.g. 'id-ul-fitr', 'eid-ul-adha')
    as whole keywords so they are searchable by their full or partial forms.
    """
    norm_text = re.sub(r'[-_]+', ' ', text.lower())
    words = re.findall(r'\b[a-zA-Z]{3,}\b', norm_text)
    freq: dict = {}
    for w in words:
        if w not in _KB_STOP_WORDS:
            freq[w] = freq.get(w, 0) + 1
    top_words = [w for w, _ in sorted(freq.items(), key=lambda x: x[1], reverse=True)[:15]]

    # Add full hyphenated tokens as extra keywords (e.g. "id-ul-fitr" alongside "fitr")
    compound = re.findall(r'\b[a-zA-Z]+-(?:[a-zA-Z]+-)*[a-zA-Z]+\b', text.lower())
    for c in compound:
        if c not in top_words:
            top_words.append(c)

    return top_words[:20]


def _make_title(section_text: str, doc_title: str, idx: int) -> str:
    """Derive a short title for a knowledge entry from the first line of the section."""
    first_line = section_text.split("\n")[0].strip()
    # Use the first line if it looks like a heading (short, mostly caps or title-case)
    if 5 < len(first_line) < 100 and not first_line.endswith("."):
        return first_line
    if doc_title:
        return f"{doc_title} — Part {idx + 1}"
    return f"PDF Upload — Part {idx + 1}"


# Q&A patterns: "Q: ...", "Question: ...", numbered "1. ..." followed by "A: ..."
_QA_QUESTION_RE = re.compile(
    r'^(?:Q(?:uestion)?[\s\d]*[:\.\)]\s*|(\d+[\.\)]\s+))',
    re.IGNORECASE,
)
_QA_ANSWER_RE = re.compile(
    r'^A(?:nswer)?[\s]*[:\.\)]\s*',
    re.IGNORECASE,
)


def _parse_faq_pairs(text: str) -> List[Dict]:
    """
    Detect and extract Q&A pairs from text.
    Returns list of {"question": str, "answer": str} dicts.
    Returns empty list if the text doesn't look like a FAQ.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    pairs: List[Dict] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        q_match = _QA_QUESTION_RE.match(line)
        if q_match:
            question = _QA_QUESTION_RE.sub("", line).strip()
            # Collect multi-line question text until we hit an answer marker or next question
            i += 1
            while i < len(lines) and not _QA_ANSWER_RE.match(lines[i]) and not _QA_QUESTION_RE.match(lines[i]):
                question += " " + lines[i]
                i += 1
            # Collect answer
            answer_parts: List[str] = []
            if i < len(lines) and _QA_ANSWER_RE.match(lines[i]):
                answer_parts.append(_QA_ANSWER_RE.sub("", lines[i]).strip())
                i += 1
                while i < len(lines) and not _QA_QUESTION_RE.match(lines[i]) and not _QA_ANSWER_RE.match(lines[i]):
                    answer_parts.append(lines[i])
                    i += 1
            if question and answer_parts:
                pairs.append({"question": question.strip(), "answer": " ".join(answer_parts).strip()})
        else:
            i += 1
    return pairs


def _is_faq_text(text: str) -> bool:
    """Return True if the text contains at least 2 Q&A pairs."""
    return len(_parse_faq_pairs(text)) >= 2


# ─── PDF Upload endpoint ──────────────────────────────────────────────────────

@router.post("/knowledge/upload-pdf")
async def upload_pdf_to_knowledge(
    file: UploadFile = File(...),
    title: str = Form(""),
    category: str = Form("general"),
    payload: dict = Depends(verify_super_admin),
):
    """
    Upload a PDF; extract its text; parse dates; classify events as
    past / present / future; store each logical section as a knowledge_base entry.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    MAX_SIZE = 50 * 1024 * 1024  # 50 MB
    file_bytes = await file.read()
    if len(file_bytes) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="PDF exceeds 50 MB limit.")

    # ── Step 1: try fast text-layer extraction ────────────────────────
    raw_text = _extract_pdf_text(file_bytes)
    ocr_used = False

    # ── Step 2: fall back to vision OCR for scanned/image PDFs ───────
    if not raw_text.strip():
        raw_text = await _ocr_pdf_with_vision(file_bytes)
        ocr_used = bool(raw_text.strip())

    if not raw_text.strip():
        raise HTTPException(
            status_code=400,
            detail=(
                "Could not extract text from this PDF. "
                "It appears to be a scanned image and OCR also failed. "
                "Please ensure OPENAI_API_KEY is set, or use a PDF with a text layer."
            ),
        )

    doc_title = title.strip() or file.filename.replace(".pdf", "").replace("_", " ").strip()
    doc_title = re.sub(r'^\d+', '', doc_title).strip()  # strip leading numeric prefix from filename

    db = await get_database()
    created_entries = []
    now_iso = datetime.now(timezone.utc).isoformat()

    # ── Detect FAQ format and parse into precise Q&A pairs ────────────
    faq_pairs = _parse_faq_pairs(raw_text)
    if faq_pairs:
        # Store each Q&A pair as its own knowledge entry with the real question
        for idx, pair in enumerate(faq_pairs):
            q_text = pair["question"]
            a_text = pair["answer"]
            full_text = f"Q: {q_text}\nA: {a_text}"
            dates = _find_dates_in_text(full_text)
            status_label = _classify_event_status(dates)
            enriched = _enrich_with_date_context(a_text, dates, status_label)
            keywords = _extract_keywords(q_text + " " + a_text)
            entry_id = str(uuid.uuid4())

            entry_doc = {
                "id": entry_id,
                "category": category,
                "title": q_text[:120],
                "question": q_text,
                "answer": enriched,
                "keywords": keywords,
                "source": f"pdf_upload:{file.filename}",
                "source_verified": True,
                "version": 1,
                "status": "active",
                "language": "en",
                "created_by": "super_admin",
                "created_at": now_iso,
                "updated_at": now_iso,
                "updated_by": None,
                "valid_from": dates[0].isoformat() if dates else None,
                "valid_until": dates[-1].isoformat() if dates else None,
                "event_status": status_label,
                "pdf_filename": file.filename,
                "pdf_doc_title": doc_title,
                "faq_entry": True,
            }
            await db.knowledge_base.insert_one(entry_doc)
            created_entries.append({
                "id": entry_id,
                "title": q_text[:80],
                "category": category,
                "event_status": status_label,
                "dates_found": [d.isoformat() for d in dates],
                "keywords": keywords[:8],
                "source": f"pdf_upload:{file.filename}",
            })
    else:
        # Regular document — split into sections as before
        sections = _split_into_sections(raw_text)
        if not sections:
            raise HTTPException(status_code=400, detail="PDF contained no usable text sections.")

        for idx, section in enumerate(sections):
            dates = _find_dates_in_text(section)
            status_label = _classify_event_status(dates)
            enriched = _enrich_with_date_context(section, dates, status_label)
            keywords = _extract_keywords(section)
            entry_title = _make_title(section, doc_title, idx)
            entry_id = str(uuid.uuid4())

            entry_doc = {
                "id": entry_id,
                "category": category,
                "title": entry_title,
                "question": f"What is the information about: {entry_title}?",
                "answer": enriched,
                "keywords": keywords,
                "source": f"pdf_upload:{file.filename}",
                "source_verified": True,
                "version": 1,
                "status": "active",
                "language": "en",
                "created_by": "super_admin",
                "created_at": now_iso,
                "updated_at": now_iso,
                "updated_by": None,
                "valid_from": dates[0].isoformat() if dates else None,
                "valid_until": dates[-1].isoformat() if dates else None,
                "event_status": status_label,
                "pdf_filename": file.filename,
                "pdf_doc_title": doc_title,
            }
            await db.knowledge_base.insert_one(entry_doc)
            created_entries.append({
                "id": entry_id,
                "title": entry_title,
                "category": category,
                "event_status": status_label,
                "dates_found": [d.isoformat() for d in dates],
                "keywords": keywords[:8],
                "source": f"pdf_upload:{file.filename}",
            })

    # Invalidate the scraper cache so the next chat request picks up the new content
    invalidate_knowledge_cache()

    return {
        "success": True,
        "filename": file.filename,
        "doc_title": doc_title,
        "sections_created": len(created_entries),
        "ocr_used": ocr_used,
        "faq_mode": bool(faq_pairs),
        "entries": created_entries,
    }


# ─── List knowledge entries from PDF uploads ──────────────────────────────────

@router.get("/knowledge/entries")
async def list_knowledge_entries(
    event_status: Optional[str] = None,   # past | present | future | general
    category: Optional[str] = None,
    pdf_filename: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    payload: dict = Depends(verify_super_admin),
):
    """List all knowledge entries created via PDF upload."""
    db = await get_database()
    query: dict = {"source": {"$regex": "^pdf_upload:"}}
    if event_status:
        query["event_status"] = event_status
    if category:
        query["category"] = category
    if pdf_filename:
        query["pdf_filename"] = pdf_filename

    skip = (page - 1) * limit
    total = await db.knowledge_base.count_documents(query)
    raw = await (
        db.knowledge_base.find(query, {"_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )

    entries = []
    for e in raw:
        entries.append({
            "id": e.get("id", ""),
            "title": e.get("title", ""),
            "category": e.get("category", ""),
            "event_status": e.get("event_status", "general"),
            "pdf_filename": e.get("pdf_filename", ""),
            "pdf_doc_title": e.get("pdf_doc_title", ""),
            "valid_from": e.get("valid_from"),
            "valid_until": e.get("valid_until"),
            "keywords": e.get("keywords", [])[:6],
            "answer_preview": (e.get("answer", "")[:200] + "…") if len(e.get("answer", "")) > 200 else e.get("answer", ""),
            "created_at": e.get("created_at", ""),
            "status": e.get("status", "active"),
        })

    return {"entries": entries, "total": total, "page": page, "limit": limit}


# ─── Delete a knowledge entry ─────────────────────────────────────────────────

@router.delete("/knowledge/entries/{entry_id}")
async def delete_knowledge_entry(
    entry_id: str,
    payload: dict = Depends(verify_super_admin),
):
    """Permanently delete a knowledge entry (PDF-sourced or otherwise)."""
    db = await get_database()
    result = await db.knowledge_base.delete_one({"id": entry_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Entry not found.")
    return {"success": True, "deleted_id": entry_id}


# ─── List distinct PDF filenames uploaded ────────────────────────────────────

@router.get("/knowledge/pdf-files")
async def list_uploaded_pdfs(payload: dict = Depends(verify_super_admin)):
    """Return the distinct PDF filenames that have been uploaded."""
    db = await get_database()
    filenames = await db.knowledge_base.distinct(
        "pdf_filename", {"source": {"$regex": "^pdf_upload:"}}
    )
    return {"files": sorted(f for f in filenames if f)}


# ─── Seva Setu Applications with Documents ───────────────────────────────────

@router.get("/seva-setu/applications")
async def get_all_applications_with_documents(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    with_documents: bool = Query(True, description="Filter only applications with documents"),
    payload: dict = Depends(verify_super_admin),
):
    """
    List all Seva Setu applications with optional document filtering.
    Superadmin can view all applications across all users.
    """
    db = await get_database()
    
    # Query to get applications with documents if requested
    query = {}
    if with_documents:
        query = {"documents": {"$exists": True, "$ne": []}}
    
    skip = (page - 1) * limit
    total = await db.seva_setu_applications.count_documents(query)
    
    applications = await (
        db.seva_setu_applications.find(query, {"_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )
    
    # Format applications with document summaries
    formatted_apps = []
    for app in applications:
        docs = app.get("documents", [])
        formatted_app = {
            "id": app.get("id"),
            "reference_id": app.get("reference_id"),
            "user_id": app.get("user_id"),
            "service_type": app.get("service_type"),
            "service_name": app.get("service_name"),
            "status": app.get("status"),
            "created_at": app.get("created_at"),
            "updated_at": app.get("updated_at"),
            "document_count": len(docs),
            "documents": [
                {
                    "id": doc.get("id"),
                    "name": doc.get("name"),
                    "filename": doc.get("filename"),
                    "content_type": doc.get("content_type"),
                    "status": doc.get("status"),
                    "uploaded_at": doc.get("uploaded_at"),
                }
                for doc in docs
            ],
            "form_data_fields": len(app.get("form_data", {})),
        }
        formatted_apps.append(formatted_app)
    
    return {
        "applications": formatted_apps,
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/seva-setu/applications/{app_id}")
async def get_application_with_documents(
    app_id: str,
    payload: dict = Depends(verify_super_admin),
):
    """
    Get a specific Seva Setu application with all document details.
    """
    db = await get_database()
    
    app = await db.seva_setu_applications.find_one(
        {"id": app_id},
        {"_id": 0}
    )
    
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )
    
    # Format with full document details
    docs = app.get("documents", [])
    formatted_app = {
        "id": app.get("id"),
        "reference_id": app.get("reference_id"),
        "user_id": app.get("user_id"),
        "service_type": app.get("service_type"),
        "service_name": app.get("service_name"),
        "service_category": app.get("service_category"),
        "status": app.get("status"),
        "created_at": app.get("created_at"),
        "updated_at": app.get("updated_at"),
        "submitted_at": app.get("submitted_at"),
        "confirmed_at": app.get("confirmed_at"),
        "form_data": app.get("form_data", {}),
        "documents": [
            {
                "id": doc.get("id"),
                "name": doc.get("name"),
                "filename": doc.get("filename"),
                "path": doc.get("path"),
                "content_type": doc.get("content_type"),
                "status": doc.get("status"),
                "uploaded_at": doc.get("uploaded_at"),
            }
            for doc in docs
        ],
        "edit_token": app.get("edit_token"),
    }
    
    return formatted_app


# ─── Keyword search & blocking ───────────────────────────────────────────────

class BlockKeywordRequest(BaseModel):
    keyword: str

@router.get("/knowledge/keyword-search")
async def search_knowledge_by_keyword(
    q: str = Query(..., min_length=1),
    payload: dict = Depends(verify_super_admin),
):
    """Search all knowledge base entries containing the given keyword."""
    db = await get_database()
    q_lower = q.strip().lower()
    cursor = db.knowledge_base.find(
        {"$or": [
            {"keywords": {"$elemMatch": {"$regex": q_lower, "$options": "i"}}},
            {"title": {"$regex": q_lower, "$options": "i"}},
            {"question": {"$regex": q_lower, "$options": "i"}},
            {"answer": {"$regex": q_lower, "$options": "i"}},
        ]},
        {"_id": 0, "id": 1, "title": 1, "category": 1, "keywords": 1,
         "pdf_filename": 1, "source": 1, "event_status": 1},
    ).limit(100)
    entries = await cursor.to_list(100)
    return {"query": q, "matches": entries, "total": len(entries)}


@router.get("/knowledge/blocked-keywords")
async def list_blocked_keywords(payload: dict = Depends(verify_super_admin)):
    """Return all currently blocked keywords."""
    db = await get_database()
    keywords = await db.blocked_keywords.find({}, {"_id": 0}).sort("blocked_at", -1).to_list(500)
    return {"keywords": keywords}


@router.post("/knowledge/blocked-keywords")
async def block_keyword(body: BlockKeywordRequest, payload: dict = Depends(verify_super_admin)):
    """Add a keyword to the blocked list so the bot returns no information for it."""
    keyword = body.keyword.strip().lower()
    if not keyword:
        raise HTTPException(status_code=400, detail="Keyword cannot be empty.")
    db = await get_database()
    existing = await db.blocked_keywords.find_one({"keyword": keyword})
    if existing:
        raise HTTPException(status_code=409, detail="Keyword is already blocked.")
    match_count = await db.knowledge_base.count_documents({"$or": [
        {"keywords": {"$elemMatch": {"$regex": keyword, "$options": "i"}}},
        {"title": {"$regex": keyword, "$options": "i"}},
    ]})
    await db.blocked_keywords.insert_one({
        "keyword": keyword,
        "blocked_at": datetime.now(timezone.utc).isoformat(),
        "blocked_by": "super_admin",
        "matches_count": match_count,
    })
    invalidate_knowledge_cache()
    return {"success": True, "keyword": keyword, "matches_count": match_count}


@router.delete("/knowledge/blocked-keywords/{keyword:path}")
async def unblock_keyword(keyword: str, payload: dict = Depends(verify_super_admin)):
    """Remove a keyword from the blocked list."""
    db = await get_database()
    result = await db.blocked_keywords.delete_one({"keyword": keyword.lower()})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Keyword not found in blocked list.")
    invalidate_knowledge_cache()
    return {"success": True, "keyword": keyword}


# ─────────────────────────────────────────────────────────────────────────────

@router.get("/seva-setu/applications-export/csv")
async def export_applications_with_documents_csv(
    with_documents: bool = Query(True, description="Export only applications with documents"),
    payload: dict = Depends(verify_super_admin),
):
    """
    Export all applications with documents to CSV format.
    """
    db = await get_database()
    
    query = {}
    if with_documents:
        query = {"documents": {"$exists": True, "$ne": []}}
    
    applications = await db.seva_setu_applications.find(
        query, {"_id": 0}
    ).sort("created_at", -1).to_list(10000)
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header row
    writer.writerow([
        "Application ID",
        "Reference ID",
        "User ID",
        "Service Type",
        "Service Name",
        "Status",
        "Document Count",
        "Documents",
        "Form Fields",
        "Created At",
        "Updated At",
        "Submitted At",
        "Confirmed At",
    ])
    
    # Data rows
    for app in applications:
        docs = app.get("documents", [])
        doc_names = "; ".join([doc.get("name", "") for doc in docs])
        
        writer.writerow([
            app.get("id", ""),
            app.get("reference_id", ""),
            app.get("user_id", ""),
            app.get("service_type", ""),
            app.get("service_name", ""),
            app.get("status", ""),
            len(docs),
            doc_names,
            len(app.get("form_data", {})),
            app.get("created_at", ""),
            app.get("updated_at", ""),
            app.get("submitted_at", ""),
            app.get("confirmed_at", ""),
        ])
    
    output.seek(0)
    filename = f"applications_with_documents_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )