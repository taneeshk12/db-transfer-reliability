"""Download selected monthly parquet files from the piebro/deutsche-bahn-data dataset.

Only `monthly_processed_data/data-YYYY-MM.parquet` is used: it is the documented,
already-parsed stop-level table. The raw API dumps (`raw_data/`, ~5 GB/month) are
not needed for the historical analysis.

Usage:
    python -m src.download_history                     # last 6 complete months
    python -m src.download_history --months 2026-04 2026-05
    python -m src.download_history --last 12
"""

from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download

from src.config import HF_DATASET_REPO, RAW_HISTORY_DIR, setup_logging

logger = logging.getLogger(__name__)

MONTHLY_PREFIX = "monthly_processed_data/"
_MONTH_RE = re.compile(r"^monthly_processed_data/data-(\d{4}-\d{2})\.parquet$")


def available_months() -> list[str]:
    """Return all months (YYYY-MM, sorted) that have a monthly processed file on the Hub."""
    files = HfApi().list_repo_files(HF_DATASET_REPO, repo_type="dataset")
    months = sorted(m.group(1) for f in files if (m := _MONTH_RE.match(f)))
    logger.info("Found %d monthly files on the Hub (%s .. %s)", len(months), months[0], months[-1])
    return months


def download_month(month: str, target_dir: Path = RAW_HISTORY_DIR) -> Path:
    """Download one month to `target_dir/data-YYYY-MM.parquet`, skipping it if already present."""
    target = target_dir / f"data-{month}.parquet"
    if target.exists():
        logger.info("%s already present, skipping", target.name)
        return target

    target_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading %s ...", target.name)
    # `local_dir` writes a single copy into the project instead of the global HF cache
    # (the files are ~350 MB each, so a second cached copy wastes GBs). The hub client
    # downloads to an `.incomplete` file first, so an interrupted run leaves no
    # truncated parquet behind.
    downloaded = Path(
        hf_hub_download(
            HF_DATASET_REPO,
            f"{MONTHLY_PREFIX}data-{month}.parquet",
            repo_type="dataset",
            local_dir=target_dir,
        )
    )
    # The client mirrors the repo path (monthly_processed_data/...); flatten it.
    downloaded.rename(target)
    logger.info("Saved %s (%.1f MB)", target.name, target.stat().st_size / 1e6)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--months", nargs="+", help="Explicit months as YYYY-MM")
    group.add_argument("--last", type=int, default=6, help="Number of most recent months (default 6)")
    args = parser.parse_args()
    setup_logging()

    available = available_months()
    if args.months:
        missing = sorted(set(args.months) - set(available))
        if missing:
            raise SystemExit(f"Months not available on the Hub: {missing}")
        months = sorted(args.months)
    else:
        months = available[-args.last:]

    logger.info("Selected months: %s", ", ".join(months))
    for month in months:
        download_month(month)


if __name__ == "__main__":
    main()
