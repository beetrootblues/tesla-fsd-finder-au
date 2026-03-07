# Tesla FSD Finder Australia v1.2

A web application that aggregates used Tesla listings from **7 major Australian car marketplaces** and identifies vehicles with Full Self-Driving (FSD) or Enhanced Autopilot (EAP) capabilities -- features often underpriced in the resale market.

---

## Overview

Tesla's FSD and EAP packages can add $5,000-$15,000+ in value, but sellers often don't highlight these features. This tool scrapes Australian car listing sites every 6 hours, analyses descriptions for FSD/EAP keywords, tracks price changes, and presents everything in a searchable dashboard.

### Key Numbers

| Metric | Value |
|--------|-------|
| Data Sources | 7 (Carsales, Drive, AutoTrader, Gumtree, CarsGuide, Pickles, Facebook) |
| FSD Detection | 3-tier confidence scoring (Confirmed / Likely / Possible) |
| HW Inference | Automatic HW2/2.5/3/4 detection from model year |
| Scrape Interval | Every 6 hours (background scheduler) |
| Price Tracking | Historical price recording with drop alerts |

---

## Data Sources

| Source | Method | Coverage |
|--------|--------|----------|
| **Carsales.com.au** | HTML scraping (BeautifulSoup) | Australia's largest marketplace (10M+ monthly visits) |
| **Drive.com.au** | Next.js SSR JSON extraction | 4.8M monthly visits, strong dealer network |
| **AutoTrader.com.au** | JSON-LD + HTML parsing | Part of Gumtree Group |
| **Gumtree.com.au** | Search API + HTML | 6.7M monthly visits, mostly private sellers |
| **CarsGuide.com.au** | Path-based HTML scraping | Part of Gumtree Group, 12K+ car reviews |
| **Pickles.com.au** | Auction listing scraper | Salvage, ex-fleet, insurance write-offs |
| **Facebook Marketplace** | Apify actor (optional) | Requires `APIFY_TOKEN` env var |

---

## Features

### Scraping Engine (`scrapers.py`)
- **7 concurrent scrapers** with async httpx
- Rotating User-Agent headers and 2s rate limiting
- FSD keyword detection with 3-tier confidence scoring
- Australian state inference from location strings
- Hardware version inference from model year + model name
- Cross-source deduplication (fuzzy matching on title + price + state)
- Detail page enrichment for FSD-possible listings

### Backend (`main.py`)
- **Background scheduler** -- auto-scrapes every 6 hours
- **Price history tracking** -- records price changes, detects drops
- **Price drop alerts** -- automatic notifications when prices decrease
- **Expanded filters** -- source, year range, seller type, has images, price drops
- **Free-text search** -- across title, description, location, variant

#### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/listings` | GET | All listings with filters and sorting |
| `/api/stats` | GET | Dashboard statistics with breakdowns |
| `/api/sources` | GET | Per-source health and counts |
| `/api/alerts` | GET | Price drop notifications |
| `/api/price-history/{id}` | GET | Price history for a specific listing |
| `/api/listing/{id}` | GET | Single listing details |
| `/api/refresh` | POST | Trigger live re-scrape (background) |
| `/api/refresh-disk` | POST | Reload from disk (no scrape) |
| `/api/health` | GET | Health check with version info |

### Frontend
- **Source filter pills** -- colour-coded by marketplace
- **3 view modes** -- Cards, Table, and Map (Leaflet)
- **Price drop indicators** -- red arrow with percentage on discounted listings
- **Comparison mode** -- select 2-3 listings for side-by-side comparison
- **Watchlist** -- save listings to localStorage with heart icon
- **FSD deadline banner** -- countdown to March 31, 2026 subscription-only cutoff
- **Search bar** -- instant free-text search across all fields
- **Dark/light theme toggle** -- persisted to localStorage
- **Mobile bottom nav** -- replaces hamburger menu on small screens
- **Stats dashboard** -- Chart.js charts for sources, prices, models, states
- **Source-coloured card accents** -- instant visual identification of listing origin

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.11+, FastAPI, Uvicorn |
| Scraping | httpx (async), BeautifulSoup4, lxml |
| Frontend | Vanilla JS (ES6+), Bootstrap 5.3, Leaflet, Chart.js |
| Deployment | Railway (Nixpacks), Docker-compatible |

---

## Quick Start

### Local Development

```bash
# Clone
git clone https://github.com/beetrootblues/tesla-fsd-finder-au.git
cd tesla-fsd-finder-au

# Install dependencies
pip install -r requirements.txt

# Run
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open [http://localhost:8000](http://localhost:8000)

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `PORT` | No | Server port (default: 8000, Railway sets automatically) |
| `APIFY_TOKEN` | No | Apify API token for Facebook Marketplace scraping |

### Deploy to Railway

1. Go to [railway.app/new](https://railway.app/new) and sign in with GitHub
2. Select "Deploy from GitHub repo" and pick this repository
3. Click Deploy -- Railway auto-detects `railway.json` and `Procfile`
4. (Optional) Add `APIFY_TOKEN` in Railway environment variables for Facebook data

No other configuration needed. The app runs with zero required env vars.

---

## Project Structure

```
tesla-fsd-finder-au/
  main.py              # FastAPI backend v1.2 (API + scheduler)
  scrapers.py          # Multi-source scraper engine (7 sources)
  requirements.txt     # Python dependencies
  Procfile             # Railway/Heroku process file
  railway.json         # Railway deployment config
  nixpacks.toml        # Nixpacks build config
  .gitignore
  data/
    listings.json      # Scraped listing data (auto-generated)
    price_history.json # Price tracking data (auto-generated)
    alerts.json        # Price drop alerts (auto-generated)
  static/
    index.html         # Frontend HTML
    app.js             # Frontend logic (1000+ lines)
    style.css          # Styles with dark/light theme
```

---

## FSD Detection Logic

The scraper analyses listing titles, descriptions, and feature lists for keywords in three tiers:

| Tier | Confidence | Keywords |
|------|-----------|----------|
| **Confirmed** | 100% | "full self-driving", "fsd capability", "fsd included/enabled/purchased" |
| **Likely** | 70% | "enhanced autopilot", "navigate on autopilot", "smart summon", "autopark" |
| **Possible** | 30% | "autopilot", "hw4", "hardware 4", "fsd", "eap" |

Hardware version is inferred from model year:
- **HW4**: Model 3 (2024+), Model Y (2024+), Model S/X (2023+), Cybertruck
- **HW3**: 2020-2023 models
- **HW2.5**: 2018-2019 models

---

## Changelog

### v1.2.0 (March 2026)
- Added 5 new data sources: Carsales, Gumtree, CarsGuide, Pickles, Facebook Marketplace
- Background scraper scheduler (every 6 hours)
- Price history tracking with drop alerts
- Cross-source deduplication
- Table view with sortable columns
- Comparison mode (2-3 listings side-by-side)
- Watchlist with localStorage persistence
- FSD March 31 deadline countdown banner
- Source filter pills with colour coding
- Free-text search bar
- Dark/light theme toggle
- Mobile bottom navigation
- Stats dashboard with Chart.js visualisations
- Expanded API: /api/sources, /api/alerts, /api/price-history/{id}
- New filters: source, year range, seller type, has images, price drops

### v1.0.0 (March 2026)
- Initial release with Drive.com.au and AutoTrader.com.au
- FSD keyword detection
- Card and map views
- Basic filtering (model, state, FSD status, price, km)

---

## License

MIT
