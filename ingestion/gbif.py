"""Download GBIF occurrences for each study region, one CSV per region and month.

Uses the public occurrence search API (no account needed):
https://techdocs.gbif.org/en/openapi/v1/occurrence

The search API refuses offsets beyond 100,000 records per query and becomes very
slow long before that (pages past ~10,000 can hang), so each month is queried
week by week to keep offsets small. If a single month exceeds that, the script warns — for such
volumes switch to the GBIF Download API (asynchronous, needs a free account).

Usage:
    python ingestion/gbif.py                       # all regions
    python ingestion/gbif.py --regions north_evia  # one region
    python ingestion/gbif.py --out /Volumes/workspace/wildfire_raw/landing  # as a Databricks job task
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import requests

# Databricks job tasks exec() the script without __file__: fall back to argv[0], and make the
# sibling module `common` importable either way.
HERE = Path(globals().get("__file__") or sys.argv[0]).resolve().parent
sys.path.insert(0, str(HERE))

from common import DEFAULT_OUT, get_with_retry, load_regions, month_ranges, needs_download, write_csv  # noqa: E402

API = "https://api.gbif.org/v1/occurrence/search"
PAGE_SIZE = 300          # API maximum
MAX_OFFSET = 100_000     # API hard limit
WORKERS = 2              # default months in parallel (more triggers HTTP 429 rate limiting)
# Same list as the dbt var `kept_basis_of_record`: no need to download museum specimens.
BASIS_OF_RECORD = ["HUMAN_OBSERVATION", "MACHINE_OBSERVATION", "OBSERVATION"]

# GBIF field -> column name in our CSV (snake_case, no SQL reserved words).
FIELDS = {
    "key": "gbif_id",
    "speciesKey": "species_key",
    "species": "species",
    "taxonRank": "taxon_rank",
    "kingdom": "kingdom",
    "phylum": "phylum",
    "class": "class_name",
    "order": "order_name",
    "family": "family",
    "decimalLatitude": "decimal_latitude",
    "decimalLongitude": "decimal_longitude",
    "coordinateUncertaintyInMeters": "coordinate_uncertainty_m",
    "eventDate": "event_date",
    "basisOfRecord": "basis_of_record",
    "datasetKey": "dataset_key",
    "countryCode": "country_code",
}
COLUMNS = ["region_id", *FIELDS.values()]


def fetch_month(session: requests.Session, region, first_day, last_day) -> list[dict]:
    rows: list[dict] = []
    start = first_day
    while start <= last_day:
        end = min(start + timedelta(days=6), last_day)
        rows += fetch_range(session, region, start, end)
        start = end + timedelta(days=1)
    return rows


def fetch_range(session: requests.Session, region, first_day, last_day) -> list[dict]:
    params = {
        "decimalLatitude": f"{region.min_lat},{region.max_lat}",
        "decimalLongitude": f"{region.min_lon},{region.max_lon}",
        "eventDate": f"{first_day.isoformat()},{last_day.isoformat()}",
        "hasCoordinate": "true",
        "hasGeospatialIssue": "false",
        "occurrenceStatus": "PRESENT",
        "basisOfRecord": BASIS_OF_RECORD,  # requests repeats the parameter for each value
        "limit": PAGE_SIZE,
        "offset": 0,
    }
    rows: list[dict] = []
    while True:
        page = get_with_retry(session, API, params).json()
        if params["offset"] == 0 and page["count"] > MAX_OFFSET:
            print(f"  ! {page['count']:,} records from {first_day}: only the first "
                  f"{MAX_OFFSET:,} are reachable — use the GBIF Download API for this region.")
        for rec in page["results"]:
            if rec.get("speciesKey") is None:
                continue  # identified above species level: unusable for richness
            rows.append({"region_id": region.region_id,
                         **{col: rec.get(field) for field, col in FIELDS.items()}})
        params["offset"] += PAGE_SIZE
        if page["endOfRecords"] or params["offset"] >= MAX_OFFSET:
            return rows
        time.sleep(0.1)  # be polite to a free public API


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--regions", nargs="*", help="region_ids from dbt/seeds/regions.csv (default: all)")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="landing root folder (local or /Volumes/...)")
    parser.add_argument("--force", action="store_true", help="re-download every month")
    parser.add_argument("--workers", type=int, default=WORKERS, help="months downloaded in parallel")
    parser.add_argument("--refresh-months", type=int, default=0,
                        help="also re-download the last N months, which keep filling up (default: 0)")
    args = parser.parse_args()

    out_dir = Path(args.out) / "gbif"
    out_dir.mkdir(parents=True, exist_ok=True)

    failed: list[str] = []

    def download(region, first_day, last_day) -> int:
        path = out_dir / f"{region.region_id}_{first_day:%Y%m}.csv"
        try:
            rows = fetch_month(requests.Session(), region, first_day, last_day)
        except requests.RequestException as err:  # one bad month must not sink the others
            print(f"  {first_day:%Y-%m}: FAILED ({err}) — will be retried on the next run", flush=True)
            failed.append(f"{region.region_id} {first_day:%Y-%m}")
            return 0
        write_csv(path, COLUMNS, rows)  # only complete months land, so re-runs resume cleanly
        print(f"  {first_day:%Y-%m}: {len(rows):>6,} occurrences", flush=True)
        return len(rows)

    for region in load_regions(args.regions):
        print(f"{region.region_name}: {region.study_start} -> {region.study_end}", flush=True)
        months = [(a, b) for a, b in month_ranges(region.study_start, region.study_end)
                  if needs_download(out_dir / f"{region.region_id}_{a:%Y%m}.csv", a, args.force, args.refresh_months)]
        with ThreadPoolExecutor(args.workers) as pool:
            total = sum(pool.map(lambda m: download(region, *m), months))
        print(f"  => {total:,} new occurrences written to {out_dir}")
    if failed:
        raise SystemExit(f"{len(failed)} month(s) failed: {', '.join(failed)}")

if __name__ == "__main__":
    main()
