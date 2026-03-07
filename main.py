"""
Tesla FSD Finder Australia - FastAPI Backend
=============================================
Serves the static frontend and provides API endpoints for listing data.
Loads real scraped data from data/listings.json and normalises field names
so the frontend receives a consistent schema.

Run locally:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATA_FILE = BASE_DIR / "data" / "listings.json"

app = FastAPI(
    title="Tesla FSD Finder Australia",
    description="Find underpriced Teslas with Full Self-Driving in Australia",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------

_listings_cache: list[dict] = []
_last_updated: Optional[str] = None


def _normalise_listing(raw: dict, index: int) -> dict:
    """
    Normalise a raw scraped listing into the schema the frontend expects.

    Field mapping (scraped -> frontend):
        odometer_km  ->  odometer
        date_found   ->  found_at
        latitude     ->  lat
        longitude    ->  lng
        (no id)      ->  id  (generated from source_url hash)
        source       ->  source  (capitalised for display)
    """
    # Generate a stable ID from source_url or index
    source_url = raw.get("source_url", "")
    if source_url:
        listing_id = hashlib.md5(source_url.encode()).hexdigest()[:12]
    else:
        listing_id = f"listing-{index:04d}"

    # Capitalise source name for display
    source_raw = raw.get("source", "unknown")
    source_display = {
        "drive": "Drive",
        "autotrader": "AutoTrader",
        "gumtree": "Gumtree",
        "carsales": "Carsales",
    }.get(source_raw.lower(), source_raw.title())

    return {
        # Core identity
        "id": raw.get("id", listing_id),
        "title": raw.get("title", "Unknown Tesla"),
        "model": raw.get("model", "Unknown"),
        "year": raw.get("year"),
        "variant": raw.get("variant", ""),

        # Pricing
        "price": raw.get("price"),
        "price_str": raw.get("price_str", ""),
        "price_driveaway": raw.get("price_driveaway"),
        "price_rating": raw.get("price_rating", ""),

        # Vehicle details
        "odometer": raw.get("odometer") or raw.get("odometer_km") or 0,
        "colour": raw.get("colour", ""),
        "body_type": raw.get("body_type", ""),
        "fuel_type": raw.get("fuel_type", "Electric"),
        "transmission": raw.get("transmission", ""),
        "condition": raw.get("condition", ""),

        # Location
        "location": raw.get("location", ""),
        "state": raw.get("state", ""),
        "lat": raw.get("lat") or raw.get("latitude"),
        "lng": raw.get("lng") or raw.get("longitude"),

        # FSD detection
        "fsd_status": raw.get("fsd_status", "none"),
        "has_fsd": raw.get("has_fsd", False),
        "has_eap": raw.get("has_eap", False),
        "fsd_keywords_found": raw.get("fsd_keywords_found", []),
        "hw_version": raw.get("hw_version"),

        # Source / listing info
        "source": source_display,
        "source_url": raw.get("source_url", ""),
        "seller_type": raw.get("seller_type", ""),
        "seller_name": raw.get("seller_name", ""),
        "image_url": raw.get("image_url", ""),
        "description": raw.get("description", ""),

        # Dates
        "found_at": raw.get("found_at") or raw.get("date_found", ""),
        "date_listed": raw.get("date_listed", ""),
        "is_active": raw.get("is_active", True),
    }


def _load_listings() -> list[dict]:
    """Load listings from the JSON data file and normalise them."""
    global _listings_cache, _last_updated

    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r") as f:
                payload = json.load(f)

            raw_list: list[dict] = []
            if isinstance(payload, dict):
                raw_list = payload.get("listings", [])
                _last_updated = payload.get("last_updated")
            elif isinstance(payload, list):
                raw_list = payload

            # Normalise every listing
            _listings_cache = [
                _normalise_listing(item, i) for i, item in enumerate(raw_list)
            ]

            if not _last_updated:
                dates = [
                    item.get("found_at", "")
                    for item in _listings_cache
                    if item.get("found_at")
                ]
                _last_updated = (
                    max(dates) if dates else datetime.now(timezone.utc).isoformat()
                )

            return _listings_cache
        except Exception as e:
            print(f"[WARNING] Failed to load {DATA_FILE}: {e}")

    _last_updated = datetime.now(timezone.utc).isoformat()
    _listings_cache = []
    return _listings_cache


# Load on startup
_load_listings()
print(f"[INFO] Loaded {len(_listings_cache)} listings from {DATA_FILE}")
_fsd_counts: dict[str, int] = {}
for _l in _listings_cache:
    _s = _l.get("fsd_status", "none")
    _fsd_counts[_s] = _fsd_counts.get(_s, 0) + 1
print(f"[INFO] FSD breakdown: {_fsd_counts}")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", include_in_schema=False)
async def root():
    """Serve the main frontend page."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path), media_type="text/html")
    return JSONResponse(
        {"error": "Frontend not found. Place index.html in /static/"},
        status_code=404,
    )


