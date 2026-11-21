# Fabric + Databricks Demo Kit — Overview

Reusable demo environment: **Azure Databricks (3 environments) + Microsoft Fabric (3 environments) + GitHub CI/CD + Fabric IQ + cross-tenant partner sharing.**
First use: Gerolsteiner workshop (Fabric vs. Databricks). Customer-specific content lives only in the sample data and `config/demo_profile.yml`, so the kit can be reused.

| File | Purpose | Audience |
|---|---|---|
| `00-README.md` | Architecture, naming, prerequisites, status of preview features | You |
| `01-base-setup-copilot.md` | Step-by-step build instructions and prompts for GitHub Copilot (agent mode + Skills for Fabric) | You + GitHub Copilot |
| `02-demo-script.md` | Live demo: acts, clicks, talk track, fallbacks | Presenter |
| `03-reset.md` | Reset scripts and procedure after each rehearsal | You + GitHub Copilot |
| `04-sample-data.md` | Data model, seed data, messy Excel files, demo change rows | You + GitHub Copilot |

---

## 1. Storyline (7 acts, ~50 min)

| # | Act | Key message | Status of features used |
|---|---|---|---|
| 1 | Sources: mirrored Unity Catalog + SharePoint Excel | Zero-copy into OneLake; Databricks stays the engineering platform | Mirrored Azure Databricks catalog: GA · SharePoint shortcut: GA · Excel shortcut transformation: **preview** |
| 2 | Integrate + Direct Lake report | Gold + forecast → curated table → Direct Lake, no import refresh | GA |
| 3 | Code-first with GitHub Copilot | AI writes code, humans review in a PR | Skills for Fabric: open source (MIT), not a supported product |
| 4 | CI/CD Dev → Test → Prod | Item definitions move, data does not; each stage binds to its own sources | fabric-cicd: open source · semantic model/report in deployment pipelines list: **preview** |
| 5 | Fabric IQ: ontology, data agent, Teams/M365 Copilot | One semantic layer for reports, agents and Copilot | Data agent: GA · Fabric capability in M365 Agent Builder: GA · Ontology: **check status** |
| 6 | OneLake security (RLS/CLS) | One rule, enforced in report, SQL and Copilot | Check status in tenant |
| 7 | Partner domain + IQ Sharing (cross-tenant) | Partner works in own tenant, no B2B guest | IQ Sharing: **preview** |

Optional (dropped for now): Power BI data app.

---

## 2. Architecture

```
┌──────────────────────── AZURE (tenant A) ───────────────────────────────┐
│ rg-demo-databricks                                                        │
│  • ADLS Gen2  stdemolake<suffix>  (containers: uc-dev, uc-test, uc-prod)  │
│  • Access Connector for Azure Databricks (managed identity)               │
│  • Azure Databricks workspace (Premium)  dbw-demo                         │
│     Unity Catalog metastore (external data access ENABLED)                │
│       demo_dev  ─┐   schemas: bronze → silver → gold                       │
│       demo_test ─┼─  managed location = own ADLS container (NOT default    │
│       demo_prod ─┘   storage), no row filters / column masks on gold      │
│     Databricks Asset Bundle: jobs seed_data + build_medallion (dev/test/prod)
└───────────────┬─────────────────────────────────────────────────────────┘
                │ Mirrored Azure Databricks catalog (metadata + shortcuts, zero copy)
┌───────────────▼──────────────── FABRIC (tenant A, F4) ───────────────────┐
│ Domain "Demo Analytics"                                                   │
│  DEMO-Analytics-Dev  ◄─ Git integration (branch main, folder /fabric)     │
│  DEMO-Analytics-Test ◄─ GitHub Actions + fabric-cicd                       │
│  DEMO-Analytics-Prod ◄─ GitHub Actions + fabric-cicd (+ approval)          │
│                                                                           │
│  Items in EACH stage workspace (bound to that stage's sources):           │
│   MIR_UC_Gold      → demo_<stage>.gold                                    │
│   LH_Landing       → shortcut SharePoint /Forecasts/<Stage>/standard      │
│                       (+ Excel shortcut transformation → forecast_standard)│
│                    → shortcut SharePoint /Forecasts/<Stage>/raw (files)    │
│   NB_Clean_Forecast (Python notebook: messy Excel → forecast_clean)       │
│   LH_Curated       → schema shortcut to MIR_UC_Gold tables                │
│                       + table sales_vs_forecast  (OneLake security roles) │
│   NB_Integrate     (gold + forecast → sales_vs_forecast)                  │
│   PL_Refresh       (NB_Clean_Forecast → NB_Integrate)                     │
│   SM_Sales         (Direct Lake on LH_Curated) → RPT_Sales                │
│   ONT_Business     (Fabric IQ ontology) → DA_Sales (data agent)           │
│   VL_Config        (variable library: value sets dev / test / prod)       │
│                                                                           │
│  Prod only: DA_Sales published → Agent Store → M365 Copilot / Teams       │
│             SM_Sales used by Fabric capability in M365 Agent Builder      │
│                                                                           │
│ Domain "Demo Partners"                                                    │
│  DEMO-Partner-A:  LH_PartnerA  (table partner_a_deliveries, filtered,     │
│                   built from Prod LH_Curated by NB_Partner_Extract)       │
│                   Files/context/partner_glossary.md                       │
│    ├─ Option A: B2B guest (Viewer) + OneLake security role                │
│    └─ Option B: IQ Share ───────────────┐                                 │
└─────────────────────────────────────────┼────────────────────────────────┘
 SharePoint site "DemoData": /Forecasts/{Dev,Test,Prod}/{standard,raw}
                                          ▼
┌──────────────── FABRIC (tenant B = partner) ───────────────┐
│ Workspace PARTNER-Inbound: Share Subscription               │
│   → Mirrored OneLake item (read-only shortcuts, zero copy)  │
└─────────────────────────────────────────────────────────────┘

GitHub repo fabric-demo-platform:
  feature branch ─PR→ main ─► Dev (Update from Git) ─► Test ─approval─► Prod
```

