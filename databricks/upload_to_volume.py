"""Create the landing volume (databricks/setup.sql) and upload data/raw/{gbif,firms} to it.

Only needed when ingestion ran on a laptop. The Databricks job (databricks.yml) writes
straight into the volume.

Uses DATABRICKS_HOST / DATABRICKS_HTTP_PATH / DATABRICKS_TOKEN from .env — no CLI needed.

    python databricks/upload_to_volume.py            # only files not yet in the volume
    python databricks/upload_to_volume.py --force    # re-upload everything
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from databricks import sql
from databricks.sdk import WorkspaceClient
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
VOLUME = "/Volumes/workspace/wildfire_raw/landing"


def run_setup() -> None:
    statements = [s.strip() for s in (ROOT / "databricks" / "setup.sql").read_text().split(";")]
    statements = [s for s in statements if any(not line.startswith("--") and line.strip() for line in s.splitlines())]
    with sql.connect(
        server_hostname=os.environ["DATABRICKS_HOST"].removeprefix("https://"),
        http_path=os.environ["DATABRICKS_HTTP_PATH"],
        access_token=os.environ["DATABRICKS_TOKEN"],
    ) as conn, conn.cursor() as cur:
        for statement in statements:
            cur.execute(statement)
    print(f"Volume ready: {VOLUME}")


def already_uploaded(client: WorkspaceClient, folder: str) -> set[str]:
    try:
        return {Path(entry.path).name for entry in client.files.list_directory_contents(folder)}
    except Exception:  # folder does not exist yet
        return set()


def upload(force: bool) -> None:
    client = WorkspaceClient(host="https://" + os.environ["DATABRICKS_HOST"].removeprefix("https://"), token=os.environ["DATABRICKS_TOKEN"])
    for source in ("gbif", "firms"):
        skip = set() if force else already_uploaded(client, f"{VOLUME}/{source}")
        files = [p for p in sorted((ROOT / "data" / "raw" / source).glob("*.csv")) if p.name not in skip]
        for i, path in enumerate(files, 1):
            with path.open("rb") as f:
                client.files.upload(f"{VOLUME}/{source}/{path.name}", f, overwrite=True)
            print(f"\r{source}: {i}/{len(files)} new files", end="", flush=True)
        print(f"\r{source}: {len(files)} new files uploaded, {len(skip)} already there")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="re-upload files already in the volume")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    run_setup()
    upload(args.force)
