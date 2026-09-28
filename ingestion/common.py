"""Shared helpers for the ingestion scripts.

The scripts run the same way on a laptop (writing to data/raw) and as Databricks job tasks
(writing straight into the Unity Catalog volume, e.g. --out /Volumes/workspace/wildfire_raw/landing).

Regions and fire episodes live in one place — the dbt seeds `dbt/seeds/regions.csv` and
`dbt/seeds/fire_episodes.csv` — so ingestion and transformation always agree on bounding
boxes and fire dates.
"""

from __future__ import annotations

import csv
import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
SEEDS = ROOT / "dbt" / "seeds"
DEFAULT_OUT = ROOT / "data" / "raw"
SECRET_SCOPE = "wildfire"

# Months after the fire — must match the dbt var `window_months` (dbt/dbt_project.yml).
# Months before the fire are set per episode (fire_episodes.before_months).
WINDOW_MONTHS = 24


@dataclass(frozen=True)
class Episode:
    episode_id: str
    fire_name: str
    fire_start: date
    fire_end: date
    before_months: int

    @property
    def study_start(self) -> date:
        return add_months(self.fire_start, -self.before_months)

    @property
    def study_end(self) -> date:
        # a recent fire has not had WINDOW_MONTHS of "after" yet: stop at yesterday
        return min(add_months(self.fire_end, WINDOW_MONTHS), date.today() - timedelta(days=1))


@dataclass(frozen=True)
class Region:
    region_id: str
    region_name: str
    country_code: str
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float
    episodes: tuple[Episode, ...]

    # Download window: covers the before/after windows of every episode of the region.
    @property
    def study_start(self) -> date:
        return min(e.study_start for e in self.episodes)

    @property
    def study_end(self) -> date:
        return max(e.study_end for e in self.episodes)


def load_regions(only: list[str] | None = None) -> list[Region]:
    """Active regions (regions.is_active), or the ones named in `only`."""
    with (SEEDS / "fire_episodes.csv").open(newline="") as f:
        episodes: dict[str, list[Episode]] = {}
        for row in csv.DictReader(f):
            episodes.setdefault(row["region_id"], []).append(Episode(
                episode_id=row["episode_id"],
                fire_name=row["fire_name"],
                fire_start=date.fromisoformat(row["fire_start"]),
                fire_end=date.fromisoformat(row["fire_end"]),
                before_months=int(row["before_months"]),
            ))
    with (SEEDS / "regions.csv").open(newline="") as f:
        regions = [
            Region(
                region_id=row["region_id"],
                region_name=row["region_name"],
                country_code=row["country_code"],
                min_lon=float(row["min_lon"]),
                min_lat=float(row["min_lat"]),
                max_lon=float(row["max_lon"]),
                max_lat=float(row["max_lat"]),
                episodes=tuple(episodes.get(row["region_id"], ())),
            )
            for row in csv.DictReader(f)
            if (row["region_id"] in only if only else row["is_active"] == "true")
        ]
    return [r for r in regions if r.episodes]


def add_months(d: date, months: int) -> date:
    month_index = d.year * 12 + (d.month - 1) + months
    year, month = divmod(month_index, 12)
    month += 1
    # clamp the day (e.g. 31 Jan + 1 month -> 28/29 Feb)
    for day in (d.day, 30, 29, 28):
        try:
            return date(year, month, day)
        except ValueError:
            continue
    raise ValueError(d)


def month_ranges(start: date, end: date):
    """Yield (first_day, last_day) for each calendar month overlapping [start, end]."""
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        next_month = add_months(cursor, 1)
        yield max(cursor, start), min(next_month - timedelta(days=1), end)
        cursor = next_month


def get_with_retry(session: requests.Session, url: str, params=None, tries: int = 8) -> requests.Response:
    """GET with retries. On HTTP 429 (rate limited) waits as long as the API asks (Retry-After)."""
    for attempt in range(tries):
        try:
            resp = session.get(url, params=params, timeout=60)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
            resp.raise_for_status()
            return resp
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as err:
            if attempt == tries - 1:
                raise
            retry_after = getattr(err.response, "headers", {}).get("Retry-After", "")
            time.sleep(int(retry_after) if retry_after.isdigit() else min(2 ** attempt * 5, 300))
    raise RuntimeError("unreachable")


def get_secret(name: str) -> str | None:
    """Environment variable first (laptop, CI), then the Databricks secret scope `wildfire`
    with the lower-cased name (job tasks): FIRMS_MAP_KEY -> wildfire/firms_map_key."""
    if os.environ.get(name):
        return os.environ[name]
    try:
        from databricks.sdk.runtime import dbutils  # only importable inside Databricks
        return dbutils.secrets.get(SECRET_SCOPE, name.lower())
    except Exception:
        return None


def needs_download(path: Path, first_day: date, force: bool, refresh_months: int) -> bool:
    """Download a month if it is missing, if --force, or if it is among the last
    `refresh_months` months — recent months keep filling up as publishers catch up."""
    if force or not path.exists():
        return True
    return first_day >= add_months(date.today().replace(day=1), -refresh_months)


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    """Write a complete file or nothing: the CSV is built in a local temp file, then moved.
    Moving (not renaming) also works when `path` is on a Unity Catalog volume."""
    fd, tmp = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    shutil.move(tmp, path)
