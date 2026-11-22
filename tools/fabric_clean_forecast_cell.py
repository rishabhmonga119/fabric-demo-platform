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
