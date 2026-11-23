"""Verify actual gold data against the seed and optionally capture its baseline."""

import argparse
from decimal import Decimal
import json
import sys

from common import ContextError, ROOT, load_config, verify_context
from check_managed_storage import check_warehouse, result_rows
from databricks_sql import DatabricksSql

sys.path.insert(0, str(ROOT / "databricks" / "src"))
from data_model import MARKER, TABLES, business_checksums, generate_model
sys.path.insert(0, str(ROOT))
from infra.deploy import record


def verify_gold(config: dict, stages: list[str], *, log=record) -> dict:
    client = DatabricksSql(config, config["azure"]["databricks_sql_warehouse_id"])
    owner = f"{config['github']['owner']}/{config['github']['repository']}"
    check_warehouse(client.read("warehouses", "get", client.warehouse_id), owner)
    baseline = {}
    try:
        for stage in stages:
            expected = generate_model(stage)
            catalog = config["environments"][stage]["databricks_catalog"]
            if catalog != f"demo_{stage}":
                raise ContextError("Unexpected stage catalog; verification remains stage isolated.")
            baseline[stage] = {}
            for name, definition in TABLES.items():
                table = f"{catalog}.gold.{name}"
                metadata = client.read("tables", "get", table)
                if (
                    metadata["table_type"] != "MANAGED"
                    or metadata["data_source_format"] != "DELTA"
                    or not (metadata.get("comment") or "").startswith(MARKER)
                    or metadata.get("row_filter")
                    or any(column.get("mask") for column in metadata["columns"])
                ):
                    raise RuntimeError(f"{table}: managed Delta ownership/policy-free check failed.")
                root = config["environments"][stage]["databricks_managed_location"].rstrip("/")
                if not metadata["storage_location"].startswith(root + "/__unitystorage/"):
                    raise RuntimeError(f"{table}: wrong stage-managed storage location.")
                actual_comments = {column["name"]: column.get("comment") for column in metadata["columns"]}
                if any(actual_comments.get(column) != description
                       for column, _, description in definition["columns"]):
                    raise RuntimeError(f"{table}: column descriptions differ from the data dictionary.")
                keys = ", ".join(definition["keys"])
                metrics = "COUNT(*) AS rows, COUNT(DISTINCT struct(" + keys + ")) AS grains, "
                metrics += "COUNT(DISTINCT env_marker) AS marker_count, MIN(env_marker) AS marker"
                fields = ", ".join(f"CAST(`{column}` AS STRING)" for column, _, _ in definition["columns"]
                                   if column != "env_marker")
                digest = f"SHA2(CONCAT_WS('|', {fields}), 256)"
                for start in (1, 50):
                    metrics += f", SUM(CAST(CONV(SUBSTR({digest}, {start}, 15), 16, 10) AS DECIMAL(38,0)))"
                measure = "actual_hl" if name == "fact_sales_monthly" else \
                    "delivered_hl" if name == "fact_deliveries" else None
                if measure:
                    metrics += f", SUM({measure}) AS checksum"
                _, rows = result_rows(client.execute(f"SELECT {metrics} FROM {table}"))
                if len(rows) != 1:
                    raise RuntimeError(f"{table}: metrics must return exactly one row.")
                values = rows[0]
                count = len(expected[name])
                if len(values) != (7 if measure else 6) or (
                    int(values[0]) != count or int(values[1]) != count or
                    int(values[2]) != 1 or values[3] != stage
                ):
                    raise RuntimeError(f"{table}: count/grain/stage differs from expected generated data.")
                checksums = business_checksums(expected[name])
                if tuple(values[4:6]) != checksums:
                    raise RuntimeError(f"{table}: business-row fingerprints differ from the deterministic seed.")
                result = {"rows": count, "business_checksums": checksums}
                if measure:
                    columns = [column[0] for column in definition["columns"]]
                    index = columns.index(measure)
                    checksum = sum((row[index] for row in expected[name]), Decimal("0"))
                    if Decimal(values[6]) != checksum:
                        raise RuntimeError(f"{table}: actual checksum differs from deterministic seed.")
                    result["checksum"] = str(checksum)
                baseline[stage][name] = result
                log(f"Step 3 Check `{table}`: `{json.dumps(result)}`; unique grain, stage, comments and no UC filters/masks PASS.")
                print(f"PASS {table}: {result}", flush=True)
        return baseline
    finally:
        client.stop()
        log("Owned verification warehouse confirmed STOPPED after gold checks.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stages", default="dev,test,prod")
    parser.add_argument("--capture-baseline", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    stages = args.stages.split(",")
    if any(stage not in ("dev", "test", "prod") for stage in stages):
        parser.error("Expected dev,test,prod stages.")
    verify_context()
    config = load_config()
    if args.dry_run:
        client = DatabricksSql(config, config["azure"]["databricks_sql_warehouse_id"])
        check_warehouse(client.read("warehouses", "get", client.warehouse_id),
                        f"{config['github']['owner']}/{config['github']['repository']}")
        print("DRY-RUN: compare actual gold counts/grains/checksums to the deterministic seed; "
              "check comments, masks, filters and managed locations.")
        return
    baseline = verify_gold(config, stages)
    if args.capture_baseline:
        path = ROOT / "seed" / "expected_counts.json"
        content = json.dumps(baseline, indent=2) + "\n"
        if path.exists() and path.read_text(encoding="utf-8") != content:
            raise ContextError("Existing expected-count baseline differs; review before overwriting.")
        if not path.exists():
            path.write_text(content, encoding="utf-8")
        record("Captured verified actual counts/checksums in seed/expected_counts.json.")
    print("Gold verification: PASS for all requested stages.")


if __name__ == "__main__":
    try:
        main()
    except ContextError as error:
        record(f"Gold verification blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
