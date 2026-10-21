"""Profile the historical data and write `docs/history_profile.md`.

Every number in the report comes from a query in this file, so the profile can be
regenerated after downloading different months. It answers "what does the data
really contain?" before any cleaning decisions are made.

Usage:
    python -m src.profile_history
"""

from __future__ import annotations

import logging
from datetime import datetime

import duckdb
import pandas as pd

from src.config import DOCS_DIR, HUBS_HISTORY_PARQUET, RAW_HISTORY_DIR, setup_logging

logger = logging.getLogger(__name__)

REPORT_PATH = DOCS_DIR / "history_profile.md"

# (title, explanation, SQL). `raw` = all monthly files, `hub` = filtered focus-hub rows.
SECTIONS: list[tuple[str, str, str]] = [
    (
        "Full dataset per source file",
        "All stations, before filtering. `time` is the actual departure (or arrival) time.",
        """SELECT file_month, count(*) AS n_rows, count(DISTINCT eva) AS n_eva,
                  min(time) AS min_time, max(time) AS max_time
           FROM raw GROUP BY 1 ORDER BY 1""",
    ),
    (
        "Full dataset totals",
        "`id` is unique per row, i.e. the dataset is already deduplicated to one row per train stop and EVA.",
        """SELECT count(*) AS n_rows, count(DISTINCT eva) AS n_eva,
                  count(DISTINCT station_name) AS n_station_names, count(DISTINCT id) AS n_distinct_id
           FROM raw""",
    ),
    (
        "Focus hubs: EVA numbers per hub",
        "A hub is spread over several EVA numbers (main hall, S-Bahn / 'tief' platforms, wing stations).",
        """SELECT hub, station_name, xml_station_name, eva, count(*) AS n_rows
           FROM hub GROUP BY ALL ORDER BY hub, n_rows DESC""",
    ),
    (
        "Focus hubs: rows per month",
        "Used to spot coverage changes between months.",
        "PIVOT (SELECT hub, file_month FROM hub) ON file_month USING count(*) ORDER BY hub",
    ),
    (
        "Focus hubs: days covered",
        "",
        """SELECT hub, count(DISTINCT CAST(time AS DATE)) AS n_days,
                  min(CAST(time AS DATE)) AS first_day, max(CAST(time AS DATE)) AS last_day
           FROM hub GROUP BY 1 ORDER BY 1""",
    ),
    (
        "Focus hubs: days with < 60 % of the hub's median daily rows",
        "Candidates for collection gaps or real service reductions (e.g. construction works) — not distinguishable from this data alone.",
        """WITH d AS (SELECT hub, CAST(time AS DATE) AS day, count(*) AS n FROM hub GROUP BY ALL),
                m AS (SELECT hub, median(n) AS median_n FROM d GROUP BY 1)
           SELECT d.hub, d.day, d.n, m.median_n FROM d JOIN m USING (hub)
           WHERE d.n < 0.6 * m.median_n ORDER BY 1, 2""",
    ),
    (
        "Focus hubs: missing values and flags (% of rows)",
        "",
        """SELECT hub, count(*) AS n_rows,
             round(100 * avg((delay_in_min IS NULL)::INT), 1)           AS pct_delay_null,
             round(100 * avg((NOT has_plan_record)::INT), 1)            AS pct_no_plan_record,
             round(100 * avg((train_type IS NULL)::INT), 1)             AS pct_type_null,
             round(100 * avg((line_number IS NULL)::INT), 1)            AS pct_line_null,
             round(100 * avg((arrival_planned_time IS NULL)::INT), 1)   AS pct_no_arrival,
             round(100 * avg((departure_planned_time IS NULL)::INT), 1) AS pct_no_departure,
             round(100 * avg((arrival_is_canceled OR departure_is_canceled)::INT), 2) AS pct_cancelled,
             round(100 * avg(is_replacement_train::INT), 2)             AS pct_replacement
           FROM hub GROUP BY 1 ORDER BY 1""",
    ),
    (
        "Focus hubs: plan record vs. missing delay",
        "Rows without a plan record and without a delay also lack train type/number, so they cannot be classified.",
        """SELECT has_plan_record, (arrival_is_canceled OR departure_is_canceled) AS cancelled,
                  delay_in_min IS NULL AS delay_null, train_type IS NULL AS type_null, count(*) AS n_rows
           FROM hub GROUP BY ALL ORDER BY n_rows DESC""",
    ),
    (
        "What is `delay_in_min`?",
        "Share of rows (with a delay) where `delay_in_min` equals the departure or arrival difference. "
        "It is the departure delay when a departure exists, otherwise the arrival delay.",
        """SELECT round(avg((delay_in_min = datediff('minute', departure_planned_time, departure_change_time))::INT), 4) AS matches_departure,
                  round(avg((delay_in_min = datediff('minute', arrival_planned_time, arrival_change_time))::INT), 4)     AS matches_arrival,
                  round(avg((delay_in_min = datediff('minute', coalesce(departure_planned_time, arrival_planned_time), time))::INT), 4) AS matches_time_minus_planned
           FROM hub WHERE delay_in_min IS NOT NULL""",
    ),
    (
        "Delay distribution (not cancelled, delay known)",
        "Raw values before any cleaning; on-time = delay < 6 min.",
        """SELECT count(*) AS n_rows, min(delay_in_min) AS min_delay,
                  quantile_cont(delay_in_min, 0.5) AS p50, quantile_cont(delay_in_min, 0.9) AS p90,
                  quantile_cont(delay_in_min, 0.99) AS p99, max(delay_in_min) AS max_delay,
                  sum((delay_in_min < 0)::INT) AS n_negative, sum((delay_in_min > 600)::INT) AS n_over_600,
                  round(100 * avg((delay_in_min < 6)::INT), 2) AS pct_on_time_raw
           FROM hub WHERE delay_in_min IS NOT NULL AND NOT (arrival_is_canceled OR departure_is_canceled)""",
    ),
    (
        "Negative delays (early departures)",
        "",
        """SELECT delay_in_min, count(*) AS n_rows FROM hub WHERE delay_in_min < 0
           GROUP BY 1 ORDER BY 1 DESC LIMIT 10""",
    ),
    (
        "Planned hour of day",
        "Few trains at 02–03 and peaks at 07–08 / 16–17 indicate naive Europe/Berlin local time (not UTC).",
        """SELECT hour(coalesce(departure_planned_time, arrival_planned_time)) AS planned_hour, count(*) AS n_rows
           FROM hub GROUP BY 1 ORDER BY 1""",
    ),
    (
        "Trains past midnight",
        "Rows whose actual date differs from the planned date.",
        """SELECT count(*) AS n_rows FROM hub
           WHERE CAST(time AS DATE) <> CAST(coalesce(departure_planned_time, arrival_planned_time) AS DATE)""",
    ),
    (
        "Same train at one hub under several EVA numbers",
        "Same hub, train type/number and planned time appearing more than once.",
        """SELECT n_eva, count(*) AS n_groups, sum(c) AS n_rows FROM (
             SELECT hub, train_type, train_number, coalesce(departure_planned_time, arrival_planned_time) AS planned,
                    count(*) AS c, count(DISTINCT eva) AS n_eva
             FROM hub WHERE train_number IS NOT NULL GROUP BY ALL HAVING count(*) > 1)
           GROUP BY 1 ORDER BY 1""",
    ),
    (
        "`train_type` values (top 30)",
        "Mixes product codes (ICE, RE, S) with operator codes (BRB, NX, ME, ...).",
        """SELECT coalesce(train_type, '<NULL>') AS train_type, count(*) AS n_rows,
                  round(100 * count(*) / sum(count(*)) OVER (), 2) AS pct
           FROM hub GROUP BY 1 ORDER BY n_rows DESC LIMIT 30""",
    ),
    (
        "Operator-coded `train_type` → `line_number` prefix",
        "For operator codes the product (S / RE / RB) is recoverable from the line number.",
        """SELECT train_type, regexp_extract(line_number, '^([A-Za-z]+)', 1) AS line_prefix, count(*) AS n_rows
           FROM hub WHERE train_type NOT IN ('S', 'ICE', 'IC', 'EC', 'ECE', 'RE', 'RB', 'RJ', 'RJX', 'NJ')
           GROUP BY ALL ORDER BY n_rows DESC LIMIT 30""",
    ),
    (
        "Cancellations per month",
        "",
        """SELECT file_month, count(*) AS n_rows,
                  round(100 * avg((arrival_is_canceled OR departure_is_canceled)::INT), 2) AS pct_cancelled
           FROM hub GROUP BY 1 ORDER BY 1""",
    ),
]


