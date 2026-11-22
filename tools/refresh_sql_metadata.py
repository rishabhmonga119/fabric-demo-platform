"""Refresh selected stage lakehouse SQL metadata without recreating source tables."""

import argparse
import json
import re
import sys

from bootstrap_fabric_items import post_and_wait
from common import ContextError, ROOT, load_config, verify_context
from http_api import Api, ApiError

sys.path.insert(0, str(ROOT))
from infra.deploy import record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--stage", choices=("dev", "test", "prod"), default="dev")
    parser.add_argument("--approved-prod", action="store_true")
    parser.add_argument("--lakehouse", choices=("LH_Landing", "LH_Curated"), default="LH_Landing")
    parser.add_argument("--schema", default="forecast")
    parser.add_argument("--tables", default="forecast_standard")
    args = parser.parse_args()
    tables = args.tables.split(",")
    if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in [args.schema, *tables]):
        parser.error("Schema and table names must be simple identifiers.")
    verify_context()
    if args.stage == "prod" and not args.approved_prod:
        raise ContextError("Production metadata refresh requires deployment approval.")
    config = load_config()
    stage = config["environments"][args.stage]
    api = Api("https://api.fabric.microsoft.com", config["tenant"]["id"], skill="sqldw-cli")
    lakehouse = api.request("GET", f"/v1/workspaces/{stage['workspace_id']}/lakehouses/{stage['items'][args.lakehouse]['id']}")
    endpoint_id = lakehouse["properties"]["sqlEndpointProperties"]["id"]
    if endpoint_id != stage["items"][args.lakehouse]["sql_endpoint_id"]:
        raise ContextError("Live lakehouse SQL endpoint differs; no rebind.")
    # SQLDW-CONSUMPTION-CORE.md REST API: Refresh SQL Endpoint Metadata.
    # https://learn.microsoft.com/rest/api/fabric/sqlendpoint/items/refresh-sql-endpoint-metadata
    payload = {"recreateTables": False,
               "tables": [{"schema": args.schema, "tableNames": tables}]}
    result = post_and_wait(api, f"/v1/workspaces/{stage['workspace_id']}/sqlEndpoints/{endpoint_id}/refreshMetadata",
                          payload, args.dry_run, "Scoped SQL metadata refresh")
    if args.dry_run:
        return
    statuses = result["value"]
    print(json.dumps(statuses), flush=True)
    if len(statuses) != len(tables) or any(
            status["status"] != "Success" and not (
                status["status"] == "NotRun" and status.get("lastSuccessfulSyncDateTime"))
            for status in statuses):
        record(f"Scoped SQL metadata refresh did not succeed: `{json.dumps(statuses)}`; source tables unchanged.")
        raise ApiError("Scoped SQL metadata refresh returned a non-success table status.")
    skipped = [status["tableName"] for status in statuses if status["status"] == "NotRun"]
    record(f"Scoped {args.lakehouse}.{args.schema} SQL metadata refresh checked for {args.tables}; "
           f"previously synced NotRun tables: {skipped}; recreateTables=false; source tables unchanged.")


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ApiError) as error:
        record(f"Forecast metadata refresh blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
