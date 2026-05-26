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
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Paragraph


# ── PDF branding palette ─────────────────────────────────────────────────────
# Neutral defaults — no brand colours hardcoded. Every tenant supplies its own
# pdf_branding dict on tenant_bot_config; if absent we fall back to greyscale.
_DEFAULT_BRANDING: Dict[str, Any] = {
    "header_color":      "#1F2937",   # primary band (navy-ish dark grey)
    "accent_color":      "#E06F2C",   # accent / sub-header / icons
    "highlight_color":   "#FF9933",   # top stripe (set to header_color to disable)
    "stripe_colors":     [],          # extra stripes (e.g. flag tricolour) — empty disables
    "notice_bg":         "#FFF8F2",   # notice box background
    "muted_text":        "#6B7280",
    "border":            "#D1D5DB",
    "footer_text":       "This document is an APPLICATION PREVIEW. Review carefully before submitting.",
    "notice_text":       "📋 REVIEW NOTICE: Check all fields carefully. You may type corrections in the chat before submitting.",
}


class _Palette:
    """Resolved colour palette for a single PDF render. Built from a
    ``pdf_branding`` dict; missing keys fall back to neutral defaults."""

    def __init__(self, branding: Optional[Dict[str, Any]] = None):
        b = {**_DEFAULT_BRANDING, **(branding or {})}
        def _c(key: str):
            v = b.get(key) or _DEFAULT_BRANDING[key]
            return colors.HexColor(v) if isinstance(v, str) and v.startswith("#") else colors.HexColor(_DEFAULT_BRANDING[key])
        self.header      = _c("header_color")
        self.accent      = _c("accent_color")
        self.highlight   = _c("highlight_color")
        self.notice_bg   = _c("notice_bg")
        self.muted_text  = _c("muted_text")
        self.border      = _c("border")
        # Stripe colours: keep as a list of HexColor for the optional flag stripe.
        stripes = b.get("stripe_colors") or []
        self.stripes = [colors.HexColor(s) for s in stripes if isinstance(s, str) and s.startswith("#")]
        self.notice_text = b.get("notice_text") or _DEFAULT_BRANDING["notice_text"]
        self.footer_text = b.get("footer_text") or _DEFAULT_BRANDING["footer_text"]


# ── Label → display name lookup ──────────────────────────────────────────────
# Generic platform fallback labels. Tenants supply per-field
# ``display_label`` on tenant_services[].fields[]; the PDF helper looks up
# the override via the ``field_labels`` map passed to ``generate_application_pdf``
# and falls back to title-case of the key when neither is set.
_FALLBACK_LABELS: Dict[str, str] = {
    "full_name":         "Full Name",
    "dob":               "Date of Birth (DD/MM/YYYY)",
    "passport_number":   "Passport Number",
    "nationality":       "Nationality",
    "travel_dates":      "Intended Travel Dates",
    "purpose":           "Purpose of Visit",
    "phone":             "Phone Number",
    "email":             "Email Address",
    "address":           "Address",
    "doc_type":          "Document Type",
    "doc_purpose":       "Purpose of Attestation",
    "birth_place":       "Place of Birth",
    "marriage_date":     "Date of Marriage (DD/MM/YYYY)",
    "marriage_place":    "Place of Marriage",
}


def _display_label(key: str, field_labels: Optional[Dict[str, str]] = None) -> str:
    """Resolve the display label for a form-field key.

    Order: tenant override (``field_labels``) → platform fallback
    (``_FALLBACK_LABELS``) → title-case of the key.
    """
    if field_labels and field_labels.get(key):
        return field_labels[key]
    return _FALLBACK_LABELS.get(key, key.replace("_", " ").title())


# ─────────────────────────────────────────────────────────────────────────────

