# Fabric notebook source

# METADATA ********************
# META {
# META   "kernel_info": {
# META     "name": "jupyter",
# META     "jupyter_kernel_name": "python3.11"
# META   },
# META   "kernelspec": {
# META     "name": "python3.11",
# META     "display_name": "Python 3.11",
# META     "language": "python"
# META   },
# META   "language_info": {
# META     "name": "python"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "56048088-1c7a-42ab-8120-41da7f3879b3",
# META       "default_lakehouse_name": "LH_PartnerA",
# META       "default_lakehouse_workspace_id": "f29bb81d-9fae-413e-bff4-0a1c56a78ac3"
# META     }
# META   }
# META }

# PARAMETERS CELL ********************

expected_tenant = '5c41223c-f1f5-4979-930f-d5f3c72353f9'
allowed_actors = ['341769a6-9b1d-422e-8080-a666d62dc21d']
partner_workspace_name = 'DEMO-Partner-A'
source_workspace_id = '4cd2247c-ab4c-441a-9637-f3c3d525f4c1'
source_lakehouse_id = '4e5c9ace-eea9-4796-94b6-48e3c1e55d91'
partner_glossary = "<!-- Managed by fabric-demo-platform demo automation -->\n# Partner A delivery glossary\n\n- **Scope:** Partner P-A deliveries only, sourced from Prod Gold delivery facts.\n- **Grain:** One month, product SKU, package code and region per delivery row.\n- **month:** First day of the delivery month.\n- **sku / product_name:** Product key and its product-dimension name. SKU digits\n  are legacy identifiers, not package sizes.\n- **package_code:** Beverage packaging identifier (German: Gebinde).\n- **region_code:** Delivery region. The baseline P-A data covers NORTH and EAST.\n- **delivered_hl:** Delivered beverage volume in hectolitres; 1 hl = 100 litres.\n- **on_time_pct:** Percentage of deliveries on time, on a 0-100 scale.\n  Do not sum percentages or describe an unweighted average as delivery-weighted.\n\nThe shared output has exactly seven columns: month, sku, product_name,\npackage_code, region_code, delivered_hl and on_time_pct. It contains no revenue,\nmargin, forecasts, other partners' rows, or shortcuts to internal source data.\n\nIQ Sharing shares the entire lakehouse and does not enforce its OneLake\nsecurity roles for consumers. Keep this lakehouse output-only; do not add\nunfiltered tables, source shortcuts or confidential files.\n"

# METADATA ********************
# META {
# META   "language": "python",
# META   "language_group": "jupyter_python",
# META   "tags": [
# META     "parameters"
# META   ]
# META }

# CELL ********************

"""Project only Partner A delivery facts and their many-to-one product names."""

from datetime import date, datetime
from decimal import Decimal

PARTNER_COLUMNS = (
    "month", "sku", "product_name", "package_code", "region_code",
    "delivered_hl", "on_time_pct",
)


def partner_deliveries(deliveries: list[dict], products: list[dict]) -> list[dict]:
    if not deliveries or not products:
        raise ValueError("Partner extraction requires nonempty delivery and product sources.")
    names = {}
    for product in products:
        if product["env_marker"] != "prod":
            raise ValueError("Product source is not exclusively Prod.")
        sku, name = product["sku"], product["product_name"]
        if sku in names or not sku or not name:
            raise ValueError("Product SKU must uniquely identify a nonempty product name.")
        names[sku] = name
    result = []
    for row in deliveries:
        if row["env_marker"] != "prod":
            raise ValueError("Delivery source is not exclusively Prod.")
        if row["partner_id"] != "P-A":
            continue
        if row["sku"] not in names:
            raise ValueError("A Partner A delivery has no matching product.")
        month = row["month"]
        if isinstance(month, datetime):
            month = month.date()
        if not isinstance(month, date) or month.day != 1:
            raise ValueError("Delivery month must be a month-start date.")
        volume, on_time = Decimal(str(row["delivered_hl"])), Decimal(str(row["on_time_pct"]))
        if not volume.is_finite() or not on_time.is_finite() or volume < 0 or not 0 <= on_time <= 100:
            raise ValueError("Invalid delivered volume or on-time percentage.")
        if not row["package_code"] or not row["region_code"]:
            raise ValueError("Partner A delivery keys must not be empty.")
        result.append(dict(zip(PARTNER_COLUMNS, (
            month, row["sku"], names[row["sku"]], row["package_code"],
            row["region_code"], volume, on_time,
        ))))
    if not result:
        raise ValueError("There are no Partner A deliveries.")
    return sorted(result, key=lambda row: (row["month"], row["sku"],
                                           row["package_code"], row["region_code"]))

