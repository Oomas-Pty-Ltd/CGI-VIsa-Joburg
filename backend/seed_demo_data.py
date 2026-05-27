"""Demo seed script — populates two tenants with realistic data so you
can cross-verify every Sprint 0-14 feature from the UI and API.

Run from backend/ after the server is up:
    .venv/bin/python seed_demo_data.py [--cleanup]

Creates (idempotent, re-runs are safe):
  * 2 tenants:  "Demo Consulate A" + "Demo Consulate B"
  * 1 primary local-admin per tenant + 1 secondary (so admins-CRUD has data)
  * 2 channel mappings (1 WhatsApp number per tenant)
  * Bot config per tenant (different branding so the difference is visible)
  * 3 services per tenant — including:
      - a plain INPUT-only "passport" service
      - a "visa" service with a CONDITIONAL step (skip-to-docs for SA nationals)
      - a "verify" service with an API_CALL step
  * Scraper config per tenant (different seeds)
  * Knowledge entries per tenant (via /admin/knowledge)
  * A chat session for each tenant (so Conversations + Audit Logs aren't empty)
  * One revoked-token demo for tenant B

With --cleanup, drops every demo row + tenant created by this script.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import bcrypt
import requests
from pymongo import MongoClient


# ── Env wiring ──────────────────────────────────────────────────────────────
ENV_PATH = Path(__file__).resolve().parent / ".env"
for line in ENV_PATH.read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    os.environ.setdefault(k.strip(), v.strip())

API = f"http://localhost:{os.environ.get('SERVER_PORT', '8000')}/api"
SA_EMAIL = "superadmin@sarthak.ai"
SA_PASS  = "Admin@2025"
# Console login is 2FA: the fixed dev OTP works only while the platform
# `dev_auth_mode` flag is ON (its default). See sa_token().
DEV_OTP  = "123456"


# ── Demo blueprint ──────────────────────────────────────────────────────────
TENANTS = [
    {
        "name":     "Demo Consulate A",
        "email":    "demo_a@example.com",      # also the primary admin's email
        "password": "DemoA@2026",
        "secondary_admin_email": "viewer_a@example.com",
        "secondary_admin_password": "ViewerA@2026",
        "branding_color": "#1E88E5",  # blue — easy to tell apart from B
        "wa_number":      "+2715555000A",
        "scraper_seed":   "https://www.example-a.gov",
    },
    {
        "name":     "Demo Consulate B",
        "email":    "demo_b@example.com",
        "password": "DemoB@2026",
        "secondary_admin_email": "viewer_b@example.com",
        "secondary_admin_password": "ViewerB@2026",
        "branding_color": "#43A047",  # green
        "wa_number":      "+2715555000B",
        "scraper_seed":   "https://www.example-b.gov",
    },
]


# ── helpers ─────────────────────────────────────────────────────────────────
def header(s):
    print(f"\n{'─' * 4} {s} {'─' * (72 - len(s))}")

def step(s):
    print(f"  {s}")


def sa_token() -> str:
    """Console login is now 2FA: ``/auth/login`` no longer returns a token —
    it issues an OTP challenge, and the JWT is minted at
    ``/auth/login/verify-otp``. With the platform ``dev_auth_mode`` flag ON
    (the default) the OTP is the fixed dev code ``123456`` and no email is
    sent, so the seed can complete the flow unattended."""
    r = requests.post(f"{API}/auth/login", json={"email": SA_EMAIL, "password": SA_PASS})
    r.raise_for_status()
    data = r.json()
    if data.get("token"):                       # 2FA disabled — direct token (unlikely)
        return data["token"]
    if not data.get("otp_required"):
        raise SystemExit(f"❌ Unexpected login response (no token, no otp_required): {data}")
    if not data.get("dev_mode", True):
        raise SystemExit(
            "❌ Console 2FA is in PRODUCTION mode (dev_auth_mode=False): the OTP is "
            "emailed, not 123456, so the seed can't auto-verify. Turn on dev_auth_mode "
            "in Super Admin → Platform Settings → Auth, then re-run."
        )
    v = requests.post(f"{API}/auth/login/verify-otp", json={"email": SA_EMAIL, "otp": DEV_OTP})
    v.raise_for_status()
    return v.json()["token"]


def mongo() -> MongoClient:
    return MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=3000)


def get_or_create_tenant(client_db, sa_tok: str, blueprint: dict) -> str:
    """Returns the company_id, creating the company + primary admin if needed."""
    existing = client_db.companies.find_one({"email": blueprint["email"]}, {"_id": 0, "id": 1})
    if existing:
        step(f"reusing existing tenant {existing['id'][:8]}… ({blueprint['name']})")
        return existing["id"]

    r = requests.post(
        f"{API}/super-admin/companies",
        headers={"Authorization": f"Bearer {sa_tok}"},
        json={
            "name": blueprint["name"],
            "email": blueprint["email"],
            "admin_password": blueprint["password"],
        },
    )
    r.raise_for_status()
    tid = r.json()["id"]
    step(f"created tenant {tid[:8]}… ({blueprint['name']})")
    return tid


def ensure_secondary_admin(client_db, sa_tok: str, company_id: str, blueprint: dict):
    """Idempotent: skip if already exists. Also clears `password_change_required`
    so the demo creds work without going through /change-password."""
    if client_db.local_admins.find_one(
        {"email": blueprint["secondary_admin_email"]}, {"_id": 0, "id": 1}
    ):
        step("secondary admin already present")
        return

    r = requests.post(
        f"{API}/super-admin/companies/{company_id}/admins",
        headers={"Authorization": f"Bearer {sa_tok}"},
        json={
            "email": blueprint["secondary_admin_email"],
            "initial_password": blueprint["secondary_admin_password"],
        },
    )
    r.raise_for_status()
    step(f"added secondary admin → {blueprint['secondary_admin_email']}")


def clear_forced_password_change(client_db, blueprint: dict):
    """Demo creds should "just work" — turn off the forced-change flag on
    the admin rows we just seeded. In production we'd let the operator
    go through /change-password normally."""
    res = client_db.local_admins.update_many(
        {"email": {"$in": [blueprint["email"], blueprint["secondary_admin_email"]]}},
        {"$set": {"password_change_required": False}},
    )
    if res.modified_count:
        step(f"cleared password_change_required on {res.modified_count} admin row(s)")


def upsert_channel_mapping(sa_tok: str, channel_type: str, external_id: str,
                           company_id: str, note: str):
    r = requests.put(
        f"{API}/super-admin/channel-mappings/{channel_type}/{external_id}",
        headers={"Authorization": f"Bearer {sa_tok}"},
        json={"company_id": company_id, "metadata": {"note": note}},
    )
    r.raise_for_status()
    step(f"channel mapping {channel_type}:{external_id} → tenant {company_id[:8]}…")


def upsert_bot_config(sa_tok: str, company_id: str, blueprint: dict):
    r = requests.put(
        f"{API}/super-admin/bot-config/{company_id}",
        headers={"Authorization": f"Bearer {sa_tok}"},
        json={
            "bot_name": f"{blueprint['name']} Bot",
            "org_name": blueprint["name"],
            "contact": {
                "phone": "+27 11 555 9999",
                "email": blueprint["email"],
                "office_hours": "Mon–Fri 09:00–17:00",
            },
            "branding": {
                "primary_color":   blueprint["branding_color"],
                "secondary_color": "#FF6F00",
            },
            "supported_languages": [
                {"code": "en", "name": "English"},
                {"code": "hi", "name": "Hindi"},
            ],
            "default_language": "en",
        },
    )
    r.raise_for_status()
    step(f"bot config upserted (primary={blueprint['branding_color']})")


def upsert_service(sa_tok: str, company_id: str, body: dict):
    """POST if missing, PUT to update."""
    url_get = f"{API}/super-admin/services/{company_id}/{body['service_key']}"
    h = {"Authorization": f"Bearer {sa_tok}"}
    exists = requests.get(url_get, headers=h).status_code == 200
    if exists:
        # PUT: drop service_key (immutable)
        put_body = {k: v for k, v in body.items() if k != "service_key"}
        r = requests.put(url_get, headers=h, json=put_body)
    else:
        r = requests.post(
            f"{API}/super-admin/services/{company_id}",
            headers=h, json=body,
        )
    r.raise_for_status()


def upsert_services(sa_tok: str, company_id: str, name: str):
    """Three services per tenant exercising the three step types."""
    services = [
        # 1. Plain INPUT-only
        {
            "service_key": "passport",
            "name": "Passport Services",
            "description": f"{name} — passport renewal / re-issue.",
            "category": "TYPE_A",
            "enabled": True,
            "display_order": 0,
            "documents": ["Current passport", "Proof of residence", "Recent photo"],
            "fields": [
                {"key": "full_name",       "type": "input", "question": "Please enter your **full name**:"},
                {"key": "dob",             "type": "input", "question": "Date of birth (DD/MM/YYYY):"},
                {"key": "passport_number", "type": "input", "question": "Current passport number:"},
                {"key": "phone",           "type": "input", "question": "Phone:"},
                {"key": "email",           "type": "input", "question": "Email:"},
            ],
        },
        # 2. Has a CONDITIONAL step — short-circuits for SA nationals
        {
            "service_key": "visa",
            "name": "Indian Visa",
            "description": "Visa is free for SA nationals — short flow.",
            "category": "TYPE_A",
            "enabled": True,
            "display_order": 1,
            "documents": ["Valid foreign passport", "Travel itinerary"],
            "fields": [
                {"key": "nationality", "type": "input", "question": "What is your **nationality**?"},
                {
                    "key": "skip_if_sa", "type": "conditional",
                    "condition": {"field": "nationality", "in": ["south african", "south africa"]},
                    "on_match": "skip_to_docs",
                    "on_no_match": "continue",
                },
                {"key": "full_name",    "type": "input", "question": "Full name:"},
                {"key": "passport_number", "type": "input", "question": "Passport number:"},
                {"key": "travel_dates", "type": "input", "question": "Travel dates (DD/MM/YYYY – DD/MM/YYYY):"},
            ],
        },
        # 3. Has an API_CALL step — verifies the passport via a public echo URL
        {
            "service_key": "verify",
            "name": "Verify Passport",
            "description": "Demo: hits a public echo endpoint to simulate verification.",
            "category": "TYPE_A",
            "enabled": True,
            "display_order": 2,
            "documents": ["Passport copy"],
            "fields": [
                {"key": "passport_number", "type": "input", "question": "Passport number:"},
                {
                    "key": "verify_call", "type": "api_call",
                    "api_config": {
                        "method": "GET",
                        "url": "https://httpbin.org/anything/{{passport_number}}",
                        "timeout_seconds": 10,
                        "store_response_as": "verify_result",
                    },
                },
                {"key": "full_name", "type": "input", "question": "Full name (as on passport):"},
            ],
        },
    ]
    for svc in services:
        upsert_service(sa_tok, company_id, svc)
    step(f"upserted {len(services)} services (input / conditional / api_call mix)")


def upsert_scraper(sa_tok: str, company_id: str, blueprint: dict):
    r = requests.put(
        f"{API}/super-admin/scrapers/{company_id}",
        headers={"Authorization": f"Bearer {sa_tok}"},
        json={
            "enabled":         True,
            "seed_urls":       [blueprint["scraper_seed"]],
            "allowed_domains": [blueprint["scraper_seed"].split("//")[1]],
            "max_depth":       2,
            "max_pages":       50,
            "concurrency":     3,
            "fetch_delay_ms":  500,
            "respect_robots":  True,
            "use_sitemap":     True,
            "use_playwright":  False,
        },
    )
    r.raise_for_status()
    step(f"scraper config seeded ({blueprint['scraper_seed']})")


def upsert_knowledge(sa_tok: str, company_id: str, name: str, db):
    """Two demo knowledge entries per tenant. Uses /admin/knowledge so the
    entry carries company_id (Sprint 4 audit + Sprint 14 hardening)."""
    h = {"Authorization": f"Bearer {sa_tok}"}
    samples = [
        {
            "category": "general",
            "title":    f"{name} — Office hours",
            "question": "What are your office hours?",
            "answer":   f"{name} is open Monday to Friday from 09:00 to 17:00. Demo seed entry.",
            "keywords": ["hours", "timing", "office"],
            "source":   "demo_seed",
        },
        {
            "category": "passport",
            "title":    f"{name} — Passport renewal demo",
            "question": "How do I renew my passport?",
            "answer":   "Apply online, then submit documents in person. Demo seed entry.",
            "keywords": ["passport", "renewal"],
            "source":   "demo_seed",
        },
    ]
    # Skip entries that already exist (match on title within the tenant)
    titles_existing = {
        r["title"]
        for r in db.knowledge_base.find(
            {"company_id": company_id, "title": {"$in": [s["title"] for s in samples]}},
            {"_id": 0, "title": 1},
        )
    }
    created = 0
    for s in samples:
        if s["title"] in titles_existing:
            continue
        r = requests.post(
            f"{API}/admin/knowledge?company_id={company_id}",
            headers=h, json=s,
        )
        r.raise_for_status()
        created += 1
    step(f"knowledge entries: {created} created, {len(titles_existing)} reused")


def seed_chat_session(db, company_id: str, name: str):
    """Insert a fake chat session straight into Mongo so Conversations +
    Audit tabs have content. Goes through the DB (not the bot) to keep
    the seed deterministic + cheap."""
    sess_id = f"demo_seed::{company_id}"
    if db.chat_sessions.find_one({"id": sess_id}, {"_id": 0, "id": 1}):
        step("chat session already present")
        return
    now = datetime.now(timezone.utc).isoformat()
    db.chat_sessions.insert_one({
        "id": sess_id,
        "company_id": company_id,
        "channel": "web",
        "user_identifier": "demo_user",
        "created_at": now,
        "last_activity": now,
        "is_active": False,
        "messages": [
            {"role": "user",      "content": f"Hello {name}, what services do you offer?",
             "timestamp": now},
            {"role": "assistant", "content": "Demo seed reply: passport, visa, and document verification.",
             "timestamp": now},
        ],
    })
    step(f"chat session seeded ({sess_id[:24]}…)")


def revoke_demo_admin_tokens(sa_tok: str, company_id: str, blueprint: dict):
    """Demonstrates the Sprint-14 revoke endpoint. We blacklist the
    secondary admin for tenant B so the UI shows a meaningful audit
    row (warning severity)."""
    h = {"Authorization": f"Bearer {sa_tok}"}
    admins = requests.get(
        f"{API}/super-admin/companies/{company_id}/admins", headers=h
    ).json()["admins"]
    sec = next(
        (a for a in admins if a["email"] == blueprint["secondary_admin_email"]),
        None,
    )
    if not sec:
        return
    r = requests.post(
        f"{API}/super-admin/companies/{company_id}/admins/{sec['id']}/revoke-tokens",
        headers=h,
    )
    if r.ok:
        step(f"revoked tokens for secondary admin (demo)")


# ── cleanup ─────────────────────────────────────────────────────────────────
def cleanup_all():
    client = mongo()
    db = client[os.environ.get("DB_NAME", "seva_setu")]
    emails  = [t["email"] for t in TENANTS]
    sec_e   = [t["secondary_admin_email"] for t in TENANTS]
    wa_nums = [t["wa_number"] for t in TENANTS]
    seeds   = [t["scraper_seed"] for t in TENANTS]

    cids = [c["id"] for c in db.companies.find({"email": {"$in": emails}}, {"_id": 0, "id": 1})]
    print(f"→ removing {len(cids)} tenant(s) and their data: {cids}")

    db.local_admins.delete_many({"email": {"$in": emails + sec_e}})
    db.companies.delete_many({"email": {"$in": emails}})
    # 2FA challenge rows accrue on every seed run (one per console login,
    # incl. the super-admin) — drop the ones for our demo + SA emails.
    db.login_otp_tokens.delete_many({"email": {"$in": emails + sec_e + [SA_EMAIL]}})

    if cids:
        db.tenant_services.delete_many({"company_id": {"$in": cids}})
        db.tenant_bot_config.delete_many({"company_id": {"$in": cids}})
        db.scraper_config.delete_many({"company_id": {"$in": cids}})
        db.knowledge_base.delete_many({"company_id": {"$in": cids}, "source": "demo_seed"})
        db.chat_sessions.delete_many({"id": {"$regex": "^demo_seed::"}})
        db.invalidated_tokens.delete_many({"company_id": {"$in": cids}})
        db.messaging_channel_map.delete_many({"external_id": {"$in": wa_nums}})
        # New crawler collections — only populated if a demo crawl was run,
        # but scope-delete them so --cleanup leaves nothing behind.
        db.crawler_runs.delete_many({"company_id": {"$in": cids}})
        db.crawler_pages.delete_many({"company_id": {"$in": cids}})
        db.crawler_frontier.delete_many({"company_id": {"$in": cids}})

    print("✅ cleanup complete")
    client.close()


# ── main ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cleanup", action="store_true",
                        help="Remove every demo row created by this script.")
    args = parser.parse_args()

    if args.cleanup:
        cleanup_all()
        return

    # Health check
    try:
        r = requests.get(f"http://localhost:{os.environ.get('SERVER_PORT','8000')}/", timeout=2)
        r.raise_for_status()
    except Exception as exc:
        print(f"❌ Backend not reachable at port {os.environ.get('SERVER_PORT','8000')}: {exc}")
        sys.exit(1)

    print("→ Authenticating as super-admin")
    sa_tok = sa_token()
    step(f"got token ({len(sa_tok)} chars)")

    client = mongo()
    db = client[os.environ.get("DB_NAME", "seva_setu")]

    for blueprint in TENANTS:
        header(f"Tenant: {blueprint['name']}")
        tid = get_or_create_tenant(db, sa_tok, blueprint)

        ensure_secondary_admin(db, sa_tok, tid, blueprint)
        clear_forced_password_change(db, blueprint)

        upsert_channel_mapping(sa_tok, "ics_waba", blueprint["wa_number"], tid,
                               note=f"demo seed for {blueprint['name']}")
        upsert_bot_config(sa_tok, tid, blueprint)
        upsert_services(sa_tok, tid, blueprint["name"])
        upsert_scraper(sa_tok, tid, blueprint)
        upsert_knowledge(sa_tok, tid, blueprint["name"], db)
        seed_chat_session(db, tid, blueprint["name"])

    # One revoke for tenant B's secondary admin
    header("Sprint-14 demo: revoke tokens for tenant B's secondary admin")
    tid_b = db.companies.find_one({"email": TENANTS[1]["email"]}, {"_id": 0, "id": 1})["id"]
    revoke_demo_admin_tokens(sa_tok, tid_b, TENANTS[1])

    # Print credentials summary
    header("Demo credentials")
    print(f"  Super-admin:        {SA_EMAIL} / {SA_PASS}")
    for t in TENANTS:
        print(f"\n  Tenant: {t['name']}")
        print(f"    Primary admin:    {t['email']} / {t['password']}")
        print(f"    Secondary admin:  {t['secondary_admin_email']} / {t['secondary_admin_password']}")
        if t == TENANTS[1]:
            print("                      (this one has its tokens revoked — re-login required)")

    print("\n  Tip: run `python seed_demo_data.py --cleanup` to remove all demo data.")
    client.close()


if __name__ == "__main__":
    main()
