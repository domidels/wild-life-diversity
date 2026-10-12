# After the Fire — wildfires × biodiversity observations

After a big wildfire, does what people observe in nature change in the burned area — more than
everywhere else? This project answers with two open datasets: **NASA satellite fire detections**
(where it burned) and **GBIF biodiversity observations** (which species people saw). It is built
with **Databricks** and **dbt** and published as an interactive dashboard.

**[Live dashboard →](https://domidels.github.io/wild-life-diversity/)**

## Fires studied

| Region | Fire | Dates |
|---|---|---|
| Kangaroo Island, AU | Black Summer (Ravine fire) | Dec 2019 – Feb 2020 |
| North Evia, GR | Evia wildfires | Aug 2021 |
| Pantanal, BR | Pantanal fires | Jul – Oct 2020 |
| Northern Sierra Nevada, US | Dixie Fire | Jul – Oct 2021 |
| Landes de Gascogne, FR | La Teste-de-Buch & Landiras fires | Jul – Sep 2022 |
| Landes de Gascogne, FR | Saumos & Biscarrosse fires (~45,000 ha) | Jul – Aug 2026 |

Each fire is compared over up to 2 years after it and, usually, the 2 years before. For a recent fire, the "before"
period keeps only the same season, so a summer is never compared with a whole year.
To add a study, add a row to [`regions.csv`](dbt/seeds/regions.csv) and
[`fire_episodes.csv`](dbt/seeds/fire_episodes.csv).

## How it works

Everything runs in the cloud, once a month:

```
 NASA FIRMS ─┐
             ├─► Databricks job: download ─► dbt: clean, compare ─► GitHub: publish dashboard
 GBIF ───────┘
```

1. **Download** — a monthly Databricks job fetches new GBIF observations and NASA fire detections.
2. **Transform** — dbt cleans the data, places it on a hexagon grid, and computes the
   before/after comparisons, in three layers (raw → clean → results), tested at each step.
3. **Publish** — GitHub Actions exports the results to JSON and publishes the dashboard
   (D3 + Leaflet) on GitHub Pages.

## Method

1. **Map the region in hexagons** of about 5 km² ([H3](https://h3geo.org/) grid).
2. **Sort the hexagons**: *burned* where satellites saw the fire, *control* for unburned land
   nearby, and a strip around the burn scar left out because it is uncertain.
3. **Compare before and after the fire, in both zones.** The fire effect is how much the burned
   area changed *compared with* the control:
   `(burned after ÷ before) ÷ (control after ÷ before)`.
   Changes that happen everywhere (more app users, a rainy year) cancel out.
4. **Compare fairly.** The more people look, the more species they find, so species are counted
   on samples of the same size. Only data sources that already published records after the fire
   are used, so late uploads cannot fake a decline.

When the burned area has too few observations (under 100), the dashboard says "too early"
instead of showing a result — the case of the 2026 French fires.

**Keep in mind:** these are records of what people noticed, not counts of animals and plants.
People also avoid burned land for a while, then come back out of curiosity.

Technical details (thresholds, formulas) are documented in the dbt models.

## Run it

Setup guide (French): [docs/GUIDE_DEMARRAGE.md](docs/GUIDE_DEMARRAGE.md) ·
Why the dashboard looks the way it does: [docs/GUIDE_PRESENTATION.md](docs/GUIDE_PRESENTATION.md).

**In the cloud** — add the GitHub secrets `DATABRICKS_HOST`, `DATABRICKS_HTTP_PATH`,
`DATABRICKS_TOKEN`, and the Databricks secrets `wildfire/firms_map_key`, `wildfire/gbif_user`,
`wildfire/gbif_password`, `wildfire/gbif_email`. Then push: the data refreshes on the 1st of
each month and the dashboard on the 2nd.

**On a laptop:**

```bash
pip install -r requirements.txt
python ingestion/gbif.py && python ingestion/firms.py      # 1. download
python databricks/upload_to_volume.py                       # 2. upload to Databricks
cd dbt && dbt deps && dbt seed && dbt build                 # 3. transform and test
python export/export_marts.py                               # 4. export results
python -m http.server -d web 8000                           # 5. view the dashboard
```

To only view the dashboard, step 5 is enough: the latest results are already in `web/data/`.

## Stack

Databricks Free Edition · dbt · Python · D3.js · Leaflet · GitHub Actions and Pages

## Data sources

- **GBIF.org** — biodiversity observations. Each download has a DOI to cite, saved in
  `gbif_citations/` in the Databricks volume.
- **NASA FIRMS** — VIIRS 375 m satellite fire detections.