# METADATA ********************
# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

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


def initialize_runtime(stage, expected_tenant, allowed_actors, *,
                       workspace_name=None, lakehouse_names=("LH_Landing", "LH_Curated")):
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
    expected_name = workspace_name or "DEMO-Analytics-" + stage.title()
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
    for name in lakehouse_names:
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

# METADATA ********************
# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

"""Run inside the approved pure-Python Partner A extraction notebook."""

from pathlib import Path

roots, options = initialize_runtime(
    "prod", expected_tenant, allowed_actors,
    workspace_name=partner_workspace_name, lakehouse_names=("LH_PartnerA",))
with notebookutils.data.connect_to_artifact(
        source_lakehouse_id, source_workspace_id, "Lakehouse") as connection:
    deliveries = connection.query("SELECT TOP (100001) * FROM [gold].[fact_deliveries]")
    products = connection.query("SELECT TOP (100001) * FROM [gold].[dim_product]")
if len(deliveries) > 100000 or len(products) > 100000:
    raise RuntimeError("Source exceeds the small-demo Python row limit.")
output = partner_deliveries(deliveries.to_dict("records"), products.to_dict("records"))
schema = pa.schema([
    ("month", pa.date32()), ("sku", pa.string()), ("product_name", pa.string()),
    ("package_code", pa.string()), ("region_code", pa.string()),
    ("delivered_hl", pa.decimal128(12, 2)), ("on_time_pct", pa.decimal128(5, 2)),
])
root = roots["LH_PartnerA"]
write_owned_delta(root, "dbo", "partner_a_deliveries", pd.DataFrame(output), schema, options)
written = DeltaTable(root + "/Tables/dbo/partner_a_deliveries",
                     storage_options=options).to_pyarrow_table()
if not written.schema.equals(schema, check_metadata=False):
    raise RuntimeError("Persisted partner table has unexpected columns or types.")
observed = written.to_pylist()
expected_rows = sorted(tuple(row[column] for column in PARTNER_COLUMNS) for row in output)
observed_rows = sorted(tuple(row[column] for column in PARTNER_COLUMNS) for row in observed)
if observed_rows != expected_rows:
    raise RuntimeError("Persisted Delta rows differ from the filtered P-A projection.")
folder = Path("/lakehouse/default/Files/context")
path = folder / "partner_glossary.md"
if path.exists() and not path.read_text(encoding="utf-8").startswith("<!-- " + OWNER_MARKER):
    raise RuntimeError("Refusing to overwrite an unowned partner glossary.")
folder.mkdir(parents=True, exist_ok=True)
path.write_text(partner_glossary, encoding="utf-8")
if path.read_text(encoding="utf-8") != partner_glossary:
    raise RuntimeError("Partner glossary did not persist exactly.")
verification = {
    "check": "PASS", "table": "dbo.partner_a_deliveries", "rows": len(observed),
    "columns": written.column_names,
    "delivered_hl": str(sum(row["delivered_hl"] for row in observed)),
    "min_month": str(min(row["month"] for row in observed)),
    "max_month": str(max(row["month"] for row in observed)),
    "regions": sorted({row["region_code"] for row in observed}),
    "exact_filtered_row_readback": True, "glossary_readback": True,
}
print(json.dumps(verification))
notebookutils.notebook.exit(json.dumps(verification))

# METADATA ********************
# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }
