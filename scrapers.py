"""
Tesla FSD Finder Australia - Multi-Source Scraper Engine v1.2
=============================================================
Async scrapers for 7 Australian car classifieds sites.
Each scraper returns a list[dict] conforming to the unified listing schema.

Sources:
  1. Drive.com.au          - Next.js SSR JSON extraction
  2. AutoTrader.com.au     - Public search API
  3. Carsales.com.au       - HTML scraping with BeautifulSoup
  4. Gumtree.com.au        - Search API / HTML fallback
  5. CarsGuide.com.au      - Path-based HTML scraping
  6. Pickles.com.au        - Auction listing scraper
  7. Facebook Marketplace  - Apify actor (optional, env-gated)

Usage:
    from scrapers import run_all_scrapers
    listings = await run_all_scrapers()
"""

import asyncio
import hashlib
import json
import logging
import os
import random
import re
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote_plus, urljoin

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger("scrapers")
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RATE_LIMIT_SECONDS = 2.0

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

TESLA_MODELS = ["Model 3", "Model Y", "Model S", "Model X", "Cybertruck"]

FSD_KEYWORDS_CONFIRMED = [
    "full self-driving", "full self driving", "fsd capability",
    "fsd included", "fsd enabled", "fsd purchased", "fsd transferr",
]
FSD_KEYWORDS_LIKELY = [
    "enhanced autopilot", "enhanced auto pilot", "eap included",
    "eap enabled", "autopilot upgrade", "navigate on autopilot",
    "auto lane change", "autopark", "smart summon", "summon feature",
]
FSD_KEYWORDS_POSSIBLE = [
    "autopilot", "self-driving", "self driving", "hw4", "hw 4",
    "hardware 4", "ai4", "fsd", "eap",
]

