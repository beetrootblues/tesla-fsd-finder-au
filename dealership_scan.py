"""
Tesla FSD Finder Australia - Dealership Scanner
================================================
The classifieds on carsales.com.au / drive.com.au etc. only capture Teslas
whose owners or dealers chose to list there. Plenty of prestige and EV
dealers across the country sell Teslas off their own websites -- Zagame,
Nick Theodossi, Prestige Auto Traders, Dutton One, EV specialists and the
big dealer groups -- and never bother syndicating every car to Carsales.

This module discovers those cars the same ToS-compliant way discovery.py
does: `site:`-restricted Serper.dev searches, one per registered dealer
domain, then classify off the title+snippet (with a best-effort detail
fetch where robots.txt allows).

Self-growing registry
---------------------
The seed list in data/dealerships.json is hand-verified. Every scan also
mines the organic results for *new* dealer domains that Google surfaced
while answering `site:` queries for existing dealers, plus a small set of
discovery queries ("tesla dealer <state>"), and appends qualifying domains
to the registry. Over successive 48-hour runs the list grows toward full
national coverage without manual curation -- capped so a single run can't
explode the registry or the query bill.

Everything degrades gracefully without SERPER_API_KEY: the scanner logs and
returns nothing, exactly like discovery.py.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

import discovery  # reuses _serper_search, _fetch_detail_text, SERPER_API_KEY
import listing_utils

logger = logging.getLogger("dealership_scan")
logger.setLevel(logging.INFO)

DATA_DIR = Path(__file__).resolve().parent / "data"
DEALERSHIP_FILE = DATA_DIR / "dealerships.json"

# One `site:` query per dealer (Tesla for sale), one per dealer + model
# combo at most. Keep the per-run bill sane: ~56 seed dealers -> ~56 queries
# with headroom for model-targeted combos as the registry grows past 100.
DEALER_QUERY_QUOTA = int(os.environ.get("DEALER_QUERY_QUOTA", "200"))
# Discovery queries that hunt for *new* dealer domains (one per state).
_DISCOVERY_STATES = ["nsw", "victoria", "queensland", "western australia", "south australia", "tasmania", "act", "nt"]
DISCOVERY_QUERIES = [f"used tesla dealer {state} australia" for state in _DISCOVERY_STATES]
DISCOVERY_QUERY_QUOTA = int(os.environ.get("DEALER_DISCOVERY_QUOTA", "16"))
MAX_NEW_DEALERS_PER_RUN = int(os.environ.get("MAX_NEW_DEALERS_PER_RUN", "40"))

# Domains that are never dealer candidates (marketplaces, auctions we
# already cover, aggregators, social media, OEM, parked pages).
SKIP_DOMAINS = {
    "carsales.com.au", "gumtree.com.au", "drive.com.au", "carsguide.com.au",
    "cars4sale.com.au", "tradingpost.com.au", "autotrader.com.au",
    "shannons.com.au", "grays.com.au", "pickles.com.au", "facebook.com",
    "youtube.com", "instagram.com", "tiktok.com", "linkedin.com",
    "twitter.com", "x.com", "wikipedia.org", "google.com", "google.com.au",
    "tesla.com", "tesla.com.au", "reddit.com", "ebay.com.au", "whichcar.com.au",
    "caradvice.com.au", "carsguide.com", "news.com.au", "drive.com", "theage.com.au",
    "smh.com.au", "carsalesnetwork.com", "automotivesuperstore.com.au",
    "duoporta.com.au", "carvan.com.au", "cars.com.au", "autotempest.com",
}

BLOCKED_HOST_SUFFIXES = (".gov.au", ".edu.au", ".org.au")


def load_dealerships() -> list[dict]:
    if not DEALERSHIP_FILE.exists():
        return []
    try:
        payload = json.loads(DEALERSHIP_FILE.read_text())
        return payload.get("dealerships", [])
    except Exception as e:
        logger.error(f"Failed to load {DEALERSHIP_FILE}: {e}")
        return []


def save_dealerships(dealerships: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 3,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "dealerships": dealerships,
    }
    DEALERSHIP_FILE.write_text(json.dumps(payload, indent=2))
    logger.info(f"Dealership registry saved: {len(dealerships)} dealers")


def _normalise_domain(url: str) -> str | None:
    """Extract a bare domain (lowercase, no scheme/www/subdomain) from either
    a full URL (https://www.example.com.au/path) or a bare domain string
    (example.com.au) -- urlparse needs the scheme, so handle both."""
    try:
        if "://" in url:
            host = urlparse(url).netloc.lower()
        else:
            host = url.split("/")[0].strip().lower()
    except Exception:
        return None
    if not host:
        return None
    host = host.split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def _is_dealer_candidate(domain: str) -> bool:
    if not domain or "." not in domain:
        return False
    if domain in SKIP_DOMAINS:
        return False
    if domain.endswith(BLOCKED_HOST_SUFFIXES):
        return False
    if re.match(r"^\d+\.\d+\.\d+\.\d+$", domain):  # bare IP
        return False
    return True


def register_new_dealer(dealerships: list[dict], domain: str, name: str = "", state: str = "") -> bool:
    """Adds a new dealer to the registry if it's a candidate and not already
    present. Returns True when a new dealer was added."""
    domain = _normalise_domain(domain) or ""
    if not _is_dealer_candidate(domain):
        return False
    if any(d.get("domain") == domain for d in dealerships):
        return False
    display = (name or domain.split(".")[0]).replace("-", " ").title()
    dealerships.append({
        "name": display,
        "domain": domain,
        "state": state or "",
        "city": "",
        "category": "discovered",
        "source": "auto",
    })
    return True


def build_dealer_query_plan(dealerships: list[dict]) -> list[tuple[str, str, str]]:
    """(query, domain, dealer_name) tuples. One generic query per dealer plus
    model-targeted queries for the most promising (prestige/EV) dealers."""
    plan = []
    budget = DEALER_QUERY_QUOTA
    for dealer in dealerships:
        if budget <= 0:
            break
        domain = dealer.get("domain", "")
        if not domain:
            continue
        plan.append((f"site:{domain} tesla for sale", domain, dealer.get("name", domain)))
        budget -= 1
    return plan


def build_discovery_query_plan() -> list[str]:
    return DISCOVERY_QUERIES[:DISCOVERY_QUERY_QUOTA]


async def _classify_result(
    client: httpx.AsyncClient,
    r: dict,
    query: str,
    source_name: str,
    dealer_state: str,
    detail_fetches: int,
    max_detail_fetches: int,
) -> tuple[dict | None, int]:
    url = r.get("link", "")
    title = r.get("title", "")
    snippet = r.get("snippet", "")
    if not url or "tesla" not in f"{title} {snippet}".lower():
        return None, detail_fetches

    body_text = None
    if detail_fetches < max_detail_fetches:
        body_text = await discovery._fetch_detail_text(client, url)
        detail_fetches += 1

    listing = listing_utils.make_listing(
        source=source_name,
        source_url=url,
        title=title,
        snippet=snippet,
        body_text=body_text or "",
        query=query,
    )
    listing["dealer"] = {
        "name": source_name,
        "domain": _normalise_domain(url) or "",
        "state": dealer_state or "",
    }
    return listing, detail_fetches


async def scan_dealerships() -> list[dict]:
    """Scans every registered dealer domain for Teslas, then mines the
    results for new dealer domains and grows the registry. Returns newly
    found listings (source = dealer name)."""
    if not discovery.SERPER_API_KEY:
        logger.error("SERPER_API_KEY is not set -- dealership scan skipped.")
        return []

    dealerships = load_dealerships()
    if not dealerships:
        logger.warning("Dealership registry is empty -- nothing to scan.")
        return []

    max_detail = int(os.environ.get("MAX_DEALER_DETAIL_FETCHES", "40"))
    listings: list[dict] = []
    seen_urls: set[str] = set()
    discovered_domains: set[str] = set()

    async with httpx.AsyncClient() as client:
        # --- Phase 1: scan registered dealers ---
        plan = build_dealer_query_plan(dealerships)
        logger.info(f"Dealership scan: {len(plan)} queries across {len(dealerships)} dealers")
        detail_fetches = 0
        for query, domain, name in plan:
            for r in await discovery._serper_search(client, query):
                url = r.get("link", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    listing, detail_fetches = await _classify_result(
                        client, r, query, name,
                        next((d.get("state", "") for d in dealerships if d.get("domain") == domain), ""),
                        detail_fetches, max_detail,
                    )
                    if listing:
                        listings.append(listing)
                # Any dealer-ish domain Google surfaced is a growth lead.
                host = _normalise_domain(url)
                if host and _is_dealer_candidate(host):
                    discovered_domains.add(host)
            await asyncio.sleep(0.15)

        # --- Phase 2: discovery queries to find *new* dealers ---
        logger.info(f"Dealership discovery: {len(DISCOVERY_QUERIES)} queries for new dealer domains")
        for query in build_discovery_query_plan():
            for r in await discovery._serper_search(client, query):
                host = _normalise_domain(r.get("link", ""))
                title = r.get("title", "")
                if host and _is_dealer_candidate(host) and ("dealer" in f"{title}".lower() or "tesla" in f"{title}".lower()):
                    discovered_domains.add(host)
            await asyncio.sleep(0.15)

    # --- Grow the registry (capped) ---
    added = 0
    for domain in sorted(discovered_domains):
        if added >= MAX_NEW_DEALERS_PER_RUN:
            break
        if register_new_dealer(dealerships, domain):
            added += 1
    if added:
        save_dealerships(dealerships)
    logger.info(f"Dealership scan complete: {len(listings)} listings, {added} new dealers added to registry ({len(dealerships)} total)")

    # Normalise ID/source fields so main.py's pipeline treats them uniformly.
    for listing in listings:
        listing["source_group"] = "Dealer"
    return listings


def get_dealer_summary() -> dict:
    dealers = load_dealerships()
    by_state: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for d in dealers:
        state = d.get("state") or "unknown"
        cat = d.get("category") or "discovered"
        by_state[state] = by_state.get(state, 0) + 1
        by_category[cat] = by_category.get(cat, 0) + 1
    last_updated = ""
    try:
        payload = json.loads(DEALERSHIP_FILE.read_text())
        last_updated = payload.get("last_updated", "")
    except Exception:
        pass
    return {
        "total": len(dealers),
        "by_state": by_state,
        "by_category": by_category,
        "last_updated": last_updated,
    }
