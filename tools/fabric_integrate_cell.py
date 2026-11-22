"""Spark SQL join and PySpark Delta write embedded in NB_Integrate."""

import base64
import json

import notebookutils
import com.microsoft.spark.fabric
from com.microsoft.spark.fabric.Constants import Constants

OWNER_MARKER = "Managed by fabric-demo-platform demo automation"
context = notebookutils.runtime.context
workspace_name = context["currentWorkspaceName"]
if workspace_name != "DEMO-Analytics-" + stage.title() or \
        context["defaultLakehouseName"] != "LH_Curated" or \
        context["defaultLakehouseWorkspaceId"] != context["currentWorkspaceId"]:
    raise RuntimeError("Integration stage/default lakehouse binding differs.")
token_payload = notebookutils.credentials.getToken("storage").split(".")[1]
claims = json.loads(base64.urlsafe_b64decode(token_payload + "=" * (-len(token_payload) % 4)))
if claims["tid"] != expected_tenant or claims["oid"] not in allowed_actors:
    raise RuntimeError("Integration identity is not an approved demo principal.")
workspace = "`" + workspace_name.replace("`", "``") + "`"
sources = {
    "_integration_actual": "LH_Curated.gold.fact_sales_monthly",
    "_integration_forecast": "LH_Landing.forecast.forecast_clean",
    "_integration_product": "LH_Curated.gold.dim_product",
    "_integration_package": "LH_Curated.gold.dim_package",
}
# SQL endpoint reads handle the source catalogManaged protocol; the join stays in Spark.
for view, source in sources.items():
    spark.read.option(Constants.WorkspaceId, context["currentWorkspaceId"]).synapsesql(source).createOrReplaceTempView(view)
actual_table = "_integration_actual"
forecast_table = "_integration_forecast"
product_table = "_integration_product"
package_table = "_integration_package"
output_table = f"{workspace}.`LH_Curated`.`dbo`.`sales_vs_forecast`"
markers = spark.sql(f"""
SELECT DISTINCT env_marker FROM {actual_table}
UNION SELECT DISTINCT env_marker FROM {forecast_table}
""").limit(3).collect()
if {row.env_marker for row in markers} != {stage}:
    raise RuntimeError("Integration inputs do not belong to this stage.")
for source in (actual_table, forecast_table):
    duplicate = spark.sql(f"""
SELECT 1 FROM {source}
GROUP BY month, sku, package_code, region_code, channel_code
HAVING COUNT(*) > 1 LIMIT 1
""").collect()
    if duplicate:
        raise RuntimeError("Integration input has duplicate product/package/region/channel/month grains.")

# Keep the full channel grain and future forecast-only months; deliveries remain separate.
integrated = spark.sql(f"""
WITH combined AS (
    SELECT CAST(COALESCE(a.month, f.month) AS DATE) AS month,
           COALESCE(a.sku, f.sku) AS sku,
           COALESCE(a.package_code, f.package_code) AS package_code,
           COALESCE(a.region_code, f.region_code) AS region_code,
           COALESCE(a.channel_code, f.channel_code) AS channel_code,
           CAST(COALESCE(a.actual_hl, 0) AS DECIMAL(12,2)) AS actual_hl,
           CAST(f.forecast_hl AS DECIMAL(12,2)) AS forecast_hl,
           CAST(COALESCE(a.actual_hl, 0) - f.forecast_hl AS DECIMAL(12,2)) AS deviation_hl,
           CAST(COALESCE(a.revenue_eur, 0) AS DECIMAL(14,2)) AS revenue_eur,
           CAST(COALESCE(a.margin_eur, 0) AS DECIMAL(14,2)) AS margin_eur
    FROM {actual_table} a
    FULL OUTER JOIN {forecast_table} f
      ON CAST(a.month AS DATE) = CAST(f.month AS DATE)
     AND a.sku = f.sku AND a.package_code = f.package_code
     AND a.region_code = f.region_code AND a.channel_code = f.channel_code
)
SELECT c.month, c.sku, p.product_name, c.package_code, k.package_type,
       c.channel_code, c.region_code, CAST(NULL AS STRING) AS partner_id,
       c.actual_hl, c.forecast_hl, c.deviation_hl, c.revenue_eur, c.margin_eur,
       CAST('{stage}' AS STRING) AS env_marker
FROM combined c
LEFT JOIN {product_table} p ON c.sku = p.sku
LEFT JOIN {package_table} k ON c.package_code = k.package_code
""")
if integrated.filter("product_name IS NULL OR package_type IS NULL").limit(1).count():
    raise RuntimeError("Integration contains a key missing from the Gold dimensions.")
if spark.catalog.tableExists(output_table):
    detail = spark.sql(f"DESCRIBE DETAIL {output_table}").first().asDict()
    if not (detail.get("description") or "").startswith(OWNER_MARKER):
        raise RuntimeError("Refusing to overwrite an unowned sales_vs_forecast table.")
integrated.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("dbo.sales_vs_forecast")
spark.sql(f"COMMENT ON TABLE {output_table} IS '{OWNER_MARKER}: sales and forecast integration.'")
print(json.dumps({"integrated_rows": spark.table("dbo.sales_vs_forecast").count(), "stage": stage}))