AU_STATES = {
    "nsw": "NSW", "new south wales": "NSW",
    "vic": "VIC", "victoria": "VIC",
    "qld": "QLD", "queensland": "QLD",
    "wa": "WA", "western australia": "WA",
    "sa": "SA", "south australia": "SA",
    "tas": "TAS", "tasmania": "TAS",
    "act": "ACT", "australian capital territory": "ACT",
    "nt": "NT", "northern territory": "NT",
    "sydney": "NSW", "melbourne": "VIC", "brisbane": "QLD",
    "perth": "WA", "adelaide": "SA", "hobart": "TAS",
    "canberra": "ACT", "darwin": "NT", "gold coast": "QLD",
    "newcastle": "NSW", "wollongong": "NSW", "geelong": "VIC",
    "cairns": "QLD", "townsville": "QLD", "toowoomba": "QLD",
    "ballarat": "VIC", "bendigo": "VIC", "launceston": "TAS",
    "albury": "NSW", "wodonga": "VIC", "maitland": "NSW",
    "rockhampton": "QLD", "mackay": "QLD", "bundaberg": "QLD",
    "hervey bay": "QLD", "wagga wagga": "NSW", "tamworth": "NSW",
    "orange": "NSW", "dubbo": "NSW", "bathurst": "NSW",
    "port macquarie": "NSW", "lismore": "NSW", "coffs harbour": "NSW",
    "sunshine coast": "QLD", "gladstone": "QLD",
    "mount gambier": "SA", "whyalla": "SA",
    "geraldton": "WA", "bunbury": "WA", "mandurah": "WA",
    "alice springs": "NT",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _random_ua() -> str:
    return random.choice(USER_AGENTS)


def _generate_id(source: str, url: str) -> str:
    raw = f"{source}:{url}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _detect_model(text: str) -> str:
    t = text.lower()
    if "model 3" in t or "model3" in t:
        return "Model 3"
    if "model y" in t or "modely" in t:
        return "Model Y"
    if "model s" in t or "models" in t:
        return "Model S"
    if "model x" in t or "modelx" in t:
        return "Model X"
    if "cybertruck" in t:
        return "Cybertruck"
    return "Unknown"


def _detect_fsd(text: str) -> dict:
    t = text.lower()
    found = []
    score = 0.0

    for kw in FSD_KEYWORDS_CONFIRMED:
        if kw in t:
            found.append(kw)
            score = max(score, 1.0)
    for kw in FSD_KEYWORDS_LIKELY:
        if kw in t:
            found.append(kw)
            score = max(score, 0.7)
    for kw in FSD_KEYWORDS_POSSIBLE:
        if kw in t:
            found.append(kw)
            score = max(score, 0.3)

    if score >= 0.9:
        status = "confirmed"
    elif score >= 0.6:
        status = "likely"
    elif score > 0:
        status = "possible"
    else:
        status = "none"

    has_eap = any(
        kw in t for kw in ["enhanced autopilot", "enhanced auto pilot", "eap"]
    )

    return {
        "fsd_status": status,
        "has_fsd": status in ("confirmed", "likely"),
        "has_eap": has_eap,
        "fsd_keywords_found": list(set(found)),
        "fsd_confidence": round(score, 2),
    }


def _infer_state(location: str) -> str:
    if not location:
        return ""
    loc_lower = location.lower().strip()
    parts = [p.strip() for p in re.split(r"[,\-/]", loc_lower)]
    for part in reversed(parts):
        if part in AU_STATES:
            return AU_STATES[part]
    for key, val in AU_STATES.items():
        if key in loc_lower:
            return val
    return ""


def _infer_hw_version(year: Optional[int], model: str) -> Optional[str]:
    if not year:
        return None
    if model == "Model 3" and year >= 2024:
        return "HW4"
    if model == "Model 3" and year == 2023:
        return "HW3/HW4"
    if model == "Model Y" and year >= 2024:
        return "HW4"
    if model in ("Model S", "Model X") and year >= 2023:
        return "HW4"
    if model == "Cybertruck":
        return "HW4"
    if year >= 2020:
        return "HW3"
    if year >= 2018:
        return "HW2.5"
    return "HW2"


def _parse_price(text: str) -> Optional[int]:
    if not text:
        return None
    cleaned = re.sub(r"[^\d]", "", str(text))
    if cleaned and len(cleaned) >= 4:
        val = int(cleaned)
        if 15_000 <= val <= 500_000:
            return val
    return None


def _parse_km(text: str) -> Optional[int]:
    if not text:
        return None
    cleaned = re.sub(r"[^\d]", "", str(text))
    if cleaned:
        val = int(cleaned)
        if 0 <= val <= 999_999:
            return val
    return None


def _parse_year(text: str) -> Optional[int]:
    match = re.search(r"(20[1-3]\d)", str(text))
    if match:
        return int(match.group(1))
    return None


def _infer_body(model: str) -> str:
    if model in ("Model 3", "Model S"):
        return "Sedan"
    if model in ("Model Y", "Model X"):
        return "SUV"
    if model == "Cybertruck":
        return "Ute"
    return ""


def _make_listing(
    source: str,
    source_url: str,
    title: str,
    price: Optional[int] = None,
    price_str: str = "",
    year: Optional[int] = None,
    model: str = "",
    variant: str = "",
    odometer: Optional[int] = None,
    location: str = "",
    state: str = "",
    seller_type: str = "",
    seller_name: str = "",
    image_url: str = "",
    description: str = "",
    colour: str = "",
    body_type: str = "",
    transmission: str = "",
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    date_listed: str = "",
    extra_text: str = "",
) -> dict:
    if not model:
        model = _detect_model(title + " " + description)
    if not year:
        year = _parse_year(title)
    if not state:
        state = _infer_state(location)

    fsd_text = " ".join([title, description, variant, extra_text])
    fsd_info = _detect_fsd(fsd_text)
    hw_version = _infer_hw_version(year, model)
    now_iso = datetime.now(timezone.utc).isoformat()

    return {
        "id": _generate_id(source, source_url),
        "title": title.strip(),
        "model": model,
        "year": year,
        "variant": variant.strip(),
        "price": price,
        "price_str": price_str or (f"${price:,}" if price else ""),
        "price_driveaway": None,
        "price_rating": "",
        "odometer": odometer or 0,
        "colour": colour,
        "body_type": body_type or _infer_body(model),
        "fuel_type": "Electric",
        "transmission": transmission or "Automatic",
        "condition": "Used",
        "location": location.strip(),
        "state": state,
        "lat": lat,
        "lng": lng,
        **fsd_info,
        "hw_version": hw_version,
        "source": source,
        "source_url": source_url,
        "seller_type": seller_type,
        "seller_name": seller_name,
        "image_url": image_url,
        "description": description[:500],
        "found_at": now_iso,
        "date_listed": date_listed,
        "is_active": True,
    }


async def _rate_limited_get(
    client: httpx.AsyncClient,
    url: str,
    **kwargs,
) -> Optional[httpx.Response]:
    await asyncio.sleep(RATE_LIMIT_SECONDS + random.uniform(0, 1))
    headers = kwargs.pop("headers", {})
    headers.setdefault("User-Agent", _random_ua())
    headers.setdefault("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
    headers.setdefault("Accept-Language", "en-AU,en;q=0.9")
    try:
        resp = await client.get(
            url, headers=headers, timeout=30, follow_redirects=True, **kwargs
        )
        resp.raise_for_status()
        return resp
    except Exception as e:
        logger.warning(f"Request failed for {url}: {e}")
        return None


# ---------------------------------------------------------------------------
# 1. Drive.com.au
# ---------------------------------------------------------------------------

async def scrape_drive(client: httpx.AsyncClient) -> list[dict]:
    logger.info("[Drive] Starting scrape...")
    listings = []
    base_url = "https://www.drive.com.au/search/buy/tesla/"

    for page in range(1, 6):
        url = f"{base_url}?page={page}" if page > 1 else base_url
        resp = await _rate_limited_get(client, url)
        if not resp:
            break

        soup = BeautifulSoup(resp.text, "lxml")
        script_tag = soup.find("script", id="__NEXT_DATA__")
        if script_tag:
            try:
                data = json.loads(script_tag.string)
                props = data.get("props", {}).get("pageProps", {})
                results = props.get("searchResults", props.get("listings", []))
                if isinstance(results, dict):
                    results = results.get("listings", results.get("results", []))
                for item in results:
                    title = item.get("title", "") or \
                        f"{item.get('year', '')} Tesla {item.get('model', '')}"
                    listings.append(_make_listing(
                        source="Drive",
                        source_url=urljoin(
                            "https://www.drive.com.au",
                            item.get("url", item.get("slug", "")),
                        ),
                        title=title,
                        price=_parse_price(str(item.get("price", ""))),
                        price_str=item.get("priceDisplay", ""),
                        year=item.get("year"),
                        model=item.get("model", ""),
                        variant=item.get("variant", item.get("badge", "")),
                        odometer=_parse_km(
                            str(item.get("odometer", item.get("kilometres", "")))
                        ),
                        location=item.get(
                            "location", item.get("dealerLocation", "")
                        ),
                        state=item.get("state", ""),
                        seller_type=item.get("sellerType", ""),
                        seller_name=item.get(
                            "dealerName", item.get("sellerName", "")
                        ),
                        image_url=item.get("image", item.get("mainImage", "")),
                        description=item.get("description", ""),
                        colour=item.get(
                            "colour", item.get("exteriorColour", "")
                        ),
                    ))
                continue
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"[Drive] __NEXT_DATA__ parse error: {e}")

        cards = soup.select(
            "div[class*='listing-card'], article[class*='listing'], "
            "div[class*='search-result']"
        )
        for card in cards:
            title_el = card.select_one("h2, h3, [class*='title']")
            price_el = card.select_one("[class*='price']")
            link_el = (
                card.select_one("a[href*='/cars/']") or card.select_one("a")
            )
            img_el = card.select_one("img")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if "tesla" not in title.lower():
                continue
            link = link_el["href"] if link_el and link_el.get("href") else ""
            if link and not link.startswith("http"):
                link = urljoin("https://www.drive.com.au", link)
            listings.append(_make_listing(
                source="Drive",
                source_url=link,
                title=title,
                price=_parse_price(price_el.get_text() if price_el else ""),
                image_url=img_el.get("src", "") if img_el else "",
            ))
        if not cards and not script_tag:
            break

    logger.info(f"[Drive] Found {len(listings)} listings")
    return listings


# ---------------------------------------------------------------------------
# 2. AutoTrader.com.au
# ---------------------------------------------------------------------------

async def scrape_autotrader(client: httpx.AsyncClient) -> list[dict]:
    logger.info("[AutoTrader] Starting scrape...")
    listings = []

    for page in range(1, 6):
        url = f"https://www.autotrader.com.au/cars/tesla?page={page}"
        resp = await _rate_limited_get(client, url)
        if not resp:
            break

        soup = BeautifulSoup(resp.text, "lxml")

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                ld = json.loads(script.string)
                items = ld if isinstance(ld, list) else [ld]
                for item in items:
                    if item.get("@type") == "Car":
                        listings.append(_make_listing(
                            source="AutoTrader",
                            source_url=item.get("url", ""),
                            title=item.get("name", ""),
                            price=_parse_price(
                                str(item.get("offers", {}).get("price", ""))
                            ),
                            year=_parse_year(item.get("modelDate", "")),
                            model=item.get("model", ""),
                            odometer=_parse_km(
                                str(
                                    item.get("mileageFromOdometer", {}).get(
                                        "value", ""
                                    )
                                )
                            ),
                            colour=item.get("color", ""),
                            image_url=item.get("image", ""),
                        ))
            except json.JSONDecodeError:
                pass

        cards = soup.select(
            "[class*='listing-item'], [class*='card-listing'], "
            "[class*='vehicle-card']"
        )
        for card in cards:
            title_el = card.select_one("h2, h3, [class*='title']")
            price_el = card.select_one("[class*='price']")
            link_el = card.select_one("a[href]")
            img_el = card.select_one("img")
            km_el = card.select_one("[class*='odometer'], [class*='km']")
            loc_el = card.select_one("[class*='location']")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if "tesla" not in title.lower():
                continue
            link = link_el["href"] if link_el and link_el.get("href") else ""
            if link and not link.startswith("http"):
                link = urljoin("https://www.autotrader.com.au", link)
            listings.append(_make_listing(
                source="AutoTrader",
                source_url=link,
                title=title,
                price=_parse_price(price_el.get_text() if price_el else ""),
                odometer=_parse_km(km_el.get_text() if km_el else ""),
                location=loc_el.get_text(strip=True) if loc_el else "",
                image_url=(
                    img_el.get("src", img_el.get("data-src", ""))
                    if img_el else ""
                ),
            ))
        if not cards:
            break

    logger.info(f"[AutoTrader] Found {len(listings)} listings")
    return listings


# ---------------------------------------------------------------------------
# 3. Carsales.com.au
# ---------------------------------------------------------------------------

async def scrape_carsales(client: httpx.AsyncClient) -> list[dict]:
    logger.info("[Carsales] Starting scrape...")
    listings = []

    model_paths = [
        "/cars/tesla/model-3/",
        "/cars/tesla/model-y/",
        "/cars/tesla/model-s/",
        "/cars/tesla/model-x/",
        "/cars/tesla/",
    ]

    for path in model_paths:
        for page in range(1, 4):
            url = f"https://www.carsales.com.au{path}"
            if page > 1:
                url += f"?offset={(page - 1) * 12}"
            resp = await _rate_limited_get(client, url)
            if not resp:
                break

            soup = BeautifulSoup(resp.text, "lxml")
            cards = soup.select(
                "[class*='listing-item'], [data-testid*='listing'], "
                ".listing-card, [class*='card'][class*='vehicle']"
            )
            for card in cards:
                title_el = card.select_one(
                    "h2, h3, [class*='title'], [data-testid*='title']"
                )
                price_el = card.select_one(
                    "[class*='price'], [data-testid*='price']"
                )
                link_el = (
                    card.select_one("a[href*='/cars/details/']")
                    or card.select_one("a[href]")
                )
                img_el = card.select_one("img")
                km_el = card.select_one("[class*='odometer'], [class*='km']")
                loc_el = card.select_one(
                    "[class*='location'], [class*='seller-location']"
                )
                seller_el = card.select_one(
                    "[class*='seller-name'], [class*='dealer']"
                )
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if "tesla" not in title.lower():
                    continue
                link = (
                    link_el["href"] if link_el and link_el.get("href") else ""
                )
                if link and not link.startswith("http"):
                    link = urljoin("https://www.carsales.com.au", link)

                price_text = price_el.get_text(strip=True) if price_el else ""

                listings.append(_make_listing(
                    source="Carsales",
                    source_url=link,
                    title=title,
                    price=_parse_price(price_text),
                    price_str=price_text,
                    odometer=_parse_km(km_el.get_text() if km_el else ""),
                    location=loc_el.get_text(strip=True) if loc_el else "",
                    seller_name=(
                        seller_el.get_text(strip=True) if seller_el else ""
                    ),
                    seller_type="Dealer" if seller_el else "Private",
                    image_url=(
                        img_el.get("src", img_el.get("data-src", ""))
                        if img_el else ""
                    ),
                ))
            if not cards:
                break

    logger.info(f"[Carsales] Found {len(listings)} listings")
    return listings


# ---------------------------------------------------------------------------
# 4. Gumtree.com.au
# ---------------------------------------------------------------------------

async def scrape_gumtree(client: httpx.AsyncClient) -> list[dict]:
    logger.info("[Gumtree] Starting scrape...")
    listings = []

    for page in range(1, 6):
        url = (
            f"https://www.gumtree.com.au/s-cars-vans-utes/australia/"
            f"tesla/page-{page}/c18320l3000001?carmake=tesla"
        )
        resp = await _rate_limited_get(client, url)
        if not resp:
            break

        soup = BeautifulSoup(resp.text, "lxml")
        cards = soup.select(
            "[class*='user-ad-row'], [class*='listing-card'], "
            "[data-testid*='listing']"
        )
        for card in cards:
            title_el = card.select_one(
                "h2, h3, [class*='title'], a[class*='title']"
            )
            price_el = card.select_one("[class*='price']")
            link_el = (
                card.select_one("a[href*='/s-ad/']")
                or card.select_one("a[href]")
            )
            img_el = card.select_one("img")
            loc_el = card.select_one("[class*='location']")
            desc_el = card.select_one("[class*='description']")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if "tesla" not in title.lower():
                continue
            link = link_el["href"] if link_el and link_el.get("href") else ""
            if link and not link.startswith("http"):
                link = urljoin("https://www.gumtree.com.au", link)

            attrs = card.select("[class*='attribute'], [class*='tag']")
            km_text = ""
            year_text = ""
            for attr in attrs:
                text = attr.get_text(strip=True).lower()
                if "km" in text:
                    km_text = text
                elif re.match(r"^20[1-3]\d$", text):
                    year_text = text

            listings.append(_make_listing(
                source="Gumtree",
                source_url=link,
                title=title,
                price=_parse_price(price_el.get_text() if price_el else ""),
                year=_parse_year(year_text or title),
                odometer=_parse_km(km_text),
                location=loc_el.get_text(strip=True) if loc_el else "",
                seller_type="Private",
                image_url=(
                    img_el.get("src", img_el.get("data-src", ""))
                    if img_el else ""
                ),
                description=(
                    desc_el.get_text(strip=True) if desc_el else ""
                ),
            ))
        if not cards:
            break

    logger.info(f"[Gumtree] Found {len(listings)} listings")
    return listings


# ---------------------------------------------------------------------------
# 5. CarsGuide.com.au
# ---------------------------------------------------------------------------

async def scrape_carsguide(client: httpx.AsyncClient) -> list[dict]:
    logger.info("[CarsGuide] Starting scrape...")
    listings = []
    model_slugs = ["model-3", "model-y", "model-s", "model-x"]

    for slug in model_slugs:
        for page in range(1, 4):
            url = f"https://www.carsguide.com.au/buy-a-car/tesla/{slug}/"
            if page > 1:
                url += f"?page={page}"
            resp = await _rate_limited_get(client, url)
            if not resp:
                break

            soup = BeautifulSoup(resp.text, "lxml")
            cards = soup.select(
                "[class*='listing-card'], [class*='search-result'], "
                ".card-listing"
            )
            for card in cards:
                title_el = card.select_one("h2, h3, [class*='title']")
                price_el = card.select_one("[class*='price']")
                link_el = (
                    card.select_one("a[href*='/listing/']")
                    or card.select_one("a[href]")
                )
                img_el = card.select_one("img")
                km_el = card.select_one("[class*='odometer'], [class*='km']")
                loc_el = card.select_one("[class*='location']")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                link = (
                    link_el["href"] if link_el and link_el.get("href") else ""
                )
                if link and not link.startswith("http"):
                    link = urljoin("https://www.carsguide.com.au", link)
                listings.append(_make_listing(
                    source="CarsGuide",
                    source_url=link,
                    title=title,
                    price=_parse_price(price_el.get_text() if price_el else ""),
                    odometer=_parse_km(km_el.get_text() if km_el else ""),
                    location=loc_el.get_text(strip=True) if loc_el else "",
                    image_url=(
                        img_el.get("src", img_el.get("data-src", ""))
                        if img_el else ""
                    ),
                ))
            if not cards:
                break

    logger.info(f"[CarsGuide] Found {len(listings)} listings")
    return listings


# ---------------------------------------------------------------------------
# 6. Pickles.com.au (Auctions)
# ---------------------------------------------------------------------------

async def scrape_pickles(client: httpx.AsyncClient) -> list[dict]:
    logger.info("[Pickles] Starting scrape...")
    listings = []

    url = (
        "https://www.pickles.com.au/cars/search"
        "?keyword=tesla&category=Passenger+Vehicles"
    )
    resp = await _rate_limited_get(client, url)
    if not resp:
        logger.warning("[Pickles] Failed to fetch search page")
        return listings

    soup = BeautifulSoup(resp.text, "lxml")

    for script in soup.find_all("script"):
        text = script.string or ""
        if "searchResults" in text:
            try:
                match = re.search(
                    r"searchResults\s*[:=]\s*(\[.+?\])\s*[;,]",
                    text,
                    re.DOTALL,
                )
                if match:
                    results = json.loads(match.group(1))
                    for item in results:
                        title = item.get(
                            "title", item.get("description", "")
                        )
                        if "tesla" not in title.lower():
                            continue
                        listings.append(_make_listing(
                            source="Pickles",
                            source_url=urljoin(
                                "https://www.pickles.com.au",
                                item.get("url", ""),
                            ),
                            title=title,
                            price=_parse_price(
                                str(
                                    item.get(
                                        "currentBid", item.get("price", "")
                                    )
                                )
                            ),
                            price_str=(
                                f"Auction: ${item.get('currentBid', 'TBD')}"
                            ),
                            odometer=_parse_km(str(item.get("odometer", ""))),
                            location=item.get("location", ""),
                            image_url=item.get(
                                "imageUrl", item.get("image", "")
                            ),
                            seller_type="Auction",
                        ))
            except (json.JSONDecodeError, AttributeError):
                pass

    cards = soup.select(
        "[class*='lot-card'], [class*='search-result'], "
        "[class*='item-card']"
    )
    for card in cards:
        title_el = card.select_one("h2, h3, [class*='title']")
        price_el = card.select_one("[class*='price'], [class*='bid']")
        link_el = card.select_one("a[href]")
        img_el = card.select_one("img")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if "tesla" not in title.lower():
            continue
        link = link_el["href"] if link_el and link_el.get("href") else ""
        if link and not link.startswith("http"):
            link = urljoin("https://www.pickles.com.au", link)
        listings.append(_make_listing(
            source="Pickles",
            source_url=link,
            title=title,
            price=_parse_price(price_el.get_text() if price_el else ""),
            seller_type="Auction",
            image_url=img_el.get("src", "") if img_el else "",
        ))

    logger.info(f"[Pickles] Found {len(listings)} listings")
    return listings


# ---------------------------------------------------------------------------
# 7. Facebook Marketplace (via Apify - optional)
# ---------------------------------------------------------------------------

async def scrape_facebook(client: httpx.AsyncClient) -> list[dict]:
    apify_token = os.environ.get("APIFY_TOKEN")
    if not apify_token:
        logger.info("[Facebook] Skipping - APIFY_TOKEN not set")
        return []

    logger.info("[Facebook] Starting Apify actor run...")
    listings = []
    actor_id = "apify~facebook-marketplace-scraper"
    run_url = f"https://api.apify.com/v2/acts/{actor_id}/runs"

    input_data = {
        "searchQuery": "Tesla",
        "location": "Australia",
        "maxItems": 100,
        "category": "vehicles",
    }

    try:
        resp = await client.post(
            run_url,
            json=input_data,
            params={"token": apify_token},
            timeout=120,
        )
        if resp.status_code != 201:
            logger.warning(f"[Facebook] Actor start failed: {resp.status_code}")
            return listings

        run_data = resp.json().get("data", {})
        run_id = run_data.get("id")
        dataset_id = run_data.get("defaultDatasetId")
        if not run_id:
            return listings

        status_url = f"https://api.apify.com/v2/actor-runs/{run_id}"
        for _ in range(18):
            await asyncio.sleep(10)
            status_resp = await client.get(
                status_url, params={"token": apify_token}
            )
            status = (
                status_resp.json().get("data", {}).get("status", "")
            )
            if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                break

        if status != "SUCCEEDED":
            logger.warning(f"[Facebook] Run ended: {status}")
            return listings

        dataset_url = (
            f"https://api.apify.com/v2/datasets/{dataset_id}/items"
        )
        items_resp = await client.get(
            dataset_url, params={"token": apify_token}
        )
        for item in items_resp.json():
            title = item.get("title", "")
            if "tesla" not in title.lower():
                continue
            listings.append(_make_listing(
                source="Facebook",
                source_url=item.get("url", ""),
                title=title,
                price=_parse_price(str(item.get("price", ""))),
                location=item.get("location", {}).get("name", ""),
                image_url=item.get("image", ""),
                description=item.get("description", ""),
                seller_type="Private",
            ))
    except Exception as e:
        logger.error(f"[Facebook] Apify scrape failed: {e}")

    logger.info(f"[Facebook] Found {len(listings)} listings")
    return listings


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def deduplicate_listings(listings: list[dict]) -> list[dict]:
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
            )
            new_score = (
                len(listing.get("description", ""))
                + (100 if listing.get("image_url") else 0)
                + (50 if listing.get("odometer", 0) > 0 else 0)
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


# ---------------------------------------------------------------------------
# FSD detail page enrichment
# ---------------------------------------------------------------------------

async def enrich_fsd_details(
    client: httpx.AsyncClient,
    listings: list[dict],
    max_enrich: int = 50,
) -> list[dict]:
    candidates = [
        l for l in listings
        if l.get("fsd_status") in ("possible", "likely") and l.get("source_url")
    ][:max_enrich]

    if not candidates:
        return listings

    logger.info(
        f"[Enrich] Checking {len(candidates)} detail pages for FSD keywords..."
    )

    for listing in candidates:
        resp = await _rate_limited_get(client, listing["source_url"])
        if not resp:
            continue
        soup = BeautifulSoup(resp.text, "lxml")
        desc_sections = soup.select(
            "[class*='description'], [class*='detail'], "
            "[class*='features'], [class*='specs']"
        )
        full_text = " ".join(
            el.get_text(" ", strip=True) for el in desc_sections
        )
        if full_text:
            fsd_info = _detect_fsd(full_text)
            if fsd_info["fsd_confidence"] > listing.get("fsd_confidence", 0):
                listing.update(fsd_info)

    return listings


# ---------------------------------------------------------------------------
# Master runner
# ---------------------------------------------------------------------------

async def run_all_scrapers(
    include_facebook: bool = True,
    enrich: bool = True,
) -> list[dict]:
    logger.info("=" * 60)
    logger.info("Starting full scrape run...")
    logger.info("=" * 60)

    start = time.time()

    async with httpx.AsyncClient() as client:
        tasks = [
            scrape_drive(client),
            scrape_autotrader(client),
            scrape_carsales(client),
            scrape_gumtree(client),
            scrape_carsguide(client),
            scrape_pickles(client),
        ]
        if include_facebook:
            tasks.append(scrape_facebook(client))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_listings = []
        source_stats = {}
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Scraper {i} failed: {result}")
                continue
            if isinstance(result, list):
                all_listings.extend(result)
                for listing in result:
                    src = listing.get("source", "Unknown")
                    source_stats[src] = source_stats.get(src, 0) + 1

        logger.info(f"Raw listings: {len(all_listings)}")
        logger.info(f"Per-source: {source_stats}")

        all_listings = deduplicate_listings(all_listings)

        if enrich:
            all_listings = await enrich_fsd_details(client, all_listings)

    elapsed = time.time() - start
    logger.info(
        f"Scrape complete: {len(all_listings)} unique listings in {elapsed:.1f}s"
    )
    return all_listings


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
