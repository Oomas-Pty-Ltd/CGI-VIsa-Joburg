"""
====================================================================
PDF SERVICE  — Editable AcroForm PDF generation  (TC 4.1)
====================================================================
Generates a pre-filled, editable application preview PDF using
reportlab.  Each form field is an AcroForm text field so the
applicant can open the PDF in any standard reader and correct
values before final submission (TC 4.2).

Usage:
    pdf_bytes = generate_application_pdf(
        service_name="Passport Services",
        form_data={"full_name": "John Smith", "dob": "15/08/1990", ...},
        tracking_id="PASSPORT-20260403-AB12CD",
        uploaded_docs=[{"name": "Passport copy", "status": "uploaded"}, ...],
    )
====================================================================
"""
import io
from datetime import datetime, timezone
from typing import Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Paragraph


# ── Brand colours ────────────────────────────────────────────────────────────
_SAFFRON  = colors.HexColor("#FF9933")   # India flag saffron
_NAVY     = colors.HexColor("#000080")   # India flag navy
_ORANGE   = colors.HexColor("#E06F2C")   # Seva Setu brand
_LIGHT_BG = colors.HexColor("#FFF8F2")
_GRAY     = colors.HexColor("#6B7280")
_BORDER   = colors.HexColor("#D1D5DB")


# ── Label → display name lookup ──────────────────────────────────────────────
_FIELD_LABELS: Dict[str, str] = {
    "full_name":       "Full Name",
    "child_name":      "Child's Full Name",
    "father_name":     "Father's Full Name",
    "mother_name":     "Mother's Full Name",
    "spouse_name":     "Spouse's Full Name",
    "dob":             "Date of Birth (DD/MM/YYYY)",
    "passport_number": "Passport Number",
    "indian_passport": "Indian Passport Number",
    "new_passport":    "New Foreign Passport No.",
    "father_passport": "Father's Passport Number",
    "nationality":     "Nationality",
    "travel_dates":    "Intended Travel Dates",
    "purpose":         "Purpose of Visit",
    "phone":           "Phone Number",
    "email":           "Email Address",
    "address":         "Residential Address in SA",
    "indian_connection": "Indian Origin Connection",
    "doc_type":        "Document Type",
    "doc_purpose":     "Purpose of Attestation",
    "new_citizenship": "New Citizenship / Nationality",
    "new_passport":    "New Foreign Passport Number",
    "indian_citizenship": "Renounced Indian Citizenship",
    "birth_place":     "Place of Birth",
    "marriage_date":   "Date of Marriage (DD/MM/YYYY)",
    "marriage_place":  "Place of Marriage",
}


def _display_label(key: str) -> str:
    return _FIELD_LABELS.get(key, key.replace("_", " ").title())


# ─────────────────────────────────────────────────────────────────────────────

