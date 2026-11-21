# 01 — Base Setup with GitHub Copilot

How to use this file:
- Work top to bottom. Each step has **Goal**, **Copilot prompt** (paste into VS Code Copilot Chat, agent mode), **Manual steps** (things Copilot can't or shouldn't do) and **Check**.
- Copilot must use **Skills for Fabric** for every Fabric API/CLI call and the official docs for Azure/Databricks. Never let it invent API payloads — if unsure, it must read the skill reference or Microsoft Learn first.
- Estimated effort: 1–1.5 days first time.

---

## Step 0 — Workstation, repo and Copilot guardrails

**Goal:** repo skeleton, Skills for Fabric installed, Copilot instructions in place.

**Manual steps**
1. Create GitHub repo `fabric-demo-platform` as **Public** with owner **`rishabhmonga119`** (your personal account — not the `microsoft` organization). Public is fine: no secrets, no customer data (keep `company_name` generic) and environments with required reviewers work on public repos. Clone it and open in VS Code.
   - Copilot can keep running under your Microsoft-linked GitHub sign-in; the repo owner is independent of the Copilot account.
   - Fabric Git integration (step 5.11): fine-grained personal access token from `rishabhmonga119`, scoped to `fabric-demo-platform` only, Contents read/write, short expiry.
2. Install Skills for Fabric for GitHub Copilot CLI:
   ```
   /plugin marketplace add microsoft/skills-for-fabric
   /plugin install fabric-skills@fabric-collection
   /plugin install powerbi-authoring@fabric-collection
   ```
   For VS Code agent mode at project scope, alternatively use APM (`apm install microsoft/skills-for-fabric --target copilot`). This also registers the Fabric MCP servers.
3. Sign in: `az login` (tenant A), `databricks auth login` (later, after step 1), `gh auth login`, `fab auth login`.

**Copilot prompt**
```
Create the repository skeleton for a reusable Fabric + Databricks demo:

/.github/copilot-instructions.md
/.github/workflows/            (empty for now)
/config/demo_profile.yml       (company_name, currency EUR, unit hl, language en)
/config/environments.yml       (dev/test/prod: Fabric workspace names, Databricks catalog,
                                SharePoint folder, entra groups – placeholders for IDs)
/databricks/                   (Databricks Asset Bundle, created in step 3)
/fabric/                       (Fabric Git integration root, populated in step 6)
/seed/excel/{dev,test,prod}/   (generated in step 4)
/tools/                        (python helpers: post_deploy.py, reset/, verify.py)
/docs/

Write .github/copilot-instructions.md with these rules:
- Use the installed Skills for Fabric for all Fabric REST, CLI (fab) and item definition work.
  Read the relevant skill before writing code. Never guess REST payloads.
- Target workspaces: DEMO-Analytics-Dev, DEMO-Analytics-Test, DEMO-Analytics-Prod, DEMO-Partner-A.
- Item names are fixed: MIR_UC_Gold, LH_Landing, LH_Curated, NB_Clean_Forecast, NB_Integrate,
  PL_Refresh, SM_Sales, RPT_Sales, ONT_Business, DA_Sales, VL_Config.
- Never copy data between stages. Each stage binds to its own sources from config/environments.yml.
- Python 3.11, azure-identity for auth, no secrets in code; read IDs from config files or env vars.
- Every script must be idempotent and support --dry-run.
- Prefer Python notebooks (no Spark) for small data; capacity is F4.
Then create a README pointing to docs/.
```

**Check:** repo pushed; `copilot-instructions.md` present; Copilot answers "which skill would you use to create a lakehouse shortcut?" with a Skills for Fabric reference.

---

## Step 1 — Azure Databricks infrastructure (create new)

**Goal:** Premium Azure Databricks workspace with Unity Catalog, own ADLS Gen2 storage per environment, external data access enabled.

