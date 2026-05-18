"""Per-tenant crawler configuration.

Reads `scraper_config` from Mongo and returns a fully-defaulted
`CrawlerConfig` dataclass. Defaults are baked here so a partially-filled
row from the super-admin UI still produces a runnable config.

`upsert_config()` is exposed for the CLI bootstrap and the super-admin
endpoint (step 5) to share.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from database import get_database

DEFAULTS: dict = {
    "enabled":               True,
    "seed_urls":             [],
    "allowed_domains":       [],
    "max_depth":             3,
    "max_pages":             500,
    "include_patterns":      [],
    "exclude_patterns":      [r"\.pdf$", r"\.jpg$", r"\.png$", r"\.gif$", r"\.zip$"],
    "respect_robots":        True,
    "use_sitemap":           True,
    "fetch_timeout_seconds": 30,
    "fetch_delay_ms":        500,
    "concurrency":           4,
    "use_playwright":        False,
    # Mimic a real browser. Many government/CMS sites 403 anything that
    # identifies as a bot. Override per-tenant via the super-admin UI if a
    # site explicitly requires a named bot.
    "user_agent":            (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "schedule_cron":         None,
}


@dataclass
class CrawlerConfig:
    company_id: str
    enabled: bool
    seed_urls: list[str]
    allowed_domains: set[str]
    max_depth: int
    max_pages: int
    include_patterns: list[re.Pattern] = field(default_factory=list)
    exclude_patterns: list[re.Pattern] = field(default_factory=list)
    respect_robots: bool = True
    use_sitemap: bool = True
    fetch_timeout_seconds: int = 30
    fetch_delay_ms: int = 500
    concurrency: int = 4
    use_playwright: bool = False
    user_agent: str = DEFAULTS["user_agent"]


async def load_config(company_id: str) -> CrawlerConfig:
    """Load + default-merge config for a tenant. Returns even if no row exists
    (caller handles `not cfg.seed_urls` as the "skip this run" condition).
    """
    db = await get_database()
    doc = await db.scraper_config.find_one({"company_id": company_id}, {"_id": 0}) or {}
    merged = {**DEFAULTS, **doc}

    return CrawlerConfig(
        company_id=company_id,
        enabled=bool(merged["enabled"]),
        seed_urls=list(merged["seed_urls"] or []),
        allowed_domains=set(merged["allowed_domains"] or []),
        max_depth=int(merged["max_depth"]),
        max_pages=int(merged["max_pages"]),
        include_patterns=[re.compile(p) for p in (merged["include_patterns"] or [])],
        exclude_patterns=[re.compile(p) for p in (merged["exclude_patterns"] or [])],
        respect_robots=bool(merged["respect_robots"]),
        use_sitemap=bool(merged["use_sitemap"]),
        fetch_timeout_seconds=int(merged["fetch_timeout_seconds"]),
        fetch_delay_ms=int(merged["fetch_delay_ms"]),
        concurrency=int(merged["concurrency"]),
        use_playwright=bool(merged["use_playwright"]),
        user_agent=str(merged["user_agent"]),
    )


async def upsert_config(company_id: str, **fields) -> dict:
    """Upsert a `scraper_config` row. Only the keys passed are written;
    everything else either retains its prior value or falls back to DEFAULTS
    on read. Returns the final stored doc.
    """
    db = await get_database()
    now = datetime.now(timezone.utc).isoformat()

    valid_keys = set(DEFAULTS.keys())
    bad = set(fields) - valid_keys
    if bad:
        raise ValueError(f"Unknown scraper_config fields: {bad}")

    set_doc = {**fields, "updated_at": now}
    insert_doc = {"company_id": company_id, "created_at": now}

    await db.scraper_config.update_one(
        {"company_id": company_id},
        {"$set": set_doc, "$setOnInsert": insert_doc},
        upsert=True,
    )
    return await db.scraper_config.find_one({"company_id": company_id}, {"_id": 0})


async def record_run_summary(
    company_id: str,
    run_id: str,
    status: str,
    summary: dict,
) -> None:
    """Cache the latest run summary on scraper_config for fast UI reads."""
    db = await get_database()
    await db.scraper_config.update_one(
        {"company_id": company_id},
        {"$set": {
            "last_run_id":      run_id,
            "last_run_status":  status,
            "last_run_at":      datetime.now(timezone.utc).isoformat(),
            "last_run_summary": summary,
        }},
    )
