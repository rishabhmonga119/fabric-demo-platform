"""Runtime cell embedded into the two pure-Python Fabric notebooks."""

import base64
import json
from urllib.parse import urlparse

import notebookutils
import pandas as pd
import pyarrow as pa
import requests
from deltalake import DeltaTable, write_deltalake
from deltalake.exceptions import TableNotFoundError

OWNER_MARKER = "Managed by fabric-demo-platform demo automation"
SQL_READ_TARGETS = {}


def initialize_runtime(stage, expected_tenant, allowed_actors):
    if "spark" in globals():
        raise RuntimeError("This notebook requires the pure Python kernel, not Spark.")
    context = notebookutils.runtime.context
    workspace_id = context["currentWorkspaceId"]
    token = notebookutils.credentials.getToken("storage")
    payload = token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    if claims["tid"] != expected_tenant or claims["oid"] not in allowed_actors:
        raise RuntimeError("Notebook storage identity is not an approved demo principal.")
    api_token = notebookutils.credentials.getToken("pbi")

    def read_api(path):
        response = requests.get(
            "https://api.fabric.microsoft.com/v1/" + path,
            headers={"Authorization": "Bearer " + api_token, "x-ms-fabric-skill": "spark-cli"},
            timeout=60, allow_redirects=False)
        response.raise_for_status()
        if response.is_redirect:
            raise RuntimeError("Unexpected Fabric API redirect.")
        return response.json()

    workspace = read_api("workspaces/" + workspace_id)
    expected_name = "DEMO-Analytics-" + stage.title()
    if workspace["displayName"] != expected_name:
        raise RuntimeError("Notebook stage and workspace binding differ.")
    lakehouses = []
    page = read_api(f"workspaces/{workspace_id}/lakehouses")
    lakehouses.extend(page["value"])
    while page.get("continuationToken"):
        from urllib.parse import quote
        page = read_api(f"workspaces/{workspace_id}/lakehouses?continuationToken={quote(page['continuationToken'], safe='')}")
        lakehouses.extend(page["value"])
    resolved = {}
    for name in ("LH_Landing", "LH_Curated"):
        matches = [item for item in lakehouses if item["displayName"] == name]
        if len(matches) != 1:
            raise RuntimeError(f"Missing or ambiguous lakehouse: {name}")
        detail = read_api(f"workspaces/{workspace_id}/lakehouses/{matches[0]['id']}")
        if detail["properties"].get("defaultSchema") != "dbo":
            raise RuntimeError("The notebook requires schema-enabled lakehouses.")
        endpoint = urlparse(detail["properties"]["oneLakeTablesPath"]).netloc
        resolved[name] = f"abfss://{workspace_id}@{endpoint}/{detail['id']}"
        SQL_READ_TARGETS[resolved[name]] = (detail["id"], workspace_id)
    return resolved, {"bearer_token": token, "use_fabric_endpoint": "true"}


def read_table(root, schema, table, options):
    artifact, workspace = SQL_READ_TARGETS[root]
    schema_name = schema.replace("]", "]]")
    table_name = table.replace("]", "]]")
    with notebookutils.data.connect_to_artifact(artifact, workspace, "Lakehouse") as connection:
        frame = connection.query(f"SELECT TOP (100001) * FROM [{schema_name}].[{table_name}]")
    if len(frame) > 100000:
        raise RuntimeError("Input exceeds the intended small-demo Python row limit.")
    return frame


def write_owned_delta(root, schema, name, frame, arrow_schema, options):
    path = f"{root}/Tables/{schema}/{name}"
    try:
        existing = DeltaTable(path, storage_options=options)
    except TableNotFoundError:
        print(f"Creating owned Delta table: {schema}.{name}")
    else:
        if not (existing.metadata().description or "").startswith(OWNER_MARKER):
            raise RuntimeError(f"Refusing to overwrite an unowned Delta table: {schema}.{name}")
    table = pa.Table.from_pandas(frame, schema=arrow_schema, preserve_index=False)
    write_deltalake(path, table, mode="overwrite", schema_mode="overwrite",
                   description=OWNER_MARKER, storage_options=options)
    print(f"{schema}.{name}: {len(frame)} rows")
