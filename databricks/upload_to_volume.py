"""Create the landing volume and upload data/raw/{gbif,gbif_names,firms} to it.

Only needed when ingestion ran on a laptop. The Databricks job (databricks.yml) writes
straight into the volume. The CI uploads the integration-test scenario the same way, into its
own volume (--source, --volume, --clean).

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


def run_setup(volume: str) -> None:
    """Create the schema and volume of `volume` (/Volumes/<catalog>/<schema>/<volume>), as databricks/setup.sql."""
    catalog, schema, name = volume.removeprefix("/Volumes/").strip("/").split("/")
    statements = [f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}",
                  f"CREATE VOLUME IF NOT EXISTS {catalog}.{schema}.{name}"]
    with sql.connect(
        server_hostname=os.environ["DATABRICKS_HOST"].removeprefix("https://"),
        http_path=os.environ["DATABRICKS_HTTP_PATH"],
        access_token=os.environ["DATABRICKS_TOKEN"],
    ) as conn, conn.cursor() as cur:
        for statement in statements:
            cur.execute(statement)
    print(f"Volume ready: {volume}")


def already_uploaded(client: WorkspaceClient, folder: str) -> set[str]:
    try:
        return {Path(entry.path).name for entry in client.files.list_directory_contents(folder)}
    except Exception:  # folder does not exist yet
        return set()


def upload(local_root: Path, volume: str, force: bool, clean: bool) -> None:
    client = WorkspaceClient(host="https://" + os.environ["DATABRICKS_HOST"].removeprefix("https://"), token=os.environ["DATABRICKS_TOKEN"])
    for source in ("gbif", "gbif_names", "firms"):
        local = sorted((local_root / source).glob("*.csv"))
        remote = already_uploaded(client, f"{volume}/{source}")
        if clean:  # the volume ends up holding exactly the local files
            for name in remote - {p.name for p in local}:
                client.files.delete(f"{volume}/{source}/{name}")
        skip = set() if force else remote
        files = [p for p in local if p.name not in skip]
        for i, path in enumerate(files, 1):
            with path.open("rb") as f:
                client.files.upload(f"{volume}/{source}/{path.name}", f, overwrite=True)
            print(f"\r{source}: {i}/{len(files)} new files", end="", flush=True)
        print(f"\r{source}: {len(files)} new files uploaded, {len(skip)} already there")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="re-upload files already in the volume")
    parser.add_argument("--source", type=Path, default=ROOT / "data" / "raw", help="local folder holding gbif/, gbif_names/ and firms/")
    parser.add_argument("--volume", default=VOLUME, help="target volume, /Volumes/<catalog>/<schema>/<volume>")
    parser.add_argument("--clean", action="store_true", help="delete volume files that are not in --source")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    run_setup(args.volume)
    upload(args.source, args.volume, args.force, args.clean)
