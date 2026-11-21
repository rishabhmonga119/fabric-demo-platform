# 04 — Sample Data Specification

Illustrative beverage data (mineral water / soft drinks). **Not customer data.** Company name and labels come from `config/demo_profile.yml`, so the same data works for other beverage or FMCG demos.

- Generator: Databricks job `seed_data` (Python, `random.seed(42)`, `numpy` seed 42) → `demo_<stage>.bronze`; job `build_medallion` → silver → gold.
- Same numbers in all three stages. Every table carries `env_marker` (`dev` / `test` / `prod`) so the audience can see which source a stage reads.
- Units: volume in hectolitres (hl), money in EUR, months as first-of-month `DATE`.
- Actuals: **2025-01 to 2026-10**. Forecasts: **2026-01 to 2026-11** (baseline) + **2026-12** (live file in Act 1).
- Expected row counts and checksums are **computed** by `tools/build_expected_counts.py` after the first run and stored in `seed/expected_counts.json` — don't hard-code them.

---

## 1. Gold tables (Unity Catalog `demo_<stage>.gold`)

Every table and column gets a `COMMENT` with the description below (feeds mirroring metadata, semantic model and data agent).

### `dim_product` (8 rows)
| Column | Type | Description |
|---|---|---|
| sku | STRING (PK) | Product code, e.g. `SKU-STL-075` |
| product_name | STRING | Display name, e.g. "Spring Still" |
| product_line | STRING | Still, Sparkling, Medium, Flavoured, Soft drink |
| launch_year | INT | Year of launch |
| env_marker | STRING | Source environment |

Products (sku → name): `SKU-STL-075` Spring Still, `SKU-SPK-100` Spring Sparkling, `SKU-MED-100` Spring Medium, `SKU-NAT-075` Spring Naturelle, `SKU-LEM-050` Spring Lemon, `SKU-APS-050` Spring Apple Spritz, `SKU-COZ-050` Spring Cola Zero, `SKU-ITP-050` Spring Iced Tea Peach. (The number in the SKU is a legacy code, not the package; package comes from `dim_package`.)

### `dim_package` (5 rows) — "Gebinde"
| package_code | package_type | volume_l | returnable |
|---|---|---|---|
| GL-075-RET | Glass | 0.75 | true |
| GL-025-RET | Glass | 0.25 | true |
| PET-100 | PET | 1.0 | false |
| PET-050 | PET | 0.5 | false |
| PET-150 | PET | 1.5 | false |

Valid SKU × package combinations: ~16 (waters in all glass + PET-100/150; soft drinks in PET-050/100 + GL-025). Generator defines the list explicitly.

### `dim_channel` (4 rows)
`RETAIL` (food retail), `HORECA` (gastronomy), `WHOLESALE` (beverage wholesale), `ECOM` (online).

### `dim_region` (4 rows)
`NORTH`, `SOUTH`, `EAST`, `WEST` with `region_name` and `sales_manager` (fictional names).

### `dim_partner` (3 rows)
`P-A` Logistics partner A, `P-B` Retail partner B, `P-C` Wholesale partner C; columns `partner_type`, `country`.

### `fact_sales_monthly`
Grain: month × sku × package_code × region_code × channel_code (valid combinations only).
| Column | Type | Description |
|---|---|---|
| month | DATE | First day of month |
| sku, package_code, region_code, channel_code | STRING | Keys |
| actual_hl | DECIMAL(12,2) | Sold volume in hectolitres |
| revenue_eur | DECIMAL(14,2) | Net revenue |
| margin_eur | DECIMAL(14,2) | Contribution margin (sensitive → hidden in Act 6) |
| env_marker | STRING | Source environment |

Generation rules: base volume per SKU/package; seasonality (summer peak +35% Jun–Aug, December +10% for soft drinks); channel mix RETAIL 55%, WHOLESALE 25%, HORECA 15%, ECOM 5%; growth +4% YoY; price per hl by package; margin 18–32% by product line; noise ±6%.

### `fact_deliveries`
Grain: month × partner_id × sku × package_code × region_code. Columns: `delivered_hl`, `on_time_pct` (85–99%), `env_marker`. Only partners P-A/P-B/P-C; P-A covers NORTH and EAST.

**Rule for Act 3/6:** no row filters or column masks on any gold table (they would block mirroring).

---

## 2. Forecast Excel files (SharePoint `Forecasts/<Stage>/`)

Grain: month × sku × package_code × region_code × channel_code. Forecast = actual × random factor 0.85–1.15 (for months with actuals) or trend projection (November).

### `standard/` — homogeneous (for Excel shortcut transformation)
All files: one sheet `Forecast`, row 1 = headers, identical columns:
`month (yyyy-mm-dd) | sku | package_code | region_code | channel_code | forecast_hl`

| File | Content |
|---|---|
| `forecast_NORTH_2026.xlsx` | NORTH, 2026-01 … 2026-11 |
| `forecast_SOUTH_2026.xlsx` | SOUTH, 2026-01 … 2026-11 |
| `forecast_EAST_2026.xlsx` | EAST, 2026-01 … 2026-11 |

