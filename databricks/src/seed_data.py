# Databricks notebook source
import random
import numpy as np

from data_model import MARKER, TABLES, generate_model

dbutils.widgets.text("catalog", "demo_dev")
dbutils.widgets.text("env_marker", "dev")
catalog = dbutils.widgets.get("catalog")
stage = dbutils.widgets.get("env_marker")
if catalog != f"demo_{stage}" or stage not in ("dev", "test", "prod"):
    raise ValueError("Catalog and environment marker must match the fixed stage.")
random.seed(42)
np.random.seed(42)

# COMMAND ----------
for layer in ("bronze", "silver", "gold"):
    for name in TABLES:
        table = f"{catalog}.{layer}.{name}"
        if spark.catalog.tableExists(table):
            detail = spark.sql(f"DESCRIBE DETAIL {table}").first().asDict()
            if not (detail.get("description") or "").startswith(MARKER):
                raise RuntimeError(f"Refusing to overwrite an unowned table: {table}")

# COMMAND ----------
model = generate_model(stage)
for name, definition in TABLES.items():
    rows = model[name]
    if name in ("fact_sales_monthly", "fact_deliveries"):
        rows = [*rows, rows[0]]
    schema = ", ".join(f"`{column}` STRING" for column, _, _ in definition["columns"])
    strings = [tuple(None if value is None else str(value) for value in row) for row in rows]
    frame = spark.createDataFrame(strings, schema=schema)
    table = f"{catalog}.bronze.{name}"
    frame.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(table)
    description = f"{MARKER}: {definition['description']}".replace("'", "''")
    spark.sql(f"COMMENT ON TABLE {table} IS '{description}'")
    print(f"{table}: {len(rows)} bronze rows")
