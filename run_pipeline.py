"""Run the batch pipeline: filter hubs -> transform -> load into PostgreSQL.

Assumes the monthly history is downloaded (`python -m src.download_history`).

Usage:
    python run_pipeline.py                 # all steps
    python run_pipeline.py --skip-filter   # reuse data/processed/history_hubs.parquet
"""

from __future__ import annotations

import argparse
import logging
import time

from src.config import setup_logging
from src.filter_hubs import filter_hubs
from src.load import load
from src.transform import transform

logger = logging.getLogger("pipeline")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-filter", action="store_true", help="reuse the existing hub parquet")
    args = parser.parse_args()

    setup_logging()
    started = time.monotonic()
    if not args.skip_filter:
        filter_hubs()
    transform()
    load()
    logger.info("Pipeline finished in %.0f s", time.monotonic() - started)


if __name__ == "__main__":
    main()
