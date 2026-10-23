"""Transfer risk: how often does a planned transfer of B minutes break?

Method (empirical pairs): every non-cancelled arrival at a hub is paired with every non-cancelled
departure at the same hub planned exactly B minutes later (B in TRANSFER_BUFFERS_MIN), excluding
the same train run. A transfer is **missed** if the arriving train actually arrives at or after the
connecting train actually departs. Walking time between platforms is not modelled (no data), so this
is a lower bound for travellers who need time to change.

For comparison, `n_missed_if_departure_on_time` applies the naive rule "arrival delay >= B", i.e.
assumes the connecting train always leaves on time (an upper bound: it ignores that connecting
trains are often late too).

Output: `agg_transfer_risk` (hub × buffer × arrival hour × weekend × arriving/connecting category).

Usage:
    python -m src.transfer_risk
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from src.config import CURATED_DIR, TRANSFER_BUFFERS_MIN, setup_logging

logger = logging.getLogger(__name__)

AGG_TABLE = "agg_transfer_risk"


def build_transfer_risk(con: duckdb.DuckDBPyConnection, buffers: tuple[int, ...] = TRANSFER_BUFFERS_MIN) -> None:
    """Create temp table `agg_transfer_risk` from registered `fact_stop`, `dim_station`, `dim_train`, `dim_date`."""
    buffer_list = ", ".join(str(b) for b in buffers)
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE {AGG_TABLE} AS
        WITH stops AS (
            SELECT f.*, s.hub, t.train_category, d.is_weekend
            FROM fact_stop f
            JOIN dim_station s USING (station_key)
            JOIN dim_train t USING (train_key)
            JOIN dim_date d USING (date_key)
            WHERE NOT f.is_delay_implausible
        ),
        arrivals AS (
            SELECT hub, ride_id, train_category, is_weekend, arrival_actual, arrival_delay_min,
                   hour(arrival_planned)::SMALLINT AS arrival_hour, b.buffer_min,
                   arrival_planned + to_minutes(b.buffer_min) AS target_departure
            FROM stops, (SELECT unnest([{buffer_list}]) AS buffer_min) b
            WHERE arrival_planned IS NOT NULL AND NOT is_arrival_cancelled
        ),
        departures AS (
            SELECT hub, ride_id, train_category, departure_planned, departure_actual
            FROM stops
            WHERE departure_planned IS NOT NULL AND NOT is_departure_cancelled
        )
        SELECT a.hub, a.buffer_min::SMALLINT AS buffer_min, a.arrival_hour, a.is_weekend,
               a.train_category AS arrival_category, d.train_category AS departure_category,
               count(*) AS n_pairs,
               count(*) FILTER (WHERE a.arrival_actual >= d.departure_actual) AS n_missed,
               count(*) FILTER (WHERE a.arrival_delay_min >= a.buffer_min) AS n_missed_if_departure_on_time
        FROM arrivals a
        JOIN departures d ON d.hub = a.hub AND d.departure_planned = a.target_departure
        WHERE d.ride_id <> a.ride_id
        GROUP BY ALL
        ORDER BY ALL
        """
    )


def transfer_risk(curated_dir: Path = CURATED_DIR) -> int:
    """Write `agg_transfer_risk.parquet` next to the star-schema tables and return its row count."""
    con = duckdb.connect()
    for table in ("fact_stop", "dim_station", "dim_train", "dim_date"):
        path = curated_dir / f"{table}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"{path} not found; run src.transform first")
        con.read_parquet(str(path)).create_view(table)
    build_transfer_risk(con)
    con.execute(f"COPY {AGG_TABLE} TO '{curated_dir / f'{AGG_TABLE}.parquet'}' (FORMAT parquet)")

    for buffer_min, n_pairs, pct, pct_naive in con.execute(
        f"""
        SELECT buffer_min, sum(n_pairs), 100.0 * sum(n_missed) / sum(n_pairs),
               100.0 * sum(n_missed_if_departure_on_time) / sum(n_pairs)
        FROM {AGG_TABLE} GROUP BY 1 ORDER BY 1
        """
    ).fetchall():
        logger.info(
            "Buffer %2d min: %s pairs, %.1f %% missed (%.1f %% if connections left on time)",
            buffer_min, f"{n_pairs:,}", pct, pct_naive,
        )
    n_rows = con.execute(f"SELECT count(*) FROM {AGG_TABLE}").fetchone()[0]
    logger.info("Wrote %s rows to %s", f"{n_rows:,}", curated_dir / f"{AGG_TABLE}.parquet")
    return n_rows


if __name__ == "__main__":
    setup_logging()
    transfer_risk()
