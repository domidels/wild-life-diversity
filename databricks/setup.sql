-- Run once in the Databricks SQL editor (Free Edition: the `workspace` catalog already exists).

-- Landing zone for the raw CSV files produced by ingestion/.
CREATE SCHEMA IF NOT EXISTS workspace.wildfire_raw
  COMMENT 'Raw files downloaded from GBIF and NASA FIRMS';

CREATE VOLUME IF NOT EXISTS workspace.wildfire_raw.landing
  COMMENT 'gbif/*.csv and firms/*.csv';

-- dbt creates wildfire_bronze, wildfire_silver, wildfire_gold and wildfire_ref by itself.