def generate_application_pdf(
    service_name: str,
    form_data: Dict[str, str],
    tracking_id: str,
    uploaded_docs: Optional[List[Dict]] = None,
) -> bytes:
    """
    Generate an editable AcroForm PDF for the applicant to review.

    Returns raw PDF bytes.
    """
    buf = io.BytesIO()
    page_w, page_h = A4
    c = rl_canvas.Canvas(buf, pagesize=A4)

    _draw_page(c, page_w, page_h, service_name, form_data, tracking_id, uploaded_docs or [])

    c.save()
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL DRAWING HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _draw_page(
    c,
    pw: float,
    ph: float,
    service_name: str,
    form_data: Dict,
    tracking_id: str,
    uploaded_docs: List[Dict],
):
    # ── Header band ───────────────────────────────────────────────────
    header_h = 30 * mm
    c.setFillColor(_NAVY)
    c.rect(0, ph - header_h, pw, header_h, fill=1, stroke=0)

    # Tricolour stripe
    stripe_h = 3 * mm
    c.setFillColor(_SAFFRON)
    c.rect(0, ph - stripe_h, pw, stripe_h, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.rect(0, ph - 2 * stripe_h, pw, stripe_h, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#138808"))  # India flag green
    c.rect(0, ph - 3 * stripe_h, pw, stripe_h, fill=1, stroke=0)

    # Header text
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(pw / 2, ph - 14 * mm, "Consulate General of India, Johannesburg")
    c.setFont("Helvetica", 9)
    c.drawCentredString(pw / 2, ph - 20 * mm, "1 Eton Road, Parktown 2193, Johannesburg  |  +27 11 581 9800  |  cons.joburg@mea.gov.in")

    # ── Sub-header: application type ─────────────────────────────────
    sub_y = ph - header_h - 10 * mm
    c.setFillColor(_ORANGE)
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(pw / 2, sub_y, f"APPLICATION PREVIEW — {service_name.upper()}")

    # Tracking ID + date
    c.setFont("Helvetica", 8)
    c.setFillColor(_GRAY)
    now = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
    c.drawString(15 * mm, sub_y - 7 * mm, f"Tracking ID: {tracking_id}")
    c.drawRightString(pw - 15 * mm, sub_y - 7 * mm, f"Generated: {now}")

    # ── Horizontal rule ───────────────────────────────────────────────
    rule_y = sub_y - 12 * mm
    c.setStrokeColor(_BORDER)
    c.setLineWidth(0.5)
    c.line(15 * mm, rule_y, pw - 15 * mm, rule_y)

    # ── Notice box ───────────────────────────────────────────────────
    notice_y = rule_y - 9 * mm
    c.setFillColor(_LIGHT_BG)
    c.roundRect(15 * mm, notice_y - 5 * mm, pw - 30 * mm, 12 * mm, 2 * mm, fill=1, stroke=0)
    c.setFillColor(_ORANGE)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(18 * mm, notice_y + 1 * mm,
                 "📋 REVIEW NOTICE: Check all fields carefully. You may type corrections in the chat "
                 "before submitting (e.g. \"correct name: John Smith\").")

    # ── Form fields ───────────────────────────────────────────────────
    field_start_y = notice_y - 12 * mm
    _draw_form_fields(c, pw, ph, form_data, field_start_y)

    # ── Documents uploaded ────────────────────────────────────────────
    # Calculate how many fields were drawn to find next y position
    fields = list(form_data.items())
    fields_drawn = len(fields)
    field_block_h = fields_drawn * 14 * mm
    docs_y = field_start_y - field_block_h - 8 * mm

    if docs_y > 40 * mm:
        _draw_docs_section(c, pw, uploaded_docs, docs_y)
        sig_y = docs_y - (len(uploaded_docs) + 1) * 7 * mm - 10 * mm
    else:
        sig_y = docs_y

    # ── Signature line ────────────────────────────────────────────────
    if sig_y > 35 * mm:
        _draw_signature(c, pw, sig_y)

    # ── Footer ────────────────────────────────────────────────────────
    _draw_footer(c, pw)


def _draw_form_fields(c, pw: float, ph: float, form_data: Dict, start_y: float):
    """Draw each field as a labelled AcroForm text field."""
    left_margin  = 15 * mm
    label_w      = 60 * mm
    field_x      = left_margin + label_w + 3 * mm
    field_w      = pw - field_x - 15 * mm
    row_h        = 14 * mm
    field_h      = 9 * mm

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(_NAVY)
    c.drawString(left_margin, start_y + 2 * mm, "FORM FIELDS")
    c.setStrokeColor(_NAVY)
    c.setLineWidth(1)
    c.line(left_margin, start_y + 0.5 * mm, left_margin + 30 * mm, start_y + 0.5 * mm)

    y = start_y - 6 * mm
    for key, value in form_data.items():
        label = _display_label(key)
        field_name = f"field_{key}"

        # Label
        c.setFont("Helvetica", 8)
        c.setFillColor(_GRAY)
        c.drawString(left_margin, y + 1 * mm, label + ":")

        # Light background for the field
        c.setFillColor(colors.HexColor("#F9FAFB"))
        c.roundRect(field_x - 1, y - 1, field_w + 2, field_h + 2, 1.5 * mm, fill=1, stroke=0)

        # AcroForm editable text field
        c.acroForm.textfield(
            name=field_name,
            tooltip=f"Edit {label}",
            x=field_x,
            y=y,
            width=field_w,
            height=field_h,
            value=str(value) if value else "",
            fontSize=9,
            textColor=colors.black,
            fillColor=colors.HexColor("#F9FAFB"),
            borderColor=_BORDER,
            borderWidth=0.5,
            forceBorder=True,
        )

        y -= row_h


def _draw_docs_section(c, pw: float, uploaded_docs: List[Dict], start_y: float):
    """Show a checklist of uploaded documents."""
    left_margin = 15 * mm
    y = start_y

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(_NAVY)
    c.drawString(left_margin, y + 2 * mm, "UPLOADED DOCUMENTS")
    c.setStrokeColor(_NAVY)
    c.setLineWidth(1)
    c.line(left_margin, y + 0.5 * mm, left_margin + 50 * mm, y + 0.5 * mm)
    y -= 6 * mm

    for doc in uploaded_docs:
        icon   = "✓" if doc.get("status") == "uploaded" else "–"
        colour = colors.HexColor("#059669") if doc.get("status") == "uploaded" else colors.HexColor("#9CA3AF")
        c.setFillColor(colour)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(left_margin, y, icon)
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 8)
        c.drawString(left_margin + 6 * mm, y, doc.get("name", "Document"))
        y -= 7 * mm


def _draw_signature(c, pw: float, y: float):
    """Draw signature and date fields at the bottom."""
    left  = 15 * mm
    right = pw - 15 * mm
    mid   = pw / 2

    c.setStrokeColor(_BORDER)
    c.setLineWidth(0.5)
    # Signature line (left)
    c.line(left, y, mid - 10 * mm, y)
    c.setFont("Helvetica", 7)
    c.setFillColor(_GRAY)
    c.drawString(left, y - 4 * mm, "Applicant Signature")

    # Date line (right)
    c.line(mid + 10 * mm, y, right, y)
    c.drawRightString(right, y - 4 * mm, "Date")

    # AcroForm fields under each line
    c.acroForm.textfield(
        name="applicant_signature",
        tooltip="Applicant Signature",
        x=left, y=y - 8 * mm,
        width=(mid - 10 * mm - left), height=7 * mm,
        fontSize=9, borderColor=_BORDER, borderWidth=0.3, forceBorder=True,
        fillColor=colors.white,
    )
    c.acroForm.textfield(
        name="signature_date",
        tooltip="Date",
        x=mid + 10 * mm, y=y - 8 * mm,
        width=(right - mid - 10 * mm), height=7 * mm,
        fontSize=9, borderColor=_BORDER, borderWidth=0.3, forceBorder=True,
        fillColor=colors.white,
    )


def _draw_footer(c, pw: float):
    """Draw footer strip."""
    footer_h = 10 * mm
    c.setFillColor(_NAVY)
    c.rect(0, 0, pw, footer_h, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica", 7)
    c.drawCentredString(
        pw / 2, 3.5 * mm,
        "This document is an APPLICATION PREVIEW generated by Seva Setu Bot.  "
        "Review carefully before submitting.  "
        "https://www.cgijoburg.gov.in"
    )