**Copilot prompt**
```
Write Bicep (infra/databricks.bicep) + a deploy script (infra/deploy.ps1) that creates in
resource group rg-demo-databricks (region: West Europe, parameterised):
1. ADLS Gen2 storage account stdemolake<uniqueSuffix> with hierarchical namespace,
   containers uc-dev, uc-test, uc-prod. Public network access enabled (demo only – document this).
2. Access Connector for Azure Databricks (system-assigned managed identity) with
   "Storage Blob Data Contributor" on the storage account.
3. Azure Databricks workspace dbw-demo, SKU premium, Unity Catalog enabled.
Output: workspace URL, access connector resource ID, storage account name.
Use only resource types and API versions documented on Microsoft Learn; cite the doc page in comments.
```

**Manual steps (Databricks UI / SQL, as metastore admin)**
1. Catalog → gear → Metastore → **enable External data access** (required for Fabric mirroring).
2. Create storage credential `sc_demo` from the access connector.
3. Create external locations `el_uc_dev|test|prod` → `abfss://uc-<env>@stdemolake<suffix>.dfs.core.windows.net/`.
4. Create catalogs with **managed location on your own container** (do not rely on Databricks default storage — Fabric must reach the files):
   ```sql
   CREATE CATALOG demo_dev  MANAGED LOCATION 'abfss://uc-dev@stdemolake<suffix>.dfs.core.windows.net/';
   CREATE CATALOG demo_test MANAGED LOCATION 'abfss://uc-test@stdemolake<suffix>.dfs.core.windows.net/';
   CREATE CATALOG demo_prod MANAGED LOCATION 'abfss://uc-prod@stdemolake<suffix>.dfs.core.windows.net/';
   -- per catalog:
   CREATE SCHEMA demo_<env>.bronze; CREATE SCHEMA demo_<env>.silver; CREATE SCHEMA demo_<env>.gold;
   ```
5. Grants for the identity Fabric uses to connect (your org account; and `sp-fabric-demo-cicd` if the connection will be shared):
   ```sql
   GRANT USE CATALOG ON CATALOG demo_<env> TO `<principal>`;
   GRANT USE SCHEMA, SELECT ON SCHEMA demo_<env>.gold TO `<principal>`;
   GRANT EXTERNAL USE SCHEMA ON SCHEMA demo_<env>.gold TO `<principal>`;  -- must be explicit
   ```
   `EXTERNAL USE SCHEMA` is not included in ALL PRIVILEGES and must be granted by the catalog owner.

**Check:** `SHOW GRANTS ON SCHEMA demo_dev.gold` lists EXTERNAL USE SCHEMA; storage containers contain `__unitystorage` folders after the first table is created.

---

## Step 2 — Fabric tenant, workspaces, identities

**Manual steps (Fabric admin portal, tenant A)** — enable for `SG-Demo-Fabric-Admins` / `SG-Demo-Fabric-API` only:
- Service principals can use Fabric APIs (group `SG-Demo-Fabric-API`, add `sp-fabric-demo-cicd`)
- Git integration (users can sync workspace items with GitHub)
- Data agent item types; Copilot and Azure OpenAI; cross-geo processing and storing for AI (needed for data agent in M365 Copilot)
- Ontology / Fabric IQ items (name may differ in your tenant — search "ontology")
- External data sharing + IQ Sharing (create shares) — also enable **acceptance** in tenant B
- Allow Fabric apps: not needed (data app dropped)

**Copilot prompt**
```
Using Skills for Fabric (fab CLI or REST), write tools/bootstrap_fabric.py that idempotently:
1. Creates domains "Demo Analytics" and "Demo Partners".
2. Creates workspaces DEMO-Analytics-Dev/Test/Prod (domain Demo Analytics) and DEMO-Partner-A
   (domain Demo Partners), assigns capacity <F4 capacity id from config>.
3. Workspace roles:
   - SG-Demo-Fabric-Admins: Admin on all.
   - sp-fabric-demo-cicd: Admin on Test and Prod (deploys there), Contributor on Dev (Git update).
   - SG-Demo-Sales-North and SG-Demo-Sales-South: **Viewer** on DEMO-Analytics-Prod only
     (Admin/Member/Contributor would bypass OneLake security).
4. Writes resulting workspace IDs into config/environments.yml.
Support --dry-run. Read capacity id and group object IDs from config.
```

