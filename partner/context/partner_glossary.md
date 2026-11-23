<!-- Managed by fabric-demo-platform demo automation -->
# Partner A delivery glossary

- **Scope:** Partner P-A deliveries only, sourced from Prod Gold delivery facts.
- **Grain:** One month, product SKU, package code and region per delivery row.
- **month:** First day of the delivery month.
- **sku / product_name:** Product key and its product-dimension name. SKU digits
  are legacy identifiers, not package sizes.
- **package_code:** Beverage packaging identifier (German: Gebinde).
- **region_code:** Delivery region. The baseline P-A data covers NORTH and EAST.
- **delivered_hl:** Delivered beverage volume in hectolitres; 1 hl = 100 litres.
- **on_time_pct:** Percentage of deliveries on time, on a 0-100 scale.
  Do not sum percentages or describe an unweighted average as delivery-weighted.

The shared output has exactly seven columns: month, sku, product_name,
package_code, region_code, delivered_hl and on_time_pct. It contains no revenue,
margin, forecasts, other partners' rows, or shortcuts to internal source data.

IQ Sharing shares the entire lakehouse and does not enforce its OneLake
security roles for consumers. Keep this lakehouse output-only; do not add
unfiltered tables, source shortcuts or confidential files.
