"""English common names of the species found in the GBIF files, so the dashboard can show
"Eurasian Kestrel" rather than "Falco tinnunculus".

Reads every species_key of <out>/gbif/*.csv and asks the GBIF species API for its English
vernacular names (https://api.gbif.org/v1/species/{key}/vernacularNames), as given by the
checklists GBIF aggregates (Catalogue of Life, national lists, eBird...). The name kept is the
one most checklists agree on, among those they flag as preferred if any. Not GBIF's single
`vernacularName` field: it can be an eBird group ("Gray/Purple Heron" for the Grey Heron)
or a vague name ("Daisy").
Writes one file, <out>/gbif_names/species_names.csv. Incremental: only species not in the
file yet are fetched, plus species without an English name checked more than RETRY_DAYS ago
(GBIF keeps adding names). No account needed.

About 1 species in 5 has no English name (mosses, lichens, small invertebrates): the
dashboard then keeps the scientific name.

    python ingestion/gbif_names.py
    python ingestion/gbif_names.py --out /Volumes/workspace/wildfire_raw/landing   # as a Databricks job task
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import requests

# Databricks job tasks exec() the script without __file__: fall back to argv[0], and make the
# sibling module `common` importable either way.
HERE = Path(globals().get("__file__") or sys.argv[0]).resolve().parent
sys.path.insert(0, str(HERE))

from common import DEFAULT_OUT, get_with_retry, write_csv  # noqa: E402

API = "https://api.gbif.org/v1/species"
COLUMNS = ["species_key", "scientific_name", "common_name", "checked_on"]
RETRY_DAYS = 90
WORKERS = 4  # parallel requests: polite to the public API, ~10,000 species in a few minutes

csv.field_size_limit(sys.maxsize)


def clean(name: str | None) -> str:
    """'western honey bee' -> 'Western honey bee'; 'Canada Goose (canadensis Group)' -> 'Canada Goose'."""
    name = re.sub(r"\s*\(.*\)\s*$", "", (name or "").strip())
    return name[:1].upper() + name[1:]


def species_in_landing(gbif_dir: Path) -> dict[str, str]:
    """species_key -> scientific name, over every GBIF file."""
    species: dict[str, str] = {}
    for path in sorted(gbif_dir.glob("*.csv")):
        with path.open(newline="") as f:
            for row in csv.DictReader(f):
                if row.get("species_key"):
                    species.setdefault(row["species_key"], row.get("species", ""))
    return species


def read_names(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    with path.open(newline="") as f:
        return {row["species_key"]: row for row in csv.DictReader(f)}


def pick_english(names: list[dict]) -> str:
    """The English name most checklists agree on, among those flagged preferred if any.
    Group names ("Little Egret/Western Reef-Heron") are left out; a tie goes to the longer,
    more specific name ("Jersey cudweed" over "Daisy")."""
    english = [n for n in names if n.get("language") == "eng" and "/" not in n.get("vernacularName", "")]
    pool = [n for n in english if n.get("preferred")] or english
    votes = Counter(clean(n["vernacularName"]).lower() for n in pool)
    votes.pop("", None)
    if not votes:
        return ""
    best = max(votes, key=lambda name: (votes[name], len(name)))
    # most common spelling of the winner ("Grey Heron" rather than "Grey heron")
    return Counter(c for n in pool if (c := clean(n["vernacularName"])).lower() == best).most_common(1)[0][0]


def fetch(session: requests.Session, key: str, scientific_name: str) -> dict:
    names = get_with_retry(session, f"{API}/{key}/vernacularNames", params={"limit": 1000}).json()["results"]
    return {"species_key": key, "scientific_name": scientific_name,
            "common_name": pick_english(names), "checked_on": date.today().isoformat()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="landing root folder (local or /Volumes/...)")
    parser.add_argument("--force", action="store_true", help="look every species up again")
    args = parser.parse_args()

    out = Path(args.out)
    target = out / "gbif_names" / "species_names.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    species = species_in_landing(out / "gbif")
    names = {} if args.force else read_names(target)
    stale = (date.today() - timedelta(days=RETRY_DAYS)).isoformat()
    todo = [k for k in species
            if k not in names or (not names[k]["common_name"] and names[k]["checked_on"] < stale)]
    print(f"{len(species):,} species in the GBIF files, {len(todo):,} to look up", flush=True)

    session = requests.Session()
    with ThreadPoolExecutor(WORKERS) as pool:
        for i, row in enumerate(pool.map(lambda k: fetch(session, k, species[k]), todo), 1):
            names[row["species_key"]] = row
            if i % 500 == 0:
                print(f"  {i:,}/{len(todo):,}", flush=True)

    write_csv(target, COLUMNS, sorted(names.values(), key=lambda r: int(r["species_key"])))
    named = sum(1 for r in names.values() if r["common_name"])
    print(f"=> {target}: {len(names):,} species, {named:,} with an English name", flush=True)


if __name__ == "__main__":
    main()
