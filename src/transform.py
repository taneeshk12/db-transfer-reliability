"""Turn the filtered hub history into star-schema tables (parquet in `data/processed/curated/`).

Steps, all in DuckDB:

1. drop rows without any planned time (no train, no delay; ~1.5 %, see history_profile.md)
2. deduplicate: a train stopping at a hub can appear under several of its EVA numbers.
   Key = hub + ride id + planned time; keep the row with a plan record, then the one with both
   arrival and departure, then the lowest EVA (deterministic)
3. delays from timestamps (actual − planned, minutes), NULL for a cancelled side
4. on-time flags (delay < ON_TIME_THRESHOLD_MIN), NULL when not measurable or implausible
5. keep only stops planned within the covered months
6. classify trains (rules in config.py) and build dim_date / dim_station / dim_train

Usage:
    python -m src.transform
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

import duckdb
import holidays
import pandas as pd

from src.config import (
    BUS_CODES,
    CURATED_DIR,
    HUB_STATES,
    HUBS_HISTORY_PARQUET,
    LONG_DISTANCE_TYPES,
    MAX_PLAUSIBLE_DELAY_MIN,
    ON_TIME_THRESHOLD_MIN,
    REGIONAL_EXPRESS_LINES,
    setup_logging,
)

logger = logging.getLogger(__name__)

TABLES = ("dim_date", "dim_station", "dim_train", "fact_stop")


def _sql_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def classify_sql(train_type: str = "train_type", line_number: str = "line_number") -> tuple[str, str]:
    """SQL expressions (product, train_category) implementing the rules in config.py."""
    t = f"upper({train_type})"
    p = f"upper(nullif(regexp_extract({line_number}, '^[A-Za-z]+'), ''))"
    product = f"""
        CASE
            WHEN {t} IN ({_sql_list(BUS_CODES)}) OR {p} IN ({_sql_list(BUS_CODES)}) THEN 'BUS'
            WHEN {t} LIKE 'FLX%' THEN 'FLX'
            WHEN {t} IN ({_sql_list(LONG_DISTANCE_TYPES)}) THEN {t}
            WHEN {t} IN ('S', 'RE', 'RB') THEN {t}
            WHEN {p} IN ('S', 'RE', 'RB') THEN {p}
            WHEN {p} IN ({_sql_list(REGIONAL_EXPRESS_LINES)}) OR {t} LIKE 'RE%' THEN 'RE'
        END"""
    category = f"""
        CASE
            WHEN ({product}) = 'BUS' THEN 'bus'
            WHEN ({product}) IN ({_sql_list(LONG_DISTANCE_TYPES)}) THEN 'long_distance'
            WHEN ({product}) = 'S' THEN 's_bahn'
            WHEN ({product}) IN ('RE', 'RB') THEN 'regional'
            ELSE 'other'
        END"""
    return product, category


def build_stops(con: duckdb.DuckDBPyConnection, source: str) -> None:
    """Create temp table `stops`: cleaned, deduplicated stops with delays and flags."""
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE stops AS
        WITH base AS (
            SELECT *, coalesce(departure_planned_time, arrival_planned_time) AS planned_ref
            FROM {source}
            WHERE coalesce(departure_planned_time, arrival_planned_time) IS NOT NULL
        ),
        ranked AS (
            SELECT *, row_number() OVER (
                PARTITION BY hub, train_line_ride_id, planned_ref
                ORDER BY has_plan_record DESC,
                         (arrival_planned_time IS NOT NULL AND departure_planned_time IS NOT NULL) DESC,
                         eva
            ) AS rn
            FROM base
        ),
        delays AS (
            SELECT *,
                CASE WHEN NOT arrival_is_canceled
                     THEN date_diff('minute', arrival_planned_time, arrival_change_time) END AS arrival_delay_min,
                CASE WHEN NOT departure_is_canceled
                     THEN date_diff('minute', departure_planned_time, departure_change_time) END AS departure_delay_min
            FROM ranked WHERE rn = 1
        )
        SELECT *,
            coalesce(arrival_delay_min > {MAX_PLAUSIBLE_DELAY_MIN}, false)
                OR coalesce(departure_delay_min > {MAX_PLAUSIBLE_DELAY_MIN}, false) AS is_delay_implausible,
            CASE WHEN arrival_delay_min <= {MAX_PLAUSIBLE_DELAY_MIN}
                 THEN arrival_delay_min < {ON_TIME_THRESHOLD_MIN} END AS is_arrival_on_time,
            CASE WHEN departure_delay_min <= {MAX_PLAUSIBLE_DELAY_MIN}
                 THEN departure_delay_min < {ON_TIME_THRESHOLD_MIN} END AS is_departure_on_time
        FROM delays
        """
    )


