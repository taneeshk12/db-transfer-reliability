"""Filter the downloaded monthly parquet files to the six focus hubs.

DuckDB scans the ~88M-row monthly files out of core and writes only the ~1.7M hub
rows to `data/processed/history_hubs.parquet`. No cleaning happens here (that is
`transform.py`); this step only adds two columns:

- `hub`         canonical hub name (e.g. "Berlin Hbf"), independent of dataset naming
- `file_month`  the source file's month, kept for lineage and coverage checks

Usage:
    python -m src.filter_hubs
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from src.config import HISTORY_STATION_NAMES, HUBS_HISTORY_PARQUET, RAW_HISTORY_DIR, setup_logging

logger = logging.getLogger(__name__)


def filter_hubs(
    source_glob: str = str(RAW_HISTORY_DIR / "data-*.parquet"),
    target: Path = HUBS_HISTORY_PARQUET,
) -> int:
    """Write all rows of the focus hubs to `target` and return the number of rows written."""
    if not list(RAW_HISTORY_DIR.glob("data-*.parquet")):
        raise FileNotFoundError(f"No monthly files in {RAW_HISTORY_DIR}; run src.download_history first")

    target.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    # Small lookup table dataset name -> canonical hub name, joined instead of a CASE chain.
    con.execute("CREATE TEMP TABLE hub_map (station_name VARCHAR, hub VARCHAR)")
    con.executemany(
        "INSERT INTO hub_map VALUES (?, ?)",
        [(dataset_name, hub) for hub, dataset_name in HISTORY_STATION_NAMES.items()],
    )
    con.execute(
        f"""
        COPY (
            SELECT m.hub,
                   regexp_extract(h.filename, 'data-(\\d{{4}}-\\d{{2}})', 1) AS file_month,
                   h.* EXCLUDE (filename)
            FROM read_parquet(?, filename = true) h
            JOIN hub_map m USING (station_name)
        ) TO '{target}' (FORMAT parquet, COMPRESSION zstd)
        """,
        [source_glob],
    )
    n_rows = con.execute("SELECT count(*) FROM read_parquet(?)", [str(target)]).fetchone()[0]
    logger.info("Wrote %s hub rows to %s", f"{n_rows:,}", target)
    return n_rows


if __name__ == "__main__":
    setup_logging()
    filter_hubs()
