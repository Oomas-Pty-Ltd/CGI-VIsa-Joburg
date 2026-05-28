from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Get MongoDB connection details with proper error handling
mongo_url = os.environ.get('MONGO_URL')
db_name = os.environ.get('DB_NAME')

if not mongo_url:
    raise RuntimeError("MONGO_URL environment variable is required")
if not db_name:
    raise RuntimeError("DB_NAME environment variable is required")

# Connection pooling configuration
client = AsyncIOMotorClient(
    mongo_url,
    maxPoolSize=50,  # Maximum connections in the pool
    minPoolSize=10,  # Minimum connections to maintain
    maxIdleTimeMS=30000,  # Close idle connections after 30s
    waitQueueTimeoutMS=10000,  # Timeout waiting for available connection
    serverSelectionTimeoutMS=5000  # Timeout for server selection
)
db = client[db_name]

async def get_database():
    return db


async def create_indexes():
    """Create database indexes for performance optimization"""
    try:
        # User indexes
        await db.users.create_index("id", unique=True)
        await db.users.create_index("email", unique=True, sparse=True)
        await db.users.create_index("phone", sparse=True)
        
        # Session indexes
        await db.chat_sessions.create_index("id", unique=True)
        await db.chat_sessions.create_index("user_id")
        await db.chat_sessions.create_index("session_id")
        await db.chat_sessions.create_index("created_at")
        await db.chat_sessions.create_index("company_id")
        await db.chat_sessions.create_index([("company_id", 1), ("created_at", -1)])
        await db.chat_sessions.create_index([("user_id", 1), ("created_at", -1)])
        
        # Document indexes
        await db.documents.create_index("id", unique=True)
        await db.documents.create_index("user_id")
        await db.documents.create_index("expiry_status")
        await db.documents.create_index("next_check_date")
        
        # Feedback indexes
        await db.feedback.create_index("id", unique=True)
        await db.feedback.create_index("session_id")
        await db.feedback.create_index("user_id")
        await db.feedback.create_index("created_at")
        
        # Notification indexes
        await db.notifications.create_index("id", unique=True)
        await db.notifications.create_index("user_id")
        await db.notifications.create_index([("user_id", 1), ("status", 1)])
        await db.notifications.create_index("scheduled_at")
        
        # Audit log indexes
        await db.audit_logs.create_index("id", unique=True)
        await db.audit_logs.create_index("user_id")
        await db.audit_logs.create_index("company_id")
        await db.audit_logs.create_index("timestamp")
        await db.audit_logs.create_index([("category", 1), ("timestamp", -1)])
        await db.audit_logs.create_index([("user_id", 1), ("timestamp", -1)])
        await db.audit_logs.create_index([("company_id", 1), ("timestamp", -1)])
        
        # Escalation indexes
        await db.escalations.create_index("id", unique=True)
        await db.escalations.create_index("status")
        await db.escalations.create_index("priority")
        await db.escalations.create_index([("status", 1), ("created_at", -1)])
        
        # Knowledge base indexes
        await db.knowledge_base.create_index("id", unique=True)
        await db.knowledge_base.create_index("category")
        await db.knowledge_base.create_index([("title", "text"), ("question", "text"), ("answer", "text")])
        # Multi-tenant + crawler upsert keys
        await db.knowledge_base.create_index(
            [("company_id", 1), ("url_hash", 1)],
            unique=True,
            partialFilterExpression={"url_hash": {"$exists": True}},
        )
        await db.knowledge_base.create_index([("company_id", 1), ("category", 1)])
        await db.knowledge_base.create_index([("company_id", 1), ("status", 1)])
        await db.knowledge_base.create_index([("company_id", 1), ("updated_at", -1)])

        # Crawler frontier (BFS queue, one row per URL per run)
        await db.crawler_frontier.create_index("id", unique=True)
        await db.crawler_frontier.create_index(
            [("company_id", 1), ("run_id", 1), ("url_hash", 1)],
            unique=True,
        )
        await db.crawler_frontier.create_index([("company_id", 1), ("run_id", 1), ("status", 1)])
        await db.crawler_frontier.create_index([("status", 1), ("depth", 1), ("discovered_at", 1)])
        await db.crawler_frontier.create_index("finished_at", expireAfterSeconds=2592000)  # 30-day TTL

        # Crawler runs (one row per crawl invocation)
        await db.crawler_runs.create_index("run_id", unique=True)
        await db.crawler_runs.create_index([("company_id", 1), ("started_at", -1)])
        await db.crawler_runs.create_index([("company_id", 1), ("status", 1)])

        # Per-page crawl records (raw HTML, extracted content, processing
        # artifacts, logs, status — one row per URL per run).
        await db.crawler_pages.create_index(
            [("company_id", 1), ("run_id", 1), ("url_hash", 1)], unique=True,
        )
        await db.crawler_pages.create_index([("company_id", 1), ("run_id", 1), ("status", 1)])
        await db.crawler_pages.create_index([("company_id", 1), ("url_hash", 1)])

        # Per-tenant scraper config
        await db.scraper_config.create_index("company_id", unique=True)

        # Notification settings (one per scenario_key) + delivery log
        await db.notification_settings.create_index("scenario_key", unique=True)
        await db.notification_log.create_index([("created_at", -1)])
        await db.notification_log.create_index([("scenario_key", 1), ("company_id", 1), ("status", 1), ("created_at", -1)])
        await db.notification_log.create_index("created_at", expireAfterSeconds=7776000)  # 90-day TTL

        # Schema migrations registry. The unique index doubles as a
        # multi-replica lock (whichever replica wins the insert owns the run).
        await db.schema_migrations.create_index("version", unique=True)

        # ── Multi-tenant scope indexes (Sprint 1A) ───────────────────────────
        # company_id is backfilled on existing rows via migration 0002.
        # Existing single-field uniques (email, phone_hash, reference_id, etc.)
        # are intentionally left as-is — evolving them to compound uniques is
        # a separate migration once we audit cross-tenant collisions.
        await db.users.create_index("company_id")
        await db.users.create_index([("company_id", 1), ("email", 1)])

        await db.documents.create_index("company_id")
        await db.documents.create_index([("company_id", 1), ("user_id", 1)])

        await db.feedback.create_index("company_id")
        await db.feedback.create_index([("company_id", 1), ("created_at", -1)])

        await db.notifications.create_index("company_id")
        await db.notifications.create_index([("company_id", 1), ("user_id", 1), ("status", 1)])

        await db.escalations.create_index("company_id")
        await db.escalations.create_index([("company_id", 1), ("status", 1), ("created_at", -1)])

        await db.applications.create_index("company_id")
        await db.applications.create_index([("company_id", 1), ("user_id", 1), ("created_at", -1)])
        await db.applications.create_index([("company_id", 1), ("status", 1)])

        await db.seva_setu_applications.create_index("company_id")
        await db.seva_setu_applications.create_index([("company_id", 1), ("user_id", 1), ("created_at", -1)])

        await db.seva_setu_users.create_index("company_id")
        # Compound (company_id, email) is created as UNIQUE in migration 0003
        # — do not also declare it here non-unique, or the next startup will
        # try to overwrite the unique index with a weaker one.

        await db.whatsapp_sessions.create_index("company_id")
        await db.whatsapp_sessions.create_index([("company_id", 1), ("last_message_at", -1)])

        await db.ics_whatsapp_sessions.create_index("company_id")
        await db.ics_whatsapp_sessions.create_index([("company_id", 1), ("updated_at", -1)])

        # Channel → tenant resolver lookup. Used by WhatsApp/Facebook webhooks
        # to figure out which company owns an inbound message. Schema lives
        # but the resolver is hardcoded to a default tenant until Sprint 5.
        await db.messaging_channel_map.create_index(
            [("channel_type", 1), ("external_id", 1)],
            unique=True,
        )
        await db.messaging_channel_map.create_index("company_id")

        # ── Messaging collections (Sprint 2D) ────────────────────────────────
        # company_id is backfilled on existing rows via migration 0004.
        # Existing single-field uniques on phone_number/phone_hash kept as-is
        # (the same user phone can only ever speak to one tenant today since
        # the channel resolver is hardcoded). When per-channel mapping ships,
        # these may need to become compound (company_id, phone_number) uniques.
        await db.whatsapp_users.create_index("company_id")
        await db.whatsapp_users.create_index([("company_id", 1), ("phone_number", 1)])

        await db.whatsapp_messages.create_index("company_id")
        await db.whatsapp_messages.create_index([("company_id", 1), ("phone_number", 1), ("timestamp", -1)])
        await db.whatsapp_messages.create_index([("company_id", 1), ("session_id", 1)])

        await db.facebook_users.create_index("company_id")
        await db.facebook_users.create_index([("company_id", 1), ("fb_id", 1)])

        await db.facebook_messages.create_index("company_id")
        await db.facebook_messages.create_index([("company_id", 1), ("fb_id", 1), ("timestamp", -1)])
        await db.facebook_messages.create_index([("company_id", 1), ("session_id", 1)])

        await db.ics_whatsapp_messages.create_index("company_id")
        await db.ics_whatsapp_messages.create_index([("company_id", 1), ("phone_number", 1), ("timestamp", -1)])

        # Templates — tenant-scoped custom templates + global system templates
        # (the latter have no company_id). See template_routes.py for the
        # visibility rules.
        await db.templates.create_index("company_id")
        await db.templates.create_index([("company_id", 1), ("category", 1), ("name", 1)])

        # Bot identity, branding, and tenant-specific config. One row per
        # tenant. Seed for the default tenant is created by migration 0005.
        # See services/bot_config.py for the read-with-defaults helper.
        await db.tenant_bot_config.create_index("company_id", unique=True)

        # Tenant services — per-tenant service catalogue. One row per
        # (tenant, service_key). Drives the conversational application flow
        # (replaces the hardcoded SERVICES dict in services/application_flow.py).
        # Seeded for the default tenant by migration 0006.
        await db.tenant_services.create_index(
            [("company_id", 1), ("service_key", 1)], unique=True,
        )
        await db.tenant_services.create_index([("company_id", 1), ("display_order", 1)])
        await db.tenant_services.create_index([("company_id", 1), ("enabled", 1)])
        
        # WhatsApp session indexes
        await db.whatsapp_sessions.create_index("phone_hash", unique=True)
        await db.whatsapp_sessions.create_index("session_id")
        await db.whatsapp_sessions.create_index("last_message_at")
        
        # ICS WABA indexes
        await db.ics_whatsapp_sessions.create_index("phone_number", unique=True)
        await db.ics_whatsapp_sessions.create_index("updated_at")
        await db.ics_whatsapp_messages.create_index("phone_number")
        await db.ics_whatsapp_messages.create_index("timestamp")
        await db.ics_whatsapp_messages.create_index("ics_mid", sparse=True)

        # Rate limit indexes — distributed fixed-window counters (see
        # security/rate_limiter.py). `key` = "<dim>:<id>:<window_start>" (unique
        # so concurrent upserts dedup to one doc); TTL on `expires_at` evicts
        # old windows automatically.
        await db.rate_limits.create_index("key", unique=True)
        await db.rate_limits.create_index("expires_at", expireAfterSeconds=0)  # TTL index
        
        # Token invalidation indexes
        await db.invalidated_tokens.create_index("user_id")
        await db.invalidated_tokens.create_index("invalidated_at")
        # Sprint-14: verify_token reads (user_id, company_id) sorted by
        # invalidated_at desc. Compound index keeps the auth hot path fast.
        await db.invalidated_tokens.create_index(
            [("user_id", 1), ("company_id", 1), ("invalidated_at", -1)]
        )
        
        # Data requests (GDPR)
        await db.data_requests.create_index("id", unique=True)
        await db.data_requests.create_index("user_id")
        await db.data_requests.create_index([("user_id", 1), ("request_type", 1)])

        # Application tracking indexes
        await db.applications.create_index("id", unique=True)
        await db.applications.create_index("tracking_id", unique=True)
        await db.applications.create_index("session_id")
        await db.applications.create_index("user_id")
        await db.applications.create_index("service")
        await db.applications.create_index("status")
        await db.applications.create_index([("user_id", 1), ("created_at", -1)])
        await db.applications.create_index([("status", 1), ("created_at", -1)])

        # ── Seva Setu auth + application indexes ──────────────────────────
        await db.seva_setu_users.create_index("id", unique=True)
        # No standalone `email` index — the compound (company_id, email) unique
        # from migration 0003 serves all email lookups (all callers scope by
        # company_id now). A standalone index would conflict on first startup
        # because the OLD `email_1` unique is dropped LATER by the migration.

        await db.otp_tokens.create_index("id", unique=True)
        await db.otp_tokens.create_index("email")
        await db.otp_tokens.create_index("expires_at", expireAfterSeconds=0)

        await db.seva_setu_sessions.create_index("session_id", unique=True)
        await db.seva_setu_sessions.create_index("user_id")
        await db.seva_setu_sessions.create_index("last_active")

        await db.seva_setu_applications.create_index("id", unique=True)
        # No standalone `reference_id` index — the compound (company_id,
        # reference_id) unique from migration 0003 is the only constraint and
        # no code does a global reference_id lookup. Same name-conflict risk
        # as the email index above.
        await db.seva_setu_applications.create_index("user_id")
        await db.seva_setu_applications.create_index("edit_token", sparse=True)
        await db.seva_setu_applications.create_index("status")
        await db.seva_setu_applications.create_index([("user_id", 1), ("created_at", -1)])

        # Response cache (services/response_cache.py) — exact-match FAQ answers
        # keyed by a (company_id, lang, query) hash. The TTL index on
        # expires_at lets Mongo auto-delete stale entries so KB edits propagate
        # within the configured window.
        await db.response_cache.create_index("expires_at", expireAfterSeconds=0)
        await db.response_cache.create_index("company_id")

        # LLM conversation history (emergentintegrations/llm/chat.py). One doc per
        # session_id (_id); the TTL on updated_at auto-expires abandoned sessions
        # so the collection stays bounded (replaces the old in-memory _sessions
        # dict, which never shared across workers and grew without limit).
        await db.llm_chat_sessions.create_index("updated_at", expireAfterSeconds=604800)  # 7 days

        logger.info("Database indexes created successfully")
        
    except Exception as e:
        logger.error(f"Failed to create indexes: {e}")
        # Don't raise - allow app to continue without indexes