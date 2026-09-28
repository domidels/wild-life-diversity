"""Export the dbt gold tables from Databricks to web/data/*.json for the static dashboard.

The dashboard is a static site (GitHub Pages): it cannot query Databricks live — nor should
a public portfolio expose a warehouse token. So we snapshot the small gold tables to JSON.

Usage:
    python export/export_marts.py            # reads DATABRICKS_* from .env
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from databricks import sql
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "data"
SCHEMA = "workspace.wildfire_gold"

# table -> optional filter keeping the payload small
TABLES = {
    "dim_episodes": "n_observations > 0",  # regions not ingested yet stay off the site
    "fct_fire_activity_monthly": None,
    "fct_observations_monthly": None,
    "fct_baci_summary": None,
    "fct_baci_effect": None,
    "fct_species_response": "response <> 'insufficient_data'",
    "fct_species_latitude_shift": None,
    "fct_taxon_group_mix": None,
    "fct_map_cells": "zone <> 'disturbed' or n_obs_before + n_obs_after > 0",
}


def to_json(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(type(value))


def main() -> None:
    load_dotenv(ROOT / ".env")
    OUT.mkdir(parents=True, exist_ok=True)
    with sql.connect(
        server_hostname=os.environ["DATABRICKS_HOST"].removeprefix("https://"),
        http_path=os.environ["DATABRICKS_HTTP_PATH"],
        access_token=os.environ["DATABRICKS_TOKEN"],
    ) as conn, conn.cursor() as cur:
        for table, where in TABLES.items():
            cur.execute(f"select * from {SCHEMA}.{table}" + (f" where {where}" if where else ""))
            columns = [c[0] for c in cur.description]
            rows = [dict(zip(columns, row)) for row in cur.fetchall()]
            (OUT / f"{table}.json").write_text(json.dumps(rows, default=to_json, separators=(",", ":")))
            print(f"{table:<30} {len(rows):>7,} rows")

    meta = {"mode": "databricks", "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    (OUT / "meta.json").write_text(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