### `raw/` — messy (for `NB_Clean_Forecast`)
Region WEST, delivered "by departments", each with a different problem:

| File | Problems built in |
|---|---|
| `Planung_West_Handel.xlsx` | Title rows 1–3 ("Absatzplanung 2026 – Vertrieb West"), German headers `Monat, Artikelnummer, Gebinde, Kanal, Menge (hl)`, comma decimals stored as text (`1.234,5`) |
| `west_gastro_forecast_v3_FINAL.xlsx` | Months as text `Jan 26`, `Feb 26`…, merged header cells, one empty row in the middle, channel written as "Gastro" (→ HORECA) |
| `West-GFGH.xlsx` | Month as `01/2026`, package as product text ("Still 0,75 Glas" → GL-075-RET), one row with unknown SKU (`SKU-XXX-999`) → must land in `forecast_rejects`, one duplicate row |

Mapping table for the cleaning notebook (also in `config/mappings.yml`): header synonyms, channel synonyms (Handel→RETAIL, Gastro→HORECA, GFGH→WHOLESALE, Online→ECOM), package text → package_code.

### `live/` — used during the demo (not uploaded at baseline)
`forecast_2026-12_late.xlsx` — standard layout, all regions except WEST, month 2026-12. Dropped into `Forecasts/Dev/standard` in Act 1.

---

## 3. Fabric tables (per stage)

| Lakehouse | Table | Built by | Notes |
|---|---|---|---|
| LH_Landing | `forecast.forecast_standard` | Excel shortcut transformation | Delta, synced ~every 2 min |
| LH_Landing | `forecast.forecast_clean` | NB_Clean_Forecast | Union of standard + cleaned raw |
| LH_Landing | `forecast.forecast_rejects` | NB_Clean_Forecast | Rows failing validation, with reason |
| LH_Curated | `gold.*` | Schema shortcut to MIR_UC_Gold | Zero copy |
| LH_Curated | `forecast_clean` | Table shortcut to LH_Landing | Zero copy |
| LH_Curated | `sales_vs_forecast` | NB_Integrate | Grain month × sku × package × region × channel; columns: actual_hl, forecast_hl, deviation_hl, revenue_eur, margin_eur, partner_id (nullable), env_marker |
| LH_PartnerA (DEMO-Partner-A) | `partner_a_deliveries` | NB_Partner_Extract | P-A only, no revenue/margin |

---

## 4. Semantic model `SM_Sales` (baseline)

Measures: `[Actual hl]`, `[Forecast hl]`, `[Deviation hl]`, `[Deviation %]`, `[Revenue EUR]`, `[Margin EUR]`, `[Margin %]`.
**Not in baseline:** `[Forecast Accuracy %]` — added live in Act 3 (reset removes it).

---

## 5. Ontology `ONT_Business`

| Entity | Bound to | Key properties | Relationships |
|---|---|---|---|
| Product | gold.dim_product | sku, name, line | sold in → Package |
| Package (Gebinde) | gold.dim_package | code, type, volume, returnable | — |
| Channel | gold.dim_channel | code, name | — |
| Region | gold.dim_region | code, name, sales manager | — |
| Partner | gold.dim_partner | id, type | delivers → Product in Region |
| SalesPeriod | sales_vs_forecast | month, actual, forecast, deviation | of Product, in Region, via Channel |

---

## 6. Demo change rows (used live, reverted by reset)

| Act | Change | Statement / action | Visible effect |
|---|---|---|---|
| 1 | +5,000 hl actual | `UPDATE demo_dev.gold.fact_sales_monthly SET actual_hl = actual_hl + 5000 WHERE sku='SKU-STL-075' AND region_code='NORTH' AND month=DATE'2026-10-01';` (all channels of that combination) | Spike in North, Oct 2026, Spring Still; large positive deviation |
| 1 | Late forecast | Upload `forecast_2026-12_late.xlsx` to `Forecasts/Dev/standard` | December 2026 forecast appears |
| 7 | New partner delivery | `INSERT INTO demo_prod.gold.fact_deliveries VALUES (DATE'2026-10-01','P-A','SKU-SPK-100','PET-100','NORTH', 120.00, 97.5,'prod');` then run Prod `PL_Refresh` + `NB_Partner_Extract` | New row visible in tenant B |

Note: Act 1 changes Dev only; Act 7 changes Prod data (needed because partners read Prod). Both are reverted by `reset_databricks.py`.

---

## 7. Pre-tested agent questions (`docs/agent_questions.md`)

1. Which package type had the largest forecast deviation in October 2026 in region North?
2. Show forecast accuracy by channel for Q3 2026. *(after Act 3 deployment; before: "deviation %")*
3. Compare actual vs forecast for PET 1.0 l in the last three months.
4. Which channel grew fastest in 2026 compared to 2025?
5. What was margin by region last month? *(used in Act 6 to show RLS/CLS)*
