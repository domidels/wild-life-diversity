"""End-to-end check of the dbt pipeline: scenario CSVs in, known gold numbers out.

Run after `dbt build --target ci` on the scenario (see .github/workflows/ci.yml).
"""

from __future__ import annotations

import pytest

from scenario import EPISODE_ID, EXPECTED


def test_boxes_keep_only_comparable_observations(query):
    rows = query(f"select * from {{gold}}.fct_baci_summary where episode_id = '{EPISODE_ID}'")
    boxes = {(r["zone"], r["period"]): (r["n_observations"], r["n_species"]) for r in rows}
    assert boxes == EXPECTED["boxes"]


def test_baci_effect(query):
    rows = query(f"select * from {{gold}}.fct_baci_effect where episode_id = '{EPISODE_ID}'")
    ratios = {r["metric"]: float(r["baci_ratio"]) for r in rows}
    for metric, expected in EXPECTED["baci_ratio"].items():
        assert ratios[metric] == pytest.approx(expected), metric
    assert all(r["is_reliable"] is EXPECTED["is_reliable"] for r in rows)


def test_rarefied_richness_falls_with_species(query):
    rows = query(f"select * from {{gold}}.fct_baci_effect where episode_id = '{EPISODE_ID}' "
                 "and metric = 'rarefied_richness'")
    assert len(rows) == 1 and float(rows[0]["baci_ratio"]) < 1


def test_episode_headline_numbers(query):
    [episode] = query(f"select * from {{gold}}.dim_episodes where episode_id = '{EPISODE_ID}'")
    assert episode["n_observations"] == EXPECTED["n_observations"]
    assert episode["n_fire_detections"] == EXPECTED["n_fire_detections"]
    assert episode["n_burned_cells"] > 0


def test_episodes_without_data_stay_empty(query):
    rows = query(f"select episode_id from {{gold}}.dim_episodes where episode_id <> '{EPISODE_ID}' "
                 "and n_observations > 0")
    assert rows == []


def test_map_has_every_zone(query):
    rows = query(f"select distinct zone from {{gold}}.fct_map_cells where episode_id = '{EPISODE_ID}'")
    assert {r["zone"] for r in rows} == {"burned", "buffer", "disturbed", "control"}


def test_species_lost_in_burned_zone(query):
    rows = query(f"select n_burned_after, response from {{gold}}.fct_species_response "
                 f"where episode_id = '{EPISODE_ID}'")
    lost = [r for r in rows if r["n_burned_after"] == 0]
    n_species_before = EXPECTED["boxes"][("burned", "before")][1]
    n_species_after = EXPECTED["boxes"][("burned", "after")][1]
    assert len(lost) == n_species_before - n_species_after
    assert {r["response"] for r in lost} == {"less_frequent"}


def test_species_carry_their_english_name(query):
    rows = query(f"select species_key, common_name from {{gold}}.fct_species_response "
                 f"where episode_id = '{EPISODE_ID}'")
    names = {r["species_key"]: r["common_name"] for r in rows}
    for key, expected in EXPECTED["common_names"].items():
        assert names[key] == expected, key
