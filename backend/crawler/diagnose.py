"""Read-only diagnostic: report what's actually in this DB.

Prints:
  - DB name + Mongo URL host
  - List of companies (id, name) — so you know what to pass as --company-id
  - knowledge_base row counts broken down by source/legacy state
  - crawler_frontier / crawler_runs / scraper_config row counts
  - A few sample knowledge_base rows so you can see the shape

Usage:
    python -m crawler.diagnose
"""
from __future__ import annotations

import asyncio
import os
import sys
from urllib.parse import urlparse

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from database import get_database  # noqa: E402


async def diagnose() -> None:
    db = await get_database()

    mongo_url = os.environ.get("MONGO_URL", "")
    parsed = urlparse(mongo_url) if mongo_url else None
    host = f"{parsed.hostname}:{parsed.port}" if parsed and parsed.hostname else "(unknown)"

    print("=" * 70)
    print(f"DB name:    {db.name}")
    print(f"Mongo host: {host}")
    print("=" * 70)

    # Companies
    print("\n[companies]")
    companies = await db.companies.find({}, {"_id": 0, "id": 1, "name": 1, "status": 1}).to_list(50)
    if not companies:
        print("  (no companies — super-admin hasn't created any)")
    else:
        for c in companies:
            print(f"  id={c.get('id')!r:30}  name={c.get('name')!r}  status={c.get('status')!r}")

    # knowledge_base breakdown
    print("\n[knowledge_base]")
    total = await db.knowledge_base.count_documents({})
    with_url_hash = await db.knowledge_base.count_documents({"url_hash": {"$exists": True}})
    legacy_title = await db.knowledge_base.count_documents({"title": {"$regex": r"^\[BGCrawl\] "}})
    legacy_source = await db.knowledge_base.count_documents({"source": {"$regex": r"^background_crawl:"}})
    auto_gen = await db.knowledge_base.count_documents({"auto_generated": True})
    print(f"  total rows:                                {total}")
    print(f"  already migrated (has url_hash):           {with_url_hash}")
    print(f"  legacy: title starts '[BGCrawl] ':         {legacy_title}")
    print(f"  legacy: source starts 'background_crawl:': {legacy_source}")
    print(f"  flagged auto_generated:                    {auto_gen}")

    # Show source-field distribution to expose any other patterns
    print("\n[knowledge_base sources — top 10]")
    pipeline = [
        {"$group": {"_id": "$source", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    async for row in db.knowledge_base.aggregate(pipeline):
        src = row.get("_id")
        src_str = (src[:60] + "…") if isinstance(src, str) and len(src) > 60 else src
        print(f"  {row['count']:>6}  {src_str!r}")

    # A few sample rows
    print("\n[knowledge_base — 3 sample rows]")
    samples = await db.knowledge_base.find(
        {}, {"_id": 0, "id": 1, "title": 1, "source": 1, "company_id": 1, "url_hash": 1, "status": 1}
    ).limit(3).to_list(3)
    for s in samples:
        print(f"  {s}")

    # Crawler collections
    print("\n[crawler collections]")
    for coll in ("crawler_frontier", "crawler_runs", "scraper_config"):
        count = await db[coll].count_documents({})
        print(f"  {coll:20} {count}")

    print()


if __name__ == "__main__":
    asyncio.run(diagnose())
