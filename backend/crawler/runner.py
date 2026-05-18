"""Orchestrator: one crawl run, end to end.

  load_config → create crawler_runs row → seed (seed_urls + sitemap)
  → spawn N workers (claim/fetch/parse/upsert/enqueue) → sweep unseen
  → finalize crawler_runs + cache summary on scraper_config.

Workers coordinate via a small in-flight counter so they don't all exit
the moment the frontier momentarily empties — a worker mid-fetch may
still enqueue new links.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from database import get_database

from . import frontier, upsert
from .config import CrawlerConfig, load_config, record_run_summary
from .fetcher import Fetcher, FetchResult
from .parser import parse, filter_links
from .robots import RobotsCache

logger = logging.getLogger("crawler.runner")

RUN_STATUS_RUNNING = "running"
RUN_STATUS_SUCCESS = "success"
RUN_STATUS_FAILED = "failed"
RUN_STATUS_SKIPPED = "skipped"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _create_run(company_id: str, run_id: str, triggered_by: str) -> None:
    db = await get_database()
    await db.crawler_runs.insert_one({
        "run_id":       run_id,
        "company_id":   company_id,
        "status":       RUN_STATUS_RUNNING,
        "triggered_by": triggered_by,
        "started_at":   _now_iso(),
        "finished_at":  None,
        "summary":      {},
    })


async def _finalize_run(run_id: str, status: str, summary: dict) -> None:
    db = await get_database()
    await db.crawler_runs.update_one(
        {"run_id": run_id},
        {"$set": {
            "status":      status,
            "summary":     summary,
            "finished_at": _now_iso(),
        }},
    )


async def _gather_seeds(cfg: CrawlerConfig, robots: RobotsCache) -> list[str]:
    """Seed list = configured seeds + (optional) sitemap discoveries, filtered."""
    seeds: list[str] = list(cfg.seed_urls)
    if cfg.use_sitemap:
        for seed in cfg.seed_urls:
            try:
                seeds.extend(await robots.sitemap_urls(seed))
            except Exception as exc:
                logger.warning("sitemap discovery failed for %s: %s", seed, exc)

    # Dedup while preserving order.
    seen: set[str] = set()
    deduped = []
    for url in seeds:
        if url and url not in seen:
            seen.add(url)
            deduped.append(url)

    filtered = filter_links(
        deduped,
        cfg.allowed_domains,
        cfg.include_patterns,
        cfg.exclude_patterns,
    )
    # Hard cap at max_pages so seeding itself can't blow past it.
    return filtered[:cfg.max_pages]


async def _process_one(
    row: frontier.FrontierRow,
    cfg: CrawlerConfig,
    fetcher: Fetcher,
    counts: Counter,
) -> None:
    """Fetch → parse → upsert → enqueue for one frontier row."""
    try:
        result: FetchResult = await fetcher.fetch(row.url)
    except Exception as exc:
        logger.exception("Unhandled fetch error for %s", row.url)
        await frontier.mark_failed(row.id, None, f"unhandled:{exc}")
        counts["failed"] += 1
        return

    if not result.ok:
        err = result.error or "unknown"
        # Treat policy-driven skips separately from real failures.
        if err.startswith("robots_") or err.startswith("non_html"):
            await frontier.mark_skipped(row.id, err)
            counts["skipped"] += 1
            return
        await frontier.mark_failed(row.id, result.http_status, err)
        counts["failed"] += 1
        # Penalize the KB row (if any) so 404s eventually go stale.
        await upsert.record_failure(cfg.company_id, row.url, result.http_status)
        return

    # Successful fetch — parse and write.
    try:
        parsed = parse(result.html or "", result.final_url)
    except Exception as exc:
        logger.exception("Parse error for %s", row.url)
        await frontier.mark_failed(row.id, result.http_status, f"parse:{exc}")
        counts["failed"] += 1
        return

    page = upsert.PageContent(
        title=parsed.title,
        text=parsed.text,
        language=parsed.language,
        keywords=parsed.keywords,
        category=parsed.category,
    )
    outcome = await upsert.upsert_page(
        cfg.company_id, row.url, page, result.http_status or 200,
    )
    counts[f"upsert_{outcome}"] += 1

    # Enqueue discovered links (filtered).
    accepted = filter_links(
        parsed.links,
        cfg.allowed_domains,
        cfg.include_patterns,
        cfg.exclude_patterns,
    )
    if accepted:
        added = await frontier.enqueue_links(
            run_id=row.run_id,
            company_id=cfg.company_id,
            parent_url=row.url,
            parent_depth=row.depth,
            links=accepted,
            max_depth=cfg.max_depth,
            max_pages=cfg.max_pages,
        )
        counts["enqueued"] += added

    await frontier.mark_success(row.id, result.http_status or 200)
    counts["success"] += 1


async def _worker_loop(
    worker_id: int,
    cfg: CrawlerConfig,
    run_id: str,
    fetcher: Fetcher,
    state: dict,
    counts: Counter,
) -> None:
    """Pull from frontier until both queue is empty AND no peer is in-flight."""
    while True:
        row = await frontier.claim_next(run_id, cfg.company_id)
        if row is None:
            # Nothing to do right now. If no peer worker is mid-fetch, we're done.
            if state["in_flight"] == 0:
                logger.debug("worker %d: frontier drained, exiting", worker_id)
                return
            await asyncio.sleep(0.5)
            continue

        state["in_flight"] += 1
        try:
            await _process_one(row, cfg, fetcher, counts)
        finally:
            state["in_flight"] -= 1


async def run_crawl(company_id: str, triggered_by: str = "manual") -> dict:
    """One full crawl. Returns summary dict including counts + run_id."""
    run_id = str(uuid.uuid4())
    cfg = await load_config(company_id)

    if not cfg.enabled:
        logger.info("Scraper disabled for company=%s — skipping", company_id)
        summary = {"reason": "disabled"}
        await _create_run(company_id, run_id, triggered_by)
        await _finalize_run(run_id, RUN_STATUS_SKIPPED, summary)
        await record_run_summary(company_id, run_id, RUN_STATUS_SKIPPED, summary)
        return {"run_id": run_id, "status": RUN_STATUS_SKIPPED, **summary}

    if not cfg.seed_urls:
        logger.error("No seed_urls in scraper_config for company=%s", company_id)
        summary = {"reason": "no_seed_urls"}
        await _create_run(company_id, run_id, triggered_by)
        await _finalize_run(run_id, RUN_STATUS_FAILED, summary)
        await record_run_summary(company_id, run_id, RUN_STATUS_FAILED, summary)
        return {"run_id": run_id, "status": RUN_STATUS_FAILED, **summary}

    await _create_run(company_id, run_id, triggered_by)
    logger.info(
        "Starting crawl run=%s company=%s seeds=%d max_depth=%d max_pages=%d concurrency=%d",
        run_id, company_id, len(cfg.seed_urls), cfg.max_depth, cfg.max_pages, cfg.concurrency,
    )

    counts: Counter = Counter()
    state = {"in_flight": 0}
    final_status = RUN_STATUS_SUCCESS

    robots = RobotsCache(user_agent=cfg.user_agent, timeout_seconds=cfg.fetch_timeout_seconds)
    try:
        async with Fetcher(
            user_agent=cfg.user_agent,
            timeout_seconds=cfg.fetch_timeout_seconds,
            fetch_delay_ms=cfg.fetch_delay_ms,
            use_playwright=cfg.use_playwright,
            robots=robots,
            respect_robots=cfg.respect_robots,
        ) as fetcher:
            seeds = await _gather_seeds(cfg, robots)
            if not seeds:
                logger.warning("No seeds survived filtering for company=%s", company_id)
                final_status = RUN_STATUS_FAILED
                counts["reason_no_seeds"] = 1
            else:
                await frontier.seed(run_id, company_id, seeds)
                workers = [
                    asyncio.create_task(_worker_loop(i, cfg, run_id, fetcher, state, counts))
                    for i in range(max(cfg.concurrency, 1))
                ]
                await asyncio.gather(*workers, return_exceptions=False)

        # Reconciliation: rows not seen this run get a missed-run penalty.
        # Skip when the run fetched zero pages — likely a transient outage or
        # UA block; we'd otherwise push the whole KB toward stale on every
        # failed run.
        if counts.get("success", 0) > 0:
            seen = await frontier.successful_url_hashes(run_id, company_id)
            sweep = await upsert.sweep_unseen(company_id, seen)
            counts["sweep_missed"] = sweep["missed"]
            counts["sweep_marked_stale"] = sweep["marked_stale"]
        else:
            counts["sweep_skipped"] = 1
            final_status = RUN_STATUS_FAILED

    except Exception as exc:
        logger.exception("Crawl run failed: %s", exc)
        final_status = RUN_STATUS_FAILED
        counts["fatal_error"] = 1
    finally:
        await robots.close()

    frontier_stats = await frontier.run_stats(run_id)
    summary = {
        "frontier":  frontier_stats,
        "counts":    dict(counts),
        "seeds":     len(cfg.seed_urls),
    }
    await _finalize_run(run_id, final_status, summary)
    await record_run_summary(company_id, run_id, final_status, summary)

    logger.info("Crawl run=%s finished status=%s summary=%s", run_id, final_status, summary)
    return {"run_id": run_id, "status": final_status, **summary}
