"""A small, fully known scenario for the pipeline integration test.

One fire in North Evia (episode north_evia_2021, 3-20 Aug 2021) with observations whose
outcome is known in advance: the burned zone loses half its observations and half its species
after the fire, the control does not change, so every BACI ratio is exactly 0.5.

Around it, records the pipeline must leave out of the comparison — museum specimens, imprecise
coordinates, duplicates, a dataset that stopped publishing, sightings during the fire, cells
burned by another fire, low-confidence detections. If one of them slips through, the expected
counts below no longer match.

    python tests/integration/scenario.py --out /tmp/landing    # writes gbif/ and firms/ CSVs
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
from itertools import cycle
from pathlib import Path

REGION_ID = "north_evia"
EPISODE_ID = "north_evia_2021"

FIRE_CENTER = (38.85, 23.25)        # (lat, lon) of the burn scar
FIRE_HALF_SIZE = 0.05               # degrees: the scar is a ~11 x 9 km square
FIRE_GRID_STEP = 0.004              # one detection point every ~400 m
FIRE_DAYS = [date(2021, 8, 5), date(2021, 8, 6)]
CONTROL_CENTER = (38.65, 23.60)     # ~40 km away: far beyond the buffer rings
OTHER_FIRE_CENTER = (39.00, 23.00)  # a later fire: its cells are "disturbed"
OBS_HALF_SIZE = 0.02                # observations fall within this distance of a center

ACTIVE_DATASET = "00000000-0000-0000-0000-00000000000a"
STALE_DATASET = "00000000-0000-0000-0000-00000000000b"  # no record after the fire

# (species_key, species, kingdom, class_name)
SPECIES = [
    (9000 + i, name, kingdom, class_name)
    for i, (name, kingdom, class_name) in enumerate([
        ("Parus major", "Animalia", "Aves"), ("Erithacus rubecula", "Animalia", "Aves"),
        ("Pica pica", "Animalia", "Aves"), ("Buteo buteo", "Animalia", "Aves"),
        ("Vulpes vulpes", "Animalia", "Mammalia"), ("Erinaceus roumanicus", "Animalia", "Mammalia"),
        ("Testudo hermanni", "Animalia", "Reptilia"), ("Bufo bufo", "Animalia", "Amphibia"),
        ("Apis mellifera", "Animalia", "Insecta"), ("Papilio machaon", "Animalia", "Insecta"),
        ("Pinus halepensis", "Plantae", "Pinopsida"), ("Quercus coccifera", "Plantae", "Magnoliopsida"),
        ("Arbutus unedo", "Plantae", "Magnoliopsida"), ("Cistus creticus", "Plantae", "Magnoliopsida"),
        ("Erica arborea", "Plantae", "Magnoliopsida"), ("Thymus capitatus", "Plantae", "Magnoliopsida"),
        ("Amanita muscaria", "Fungi", "Agaricomycetes"), ("Boletus edulis", "Fungi", "Agaricomycetes"),
        ("Helix lucorum", "Animalia", "Gastropoda"), ("Scolopendra cingulata", "Animalia", "Chilopoda"),
    ])
]
BEFORE_DAYS = (date(2019, 9, 1), date(2021, 7, 31))  # inside the 24-month "before" window
AFTER_DAYS = (date(2021, 9, 1), date(2023, 7, 31))   # inside the 24-month "after" window

# What the gold tables must contain for EPISODE_ID.
EXPECTED = {
    "boxes": {  # (zone, period) -> (n_observations, n_species)
        ("burned", "before"): (400, 20),
        ("burned", "after"): (200, 10),
        ("control", "before"): (400, 20),
        ("control", "after"): (400, 20),
    },
    "baci_ratio": {"n_observations": 0.5, "n_species": 0.5},
    "is_reliable": True,
    # every row of int_occurrences_labeled: the boxes + stale dataset + during fire + disturbed
    "n_observations": 400 + 200 + 400 + 400 + 100 + 20 + 50,
    "n_fire_detections": None,  # filled in below from the grid size
}

GBIF_COLUMNS = ["region_id", "gbif_id", "species_key", "species", "taxon_rank", "kingdom", "phylum",
                "class_name", "order_name", "family", "decimal_latitude", "decimal_longitude",
                "coordinate_uncertainty_m", "event_date", "basis_of_record", "dataset_key",
                "country_code", "observer_id"]
FIRMS_COLUMNS = ["region_id", "source", "latitude", "longitude", "acq_date", "acq_time",
                 "satellite", "instrument", "confidence", "frp", "daynight"]


def grid(center: tuple[float, float], half_size: float, step: float) -> list[tuple[float, float]]:
    n = round(2 * half_size / step)
    lat0, lon0 = center[0] - half_size, center[1] - half_size
    return [(round(lat0 + i * step, 5), round(lon0 + j * step, 5)) for i in range(n + 1) for j in range(n + 1)]


FIRE_POINTS = grid(FIRE_CENTER, FIRE_HALF_SIZE, FIRE_GRID_STEP)
EXPECTED["n_fire_detections"] = len(FIRE_POINTS) * len(FIRE_DAYS)


def spread_days(start: date, end: date, n: int) -> list[date]:
    span = (end - start).days
    return [start + timedelta(days=span * i // max(n - 1, 1)) for i in range(n)]


class Occurrences:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.next_id = 1_000_000

    def add(self, n: int, center, days: tuple[date, date], species: list, dataset=ACTIVE_DATASET, **overrides):
        points = cycle(grid(center, OBS_HALF_SIZE, 2 * OBS_HALF_SIZE / 9))
        taxa = cycle(species)
        for i, day in enumerate(spread_days(*days, n)):
            key, name, kingdom, class_name = next(taxa)
            lat, lon = next(points)
            self.rows.append({
                "region_id": REGION_ID, "gbif_id": self.next_id, "species_key": key, "species": name,
                "taxon_rank": "SPECIES", "kingdom": kingdom, "phylum": "", "class_name": class_name,
                "order_name": "", "family": "", "decimal_latitude": lat, "decimal_longitude": lon,
                "coordinate_uncertainty_m": 25,
                # GBIF eventDate is a timestamp or an interval: both forms must parse
                "event_date": f"{day}T08:30:00" if i % 3 else f"{day}/{day + timedelta(days=2)}",
                "basis_of_record": "HUMAN_OBSERVATION", "dataset_key": dataset, "country_code": "GR",
                "observer_id": f"observer{i % 7:02d}", **overrides,
            })
            self.next_id += 1


def occurrences() -> list[dict]:
    occ = Occurrences()
    # the four BACI boxes
    occ.add(400, FIRE_CENTER, BEFORE_DAYS, SPECIES)
    occ.add(200, FIRE_CENTER, AFTER_DAYS, SPECIES[:10])
    occ.add(400, CONTROL_CENTER, BEFORE_DAYS, SPECIES)
    occ.add(400, CONTROL_CENTER, AFTER_DAYS, SPECIES)
    # kept in the episode but out of every comparison
    occ.add(100, CONTROL_CENTER, BEFORE_DAYS, SPECIES, dataset=STALE_DATASET)
    occ.add(20, CONTROL_CENTER, (FIRE_DAYS[0], FIRE_DAYS[-1]), SPECIES)
    occ.add(50, OTHER_FIRE_CENTER, AFTER_DAYS, SPECIES)
    # dropped by staging
    occ.add(30, CONTROL_CENTER, BEFORE_DAYS, SPECIES, basis_of_record="PRESERVED_SPECIMEN")
    occ.add(30, CONTROL_CENTER, BEFORE_DAYS, SPECIES, coordinate_uncertainty_m=5000)
    duplicates = [dict(row) for row in occ.rows[:30]]
    return occ.rows + duplicates


def detections() -> list[dict]:
    def row(lat, lon, day, confidence):
        return {"region_id": REGION_ID, "source": "VIIRS_SNPP_SP", "latitude": lat, "longitude": lon,
                "acq_date": day.isoformat(), "acq_time": "1105", "satellite": "N", "instrument": "VIIRS",
                "confidence": confidence, "frp": "12.5", "daynight": "D"}

    rows = [row(lat, lon, day, "h") for lat, lon in FIRE_POINTS for day in FIRE_DAYS]
    # another fire a year later: its cells become "disturbed"
    rows += [row(lat, lon, day, "n") for lat, lon in grid(OTHER_FIRE_CENTER, OBS_HALF_SIZE + 0.015, 0.005)
             for day in (date(2022, 7, 10), date(2022, 7, 11))]
    # low-confidence detections over the control: must not turn it into a fire zone
    rows += [row(lat, lon, date(2020, 8, 1), "l") for lat, lon in grid(CONTROL_CENTER, 0.01, 0.005)] * 2
    return rows


def write(path: Path, columns: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, type=Path, help="landing root folder to write gbif/ and firms/ into")
    out = parser.parse_args().out
    write(out / "gbif" / f"{REGION_ID}_scenario.csv", GBIF_COLUMNS, occurrences())
    write(out / "firms" / f"{REGION_ID}_scenario.csv", FIRMS_COLUMNS, detections())
    print(f"Scenario written to {out}")


if __name__ == "__main__":
    main()
