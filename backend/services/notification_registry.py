"""Catalog of all notification scenarios the platform can emit.

This registry is the single source of truth for *what* notifications exist.
Each scenario declares its metadata, default recipients, default copy
(subject/body with ``{{variable}}`` placeholders), any configurable params
(e.g. a usage threshold), and a sample context used by the "send test"
button. The super-admin UI renders one card per scenario; per-scenario
overrides live in the ``notification_settings`` collection.

Adding a new notification = add one Scenario here + one ``notify(key, …)``
call at the emit point. The UI and config plumbing pick it up automatically.

Recipient roles (resolved at send time by the dispatcher):
  - ``super_admin``  — all platform super-admins
  - ``tenant_admin`` — local admins of the scenario's company_id
  - ``applicant``    — the end user; context must carry ``applicant_email``
  - ``custom``       — the addresses configured on the setting
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

# Categories (display grouping in the UI), ordered.
CATEGORIES = [
    ("tenant", "Tenant lifecycle"),
    ("crawler", "Crawler / Knowledge base"),
    ("llm", "LLM cost & usage"),
    ("application", "Applications"),
    ("security", "Security & ops"),
    ("digest", "Digests"),
]

ROLE_CHOICES = ["super_admin", "tenant_admin", "applicant", "custom"]
SEVERITIES = ["info", "warning", "critical"]


@dataclass
class Scenario:
    key: str
    name: str
    description: str
    category: str
    scope: str                       # "tenant" (context has company_id) | "platform"
    default_recipients: List[str]
    default_subject: str
    default_body: str
    severity: str = "info"
    default_enabled: bool = True
    params: Dict[str, Any] = field(default_factory=dict)   # configurable knobs (e.g. threshold)
    sample_context: Dict[str, Any] = field(default_factory=dict)
    # cooldown protects against floods (e.g. a flapping crawler). 0 = no limit.
    default_cooldown_minutes: int = 0


_S = Scenario  # brevity

SCENARIOS: List[Scenario] = [
    # ── Tenant lifecycle ──────────────────────────────────────────────────
    _S("tenant.created", "Tenant created", "A new tenant + admin account was provisioned.",
       "tenant", "tenant", ["tenant_admin"],
       "Welcome to {{org_name}} on {{platform_name}}",
       "Hi,\n\nYour tenant \"{{tenant_name}}\" is ready. Sign in at {{login_url}} with {{admin_email}} and the password your administrator shared. You'll be asked to set a new password on first login.\n\n— {{platform_name}}",
       severity="info", sample_context={"tenant_name": "Acme Consulate", "admin_email": "admin@acme.test",
                                         "login_url": "https://app.example/login", "org_name": "Acme Consulate"}),
    _S("tenant.status_changed", "Tenant activated / deactivated", "A tenant was activated or deactivated.",
       "tenant", "tenant", ["tenant_admin", "super_admin"],
       "Your tenant is now {{status}}",
       "Tenant \"{{tenant_name}}\" was {{status}} on {{when}}.",
       severity="warning", sample_context={"tenant_name": "Acme Consulate", "status": "deactivated", "when": "2026-05-27"}),
    _S("tenant.admin_added", "Admin/viewer added", "A new admin or viewer was added to a tenant.",
       "tenant", "tenant", ["super_admin"],
       "New {{role}} added to {{tenant_name}}",
       "{{new_email}} was added as {{role}} to tenant \"{{tenant_name}}\".",
       severity="info", sample_context={"tenant_name": "Acme Consulate", "new_email": "viewer@acme.test", "role": "viewer"}),
    _S("tenant.password_reset", "Admin password reset", "An admin password was reset by a super-admin.",
       "tenant", "tenant", ["tenant_admin"],
       "Your password was reset",
       "The password for {{admin_email}} was reset. Sign in at {{login_url}} and set a new password.",
       severity="warning", sample_context={"admin_email": "admin@acme.test", "login_url": "https://app.example/login"}),

    # ── Crawler / Knowledge base ──────────────────────────────────────────
    _S("crawler.run_succeeded", "Crawl succeeded", "A crawl run finished successfully.",
       "crawler", "tenant", ["super_admin"],
       "Crawl complete for {{tenant_name}} — {{pages}} pages",
       "Crawl {{run_id}} finished: {{processed}} processed, {{updated}} updated, {{failed}} failed, {{pages}} total.",
       severity="info", default_enabled=False, sample_context={"tenant_name": "Acme", "run_id": "abc12345", "pages": 16, "processed": 14, "updated": 2, "failed": 2}),
    _S("crawler.run_failed", "Crawl failed", "A crawl run failed or produced no usable pages.",
       "crawler", "tenant", ["super_admin"],
       "Crawl FAILED for {{tenant_name}}",
       "Crawl {{run_id}} failed: {{reason}}. Seeds: {{seeds}}.",
       severity="critical", sample_context={"tenant_name": "Acme", "run_id": "abc12345", "reason": "no_seeds", "seeds": 2}),
    _S("crawler.stale_pages", "Pages went stale / removed", "Crawled pages were marked stale (removed or repeatedly failing).",
       "crawler", "tenant", ["super_admin"],
       "{{count}} page(s) went stale for {{tenant_name}}",
       "{{count}} page(s) were marked stale after repeated failures and removed from the bot's knowledge base.",
       severity="warning", params={"min_count": 1}, sample_context={"tenant_name": "Acme", "count": 3}),

    # ── LLM cost & usage ──────────────────────────────────────────────────
    _S("llm.usage_threshold", "Usage crossed threshold", "A tenant's LLM spend crossed the configured threshold.",
       "llm", "tenant", ["super_admin", "tenant_admin"],
       "{{tenant_name}} hit {{pct}}% of LLM budget",
       "Tenant \"{{tenant_name}}\" has used {{pct}}% of its budget ({{used}} / {{budget}}).",
       severity="warning", params={"threshold_pct": 80}, default_cooldown_minutes=720,
       sample_context={"tenant_name": "Acme", "pct": 82, "used": "$41", "budget": "$50"}),
    _S("llm.budget_exceeded", "Budget exceeded", "A tenant exceeded its LLM budget / hard cap.",
       "llm", "tenant", ["super_admin", "tenant_admin"],
       "{{tenant_name}} EXCEEDED its LLM budget",
       "Tenant \"{{tenant_name}}\" exceeded its budget ({{used}} / {{budget}}). Service may be degraded.",
       severity="critical", default_cooldown_minutes=1440, sample_context={"tenant_name": "Acme", "used": "$53", "budget": "$50"}),
    _S("llm.provider_error", "Provider / key error", "An LLM provider returned auth/availability errors.",
       "llm", "platform", ["super_admin"],
       "LLM provider error: {{provider}}",
       "Provider {{provider}} ({{model}}) returned errors: {{error}}. Check API key / model availability.",
       severity="critical", default_cooldown_minutes=30, sample_context={"provider": "openai", "model": "gpt-5.2", "error": "invalid_api_key"}),
    _S("llm.usage_digest", "Usage digest", "Periodic summary of LLM spend.",
       "llm", "platform", ["super_admin"],
       "LLM usage digest — {{period}}",
       "Total spend {{total}} across {{tenants}} tenants this {{period}}. Top: {{top}}.",
       severity="info", default_enabled=False, default_cooldown_minutes=10080,  # weekly
       sample_context={"period": "week", "total": "$120", "tenants": 4, "top": "Acme ($60)"}),

    # ── Applications ──────────────────────────────────────────────────────
    _S("application.submitted", "Application submitted", "An applicant submitted an application.",
       "application", "tenant", ["applicant"],
       "We received your {{service_name}} application",
       "Hi {{applicant_name}},\n\nWe've received your {{service_name}} application (Ref {{reference_id}}).",
       severity="info", default_enabled=False, sample_context={"applicant_name": "Jane", "service_name": "Passport Renewal", "reference_id": "REF-123", "applicant_email": "jane@test"}),
    _S("application.confirmed", "Application confirmed", "An application was confirmed by the system of record.",
       "application", "tenant", ["applicant"],
       "Your {{service_name}} application is confirmed",
       "Hi {{applicant_name}},\n\nYour {{service_name}} application (Ref {{reference_id}}) is confirmed. Processing ref: {{gov_ref}}.",
       severity="info", default_enabled=False, sample_context={"applicant_name": "Jane", "service_name": "Passport Renewal", "reference_id": "REF-123", "gov_ref": "GOV-XYZ", "applicant_email": "jane@test"}),
    _S("application.submission_failed", "Submission to authority failed", "The external processing service rejected/failed a submission.",
       "application", "tenant", ["super_admin", "tenant_admin"],
       "Submission failed for {{reference_id}}",
       "The processing service failed for application {{reference_id}} ({{service_name}}): {{error}}. It is pending and retryable.",
       severity="critical", sample_context={"reference_id": "REF-123", "service_name": "Passport Renewal", "error": "HTTP 503"}),
    _S("application.stuck_pending", "Application stuck pending", "An application has been in submission_pending too long.",
       "application", "tenant", ["super_admin", "tenant_admin"],
       "{{count}} application(s) stuck pending",
       "{{count}} application(s) have been pending submission for over {{hours}}h. Consider retrying.",
       severity="warning", params={"hours": 24}, sample_context={"count": 2, "hours": 24}),
    _S("application.ocr_failed", "Document OCR failed", "OCR/extraction failed on an uploaded document.",
       "application", "tenant", ["super_admin"],
       "OCR failed for a document on {{reference_id}}",
       "Document \"{{doc_name}}\" on application {{reference_id}} could not be processed by OCR.",
       severity="info", default_enabled=False, sample_context={"reference_id": "REF-123", "doc_name": "Passport"}),

    # ── Security & ops ────────────────────────────────────────────────────
    _S("security.login_lockout", "Failed logins / lockout", "Repeated failed logins for an account.",
       "security", "platform", ["super_admin"],
       "Repeated failed logins for {{email}}",
       "{{attempts}} failed login attempts for {{email}} from {{ip}}.",
       severity="warning", params={"attempts_threshold": 5}, default_cooldown_minutes=15,
       sample_context={"email": "admin@acme.test", "attempts": 6, "ip": "203.0.113.7"}),
    _S("security.guardrail_triggered", "Guardrail / safety triggered", "A safety guardrail blocked content in chat.",
       "security", "tenant", ["super_admin"],
       "Guardrail triggered for {{tenant_name}}",
       "A {{rule}} guardrail blocked a message in tenant \"{{tenant_name}}\".",
       severity="warning", default_enabled=False, default_cooldown_minutes=10,
       sample_context={"tenant_name": "Acme", "rule": "prompt_injection"}),
    _S("chat.escalation_requested", "Human escalation requested", "A chat user asked for a human agent.",
       "security", "tenant", ["tenant_admin"],
       "A user requested a human agent — {{tenant_name}}",
       "A chat user in \"{{tenant_name}}\" requested human escalation. Session: {{session_id}}.",
       severity="warning", sample_context={"tenant_name": "Acme", "session_id": "sess-abc"}),
    _S("ops.webhook_failure", "Channel webhook failure", "A messaging channel webhook failed.",
       "security", "tenant", ["super_admin"],
       "{{channel}} webhook failing for {{tenant_name}}",
       "The {{channel}} webhook for \"{{tenant_name}}\" returned errors: {{error}}.",
       severity="critical", default_enabled=False, default_cooldown_minutes=30,
       sample_context={"channel": "whatsapp", "tenant_name": "Acme", "error": "401 from Meta"}),
    _S("ops.migration_failed", "Migration failed", "A database migration failed at startup.",
       "security", "platform", ["super_admin"],
       "Migration {{version}} FAILED",
       "Migration {{version}} ({{description}}) failed at startup: {{error}}.",
       severity="critical", sample_context={"version": 12, "description": "add notifications", "error": "duplicate key"}),

    # ── Digests ───────────────────────────────────────────────────────────
    _S("digest.activity", "Activity digest", "Periodic platform/tenant activity summary.",
       "digest", "platform", ["super_admin"],
       "Activity digest — {{period}}",
       "This {{period}}: {{conversations}} conversations, {{applications}} applications, {{crawls}} crawls.",
       severity="info", default_enabled=False, default_cooldown_minutes=1440,  # daily
       sample_context={"period": "week", "conversations": 120, "applications": 8, "crawls": 3}),
]

SCENARIOS_BY_KEY: Dict[str, Scenario] = {s.key: s for s in SCENARIOS}


def get_scenario(key: str) -> Scenario | None:
    return SCENARIOS_BY_KEY.get(key)


def scenario_defaults(s: Scenario) -> Dict[str, Any]:
    """The default setting blob for a scenario (used to seed/merge settings)."""
    return {
        "enabled":          s.default_enabled,
        "channels":         ["email"],
        "recipients":       list(s.default_recipients),
        "custom_emails":    [],
        "subject":          s.default_subject,
        "body":             s.default_body,
        "params":           dict(s.params),
        "cooldown_minutes": s.default_cooldown_minutes,
    }
