# 02 — Live Demo Script (~50 min)

## Before the session (T-60 min)

- [ ] `python tools/verify.py --all` → all green (see `03-reset.md`).
- [ ] Capacity scaled up (recommended F16+ for the session), Spark session pre-warmed: run `PL_Refresh` once in Dev.
- [ ] Browser profiles, signed in and on the right page:
  - **P1 – Presenter (tenant A admin):** Fabric `DEMO-Analytics-Dev`, Databricks SQL editor, GitHub repo, SharePoint `DemoData/Forecasts/Dev/standard`.
  - **P2 – demo.north (tenant A, Viewer):** `RPT_Sales` in Prod, Teams with M365 Copilot.
  - **P3 – partner.user (tenant B):** Fabric `PARTNER-Inbound`.
- [ ] VS Code open on `fabric-demo-platform`, branch `main`, terminal ready, Copilot Chat in agent mode.
- [ ] `RPT_Sales` (Dev) has the bookmark "Demo – North Retail Oct 2026" (Region North, Channel Retail, Month Oct 2026) – create once by hand, then commit via Git sync.
- [ ] Files ready: `seed/excel/live/forecast_2026-12_late.xlsx` on desktop.
- [ ] Fallback recordings open in a hidden tab.
- [ ] Notifications off; zoom 125%.

---

## Act 1 — Sources: Databricks + SharePoint, zero copy (8 min)

**Message:** Databricks stays the engineering platform. Fabric reads Gold in place.

1. **P1 → DEMO-Analytics-Dev → `MIR_UC_Gold`.** Show the catalog tree (schemas/tables mirrored, metadata only).
   *Talk:* "Only metadata is mirrored. Fabric reads the Delta files Databricks already wrote. No pipeline, no copy, no Databricks compute at query time."
2. Open SQL analytics endpoint and run the **one-row** query (the table grain is month × sku × package × region × channel, so filtering on sku/region/month alone returns up to 16 rows):
   ```sql
   SELECT month, sku, package_code, region_code, channel_code, actual_hl, revenue_eur, margin_eur, env_marker
   FROM gold.fact_sales_monthly
   WHERE sku = 'SKU-STL-075' AND region_code = 'NORTH' AND month = '2026-10-01'
     AND package_code = 'GL-075-RET' AND channel_code = 'RETAIL';
   ```
   Point at the values (e.g. 786.28 hl) and `env_marker = 'dev'`.
3. **Databricks SQL editor (P1):** run the demo change from `04-sample-data.md` §6 – exactly **one row**, volume +500 hl, revenue and margin scaled at the same price/margin per hl so the row stays consistent:
   ```sql
   UPDATE demo_dev.gold.fact_sales_monthly
   SET actual_hl   = actual_hl + 500,
       revenue_eur = ROUND(revenue_eur * (actual_hl + 500) / actual_hl, 2),
       margin_eur  = ROUND(margin_eur  * (actual_hl + 500) / actual_hl, 2)
   WHERE sku = 'SKU-STL-075' AND region_code = 'NORTH' AND month = DATE'2026-10-01'
     AND package_code = 'GL-075-RET' AND channel_code = 'RETAIL';
   ```
   Databricks must report **num_affected_rows = 1**; if not, stop (the seed has duplicates – run reset). Optionally show `DESCRIBE HISTORY demo_dev.gold.fact_sales_monthly` – new Delta version.
   Back in Fabric, re-run the same query → new value visible (allow up to ~1 min for the SQL endpoint to pick up the new Delta version; rehearse the timing).
   *Talk:* "Your Databricks job writes, Fabric sees it. Unity Catalog stays the source of truth."
4. **`LH_Landing`:** show the SharePoint shortcuts (`standard` with Excel transformation, `raw` as files).
5. **Live:** drag `forecast_2026-12_late.xlsx` into SharePoint `Forecasts/Dev/standard`.
   *Talk while syncing (~2 min):* "Business users keep working in Excel/SharePoint. The shortcut transformation turns homogeneous files into a Delta table. It polls about every two minutes. For messy files we don't use no-code — that's a Python notebook in Git, you'll see it in a minute." *(Excel transformation is preview — say so.)*
6. Refresh `forecast.forecast_standard` → December 2026 rows present.

**If it fails:** show the Prod workspace (already contains the file) or the recording.

---

## Act 2 — Integrate + Direct Lake (5 min)

**Message:** Gold + business input → one curated table → report without an import copy.

1. Open `PL_Refresh` → **Run** (NB_Clean_Forecast → NB_Integrate). While it runs, open `NB_Clean_Forecast` and scroll through the pure parsing functions.
   *Talk:* "This is code — Python, versioned, tested with pytest — exactly your keep-it-simple principle."
2. Open `LH_Curated`: shortcuts to `gold` (from the mirror) and `forecast_clean`, plus the one materialised table `sales_vs_forecast`.
   *Talk:* "Sources exist once per environment. The only thing we materialise is the result."
