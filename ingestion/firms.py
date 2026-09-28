"""Download NASA FIRMS active-fire detections for each study region.

Uses the FIRMS area API, which needs a free MAP_KEY:
https://firms.modaps.eosdis.nasa.gov/api/area/

    /api/area/csv/{MAP_KEY}/{SOURCE}/{west,south,east,north}/{DAY_RANGE}/{START_DATE}

One request covers at most DAY_RANGE days, so we walk the study window in
chunks and write one CSV per region and month. A MAP_KEY allows 5,000
transactions per 10 minutes — a 4-year window is ~300 requests per region.

Sources: by default each month uses VIIRS_SNPP_SP, the "standard processing"
archive (science quality, from 2012, a few months of lag), and falls back to
VIIRS_SNPP_NRT (near real time) for months the archive does not cover yet.
Coverage dates come from the FIRMS data_availability endpoint.

Usage:
    export FIRMS_MAP_KEY=...            # or put it in .env, or in the Databricks secret wildfire/firms_map_key
    python ingestion/firms.py
    python ingestion/firms.py --regions north_evia --source MODIS_SP   # force one source
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

# Databricks job tasks exec() the script without __file__: fall back to argv[0], and make the
# sibling module `common` importable either way.
HERE = Path(globals().get("__file__") or sys.argv[0]).resolve().parent
sys.path.insert(0, str(HERE))

from common import DEFAULT_OUT, ROOT, get_secret, get_with_retry, load_regions, month_ranges, needs_download, write_csv  # noqa: E402

API = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
AVAILABILITY = "https://firms.modaps.eosdis.nasa.gov/api/data_availability/csv"
DAY_RANGE = 5  # days per request (the API caps this; 5 is safe)

COLUMNS = ["region_id", "source", "latitude", "longitude", "acq_date", "acq_time",
           "satellite", "instrument", "confidence", "frp", "daynight"]


def fetch_range(session, key, source, region, first_day, last_day) -> list[dict]:
    bbox = f"{region.min_lon},{region.min_lat},{region.max_lon},{region.max_lat}"
    rows: list[dict] = []
    day = first_day
    while day <= last_day:
        span = min(DAY_RANGE, (last_day - day).days + 1)
        text = get_with_retry(session, f"{API}/{key}/{source}/{bbox}/{span}/{day.isoformat()}").text
        if text.lstrip().lower().startswith(("invalid", "error")):
            raise RuntimeError(f"FIRMS API error: {text.strip()[:200]}")
        for rec in csv.DictReader(io.StringIO(text)):
            rows.append({"region_id": region.region_id, "source": source,
                         **{c: rec.get(c) for c in COLUMNS[2:]}})
        day += timedelta(days=span)
        time.sleep(0.2)
    return rows


def archive_end(session, key, archive: str) -> date:
    """Last day covered by a standard-processing (SP) source."""
    text = get_with_retry(session, f"{AVAILABILITY}/{key}/{archive}").text
    row = next(csv.DictReader(io.StringIO(text)))
    return date.fromisoformat(row["max_date"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--regions", nargs="*", help="region_ids from dbt/seeds/regions.csv (default: all)")
    parser.add_argument("--source", help="force one FIRMS source (default: VIIRS_SNPP_SP, then _NRT for recent months)")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="landing root folder (local or /Volumes/...)")
    parser.add_argument("--force", action="store_true", help="re-download every month")
    parser.add_argument("--refresh-months", type=int, default=0,
                        help="also re-download the last N months (near-real-time data gets replaced)")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    key = get_secret("FIRMS_MAP_KEY")
    if not key:
        raise SystemExit("FIRMS_MAP_KEY is not set (.env locally, secret wildfire/firms_map_key in Databricks).")

    out_dir = Path(args.out) / "firms"
    out_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    sp_end = None if args.source else archive_end(session, key, "VIIRS_SNPP_SP")

    for region in load_regions(args.regions):
        print(f"{region.region_name}: {region.study_start} -> {region.study_end}")
        for first_day, last_day in month_ranges(region.study_start, region.study_end):
            source = args.source or ("VIIRS_SNPP_SP" if last_day <= sp_end else "VIIRS_SNPP_NRT")
            path = out_dir / f"{region.region_id}_{source}_{first_day:%Y%m}.csv"
            if not needs_download(path, first_day, args.force, args.refresh_months):
                continue
            rows = fetch_range(session, key, source, region, first_day, last_day)
            write_csv(path, COLUMNS, rows)
            print(f"  {first_day:%Y-%m}: {len(rows):>6,} detections ({source})")


if __name__ == "__main__":
    main()
