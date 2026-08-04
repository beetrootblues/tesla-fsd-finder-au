"""
Tesla FSD Finder Australia - Discovery Engine
==============================================
Replaces the old scrapers.py approach of directly fetching carsales.com.au,
drive.com.au, gumtree.com.au, carsguide.com.au, pickles.com.au and Facebook
Marketplace with rotating browser User-Agents and randomised delays.

Why this changed: carsales.com.au's own terms of service explicitly
prohibit "any automated process ... to query, access, retrieve, scrape,
data-mine" their listings, and they run DataDome specifically to detect and
block exactly the kind of traffic the old `_rate_limited_get` was designed
to imitate. Facebook Marketplace scraping via a third-party Apify actor
carries the same problem under Meta's terms. Rotating fake browser
identities to blend in as organic traffic is a materially different thing
from "search the web for what's out there" -- this module does the latter.

Approach:
  1. Ask Serper.dev (a legitimate, ToS-compliant Google SERP API -- Google
     closed its own Custom Search API to new signups) for public search
     results restricted to each site with `site:`. This automates "Google
     it", not "impersonate a browser to get past a bot-wall".
  2. Best-effort, honestly-identified GET of each result's own page for
     full ad text -- one real, descriptive User-Agent (no rotation),
     robots.txt respected, low concurrency, short timeout. Sites that
     block this simply fall back to classifying off the title+snippet
     Google already gave us, which in practice still catches most
     seller-written "MCU2", "FSD", "HW4" mentions, since sellers use them
     to be found.
  3. Hand off to listing_utils.make_listing(), which runs classify.py.

Requires SERPER_API_KEY (get one at https://serper.dev -- 2,500 free
queries, then roughly $1/1,000).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from urllib.parse import urlparse

import httpx

import listing_utils
import vin_check

logger = logging.getLogger("discovery")
logger.setLevel(logging.INFO)

SERPER_API_KEY = os.environ.get("SERPER_API_KEY")
SERPER_URL = "https://google.serper.dev/search"

# Honest self-identification, not a disguise. If a site blocks this, that's
# an expected, acceptable outcome (fall back to snippet-only), not a bug to
# route around with spoofed headers.
USER_AGENT = (
    "TeslaFSDFinderAU/1.0 (+https://github.com/beetrootblues/tesla-fsd-finder-au; "
    "personal research tool, low volume, contact via GitHub issues)"
)

# Expanded in v2.1: the four original marketplaces plus the remaining
# major Australian classifieds/auction platforms, all discovered via the
# same legitimate `site:` SERP search (never direct scraping -- see the
# module docstring). Facebook Marketplace is best-effort: Google indexes
# some public marketplace listings, so a `site:` search is the only
# ToS-compliant way to discover them; most will fall back to snippet-only
# classification, which is fine.
SITES = [
    "carsales.com.au",
    "gumtree.com.au",
    "drive.com.au",
    "carsguide.com.au",
    "cars4sale.com.au",
    "tradingpost.com.au",
    "autotrader.com.au",
    "shannons.com.au",
    "grays.com.au",
    "facebook.com/marketplace",
]

# Display names -- facebook.com/marketplace and cars4sale don't clean up
# with .capitalize(), so map them explicitly.
SOURCE_DISPLAY = {
    "carsales.com.au": "Carsales",
    "gumtree.com.au": "Gumtree",
    "drive.com.au": "Drive",
    "carsguide.com.au": "CarsGuide",
    "cars4sale.com.au": "Cars4Sale",
    "tradingpost.com.au": "Trading Post",
    "autotrader.com.au": "AutoTrader",
    "shannons.com.au": "Shannons",
    "grays.com.au": "Grays",
    "facebook.com/marketplace": "Facebook",
}

MODELS = [("S", "Tesla Model S"), ("3", "Tesla Model 3"), ("X", "Tesla Model X"), ("Y", "Tesla Model Y")]

MAX_DETAIL_FETCHES = int(os.environ.get("MAX_DETAIL_FETCHES", "60"))
DETAIL_TIMEOUT_SECONDS = 8
SERPER_RESULTS_PER_QUERY = 20


def _attribute_queries(model_phrase: str, model_key: str) -> list[str]:
    """Model-aware: MCU only makes sense for S/X, HW4/AI4 only worth
    targeting on 3/Y since AU's S/X never received it."""
    common = [f'{model_phrase} "full self driving"', f"{model_phrase} FSD"]
    if model_key in ("S", "X"):
        return common + [f"{model_phrase} MCU2", f'{model_phrase} "unlimited supercharging"']
    return common + [f"{model_phrase} HW4", f'{model_phrase} "AI4"']