@app.get("/api/health")
async def health():
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "total_listings": len(_listings_cache),
        "last_updated": _last_updated,
        "version": "1.0.0",
    }


@app.get("/api/listings")
async def get_listings(
    model: Optional[str] = Query(
        None, description="Comma-separated model names (e.g. Model 3,Model Y)"
    ),
    state: Optional[str] = Query(
        None, description="Comma-separated state codes (e.g. NSW,VIC)"
    ),
    fsd_status: Optional[str] = Query(
        None,
        description="Comma-separated: confirmed,likely,possible,none",
    ),
    min_price: Optional[int] = Query(None, ge=0),
    max_price: Optional[int] = Query(None, ge=0),
    max_km: Optional[int] = Query(None, ge=0),
    sort: Optional[str] = Query(
        "newest",
        description="newest | price_asc | price_desc | km_asc | year_desc",
    ),
):
    """Return all listings, optionally filtered and sorted."""
    results = list(_listings_cache)

    # --- Filters ---
    if model:
        models = {m.strip().lower() for m in model.split(",")}
        results = [r for r in results if r.get("model", "").lower() in models]
    if state:
        states = {s.strip().upper() for s in state.split(",")}
        results = [r for r in results if r.get("state", "").upper() in states]
    if fsd_status:
        statuses = {s.strip().lower() for s in fsd_status.split(",")}
        results = [
            r for r in results if r.get("fsd_status", "").lower() in statuses
        ]
    if min_price is not None:
        results = [r for r in results if (r.get("price") or 0) >= min_price]
    if max_price is not None:
        results = [
            r for r in results if (r.get("price") or 999_999_999) <= max_price
        ]
    if max_km is not None:
        results = [r for r in results if (r.get("odometer") or 0) <= max_km]

    # --- Sort ---
    if sort == "price_asc":
        results.sort(key=lambda r: r.get("price") or 0)
    elif sort == "price_desc":
        results.sort(key=lambda r: r.get("price") or 0, reverse=True)
    elif sort == "km_asc":
        results.sort(key=lambda r: r.get("odometer") or 0)
    elif sort == "year_desc":
        results.sort(key=lambda r: r.get("year") or 0, reverse=True)
    else:  # newest
        results.sort(key=lambda r: r.get("found_at") or "", reverse=True)

    return {"listings": results, "total": len(results)}


@app.get("/api/stats")
async def get_stats():
    """Return summary statistics for the dashboard header."""
    total = len(_listings_cache)
    confirmed = sum(
        1 for l in _listings_cache if l.get("fsd_status") == "confirmed"
    )
    likely = sum(
        1 for l in _listings_cache if l.get("fsd_status") == "likely"
    )
    possible = sum(
        1 for l in _listings_cache if l.get("fsd_status") == "possible"
    )
    fsd_total = confirmed + likely + possible
    hw4_count = sum(
        1 for l in _listings_cache if l.get("hw_version") == "HW4"
    )

    # Price stats (exclude None/0 prices)
    prices = [l["price"] for l in _listings_cache if (l.get("price") or 0) > 0]
    avg_price = int(sum(prices) / len(prices)) if prices else 0
    min_price = min(prices) if prices else 0
    max_price = max(prices) if prices else 0

    # Breakdowns
    models_dict: dict[str, int] = {}
    states_dict: dict[str, int] = {}
    sources_dict: dict[str, int] = {}
    for listing in _listings_cache:
        m = listing.get("model", "Unknown")
        models_dict[m] = models_dict.get(m, 0) + 1

        s = listing.get("state") or "Unknown"
        states_dict[s] = states_dict.get(s, 0) + 1

        src = listing.get("source", "Unknown")
        sources_dict[src] = sources_dict.get(src, 0) + 1

    return {
        "total_listings": total,
        "fsd_total": fsd_total,
        "confirmed": confirmed,
        "likely": likely,
        "possible": possible,
        "hw4_count": hw4_count,
        "avg_price": avg_price,
        "min_price": min_price,
        "max_price": max_price,
        "by_model": models_dict,
        "by_state": states_dict,
        "by_source": sources_dict,
        "last_updated": _last_updated,
    }


@app.get("/api/listing/{listing_id}")
async def get_listing(listing_id: str):
    """Return a single listing by ID."""
    for listing in _listings_cache:
        if listing.get("id") == listing_id:
            return listing
    return JSONResponse({"error": "Listing not found"}, status_code=404)


@app.post("/api/refresh")
async def refresh_listings():
    """Re-load listings from disk."""
    _load_listings()
    return {"status": "ok", "total": len(_listings_cache)}


# ---------------------------------------------------------------------------
# Run with:  uvicorn main:app --host 0.0.0.0 --port 8000 --reload
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
