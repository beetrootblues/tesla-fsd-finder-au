# Tesla FSD Finder Australia v2.0

A web application that discovers used Tesla listings across Australian car marketplaces and classifies which ones actually have Full Self-Driving (FSD), which autopilot hardware generation, MCU1 vs MCU2 (Model S/X), and transferable unlimited Supercharging -- features often underpriced or under-described in the resale market.

---

## Overview

Tesla's FSD option and older transferable Supercharging can add real value, but sellers often don't describe them precisely -- or conflate "has FSD" (which might mean an active $149/mo subscription that does **not** transfer) with a one-off $10,100 purchase that does. This tool searches Australian car listing sites every 6 hours via a legitimate search API, classifies each listing's hardware/software claims with an explicit confidence level and evidence trail, and presents everything in a searchable dashboard.

### Key Numbers

| Metric | Value |
|--------|-------|
| Data Sources | Carsales, Drive, Gumtree, CarsGuide -- discovered via search, not direct scraping |
| Classification | 4-tier confidence scoring (Confirmed / Likely / Possible / Unknown), every field carries its evidence |
| FSD Transfer Clarity | Distinguishes purchased-outright (transfers) from active subscription (does not) |
| MCU Detection | MCU1 vs MCU2 for Model S/X (Model 3/Y are MCU2-class from launch) |
| Scrape Interval | Every 6 hours (background scheduler) |
| Price Tracking | Historical price recording with drop alerts |

---

## Data Sources