def generate_application_pdf(
    service_name: str,
    form_data: Dict[str, str],
    tracking_id: str,
    uploaded_docs: Optional[List[Dict]] = None,
    required_docs: Optional[List[str]] = None,
    org_name: str = "",
    branding: Optional[Dict[str, Any]] = None,
    field_labels: Optional[Dict[str, str]] = None,
) -> bytes:
    """
    Generate an editable AcroForm PDF for the applicant to review.

    ``branding`` is the tenant's ``pdf_branding`` dict from bot_config — see
    ``_DEFAULT_BRANDING`` above for the schema. ``org_name`` is the header
    label; both default to neutral values.

    Returns raw PDF bytes.
    """
    buf = io.BytesIO()
    page_w, page_h = A4
    c = rl_canvas.Canvas(buf, pagesize=A4)
    palette = _Palette(branding)

    _draw_page(c, page_w, page_h, service_name, form_data, tracking_id,
               uploaded_docs or [], required_docs or [], org_name=org_name,
               palette=palette, field_labels=field_labels or {})

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
    required_docs: List[str] = None,
    org_name: str = "",
    palette: Optional[_Palette] = None,
    field_labels: Optional[Dict[str, str]] = None,
):
    p = palette or _Palette()

    # ── Header band ───────────────────────────────────────────────────
    header_h = 30 * mm
    c.setFillColor(p.header)
    c.rect(0, ph - header_h, pw, header_h, fill=1, stroke=0)

    # Optional top stripe(s). If the tenant supplies `stripe_colors`,
    # render them as horizontal bars across the top of the header. Falls
    # back to a single highlight stripe so a single-colour brand still
    # gets a subtle accent.
    stripe_h = 3 * mm
    stripes = p.stripes or [p.highlight]
    for idx, col in enumerate(stripes):
        c.setFillColor(col)
        c.rect(0, ph - (idx + 1) * stripe_h, pw, stripe_h, fill=1, stroke=0)

    # Header text
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 14)
    header_title = org_name or ""
    if header_title:
        c.drawCentredString(pw / 2, ph - 17 * mm, header_title)

    # ── Sub-header: application type ─────────────────────────────────
    sub_y = ph - header_h - 10 * mm
    c.setFillColor(p.accent)
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(pw / 2, sub_y, f"APPLICATION PREVIEW — {service_name.upper()}")

    # Tracking ID + date
    c.setFont("Helvetica", 8)
    c.setFillColor(p.muted_text)
    now = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
    c.drawString(15 * mm, sub_y - 7 * mm, f"Tracking ID: {tracking_id}")
    c.drawRightString(pw - 15 * mm, sub_y - 7 * mm, f"Generated: {now}")

    # ── Horizontal rule ───────────────────────────────────────────────
    rule_y = sub_y - 12 * mm
    c.setStrokeColor(p.border)
    c.setLineWidth(0.5)
    c.line(15 * mm, rule_y, pw - 15 * mm, rule_y)

    # ── Notice box ───────────────────────────────────────────────────
    notice_y = rule_y - 9 * mm
    c.setFillColor(p.notice_bg)
    c.roundRect(15 * mm, notice_y - 5 * mm, pw - 30 * mm, 12 * mm, 2 * mm, fill=1, stroke=0)
    c.setFillColor(p.accent)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(18 * mm, notice_y + 1 * mm, p.notice_text)

    # ── Form fields ───────────────────────────────────────────────────
    field_start_y = notice_y - 12 * mm
    _draw_form_fields(c, pw, ph, form_data, field_start_y, p, field_labels or {})

    # Track vertical position after form fields
    field_block_h = len(form_data) * 14 * mm
    current_y = field_start_y - field_block_h - 8 * mm

    # ── Required documents checklist ──────────────────────────────────
    if required_docs and current_y > 50 * mm:
        _draw_required_docs_section(c, pw, required_docs, current_y, p)
        current_y -= (len(required_docs) + 2) * 7 * mm + 8 * mm

    # ── Uploaded documents checklist ──────────────────────────────────
    if uploaded_docs and current_y > 50 * mm:
        _draw_docs_section(c, pw, uploaded_docs, current_y, p)
        current_y -= (len(uploaded_docs) + 2) * 7 * mm + 8 * mm

    # ── Signature line ────────────────────────────────────────────────
    if current_y > 35 * mm:
        _draw_signature(c, pw, current_y, p)

    # ── Footer ────────────────────────────────────────────────────────
    _draw_footer(c, pw, p)


