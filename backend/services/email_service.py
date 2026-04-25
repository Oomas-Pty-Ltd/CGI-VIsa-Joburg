"""
Email service for Seva Setu — OTP, review link, and confirmation emails.
Uses SMTP (configurable via env vars). Falls back to console logging in dev mode.
"""
import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional

logger = logging.getLogger(__name__)

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")

_DEV_MODE = not SMTP_USER  # skip actual send if SMTP not configured


def _send(to: str, subject: str, html: str, attachment_bytes: Optional[bytes] = None, attachment_name: str = "application.pdf") -> bool:
    if _DEV_MODE:
        logger.info(f"[EMAIL DEV] To: {to} | Subject: {subject}")
        logger.info(f"[EMAIL DEV] Body (truncated): {html[:200]}")
        return True
    try:
        msg = MIMEMultipart("mixed")
        msg["From"] = SMTP_FROM
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(html, "html"))
        if attachment_bytes:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment_bytes)
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{attachment_name}"')
            msg.attach(part)
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_FROM, to, msg.as_string())
        logger.info(f"Email sent to {to}: {subject}")
        return True
    except Exception as e:
        logger.error(f"Email send failed to {to}: {e}")
        return False


def send_otp_email(to: str, otp: str) -> bool:
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:auto">
      <div style="background:#000080;padding:20px;text-align:center">
        <h2 style="color:#fff;margin:0">Seva Setu — Consulate General of India</h2>
        <p style="color:#FF9933;margin:4px 0">Johannesburg</p>
      </div>
      <div style="padding:24px;background:#fff">
        <h3 style="color:#1A2E40">Your Verification Code</h3>
        <p style="color:#555">Use the OTP below to verify your identity. It is valid for <strong>10 minutes</strong>.</p>
        <div style="background:#FFF8F2;border:2px solid #E06F2C;border-radius:8px;padding:20px;text-align:center;margin:20px 0">
          <span style="font-size:36px;font-weight:bold;letter-spacing:8px;color:#E06F2C">{otp}</span>
        </div>
        <p style="color:#888;font-size:12px">If you did not request this, please ignore this email.</p>
      </div>
    </div>"""
    return _send(to, "Your Seva Setu Verification Code", html)


def send_account_created_email(to: str, name: str, reference_id: str, service_name: str) -> bool:
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:auto">
      <div style="background:#000080;padding:20px;text-align:center">
        <h2 style="color:#fff;margin:0">Seva Setu — Account Created</h2>
        <p style="color:#FF9933;margin:4px 0">Consulate General of India, Johannesburg</p>
      </div>
      <div style="padding:24px;background:#fff">
        <p>Dear <strong>{name}</strong>,</p>
        <p>Your Seva Setu account has been created successfully for <strong>{service_name}</strong>.</p>
        <div style="background:#FFF8F2;border-left:4px solid #E06F2C;padding:12px 16px;margin:16px 0">
          <p style="margin:0;font-size:13px;color:#555">Reference ID</p>
          <p style="margin:4px 0;font-size:20px;font-weight:bold;color:#E06F2C">{reference_id}</p>
        </div>
        <p>Keep this Reference ID safe — you will need it to track your application.</p>
        <h4 style="color:#1A2E40">Next Steps</h4>
        <ol style="color:#555;line-height:1.8">
          <li>Complete your application in the chat</li>
          <li>Upload required documents</li>
          <li>Submit and receive your confirmation email with PDF</li>
        </ol>
        <p style="color:#888;font-size:12px;margin-top:24px">
          Consulate General of India, Johannesburg<br>
          1 Eton Road, Parktown 2193 | +27 11 581 9800 | cons.joburg@mea.gov.in
        </p>
      </div>
    </div>"""
    return _send(to, f"Seva Setu — Account Created ({reference_id})", html)


