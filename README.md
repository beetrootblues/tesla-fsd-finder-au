# Tesla FSD Finder Australia

A web application that aggregates used Tesla listings from major Australian car marketplaces and identifies vehicles that may have Full Self-Driving (FSD) or Enhanced Autopilot (EAP) capabilities -- features that are often underpriced in the resale market.

<!-- ![Tesla FSD Finder Screenshot](screenshot.png) -->

---

## Overview

Tesla's FSD and EAP packages can add $5,000-$15,000+ in value, but sellers often don't highlight these features in their listings. This tool scrapes Australian car listing sites, analyses descriptions for FSD/EAP keywords, and presents the results in a searchable dashboard -- helping buyers find hidden value.

### Current Data Snapshot

| Metric | Value |
|--------|-------|
| Total Listings | 146 |
| FSD Confirmed | 1 |
| FSD Likely (EAP) | 9 |
| FSD Possible | 1 |
| Average Price | $45,103 AUD |
| Price Range | $24,999 - $89,400 AUD |
| Data Sources | Drive.com.au, AutoTrader.com.au |
| Last Updated | March 2026 |

---

## Features

- **Real-time Scraping** -- Aggregates Tesla listings from Drive.com.au and AutoTrader.com.au
- **FSD Detection Engine** -- Keyword-based analysis of listing descriptions and variants to identify FSD/EAP equipped vehicles
- **Advanced Filtering** -- Filter by model (Model 3, Y, S, X), state, price range, kilometres, and FSD status
- **Multiple Sort Options** -- Sort by newest, price (low/high), kilometres, or year
- **Dark-Themed Dashboard** -- Modern, responsive SPA with real-time statistics
- **REST API** -- Full JSON API with OpenAPI/Swagger documentation at `/docs`
- **One-Click Deploy** -- Ready for Railway, Render, Heroku, or any Docker host

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+ / FastAPI |
| Frontend | Vanilla HTML/CSS/JS (no build step) |
| Server | Uvicorn (ASGI) |
| Data | JSON flat-file (scraped listings) |
| Deployment | Railway / Nixpacks |

---

## Project Structure