### Design rules (explain these in the demo)

1. **CI/CD moves item definitions, never data.** Each stage reads its own sources (`demo_<stage>` catalog, `/Forecasts/<Stage>` folder).
2. **Mirroring and shortcuts are zero copy.** Materialized per stage are only: the Excel-transformed table, `forecast_clean` and `sales_vs_forecast` (small, deliberate isolation).
3. **No Unity Catalog row filters / column masks on gold.** Tables with RLS/CLM policies are not mirrored. Security is applied in OneLake security instead (Act 6).
4. **Consumers (Copilot, Teams, partners) connect to Prod only.**

---

## 3. Naming convention (generic, reusable)

| Object | Name |
|---|---|
| Fabric domains | `Demo Analytics`, `Demo Partners` |
| Stage workspaces | `DEMO-Analytics-Dev`, `DEMO-Analytics-Test`, `DEMO-Analytics-Prod` |
| Partner workspace (tenant A) | `DEMO-Partner-A` |
| Consumer workspace (tenant B) | `PARTNER-Inbound` |
| Databricks catalogs | `demo_dev`, `demo_test`, `demo_prod` |
| SharePoint site / folders | `DemoData` / `Forecasts/{Dev,Test,Prod}/{standard,raw}` |
| GitHub repo | `fabric-demo-platform` |
| Service principal | `sp-fabric-demo-cicd` |
| Entra groups | `SG-Demo-Fabric-Admins`, `SG-Demo-Sales-North`, `SG-Demo-Sales-South`, `SG-Demo-Fabric-API` |
| Test users (tenant A) | `demo.north@<tenantA>`, `demo.south@<tenantA>` |
| Partner user (tenant B) | `partner.user@<tenantB>` |
| Items | `MIR_UC_Gold`, `LH_Landing`, `LH_Curated`, `NB_Clean_Forecast`, `NB_Integrate`, `PL_Refresh`, `SM_Sales`, `RPT_Sales`, `ONT_Business`, `DA_Sales`, `VL_Config` |

Customer branding (company name, product names, language of report titles) comes from `config/demo_profile.yml` and the seed data only.

---

## 4. Prerequisites checklist

**Tenant A (Microsoft)**
- [ ] Fabric capacity **F4** assigned to all `DEMO-*` workspaces. Consider scaling to F16+ on demo day (Spark on F4 is small) and pausing afterwards.
- [ ] Microsoft 365 Copilot licence for you, `demo.north`, `demo.south`.
- [ ] Power BI **Pro** (or E5) for every user who opens reports — capacity is below F64, so viewers need Pro.
- [ ] Azure subscription (Owner or Contributor + User Access Administrator) to create Databricks, storage, access connector.
- [ ] Entra: permission to create app registration `sp-fabric-demo-cicd`, security groups, test users, B2B invitation.
- [ ] SharePoint: site `DemoData`.
- [ ] Fabric admin rights for tenant settings (see `01`, step 2).

**Tenant B (partner)**
- [ ] Fabric-enabled user `partner.user@<tenantB>` and a workspace `PARTNER-Inbound` on capacity or trial (verify capacity requirement for IQ Sharing consumers).
- [ ] Fabric admin in tenant B enables external data sharing / IQ Sharing acceptance.

**GitHub**
- [ ] Organisation or account that supports **Environments with required reviewers** for the repo visibility you use (private repos may require a paid plan — check before building).
- [ ] GitHub Copilot (agent mode) in VS Code.

**Local machine**
- [ ] VS Code, GitHub Copilot, Python 3.11+, Azure CLI, Databricks CLI (bundles), GitHub CLI `gh`, Fabric CLI (`fab`), Git.
- [ ] Skills for Fabric installed (see `01`, step 0).

---

## 5. Things to verify before building (status changes fast)

| Item | Why it matters | Where to check |
|---|---|---|
| fabric-cicd support for `MirroredAzureDatabricksCatalog`, `Ontology`, `DataAgent`, lakehouse shortcuts | Decides whether an item is deployed by fabric-cicd or by the post-deploy script | fabric-cicd docs → Item Types |
| `find_replace` on lakehouses | Older fabric-cicd versions don't apply `find_replace` to lakehouses; shortcut publish is behind `enable_shortcut_publish` | fabric-cicd docs |
| Direct Lake + OneLake security | RLS in Act 6 must reach the report → model must use Direct Lake **on OneLake** with user identity (SSO) | Learn: Direct Lake + OneLake security |
| OneLake security bypass | Workspace Admin/Member/Contributor bypass OneLake security → test users must be **Viewer** | Learn: OneLake security |
| Data agent in M365 Copilot prerequisites | F2+, cross-geo tenant settings, same tenant/same account | Learn: Consume a data agent from Microsoft Copilot |
| IQ Sharing | Preview, required expiration date, supported item types | Learn: IQ Sharing overview |
| Excel shortcut transformation | Preview; requires **homogeneous** files in the folder | Learn: Shortcut transformations (file) |
