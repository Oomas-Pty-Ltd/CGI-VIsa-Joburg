"""Crawler CLI.

Usage:
    cd backend

    # 1. Bootstrap config for a tenant (one-time, or to update settings)
    python -m crawler.main init \\
        --company-id <UUID> \\
        --seed-url https://www.example.com/ \\
        --allowed-domain www.example.com \\
        --max-depth 3 --max-pages 500

    # 2. Run a crawl
    python -m crawler.main run --company-id <UUID>

    # 3. Inspect last run
    python -m crawler.main show --company-id <UUID>

Cron / K8s CronJob just invokes `run`.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from database import get_database

from .config import load_config, upsert_config
from .runner import run_crawl

logger = logging.getLogger("crawler.main")


# ── run ─────────────────────────────────────────────────────────────────────

async def _cmd_run(args: argparse.Namespace) -> int:
    result = await run_crawl(args.company_id, triggered_by=args.trigger)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("status") == "success" else 1


# ── init ────────────────────────────────────────────────────────────────────

async def _cmd_init(args: argparse.Namespace) -> int:
    # Allowed domains: explicit list, or derived from seed URLs if not provided.
    if args.allowed_domain:
        allowed = list(args.allowed_domain)
    else:
        from urllib.parse import urlparse
        allowed = sorted({urlparse(u).netloc for u in args.seed_url if u})

    fields = {
        "seed_urls":       list(args.seed_url),
        "allowed_domains": allowed,
        "max_depth":       args.max_depth,
        "max_pages":       args.max_pages,
        "use_playwright":  args.use_playwright,
        "respect_robots":  args.respect_robots,
        "use_sitemap":     args.use_sitemap,
        "concurrency":     args.concurrency,
        "fetch_delay_ms":  args.fetch_delay_ms,
        "enabled":         True,
    }
    if args.user_agent:
        fields["user_agent"] = args.user_agent
    if args.schedule_cron:
        fields["schedule_cron"] = args.schedule_cron

    doc = await upsert_config(args.company_id, **fields)
    print(json.dumps(doc, indent=2, default=str))
    return 0


# ── show ────────────────────────────────────────────────────────────────────

async def _cmd_show(args: argparse.Namespace) -> int:
    cfg = await load_config(args.company_id)
    db = await get_database()
    raw = await db.scraper_config.find_one({"company_id": args.company_id}, {"_id": 0})

    print(f"\n=== scraper_config (company_id={args.company_id}) ===")
    if not raw:
        print("(no row yet — using defaults; run `init` to create one)")
    else:
        print(json.dumps({
            "enabled":         cfg.enabled,
            "seed_urls":       cfg.seed_urls,
            "allowed_domains": sorted(cfg.allowed_domains),
            "max_depth":       cfg.max_depth,
            "max_pages":       cfg.max_pages,
            "include_patterns":[p.pattern for p in cfg.include_patterns],
            "exclude_patterns":[p.pattern for p in cfg.exclude_patterns],
            "respect_robots":  cfg.respect_robots,
            "use_sitemap":     cfg.use_sitemap,
            "concurrency":     cfg.concurrency,
            "fetch_delay_ms":  cfg.fetch_delay_ms,
            "use_playwright":  cfg.use_playwright,
            "user_agent":      cfg.user_agent,
            "last_run_id":     raw.get("last_run_id"),
            "last_run_status": raw.get("last_run_status"),
            "last_run_at":     raw.get("last_run_at"),
            "last_run_summary":raw.get("last_run_summary"),
        }, indent=2, default=str))

    runs = await db.crawler_runs.find(
        {"company_id": args.company_id},
        {"_id": 0, "run_id": 1, "status": 1, "started_at": 1, "finished_at": 1, "triggered_by": 1, "summary.counts": 1},
    ).sort("started_at", -1).limit(5).to_list(5)

    print(f"\n=== last {len(runs)} crawler_runs ===")
    for r in runs:
        print(json.dumps(r, indent=2, default=str))
    return 0


# ── argparse ────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="crawler", description=__doc__)
    parser.add_argument("--log-level", default="INFO")

    sub = parser.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("run", help="Run a crawl for one tenant")
    pr.add_argument("--company-id", required=True)
    pr.add_argument("--trigger", default="manual",
                    help="Audit tag: manual | cron | api (default: manual)")

    pi = sub.add_parser("init", help="Create / update scraper_config for one tenant")
    pi.add_argument("--company-id", required=True)
    pi.add_argument("--seed-url", action="append", required=True,
                    help="May be repeated for multiple seeds.")
    pi.add_argument("--allowed-domain", action="append",
                    help="May be repeated; defaults to hosts of seed URLs.")
    pi.add_argument("--max-depth", type=int, default=3)
    pi.add_argument("--max-pages", type=int, default=500)
    pi.add_argument("--concurrency", type=int, default=4)
    pi.add_argument("--fetch-delay-ms", type=int, default=500)
    pi.add_argument("--use-playwright", action="store_true", default=False)
    pi.add_argument("--no-respect-robots", dest="respect_robots", action="store_false", default=True)
    pi.add_argument("--no-sitemap", dest="use_sitemap", action="store_false", default=True)
    pi.add_argument("--user-agent")
    pi.add_argument("--schedule-cron",
                    help="Cron expression for the scheduler (read by deployment cron, not by this CLI).")

    ps = sub.add_parser("show", help="Print scraper_config + last 5 runs for a tenant")
    ps.add_argument("--company-id", required=True)

    return parser


_DISPATCH = {
    "run":  _cmd_run,
    "init": _cmd_init,
    "show": _cmd_show,
}


def main() -> int:
    args = _build_parser().parse_args()
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    return asyncio.run(_DISPATCH[args.cmd](args))


if __name__ == "__main__":
    sys.exit(main())
