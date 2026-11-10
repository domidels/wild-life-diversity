"""Connection to the gold tables built from the scenario (see scenario.py).

Reads DATABRICKS_HOST / DATABRICKS_HTTP_PATH / DATABRICKS_TOKEN from the environment or .env,
and the schema from CI_GOLD_SCHEMA (default workspace.wildfire_ci_gold, the dbt `ci` target).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def query():
    load_dotenv(ROOT / ".env")
    if not os.environ.get("DATABRICKS_TOKEN"):
        pytest.skip("DATABRICKS_TOKEN not set: no warehouse to test against")
    from databricks import sql

    schema = os.environ.get("CI_GOLD_SCHEMA", "workspace.wildfire_ci_gold")
    with sql.connect(
        server_hostname=os.environ["DATABRICKS_HOST"].removeprefix("https://"),
        http_path=os.environ["DATABRICKS_HTTP_PATH"],
        access_token=os.environ["DATABRICKS_TOKEN"],
    ) as conn, conn.cursor() as cur:
        def run(statement: str) -> list[dict]:
            cur.execute(statement.format(gold=schema))
            columns = [c[0] for c in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]

        yield run
