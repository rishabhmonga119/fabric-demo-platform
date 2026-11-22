# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "jupyter",
# META     "jupyter_kernel_name": "python3.11"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "fd2d2f87-dff9-4974-b943-1d45cc2fcd90",
# META       "default_lakehouse_name": "LH_Landing",
# META       "default_lakehouse_workspace_id": "3fa9b173-f000-4529-a4f7-00d0d6a8d136"
# META     }
# META   }
# META }

# PARAMETERS CELL ********************

stage = 'dev'
expected_tenant = '5c41223c-f1f5-4979-930f-d5f3c72353f9'
allowed_actors = ['341769a6-9b1d-422e-8080-a666d62dc21d', 'e4234475-0f90-44c2-b256-20ce1b6c7614', '4d3bdf19-e671-4e5a-b2cb-b2b0098a5d89']
mappings = {'headers': {'Monat': 'month', 'Artikelnummer': 'sku', 'Gebinde': 'package_code', 'Region': 'region_code', 'Kanal': 'channel_code', 'Menge (hl)': 'forecast_hl'}, 'channels': {'Handel': 'RETAIL', 'Gastro': 'HORECA', 'GFGH': 'WHOLESALE', 'Online': 'ECOM'}, 'packages': {'Still 0,75 Glas': 'GL-075-RET', '0,25 Glas': 'GL-025-RET', 'PET 1,0': 'PET-100', 'PET 0,5': 'PET-050', 'PET 1,5': 'PET-150'}}


# CELL ********************