3. **Open `RPT_Sales` (Dev), page "Actual vs Forecast".** The report reads `sales_vs_forecast`, so the Act 1 change only shows after `PL_Refresh` (step 1) has finished.
   - Use the prepared bookmark **"Demo – North Retail Oct 2026"**: Region = North, Channel = Retail, Month = Oct 2026.
   - In the product × package matrix, point at **SKU-STL-075 / GL-075-RET**: Actual hl is about 500 higher than in the Act 1 query (~786 → ~1,286). Deviation hl and Deviation % now show a clear positive gap against the forecast, and Revenue and Margin rise with it.
   - Clear the Month filter → the line chart shows the forecast line running through **December 2026** (from the late Excel upload); actuals end earlier.
   - If the value has not changed: model settings → Refresh (for Direct Lake this is a reframe that takes seconds – no data import). Keep "Keep your Direct Lake data up to date" switched on.
   *Talk:* "Direct Lake reads the Delta table directly – no import refresh, no second copy per department model. Refresh here only means 'look at the latest table version', it takes seconds, not a scheduled import."

---

## Act 3 — Code-first with GitHub Copilot (8 min)

**Message:** AI writes the code; humans review; the result is deterministic.

1. **VS Code:** `git checkout -b feature/forecast-accuracy`.
2. Copilot Chat (agent mode) prompt:
   ```
   Using the semantic-model-authoring skill, add a measure [Forecast Accuracy %] to
   SM_Sales (TMDL in /fabric/SM_Sales.SemanticModel):
   1 - ABS([Actual hl] - [Forecast hl]) / [Actual hl], 0 when actual is 0, format 0.0%,
   display folder "Forecast", description for business users, synonym "accuracy".
   Also add the measure to the DA_Sales instructions as the definition of forecast accuracy.
   Don't change anything else. Show me the diff.
   ```
3. Walk through the **diff** (readable TMDL + instruction text).
   *Talk:* "Your page 'AI as code generator' — semantics provided, AI generates, review in Git, deterministic run. Same four steps, on Fabric."
4. Commit, push, `gh pr create --fill` → open PR in browser → **pr-check** workflow runs pytest + parameter validation (green).
5. Mention: "Skills for Fabric is open source from Microsoft; Fabric MCP gives the agent access to the tenant. Skills = knowledge, MCP = hands."

**If Copilot output differs:** use the prepared branch `demo/forecast-accuracy-prepared` (`git checkout` it and continue).

---

## Act 4 — CI/CD Dev → Test → Prod (7 min)

**Message:** Definitions move, data doesn't. Each stage binds to its own sources.

1. Merge the PR. Open **Actions → deploy**: `update-dev` → `deploy-test` (running).
2. While it runs, open `/fabric/parameter.yml` and `config/environments.yml`.
   *Talk:* "Dev binds to `demo_dev` and `Forecasts/Dev`; Test to `demo_test`; Prod to `demo_prod`. fabric-cicd re-points the items; the post-deploy step rebinds shortcuts and the mirror. No data is copied between stages."
   *Honest note:* "Compared to DABs, this is more pieces — Git integration, fabric-cicd, parameter file, variable library. DABs are more declarative today; Terraform coverage on Fabric is lower. That's the trade-off."
3. `deploy-prod` waits for **approval** → approve in GitHub.
4. Open **DEMO-Analytics-Prod → SM_Sales** → measure `[Forecast Accuracy %]` exists; report uses Prod data (`env_marker = 'prod'`).
   *Talk:* "Prod never saw our Dev update of Databricks — different catalog."

**Timing tip:** if the run is slow, show a completed run from the rehearsal (`Actions → previous run`) and come back later.

---

## Act 5 — Fabric IQ: ontology, data agent, Teams and M365 Copilot (9 min)

**Message:** One business layer — used by reports, agents and Copilot.

1. **Prod → `ONT_Business`:** show entities Product, Package, Channel, Region, Partner and their bindings to gold + `sales_vs_forecast`.
   *Talk:* "Your Unity Catalog comments and metric views map to this: descriptions, measures, relationships — but reused by Power BI, Copilot and any MCP client."
2. **`DA_Sales`** (in Fabric): ask
   - "Which package type had the largest forecast deviation in October 2026 in region North?"
   - "Show forecast accuracy by channel for Q3 2026."
   → open the generated query (DAX/SQL) — *"traceable, not a black box"*.
3. **Teams / M365 Copilot (P1):** `@DA_Sales Compare actual vs forecast for PET 1.0 l in the last three months.`
4. **M365 Copilot → "Sales Assistant" (Agent Builder, Fabric capability):** "Which channel grew fastest this year?"
   *Talk:* "No MCP endpoint to configure — Fabric IQ is a first-party capability. Permissions and row-level security are respected."
5. Optional one-liner: "Fabric IQ connectors for ChatGPT and Claude were announced at Ignite in preview — same semantics, other assistants."

**Example questions (pre-tested):** keep 5 in `docs/agent_questions.md`.

---

## Act 6 — OneLake security: RLS + CLS everywhere (6 min)

**Message:** Define once, enforced in report, SQL and Copilot.