**v2.0 change:** listings are now *discovered* via [Serper.dev](https://serper.dev) (a Google-backed search API) using `site:` searches, then optionally enriched with a polite, honestly-identified fetch of the listing's own page. This replaced direct scraping with rotating browser User-Agents against sites whose terms of service explicitly prohibit automated access (carsales.com.au runs DataDome specifically to detect this) -- see `discovery.py` for the full reasoning. Facebook Marketplace and Pickles auctions were dropped rather than ported; there's no comparable ToS-compliant path for either. AutoTrader listings from the pre-v2.0 scrape remain in the historical dataset but are no longer a live source.

| Source | Method |
|--------|--------|
| **Carsales.com.au** | Discovered via Serper `site:` search |
| **Drive.com.au** | Discovered via Serper `site:` search |
| **Gumtree.com.au** | Discovered via Serper `site:` search |
| **CarsGuide.com.au** | Discovered via Serper `site:` search |

---

## Features

### Discovery Engine (`discovery.py` + `classify.py`)
- Serper.dev `site:`-restricted search across 4 sources x 4 Tesla models x targeted attribute queries (~A$0.10-0.20 per full run at Serper's published rate)
- Best-effort, honestly-identified detail-page fetch (no header spoofing, robots.txt respected) for full ad text; falls back to the search snippet where blocked
- Classification engine grounded in verified Tesla hardware/software history (see `classify.py` docstring), never a bare fact -- every field is (value, confidence, evidence)
- Cross-source deduplication

### Backend (`main.py`)
- **Background scheduler** -- auto-refreshes every 6 hours
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
| `/api/refresh` | POST | Trigger live re-discovery (background) |
| `/api/refresh-disk` | POST | Reload from disk (no discovery run) |
| `/api/health` | GET | Health check with version info |

### Frontend
- **Source filter pills** -- colour-coded by marketplace
- **3 view modes** -- Cards, Table, and Map (Leaflet)
- **Price drop indicators** -- red arrow with percentage on discounted listings
- **Comparison mode** -- select 2-3 listings for side-by-side comparison
- **Watchlist** -- save listings to localStorage with heart icon
- **FSD transfer clarity badge** -- "FSD owned (transfers)" vs "FSD sub only (won't transfer)", not just a confidence score
- **MCU / unlimited-Supercharging badges** -- Model S/X specific
- **Classification warnings** -- flags contradictions (e.g. HW4 claimed on a Model S) inline on the card
- **Search bar** -- instant free-text search across all fields
- **Dark/light theme toggle** -- persisted to localStorage
- **Mobile bottom nav** -- replaces hamburger menu on small screens
- **Stats dashboard** -- Chart.js charts for sources, prices, models, states

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.11+, FastAPI, Uvicorn |
| Discovery | httpx (async) + Serper.dev search API |
| Frontend | Vanilla JS (ES6+), Bootstrap 5.3, Leaflet, Chart.js |
| Deployment | Railway (Nixpacks), Docker-compatible |
| iOS | Capacitor wrapper around the deployed web app |

---

## Quick Start

### Local Development

```bash
git clone https://github.com/beetrootblues/tesla-fsd-finder-au.git
cd tesla-fsd-finder-au
pip install -r requirements.txt
export SERPER_API_KEY=your_key_here   # optional locally -- omit and it serves data/listings.json as-is
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open [http://localhost:8000](http://localhost:8000)

### Environment Variables

| Variable | Required | Description |
|----------|----------|--------------|
| `SERPER_API_KEY` | **Yes, for live discovery** | Get one at [serper.dev](https://serper.dev) -- 2,500 free queries, then ~$1/1,000. Without it, `/api/refresh` logs an error and returns no new listings; the app still serves whatever is in `data/listings.json`. |
| `PORT` | No | Server port (default: 8000, Railway sets automatically) |
| `MAX_DETAIL_FETCHES` | No | Cap on per-listing detail-page fetches per discovery run (default: 60) |

### Deploy to Railway

1. Go to [railway.app/new](https://railway.app/new) and sign in with GitHub
2. Select "Deploy from GitHub repo" and pick this repository
3. Click Deploy -- Railway auto-detects `railway.json` and `Procfile`
4. Add `SERPER_API_KEY` in Railway's environment variables tab so the scheduled discovery run actually finds anything

---

## Project Structure

```
tesla-fsd-finder-au/
  main.py                  # FastAPI backend (API + scheduler)
  classify.py               # Classification engine (HW/MCU/FSD-transfer/Supercharging)
  discovery.py               # Serper-based discovery layer (replaces v1.2 direct scraping)
  listing_utils.py            # Shared, source-agnostic listing helpers
  scrapers.py               # Thin orchestrator: discovery -> dedup
  requirements.txt         # Python dependencies
  package.json             # Node/Capacitor dependencies (iOS build)
  capacitor.config.ts      # Capacitor iOS configuration
  Procfile                 # Railway/Heroku process file
  railway.json             # Railway deployment config
  nixpacks.toml             # Nixpacks build config
  DEPLOY-IOS.md             # Full App Store / sideload deployment guide
  .gitignore
  data/
    listings.json           # 146 historical listings, backfilled with v2.0 fields; auto-refreshed thereafter
    price_history.json      # Price tracking data (auto-generated)
    alerts.json             # Price drop alerts (auto-generated)
    devices.json            # Registered iOS device tokens (auto-generated)
  static/
    index.html             # Frontend HTML
    app.js                 # Frontend logic + Capacitor bridge
    style.css              # Styles with dark/light theme
    offline.html            # Offline fallback page (iOS)
  ios/
    App/App/
      AppDelegate.swift        # Push notification registration + biometric auth (client-side only -- see note below)
      Info.plist                # iOS app configuration
      OfflineViewController.swift  # Native offline screen
  assets/
    icon-spec.json         # Icon/splash generation spec
  scripts/
    build-ios.sh           # iOS build automation script
```

---

## Classification Logic

See `classify.py` for the full, commented rule set and the researched facts it's grounded in (hardware-generation timelines, AU-specific Model S/X discontinuation, MCU1/2 cutover, FSD purchase-vs-subscription transfer rules, Supercharging transferability window). Every field is `(value, confidence, evidence)` -- nothing is presented as a bare fact, because none of it comes from the vehicle itself, only from what a seller wrote.

| Tier | Meaning |
|------|---------|
| **Confirmed** | Seller's text explicitly states it (or it's structurally guaranteed, e.g. Model 3/Y = MCU2) |
| **Likely** | Strong indirect evidence (a feature that requires the claimed hardware, a build date outside any transition window) |
| **Possible** | Weaker or conflicting evidence (a build date inside a genuine transition window, a claim that contradicts what's possible for an AU-delivered car) |
| **Unknown** | No usable signal in the available text |

---

## iOS App

The web app is wrapped as a native iOS app using [Capacitor](https://capacitorjs.com/).

**Client-side native features implemented:** push notification permission registration, Face ID/Touch ID lock on launch, dark-mode navigation styling (see `AppDelegate.swift`).

**Not yet implemented -- server-side push sending.** Registering for push and receiving one are different things: nothing in `main.py` currently reads `data/devices.json` and calls the Apple Push Notification service when a price drop fires. `/api/register-device` stores the token; actually sending a notification needs an APNs `.p8` key plus a sender added to the Railway backend (see DEPLOY-IOS.md's "Post-Launch" section). Treat "Push Notifications" as partially built, not shipped end-to-end.

### Quick Build

```bash
chmod +x scripts/build-ios.sh
./scripts/build-ios.sh --open
```

Prerequisites: macOS, Xcode 15+, Node 18+, CocoaPods. See [DEPLOY-IOS.md](DEPLOY-IOS.md) for full signing, TestFlight, and App Store / sideload details, including the unsigned-IPA path if you don't have a paid Apple Developer account.

---

## Changelog

### v2.0.0 (July 2026)
- Replaced direct multi-site scraping (rotating browser User-Agents against carsales.com.au, drive.com.au, gumtree.com.au, carsguide.com.au, pickles.com.au, plus a Facebook Marketplace Apify actor) with Serper.dev-based discovery -- see `discovery.py` for why
- Dropped Pickles (salvage/auction, poor fit) and Facebook Marketplace (no ToS-compliant discovery path) rather than porting them
- New `classify.py`: MCU1/MCU2 detection for Model S/X, FSD purchased-outright vs subscription-active distinction, unlimited-Supercharging transferability detection, confidence + evidence on every field
- Fixed AU-specific hardware inference: the old model-year heuristic assigned HW4 to any 2023+ Model S/X, which is impossible -- Tesla never resumed RHD Model S/X production for Australia, so every AU-delivered S/X is a pre-2021 build
- Negation-aware detection ("no FSD", "FSD not included") so disclaimed features aren't scored as present
- Backfilled the existing 146-listing dataset with the new fields rather than discarding it
- New UI badges for MCU version, FSD transfer clarity, Supercharging claims, and classification warnings
- Corrected README/App Store copy that overstated push notifications as fully working

### v1.2.0 (March 2026)
- Added 5 data sources, background scraper scheduler, price history tracking with drop alerts, cross-source deduplication, table view, comparison mode, watchlist, source filter pills, search bar, theme toggle, mobile nav, stats dashboard

### v1.0.0 (March 2026)
- Initial release with Drive.com.au and AutoTrader.com.au, FSD keyword detection, card and map views, basic filtering

---

## License

MIT
