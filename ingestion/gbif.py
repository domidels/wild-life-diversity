"""Download GBIF occurrences for each active region, one CSV per region and month.

Uses the GBIF Download API (asynchronous, free account needed):
https://techdocs.gbif.org/en/data-use/api-downloads

One request per region covers every month still to fetch: GBIF prepares a zipped
file on its side (usually a few minutes), we download it once and split it by month.
No paging and no rate limiting, unlike the search API — and every download gets a
citable DOI, logged in <out>/gbif_citations/.

Credentials: GBIF_USER, GBIF_PASSWORD, GBIF_EMAIL in .env locally, or the Databricks
secrets wildfire/gbif_user, wildfire/gbif_password, wildfire/gbif_email in a job.

Usage:
    python ingestion/gbif.py                       # active regions
    python ingestion/gbif.py --regions north_evia  # one region
    python ingestion/gbif.py --out /Volumes/workspace/wildfire_raw/landing  # as a Databricks job task
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import tempfile
import time
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests

# Databricks job tasks exec() the script without __file__: fall back to argv[0], and make the
# sibling module `common` importable either way.
HERE = Path(globals().get("__file__") or sys.argv[0]).resolve().parent
sys.path.insert(0, str(HERE))

from common import (  # noqa: E402
    DEFAULT_OUT, ROOT, get_secret, get_with_retry, load_regions, month_ranges, needs_download, write_csv,
)

API = "https://api.gbif.org/v1/occurrence/download"
POLL_SECONDS = 30
MAX_WAIT_SECONDS = 3 * 3600
# Same list as the dbt var `kept_basis_of_record`: no need to download museum specimens.
BASIS_OF_RECORD = ["HUMAN_OBSERVATION", "MACHINE_OBSERVATION", "OBSERVATION"]

# GBIF SIMPLE_CSV column -> column name in our CSV (snake_case, no SQL reserved words).
FIELDS = {
    "gbifID": "gbif_id",
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
csv.field_size_limit(sys.maxsize)  # some GBIF text fields are long


def predicate(region, start, end) -> dict:
    w, s, e, n = region.min_lon, region.min_lat, region.max_lon, region.max_lat
    return {"type": "and", "predicates": [
        {"type": "within", "geometry": f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))"},
        {"type": "greaterThanOrEquals", "key": "EVENT_DATE", "value": start.isoformat()},
        {"type": "lessThanOrEquals", "key": "EVENT_DATE", "value": end.isoformat()},
        {"type": "equals", "key": "HAS_COORDINATE", "value": "true"},
        {"type": "equals", "key": "HAS_GEOSPATIAL_ISSUE", "value": "false"},
        {"type": "equals", "key": "OCCURRENCE_STATUS", "value": "PRESENT"},
        {"type": "in", "key": "BASIS_OF_RECORD", "values": BASIS_OF_RECORD},
    ]}


def request_download(session, credentials, region, start, end) -> str:
    user, password, email = credentials
    body = {
        "creator": user,
        "notificationAddresses": [email],
        "sendNotification": False,
        "format": "SIMPLE_CSV",
        "predicate": predicate(region, start, end),
    }
    resp = session.post(f"{API}/request", json=body, auth=(user, password), timeout=60)
    if resp.status_code == 401:
        raise SystemExit("GBIF refused the credentials (GBIF_USER / GBIF_PASSWORD).")
    resp.raise_for_status()
    return resp.text.strip()


def wait_for(session, key: str) -> dict:
    waited = 0
    while waited < MAX_WAIT_SECONDS:
        info = get_with_retry(session, f"{API}/{key}").json()
        if info["status"] == "SUCCEEDED":
            return info
        if info["status"] in ("FAILED", "KILLED", "CANCELLED"):
            raise RuntimeError(f"GBIF download {key} ended with status {info['status']}")
        time.sleep(POLL_SECONDS)
        waited += POLL_SECONDS
    raise TimeoutError(f"GBIF download {key} not ready after {MAX_WAIT_SECONDS // 3600} h")


def read_by_month(session, info: dict, region_id: str) -> dict[str, list[dict]]:
    """Stream the zip to a temp file and split its rows by month of eventDate (YYYYMM)."""
    by_month: dict[str, list[dict]] = defaultdict(list)
    with tempfile.TemporaryFile() as tmp:
        with session.get(info["downloadLink"], stream=True, timeout=300) as resp:
            resp.raise_for_status()
            for chunk in resp.iter_content(1 << 20):
                tmp.write(chunk)
        tmp.seek(0)
        with zipfile.ZipFile(tmp) as zf:
            name = next(n for n in zf.namelist() if n.endswith(".csv"))
            with zf.open(name) as raw:
                text = io.TextIOWrapper(raw, encoding="utf-8", newline="")
                for rec in csv.DictReader(text, delimiter="\t", quoting=csv.QUOTE_NONE):
                    if not rec.get("speciesKey") or not rec.get("eventDate"):
                        continue  # identified above species level, or undated: unusable
                    month = rec["eventDate"][:7].replace("-", "")
                    by_month[month].append({"region_id": region_id,
                                            **{col: rec.get(field) for field, col in FIELDS.items()}})
    return by_month


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--regions", nargs="*", help="region_ids from dbt/seeds/regions.csv (default: active ones)")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="landing root folder (local or /Volumes/...)")
    parser.add_argument("--force", action="store_true", help="re-download every month")
    parser.add_argument("--refresh-months", type=int, default=0,
                        help="also re-download the last N months, which keep filling up (default: 0)")
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    credentials = tuple(get_secret(k) for k in ("GBIF_USER", "GBIF_PASSWORD", "GBIF_EMAIL"))
    if not all(credentials):
        raise SystemExit("GBIF_USER / GBIF_PASSWORD / GBIF_EMAIL are not set "
                         "(.env locally, secrets wildfire/gbif_* in Databricks).")

    out_dir = Path(args.out) / "gbif"
    citations_dir = Path(args.out) / "gbif_citations"  # outside gbif/: dbt reads every file there as CSV
    out_dir.mkdir(parents=True, exist_ok=True)
    citations_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()

    for region in load_regions(args.regions):
        months = [(a, b) for a, b in month_ranges(region.study_start, region.study_end)
                  if needs_download(out_dir / f"{region.region_id}_{a:%Y%m}.csv", a, args.force, args.refresh_months)]
        if not months:
            print(f"{region.region_name}: up to date", flush=True)
            continue
        start, end = months[0][0], months[-1][1]
        print(f"{region.region_name}: {len(months)} month(s) to fetch, {start} -> {end}", flush=True)

        key = request_download(session, credentials, region, start, end)
        print(f"  GBIF download {key} requested, waiting for GBIF to prepare it...", flush=True)
        info = wait_for(session, key)
        print(f"  ready: {info.get('totalRecords', 0):,} records, DOI {info.get('doi')}", flush=True)

        by_month = read_by_month(session, info, region.region_id)
        total = 0
        for first_day, _ in months:
            rows = by_month.get(f"{first_day:%Y%m}", [])
            write_csv(out_dir / f"{region.region_id}_{first_day:%Y%m}.csv", COLUMNS, rows)
            total += len(rows)
        print(f"  => {total:,} occurrences written in {len(months)} monthly files", flush=True)

        (citations_dir / f"{region.region_id}_{key}.json").write_text(json.dumps({
            "region_id": region.region_id, "download_key": key, "doi": info.get("doi"),
            "total_records": info.get("totalRecords"), "start": start.isoformat(), "end": end.isoformat(),
            "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }, indent=2))


if __name__ == "__main__":
    main()