**Manual steps (Entra)**
1. App registration `sp-fabric-demo-cicd`; **federated credentials** for GitHub OIDC (issuer `https://token.actions.githubusercontent.com`, audience `api://AzureADTokenExchange`), subjects:
   - `repo:rishabhmonga119/fabric-demo-platform:environment:test`
   - `repo:rishabhmonga119/fabric-demo-platform:environment:prod`
   - `repo:rishabhmonga119/fabric-demo-platform:ref:refs/heads/main` (for the `update-dev` job)
   - For GitHub's immutable-subject format, the prefix includes owner/repository IDs:
     `repo:rishabhmonga119@<owner-id>/fabric-demo-platform@<repo-id>`.
     Read the repository OIDC settings/preview rather than assuming the legacy prefix.
     `tools/bootstrap_entra.py` verifies the current prefix and records it in
     `config/environments.yml`; it updates only this build's recorded credentials.
2. Users `demo.north`, `demo.south` → groups `SG-Demo-Sales-North` / `-South`; licences: M365 Copilot + Power BI Pro.
   - Alternatively, reuse two existing licensed test accounts with
     `tools/select_test_users.py --north <UPN> --south <UPN> --dry-run`, then
     without `--dry-run`. The script verifies licences and non-privileged Prod
     access, adds only sales-group memberships, and records the runtime UPNs.
     It does not move licences, change passwords or delete existing accounts.

**Check:** `fab ls` shows 4 workspaces on the F4 capacity; SP can list items in Test via a token from `az login --service-principal` (or a quick OIDC test workflow).

---

## Step 3 — Databricks Asset Bundle: seed + medallion (3 targets)

**Goal:** deterministic data in `demo_dev|test|prod`, built bronze → silver → gold by a job. Using DABs here is deliberate: it is Gerolsteiner's own tool.

**Copilot prompt**
```
Create a Databricks Asset Bundle in /databricks:
- databricks.yml with targets dev, test, prod; variable `catalog` = demo_dev|demo_test|demo_prod.
- Job `seed_data`: Python notebook that generates the data model from docs/04-sample-data.md
  with a fixed random seed (42) into ${var.catalog}.bronze (Delta, managed tables).
- Job `build_medallion`: SQL notebooks bronze→silver (types, dedup) → gold
  (dim_product, dim_package, dim_channel, dim_region, dim_partner, fact_sales_monthly,
  fact_deliveries). Gold tables: managed Delta, column comments from the data dictionary,
  NO row filters or column masks.
- Use serverless job compute if available in the workspace, otherwise a single-node job cluster.
- Add a `reset` job = seed_data then build_medallion.
Follow the current Databricks Asset Bundles docs; don't invent keys.
```

**Run**
```
databricks bundle deploy -t dev  && databricks bundle run reset -t dev
databricks bundle deploy -t test && databricks bundle run reset -t test
databricks bundle deploy -t prod && databricks bundle run reset -t prod
```

**Check:** `SELECT COUNT(*) FROM demo_prod.gold.fact_sales_monthly` matches the expected count in `04-sample-data.md`. Dev/test/prod differ only by the `env_marker` column (makes stage binding visible in the demo).

---

## Step 4 — SharePoint forecast files

**Copilot prompt**
```
Write tools/generate_excel.py (openpyxl) that creates the forecast workbooks described in
docs/04-sample-data.md into seed/excel/{dev,test,prod}/{standard,raw}/ :
- standard/: 3 homogeneous workbooks (identical columns, one sheet "Forecast") – for the
  Excel shortcut transformation.
- raw/: 3 messy workbooks (German headers, comma decimals, title rows, merged cells,
  month as text) – for the Python cleaning notebook.
- live/: 1 extra standard workbook "forecast_2026-12_late.xlsx" used during the demo (not uploaded).
Also write tools/upload_sharepoint.py using Microsoft Graph (azure-identity, delegated
device-code login) to upload seed/excel/<env>/ to site DemoData, library Documents,
folder Forecasts/<Env>/. Idempotent; --dry-run.
```

**Manual:** create site `DemoData`; run the upload for dev, test, prod.