def send_review_email(to: str, name: str, reference_id: str, edit_token: str, form_summary: dict) -> bool:
    edit_url = f"{FRONTEND_URL}/review/{edit_token}"
    rows = "".join(
        f"<tr><td style='padding:6px 12px;color:#555;font-size:13px'>{k.replace('_',' ').title()}</td>"
        f"<td style='padding:6px 12px;color:#1A2E40;font-size:13px'><strong>{v}</strong></td></tr>"
        for k, v in form_summary.items() if v
    )
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto">
      <div style="background:#000080;padding:20px;text-align:center">
        <h2 style="color:#fff;margin:0">Review Your Application</h2>
        <p style="color:#FF9933;margin:4px 0">Seva Setu — Consulate General of India, Johannesburg</p>
      </div>
      <div style="padding:24px;background:#fff">
        <p>Dear <strong>{name}</strong>,</p>
        <p>Your application <strong>{reference_id}</strong> has been submitted for review.
           Please review the details below and confirm within <strong>24 hours</strong>.</p>
        <table style="width:100%;border-collapse:collapse;margin:16px 0;border:1px solid #e5e7eb">
          <thead><tr style="background:#f9fafb">
            <th style="padding:8px 12px;text-align:left;color:#6b7280;font-size:12px;text-transform:uppercase">Field</th>
            <th style="padding:8px 12px;text-align:left;color:#6b7280;font-size:12px;text-transform:uppercase">Value</th>
          </tr></thead>
          <tbody>{rows}</tbody>
        </table>
        <div style="text-align:center;margin:24px 0">
          <a href="{edit_url}" style="display:inline-block;background:#E06F2C;color:#fff;padding:12px 32px;border-radius:6px;text-decoration:none;font-weight:bold;font-size:15px">
            Review &amp; Confirm Application
          </a>
        </div>
        <p style="color:#888;font-size:12px">This link expires in 24 hours. After expiry, your application will be submitted as-is.</p>
        <p style="color:#888;font-size:12px;margin-top:24px">
          Consulate General of India, Johannesburg<br>
          1 Eton Road, Parktown 2193 | +27 11 581 9800 | cons.joburg@mea.gov.in
        </p>
      </div>
    </div>"""
    return _send(to, f"Seva Setu — Review Your Application [{reference_id}]", html)


def send_confirmation_email(to: str, name: str, reference_id: str, service_name: str, pdf_bytes: Optional[bytes] = None) -> bool:
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto">
      <div style="background:#000080;padding:20px;text-align:center">
        <h2 style="color:#fff;margin:0">Application Confirmed</h2>
        <p style="color:#FF9933;margin:4px 0">Seva Setu — Consulate General of India, Johannesburg</p>
      </div>
      <div style="padding:24px;background:#fff">
        <p>Dear <strong>{name}</strong>,</p>
        <p>Your <strong>{service_name}</strong> application has been confirmed and received by the Consulate.</p>
        <div style="background:#FFF8F2;border-left:4px solid #E06F2C;padding:12px 16px;margin:16px 0">
          <p style="margin:0;font-size:13px;color:#555">Application Reference Number</p>
          <p style="margin:4px 0;font-size:22px;font-weight:bold;color:#E06F2C">{reference_id}</p>
          <p style="margin:4px 0;font-size:13px;color:#555">Status: <strong style="color:#059669">Submitted — Pending Review</strong></p>
        </div>
        <h4 style="color:#1A2E40">Processing Timeline</h4>
        <ul style="color:#555;line-height:1.8">
          <li>Applications are reviewed within 5–7 working days</li>
          <li>You will be contacted via email if additional documents are required</li>
          <li>Track your application using your Reference ID</li>
        </ul>
        <h4 style="color:#1A2E40">Contact &amp; Office Hours</h4>
        <p style="color:#555">
          <strong>Phone:</strong> +27 11 581 9800<br>
          <strong>Email:</strong> cons.joburg@mea.gov.in<br>
          <strong>Address:</strong> 1 Eton Road, Parktown 2193, Johannesburg<br>
          <strong>Hours:</strong> Mon–Fri, 09:00–13:00 (Consular Section)
        </p>
        <p style="color:#888;font-size:12px">Your completed application PDF is attached to this email.</p>
      </div>
    </div>"""
    return _send(
        to,
        f"Seva Setu — Application Confirmed [{reference_id}]",
        html,
        attachment_bytes=pdf_bytes,
        attachment_name=f"{reference_id}.pdf"
    )