"""Pure forecast parsing shared by the generated Fabric notebook and local checks."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

FIELDS = ("month", "sku", "package_code", "region_code", "channel_code", "forecast_hl")
GRAIN = FIELDS[:-1]


def parse_month(value):
    if isinstance(value, (datetime, date)):
        return date(value.year, value.month, 1)
    text = str(value).strip()
    text = re.sub(r"\b(?:Mär|Maerz|März)\b", "Mar", text, flags=re.IGNORECASE)
    for pattern in ("%Y-%m-%d", "%Y-%m", "%m/%Y", "%b %y"):
        try:
            parsed = datetime.strptime(text, pattern)
            return date(parsed.year, parsed.month, 1)
        except ValueError:
            continue
    raise ValueError(f"Invalid forecast month: {value}")


def parse_volume(value):
    if value is None or isinstance(value, bool):
        raise ValueError("Forecast volume is missing or invalid.")
    text = str(value).strip().replace(" ", "")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        volume = Decimal(text)
    except InvalidOperation as error:
        raise ValueError(f"Invalid forecast volume: {value}") from error
    if not volume.is_finite() or volume < 0:
        raise ValueError("Forecast volume must be finite and non-negative.")
    return volume.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def header_key(value, mappings):
    text = str(value or "").strip()
    aliases = {key.casefold(): target for key, target in mappings["headers"].items()}
    aliases.update({field.casefold(): field for field in FIELDS})
    return aliases.get(text.casefold())


def normalize_record(record, mappings, dimensions):
    normalized = {
        "month": parse_month(record.get("month")),
        "sku": str(record.get("sku") or "").strip().upper(),
        "region_code": str(record.get("region_code") or "").strip().upper(),
        "forecast_hl": parse_volume(record.get("forecast_hl")),
    }
    package = str(record.get("package_code") or "").strip()
    package_aliases = {text.casefold(): code for text, code in mappings["packages"].items()}
    normalized["package_code"] = package_aliases.get(package.casefold(), package.upper())
    channel = str(record.get("channel_code") or "").strip()
    channel_aliases = {text.casefold(): code for text, code in mappings["channels"].items()}
    normalized["channel_code"] = channel_aliases.get(channel.casefold(), channel.upper())
    for field in ("sku", "package_code", "region_code", "channel_code"):
        if normalized[field] not in dimensions[field]:
            raise ValueError(f"Unknown {field}: {normalized[field]}")
    if (normalized["sku"], normalized["package_code"]) not in dimensions["valid_pairs"]:
        raise ValueError("Invalid product/package combination.")
    return normalized


def parse_sheet(rows, filename, mappings, dimensions):
    records, rejects = [], []
    indexes = None
    for number, values in enumerate(rows, start=1):
        if not any(value is not None and str(value).strip() for value in values):
            continue
        if indexes is None:
            candidates = {header_key(value, mappings): index for index, value in enumerate(values)}
            if all(field in candidates for field in FIELDS):
                indexes = {field: candidates[field] for field in FIELDS}
            continue
        source = {field: values[index] if index < len(values) else None
                  for field, index in indexes.items()}
        try:
            records.append(normalize_record(source, mappings, dimensions))
        except ValueError as error:
            rejects.append({"filename": filename, "row_number": number,
                            "reason": str(error), "raw_values": repr(source)})
    if indexes is None:
        raise ValueError(f"{filename}: required forecast headers were not found.")
    return records, rejects


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


# CELL ********************

"""Execution cell embedded in NB_Clean_Forecast."""

from pathlib import Path
from openpyxl import load_workbook

roots, options = initialize_runtime(stage, expected_tenant, allowed_actors)
curated = roots["LH_Curated"]
products = read_table(curated, "gold", "dim_product", options)
packages = read_table(curated, "gold", "dim_package", options)
regions = read_table(curated, "gold", "dim_region", options)
channels = read_table(curated, "gold", "dim_channel", options)
sales = read_table(curated, "gold", "fact_sales_monthly", options)
if set(sales["env_marker"]) != {stage}:
    raise RuntimeError("Actual data does not belong to this stage.")
dimensions = {"sku": set(products["sku"]), "package_code": set(packages["package_code"]),
              "region_code": set(regions["region_code"]), "channel_code": set(channels["channel_code"]),
              "valid_pairs": set(zip(sales["sku"], sales["package_code"]))}
standard = read_table(roots["LH_Landing"], "forecast", "forecast_standard", options)
records, rejects = [], []
for number, row in enumerate(standard.to_dict("records"), start=1):
    try:
        if pd.notna(row.get("__corrupt__")) and str(row["__corrupt__"]).strip():
            raise ValueError("Excel transformation flagged a corrupt source row.")
        records.append(normalize_record(row, mappings, dimensions))
    except ValueError as error:
        rejects.append({"filename": "forecast_standard", "row_number": number,
                        "reason": str(error), "raw_values": repr(row)})
paths = sorted(Path("/lakehouse/default/Files/raw_forecasts").glob("*.xlsx"))
if not paths:
    raise RuntimeError("No raw forecast workbooks were found through the default lakehouse shortcut.")
for path in paths:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        parsed, rejected = parse_sheet(list(workbook.active.values), path.name, mappings, dimensions)
        records.extend(parsed)
        rejects.extend(rejected)
    finally:
        workbook.close()
clean = pd.DataFrame(records, columns=FIELDS)
conflicts = clean.groupby(list(GRAIN), dropna=False)["forecast_hl"].nunique()
if (conflicts > 1).any():
    raise RuntimeError("Conflicting forecasts share the same business grain.")
duplicates = len(clean) - len(clean.drop_duplicates(subset=list(GRAIN)))
clean = clean.drop_duplicates(subset=list(GRAIN)).reset_index(drop=True)
clean["env_marker"] = stage
clean_schema = pa.schema([
    pa.field("month", pa.date32()), pa.field("sku", pa.string()),
    pa.field("package_code", pa.string()), pa.field("region_code", pa.string()),
    pa.field("channel_code", pa.string()), pa.field("forecast_hl", pa.decimal128(12, 2)),
    pa.field("env_marker", pa.string()),
])
reject_schema = pa.schema([
    pa.field("filename", pa.string()), pa.field("row_number", pa.int64()),
    pa.field("reason", pa.string()), pa.field("raw_values", pa.string()),
])
write_owned_delta(roots["LH_Landing"], "forecast", "forecast_rejects",
                  pd.DataFrame(rejects, columns=reject_schema.names), reject_schema, options)
write_owned_delta(roots["LH_Landing"], "forecast", "forecast_clean", clean, clean_schema, options)
print(json.dumps({"clean_rows": len(clean), "reject_rows": len(rejects), "duplicates_removed": duplicates}))