def _to_markdown(df: pd.DataFrame) -> str:
    """Render a DataFrame as a GitHub table without extra dependencies (no `tabulate`)."""
    df = df.astype(object).where(df.notna(), "")
    header = "| " + " | ".join(map(str, df.columns)) + " |"
    sep = "|" + "|".join("---" for _ in df.columns) + "|"
    rows = ["| " + " | ".join(map(str, r)) + " |" for r in df.itertuples(index=False)]
    return "\n".join([header, sep, *rows])


def build_report() -> str:
    """Run all profile queries and return the Markdown report."""
    con = duckdb.connect()
    # DDL statements can't take bound parameters; the paths come from config, not user input.
    con.execute(
        "CREATE VIEW raw AS SELECT *, regexp_extract(filename, 'data-(\\d{4}-\\d{2})', 1) AS file_month "
        f"FROM read_parquet('{RAW_HISTORY_DIR / 'data-*.parquet'}', filename = true)"
    )
    con.execute(f"CREATE TABLE hub AS SELECT * FROM read_parquet('{HUBS_HISTORY_PARQUET}')")

    parts = [
        "# Historical data profile (piebro/deutsche-bahn-data)",
        "",
        f"_Generated by `python -m src.profile_history` on {datetime.now():%Y-%m-%d %H:%M}. "
        "All numbers are query results; nothing is edited by hand._",
    ]
    for title, note, sql in SECTIONS:
        logger.info("Profiling: %s", title)
        parts += ["", f"## {title}", ""]
        if note:
            parts += [note, ""]
        parts.append(_to_markdown(con.sql(sql).df()))
    return "\n".join(parts) + "\n"


def main() -> None:
    setup_logging()
    REPORT_PATH.write_text(build_report(), encoding="utf-8")
    logger.info("Wrote %s", REPORT_PATH)


if __name__ == "__main__":
    main()