**Check:** 6 files per stage folder in SharePoint.

---

## Step 5 — Build Fabric items in Dev (UI-first, then Git)

Build in **DEMO-Analytics-Dev** first. Mirrored catalogs, shortcuts, ontology and data agents are most reliable when created through the UI or the documented API, then captured in Git. Copilot helps with notebooks, TMDL and scripts.

### 5.1 Connections (created once, shared by all stages)
- Azure Databricks connection `conn-dbw-demo` (organizational account for the demo; share with `sp-fabric-demo-cicd`).
- SharePoint connection `conn-sp-demodata` (organizational account or workspace identity; service principal requires a **certificate**, not a secret).
- Record both connection IDs in `config/environments.yml`.

### 5.2 Mirrored catalog — `MIR_UC_Gold`
Workspace → New item → **Mirrored Azure Databricks catalog** → `conn-dbw-demo` → catalog `demo_dev`, schema `gold` only → keep "automatically sync future catalog changes" → name `MIR_UC_Gold`.
**Check:** SQL analytics endpoint shows all gold tables; `env_marker = 'dev'`.

### 5.3 `LH_Landing` (schemas enabled)
1. New **table shortcut** in schema `forecast` → OneDrive/SharePoint → `conn-sp-demodata` → folder `Forecasts/Dev/standard` → **Transform**: Excel, first row as headers, sheet `Forecast` → name `forecast_standard`. *(Excel transformation = preview)*
2. New **shortcut** under `Files` → `Forecasts/Dev/raw` → name `raw_forecasts` (no transformation).
**Check:** table `forecast.forecast_standard` populated; transformation polls about every 2 minutes.

### 5.4 Notebooks (Copilot writes them)
**Copilot prompt**
```
Using the Fabric notebook skill, create two notebooks in /fabric (Git format) for workspace
DEMO-Analytics-Dev:

NB_Clean_Forecast (Python notebook, no Spark – capacity is F4):
- Read every .xlsx under LH_Landing Files/raw_forecasts with pandas/openpyxl.
- Normalise headers (Artikelnummer→sku, Gebinde→package_code, Region→region_code,
  Monat→month, Menge (hl)→forecast_hl), skip title rows, parse German decimals and
  month text ("Jan 26", "01/2026", "2026-01") to first-of-month date.
- Validate against gold dims (read via LH_Curated shortcuts); write rejects to forecast_rejects.
- Union with forecast.forecast_standard; write LH_Landing table forecast.forecast_clean (overwrite).
- All parsing in pure functions at the top (testable).

NB_Integrate (Python or PySpark – choose Python if data < 1 GB):
- Join gold.fact_sales_monthly with forecast_clean on sku, package_code, region_code, month.
- Output LH_Curated table sales_vs_forecast: month, sku, product_name, package_code,
  package_type, channel_code, region_code, partner_id, actual_hl, forecast_hl,
  deviation_hl, revenue_eur, margin_eur, env_marker.
- Lakehouse references must use logical names/IDs that fabric-cicd can re-point
  (document required parameter.yml entries).
Also add tests in /tests for the pure parsing functions (pytest).
```

### 5.5 `LH_Curated`
- Schema shortcut `gold` → `MIR_UC_Gold` (all gold tables).
- Table shortcut `forecast_clean` → `LH_Landing`.
- Run `NB_Integrate` once → table `sales_vs_forecast`.
- **Enable OneLake security** on `LH_Curated`; keep only the default reader role for now (Act 6 adds roles live).

### 5.6 `PL_Refresh`
Pipeline: `NB_Clean_Forecast` → `NB_Integrate`. (Direct Lake picks up new Delta versions automatically; add a semantic model refresh activity only if automatic updates are off.)

