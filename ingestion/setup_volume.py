"""First task of the Databricks job: create the landing schema and volume if missing.

Runs databricks/setup.sql with Spark, so the job works on a brand-new workspace.
"""

import sys
from pathlib import Path

from pyspark.sql import SparkSession

# Databricks job tasks exec() the script without __file__: fall back to argv[0].
HERE = Path(globals().get("__file__") or sys.argv[0]).resolve().parent
SETUP_SQL = HERE.parent / "databricks" / "setup.sql"


def statements(sql: str) -> list[str]:
    cleaned = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
    return [s.strip() for s in cleaned.split(";") if s.strip()]


if __name__ == "__main__":
    spark = SparkSession.builder.getOrCreate()
    for statement in statements(SETUP_SQL.read_text()):
        spark.sql(statement)
    print("Landing volume ready")
