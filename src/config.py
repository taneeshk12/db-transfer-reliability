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

# --- Hugging Face source -------------------------------------------------------
HF_DATASET_REPO = "piebro/deutsche-bahn-data"


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
