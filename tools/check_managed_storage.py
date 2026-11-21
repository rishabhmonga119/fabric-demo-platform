"""Verify Step 1 grants and physical managed storage using tiny Delta tables."""

import argparse
import json
from pathlib import Path
import re
import sys
import tempfile

from check_databricks import workspace_environment
from common import ContextError, ROOT, cli, load_config, mutate, run, verify_context
from databricks_sql import DatabricksSql

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config


def check_warehouse(warehouse: dict, owner: str) -> None:
    tags = {tag["key"]: tag["value"]
            for tag in warehouse.get("tags", {}).get("custom_tags", [])}
    if tags.get("demoOwner") != owner or tags.get("createdBy") != "copilot-demo-build":
        raise ContextError("STOP: wh-demo-bootstrap is not owned by this automation.")
    if (
        warehouse["enable_serverless_compute"] is not True
        or warehouse["auto_stop_mins"] != 15
        or warehouse["cluster_size"] != "2X-Small"
        or warehouse["min_num_clusters"] != 1
        or warehouse["max_num_clusters"] != 1
    ):
        raise ContextError("Bootstrap warehouse violates the serverless/size/15-minute cost guardrails.")


def result_rows(response: dict) -> tuple[list[str], list[list]]:
    manifest = response["manifest"]
    if manifest["format"] != "JSON_ARRAY" or manifest.get("truncated") is True:
        raise RuntimeError("SQL verification result must be complete INLINE JSON_ARRAY data.")
    names = [column["name"] for column in manifest["schema"]["columns"]]
    rows = response["result"]["data_array"]
    if any(len(row) != len(names) for row in rows):
        raise RuntimeError("SQL verification column and row shapes differ.")
    return names, rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    verify_context()
    config = load_config()
    environment = workspace_environment(config)
    executable = cli("databricks")
    owner = f"{config['github']['owner']}/{config['github']['repository']}"
    comment = f"Demo managed-storage probe owned by {owner}"

    def read(*arguments: str):
        return json.loads(run([executable, *arguments, "--output", "json"], env=environment))

    def post(endpoint: str, payload: dict):
        command = [executable, "api", "post", endpoint, "--output", "json"]
        if args.dry_run:
            mutate([*command, "--json", json.dumps(payload)], dry_run=True, env=environment)
            return None
        with tempfile.TemporaryDirectory(prefix="demo-sql-body-") as directory:
            body = Path(directory) / "body.json"
            body.write_text(json.dumps(payload), encoding="utf-8")
            return json.loads(mutate([*command, "--json", f"@{body}"], env=environment))

    warehouses = read("warehouses", "list")
    existing = [warehouse for warehouse in warehouses if warehouse["name"] == "wh-demo-bootstrap"]
    if len(existing) > 1:
        raise ContextError("Multiple warehouses named wh-demo-bootstrap.")
    if existing:
        check_warehouse(existing[0], owner)
        warehouse_id = existing[0]["id"]
    else:
        # https://docs.databricks.com/api/warehouses/v1/create-warehouse
        created = post("/api/2.0/sql/warehouses", {
            "name": "wh-demo-bootstrap", "cluster_size": "2X-Small",
            "min_num_clusters": 1, "max_num_clusters": 1, "auto_stop_mins": 15,
            "enable_serverless_compute": True, "warehouse_type": "PRO",
            "tags": {"custom_tags": [
                {"key": "demoOwner", "value": owner},
                {"key": "createdBy", "value": "copilot-demo-build"},
            ]},
        })
        if args.dry_run:
            print("DRY-RUN: create one-row managed probes per stage, verify gold grants and storage locations, then stop the owned warehouse.")
            return
        warehouse_id = created["id"]
        config["azure"]["databricks_sql_warehouse_id"] = warehouse_id
        save_config(config)
        record(f"Created owned serverless warehouse `wh-demo-bootstrap`: `{warehouse_id}`; auto-stop 15 minutes.")

    if args.dry_run:
        print(f"DRY-RUN: use owned warehouse {warehouse_id} for stage probes and stop it afterwards.")
        return

    client = DatabricksSql(config, warehouse_id)

    def sql(statement: str) -> dict:
        response = client.execute(statement)
        record(f"SQL statement submitted: `{statement}`.")
        return response

    try:
        check_warehouse(read("warehouses", "get", warehouse_id), owner)
        for stage, stage_config in config["environments"].items():
            catalog = stage_config["databricks_catalog"]
            if not re.fullmatch(r"demo_(dev|test|prod)", catalog):
                raise ContextError(f"Unexpected catalog identifier: {catalog}")
            # https://learn.microsoft.com/azure/databricks/sql/language-manual/sql-ref-syntax-ddl-create-table-using
            sql(f"CREATE TABLE IF NOT EXISTS {catalog}.bronze.bootstrap_probe "
                f"USING DELTA COMMENT '{comment}' "
                f"AS SELECT 1 AS probe_id, '{stage}' AS env_marker")
            detail_names, detail_rows = result_rows(sql(f"DESCRIBE DETAIL {catalog}.bronze.bootstrap_probe"))
            if len(detail_rows) != 1:
                raise RuntimeError("DESCRIBE DETAIL must return one probe metadata row.")
            detail = dict(zip(detail_names, detail_rows[0], strict=True))
            root = stage_config["databricks_managed_location"].rstrip("/")
            if (
                detail["description"] != comment
                or detail["format"] != "delta"
                or not detail["location"].startswith(root + "/__unitystorage/")
                or int(detail["numFiles"]) < 1
            ):
                raise RuntimeError(f"{catalog} probe ownership/Delta/physical-storage verification failed.")
            _, rows = result_rows(sql(
                f"SELECT COUNT(*) AS row_count, env_marker FROM {catalog}.bronze.bootstrap_probe GROUP BY env_marker"
            ))
            if rows != [["1", stage]]:
                raise RuntimeError(f"{catalog} probe row count or stage marker is incorrect: {rows}")
            _, grants = result_rows(sql(f"SHOW GRANTS ON SCHEMA {catalog}.gold"))
            if not any("EXTERNAL USE SCHEMA" in row for row in grants):
                raise RuntimeError(f"SHOW GRANTS does not list EXTERNAL USE SCHEMA for {catalog}.gold.")
            stage_config["databricks_storage_probe_id"] = detail["id"]
            stage_config["databricks_storage_probe_location"] = detail["location"]
            save_config(config)
            record(f"Step 1 Check `{stage}`: explicit gold grants, one readable row and physical __unitystorage files PASS.")
        print("Step 1 managed-storage and SHOW GRANTS checks: PASS for dev, test and prod.")
    finally:
        # https://docs.databricks.com/api/warehouses/v1/stop-warehouse
        client.stop()
        record(f"Owned bootstrap warehouse `{warehouse_id}`: STOPPED; starter warehouse untouched.")


if __name__ == "__main__":
    try:
        main()
    except ContextError as error:
        record(f"Managed-storage check blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
