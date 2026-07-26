"""
Tesla FSD Finder Australia - FastAPI Backend v1.2
==================================================
Serves the static frontend and provides API endpoints for listing data.
Integrates with scrapers.py for multi-source data collection.

New in v1.2:
  - Background scraper scheduler (every 6 hours)
  - /api/refresh triggers live re-scrape
  - /api/sources shows per-source health
  - /api/alerts for price drop notifications
  - /api/price-history/{id} for price tracking
  - New filters: source, year_min, year_max, seller_type, has_images
  - Cross-source deduplication
  - Price history tracking

Run locally:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import asyncio
import hashlib
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"
DATA_FILE = DATA_DIR / "listings.json"
PRICE_HISTORY_FILE = DATA_DIR / "price_history.json"
ALERTS_FILE = DATA_DIR / "alerts.json"

SCRAPE_INTERVAL_HOURS = 6

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------

_listings_cache: list[dict] = []
_last_updated: Optional[str] = None
_last_scrape_status: str = "idle"  # idle | running | completed | failed
_price_history: dict[str, list[dict]] = {}  # listing_id -> [{price, date}]
_alerts: list[dict] = []  # price drop alerts
_source_health: dict = {}
_scrape_task: Optional[asyncio.Task] = None


# ---------------------------------------------------------------------------
# Normalisation (backward compat with v1.0 data)
# ---------------------------------------------------------------------------

def _normalise_listing(raw: dict, index: int) -> dict:
    source_url = raw.get("source_url", "")
    if source_url:
        listing_id = hashlib.md5(source_url.encode()).hexdigest()[:12]
    else:
        listing_id = f"listing-{index:04d}"

    source_raw = raw.get("source", "unknown")
    source_display = {
        "drive": "Drive", "autotrader": "AutoTrader",
        "gumtree": "Gumtree", "carsales": "Carsales",
        "carsguide": "CarsGuide", "pickles": "Pickles",
        "facebook": "Facebook",
    }.get(source_raw.lower(), source_raw.title())

    return {
        "id": raw.get("id", listing_id),
        "title": raw.get("title", "Unknown Tesla"),
        "model": raw.get("model", "Unknown"),
        "year": raw.get("year"),
        "variant": raw.get("variant", ""),
        "price": raw.get("price"),
        "price_str": raw.get("price_str", ""),
        "price_driveaway": raw.get("price_driveaway"),
        "price_rating": raw.get("price_rating", ""),
        "price_dropped": raw.get("price_dropped", False),
        "price_drop_pct": raw.get("price_drop_pct", 0),
        "previous_price": raw.get("previous_price"),
        "odometer": raw.get("odometer") or raw.get("odometer_km") or 0,
        "colour": raw.get("colour", ""),
        "body_type": raw.get("body_type", ""),
        "fuel_type": raw.get("fuel_type", "Electric"),
        "transmission": raw.get("transmission", ""),
        "condition": raw.get("condition", ""),
        "location": raw.get("location", ""),
        "state": raw.get("state", ""),
        "lat": raw.get("lat") or raw.get("latitude"),
        "lng": raw.get("lng") or raw.get("longitude"),
        "fsd_status": raw.get("fsd_status", "none"),
        "has_fsd": raw.get("has_fsd", False),
        "has_eap": raw.get("has_eap", False),
        "fsd_keywords_found": raw.get("fsd_keywords_found", []),
        "fsd_confidence": raw.get("fsd_confidence", 0),
        "hw_version": raw.get("hw_version"),
        # v2.0: precise classification fields (see classify.py). fsd_transfer
        # is the important one -- "purchased_outright" transfers on private
        # sale, "subscription_active" does not, regardless of fsd_status.
        "mcu_version": raw.get("mcu_version"),
        "fsd_transfer": raw.get("fsd_transfer", "none"),
        "supercharging_status": raw.get("supercharging_status", "none"),
        "classification_warnings": raw.get("warnings", []),
        "classification": raw.get("classification"),
        "discovery_query": raw.get("discovery_query", ""),
        "detail_page_fetched": raw.get("detail_page_fetched", False),
        "source": source_display,
        "source_url": raw.get("source_url", ""),
        "seller_type": raw.get("seller_type", ""),
        "seller_name": raw.get("seller_name", ""),
        "image_url": raw.get("image_url", ""),
        "description": raw.get("description", ""),
        "found_at": raw.get("found_at") or raw.get("date_found", ""),
        "date_listed": raw.get("date_listed", ""),
        "is_active": raw.get("is_active", True),
    }


# ---------------------------------------------------------------------------
# Data loading & persistence
# ---------------------------------------------------------------------------

def _load_listings() -> list[dict]:
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
            _listings_cache = [
                _normalise_listing(item, i) for i, item in enumerate(raw_list)
            ]
            if not _last_updated:
                dates = [
                    item.get("found_at", "")
                    for item in _listings_cache if item.get("found_at")
                ]
                _last_updated = (
                    max(dates) if dates
                    else datetime.now(timezone.utc).isoformat()
                )
            return _listings_cache
        except Exception as e:
            logger.error(f"Failed to load {DATA_FILE}: {e}")
    _last_updated = datetime.now(timezone.utc).isoformat()
    _listings_cache = []
    return _listings_cache


def _save_listings(listings: list[dict]):
    global _listings_cache, _last_updated
    _last_updated = datetime.now(timezone.utc).isoformat()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_updated": _last_updated,
        "total": len(listings),
        "listings": listings,
    }
    with open(DATA_FILE, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    _listings_cache = listings
    logger.info(f"Saved {len(listings)} listings to {DATA_FILE}")


def _load_price_history():
    global _price_history
    if PRICE_HISTORY_FILE.exists():
        try:
            with open(PRICE_HISTORY_FILE, "r") as f:
                _price_history = json.load(f)
        except Exception:
            _price_history = {}


def _save_price_history():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(PRICE_HISTORY_FILE, "w") as f:
        json.dump(_price_history, f, indent=2)


def _load_alerts():
    global _alerts
    if ALERTS_FILE.exists():
        try:
            with open(ALERTS_FILE, "r") as f:
                _alerts = json.load(f)
        except Exception:
            _alerts = []


def _save_alerts():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(ALERTS_FILE, "w") as f:
        json.dump(_alerts[-500:], f, indent=2)  # Keep last 500


# ---------------------------------------------------------------------------
# Price tracking
# ---------------------------------------------------------------------------

def _track_prices(new_listings: list[dict]):
    global _price_history, _alerts
    now_iso = datetime.now(timezone.utc).isoformat()

    for listing in new_listings:
        lid = listing.get("id", "")
        price = listing.get("price")
        if not lid or not price:
            continue

        if lid not in _price_history:
            _price_history[lid] = []

        history = _price_history[lid]

        # Only record if price changed
        if history and history[-1].get("price") == price:
            continue

        old_price = history[-1]["price"] if history else None
        history.append({"price": price, "date": now_iso})

        # Keep last 50 price points per listing
        if len(history) > 50:
            _price_history[lid] = history[-50:]

        # Detect price drop
        if old_price and price < old_price:
            drop_pct = round((old_price - price) / old_price * 100, 1)
            listing["price_dropped"] = True
            listing["price_drop_pct"] = drop_pct
            listing["previous_price"] = old_price

            _alerts.append({
                "type": "price_drop",
                "listing_id": lid,
                "title": listing.get("title", ""),
                "old_price": old_price,
                "new_price": price,
                "drop_pct": drop_pct,
                "source": listing.get("source", ""),
                "source_url": listing.get("source_url", ""),
                "date": now_iso,
            })

    _save_price_history()
    _save_alerts()


# ---------------------------------------------------------------------------
# Background scraping
# ---------------------------------------------------------------------------

async def _run_scrape():
    global _last_scrape_status, _source_health
    _last_scrape_status = "running"
    logger.info("Background scrape starting...")

    try:
        from scrapers import run_all_scrapers, get_source_health
        new_listings = await run_all_scrapers(enrich=True)

        if new_listings:
            # Normalise scraped data
            normalised = [
                _normalise_listing(l, i) for i, l in enumerate(new_listings)
            ]
            _track_prices(normalised)
            _save_listings(normalised)
            _source_health = get_source_health(normalised)
            _last_scrape_status = "completed"
            logger.info(f"Scrape completed: {len(normalised)} listings")
        else:
            _last_scrape_status = "completed"
            logger.warning("Scrape returned 0 listings, keeping existing data")
    except Exception as e:
        _last_scrape_status = "failed"
        logger.error(f"Scrape failed: {e}")


async def _scheduler():
    """Run scraper every SCRAPE_INTERVAL_HOURS."""
    while True:
        await asyncio.sleep(SCRAPE_INTERVAL_HOURS * 3600)
        await _run_scrape()


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    _load_listings()
    _load_price_history()
    _load_alerts()

    fsd_counts: dict[str, int] = {}
    for l in _listings_cache:
        s = l.get("fsd_status", "none")
        fsd_counts[s] = fsd_counts.get(s, 0) + 1
    logger.info(f"Loaded {len(_listings_cache)} listings. FSD: {fsd_counts}")

    # Update source health from loaded data
    global _source_health
    try:
        from scrapers import get_source_health
        _source_health = get_source_health(_listings_cache)
    except ImportError:
        pass

    # Start background scheduler
    task = asyncio.create_task(_scheduler())

    yield

    # Shutdown
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Tesla FSD Finder Australia",
    description="Find underpriced Teslas with Full Self-Driving in Australia",
    version="1.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def root():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path), media_type="text/html")
    return JSONResponse(
        {"error": "Frontend not found. Place index.html in /static/"},
        status_code=404,
    )


@app.get("/api/health")
async def health():
    return {
        "status": "healthy",
        "total_listings": len(_listings_cache),
        "last_updated": _last_updated,
        "scrape_status": _last_scrape_status,
        "version": "1.2.0",
    }


@app.get("/api/listings")
async def get_listings(
    model: Optional[str] = Query(None, description="Comma-separated model names"),
    state: Optional[str] = Query(None, description="Comma-separated state codes"),
    fsd_status: Optional[str] = Query(None, description="confirmed,likely,possible,none"),
    source: Optional[str] = Query(None, description="Comma-separated sources"),
    seller_type: Optional[str] = Query(None, description="Dealer,Private,Auction"),
    year_min: Optional[int] = Query(None, ge=2010),
    year_max: Optional[int] = Query(None, le=2030),
    min_price: Optional[int] = Query(None, ge=0),
    max_price: Optional[int] = Query(None, ge=0),
    max_km: Optional[int] = Query(None, ge=0),
    has_images: Optional[bool] = Query(None),
    price_dropped: Optional[bool] = Query(None),
    search: Optional[str] = Query(None, description="Free-text search"),
    sort: Optional[str] = Query("newest", description="newest|price_asc|price_desc|km_asc|year_desc|drops"),
):
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
        results = [r for r in results if r.get("fsd_status", "").lower() in statuses]
    if source:
        sources = {s.strip().lower() for s in source.split(",")}
        results = [r for r in results if r.get("source", "").lower() in sources]
    if seller_type:
        types = {t.strip().lower() for t in seller_type.split(",")}
        results = [r for r in results if r.get("seller_type", "").lower() in types]
    if year_min is not None:
        results = [r for r in results if (r.get("year") or 0) >= year_min]
    if year_max is not None:
        results = [r for r in results if (r.get("year") or 9999) <= year_max]
    if min_price is not None:
        results = [r for r in results if (r.get("price") or 0) >= min_price]
    if max_price is not None:
        results = [r for r in results if (r.get("price") or 999_999_999) <= max_price]
    if max_km is not None:
        results = [r for r in results if (r.get("odometer") or 0) <= max_km]
    if has_images is not None:
        if has_images:
            results = [r for r in results if r.get("image_url")]
        else:
            results = [r for r in results if not r.get("image_url")]
    if price_dropped is not None:
        results = [r for r in results if r.get("price_dropped") == price_dropped]
    if search:
        q = search.lower()
        results = [
            r for r in results
            if q in r.get("title", "").lower()
            or q in r.get("description", "").lower()
            or q in r.get("location", "").lower()
            or q in r.get("variant", "").lower()
        ]

    # --- Sort ---
    sort_map = {
        "price_asc": lambda r: r.get("price") or 0,
        "price_desc": lambda r: -(r.get("price") or 0),
        "km_asc": lambda r: r.get("odometer") or 0,
        "year_desc": lambda r: -(r.get("year") or 0),
        "drops": lambda r: -(r.get("price_drop_pct") or 0),
        "newest": lambda r: r.get("found_at") or "",
    }
    if sort in ("newest", "drops"):
        results.sort(key=sort_map.get(sort, sort_map["newest"]), reverse=True)
    else:
        results.sort(key=sort_map.get(sort, sort_map["newest"]))

    return {"listings": results, "total": len(results)}


@app.get("/api/stats")
async def get_stats():
    total = len(_listings_cache)
    confirmed = sum(1 for l in _listings_cache if l.get("fsd_status") == "confirmed")
    likely = sum(1 for l in _listings_cache if l.get("fsd_status") == "likely")
    possible = sum(1 for l in _listings_cache if l.get("fsd_status") == "possible")
    fsd_total = confirmed + likely + possible
    hw4_count = sum(1 for l in _listings_cache if l.get("hw_version") == "HW4")
    drops_count = sum(1 for l in _listings_cache if l.get("price_dropped"))

    prices = [l["price"] for l in _listings_cache if (l.get("price") or 0) > 0]
    avg_price = int(sum(prices) / len(prices)) if prices else 0
    min_price = min(prices) if prices else 0
    max_price = max(prices) if prices else 0

    models_dict: dict[str, int] = {}
    states_dict: dict[str, int] = {}
    sources_dict: dict[str, int] = {}
    years_dict: dict[str, int] = {}
    seller_types_dict: dict[str, int] = {}

    for listing in _listings_cache:
        m = listing.get("model", "Unknown")
        models_dict[m] = models_dict.get(m, 0) + 1
        s = listing.get("state") or "Unknown"
        states_dict[s] = states_dict.get(s, 0) + 1
        src = listing.get("source", "Unknown")
        sources_dict[src] = sources_dict.get(src, 0) + 1
        yr = str(listing.get("year", "Unknown"))
        years_dict[yr] = years_dict.get(yr, 0) + 1
        st = listing.get("seller_type") or "Unknown"
        seller_types_dict[st] = seller_types_dict.get(st, 0) + 1

    # Price distribution buckets (10k intervals)
    price_buckets: dict[str, int] = {}
    for p in prices:
        bucket = f"${(p // 10000) * 10}k-${((p // 10000) + 1) * 10}k"
        price_buckets[bucket] = price_buckets.get(bucket, 0) + 1

    return {
        "total_listings": total,
        "fsd_total": fsd_total,
        "confirmed": confirmed,
        "likely": likely,
        "possible": possible,
        "hw4_count": hw4_count,
        "price_drops": drops_count,
        "avg_price": avg_price,
        "min_price": min_price,
        "max_price": max_price,
        "by_model": models_dict,
        "by_state": states_dict,
        "by_source": sources_dict,
        "by_year": years_dict,
        "by_seller_type": seller_types_dict,
        "price_distribution": price_buckets,
        "last_updated": _last_updated,
        "scrape_status": _last_scrape_status,
    }


@app.get("/api/listing/{listing_id}")
async def get_listing(listing_id: str):
    for listing in _listings_cache:
        if listing.get("id") == listing_id:
            return listing
    return JSONResponse({"error": "Listing not found"}, status_code=404)


@app.get("/api/sources")
async def get_sources():
    return {
        "sources": _source_health,
        "last_updated": _last_updated,
        "scrape_status": _last_scrape_status,
    }


@app.get("/api/alerts")
async def get_alerts(
    limit: int = Query(50, ge=1, le=200),
):
    return {
        "alerts": _alerts[-limit:],
        "total": len(_alerts),
    }


@app.get("/api/price-history/{listing_id}")
async def get_price_history(listing_id: str):
    history = _price_history.get(listing_id)
    if history is None:
        return JSONResponse({"error": "No price history found"}, status_code=404)
    return {
        "listing_id": listing_id,
        "history": history,
        "total_points": len(history),
    }


@app.post("/api/refresh")
async def refresh_listings(background_tasks: BackgroundTasks):
    global _last_scrape_status
    if _last_scrape_status == "running":
        return JSONResponse(
            {"status": "already_running", "message": "A scrape is already in progress"},
            status_code=409,
        )
    background_tasks.add_task(_run_scrape)
    return {"status": "started", "message": "Scrape started in background"}


@app.post("/api/refresh-disk")
async def refresh_from_disk():
    _load_listings()
    return {"status": "ok", "total": len(_listings_cache)}


# ---------------------------------------------------------------------------
# Push Notification Device Registration (iOS / APNs)
# ---------------------------------------------------------------------------

DEVICES_FILE = DATA_DIR / "devices.json"

def _load_devices() -> dict:
    if DEVICES_FILE.exists():
        try:
            return json.loads(DEVICES_FILE.read_text())
        except Exception:
            pass
    return {}

def _save_devices(devices: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DEVICES_FILE.write_text(json.dumps(devices, indent=2))


@app.post("/api/register-device")
async def register_device(
    token: str = Query(..., description="APNs device token"),
    platform: str = Query("ios", description="Platform identifier"),
    alerts_enabled: bool = Query(True, description="Receive price drop push alerts"),
):
    """Register an iOS device token for push notifications."""
    devices = _load_devices()
    devices[token] = {
        "platform": platform,
        "alerts_enabled": alerts_enabled,
        "registered_at": datetime.now(timezone.utc).isoformat(),
        "last_seen": datetime.now(timezone.utc).isoformat(),
    }
    _save_devices(devices)
    logger.info(f"Device registered: {token[:12]}... ({platform})")
    return {"status": "ok", "token": token[:12] + "...", "alerts_enabled": alerts_enabled}


@app.delete("/api/register-device")
async def unregister_device(
    token: str = Query(..., description="APNs device token to remove"),
):
    """Unregister a device from push notifications."""
    devices = _load_devices()
    if token in devices:
        del devices[token]
        _save_devices(devices)
    return {"status": "ok"}


@app.get("/api/devices/count")
async def device_count():
    """Return count of registered devices (admin/debug)."""
    devices = _load_devices()
    active = sum(1 for d in devices.values() if d.get("alerts_enabled"))
    return {"total": len(devices), "alerts_enabled": active}


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
