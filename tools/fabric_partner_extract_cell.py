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
