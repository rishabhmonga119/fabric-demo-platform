"""Shared GA SQL Statement Execution client for owned Databricks verification."""

import json
from pathlib import Path
import tempfile
import time

from check_databricks import workspace_environment
from common import cli, mutate, run


class DatabricksSql:
    def __init__(self, config: dict, warehouse_id: str):
        self.executable = cli("databricks")
        self.environment = workspace_environment(config)
        self.warehouse_id = warehouse_id

    def read(self, *arguments: str) -> dict:
        return json.loads(run([self.executable, *arguments, "--output", "json"],
                              env=self.environment))

    def execute(self, statement: str) -> dict:
        # https://docs.databricks.com/api/statement-execution/v1/execute-statement
        payload = {
            "warehouse_id": self.warehouse_id, "statement": statement,
            "format": "JSON_ARRAY", "disposition": "INLINE",
            "wait_timeout": "0s", "on_wait_timeout": "CONTINUE", "row_limit": 100,
        }
        with tempfile.TemporaryDirectory(prefix="demo-sql-") as directory:
            body = Path(directory) / "body.json"
            body.write_text(json.dumps(payload), encoding="utf-8")
            response = json.loads(mutate(
                [self.executable, "api", "post", "/api/2.0/sql/statements",
                 "--json", f"@{body}", "--output", "json"], env=self.environment
            ))
        deadline = time.monotonic() + 600
        while True:
            state = response["status"]["state"]
            if state == "SUCCEEDED":
                return response
            if state not in ("PENDING", "RUNNING"):
                raise RuntimeError(f"SQL execution failed: {json.dumps(response['status'])}")
            if time.monotonic() >= deadline:
                mutate([self.executable, "api", "post",
                        f"/api/2.0/sql/statements/{response['statement_id']}/cancel"],
                       env=self.environment)
                raise TimeoutError("SQL execution exceeded ten minutes.")
            time.sleep(5)
            # https://docs.databricks.com/api/statement-execution/v1/get-statement-result
            response = self.read("api", "get", f"/api/2.0/sql/statements/{response['statement_id']}")

    def stop(self) -> None:
        if self.read("warehouses", "get", self.warehouse_id)["state"] != "STOPPED":
            mutate([self.executable, "api", "post",
                    f"/api/2.0/sql/warehouses/{self.warehouse_id}/stop"],
                   env=self.environment)
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            if self.read("warehouses", "get", self.warehouse_id)["state"] == "STOPPED":
                return
            time.sleep(5)
        raise TimeoutError("Owned SQL warehouse did not confirm STOPPED.")