### 5.7 `SM_Sales` + `RPT_Sales`
**Copilot prompt**
```
Using the semantic-model-authoring skill (powerbi-authoring bundle), create SM_Sales as a
Direct Lake on OneLake model over LH_Curated:
- Tables: sales_vs_forecast (fact), gold.dim_product, gold.dim_package, gold.dim_channel,
  gold.dim_region, gold.dim_partner. Star schema relationships.
- Measures: [Actual hl], [Forecast hl], [Deviation hl], [Deviation %], [Revenue EUR],
  [Margin EUR], [Margin %]. Format strings, display folders, descriptions on every
  table/column/measure (these feed Copilot and the data agent).
- Synonyms: hl/hectolitre/volume; Gebinde/package; Kanal/channel.
- Model must use the end-user identity for OneLake access (SSO) so OneLake security
  applies — read the Direct Lake + OneLake security doc and configure accordingly.
Save as TMDL in /fabric/SM_Sales.SemanticModel.
Then create RPT_Sales (PBIR): page 1 "Actual vs Forecast" (line by month, matrix
product × package, slicers region/channel), page 2 "Margin" (bar by channel, card Margin %).
```
**Manual:** open in Fabric, confirm the model loads; set the connection once if prompted.

### 5.8 `ONT_Business` (Fabric IQ ontology)
Create in UI (ontology skill can script it if supported): entity types **Product, Package, Channel, Region, Partner, SalesPeriod**; bind to gold dims and `sales_vs_forecast`; relationships Product–Package (sold in), Sales–Region, Sales–Channel, Partner–Deliveries; business descriptions for each entity and property. Optionally add a few rules (e.g. "Deviation above 10% = critical").

### 5.9 `DA_Sales` (data agent)
Sources: `ONT_Business` and `SM_Sales`. Instructions (store in Git with the item):
```
You answer sales and forecast questions for a beverage company.
Volumes are in hectolitres (hl), money in EUR. Months are first-of-month dates.
Use SM_Sales measures for actuals, forecast, deviation, revenue and margin.
Use ONT_Business for business terms (package/Gebinde, channel, region, partner).
Always state the period and filters you used. Never estimate missing values.
```
Add 5 example questions (see `02`, Act 5).

### 5.10 `VL_Config`
Variables: `catalog` (demo_dev/test/prod), `sp_folder` (Forecasts/Dev|Test|Prod), `env_label`. Value sets: `dev`, `test`, `prod`.

### 5.11 Connect Dev to Git
Workspace settings → Git integration → GitHub → repo `fabric-demo-platform`, branch `main`, folder `/fabric` → commit all.

**Check:** `/fabric` contains one folder per item; `git log` shows the initial commit.

---

## Step 6 — fabric-cicd, parameterisation, post-deploy bindings

**Copilot prompt**
```
Set up deployment with fabric-cicd for Test and Prod:

1. /fabric/parameter.yml – find_replace entries for:
   - Dev workspace ID → $workspace.id
   - Dev lakehouse IDs (LH_Landing, LH_Curated) in notebooks/semantic model → $items.Lakehouse.<name>.id
   - SQL endpoint / OneLake IDs in SM_Sales if present
   - DA_Sales data source IDs (ONT_Business, SM_Sales)
   - Mirrored catalog name demo_dev → demo_test / demo_prod (only if fabric-cicd applies
     find_replace to MirroredAzureDatabricksCatalog – check the item types doc first)
2. tools/deploy.py: FabricWorkspace(..., environment=<stage>, item_type_in_scope=[...]),
   publish_all_items, unpublish_all_orphan_items; enable feature flag
   enable_shortcut_publish only if needed; VL_Config active value set = stage.
3. tools/post_deploy.py (idempotent) for whatever fabric-cicd cannot bind per stage:
   - (Re)create LH_Landing shortcuts to SharePoint Forecasts/<Stage>/standard (with Excel
     transformation) and /raw, using conn-sp-demodata.
   - (Re)create or update MIR_UC_Gold to point to demo_<stage>.gold if not handled by fabric-cicd.
   - (Re)create LH_Curated shortcuts to MIR_UC_Gold and LH_Landing.forecast_clean.
   - Ensure OneLake security is enabled on LH_Curated with baseline roles from
     config/onelake_roles.baseline.json.
   - Run PL_Refresh and wait for completion.
   - For ONT_Business / DA_Sales: deploy via fabric-cicd if supported, otherwise create from
     the Git definitions via REST (document which path is used).
For every API you call, cite the Skills for Fabric reference file you used.
```