def build_query_plan() -> list[tuple[str, str, str]]:
    """Returns (query, site, model_key) tuples."""
    plan = []
    for site in SITES:
        for model_key, model_phrase in MODELS:
            plan.append((f"site:{site} {model_phrase} for sale", site, model_key))
            for q in _attribute_queries(model_phrase, model_key):
                plan.append((f"site:{site} {q}", site, model_key))
    return plan


def estimate_cost_aud(query_count: int) -> float:
    """Rough estimate at Serper's published ~$1/1,000-query rate, logged for visibility -- not a bill."""
    return round((query_count / 1000) * 1.0 * 1.55, 2)


async def _serper_search(client: httpx.AsyncClient, query: str) -> list[dict]:
    try:
        resp = await client.post(
            SERPER_URL,
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={"q": query, "gl": "au", "num": SERPER_RESULTS_PER_QUERY},
            timeout=20,
        )
        if resp.status_code != 200:
            logger.warning(f"Serper query failed ({resp.status_code}): {query}")
            return []
        return resp.json().get("organic", [])
    except Exception as e:
        logger.warning(f"Serper query error for '{query}': {e}")
        return []


_robots_cache: dict[str, list[str]] = {}


async def _allowed_by_robots(client: httpx.AsyncClient, url: str) -> bool:
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin not in _robots_cache:
        try:
            resp = await client.get(f"{origin}/robots.txt", headers={"User-Agent": USER_AGENT}, timeout=10)
            body = resp.text if resp.status_code == 200 else ""
            _robots_cache[origin] = re.findall(r"^Disallow:\s*(\S*)", body, re.IGNORECASE | re.MULTILINE)
        except Exception:
            _robots_cache[origin] = []
    disallows = _robots_cache[origin]
    return not any(disallow and parsed.path.startswith(disallow) for disallow in disallows)


async def _fetch_detail_text(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        if not await _allowed_by_robots(client, url):
            return None
        resp = await client.get(url, headers={"User-Agent": USER_AGENT}, timeout=DETAIL_TIMEOUT_SECONDS, follow_redirects=True)
        if resp.status_code != 200:
            return None
        html = resp.text
        text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
        text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()[:5000]
    except Exception:
        return None  # blocked, timed out, or otherwise unavailable -- expected on protected sites, not an error to fix


async def run_discovery() -> list[dict]:
    if not SERPER_API_KEY:
        logger.error("SERPER_API_KEY is not set -- discovery will return no listings. See README for setup.")
        return []

    plan = build_query_plan()
    logger.info(f"Running {len(plan)} Serper queries (~A${estimate_cost_aud(len(plan))} estimated)")

    seen: dict[str, dict] = {}
    async with httpx.AsyncClient() as client:
        for query, site, _model_key in plan:
            for r in await _serper_search(client, query):
                link = r.get("link")
                if link and link not in seen:
                    seen[link] = {"result": r, "query": query, "site": site}
            await asyncio.sleep(0.15)  # polite pacing, not evasive rotation

        logger.info(f"{len(seen)} unique result URLs after dedup")

        listings: list[dict] = []
        detail_fetches = 0
        for url, entry in seen.items():
            r, query, site = entry["result"], entry["query"], entry["site"]
            title = r.get("title", "")
            snippet = r.get("snippet", "")

            if "tesla" not in f"{title} {snippet}".lower():
                continue  # a site: search inevitably returns some non-Tesla pages too

            body_text = None
            if detail_fetches < MAX_DETAIL_FETCHES:
                body_text = await _fetch_detail_text(client, url)
                detail_fetches += 1

            listing = listing_utils.make_listing(
                source=SOURCE_DISPLAY.get(site, site.replace(".com.au", "").capitalize()),
                source_url=url,
                title=title,
                snippet=snippet,
                body_text=body_text or "",
                query=query,
            )

            # Best-effort VIN cross-check -- only when the ad actually
            # exposes a VIN (mostly dealer listings), fails silently if
            # NHTSA's API is unreachable rather than blocking the listing.
            vin = vin_check.extract_vin(f"{title} {snippet} {body_text or ''}")
            if vin:
                result = await vin_check.cross_check_vin(vin, listing.get("year"))
                if result:
                    listing["vin_check"] = {
                        "vin": result.vin,
                        "decoded_year": result.decoded_year,
                        "matches_ad_year": result.matches_ad_year,
                        "note": result.note,
                    }

            listings.append(listing)

    logger.info(f"Discovery complete: {len(listings)} candidate listings ({detail_fetches} detail pages fetched, rest classified from search snippet only)")
    return listings
