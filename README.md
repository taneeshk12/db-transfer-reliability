# How likely am I to miss my connection?

**Train delay and transfer reliability at Germany's major rail hubs**

> 🚧 Work in progress. Sections marked _TBD_ are filled in once the analysis has produced real results.

## Problem

Anyone changing trains at a German hub wants to know: *if my planned transfer time is 5, 10 or 15 minutes, how likely is it that my arriving train is too late?*
This project measures punctuality and transfer risk at six major hubs:
Frankfurt (Main) Hbf, Hannover Hbf, Köln Hbf, Berlin Hbf, München Hbf and Hamburg Hbf.

### Business questions

1. How punctual are trains at the major hubs (on time = delay < 6 min, DB's official definition), and how do the hubs compare?
2. How do delays differ by train type (long-distance / regional / S-Bahn), hour of day, weekday and month?
3. Which lines or routes are the least reliable?
4. How do cancellations develop over time?
5. Transfer risk: for 5/10/15-minute transfer buffers, how often does an arriving train's delay break the transfer, per hub and time of day?

## Data sources

| Source | Use | License |
|---|---|---|
| [piebro/deutsche-bahn-data](https://huggingface.co/datasets/piebro/deutsche-bahn-data) (Hugging Face) | Historical analysis (monthly parquet) | CC BY 4.0 |
| [DB Timetables API](https://developers.deutschebahn.com/db-api-marketplace) (Deutsche Bahn, DB API Marketplace) | Live collector | CC BY 4.0 |

_Full attribution: TBD (Phase 8)._

## Architecture

_TBD (Mermaid diagram, Phase 8)._

## Data model

_TBD (star schema, Phase 4)._

## Getting started

### Prerequisites

- Python 3.11+
- Docker Desktop (for PostgreSQL 16)
- Power BI Desktop (Windows) for the report
- A DB API Marketplace account with the *Timetables* API subscribed (live collector only)

### Setup

```bash
# 1. Python environment
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Configuration
cp .env.example .env               # then fill in passwords and API credentials

# 3. Database
docker compose up -d               # PostgreSQL 16 on localhost:5434
docker compose ps                  # wait until the status is "healthy"

# 4. Tests
pytest
```

API credentials for the live collector: see [docs/collector.md](docs/collector.md).

### Running the pipeline

_TBD: `python run_pipeline.py` (Phase 4)._

## Repository structure

```
db-transfer-reliability/
├── data/raw/            # downloaded parquet + API snapshots (gitignored)
├── data/processed/      # cleaned data (gitignored)
├── src/
│   ├── config.py             # paths, DB URL, credentials, analysis constants
│   ├── download_history.py   # fetch selected months from Hugging Face
│   ├── collector/            # live API collector (client, XML parser, snapshot runner)
│   ├── transform.py          # cleaning, dedup, delay + on-time flags
│   ├── transfer_risk.py      # transfer failure rates per buffer time
│   ├── load.py               # idempotent load into PostgreSQL
│   └── quality_checks.py
├── sql/                 # schema + analysis queries
├── powerbi/             # DAX measures + report spec
├── docs/                # architecture, data model, quality report
├── tests/               # pytest
├── docker-compose.yml
├── requirements.txt
└── run_pipeline.py      # one command runs the full batch pipeline
```

## Key findings

_TBD: based on real query results (Phase 6/8)._

## Limitations

_TBD._

## Next steps

_TBD._