**Copilot prompt (workflow)**
```
Create .github/workflows/deploy.yml:
- on: push to main (paths: fabric/**), workflow_dispatch (input stage: test|prod|both).
- permissions: id-token: write, contents: read.
- job update-dev: azure/login (OIDC, sp-fabric-demo-cicd) → python tools/git_update_dev.py
  (Fabric REST updateFromGit for DEMO-Analytics-Dev, conflict resolution PreferRemote).
- job deploy-test: needs update-dev, environment: test → deploy.py --stage test →
  post_deploy.py --stage test → tools/verify.py --stage test.
- job deploy-prod: needs deploy-test, environment: prod (required reviewer = me) → same for prod.
- Show a step summary with item counts and the env_marker check.
Also create .github/workflows/pr-check.yml: on pull_request → pytest + a fabric-cicd
dry-run/validation of parameter.yml.
```

**Manual (GitHub):** environments `test` and `prod`; `prod` with **required reviewer** (you); secrets/vars: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `FABRIC_CAPACITY_ID` (variables, no client secret). Branch protection on `main`: PR required; allow admins to bypass (needed for reset).

**First run:** `gh workflow run deploy.yml -f stage=both` → approve Prod.
**Check:** Test shows `env_marker = 'test'`, Prod `'prod'`; reports render; shortcuts point to the stage's own folder/catalog.

---

## Step 7 — Prod-only: Copilot, Teams, Fabric IQ

1. **Publish `DA_Sales` in Prod** → Publish → **Publish to Agent Store** with a clear description.
2. M365 Copilot (as you): Agents → find DA_Sales → pin; test in Teams.
3. **Agent Builder:** New agent "Sales Assistant" → Configure → Work content → turn on **Fabric** (may show as "Power BI") → instructions:
   ```
   Use Fabric to answer business questions with Power BI data the user can access.
   State the data source, filters and period. Don't estimate unavailable values.
   ```
   Share with `SG-Demo-Sales-North`, `SG-Demo-Sales-South`.
4. Grant `demo.north`/`demo.south` read on `DA_Sales`, `SM_Sales`, `RPT_Sales` (Viewer role already covers this) — Copilot only returns data they can access.

**Check:** as `demo.north`, `@DA_Sales What was actual volume by region last month?` returns all regions (no roles yet).

---

## Step 8 — Partner domain and cross-tenant sharing

**Copilot prompt**
```
Create in /partner (separate fabric-cicd folder, deployed manually) for DEMO-Partner-A:
- LH_PartnerA with a table shortcut to DEMO-Analytics-Prod LH_Curated.sales_vs_forecast
  (shortcuts can't filter rows, so the shortcut is only an input).
- NB_Partner_Extract (Python notebook) that reads that shortcut and writes LH_PartnerA table
  partner_a_deliveries
  (only partner_id = 'P-A', columns: month, sku, product_name, package_code, region_code,
  delivered_hl, on_time_pct). No margin or revenue columns.
- Files/context/partner_glossary.md with business definitions (hl, package codes, on-time %).
```

**Manual**
1. **Option A (B2B guest):** invite `partner.user@<tenantB>` as guest to tenant A → Viewer on `DEMO-Partner-A` → enable OneLake security on `LH_PartnerA`, role `Partner_A_Read` (tables `partner_a_deliveries` only). Test once in a private browser window.
2. **Option B (IQ Sharing, preview):** keep for live (Act 7). Pre-check only: tenant A can create Shares, tenant B can accept; `PARTNER-Inbound` exists in tenant B.
3. Do a full dry run of Option B once, then delete Share + Share Subscription (see `03`).

---

## Step 9 — Baseline and recordings

1. `git tag demo-baseline && git push origin demo-baseline`.
2. Export `config/onelake_roles.baseline.json` per stage (`tools/export_roles.py`).
3. Snapshot list of SharePoint files (`seed/manifest.json`).
4. Record each act (screen recording) as fallback — especially Acts 3, 5 and 7.
5. Run `tools/verify.py --all` → all green.
