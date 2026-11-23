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
python tools/run_databricks_bundle.py --dry-run
python tools/run_databricks_bundle.py --stages dev,test,prod
python tools/build_expected_counts.py --capture-baseline
```

The driver supplies the recorded owned warehouse ID, validates each bundle,
checks ownership and serverless limits, runs targets sequentially and confirms
the warehouse is stopped after every run.

**Check:** `SELECT COUNT(*) FROM demo_prod.gold.fact_sales_monthly` matches the computed count in `seed/expected_counts.json`. The verifier also compares independent business-row fingerprints, volume checksums, unique grains, managed Delta locations, column comments and absence of UC masks/filters. Dev/test/prod differ only by `env_marker` (makes stage binding visible in the demo).

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

**Automation / human authentication:**
```
python tools/generate_excel.py --dry-run
python tools/generate_excel.py
python tools/prepare_sharepoint_auth.py --dry-run
python tools/prepare_sharepoint_auth.py
python tools/upload_sharepoint.py --dry-run
```
The owned single-tenant public client requests delegated `Sites.Create.All`,
`Sites.Selected` and `User.Read`, without a client secret or tenant-wide site-read
scope. An administrator must consent and complete device-code/MFA sign-in:
`python tools/upload_sharepoint.py --authenticate`.
Then provide the authoritative site URL:
`python tools/upload_sharepoint.py --site-url https://<tenant-host>.sharepoint.com/sites/DemoData`.

