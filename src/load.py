"""Load the curated star-schema parquet files into PostgreSQL.

Idempotent: `sql/schema.sql` is applied (CREATE … IF NOT EXISTS), then all tables are truncated
and reloaded with COPY inside one transaction. A failed load leaves the previous data untouched.

Usage:
    python -m src.load
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from src.config import CURATED_DIR, DW_SCHEMA, SQL_DIR, database_url, setup_logging
from src.transfer_risk import AGG_TABLE
from src.transform import TABLES

logger = logging.getLogger(__name__)

NULL_MARKER = r"\N"
# Dimensions first, then the fact (foreign keys), then the aggregate.
LOAD_TABLES = (*TABLES, AGG_TABLE)


def frame_to_csv(frame: pd.DataFrame) -> io.StringIO:
    """CSV buffer for COPY; NULLs written as \\N so empty strings stay distinct from NULL."""
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False, header=False, na_rep=NULL_MARKER)
    buffer.seek(0)
    return buffer


def load(source_dir: Path = CURATED_DIR, url: str | None = None) -> dict[str, int]:
    """Reload all star-schema tables and return the row count of each table in the database."""
    missing = [t for t in LOAD_TABLES if not (source_dir / f"{t}.parquet").exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing curated tables {missing} in {source_dir}; run src.transform and src.transfer_risk first"
        )

    engine = create_engine(url or database_url())
    schema_sql = (SQL_DIR / "schema.sql").read_text(encoding="utf-8")
    counts: dict[str, int] = {}
    with engine.begin() as conn:
        conn.execute(text(schema_sql))
        conn.execute(text(f"TRUNCATE {', '.join(f'{DW_SCHEMA}.{t}' for t in LOAD_TABLES)}"))
        cursor = conn.connection.cursor()
        for table in LOAD_TABLES:
            # numpy_nullable keeps integer columns with NULLs as integers (not 5.0 floats).
            frame = pd.read_parquet(source_dir / f"{table}.parquet", dtype_backend="numpy_nullable")
            columns = ", ".join(frame.columns)
            cursor.copy_expert(
                f"COPY {DW_SCHEMA}.{table} ({columns}) FROM STDIN WITH (FORMAT csv, NULL '{NULL_MARKER}')",
                frame_to_csv(frame),
            )
            counts[table] = conn.execute(text(f"SELECT count(*) FROM {DW_SCHEMA}.{table}")).scalar_one()
            if counts[table] != len(frame):
                raise RuntimeError(f"{table}: loaded {counts[table]} rows, expected {len(frame)}")
            logger.info("Loaded %s rows into %s.%s", f"{counts[table]:,}", DW_SCHEMA, table)
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f"ANALYZE {', '.join(f'{DW_SCHEMA}.{t}' for t in LOAD_TABLES)}"))
    return counts


if __name__ == "__main__":
    setup_logging()
    load()