def _draw_form_fields(c, pw: float, ph: float, form_data: Dict, start_y: float, p: _Palette, field_labels: Optional[Dict[str, str]] = None):
    """Draw each field as a labelled AcroForm text field."""
    left_margin  = 15 * mm
    label_w      = 60 * mm
    field_x      = left_margin + label_w + 3 * mm
    field_w      = pw - field_x - 15 * mm
    row_h        = 14 * mm
    field_h      = 9 * mm

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(p.header)
    c.drawString(left_margin, start_y + 2 * mm, "FORM FIELDS")
    c.setStrokeColor(p.header)
    c.setLineWidth(1)
    c.line(left_margin, start_y + 0.5 * mm, left_margin + 30 * mm, start_y + 0.5 * mm)

    y = start_y - 6 * mm
    for key, value in form_data.items():
        label = _display_label(key, field_labels)
        field_name = f"field_{key}"

        # Label
        c.setFont("Helvetica", 8)
        c.setFillColor(p.muted_text)
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
            borderColor=p.border,
            borderWidth=0.5,
            forceBorder=True,
        )

        y -= row_h


def _draw_required_docs_section(c, pw: float, required_docs: List[str], start_y: float, p: _Palette):
    """Show a checklist of required documents the applicant must bring."""
    left_margin = 15 * mm
    y = start_y

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(p.header)
    c.drawString(left_margin, y + 2 * mm, "REQUIRED DOCUMENTS (Please bring originals + copies)")
    c.setStrokeColor(p.header)
    c.setLineWidth(1)
    c.line(left_margin, y + 0.5 * mm, left_margin + 90 * mm, y + 0.5 * mm)
    y -= 6 * mm

    for doc in required_docs:
        c.setFillColor(p.accent)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(left_margin, y, "□")
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 8)
        c.drawString(left_margin + 6 * mm, y, doc)
        y -= 7 * mm


def _draw_docs_section(c, pw: float, uploaded_docs: List[Dict], start_y: float, p: _Palette):
    """Show a checklist of uploaded/attached documents."""
    left_margin = 15 * mm
    y = start_y

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(p.header)
    c.drawString(left_margin, y + 2 * mm, "ATTACHED DOCUMENTS")
    c.setStrokeColor(p.header)
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


def _draw_signature(c, pw: float, y: float, p: _Palette):
    """Draw signature and date fields at the bottom."""
    left  = 15 * mm
    right = pw - 15 * mm
    mid   = pw / 2

    c.setStrokeColor(p.border)
    c.setLineWidth(0.5)
    # Signature line (left)
    c.line(left, y, mid - 10 * mm, y)
    c.setFont("Helvetica", 7)
    c.setFillColor(p.muted_text)
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
        fontSize=9, borderColor=p.border, borderWidth=0.3, forceBorder=True,
        fillColor=colors.white,
    )
    c.acroForm.textfield(
        name="signature_date",
        tooltip="Date",
        x=mid + 10 * mm, y=y - 8 * mm,
        width=(right - mid - 10 * mm), height=7 * mm,
        fontSize=9, borderColor=p.border, borderWidth=0.3, forceBorder=True,
        fillColor=colors.white,
    )


def _draw_footer(c, pw: float, p: _Palette):
    """Draw footer strip."""
    footer_h = 10 * mm
    c.setFillColor(p.header)
    c.rect(0, 0, pw, footer_h, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica", 7)
    c.drawCentredString(pw / 2, 3.5 * mm, p.footer_text)