The script uses the documented Microsoft Graph beta Create Site operation and
polls `getOperationStatus` before reading back the site. The creating application
receives selected-site access under the documented site-creation flow. Existing
unrecorded sites/files are not overwritten. For an already-existing site, review
and explicitly grant this app selected-site access rather than recreating it.
See [Create site](https://learn.microsoft.com/graph/api/site-post-sites?view=graph-rest-beta)
and [selected permissions](https://learn.microsoft.com/graph/permissions-selected-overview).
If Graph accepts creation without a usable Graph-origin operation URL, the
script records acceptance and verifies named-site/default-drive readiness using
Graph GETs instead; it never forwards credentials to a foreign Location.

**File-protection prerequisite:** locally generated files must remain readable
XLSX containers. If organizational protection wraps them as encrypted Office
files, the uploader stops before authenticating/uploading. Have the data owner
review an appropriate approved classification for the synthetic files; do not
decrypt them, disable protection policies or move them to evade protection.

**Check:** 6 files per stage folder in SharePoint.
Upload verification compares complete worksheet/cell values, not package byte
size (SharePoint can update Office package properties). A repeat run must reuse
the recorded site/files; the December live workbook stays outside upload roots.

---

## Step 5 — Build Fabric items in Dev (UI-first, then Git)

Build in **DEMO-Analytics-Dev** first. Mirrored catalogs, shortcuts, ontology and data agents are most reliable when created through the UI or the documented API, then captured in Git. Copilot helps with notebooks, TMDL and scripts.

### 5.1 Connections (created once, shared by all stages)
- **Azure Databricks workspace** connection `conn-dbw-demo` (organizational account/OAuth2 for the demo; workspace URL, not a Databricks SQL host/httpPath connection; share with `sp-fabric-demo-cicd`).
- SharePoint connection `conn-sp-demodata` (organizational account or workspace identity; service principal requires a **certificate**, not a secret).
- Record both connection IDs in `config/environments.yml`.

Organizational-account connections require interactive Fabric portal authoring:
OAuth2 is not accepted in the public Create Connection REST credential union.
Use Settings → Manage connections and gateways → New → Cloud for the Databricks
workspace connection. For SharePoint, use the SharePoint connection or the
SharePoint Folder shortcut's New connection sign-in flow. Do not substitute
PATs/client secrets. Once authenticated connections exist, automate their
sharing and item binding through the supported APIs.

### 5.2 Mirrored catalog — `MIR_UC_Gold`
Workspace → New item → **Mirrored Azure Databricks catalog** → `conn-dbw-demo` → catalog `demo_dev`, schema `gold` only → keep "automatically sync future catalog changes" → name `MIR_UC_Gold`.
**Check:** SQL analytics endpoint shows all gold tables; `env_marker = 'dev'`.

### 5.3 `LH_Landing` (schemas enabled)
1. New **table shortcut** in schema `forecast` → OneDrive/SharePoint → `conn-sp-demodata` → folder `Forecasts/Dev/standard` → **Transform**: Excel, first row as headers, sheet `Forecast` → name `forecast_standard`. *(Excel transformation = preview)*
2. New **shortcut** under `Files` → `Forecasts/Dev/raw` → name `raw_forecasts` (no transformation).
The raw-file and mirrored Gold schema shortcuts can be created through the
documented REST API. The current public shortcut transform request schema does
not document Excel preview configuration; author that transformation in the UI
instead of guessing a payload, then capture its service definition.
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

NB_Integrate (PySpark, default Starter Pool, no custom Environment):
- Use Spark SQL to join gold.fact_sales_monthly with forecast_clean on
  sku, package_code, region_code, channel_code, month; use PySpark for the Delta write.
- Output LH_Curated table sales_vs_forecast: month, sku, product_name, package_code,
  package_type, channel_code, region_code, partner_id, actual_hl, forecast_hl,
  deviation_hl, revenue_eur, margin_eur, env_marker.
- Lakehouse references must use logical names/IDs that fabric-cicd can re-point
  (document required parameter.yml entries).
Decision reason: "show Spark compatibility for a Databricks audience".
Also add tests in /tests for the pure parsing functions (pytest).
```

### 5.5 `LH_Curated`
- Schema shortcut `gold` → `MIR_UC_Gold` (all gold tables).
- Table shortcut `forecast_clean` → `LH_Landing`.
- Run `NB_Integrate` once → table `sales_vs_forecast`.
- **Enable OneLake security** on `LH_Curated`; keep only the default reader role for now (Act 6 adds roles live).
  Current OneLake documentation provides `DefaultReader` on lakehouses by default.
  Verify its actual policy through `dataAccessRoles`: Read on all data, with virtual
  `ReadAll` membership. Do not invent an enable-setting payload or overwrite a
  customized role. Before the later restricted-role demo, remove unrestricted
  access paths explicitly so additive roles cannot bypass the restrictions.

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

The complete model is authored in modeling MCP and exported to TMDL. Deploy the
exported source using `python tools/bootstrap_sales_model.py --dry-run --refresh`,
then `python tools/bootstrap_sales_model.py --refresh`. The script checks the
F4 capacity and OneLake baseline, preserves existing model/AI state, verifies
Automatic end-user SSO, and resumes recorded refreshes instead of resubmitting.
The calendar is a small imported Power Query table; all business tables use
Direct Lake on OneLake. Deviation sums the grain-level differences where a
forecast exists rather than treating missing forecasts as zero.

Report automation: `tools/generate_sales_report.py --spec <approved-report-spec>`
supports `--dry-run` and generates the two FHD pages using the official report
CLI shell. Validate and review both rendered pages before
`python tools/bootstrap_sales_report.py --render-reviewed`; use `--dry-run`
first. Publication stages only the validated source files, changes the temporary
binding to the existing model's API `byConnection` form, and uses CLI `pack`.
The durable source retains its local `byPath` binding. Accepted report creates
are recorded and resumed rather than submitted again. Preview browser profiles
and local settings are ignored by Git and never included in publication.

**Terminology clarification:** the user places the demo's business synonyms
in `ONT_Business` (Step 5.8). The terminology added in Power BI's Prep data for
AI -> Add AI instructions is useful Copilot guidance, but does not create
ontology synonyms. Preserve that user-authored guidance; do not fabricate
linguistic metadata or modify opaque AI state through TMDL. See the semantic-model
skill's `semantic-model-ai-readiness.md` and the owning `ontology-cli` skill.

### 5.8 `ONT_Business` (Fabric IQ ontology)
Create in UI (ontology skill can script it if supported): entity types **Product, Package, Channel, Region, Partner, SalesPeriod**; bind to gold dims and `sales_vs_forecast`; relationships Product–Package (sold in), Sales–Region, Sales–Channel, Partner–Deliveries; business descriptions for each entity and property. Optionally add a few rules (e.g. "Deviation above 10% = critical").

The installed `ontology-cli` scripts legacy V1 definitions only. Use the
new-experience V2 UI for this demo; do not substitute a V1 item or invent a V2
definition. The supported UI flow is New item -> Ontology (preview), then
Home -> Ontology agent: review the plan and explicitly switch to Act to apply
it. Existing `SM_Sales` tables and measures can be bound through that agent.
Keep partner delivery connections on `LH_Curated.gold.fact_deliveries`,
separate from the sales fact. Add the business synonyms to the ontology;
Power BI AI instructions are not a substitute for these ontology terms.
See the [current ontology tutorial](https://learn.microsoft.com/fabric/iq/ontology/tutorial-1-create-ontology).

### 5.9 `DA_Sales` (data agent)
Source: `ONT_Business` as ontology context only. Do not independently add
`SM_Sales` as a Data Agent source. The report still uses `SM_Sales`; the ontology
uses its own bound underlying sources to execute queries. Instructions (store
in Git with the item):
```
You answer sales and forecast questions for a beverage company.
Volumes are in hectolitres (hl), money in EUR. Months are first-of-month dates.
Use ONT_Business as the only configured agent context source.
Resolve business terms, metrics and query bindings through the ontology.
Query its eligible underlying sources; do not add SM_Sales independently.
Always state the period and filters you used. Never estimate missing values.
```
Add 5 example questions (see `02`, Act 5).

`python tools/bootstrap_dev_context.py --dry-run`, then run without `--dry-run`,
captures the user-created ontology identity and creates the owned Data Agent
draft using the public definition API. It stores global instructions and five
rehearsal questions without changing the model or ontology.
`tools/set_data_agent_ontology_only.py --dry-run`, then run without `--dry-run`,
removes the previously added standalone semantic-model source from the draft
and updates routing while preserving other definition parts and published state.

**Manual - V2 ontology context:** in DA_Sales, Sources -> Add sources ->
Add an ontology -> ONT_Business. Expand it to review the associated sources.
This is context, not a `graph`/GQL query source; do not substitute that legacy
public-definition type or guess an experimental metadata property. Use the
preview runtime for the best documented experience. Sharing the agent does
not grant its source permissions.

The current Ontology integration does not support supplemental context for
Power BI semantic-model sources. Retain the questions in global instructions
and [agent_questions.md](agent_questions.md); do not claim unsupported native
few-shot configuration or pre-tested agent answers.
See [Ontology context in a Data Agent](https://learn.microsoft.com/fabric/data-science/data-agent-ontology-sources).

### 5.10 `VL_Config`
Variables: `catalog` (demo_dev/test/prod), `sp_folder` (Forecasts/Dev|Test|Prod), `env_label`. Value sets: `dev`, `test`, `prod`.

The same bootstrap script creates the public Variable Library definition.
Dev inherits the defaults (no redundant overrides); Test and Prod override
only different values. The active Dev value set is separate workspace item
state, selected through the documented PATCH and checked through the typed
Variable Library GET. Definition requests omit `format`.

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
- Do not update Dev from this Test/Prod workflow.
- job preflight: Azure OIDC, approved app/tenant/repository context checks, read-only
  fabric-cicd dry-runs for the selected stages.
- job deploy-test: needs preflight, environment: test → deploy.py --stage test
  --phase ingest → deploy.py --stage test --phase analytics → verify.py --stage test
  --metadata-only.
- job deploy-prod: needs preflight and successful/skipped deploy-test, environment:
  prod (required reviewer = me) → same metadata-only phases with --approved-prod.
- Add validate_only input: run OIDC preflight but skip both deployment jobs.
- Show metadata scope/binding results and explicitly state that env_marker and
  business-data checks are a separate user-authenticated step, not a successful skip.
Also create .github/workflows/pr-check.yml: on pull_request → existing unittest
suite + the fabric-cicd parameter parser offline for every stage/phase.
```

**Manual (GitHub):** environments `test` and `prod`; `prod` with **required reviewer** (you); secrets/vars: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `FABRIC_CAPACITY_ID` (variables, no client secret). Branch protection on `main`: PR required; allow admins to bypass (needed for reset).

**Approved identity split:** GitHub OIDC uses sp-fabric-demo-cicd for metadata
only. Local changes retain the original three admin-user context checks.
PL_Refresh, model data refresh, row counts, rendered pages and Data Agent answers
remain a separate DEMO-user-authenticated acceptance step. The current Spark SQL
reader does not support service principals. Initial stage mirrors, lakehouses and
transformed shortcuts must exist before OIDC metadata deployment.

**First validation:** `gh workflow run deploy.yml -f stage=prod -f validate_only=true`
does not change any workspace. Normal deployment is `-f stage=both` without
validate_only; approve Prod. Do not dispatch Test deployment during an explicitly
Prod-only rollout.
**Check:** Test shows `env_marker = 'test'`, Prod `'prod'`; reports render; shortcuts point to the stage's own folder/catalog.

For report-only corrections, use `tools/deploy.py --stage test --phase report`
to avoid republishing models, notebooks, ontology, or agent. The report's source
caption is parameterized for Test/Prod. Use `tools/verify.py --stage test
--report-only --report-preview-dir <new-local-report-directory>` to check its
binding/caption and download the deployed PBIR for rendering; this does not
rerun the successful model refresh. Add `--dry-run` for a read-only preflight.
Never unpack over durable source files.

---

## Step 7 — Prod-only: Copilot, Teams, Fabric IQ

Run `python tools/check_copilot_publication.py --dry-run`, then without
`--dry-run`, to verify Prod/F4, existing Fabric publication, viewer-group
memberships and enabled Power BI/Copilot licence plans. This creates no cloud
objects or access grants. Fabric runtime/MCP publication is **not** Agent Store
publication; the remaining M365/Teams actions below are a human checkpoint.
The current publish dialog calls this **Also publish to Microsoft Copilot**;
older documentation calls it **Publish to Agent Store**. Turn the current toggle
on and select **Publish**; do not look for a separate Agent Store button.
Use the configured licensed viewer accounts (`aadik` for North, `andrel` for
South), not the unused initial `demo.north`/`demo.south` placeholders.

1. **Publish `DA_Sales` in Prod** → Publish → **Also publish to Microsoft Copilot**
   = **On**, then **Publish**, with a clear description.
2. M365 Copilot (as you): open DA_Sales → pin; test in Teams. Publication
   does not automatically install the agent for every viewer. From DA_Sales
   in Copilot, use **Share → Copy link**. Open that agent link as the configured
   viewer, select **Add/Open** if offered, and pin it from **Agents**. Searching
   the viewer's installed **Plugins** alone is not a publication check.
   Fabric item/data permissions and Copilot agent distribution are separate.
   If the link requests a new access grant or tenant-policy change, stop for
   approval rather than changing organization-wide settings.
3. **Agent Builder:** New agent "Sales Assistant" → Configure → Work content → turn on **Fabric** (may show as "Power BI") → instructions:
   ```
   Use Fabric to answer business questions with Power BI data the user can access.
   State the data source, filters and period. Don't estimate unavailable values.
   ```
   Share with `SG-Demo-Sales-North`, `SG-Demo-Sales-South`.
4. Verify the configured North/South sales groups have Read on `DA_Sales`,
   `ONT_Business`, `SM_Sales` and `RPT_Sales` (workspace Viewer covers this).
   For this semantic-model-backed ontology, the groups also need **Build on
   `SM_Sales`** to query through the ontology, including its entity instances.
   This is distinct from direct Data Agent semantic-model access, for which
   Read alone suffices. New grants require explicit approval.

**Check:** in a separate session as the configured North viewer (`aadik`),
`@DA_Sales What was actual volume by region in October 2026?` returns all
four baseline regions (before the live North-only role is added). Do not
change the automation's Azure/Fabric/GitHub administrator sign-ins to perform
this viewer check. Verify `Sales Assistant` uses the Fabric/Power BI capability;
it is separate from the ontology-only `DA_Sales` and does not change its source.

Workspace Viewer/model Read alone does not grant Direct Lake SSO source-data
access. Before accepting this check, inspect `LH_Curated` OneLake role
membership and the source shortcut permissions. Run
`python tools/check_copilot_publication.py --model-access-only --dry-run`
for a read-only diagnostic; it does not impersonate the viewer or grant access.
Any required new data-access grant needs explicit approval. Do not grant Build
solely to address a generic Copilot error, promote the workspace role, disable SSO,
or rebind the model merely because
Copilot describes the source as on-premises. A successful administrator query
does not validate the viewer's access.

The approved initial baseline membership grant is implemented by
`python tools/grant_baseline_readers.py --dry-run`, then
`python tools/grant_baseline_readers.py --approved-prod-baseline-read`.
It adds only the North/South sales groups to Prod Curated DefaultReader,
preserves other members/policies, and protects the update with the collection
ETag. It never grants workspace Contributor, model Build or write access.
Before Act 6, remove North's unrestricted membership so it cannot override
the restricted role. Always verify the real viewer session after a grant.

For the separately approved ontology-bound model permission, run
`python tools/grant_ontology_readers.py --dry-run`, then
`python tools/grant_ontology_readers.py --approved-prod-ontology-build`.
It grants only the two sales groups Read+Build (`ReadExplore`) on Prod
`SM_Sales`, retains workspace Viewer and refuses unexpected existing grants
rather than overwriting them. Build also enables authoring reports and Analyze
in Excel, subject to existing data security; it is not model Write or Reshare.
See the explicit Read+Build query requirement in
[Generate ontology from semantic models](https://learn.microsoft.com/fabric/iq/ontology/how-to-generate-from-semantic-models).
After propagation, verify `ONT_Business` -> `SalesPeriod` -> **Instances** as
the North viewer, then retry the published `DA_Sales` question. An API permission
readback or an administrator answer alone does not complete this check.

---

## Step 8 — Partner domain and cross-tenant sharing

**Copilot prompt**
```
Create in /partner (separate fabric-cicd folder, deployed manually) for DEMO-Partner-A:
- LH_PartnerA as an output-only lakehouse, with no internal source shortcuts.
- NB_Partner_Extract (Python notebook) reads the existing internal Gold shortcuts
  gold.fact_deliveries and gold.dim_product through Prod LH_Curated, then writes LH_PartnerA table
  partner_a_deliveries
  (only partner_id = 'P-A', columns: month, sku, product_name, package_code, region_code,
  delivered_hl, on_time_pct). No margin or revenue columns.
- Files/context/partner_glossary.md with business definitions (hl, package codes, on-time %).
```

The output-only layout is explicitly approved. The earlier prompt's
`sales_vs_forecast` source has no delivery measures; do not infer deliveries
from sales or multiply the sales grain through delivery joins. Keep input
shortcuts in the internal Prod item, which is not modified by the extraction.
IQ Sharing shares an **entire item** and ignores its OneLake security roles,
so unfiltered inputs must never be placed in `LH_PartnerA`.

Run `python tools/bootstrap_partner.py --dry-run --run`, then
`python tools/bootstrap_partner.py --run` locally as the verified DEMO admin.
The separate `partner/` source folder is not in the metadata CI deployment.
Initial acceptance requires 1,232 P-A rows and 1,121,803.72 hl, Jan 2025-Oct 2026,
the exact seven-column schema and exact persisted Delta row/glossary readback.
Later source updates still require the exact filtered projection but aren't
forced to retain the original baseline count.

**Manual**
1. **Option A (B2B guest):** invite `partner.user@<tenantB>` as guest to tenant A → Viewer on `DEMO-Partner-A` → enable OneLake security on `LH_PartnerA`, role `Partner_A_Read` (tables `partner_a_deliveries` only). Test once in a private browser window.
2. **Option B (IQ Sharing, preview):** keep for live (Act 7). Pre-check only: tenant A can create Shares, tenant B can accept; `PARTNER-Inbound` exists in tenant B.
3. Do a full dry run of Option B once, then delete Share + Share Subscription (see `03`).

For IQ Sharing, create **+ New item -> Share (preview)** and select the whole
output-only `LH_PartnerA`. This is not the lakehouse's ordinary **Share** action.
Tenant B needs its own acceptance and inbound lakehouse shortcuts to the
Mirrored OneLake item before notebook/semantic-model consumption.
Tenant settings, invitations and any new access grants require explicit
approval; do not switch the automation's tenant-A CLI identity to tenant B.
References: [IQ Sharing overview](https://learn.microsoft.com/fabric/onelake/iq-share/onelake-share-overview)
and [Create a Share](https://learn.microsoft.com/fabric/onelake/iq-share/create-share).

The producer Share now has a documented public API. Set the private recipient
UPN in the local environment variable named by `partner.recipient_upn_env`;
do not commit that address or the invitation URL to this public repository.
After explicit approval, use:

```powershell
python tools\manage_partner_share.py create --expires-utc 2026-11-30T23:59:59Z --dry-run
python tools\manage_partner_share.py create --expires-utc 2026-11-30T23:59:59Z --approved-external-share
python tools\manage_partner_share.py status
```

Choose a new approved future expiration for later rehearsals. The script
inventories the whole OneLake Tables/Files trees, rejects extra data or files,
checks the exact glossary text, and reads back the Share's exact asset,
recipient and expiration. No source OneLake role is treated as an IQ Share
filter. The ordinary List Tables API rejects schema-enabled lakehouses;
the physical OneLake inventory avoids that unsupported operation.

Tenant B accepts using the invited identity; do not change the tenant-A CLI.
After the consumer query and revocation rehearsal, explicitly approved cleanup
uses `python tools\manage_partner_share.py delete --approved-rehearsal-cleanup`.
It deletes only the recorded owned rehearsal Share and verifies its absence.
The tenant-B operator separately deletes only the rehearsal Share Subscription
and its associated newly created Mirrored OneLake item. Never delete an
existing inbound workspace or unrelated tenant-B content.
API references: [Create Share](https://learn.microsoft.com/rest/api/fabric/share/items/create-share)
and the [public Share definition schema](https://developer.microsoft.com/json-schemas/fabric/item/share/definition/share/1.0.0/schema.json).

---

## Step 9 — Baseline and recordings

1. Capture the actual baselines, with `--dry-run` first:
   `python tools/export_roles.py` writes `config/onelake_roles.baseline.json`
   for all stage Landing/Curated/mirror items plus the partner lakehouse;
   `python tools/build_manifest.py` writes the actual 18-file `seed/manifest.json`.
   Existing different baselines are never silently overwritten.
2. Keep the independently generated and verified `seed/expected_counts.json`.
   Commit/push the tooling, snapshots and readiness log before Git sealing.
3. Run `python tools/prepare_fallback.py --dry-run`, then without `--dry-run`.
   This validates the Forecast Accuracy formula with three nonpersistent DAX
   cases, creates/pushes `demo/forecast-accuracy-prepared` and
   `demo-prepared-change`, and changes only the local prepared model measure
   and draft Data Agent instructions. It does not deploy to any workspace.
   The optional model AI-schema synonym is a user Prep data for AI action,
   not a fabricated serialized synonym.
4. Record each act as fallback, especially Acts 3, 5 and 7. **For this build,
   the user explicitly skipped recordings.** Do not claim that videos exist.
5. Run `python tools/verify.py --all --dry-run --seal`, then
   `python tools/verify.py --all --seal`. Full live checks happen **before**
   creating/pushing `demo-baseline`; no existing different tag is overwritten.
   The verifier never deploys, refreshes Fabric data or changes access. It
   reads actual Gold fingerprints, files, roles, bindings, model measures,
   physical SQL counts/checksums and partner state. Its owned Databricks
   verification warehouse is stopped afterward.
6. Later use `python tools/verify.py --all` for the same read-only pre-session
   checks, including `main == demo-baseline`, no open PRs and prepared refs.
   The final verifier prints its audit to stdout rather than changing the
   worktree after sealing.

The one-command reset toolkit in `03-reset.md` remains a separate specification,
not an implemented or rehearsed command. Baseline capture, prepared fallback,
aggregate verification and scoped IQ Share cleanup are implemented.