```
tesla-fsd-finder-au/
├── main.py              # FastAPI app (API + serves frontend)
├── requirements.txt     # Python dependencies
├── Procfile             # Process file for Railway/Heroku
├── railway.json         # Railway deployment config
├── nixpacks.toml        # Nixpacks build config
├── .gitignore
├── README.md
├── static/
│   ├── index.html       # Main SPA page
│   ├── style.css        # Dark theme stylesheet
│   └── app.js           # Frontend application logic
└── data/
    └── listings.json    # Scraped listing data (146 listings)
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- pip

### Local Development

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/tesla-fsd-finder-au.git
cd tesla-fsd-finder-au

# Create virtual environment
python -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start the development server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

### API Documentation

Once running, interactive API docs are available at:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## API Endpoints

### `GET /api/health`
Health check with listing count and last update timestamp.

### `GET /api/stats`
Dashboard statistics: totals, FSD breakdown, price stats, model/state/source distributions.

### `GET /api/listings`
All listings with optional filters:

| Parameter | Type | Description |
|-----------|------|-------------|
| `model` | string | Comma-separated: `Model 3`, `Model Y`, `Model S`, `Model X` |
| `state` | string | Comma-separated state codes: `NSW`, `VIC`, `QLD`, `WA`, `SA`, `TAS`, `ACT`, `NT` |
| `fsd_status` | string | Comma-separated: `confirmed`, `likely`, `possible`, `none` |
| `min_price` | int | Minimum price in AUD |
| `max_price` | int | Maximum price in AUD |
| `max_km` | int | Maximum odometer reading in km |
| `sort` | string | `newest`, `price_asc`, `price_desc`, `km_asc`, `year_desc` |

**Example:**
```bash
# Find FSD-equipped Model 3s under $50k
curl "http://localhost:8000/api/listings?model=Model+3&fsd_status=confirmed,likely&max_price=50000"
```

### `GET /api/listing/{id}`
Single listing detail by ID.

### `POST /api/refresh`
Reload listings from the data file.

---

## FSD Detection

The FSD detection engine analyses each listing's title, description, and variant fields for keywords indicating FSD or EAP capability.

### Detection Levels

| Status | Meaning | Keywords / Signals |
|--------|---------|--------------------|
| **confirmed** | Strong evidence of FSD | "full self-driving", "fsd capability", "fsd included" |
| **likely** | Probable EAP/FSD (Enhanced Autopilot keywords) | "enhanced autopilot", "EAP", "autopilot upgrade", "HW3", "HW4" |
| **possible** | Some autopilot signals worth investigating | "autopilot", "self driving", "autonomous" |
| **none** | No FSD/EAP keywords detected | -- |

### How It Works

1. Listing title, variant, and description text are concatenated and lowercased
2. A tiered keyword matching system checks for FSD, EAP, and autopilot terms
3. Hardware version detection (HW3/HW4) is used as a supporting signal
4. Each listing receives a status (`confirmed` / `likely` / `possible` / `none`)

> **Note:** Keyword detection is heuristic. Always verify FSD status directly with Tesla or through the vehicle's touchscreen before purchasing.

---

## Data Sources

| Source | Method | Coverage |
|--------|--------|----------|
| **Drive.com.au** | Next.js SSR data extraction (`__NEXT_DATA__`) | Titles, prices, locations, variants |
| **AutoTrader.com.au** | Public search API (`listings.platform.autotrader.com.au`) | Full descriptions, seller info, images |

### Data Pipeline

1. **Scrape** -- Fetch Tesla listings from each source using their public endpoints
2. **Normalise** -- Map each source's field names to a unified schema
3. **Deduplicate** -- Remove duplicates based on title + price + location matching
4. **Detect FSD** -- Run keyword analysis on every listing
5. **Serve** -- Load the JSON data into FastAPI's in-memory cache on startup

---

## Deployment

### Railway (Recommended)

1. Push this repo to GitHub
2. Go to [railway.app](https://railway.app) and create a new project
3. Select "Deploy from GitHub repo"
4. Railway auto-detects the `railway.json` and deploys

The included `railway.json` and `nixpacks.toml` handle all configuration.

### Render

1. Create a new Web Service on [render.com](https://render.com)
2. Connect your GitHub repo
3. Set the start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Deploy

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t tesla-fsd-finder .
docker run -p 8000:8000 tesla-fsd-finder
```

### Heroku

The included `Procfile` works with Heroku out of the box:
```bash
heroku create tesla-fsd-finder-au
git push heroku main
```

---

## Model Distribution

| Model | Count | Percentage |
|-------|-------|------------|
| Model 3 | 81 | 55.5% |
| Model Y | 45 | 30.8% |
| Model X | 12 | 8.2% |
| Model S | 8 | 5.5% |

## State Distribution

| State | Count |
|-------|-------|
| VIC | 46 |
| WA | 42 |
| NSW | 24 |
| QLD | 19 |
| ACT | 7 |
| TAS | 1 |
| SA | 1 |

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/add-carsales-scraper`)
3. Commit your changes (`git commit -m 'Add Carsales scraper'`)
4. Push to the branch (`git push origin feature/add-carsales-scraper`)
5. Open a Pull Request

### Ideas for Contribution

- Add Carsales.com.au scraper
- Add Facebook Marketplace integration
- Implement price trend tracking over time
- Add email alerts for new FSD listings
- Improve FSD detection with VIN decoding
- Add map visualisation for listing locations

---

## Disclaimer

This is an independent research project for educational purposes only. It is **not affiliated with, endorsed by, or connected to Tesla, Inc.** in any way.

- Listing data is scraped from publicly available car marketplace websites
- FSD/EAP detection is based on keyword heuristics and may produce false positives or negatives
- Always verify Full Self-Driving capability directly with Tesla or through the vehicle's interface before making a purchase decision
- Prices and availability shown may not reflect current market conditions
- The authors accept no liability for decisions made based on this tool's output

---

## License

MIT License. See [LICENSE](LICENSE) for details.
