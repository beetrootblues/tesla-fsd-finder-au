"""
Tesla FSD Finder Australia - Scraper Orchestrator v2.0
=======================================================
v2.0 replaces the old direct-scraping approach (rotating browser
User-Agents + randomised delays against carsales.com.au, drive.com.au,
gumtree.com.au, carsguide.com.au, pickles.com.au, plus a Facebook
Marketplace Apify actor) with discovery.py, which uses Serper.dev's
Google-backed SERP API instead. See discovery.py for the full reasoning.

Pickles.com.au (auction listings) and Facebook Marketplace are dropped
rather than ported: Pickles' inventory is overwhelmingly salvage/insurance
write-offs, a poor fit for "confirm what's actually driveable and road
legal", and Facebook Marketplace has no comparable legitimate search-API
path -- scraping it via a third-party actor carries the same ToS problem
this rewrite removes elsewhere. Re-add either deliberately, eyes open, if
you decide the trade-off is worth it for your use case.

Usage:
    from scrapers import run_all_scrapers
    listings = await run_all_scrapers()
"""

import logging
import re

import discovery

logger = logging.getLogger("scrapers")
logger.setLevel(logging.INFO)


def deduplicate_listings(listings: list[dict]) -> list[dict]:
    """Unchanged from v1.2 -- this logic was never the problem, only the
    fetch mechanism feeding it was."""
    seen: dict[str, dict] = {}

    for listing in listings:
        title_norm = re.sub(r"[^a-z0-9]", "", listing.get("title", "").lower())
        price = listing.get("price") or 0
        state = listing.get("state", "").upper()
        price_bucket = (price // 500) * 500
        key = f"{title_norm[:30]}|{price_bucket}|{state}"

        if key in seen:
            existing = seen[key]
            existing_score = (
                len(existing.get("description", ""))
                + (100 if existing.get("image_url") else 0)
                + (50 if existing.get("odometer", 0) > 0 else 0)
                + (200 if existing.get("detail_page_fetched") else 0)
            )
            new_score = (
                len(listing.get("description", ""))
                + (100 if listing.get("image_url") else 0)
                + (50 if listing.get("odometer", 0) > 0 else 0)
                + (200 if listing.get("detail_page_fetched") else 0)
            )
            if new_score > existing_score:
                seen[key] = listing
        else:
            seen[key] = listing

    deduped = list(seen.values())
    removed = len(listings) - len(deduped)
    if removed:
        logger.info(f"[Dedup] Removed {removed} duplicates")
    return deduped


def get_source_health(listings: list[dict]) -> dict:
    sources = {}
    for listing in listings:
        src = listing.get("source", "Unknown")
        if src not in sources:
            sources[src] = {"count": 0, "status": "ok", "last_listing": ""}
        sources[src]["count"] += 1
        found = listing.get("found_at", "")
        if found > sources[src]["last_listing"]:
            sources[src]["last_listing"] = found
    return sources


async def run_all_scrapers(include_facebook: bool = False, enrich: bool = True) -> list[dict]:
    """
    Signature kept compatible with v1.2's call sites in main.py.
    `include_facebook` is accepted but ignored -- see module docstring.
    `enrich` is accepted but ignored -- discovery.py already does a single
    combined discover+enrich pass per listing rather than a second one.
    """
    logger.info("=" * 60)
    logger.info("Starting discovery run (Serper-based)...")
    logger.info("=" * 60)

    listings = await discovery.run_discovery()
    listings = deduplicate_listings(listings)

    logger.info(f"Discovery + dedup complete: {len(listings)} unique listings")
    return listings