1. **P1 → Prod → `LH_Curated` → Manage OneLake security → New role `Sales_North`:**
   - Data: **only `dbo.sales_vs_forecast`** (the one table materialised in `LH_Curated`). Do **not** select `gold/*` or `forecast_clean`: those are shortcuts, and OneLake security does not allow roles on shortcuts that pass the user's identity through (error "defining roles for SSO shortcuts is not supported"). Their access is governed at the source item.
   - Row filter on `sales_vs_forecast`: `region_code = 'NORTH'`.
   - Column security: hide `margin_eur`, `revenue_eur`.
   - Members: `SG-Demo-Sales-North`.
   - *Prepared before the session:* read access for the sales groups on the gold dims at the source (`MIR_UC_Gold`) – a read role there, or share the item with "Read all data". Dims are not sensitive; the facts are protected in `LH_Curated`.
   *Talk:* "Security is defined where the data lives. A shortcut passes the user's identity through to the source, which is the same principle as Unity Catalog."
2. **P2 (demo.north):**
   - `RPT_Sales` → only North; Margin page shows no data / not allowed.
   - SQL endpoint: `SELECT DISTINCT region_code FROM sales_vs_forecast` → only NORTH; selecting `margin_eur` fails.
   - Teams: `@DA_Sales What was margin by region last month?` → only North, no margin.
   *Talk:* "Same rule, three engines. Your department-level service principals in Power BI become roles on the data."
3. Mention the Databricks link: "UC row filters and column masks are not mirrored — tables with those policies are excluded. That's why we set the rule in OneLake. Policy Weaver or Trust3 AI can sync supported UC policies if you want one source."

**If the report doesn't filter:** the model isn't using user identity → show SQL endpoint + agent, explain, fix after the session.

---

## Act 7 — Partners: own domain, own tenant, no guest (7 min)

**Message:** Your partner works in their tenant; you control access, expiry and revocation.

1. **P1 → OneLake catalog → Domains:** `Demo Analytics` vs `Demo Partners`. Open `DEMO-Partner-A` → `LH_PartnerA.partner_a_deliveries` (only partner P-A, no money columns) + `Files/context/partner_glossary.md`.
2. **Option A (today, per your PDF):** "A guest user from the partner gets Viewer + a OneLake role here." Show the role `Partner_A_Read` (pre-built). Don't log in.
3. **Option B — IQ Sharing (preview), live:**
   1. **P1 → `DEMO-Partner-A` → + New item → Share (preview)** – a separate Share item, *not* the Share button on the lakehouse. Name `LHPartnerShare` → Select data: `LH_PartnerA` (the whole item is shared, incl. its Markdown context files; no single-table selection) → Recipients: the partner user's e-mail in tenant B → Expiration date (required) → Share.
      **IQ Sharing sends no e-mail.** Click **Copy share URL** and paste it into the P3 browser window (in real life: send it by mail/Teams). Recipients tab shows *Pending* until accepted.
   2. **P3 (tenant B, signed in as the invited identity):** open the share URL → review *Sent from*, expiry, shared data → item name → select workspace `PARTNER-Inbound` (P3 needs Admin/Member/Contributor there; Viewer can't accept) → **Accept and create item** → Share Subscription + Mirrored OneLake item appear → query `partner_a_deliveries` via its SQL analytics endpoint. Producer side: Recipients status changes to *Accepted*.
      *Prerequisite tenant B:* Fabric admin setting **Enable Share Subscription Item (preview)**. Tenant A: **Enable Share Item (preview)** + **External data sharing**.
   3. **P1:** run `NB_Partner_Extract` after the Act 1 change (or insert one delivery row) → **P3** re-query → new row visible (zero copy).
   4. **P1:** revoke recipient → **P3** query fails.
   *Talk:* "No B2B guest, no copy, expiry built in. Important: OneLake security roles on the source are not applied through IQ Sharing, and the partner's tenant governs access on their side — that's why we share a partner-specific lakehouse, never the full curated data with row filters."
4. Mention: Delta Sharing from Databricks remains valid for partners without Fabric.

**If IQ Sharing misbehaves (preview):** fall back to **external data sharing** (GA path) with the same flow, or the recording.

---

## Close (2 min)

- Recap the seven acts against their comparison rows: Ingest, Externals, Notebooks, CI/CD, IaC, Power BI, Semantics, AI writes code.
- Be explicit about gaps: DABs more declarative; Terraform coverage lower; SAC tighter with Databricks today; ABAC on roadmap without date.
- Next step: PoC on their Gold catalog (Acts 1, 2, 5, 6) with measurable criteria.

## Timing summary

| Act | Min |
|---|---|
| 1 Sources | 8 |
| 2 Integrate + Direct Lake | 5 |
| 3 Copilot code-first | 8 |
| 4 CI/CD | 7 |
| 5 Fabric IQ / Copilot / Teams | 9 |
| 6 OneLake security | 6 |
| 7 Partners | 7 |
| Close | 2 |
| **Total** | **52** |

Shorten if needed: drop Act 2 step 1 (pipeline run) and the SQL part of Act 6.
