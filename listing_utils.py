"""
Shared, source-agnostic helpers for turning scraped/discovered text into a
normalised listing dict. Split out from scrapers.py so both scrapers.py and
discovery.py can import them without a circular dependency.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Optional

import classify

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


def generate_id(source: str, url: str) -> str:
    return hashlib.md5(f"{source}:{url}".encode()).hexdigest()[:12]


def infer_state(location: str) -> str:
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


def parse_price(text: str) -> Optional[int]:
    if not text:
        return None
    cleaned = re.sub(r"[^\d]", "", str(text))
    if cleaned and len(cleaned) >= 4:
        val = int(cleaned)
        if 5_000 <= val <= 500_000:
            return val
    return None


def parse_km(text: str) -> Optional[int]:
    if not text:
        return None
    cleaned = re.sub(r"[^\d]", "", str(text))
    if cleaned:
        val = int(cleaned)
        if 0 <= val <= 999_999:
            return val
    return None


def parse_year(text: str) -> Optional[int]:
    match = re.search(r"(20[1-3]\d)", str(text))
    return int(match.group(1)) if match else None


def infer_body(model: str) -> str:
    if model in ("Model 3", "Model S"):
        return "Sedan"
    if model in ("Model Y", "Model X"):
        return "SUV"
    return ""


_MODEL_DISPLAY = {"S": "Model S", "3": "Model 3", "X": "Model X", "Y": "Model Y", "unknown": ""}


def make_listing(
    source: str,
    source_url: str,
    title: str,
    snippet: str = "",
    body_text: str = "",
    price: Optional[int] = None,
    location: str = "",
    seller_type: str = "",
    image_url: str = "",
    query: str = "",
) -> dict:
    """
    Builds one normalised listing dict, running the full classifier (model,
    autopilot HW, MCU, FSD purchase/subscription, supercharging) over
    whatever text is available -- snippet-only if the detail page fetch was
    blocked/skipped, snippet+body if it succeeded.
    """
    legacy = classify.classify_to_legacy_fields(title, f"{snippet}\n{body_text}")

    model_code = legacy["classification"]["model"]["value"]
    model_display = _MODEL_DISPLAY.get(model_code, "")
    year = parse_year(title) or parse_year(snippet)
    state = infer_state(location)
    if not price:
        price = parse_price(snippet) or parse_price(body_text)

    now_iso = datetime.now(timezone.utc).isoformat()

    return {
        "id": generate_id(source, source_url),
        "title": title.strip(),
        "model": model_display,
        "year": year,
        "price": price,
        "price_str": f"${price:,}" if price else "",
        "odometer": parse_km(snippet) or parse_km(body_text) or 0,
        "body_type": infer_body(model_display),
        "fuel_type": "Electric",
        "location": location.strip(),
        "state": state,
        **{k: v for k, v in legacy.items() if k != "classification"},
        "classification": legacy["classification"],
        "source": source,
        "source_url": source_url,
        "seller_type": seller_type,
        "image_url": image_url,
        "description": (snippet or body_text)[:500],
        "found_at": now_iso,
        "date_listed": "",
        "is_active": True,
        "discovery_query": query,
        "detail_page_fetched": bool(body_text),
    }
