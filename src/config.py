"""Central configuration: paths, database URL, API credentials and analysis constants.

Everything that differs between machines comes from `.env`; everything that defines
the analysis (focus hubs, on-time threshold, transfer buffers) lives here so it is
versioned and identical for every run.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# --- Paths -------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_HISTORY_DIR = DATA_DIR / "raw" / "history"   # monthly parquet from Hugging Face
RAW_API_DIR = DATA_DIR / "raw" / "api"           # timestamped live API snapshots
PROCESSED_DIR = DATA_DIR / "processed"
SQL_DIR = PROJECT_ROOT / "sql"
DOCS_DIR = PROJECT_ROOT / "docs"

load_dotenv(PROJECT_ROOT / ".env")

# --- Analysis constants --------------------------------------------------------
TIMEZONE = "Europe/Berlin"

# DB's official punctuality definition: a stop counts as on time if delay < 6 minutes.
ON_TIME_THRESHOLD_MIN = 6

# Transfer buffers (minutes) evaluated in the transfer-risk analysis.
TRANSFER_BUFFERS_MIN = (5, 10, 15)

# Delays above this are treated as implausible and flagged by the quality checks.
MAX_PLAUSIBLE_DELAY_MIN = 600

# Focus hubs. EVA numbers are deliberately left out here: they are resolved and
# verified via the API's /station endpoint in Phase 3, not hard-coded from memory.
FOCUS_HUBS: tuple[str, ...] = (
    "Frankfurt (Main) Hbf",
    "Hannover Hbf",
    "Köln Hbf",
    "Berlin Hbf",
    "München Hbf",
    "Hamburg Hbf",
)

# How each focus hub is named in the piebro dataset's `station_name` column.
# Verified in Phase 2: the dataset uses "Berlin Hauptbahnhof", not "Berlin Hbf", and
# groups several EVA numbers (main hall, S-Bahn/"tief" platforms, wing stations)
# under one `station_name`. Matching on this name therefore captures the whole hub.
HISTORY_STATION_NAMES: dict[str, str] = {
    "Frankfurt (Main) Hbf": "Frankfurt (Main) Hbf",
    "Hannover Hbf": "Hannover Hbf",
    "Köln Hbf": "Köln Hbf",
    "Berlin Hbf": "Berlin Hauptbahnhof",
    "München Hbf": "München Hbf",
    "Hamburg Hbf": "Hamburg Hbf",
}

# Federal state (ISO 3166-2:DE subdivision) per hub, for state-level public holidays.
HUB_STATES: dict[str, str] = {
    "Frankfurt (Main) Hbf": "HE",
    "Hannover Hbf": "NI",
    "Köln Hbf": "NW",
    "Berlin Hbf": "BE",
    "München Hbf": "BY",
    "Hamburg Hbf": "HH",
}

# --- Train classification ----------------------------------------------------------
# `train_type` mixes product codes with operator codes (Phase 2 profile). Rules, in order:
#   1. bus / rail replacement: type or line prefix in BUS_CODES
#   2. long distance: type in LONG_DISTANCE_TYPES (FLX20/FLX30 count as FLX)
#   3. product = type if it is S/RE/RB, else the line prefix (operator codes like ME, NX, SBH)
#   4. regional-express style lines (FEX, NIRE, HBX) and types like RE8/REOE count as RE
#   5. anything else (charter, special trains, unknown) is "other"
BUS_CODES: tuple[str, ...] = ("BUS", "SEV", "BSV", "EV", "SSV", "LEERS")
LONG_DISTANCE_TYPES: tuple[str, ...] = (
    "ICE", "IC", "EC", "ECE", "EN", "NJ", "RJ", "RJX", "TGV", "EUR", "ES", "FLX", "WB", "D", "UEX",
)
REGIONAL_EXPRESS_LINES: tuple[str, ...] = ("FEX", "NIRE", "HBX")

# How each hub is named in the DB Timetables API (`/station` search pattern and the
# exact `name` we expect back). Taken from `xml_station_name` in the historical data.
API_STATION_NAMES: dict[str, str] = {
    "Frankfurt (Main) Hbf": "Frankfurt(Main)Hbf",
    "Hannover Hbf": "Hannover Hbf",
    "Köln Hbf": "Köln Hbf",
    "Berlin Hbf": "Berlin Hbf",
    "München Hbf": "München Hbf",
    "Hamburg Hbf": "Hamburg Hbf",
}

# --- DB Timetables API ------------------------------------------------------------
TIMETABLES_BASE_URL = "https://apis.deutschebahn.com/db-api-marketplace/apis/timetables/v1"
# The Free plan allows 60 calls/min (DB API Marketplace product page, checked 2026-10-21).
# We pace at one call every 3 s = 20 calls/min, a third of the limit.
API_MIN_INTERVAL_S = 3.0
API_TIMEOUT_S = 30.0
# Plans are fetched this many hours ahead (current hour included).
PLAN_HOURS_AHEAD = 3
STATIONS_CACHE = RAW_API_DIR / "stations.json"

# --- Hugging Face source -------------------------------------------------------
HF_DATASET_REPO = "piebro/deutsche-bahn-data"
HUBS_HISTORY_PARQUET = PROCESSED_DIR / "history_hubs.parquet"
CURATED_DIR = PROCESSED_DIR / "curated"            # star-schema tables as parquet, input to load.py
DW_SCHEMA = "dw"


# --- Database ------------------------------------------------------------------
def database_url() -> str:
    """Build the SQLAlchemy URL for the project's PostgreSQL from environment variables."""
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5434")
    db = os.environ["POSTGRES_DB"]
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"


# --- DB Timetables API -----------------------------------------------------------
@dataclass(frozen=True)
class ApiCredentials:
    """DB API Marketplace credentials. `repr` is masked so they never end up in logs."""

    client_id: str
    api_key: str

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return "ApiCredentials(client_id=***, api_key=***)"


def api_credentials() -> ApiCredentials:
    """Read DB_CLIENT_ID / DB_API_KEY from the environment, failing loudly if missing."""
    client_id = os.getenv("DB_CLIENT_ID", "").strip()
    api_key = os.getenv("DB_API_KEY", "").strip()
    if not client_id or not api_key:
        raise RuntimeError(
            "DB_CLIENT_ID and DB_API_KEY must be set in .env (see .env.example)."
        )
    return ApiCredentials(client_id=client_id, api_key=api_key)


# --- Logging ---------------------------------------------------------------------
def setup_logging(level: int = logging.INFO) -> None:
    """Configure a consistent log format for all entry points."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # HTTP client libraries log every request at INFO; keep our own logs readable.
    for noisy in ("httpx", "httpx2", "httpcore", "urllib3", "huggingface_hub"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