def build_dim_date(start: date, end: date) -> pd.DataFrame:
    """One row per calendar day with weekday and national public holidays."""
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    national = holidays.Germany(years=range(start.year, end.year + 1), language="en_US")
    return pd.DataFrame(
        {
            "date_key": [int(d.strftime("%Y%m%d")) for d in days],
            "date": days,
            "year": [d.year for d in days],
            "month": [d.month for d in days],
            "month_name": [d.strftime("%B") for d in days],
            "iso_week": [d.isocalendar().week for d in days],
            "weekday_num": [d.isoweekday() for d in days],
            "weekday_name": [d.strftime("%A") for d in days],
            "is_weekend": [d.isoweekday() >= 6 for d in days],
            "is_national_holiday": [d in national for d in days],
            "holiday_name": [national.get(d) for d in days],
        }
    )


def hub_holidays(start: date, end: date) -> pd.DataFrame:
    """(hub, date) pairs that are public holidays in the hub's federal state."""
    years = range(start.year, end.year + 1)
    rows = [
        (hub, d)
        for hub, state in HUB_STATES.items()
        for d in holidays.Germany(subdiv=state, years=years)
        if start <= d <= end
    ]
    return pd.DataFrame(rows, columns=["hub", "holiday_date"])


def transform(source: Path = HUBS_HISTORY_PARQUET, target_dir: Path = CURATED_DIR) -> dict[str, int]:
    """Write the four star-schema tables to `target_dir` and return row counts."""
    if not source.exists():
        raise FileNotFoundError(f"{source} not found; run src.filter_hubs first")
    target_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.read_parquet(str(source)).create_view("src")
    n_source = con.execute("SELECT count(*) FROM src").fetchone()[0]

    build_stops(con, "src")
    n_untyped = con.execute("SELECT count(*) FROM stops WHERE train_type IS NULL").fetchone()[0]
    if n_untyped:
        raise ValueError(f"{n_untyped} stops with a planned time but no train_type; check the source")

    # Keep only stops planned within the covered months: a source file also holds a few trains
    # planned late on the previous month's last day (they ran after midnight), which would
    # otherwise show up as an almost empty extra day/month.
    start, end = con.execute(
        """
        SELECT strptime(min(file_month), '%Y-%m')::DATE,
               last_day(strptime(max(file_month), '%Y-%m'))::DATE
        FROM stops
        """
    ).fetchone()
    n_out_of_range = con.execute(
        "SELECT count(*) FROM stops WHERE planned_ref::DATE NOT BETWEEN ? AND ?", [start, end]
    ).fetchone()[0]
    con.execute("DELETE FROM stops WHERE planned_ref::DATE NOT BETWEEN ? AND ?", [start, end])
    dim_date = build_dim_date(start, end)
    con.register("hub_hol", hub_holidays(start, end))

    dim_station = con.execute(
        """
        SELECT row_number() OVER (ORDER BY hub, eva)::SMALLINT AS station_key,
               eva, hub, any_value(xml_station_name) AS platform_area
        FROM stops GROUP BY eva, hub ORDER BY station_key
        """
    ).df()
    dim_station["state_code"] = dim_station["hub"].map(HUB_STATES)

    product, category = classify_sql()
    dim_train = con.execute(
        f"""
        SELECT row_number() OVER (ORDER BY train_type, line_number NULLS FIRST)::INTEGER AS train_key,
               {category} AS train_category, {product} AS product, train_type, line_number,
               -- digit-only line numbers ("30" for FlixTrain, "7" for S-Bahn) get the product prefix
               CASE WHEN regexp_matches(line_number, '^[0-9]+$') AND {product} IS NOT NULL
                    THEN {product} || CASE WHEN {product} = 'S' THEN '' ELSE ' ' END || line_number
                    ELSE coalesce(nullif(line_number, ''), {product}, train_type)
               END AS line_label
        FROM (SELECT DISTINCT train_type, line_number FROM stops)
        ORDER BY train_key
        """
    ).df()

    fact = con.execute(
        """
        SELECT row_number() OVER (ORDER BY s.planned_ref, st.station_key, s.train_line_ride_id)::BIGINT AS stop_key,
               s.id AS source_id,
               CAST(strftime(s.planned_ref, '%Y%m%d') AS INTEGER) AS date_key,
               hour(s.planned_ref)::SMALLINT AS planned_hour,
               st.station_key, tr.train_key, s.train_number, s.train_line_ride_id AS ride_id,
               s.arrival_planned_time::TIMESTAMP AS arrival_planned,
               s.arrival_change_time::TIMESTAMP AS arrival_actual,
               s.departure_planned_time::TIMESTAMP AS departure_planned,
               s.departure_change_time::TIMESTAMP AS departure_actual,
               s.arrival_delay_min::INTEGER AS arrival_delay_min,
               s.departure_delay_min::INTEGER AS departure_delay_min,
               s.arrival_is_canceled AS is_arrival_cancelled,
               s.departure_is_canceled AS is_departure_cancelled,
               s.arrival_is_canceled OR s.departure_is_canceled AS is_cancelled,
               s.is_arrival_on_time, s.is_departure_on_time, s.is_delay_implausible,
               hh.hub IS NOT NULL AS is_hub_holiday,
               s.has_plan_record, coalesce(s.is_replacement_train, false) AS is_replacement_train,
               s.file_month
        FROM stops s
        JOIN dim_station st ON st.eva = s.eva
        JOIN dim_train tr ON tr.train_type = s.train_type
                         AND tr.line_number IS NOT DISTINCT FROM s.line_number
        LEFT JOIN hub_hol hh ON hh.hub = s.hub AND hh.holiday_date = s.planned_ref::DATE
        """
    ).df()

    counts: dict[str, int] = {}
    for name, frame in zip(TABLES, (dim_date, dim_station, dim_train, fact)):
        frame.to_parquet(target_dir / f"{name}.parquet", index=False)
        counts[name] = len(frame)
    n_planned = con.execute(
        "SELECT count(*) FROM src WHERE coalesce(departure_planned_time, arrival_planned_time) IS NOT NULL"
    ).fetchone()[0]
    counts["dropped_no_planned_time"] = n_source - n_planned
    counts["dropped_out_of_range"] = n_out_of_range
    counts["dropped_duplicates"] = n_planned - n_out_of_range - counts["fact_stop"]
    logger.info(
        "Source %s rows -> %s stops (%s without planned time, %s duplicates removed, %s outside %s..%s)",
        f"{n_source:,}",
        f"{counts['fact_stop']:,}",
        f"{counts['dropped_no_planned_time']:,}",
        f"{counts['dropped_duplicates']:,}",
        f"{n_out_of_range:,}",
        start,
        end,
    )
    logger.info("Curated tables in %s: %s", target_dir, counts)
    return counts


if __name__ == "__main__":
    setup_logging()
    transform()
