"""One collector run = one snapshot of all focus hubs.

Per run and EVA number:
1. `/plan` for the current hour and the next `PLAN_HOURS_AHEAD - 1` hours, but only for
   hours not fetched before (plans are static, so each hour is fetched once).
2. `/fchg` (full changes), every run. Repeated snapshots of the same stop are expected;
   `transform.py` keeps the latest one per stop.

Output (all under data/raw/api/, gitignored):
    stations.json                                 resolved hubs -> EVA numbers (cached)
    xml/station/<hub>.xml                         raw /station responses
    xml/plan/<eva>/<YYMMDDHH>.xml.gz              raw /plan responses
    xml/fchg/<eva>/<snapshot UTC>.xml.gz          raw /fchg responses
    parsed/plan/<eva>_<YYMMDDHH>.parquet          parsed plan rows
    parsed/changes/changes_<snapshot UTC>.parquet parsed change rows of all EVAs + snapshot_ts

Raw XML is archived (gzip) so the parser can be fixed and re-run without re-collecting.

Usage:
    python -m src.collector.collect                    # one snapshot
    python -m src.collector.collect --refresh-stations # re-resolve EVA numbers first
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src.collector.api_client import TimetablesClient
from src.collector.parse_xml import parse_changes, parse_plan, parse_station
from src.config import (
    API_STATION_NAMES,
    PLAN_HOURS_AHEAD,
    RAW_API_DIR,
    STATIONS_CACHE,
    TIMEZONE,
    api_credentials,
    setup_logging,
)

logger = logging.getLogger(__name__)

BERLIN = ZoneInfo(TIMEZONE)
LOCK_FILE = RAW_API_DIR / ".collect.lock"
STALE_LOCK_S = 30 * 60


# --- helpers -----------------------------------------------------------------------
def _write_gz(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(text)


def _acquire_lock() -> bool:
    """Prevent overlapping runs when the scheduler fires while a run is still going.

    Uses an O_EXCL lock file (works on macOS, Linux and Windows); a lock older than
    STALE_LOCK_S is assumed to be left over from a crashed run and is taken over.
    """
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_FILE.exists() and time.time() - LOCK_FILE.stat().st_mtime > STALE_LOCK_S:
        logger.warning("Removing stale lock file %s", LOCK_FILE)
        LOCK_FILE.unlink(missing_ok=True)
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    return True


# --- station resolution --------------------------------------------------------------
def resolve_hubs(client: TimetablesClient, refresh: bool = False) -> dict[str, dict]:
    """Map each focus hub to its main EVA and all related EVAs via `/station`.

    The API's `meta` attribute lists EVAs that belong to the same station (e.g. the
    S-Bahn or "tief" platforms); these are separate EVAs in the data, so all of them
    are collected. The result is cached in stations.json and only refreshed on request.
    """
    if STATIONS_CACHE.exists() and not refresh:
        return json.loads(STATIONS_CACHE.read_text(encoding="utf-8"))

    hubs: dict[str, dict] = {}
    for hub, api_name in API_STATION_NAMES.items():
        xml = client.station(api_name)
        (RAW_API_DIR / "xml" / "station").mkdir(parents=True, exist_ok=True)
        (RAW_API_DIR / "xml" / "station" / f"{hub}.xml").write_text(xml, encoding="utf-8")

        candidates = parse_station(xml)
        matches = [c for c in candidates if c["name"] == api_name]
        if len(matches) != 1:
            names = [c["name"] for c in candidates]
            raise RuntimeError(f"Expected exactly one station named {api_name!r}, got {names}")
        st = matches[0]
        evas = [st["eva"], *[e for e in st["meta_evas"] if e != st["eva"]]]
        hubs[hub] = {"api_name": st["name"], "eva": st["eva"], "ds100": st["ds100"], "evas": evas}
        logger.info("Resolved %s -> EVA %s (all EVAs: %s)", hub, st["eva"], ", ".join(evas))

    STATIONS_CACHE.write_text(json.dumps(hubs, indent=2, ensure_ascii=False), encoding="utf-8")
    return hubs


# --- snapshot --------------------------------------------------------------------------
def fetch_plans(client: TimetablesClient, eva: str, now_utc: datetime) -> int:
    """Fetch and parse not-yet-collected plan hours for one EVA; return the number fetched."""
    fetched = 0
    for h in range(PLAN_HOURS_AHEAD):
        # Step in UTC, then convert: correct across DST changes (wall-clock arithmetic isn't).
        local = (now_utc + timedelta(hours=h)).astimezone(BERLIN)
        slot = local.strftime("%y%m%d%H")
        parsed_path = RAW_API_DIR / "parsed" / "plan" / f"{eva}_{slot}.parquet"
        if parsed_path.exists():
            continue
        xml = client.plan(eva, local.strftime("%y%m%d"), local.strftime("%H"))
        if xml is None:
            logger.warning("No plan published for EVA %s hour %s", eva, slot)
            continue
        _write_gz(RAW_API_DIR / "xml" / "plan" / eva / f"{slot}.xml.gz", xml)
        df = parse_plan(xml, eva)
        df["plan_slot"] = slot
        df["fetched_at"] = now_utc
        parsed_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(parsed_path, index=False)
        fetched += 1
    return fetched


def run_snapshot(client: TimetablesClient, hubs: dict[str, dict]) -> pd.DataFrame:
    """Collect plans + full changes for every EVA of every hub; return the change rows."""
    now_utc = datetime.now(timezone.utc).replace(microsecond=0)
    stamp = now_utc.strftime("%Y%m%dT%H%M%SZ")
    frames, failures, n_evas = [], [], 0

    for hub, info in hubs.items():
        for eva in info["evas"]:
            n_evas += 1
            try:
                n_plans = fetch_plans(client, eva, now_utc)
                xml = client.fchg(eva)
                _write_gz(RAW_API_DIR / "xml" / "fchg" / eva / f"{stamp}.xml.gz", xml)
                changes = parse_changes(xml, eva)
                changes["hub"] = hub
                frames.append(changes)
                logger.info("%s / %s: %d new plan hours, %d change rows", hub, eva, n_plans, len(changes))
            except Exception:  # one failing EVA must not abort the whole snapshot
                logger.exception("Failed to collect %s / EVA %s", hub, eva)
                failures.append(eva)

    if len(failures) == n_evas:
        raise RuntimeError("All EVAs failed; see log above")

    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    result["snapshot_ts"] = now_utc
    out = RAW_API_DIR / "parsed" / "changes" / f"changes_{stamp}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(out, index=False)
    logger.info(
        "Snapshot %s: %d EVAs, %d failed, %d change rows, %d API calls -> %s",
        stamp, n_evas, len(failures), len(result), client.n_calls, out.name,
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect one DB Timetables snapshot for all focus hubs.")
    parser.add_argument("--refresh-stations", action="store_true", help="Re-resolve EVA numbers via /station")
    args = parser.parse_args()
    setup_logging()

    if not _acquire_lock():
        logger.warning("Another collector run is in progress (%s); exiting", LOCK_FILE)
        return 0
    try:
        client = TimetablesClient(api_credentials())
        hubs = resolve_hubs(client, refresh=args.refresh_stations)
        run_snapshot(client, hubs)
        return 0
    except Exception:
        logger.exception("Collector run failed")
        return 1
    finally:
        LOCK_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
