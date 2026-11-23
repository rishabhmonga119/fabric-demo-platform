# Demo environment build log

## 2026-11-21 - Step 0: workstation, repository and guardrails

Status: COMPLETE. Step 0 commit pushed and remote HEAD verified.
No cloud resources created or modified.

### Inputs and context

- Read docs/00-README.md through docs/04-sample-data.md in full.
- `az account show --output json`: PASS. Active administrator is
  `admin@caldova30465160.onmicrosoft.com`.
- Azure tenant ID: `5c41223c-f1f5-4979-930f-d5f3c72353f9`.
- Azure subscription ID: `61ab2275-fb68-4081-ac0f-076c87caf0c1`.
- Verified the tenant domain with the read-only Graph request
  `az rest --method get --resource https://graph.microsoft.com --url
  'https://graph.microsoft.com/v1.0/organization?$select=id,displayName,verifiedDomains'`.
  The verified initial domain is `caldova30465160.onmicrosoft.com`.
- `fab auth status`: BLOCKED initially; `fab` is not installed/on PATH.
- `gh auth status`: command not on PATH. Retried with the existing executable
  `C:\Program Files\GitHub CLI\gh.exe`; PASS, active account `rishabhmonga119`.
- Read-only `gh repo view rishabhmonga119/fabric-demo-platform --json
  nameWithOwner,visibility,defaultBranchRef`: PASS; PUBLIC, owner
  `rishabhmonga119`, default branch `main`.
- `git status --short`: initial worktree clean. Initial HEAD `40d58a3`.
- Installed Fabric skills verified in
  `~\.copilot\installed-plugins\fabric-collection\fabric-skills\skills`
  and `~\.copilot\installed-plugins\fabric-collection\powerbi-authoring\skills`.

### Local changes and decisions

- Created the generic repository skeleton, Copilot guardrails, dependency
  manifest, local setup script and non-secret environment configuration.
- Existing Azure IDs came from the verified context; resource IDs not yet
  discovered remain explicit `null` placeholders.
- Use a repository-local `.venv` instead of changing shared/global Python.
- Installed Python is 3.13.14, satisfying the documented 3.11+ prerequisite;
  scripts remain compatible with Python 3.11.
- Fabric CLI's documented package is `ms-fabric-cli`, not
  `microsoft-fabric-cli`. The latter is not installed.
- Skill/reference: `e2e-medallion-architecture/SKILL.md`, and the shared
  `fabric-skills/common/COMMON-CLI.md` authentication and attribution sections.
- Official installation reference: https://microsoft.github.io/fabric-cli/.
- Official authentication reference:
  https://microsoft.github.io/fabric-cli/examples/auth_examples/.
- Ran `python infra/prepare_workstation.py --dry-run`, then
  `python infra/prepare_workstation.py`: PASS; local environment created.
- Re-ran the installer after adding the Databricks CLI: PASS, existing packages
  unchanged; `pip check` reports no broken requirements.
- Installed `ms-fabric-cli` 1.9.0, `azure-identity` 1.27.0 and PyYAML 6.0.3.
  `fabric-cicd` 1.4.0 was installed as a Fabric CLI dependency.
- Databricks CLI 1.27.0 installed locally from the official Windows archive;
  SHA256 verified against official release metadata:
  `335cf6b28397eb0b45880a9abf86c7016210ff6e40276fb82a7d855055a0e590`.
- Added `tools/check_context.py` and the shared fail-closed mutation helper.
- `fab auth status`: PASS after installation; an existing cached login already
  matches `admin@caldova30465160.onmicrosoft.com`, tenant
  `5c41223c-f1f5-4979-930f-d5f3c72353f9`. No login/context switch was needed.
- `python tools/check_context.py --dry-run`: PASS for all three identities.
- `python -m py_compile infra/prepare_workstation.py`: PASS.
- Parsed both configuration YAML files and checked stage bindings and generic
  branding: PASS.
- `git diff --check`: PASS.
- Read-only Step 1 preflight: `az group exists --name rg-demo-databricks` is
  false; `az resource list --resource-type Microsoft.Databricks/workspaces`
  returns no workspaces; `az bicep version` is 0.49.2.
- Documentation requests to `/installation/` and `/authentication/` returned
  404; the home page and `/examples/auth_examples/` provide the official recipes.

### Check

- Repository already exists publicly: PASS.
- Copilot instructions and skeleton: PASS.
- Fabric shortcut skill reference: shared
  `fabric-skills/common/COMMON-CLI.md`, "OneLake Shortcuts / Create a Shortcut";
  `e2e-medallion-architecture` owns layered platform setup.
- Local setup and Fabric identity verification: PASS.
- `python -m unittest discover -s tests -p test_context.py -v`: PASS (4 tests;
  Azure mismatch, Fabric missing/duplicate/mismatched identity, GitHub wrong or
  inactive identity, and no writes during dry-run).
- Re-ran `prepare_workstation.py --dry-run` after installation: PASS; existing
  Databricks version recognised and no virtual environment recreated.
- Compile-check of all three automation modules: PASS.
- Added `tools/commit_step.py`: explicit paths only, expected branch/remote,
  fail-closed context before each mutation, co-author trailer, dry-run and remote
  HEAD verification.
- Commit/push will use `python tools/commit_step.py --step 0 --message
  "bootstrap guarded demo repository and local tooling" --paths ...`.
- Commit and remote HEAD check: pending execution below.
- First commit attempt was blocked before staging by an intermittent
  `fab auth status` error, "Failed to decode JWT token". No files were staged,
  committed or pushed by the failed attempt.
- Immediate read-only recheck of all contexts succeeded, including Fabric.
  The active identities were unchanged; no logout or login was performed.
- Retried the guarded commit without changing credentials: PASS.
- Commit: `3ac4a68d57efb2a727cf8f252ea56f4c3e3bdf3a`,
  `step 0: bootstrap guarded demo repository and local tooling`.
- Push and read-only `git ls-remote` check: PASS; remote `main` matches local HEAD.

## 2026-11-21 - Step 1: Azure Databricks infrastructure

Status: COMPLETE. Azure, external-access, explicit grants and physical managed-storage
checks passed for Dev, Test and Prod. The owned verification warehouse is stopped.

- Read official Microsoft Learn resource schemas for storage accounts and
  containers (2023-05-01), access connectors (2023-05-01), role assignments
  (2022-04-01), and Databricks workspaces (2024-05-01).
- Read the official Azure workspace quickstart Bicep, Unity Catalog workspace
  enablement, and managed-identity storage configuration documentation.
- Added `infra/databricks.bicep`, `infra/deploy.py` and its PowerShell wrapper.
- Plan: one Premium `dbw-demo`, ADLS Gen2 `stdemolake<deterministicSuffix>`,
  containers `uc-dev`, `uc-test`, `uc-prod`, and access connector `ac-dbw-demo`.
- New resources carry ownership tags. Incremental deployments cannot delete
  orphans; unowned existing resources cause an explicit stop.
- Public network access is enabled for demo-only access; anonymous blob access
  remains disabled. No paid networking services, extra workspace or compute
  are explicitly provisioned. Databricks creates its required managed resources.
- Unity Catalog is requested with the documented `defaultCatalog.initialType`
  value `UnityCatalog`; actual metastore configuration will be checked afterwards.
- Existing Fabric F4 capacity is untouched.
- `az bicep build --file infra/databricks.bicep --stdout`: PASS; no generated
  template file left in the repository.
- Python compile-check and 4 context safety tests: PASS.
- `infra/deploy.ps1 --dry-run`: PASS; ownership/context/cost preflight succeeded;
  printed only the resource-group and incremental deployment commands.
- Actual deployment: starting. No resource deletions or cleanup are authorised.

- First provider validation failed for storage, access connector and workspace:
  `RequestDisallowedByAzure`, West Europe is not accepting new customers.
  No paid resource deployment was submitted.
- Created resource group ID:
  `/subscriptions/61ab2275-fb68-4081-ac0f-076c87caf0c1/resourceGroups/rg-demo-databricks`.
  Its metadata location remains West Europe; resource locations can differ.
- Read https://aka.ms/locationineligible (official ARM troubleshooting).
  It identifies West Europe as restricted and recommends an alternative region.
- Provider preflight found `Microsoft.Databricks` NotRegistered and
  `Microsoft.Storage` Registered. Added explicit, guarded provider registration.
- Alternative region selected: North Europe, supported by both providers;
  keeps resources in the EU. Fabric capacity remains unchanged.
- Added `--region` override; the selected region is persisted with successful
  deployment outputs. Existing owned resource group is reused, not recreated.
- Attempting the documented region remedy with prerequisite registration.

- North Europe provider validation: PASS. `Microsoft.Databricks` registered.
- Incremental deployment failed with `InvalidInitialCatalogName`: the live
  service does not support a custom initial catalog name despite the schema
  exposing that optional field.
- Removed only the optional `defaultCatalog.initialName`; kept the documented
  `initialType: UnityCatalog`. Stage catalogs are created explicitly later.
- Added partial-deployment ID persistence for future failed/cancelled ARM runs;
  no created resources are deleted. Retrying reuses owned resources.
- Read-only failed-operation inspection confirmed that storage, all three
  containers, access connector and its RBAC grant succeeded; workspace failed
  before creation. Retry creates only the missing workspace.
- Minimal Bicep fix compile-check and North Europe dry-run: PASS.
- Read the official Databricks Azure CLI authentication guide and Unity Catalog
  metastore, storage credential, catalog and grants API schemas. The documented
  metastore flag is `external_access_enabled` / CLI `--external-access-enabled`.
- Added `tools/check_databricks.py` for read-only, explicitly Azure-CLI-authenticated
  identity/metastore/compute preflight after the Azure deployment completes.
- No Databricks login prompt, SQL warehouse, job cluster or table has been created.

- North Europe retry succeeded. Deployment outputs were persisted in
  `config/environments.yml` and recorded below by the deploy script.
- First Databricks read-only identity check failed during automatic tenant
  discovery: `azure-cli auth: load tenant id: parse "": empty url`.
- Read the official unified-authentication environment-variable reference and
  upstream Azure CLI authentication implementation. Added the documented
  `ARM_TENANT_ID` and `ARM_ENVIRONMENT=PUBLIC` to the child-process environment;
  no global authentication/configuration or tokens are changed.
- Read-only `az databricks workspace show` needed an uninstalled Azure extension
  and failed at a noninteractive installation prompt. No extension was installed;
  use core `az resource show` instead.
- Explicit tenant configuration fixed the tenant-discovery failure, but
  Databricks now reports `Did not find workspace with specified org ID:
  7405618307807698` during the read-only current-user call.
- Core `az resource show` confirms workspace provisioning `Succeeded`, SKU
  `premium`, region `northeurope`, and URL
  `https://adb-7405618307807698.18.azuredatabricks.net`.
- `az storage container-rm list`: PASS, `uc-dev`, `uc-test`, `uc-prod`;
  all have public access `None`.
- Readiness remedy: bounded, read-only retry for new workspace registration;
  no retry on any different authentication/context error.
- Storage RBAC read-only check: PASS, access connector principal
  `bc435bde-5ec3-4da6-bb00-6dca87807b91` has Storage Blob Data Contributor on
  the demo account. HNS is enabled and anonymous blobs are disabled.
- Exact post-deployment check found `publicNetworkAccess=Disabled`, despite
  the Bicep setting `Enabled`. Added ownership-checked, idempotent reapplication
  and verification of this demo-only setting; anonymous blobs stay disabled.
- Added `--repair-network-only` to fix/check that setting without redeploying.
- Prepared direct `az rest` current-user diagnostic using the documented SCIM
  Me endpoint and Azure Databricks audience, avoiding SDK tenant/host discovery.
  No bearer token is printed, stored or passed on the command line.
- Databricks access attempts:
  1. Explicit `ARM_TENANT_ID` and `ARM_ENVIRONMENT=PUBLIC` with Azure CLI
     authentication: tenant-discovery error resolved, but workspace org ID
     `7405618307807698` is still not found.
  2. `python tools/check_databricks.py --dry-run --wait-ready 300`:
     FAIL after bounded readiness retries with the same workspace-not-found error.
  3. `python tools/check_databricks.py --rest --dry-run`: FAIL with the same
     error using the documented direct REST current-user endpoint.
- `infra/deploy.ps1 --repair-network-only --dry-run`: PASS, no writes.
- `infra/deploy.ps1 --repair-network-only`: command completed, but exact
  read-back still showed `publicNetworkAccess=Disabled`; check FAIL.
  Anonymous blob access remains disabled. No policy has been disabled or bypassed.
- Storage network check error now reports the actual observed values rather
  than incorrectly implying anonymous blob access was enabled.
- Stopping resource changes at the human checkpoint; no Databricks catalog,
  schema, job, cluster, table or SQL warehouse was created by this automation.

### Step 1 Check

- One Premium Databricks workspace provisioned in North Europe: PASS.
- ADLS Gen2/HNS, three private containers, managed identity and storage grant: PASS.
- Required public storage endpoint: FAIL (still Disabled).
- Databricks current-user/metastore access: FAIL (workspace org ID not found).
- `SHOW GRANTS ON SCHEMA demo_dev.gold` / `EXTERNAL USE SCHEMA`: BLOCKED;
  catalog/schema creation cannot run before workspace API access succeeds.
- `__unitystorage` after the first managed table: BLOCKED; no table created.
- Overall Step 1: BLOCKED, not green. Existing Fabric F4 capacity is unchanged.

### Human checkpoint and continuation

1. In Azure portal, open `rg-demo-databricks` -> `dbw-demo` -> Launch Workspace
   while signed in as `admin@Caldova30465160.onmicrosoft.com`.
2. Complete any first-launch, MFA or consent prompt. Confirm the workspace home
   opens at `https://adb-7405618307807698.18.azuredatabricks.net`.
3. Reply `done` once it opens; if it still fails, provide the displayed error
   instead. Do not send passwords, tokens or screenshots containing secrets.

After `done`, reverify all three contexts and Databricks access, resolve the
storage endpoint check, finish Unity Catalog setup and Step 1 checks, then
continue Steps 2-9 in order.

### Checkpoint validation and persistence

- `python -m unittest discover -s tests -p 'test_*.py' -v`: PASS (7 focused
  context, ownership, dry-run and network read-back safety tests).
- Python compile-check of all six automation entry/helper modules: PASS.
- `az bicep build --file infra/databricks.bicep --stdout`: PASS.
- `git diff --check`: PASS. Worktree contains only this step's intended changes.
- Persist the partial step with `tools/commit_step.py --step 1 --message
  "provision guarded Azure infrastructure and record blocked checks"`, explicit
  changed paths, fresh context checks, co-author trailer and verified push.
  This is a blocked checkpoint commit, not a claim that Step 1 is complete.
- Checkpoint commit `047fa13c9890b321fb0902a62f36c919459121a0` pushed:
  PASS; remote `main` equals local HEAD. Worktree was clean after the push.
- Updating this log with the verified checkpoint commit before requesting the
  human action; the log-only update is committed separately.

### First-launch checkpoint completed

- User replied `done` to the first interactive launch checkpoint.
- `python tools/check_databricks.py --dry-run`: PASS for all three contexts
  and Databricks identity `admin@caldova30465160.onmicrosoft.com`.
- Unity Catalog assignment confirmed: workspace `7405618307807698`,
  metastore `63247cf6-7207-4507-8329-1310ece4d4e7`,
  default catalog `dbw_demo`, metastore name `metastore_azure_northeurope`.
- Metastore `external_access_enabled` is false. It was automatically provisioned,
  not explicitly created by this script; request approval before changing it.
- Auto-provisioned `Serverless Starter Warehouse` ID `8cf2dc575a41aa17` is
  STOPPED, serverless, auto-stop 10 minutes. It is not modified or started.
  Any compute created by this automation must have the requested 15-minute
  auto-stop setting.
- Added the official ARM PATCH alternative for storage network repair
  (`--network-method arm`); payload is limited to `publicNetworkAccess=Enabled`.
  It uses a temporary non-secret body file and verifies the resulting state.

### Remaining Step 1 checkpoint

- `python -m unittest discover -s tests -p test_infra.py -v`: PASS (3 network
  safety tests before the ARM diagnostic).
- `infra/deploy.ps1 --repair-network-only --network-method arm --dry-run`: PASS.
- `infra/deploy.ps1 --repair-network-only --network-method arm`: PATCH completed,
  but exact read-back is still `publicNetworkAccess=Disabled`,
  `allowBlobPublicAccess=False`; check FAIL.
- Three distinct implementations now leave the required public endpoint
  disabled: Bicep deployment, storage CLI update, and direct ARM PATCH.
  Stop rather than retrying again or bypassing any policy.
- Databricks workspace API access is now PASS after the user's first launch.
- Human action: verify/save public network access for the created demo storage
  account in Azure portal (or report a policy/error if it cannot remain enabled).
  Keep anonymous blob access disabled; do not disable an organisation policy.
- Human authorisation: approve changing only `external_access_enabled` on the
  automatically provisioned metastore `63247cf6-7207-4507-8329-1310ece4d4e7`.
  The script will perform the documented CLI change after explicit approval;
  no existing metastore setting has been changed yet.
- No catalog/schema/table or compute created by this automation; starter
  warehouse remains untouched. Step 1 stays BLOCKED and Steps 2-9 are pending.

### Approved storage-policy exceptions

- User reported that public network access is disabled by policy and explicitly
  requested an exception, then expanded this to all storage accounts.
- Clarification confirmed scope `existing-subscription`: all existing storage
  accounts in verified subscription `61ab2275-fb68-4081-ac0f-076c87caf0c1`;
  not future accounts and not tenant-wide.
- User also approved enabling external data access on the identified metastore.
- Read official policy exemption CLI documentation and exemption structure.
- Policy Insights identified the actual Modify rule that forces
  `Microsoft.Storage/storageAccounts/publicNetworkAccess` to `Disabled`.
- Assignment: management-group `MCAPSGovDeployPolicies`; definition:
  `StorageAccount_PublicNetwork_Modify`. The exact initiative reference is
  `StorageAccountPublicNetworkModify` (Policy Insights lowercases it).
- The definition's exclusion tag could affect other rules, so use a narrowly
  reference-scoped policy exemption instead of tagging resources or disabling
  the initiative. Other rules, including anonymous blob protection, stay active.
- Current storage inventory: 10 accounts, including pre-existing and managed
  accounts. The script snapshots their IDs before the first write and saves each
  resulting exemption ID in config/environments.yml.
- Added `infra/exempt_storage_policy.py`: idempotent, dry-run, fresh context
  verification per write, no overwrites of unowned exemptions, no future-account
  coverage, and exact scope/reference/category read-back.
- Only the created demo storage account will have its network setting reapplied
  after exemptions; no network settings on other storage accounts are changed.

- Focused exemption/network tests: PASS (5 tests); Python compile-check: PASS.
- `python infra/exempt_storage_policy.py --dry-run`: plan completed for the
  approved existing 10-account snapshot, without writes. Dry-run does not
  validate effective permissions.
- `python infra/exempt_storage_policy.py`: partially applied, then stopped.
- Created and verified `demo-storage-public-network` on account
  `demoaasn0dv1901`. Its resource-scoped ID and exact single-rule reference are
  persisted in config/environments.yml.
- Next account `scaneastus2jqfxsge` in `managed-rg-kiwamfn` rejected the write
  with `DenyAssignmentAuthorizationFailed`, despite the administrator having
  normal policy-exemption write permission.
- Platform deny assignment: name `e28e75fa-25df-413e-8a75-bdb2ee4a02fd`,
  ID `e28e75fa25df413e8a75bdb2ee4a02fd`, scoped to that managed resource group.
- Current result: 1/10 exemptions verified; 9 pending. No existing exemption,
  deny assignment, initiative or storage network setting was changed by this run.
- A supported managed-resource owner action or an approved scope exclusion is
  required. Do not remove/bypass the platform deny assignment or create a
  subscription-wide exemption that would cover unapproved future accounts.
- Existing-account snapshots and partial exemption IDs are durable, so rerunning
  can reuse the verified first exemption without duplicating it.
- User explicitly selected `exclude-protected`: exclude storage accounts
  protected by platform deny assignments and apply the single-rule exemption to
  all remaining accounts in the existing snapshot.
- Added a narrowly gated exclusion for only `DenyAssignmentAuthorizationFailed`.
  Every excluded account is logged and persisted; any other error still stops.
  Completion reports exemptions and exclusions separately, never "10 applied".
- Completed approved scope: 9 resource-scoped exemptions verified; 1 explicitly
  excluded protected account (`scaneastus2jqfxsge`). Databricks-managed storage
  accepted its exemption and did not require exclusion.
- Subscription-wide descendant-inclusive read verified all 9 exemptions and
  their single reference `StorageAccountPublicNetworkModify`; no future scope.
- Corrected existence lookup to use that descendant-inclusive listing:
  account-scoped CLI listing omitted extension-resource exemptions. Exact IDs
  and ownership are still checked before any create/update.
- Idempotency dry-run: PASS, reuses all 9 existing exemptions with no create
  commands and reports the 1 explicitly approved protected exclusion.
- Demo account network reapplication via ARM PATCH: PASS,
  `publicNetworkAccess=Enabled`; anonymous blob access remains disabled.
  No other account's network configuration was changed.
- Storage exception subtask is complete. Continue Unity Catalog setup in Step 1.
- Storage-exception completion commit `dbb975842cab30d94337887c9fa2ecca6402e9e1`
  pushed and verified; the approved scope has 9 exemptions and 1 protected exclusion.

### Unity Catalog setup and administrator checkpoint

- Added `tools/bootstrap_databricks.py`, using the documented Databricks API
  schemas and Azure CLI authentication. It gates the existing metastore flag on
  explicit approval, refuses to overwrite unowned UC objects, keeps per-stage
  managed storage locations separate, and disables file events.
- Read official storage-credential, external-location, catalog, schema, grants
  and metastore API references; exact reference URLs are cited in the script.
- Python compile-check and `bootstrap_databricks.py --dry-run`: PASS.
  Dry-run printed the planned payloads without changing settings, IDs or data.
- `bootstrap_databricks.py`: stopped at its first Databricks write, the approved
  external-access flag. Error:
  `User is not a metastore admin for Metastore 'metastore_azure_northeurope'.`
- No credential, external location, catalog, schema, table or compute was created
  by the failed UC bootstrap. The flag remains disabled.
- No metastore ownership, owner-group membership or permissions were changed;
  approval to change the flag is not approval to grant ourselves administrator access.
- Human action: have a metastore administrator enable **External data access**
  for metastore `63247cf6-7207-4507-8329-1310ece4d4e7` (name
  `metastore_azure_northeurope`) in Catalog -> gear -> Metastore -> Details.
  Then reply `done`; contexts and the actual flag will be rechecked before continuing.
- Step 1 Check: Azure Premium workspace, HNS/private containers, access connector
  grant and public endpoint PASS; metastore external access, explicit gold grants
  and first-table `__unitystorage` verification remain BLOCKED.
- Read GA SQL warehouse/Statement Execution references for the future first-table
  probe. Do not use Statement Execution v2 for this probe: it is Lakehouse//RT-only.
  No warehouse was created or started. The auto-provisioned starter stays untouched.
- User enabled external data access; the read-only Databricks preflight confirmed
  `external_access_enabled=true` and all three required authentication contexts.
- Resumed UC bootstrap created `sc_demo`, `el_uc_dev|test|prod`,
  `demo_dev|demo_test|demo_prod`, and each catalog's bronze/silver/gold schemas.
  Managed locations use the stage's own `uc-<stage>` container. File events remain off.
- First resumed run stopped on an empty grants response: Databricks CLI returns
  `{}` when no explicit grants exist. Added focused handling that treats missing
  assignments as no explicit privileges, then adds the required grants.
- Fixed bootstrap rerun reused owned existing resources and completed all stages.
  Explicit `EXTERNAL_USE_SCHEMA`, `USE_SCHEMA`, `SELECT` and `USE_CATALOG`
  were read back successfully; no other principals' grants were used as a proxy.
- Added `tools/check_managed_storage.py`, using documented GA warehouse and
  Statement Execution APIs. It uses one owned serverless 2X-Small warehouse,
  min/max 1, auto-stop 15 minutes, and never starts the existing starter warehouse.
- Verification warehouse `wh-demo-bootstrap` ID `56f680445ba7585a` was created.
- Created a one-row `bronze.bootstrap_probe` Delta table in each stage.
  These are infrastructure probes, not business seed data.
- Each probe was read successfully with the correct stage marker and count 1.
  `DESCRIBE DETAIL` confirmed Delta format, at least one physical data file, and
  a location under the correct container's `__unitystorage` path.
- Actual SQL `SHOW GRANTS ON SCHEMA demo_<stage>.gold` lists EXTERNAL USE SCHEMA.
- The verification script stopped the owned warehouse and polled until STOPPED.
  Starter warehouse unchanged; Fabric F4 unchanged; no other Azure resources created.
- Probe IDs/locations and warehouse ID were persisted in config/environments.yml.
- Four focused Databricks grant/result-shape/compute-guard tests passed.
- Step 1 Check: PASS for Dev, Test and Prod. Commit and push the completed step
  before starting Step 2.

- 2026-11-21T17:18:21+00:00: Created resource group `rg-demo-databricks` in `westeurope` with ownership tags.

- 2026-11-21T17:20:24+00:00: Requested registration of `Microsoft.Databricks` for Step 1.

- 2026-11-21T17:22:13+00:00: Provider `Microsoft.Databricks` registration: PASS.

- 2026-11-21T17:22:15+00:00: Provider `Microsoft.Storage` registration: PASS.

- 2026-11-21T17:22:20+00:00: Validating Step 1 resources in `northeurope` using `az deployment group validate`.

- 2026-11-21T17:22:26+00:00: ARM provider validation: PASS for `infra/databricks.bicep`.

- 2026-11-21T17:22:39+00:00: Submitted `az deployment group create --name demo-step-1 --mode Incremental --no-wait`.

- 2026-11-21T17:23:16+00:00: Azure deployment FAILED: `{"additionalInfo": null, "code": "DeploymentFailed", "details": [{"additionalInfo": null, "code": "InvalidInitialCatalogName", "details": null, "message": "Currently custom initial catalog name is not supported. This capability will be added in future.", "target": null}], "message": "At least one resource deployment operation failed. Please list deployment operations for details. Please see https://aka.ms/arm-deployment-operations for usage details. Correlation ID: 54de96a6-97e1-474e-ae29-5a3b4b982247", "target": "/subscriptions/61ab2275-fb68-4081-ac0f-076c87caf0c1/resourceGroups/rg-demo-databricks/providers/Microsoft.Resources/deployments/demo-step-1"}`.

- 2026-11-21T17:24:35+00:00: Provider `Microsoft.Databricks` registration: PASS.

- 2026-11-21T17:24:37+00:00: Provider `Microsoft.Storage` registration: PASS.

- 2026-11-21T17:24:42+00:00: Validating Step 1 resources in `northeurope` using `az deployment group validate`.

- 2026-11-21T17:24:48+00:00: ARM provider validation: PASS for `infra/databricks.bicep`.

- 2026-11-21T17:25:00+00:00: Submitted `az deployment group create --name demo-step-1 --mode Incremental --no-wait`.

- 2026-11-21T17:28:28+00:00: `databricks_workspace_id` = `/subscriptions/61ab2275-fb68-4081-ac0f-076c87caf0c1/resourceGroups/rg-demo-databricks/providers/Microsoft.Databricks/workspaces/dbw-demo`.

- 2026-11-21T17:28:28+00:00: `databricks_workspace_url` = `https://adb-7405618307807698.18.azuredatabricks.net`.

- 2026-11-21T17:28:28+00:00: `storage_account_name` = `stdemolakenzskwyvxcpeuk`.

- 2026-11-21T17:28:28+00:00: `storage_account_id` = `/subscriptions/61ab2275-fb68-4081-ac0f-076c87caf0c1/resourceGroups/rg-demo-databricks/providers/Microsoft.Storage/storageAccounts/stdemolakenzskwyvxcpeuk`.

- 2026-11-21T17:28:28+00:00: `access_connector_id` = `/subscriptions/61ab2275-fb68-4081-ac0f-076c87caf0c1/resourceGroups/rg-demo-databricks/providers/Microsoft.Databricks/accessConnectors/ac-dbw-demo`.

- 2026-11-21T17:28:28+00:00: `access_connector_principal_id` = `bc435bde-5ec3-4da6-bb00-6dca87807b91`.

- 2026-11-21T17:28:28+00:00: `managed_resource_group_id` = `/subscriptions/61ab2275-fb68-4081-ac0f-076c87caf0c1/resourceGroups/rg-demo-databricks-managed`.

- 2026-11-21T17:28:28+00:00: Azure deployment: PASS. Unity Catalog configuration/checks still pending.

- 2026-11-21T18:39:06+00:00: Re-applied the demo-only public network setting with `az storage account update`.

- 2026-11-21T18:55:22+00:00: Re-applied the demo-only public network setting with method `arm`.

- 2026-11-21T19:20:04+00:00: Approved existing-account exemption snapshot: 10 accounts; no future accounts.

- 2026-11-21T19:20:16+00:00: Verified exemption `/subscriptions/61ab2275-fb68-4081-ac0f-076c87caf0c1/resourceGroups/rg-demoaas-n0dv-1901/providers/Microsoft.Storage/storageAccounts/demoaasn0dv1901/providers/Microsoft.Authorization/policyExemptions/demo-storage-public-network` for only `StorageAccountPublicNetworkModify`.

- 2026-11-21T19:20:25+00:00: Storage exemption blocked: az.CMD policy exemption create --name demo-storage-public-network --scope /subscriptions/61ab2275-fb68-4081-ac0f-076c87caf0c1/resourceGroups/managed-rg-kiwamfn/providers/Microsoft.Storage/storageAccounts/scaneastus2jqfxsge --policy-assignment /providers/Microsoft.Management/managementGroups/5c41223c-f1f5-4979-930f-d5f3c72353f9/providers/Microsoft.Authorization/policyAssignments/MCAPSGovDeployPolicies --exemption-category Waiver --display-name Demo storage public-network exception --description Approved existing-storage-account waiver for public network access only. --only-show-errors --output json --policy-definition-reference-ids @C:\Users\RISHAB~1\AppData\Local\Temp\demo-exemption-m8ofezu2\references.json --metadata @C:\Users\RISHAB~1\AppData\Local\Temp\demo-exemption-m8ofezu2\metadata.json failed (exit 1): ERROR: (DenyAssignmentAuthorizationFailed) The client 'admin@caldova30465160.onmicrosoft.com' with object id '341769a6-9b1d-422e-8080-a666d62dc21d' has permission to perform action 'Microsoft.Authorization/policyExemptions/write' on scope '/subscriptions/61ab2275-fb68-4081-ac0f-076c87caf0c1/resourceGroups/managed-rg-kiwamfn/providers/Microsoft.Storage/storageAccounts/scaneastus2jqfxsge/providers/Microsoft.Authorization/policyExemptions/demo-storage-public-network'; however, the access is denied because of the deny assignment with name 'e28e75fa-25df-413e-8a75-bdb2ee4a02fd' and Id 'e28e75fa25df413e8a75bdb2ee4a02fd' at scope '/subscriptions/61ab2275-fb68-4081-ac0f-076c87caf0c1/resourcegroups/managed-rg-kiwamfn'.
Code: DenyAssignmentAuthorizationFailed
Message: The client 'admin@caldova30465160.onmicrosoft.com' with object id '341769a6-9b1d-422e-8080-a666d62dc21d' has permission to perform action 'Microsoft.Authorization/policyExemptions/write' on scope '/subscriptions/61ab2275-fb68-4081-ac0f-076c87caf0c1/resourceGroups/managed-rg-kiwamfn/providers/Microsoft.Storage/storageAccounts/scaneastus2jqfxsge/providers/Microsoft.Authorization/policyExemptions/demo-storage-public-network'; however, the access is denied because of the deny assignment with name 'e28e75fa-25df-413e-8a75-bdb2ee4a02fd' and Id 'e28e75fa25df413e8a75bdb2ee4a02fd' at scope '/subscriptions/61ab2275-fb68-4081-ac0f-076c87caf0c1/resourcegroups/managed-rg-kiwamfn'.

- 2026-11-21T19:26:00+00:00: Verified exemption `/subscriptions/61ab2275-fb68-4081-ac0f-076c87caf0c1/resourceGroups/rg-demoaas-n0dv-1901/providers/Microsoft.Storage/storageAccounts/demoaasn0dv1901/providers/Microsoft.Authorization/policyExemptions/demo-storage-public-network` for only `StorageAccountPublicNetworkModify`.

- 2026-11-21T19:26:09+00:00: Explicitly approved protected-account exclusion: `/subscriptions/61ab2275-fb68-4081-ac0f-076c87caf0c1/resourceGroups/managed-rg-kiwamfn/providers/Microsoft.Storage/storageAccounts/scaneastus2jqfxsge` (platform deny assignment).

- 2026-11-21T19:26:19+00:00: Verified exemption `/subscriptions/61ab2275-fb68-4081-ac0f-076c87caf0c1/resourceGroups/rg-demo-databricks-managed/providers/Microsoft.Storage/storageAccounts/dbstoraget6ajpmi4ehdl2/providers/Microsoft.Authorization/policyExemptions/demo-storage-public-network` for only `StorageAccountPublicNetworkModify`.

- 2026-11-21T19:26:31+00:00: Verified exemption `/subscriptions/61ab2275-fb68-4081-ac0f-076c87caf0c1/resourceGroups/rg-demo-databricks/providers/Microsoft.Storage/storageAccounts/stdemolakenzskwyvxcpeuk/providers/Microsoft.Authorization/policyExemptions/demo-storage-public-network` for only `StorageAccountPublicNetworkModify`.

- 2026-11-21T19:26:43+00:00: Verified exemption `/subscriptions/61ab2275-fb68-4081-ac0f-076c87caf0c1/resourceGroups/rg-alz-mgmt-state-westus2-001/providers/Microsoft.Storage/storageAccounts/udshyd1901/providers/Microsoft.Authorization/policyExemptions/demo-storage-public-network` for only `StorageAccountPublicNetworkModify`.

- 2026-11-21T19:26:54+00:00: Verified exemption `/subscriptions/61ab2275-fb68-4081-ac0f-076c87caf0c1/resourceGroups/rg-waypoint-agents-qurvrwwr/providers/Microsoft.Storage/storageAccounts/styctih56h2ong2/providers/Microsoft.Authorization/policyExemptions/demo-storage-public-network` for only `StorageAccountPublicNetworkModify`.

- 2026-11-21T19:27:06+00:00: Verified exemption `/subscriptions/61ab2275-fb68-4081-ac0f-076c87caf0c1/resourceGroups/modernwork-rg-n0dv-1901/providers/Microsoft.Storage/storageAccounts/internalpaymentsn0dv1901/providers/Microsoft.Authorization/policyExemptions/demo-storage-public-network` for only `StorageAccountPublicNetworkModify`.

- 2026-11-21T19:27:19+00:00: Verified exemption `/subscriptions/61ab2275-fb68-4081-ac0f-076c87caf0c1/resourceGroups/rg-agent365-complexagent/providers/Microsoft.Storage/storageAccounts/sta365cplxkopcvi/providers/Microsoft.Authorization/policyExemptions/demo-storage-public-network` for only `StorageAccountPublicNetworkModify`.

- 2026-11-21T19:27:29+00:00: Verified exemption `/subscriptions/61ab2275-fb68-4081-ac0f-076c87caf0c1/resourceGroups/rg-a365-foundry-agent/providers/Microsoft.Storage/storageAccounts/stfoundrybfc74u3drvzlw/providers/Microsoft.Authorization/policyExemptions/demo-storage-public-network` for only `StorageAccountPublicNetworkModify`.

- 2026-11-21T19:27:41+00:00: Verified exemption `/subscriptions/61ab2275-fb68-4081-ac0f-076c87caf0c1/resourceGroups/rg-customimages/providers/Microsoft.Storage/storageAccounts/udsimggl1901/providers/Microsoft.Authorization/policyExemptions/demo-storage-public-network` for only `StorageAccountPublicNetworkModify`.

- 2026-11-21T19:28:33+00:00: Re-applied the demo-only public network setting with method `arm`.

- 2026-11-21T19:28:33+00:00: Storage network verification: PASS (public endpoint enabled; anonymous blobs disabled).

- 2026-11-21T19:37:54+00:00: Storage network verification: PASS (public endpoint enabled; anonymous blobs disabled).

- 2026-11-21T19:38:13+00:00: Databricks bootstrap blocked: databricks.exe api patch /api/2.1/unity-catalog/metastores/63247cf6-7207-4507-8329-1310ece4d4e7 --output json --json @C:\Users\RISHAB~1\AppData\Local\Temp\demo-databricks-body-heq_j0p1\body.json failed (exit 1): Error: User is not a metastore admin for Metastore 'metastore_azure_northeurope'.

- 2026-11-21T19:54:29+00:00: Storage network verification: PASS (public endpoint enabled; anonymous blobs disabled).

- 2026-11-21T19:54:59+00:00: Databricks `POST /api/2.1/unity-catalog/storage-credentials`: completed.

- 2026-11-21T19:55:25+00:00: Databricks `POST /api/2.1/unity-catalog/external-locations`: completed.

- 2026-11-21T19:55:38+00:00: Databricks `POST /api/2.1/unity-catalog/catalogs`: completed.

- 2026-11-21T19:55:52+00:00: Databricks `POST /api/2.1/unity-catalog/schemas`: completed.

- 2026-11-21T19:56:02+00:00: Databricks `POST /api/2.1/unity-catalog/schemas`: completed.

- 2026-11-21T19:56:12+00:00: Databricks `POST /api/2.1/unity-catalog/schemas`: completed.

- 2026-11-21T19:58:41+00:00: Storage network verification: PASS (public endpoint enabled; anonymous blobs disabled).

- 2026-11-21T19:59:36+00:00: Databricks `PATCH /api/2.1/unity-catalog/permissions/catalog/demo_dev`: completed.

- 2026-11-21T19:59:51+00:00: Databricks `PATCH /api/2.1/unity-catalog/permissions/schema/demo_dev.gold`: completed.

- 2026-11-21T19:59:56+00:00: Explicit EXTERNAL USE SCHEMA on `demo_dev.gold`: PASS.

- 2026-11-21T20:00:05+00:00: Databricks `POST /api/2.1/unity-catalog/external-locations`: completed.

- 2026-11-21T20:00:16+00:00: Databricks `POST /api/2.1/unity-catalog/catalogs`: completed.

- 2026-11-21T20:00:31+00:00: Databricks `POST /api/2.1/unity-catalog/schemas`: completed.

- 2026-11-21T20:00:44+00:00: Databricks `POST /api/2.1/unity-catalog/schemas`: completed.

- 2026-11-21T20:00:54+00:00: Databricks `POST /api/2.1/unity-catalog/schemas`: completed.

- 2026-11-21T20:01:10+00:00: Databricks `PATCH /api/2.1/unity-catalog/permissions/catalog/demo_test`: completed.

- 2026-11-21T20:01:24+00:00: Databricks `PATCH /api/2.1/unity-catalog/permissions/schema/demo_test.gold`: completed.

- 2026-11-21T20:01:29+00:00: Explicit EXTERNAL USE SCHEMA on `demo_test.gold`: PASS.

- 2026-11-21T20:01:39+00:00: Databricks `POST /api/2.1/unity-catalog/external-locations`: completed.

- 2026-11-21T20:01:50+00:00: Databricks `POST /api/2.1/unity-catalog/catalogs`: completed.

- 2026-11-21T20:02:05+00:00: Databricks `POST /api/2.1/unity-catalog/schemas`: completed.

- 2026-11-21T20:02:14+00:00: Databricks `POST /api/2.1/unity-catalog/schemas`: completed.

- 2026-11-21T20:02:24+00:00: Databricks `POST /api/2.1/unity-catalog/schemas`: completed.

- 2026-11-21T20:02:42+00:00: Databricks `PATCH /api/2.1/unity-catalog/permissions/catalog/demo_prod`: completed.

- 2026-11-21T20:02:56+00:00: Databricks `PATCH /api/2.1/unity-catalog/permissions/schema/demo_prod.gold`: completed.

- 2026-11-21T20:03:00+00:00: Explicit EXTERNAL USE SCHEMA on `demo_prod.gold`: PASS.

- 2026-11-21T20:03:00+00:00: Unity Catalog credentials, stage locations/catalogs/schemas and explicit grants: PASS.

- 2026-11-21T20:04:38+00:00: Created owned serverless warehouse `wh-demo-bootstrap`: `56f680445ba7585a`; auto-stop 15 minutes.

- 2026-11-21T20:05:06+00:00: SQL statement submitted: `CREATE TABLE IF NOT EXISTS demo_dev.bronze.bootstrap_probe USING DELTA COMMENT 'Demo managed-storage probe owned by rishabhmonga119/fabric-demo-platform' AS SELECT 1 AS probe_id, 'dev' AS env_marker`.

- 2026-11-21T20:05:18+00:00: SQL statement submitted: `DESCRIBE DETAIL demo_dev.bronze.bootstrap_probe`.

- 2026-11-21T20:05:29+00:00: SQL statement submitted: `SELECT COUNT(*) AS row_count, env_marker FROM demo_dev.bronze.bootstrap_probe GROUP BY env_marker`.

- 2026-11-21T20:05:42+00:00: SQL statement submitted: `SHOW GRANTS ON SCHEMA demo_dev.gold`.

- 2026-11-21T20:05:42+00:00: Step 1 Check `dev`: explicit gold grants, one readable row and physical __unitystorage files PASS.

- 2026-11-21T20:05:54+00:00: SQL statement submitted: `CREATE TABLE IF NOT EXISTS demo_test.bronze.bootstrap_probe USING DELTA COMMENT 'Demo managed-storage probe owned by rishabhmonga119/fabric-demo-platform' AS SELECT 1 AS probe_id, 'test' AS env_marker`.

- 2026-11-21T20:06:05+00:00: SQL statement submitted: `DESCRIBE DETAIL demo_test.bronze.bootstrap_probe`.

- 2026-11-21T20:06:15+00:00: SQL statement submitted: `SELECT COUNT(*) AS row_count, env_marker FROM demo_test.bronze.bootstrap_probe GROUP BY env_marker`.

- 2026-11-21T20:06:25+00:00: SQL statement submitted: `SHOW GRANTS ON SCHEMA demo_test.gold`.

- 2026-11-21T20:06:25+00:00: Step 1 Check `test`: explicit gold grants, one readable row and physical __unitystorage files PASS.

- 2026-11-21T20:06:56+00:00: SQL statement submitted: `CREATE TABLE IF NOT EXISTS demo_prod.bronze.bootstrap_probe USING DELTA COMMENT 'Demo managed-storage probe owned by rishabhmonga119/fabric-demo-platform' AS SELECT 1 AS probe_id, 'prod' AS env_marker`.

- 2026-11-21T20:07:09+00:00: SQL statement submitted: `DESCRIBE DETAIL demo_prod.bronze.bootstrap_probe`.

- 2026-11-21T20:07:22+00:00: SQL statement submitted: `SELECT COUNT(*) AS row_count, env_marker FROM demo_prod.bronze.bootstrap_probe GROUP BY env_marker`.

- 2026-11-21T20:07:32+00:00: SQL statement submitted: `SHOW GRANTS ON SCHEMA demo_prod.gold`.

- 2026-11-21T20:07:32+00:00: Step 1 Check `prod`: explicit gold grants, one readable row and physical __unitystorage files PASS.

- 2026-11-21T20:07:47+00:00: Owned bootstrap warehouse `56f680445ba7585a`: STOPPED; starter warehouse untouched.

## 2026-11-21 - Step 2: Fabric tenant, workspaces and identities

Status: COMPLETE on explicitly approved F8. Domains, workspaces, roles, OIDC access
and licensed viewer personas are verified. Commit before starting Step 3.

- Step 1 completion commit `d5fdd0ba5e39b52b581da158952b7c582564bfa1` pushed
  and remote HEAD verified.
- Loaded `onelake-catalog-cli` admin-remediate mode and its governance roles,
  catalog concepts, domain CRUD/roles/assignment and no-write escalation references.
- Read `fabric-skills/common/COMMON-CORE.md` auth, REST, pagination and capacity
  references, and the official Admin Workspaces and Tenants REST schemas.
- Added `tools/fabric_preflight.py`: read-only, dry-run-compatible, full pagination,
  active Workspace-only scope, same-origin continuation checks, and the mandatory
  `x-ms-fabric-skill: onelake-catalog-cli` header on every Fabric request.
- Initial Admin Workspaces read failed because Windows `az.cmd` interpreted `&`
  in the query URI as a shell separator. Updated the shared runner to execute
  Azure CLI's official bundled Python module directly, preserving `AZ_INSTALLER=MSI`.
  This keeps arguments literal and preserves existing Azure login/configuration.
- Current official tenant-settings list schema returns `value`, not the older
  skill example's `tenantSettings`; updated the parser to the verified schema.
- Context/native-CLI regression tests: PASS (5 tests).
- `python tools/fabric_preflight.py --dry-run`: PASS, all pages exhausted, no
  Fabric resources or tenant settings changed.
- Existing capacity: `capacityswitzerlandnorth`, ID
  `5332e7ad-fe3b-4c0b-a1b7-3f1975e7b2dd`, F4, Active, Switzerland North.
  Recorded in config/environments.yml; no scaling, creation or resizing.
- No active demo target workspaces or matching demo domains exist in the snapshot.
- Existing enabled settings include Fabric public API service principals,
  Azure OpenAI, AI cross-geo processing/storage, general Git integration and
  Ontology preview. No enabled-group allowlists were reported for those settings.
- Missing relevant settings include GitHub integration, cross-geo Git exports,
  the Microsoft Copilot access switch, external data sharing, and Share Item preview.
- Proposed default: preserve already-enabled settings/scopes so other users are
  not affected, and enable only missing demo prerequisites for the requested
  SG-Demo-Fabric-Admins / SG-Demo-Fabric-API groups after their creation.
- Alternative requiring explicit approval: narrow the required already-enabled
  settings to those demo groups. This overwrites existing tenant scopes.
- Before creating domains, the skill requires explicit choices for owner,
  description, default sensitivity label (or conscious skip), and contributor scope.
  Proposed owner/contributor group for both domains: SG-Demo-Fabric-Admins.
- At the preflight checkpoint, no Step 2 cloud objects had been created.
  Subsequent results and changes are recorded below; Steps 3-9 remain pending.

- 2026-11-21T21:00:17+00:00: Verified security group `SG-Demo-Fabric-Admins`: `c3e74838-ac5e-4541-963a-d9dd63f333ff`.

- 2026-11-21T21:00:25+00:00: Verified security group `SG-Demo-Fabric-API`: `4644c7fa-fc3a-43d0-a29d-d65f5f7b7305`.

- 2026-11-21T21:00:34+00:00: Verified security group `SG-Demo-Sales-North`: `ad4dc1e3-8180-4f7f-98fa-1134f37cc239`.

- 2026-11-21T21:00:42+00:00: Verified security group `SG-Demo-Sales-South`: `199f4419-549f-4f29-9e4a-33a25afc0a36`.

- 2026-11-21T21:01:00+00:00: Verified CI/CD application `sp-fabric-demo-cicd` and SP `e4234475-0f90-44c2-b256-20ce1b6c7614`.

- 2026-11-21T21:01:09+00:00: Verified OIDC credential `github-test`: `e9cb629f-3d30-4794-94b6-ff9adc47dde5`; subject `repo:rishabhmonga119/fabric-demo-platform:environment:test`.

- 2026-11-21T21:01:15+00:00: Verified OIDC credential `github-prod`: `059e40c1-f4e4-4468-9646-e05a15489cc6`; subject `repo:rishabhmonga119/fabric-demo-platform:environment:prod`.

- 2026-11-21T21:01:22+00:00: Verified OIDC credential `github-main`: `7bb1ec3a-a212-45b6-aa1d-02403daea726`; subject `repo:rishabhmonga119/fabric-demo-platform:ref:refs/heads/main`.

- 2026-11-21T21:01:35+00:00: Entra bootstrap blocked: Group membership read-back failed.

- 2026-11-21T21:04:13+00:00: Verified security group `SG-Demo-Fabric-Admins`: `c3e74838-ac5e-4541-963a-d9dd63f333ff`.

- 2026-11-21T21:04:15+00:00: Verified security group `SG-Demo-Fabric-API`: `4644c7fa-fc3a-43d0-a29d-d65f5f7b7305`.

- 2026-11-21T21:04:16+00:00: Verified security group `SG-Demo-Sales-North`: `ad4dc1e3-8180-4f7f-98fa-1134f37cc239`.

- 2026-11-21T21:04:18+00:00: Verified security group `SG-Demo-Sales-South`: `199f4419-549f-4f29-9e4a-33a25afc0a36`.

- 2026-11-21T21:04:21+00:00: Verified CI/CD application `sp-fabric-demo-cicd` and SP `e4234475-0f90-44c2-b256-20ce1b6c7614`.

- 2026-11-21T21:04:23+00:00: Verified OIDC credential `github-test`: `e9cb629f-3d30-4794-94b6-ff9adc47dde5`; subject `repo:rishabhmonga119/fabric-demo-platform:environment:test`.

- 2026-11-21T21:04:23+00:00: Verified OIDC credential `github-prod`: `059e40c1-f4e4-4468-9646-e05a15489cc6`; subject `repo:rishabhmonga119/fabric-demo-platform:environment:prod`.

- 2026-11-21T21:04:23+00:00: Verified OIDC credential `github-main`: `7bb1ec3a-a212-45b6-aa1d-02403daea726`; subject `repo:rishabhmonga119/fabric-demo-platform:ref:refs/heads/main`.

- 2026-11-21T21:05:16+00:00: Verified test user `demo.north@Caldova30465160.onmicrosoft.com`: `62edf9fe-1ae2-46de-bda8-6bede313c3f5`; password not stored; licences pending.

- 2026-11-21T21:05:45+00:00: Verified test user `demo.south@Caldova30465160.onmicrosoft.com`: `b642d835-0e39-48cb-8ebe-a4fdd90320ca`; password not stored; licences pending.

- 2026-11-21T21:09:31+00:00: Fabric bootstrap blocked: Configured F4 capacity is not visible and Active; never substitute or resize.

### Approved governance and Entra results

- User approved preserving already-enabled tenant-setting scopes, the two
  suggested domain descriptions, SG-Demo-Fabric-Admins as owner/contributor,
  and explicitly skipping default sensitivity labels for this synthetic demo.
  Choices were stored in config/environments.yml.
- Added `tools/http_api.py` for AzureCliCredential-authenticated Graph/Fabric
  requests: context before writes, fixed authenticated origins, no credential
  redirects or request-body logging, bounded retries, and no success claim on 202.
- Added and dry-ran `tools/bootstrap_entra.py` using official Graph schemas.
- Created four owned security groups, sp-fabric-demo-cicd application/SP,
  and three GitHub OIDC federated credentials. All non-secret IDs are persisted.
- Initial membership verification exposed the documented Graph v1.0 issue:
  service principals are omitted from group member listings. Replaced it with
  documented directoryObject/checkMemberGroups, with explicit response validation.
- Retried idempotently: groups/application/credentials reused, memberships
  verified, and demo.north/demo.south created and added to their sales groups.
- Initial user passwords were generated only in memory, transmitted to Graph,
  never printed or stored. Reset through Entra before first use; licences pending.
- Added `tools/bootstrap_fabric.py` for approved missing tenant settings, complete
  domain governance and four workspaces created directly on the existing capacity.
  Existing enabled scopes and conflicting/unowned objects are preserved.
- API/Graph membership/tenant-scope tests passed (9 targeted tests).
- Fabric dry-run stopped at the capacity guard before any Fabric writes:
  capacity 5332e7ad-fe3b-4c0b-a1b7-3f1975e7b2dd now reports F8, Active.
- Both the direct authenticated API client and CLI preflight confirmed F8.
  Previously it was F4. No capacity resize was performed by this automation.
- Another visible F4, capacityswedencentral, is Inactive; it was not substituted
  or resumed.
- No demo domains/workspaces or tenant-setting changes were made in this run.
- Human decision required: restore the selected shared capacity to F4, or
  explicitly revise the cost guardrail to allow the already-existing F8.
  Do not overwrite the capacity's externally changed SKU without approval.

### Explicit F8 approval

- User confirmed the manual resize and said: "i have resized it. you can continue with f8 now".
- Rechecked all three identities and the selected capacity: ID
  `5332e7ad-fe3b-4c0b-a1b7-3f1975e7b2dd`, `capacityswitzerlandnorth`, F8, Active.
- Updated the configured SKU and matching cost guardrail to F8 for this existing
  capacity. Automation does not resize it, create another capacity or substitute
  the inactive Sweden capacity.
- One Premium Databricks workspace, serverless/single-node compute, 15-minute
  auto-termination, and no other paid Azure resources remain unchanged.
- Updated dependent preflight/bootstrap guards to require the approved configured
  SKU and reject inconsistent configuration rather than silently accepting changes.
- Resuming the already-approved Fabric domain/workspace/tenant-setting bootstrap.

- 2026-11-21T21:17:31+00:00: Verified tenant setting `GitHubTenantSettings` enabled for only the two demo admin/API groups; existing enabled scopes preserved.

- 2026-11-21T21:17:39+00:00: Verified tenant setting `GitIntegrationCrossGeoTenantSwitch` enabled for only the two demo admin/API groups; existing enabled scopes preserved.

- 2026-11-21T21:17:48+00:00: Verified tenant setting `CatalystTenantAdminSwitch` enabled for only the two demo admin/API groups; existing enabled scopes preserved.

- 2026-11-21T21:17:56+00:00: Verified tenant setting `AllowExternalDataSharingSwitch` enabled for only the two demo admin/API groups; existing enabled scopes preserved.

- 2026-11-21T21:18:05+00:00: Verified tenant setting `ArtifactIQSharePreview` enabled for only the two demo admin/API groups; existing enabled scopes preserved.

- 2026-11-21T21:18:38+00:00: Fabric bootstrap blocked: Domain Admin group read-back failed.

- 2026-11-21T21:21:03+00:00: Verified domain `Demo Analytics`: `93e8c278-af0e-4133-9ed2-a8d91a81df4c`; approved group owner/contributors; default label explicitly skipped.

- 2026-11-21T21:21:26+00:00: Verified domain `Demo Partners`: `0cfb34eb-d336-4308-b4af-a9cc49827577`; approved group owner/contributors; default label explicitly skipped.

- 2026-11-21T21:21:40+00:00: Fabric bootstrap blocked: POST /v1/workspaces: HTTP 401, InsufficientPermissionsToDomain

- 2026-11-21T21:24:06+00:00: Verified domain `Demo Analytics`: `93e8c278-af0e-4133-9ed2-a8d91a81df4c`; approved group owner/contributors; default label explicitly skipped.

- 2026-11-21T21:24:12+00:00: Verified domain `Demo Partners`: `0cfb34eb-d336-4308-b4af-a9cc49827577`; approved group owner/contributors; default label explicitly skipped.

- 2026-11-21T21:24:54+00:00: Verified workspace `DEMO-Analytics-Dev`: `3fa9b173-f000-4529-a4f7-00d0d6a8d136`; F8, domain and exact required roles PASS.

- 2026-11-21T21:25:34+00:00: Verified workspace `DEMO-Analytics-Test`: `0a29b70a-6bc9-4bfc-b196-61825cf9f75a`; F8, domain and exact required roles PASS.

- 2026-11-21T21:26:30+00:00: Verified workspace `DEMO-Analytics-Prod`: `4cd2247c-ab4c-441a-9637-f3c3d525f4c1`; F8, domain and exact required roles PASS.

- 2026-11-21T21:27:05+00:00: Verified workspace `DEMO-Partner-A`: `f29bb81d-9fae-413e-bff4-0a1c56a78ac3`; F8, domain and exact required roles PASS.

- 2026-11-21T21:34:25+00:00: Verified GitHub test environment and three non-secret OIDC variables; no client secret.

### Fabric bootstrap completion and licence checkpoint

- Applied the five approved missing tenant settings, each scoped to only
  SG-Demo-Fabric-Admins / SG-Demo-Fabric-API and read back successfully.
  All already-enabled tenant settings/scopes were preserved.
- Created both domains with approved descriptions and group ownership.
  Default sensitivity labels were explicitly skipped as approved.
- A contributor assignment to the same group replaced its Admin role in the
  live service. Fixed the plan to retain Admin when owner/contributor are the
  same group, because Admin already grants workspace-assignment rights.
- Restored and verified the group Admin role. Explicit EntireTenant contributor
  entries were removed; no existing domain administrators were removed.
- Core Create Workspace with domainId returned InsufficientPermissionsToDomain.
  Used the documented tenant-admin by-ID assignment route instead: create the
  workspace on the selected capacity, verify Active and unassigned, assign only
  that ID, then read back domain/capacity/roles. No other-domain override attempted.
- Four workspaces now pass exact F8/domain/role checks:
  DEMO-Analytics-Dev, DEMO-Analytics-Test, DEMO-Analytics-Prod, DEMO-Partner-A.
- `fab ls --json --skill onelake-catalog-cli` filtered to DEMO- names returned
  exactly those four workspaces. All IDs are in config/environments.yml.
- Added a read-only GitHub OIDC check workflow and scripts. Test environment and
  non-secret AZURE_CLIENT_ID, AZURE_TENANT_ID, FABRIC_CAPACITY_ID variables
  created/verified through gh; no client secret or new Azure role assigned.
- Licence check: admin has active Power BI Pro and M365 Copilot service plans
  through MICROSOFT_365_E7. Both demo users have no assigned licences.
- Updated detection to use actual service-plan capabilities rather than older
  E5/Copilot product-name assumptions. The E7 pool has 53 enabled, 53 consumed,
  0 free seats. No licence purchase, reassignment or reclamation was performed.
- Human action after access proof: provide and assign suitable licences to
  demo.north and demo.south (E7 includes both required capabilities, or equivalent
  base/Power BI Pro plus M365 Copilot), and reset their generated initial passwords
  in Entra. Do not send passwords to the repository or chat.
- New licence, domain-role, tenant-scope, membership and API guard tests passed.
- Step 2 Check: four workspace/F8/domain/roles PASS; actual OIDC proof pending;
  end-user licence prerequisites BLOCKED until allocation.

- 2026-11-21T21:42:08+00:00: Verified GitHub test environment and three non-secret OIDC variables; no client secret.

- 2026-11-21T21:43:54+00:00: OIDC check FAILED: `https://github.com/rishabhmonga119/fabric-demo-platform/actions/runs/44953000815`.

- 2026-11-21T21:50:32+00:00: Verified security group `SG-Demo-Fabric-Admins`: `c3e74838-ac5e-4541-963a-d9dd63f333ff`.

- 2026-11-21T21:50:34+00:00: Verified security group `SG-Demo-Fabric-API`: `4644c7fa-fc3a-43d0-a29d-d65f5f7b7305`.

- 2026-11-21T21:50:36+00:00: Verified security group `SG-Demo-Sales-North`: `ad4dc1e3-8180-4f7f-98fa-1134f37cc239`.

- 2026-11-21T21:50:38+00:00: Verified security group `SG-Demo-Sales-South`: `199f4419-549f-4f29-9e4a-33a25afc0a36`.

- 2026-11-21T21:50:43+00:00: Verified CI/CD application `sp-fabric-demo-cicd` and SP `e4234475-0f90-44c2-b256-20ce1b6c7614`.

- 2026-11-21T21:50:55+00:00: Verified OIDC credential `github-test`: `e9cb629f-3d30-4794-94b6-ff9adc47dde5`; subject `repo:rishabhmonga119@23618963/fabric-demo-platform@1466744419:environment:test`.

- 2026-11-21T21:51:04+00:00: Verified OIDC credential `github-prod`: `059e40c1-f4e4-4468-9646-e05a15489cc6`; subject `repo:rishabhmonga119@23618963/fabric-demo-platform@1466744419:environment:prod`.

- 2026-11-21T21:51:13+00:00: Verified OIDC credential `github-main`: `7bb1ec3a-a212-45b6-aa1d-02403daea726`; subject `repo:rishabhmonga119@23618963/fabric-demo-platform@1466744419:ref:refs/heads/main`.

- 2026-11-21T21:51:56+00:00: Verified test user `demo.north@Caldova30465160.onmicrosoft.com`: `62edf9fe-1ae2-46de-bda8-6bede313c3f5`; password not stored; licences pending.

- 2026-11-21T21:52:12+00:00: Verified test user `demo.south@Caldova30465160.onmicrosoft.com`: `b642d835-0e39-48cb-8ebe-a4fdd90320ca`; password not stored; licences pending.

### OIDC immutable-subject compatibility fix

- First OIDC run `44953000815` failed during Azure login with AADSTS700213.
  GitHub emitted `repo:rishabhmonga119@23618963/fabric-demo-platform@1466744419:environment:test`,
  while the initial credentials used the older name-only subject.
- Read Microsoft's current immutable-subject migration and Graph FIC-update docs.
- GitHub OIDC settings confirmed use_default=true, use_immutable_subject=true,
  and the exact sub_claim_prefix. Repository/owner IDs were independently read
  and verified against the requested repository.
- Updated only the three recorded federated credentials created by this build:
  names, IDs, issuer and audience preserved; subjects now match the verified
  immutable prefix for test, prod and main. Graph read-back passed.
- GitHub's repository OIDC configuration was not changed or downgraded.
- Updated the idempotent Entra script to derive and verify the current format,
  refuse custom/unexpected prefixes and unowned credential changes, and persist
  immutable IDs/prefix. Added two focused subject/ownership-boundary tests.
- Dry-run and actual credential update passed; no new identities, credentials,
  passwords, licences or Azure resources were created.
- Rerun the read-only OIDC proof before the licence-allocation checkpoint.

- 2026-11-21T21:55:40+00:00: Step 2 Check: GitHub OIDC SP lists Test items PASS; `https://github.com/rishabhmonga119/fabric-demo-platform/actions/runs/44954014294`.

- 2026-11-21T22:02:43+00:00: Selected existing licensed `north` viewer `aadik@Caldova30465160.onmicrosoft.com`: `65546fca-dad1-412b-8f87-4b6b83b84ccf`; licences/password unchanged.

- 2026-11-21T22:02:43+00:00: Selected existing licensed `south` viewer `andrel@Caldova30465160.onmicrosoft.com`: `6de428d2-b6a8-42be-8ac2-7f700616576b`; licences/password unchanged.

### Step 2 final checks and existing-user reuse

- Actual OIDC rerun `44954014294` succeeded:
  https://github.com/rishabhmonga119/fabric-demo-platform/actions/runs/44954014294.
  The configured service principal authenticated through GitHub OIDC and listed
  Test items; no Azure subscription role or client secret was required.
- User explicitly chose existing E7 accounts instead of moving licences:
  AadiK for the North persona and AndreL for the South persona.
- Added and dry-ran `tools/select_test_users.py`; it verifies active Power BI Pro
  and M365 Copilot service plans, rejects privileged Prod roles/opposite sales-group
  membership, then adds only the approved sales-group memberships.
- Actual selection passed: both accounts are licensed, non-privileged Prod viewers
  through the corresponding existing Viewer groups.
- No existing licences, passwords, account properties or prior memberships were
  removed/changed. No licences purchased or reclaimed from other accounts.
- Runtime persona UPNs/IDs are now in config/environments.yml. The originally
  created demo.north/demo.south identities are retained under created_test_users
  as unused, unlicensed accounts; no deletion or password reset was performed.
- Entra bootstrap recognises explicitly reused accounts and will not recreate
  them if they disappear.
- Added two focused viewer-eligibility tests; targeted Fabric tests passed (16).
- Step 2 Check: four workspaces on approved F8 PASS; exact domains/roles PASS;
  GitHub OIDC SP access PASS; existing licensed viewer personas PASS.
- Step 2 is complete; no outstanding licence allocation is required for the
  selected personas. Continue Step 3 after committing/pushing this result.

## Step 3 - Deterministic Databricks bundle and medallion

Status: Databricks build and all Step 3 checks COMPLETE. Step 2 was committed/pushed as
`0e561fb18a61894ccf9fc2d774401b6045cca7b4`.

- Final successful reset runs: Dev `991065013003844`, Test `373599146720507`,
  Prod `974721778093552`. Actual job IDs and bundle roots are in configuration.
- All 21 Gold tables passed managed Delta, correct stage storage, exact column
  descriptions, unique grains, marker and no UC filter/mask checks.
  Each stage has 9,856 sales rows and 6,160 delivery rows. Independent complete
  business-row fingerprints match across stages; sales volume checksum
  `4488091.02`, deliveries `4488094.60` (two-decimal partner-share rounding).
- Captured `seed/expected_counts.json` only after actual data matched the seed.
  The first verification was interrupted at 18/21 tables; reran only
  `python tools/build_expected_counts.py --capture-baseline`, not the data jobs.
  Recovery verification passed all 21 tables; the owned SQL warehouse confirmed
  STOPPED. Starter compute and approved Fabric F8 were not changed.
- Final targeted regression command:
  `python -m unittest test_context test_databricks test_seed_model -v`
  with `tests` on PYTHONPATH: 14 tests PASS; `git diff --check` PASS.
- Commit/push uses `tools/commit_step.py --step 3`, explicit Step 3 paths and
  remote-HEAD verification. No Fabric data items exist yet; those are Step 5
  after the Step 4 forecasts, following the requested order.

- Added a three-target DAB with serverless seed, SQL medallion and reset jobs.
  SQL tasks reuse owned serverless warehouse `56f680445ba7585a`, size 2X-Small,
  one cluster, 15-minute auto-stop, explicitly stopped after each stage.
- Read official Databricks bundle settings/resources, serverless notebook jobs,
  SQL notebook warehouse binding, SQL Statement Execution v1, widgets,
  IDENTIFIER and EXECUTE IMMEDIATE references before implementation.
- Data dictionary and deterministic business numbers live in the shared model.
  The complete specified family/package rules give 28 combinations (16 water
  and 12 flavoured/soft-drink), not the approximate "~16" in the sample count.
  Kept every valid combination rather than silently omitting products/packages.
  Expected canonical sales rows: 9,856; deliveries: 6,160. Margins are mapped
  by product line. All stages differ only by their environment marker.
- Ran `python -m unittest discover -s tests -p test_seed_model.py -v` and
  `python tools/run_databricks_bundle.py --dry-run`: generator checks PASS;
  all three live bundle validations PASS; Azure/Fabric/GitHub context PASS.
  No deploy or business data execution had occurred at this checkpoint.
- Added an actual Gold verifier for managed Delta, stage storage, every column
  comment, no masks/row filters, unique grains, markers, independently generated
  business-row fingerprints and volume checksums. Baseline capture is allowed
  only after these actual checks pass.
- First Dev deployment succeeded. `bundle run reset --no-wait --output json`
  submitted reset run `923174667270674` but emitted no JSON stdout, so the
  driver's JSON parsing failed. Read-back confirmed the reset/seed were RUNNING,
  and the SQL warehouse was still STOPPED. Changed submission to the documented
  `jobs run-now <deployed-reset-job-id> --no-wait --output json` command, whose
  contract returns the run ID. The driver detects/reuses an already-active
  reset rather than duplicating it. No authentication/capacity changes needed.
- Local regression suite: 34 tests PASS. Added two targeted shared SQL-client
  checks for pending-to-success polling and explicit failed-statement errors;
  all 6 Databricks tests PASS after extraction.
- The original Dev reset had already finished by the resume attempt, so a new
  reset `251261354222065` was submitted via `jobs run-now`; JSON run-ID capture
  worked. Both Dev runs completed serverless seeding and bronze-to-silver,
  but Gold failed while setting the first column comment: the dynamic
  `EXECUTE IMMEDIATE` literal lost its intended quotes around the description
  (`PARSE_SYNTAX_ERROR`, `IS Product code...`). Warehouse stop was confirmed.
- Read the official ALTER TABLE COLUMN and IDENTIFIER grammar. Replaced dynamic
  comment SQL with `ALTER TABLE IDENTIFIER(...) ALTER COLUMN ... COMMENT '...'`,
  eliminating nested quoting. Regeneration is limited to files carrying this
  generator's known header; unrelated SQL is never overwritten.

- 2026-11-21T22:28:44+00:00: DAB target `dev` validation: PASS.

- 2026-11-21T22:29:24+00:00: Reserved verified-empty bundle path `/Shared/fabric-demo-platform/dev` for owned stage deployment.

- 2026-11-21T22:30:04+00:00: DAB `dev` job `seed_data` = `671885229488893`.

- 2026-11-21T22:30:13+00:00: DAB `dev` job `build_medallion` = `177086689925060`.

- 2026-11-21T22:30:23+00:00: DAB `dev` job `reset` = `366072946856549`.

- 2026-11-21T22:32:49+00:00: DAB target `dev` validation: PASS.

- 2026-11-21T22:33:47+00:00: DAB `dev` job `seed_data` = `671885229488893`.

- 2026-11-21T22:33:57+00:00: DAB `dev` job `build_medallion` = `177086689925060`.

- 2026-11-21T22:34:10+00:00: DAB `dev` job `reset` = `366072946856549`.

- 2026-11-21T22:34:25+00:00: Started DAB `dev` reset run `251261354222065`.

- 2026-11-21T22:36:12+00:00: DAB `dev` reset FAILED: `{"life_cycle_state": "INTERNAL_ERROR", "result_state": "FAILED", "state_message": "Task medallion failed with message: Workload failed, see run output for details. This caused all downstream tasks to get skipped.", "user_cancelled_or_timedout": false}`.

- 2026-11-21T22:36:34+00:00: Owned SQL warehouse confirmed STOPPED after `dev`; auto-stop remains 15 minutes.

- 2026-11-21T22:39:02+00:00: DAB target `dev` validation: PASS.

- 2026-11-21T22:40:19+00:00: DAB `dev` job `seed_data` = `671885229488893`.

- 2026-11-21T22:40:29+00:00: DAB `dev` job `build_medallion` = `177086689925060`.

- 2026-11-21T22:40:38+00:00: DAB `dev` job `reset` = `366072946856549`.

- 2026-11-21T22:40:56+00:00: Started DAB `dev` reset run `991065013003844`.

- 2026-11-21T22:43:44+00:00: DAB `dev` reset run `991065013003844`: SUCCESS.

- 2026-11-21T22:44:06+00:00: Owned SQL warehouse confirmed STOPPED after `dev`; auto-stop remains 15 minutes.

- 2026-11-21T22:44:12+00:00: DAB target `test` validation: PASS.

- 2026-11-21T22:44:50+00:00: Reserved verified-empty bundle path `/Shared/fabric-demo-platform/test` for owned stage deployment.

- 2026-11-21T22:45:17+00:00: DAB `test` job `seed_data` = `169955690803706`.

- 2026-11-21T22:45:27+00:00: DAB `test` job `build_medallion` = `101742214912740`.

- 2026-11-21T22:45:38+00:00: DAB `test` job `reset` = `85327181441208`.

- 2026-11-21T22:45:54+00:00: Started DAB `test` reset run `373599146720507`.

- 2026-11-21T22:48:43+00:00: DAB `test` reset run `373599146720507`: SUCCESS.

- 2026-11-21T22:49:05+00:00: Owned SQL warehouse confirmed STOPPED after `test`; auto-stop remains 15 minutes.

- 2026-11-21T22:49:10+00:00: DAB target `prod` validation: PASS.

- 2026-11-21T22:49:50+00:00: Reserved verified-empty bundle path `/Shared/fabric-demo-platform/prod` for owned stage deployment.

- 2026-11-21T22:50:38+00:00: DAB `prod` job `seed_data` = `469401106812777`.

- 2026-11-21T22:50:48+00:00: DAB `prod` job `build_medallion` = `303569236547339`.

- 2026-11-21T22:50:58+00:00: DAB `prod` job `reset` = `31166941175571`.

- 2026-11-21T22:51:14+00:00: Started DAB `prod` reset run `974721778093552`.

- 2026-11-21T22:55:06+00:00: DAB `prod` reset run `974721778093552`: SUCCESS.

- 2026-11-21T22:55:42+00:00: Owned SQL warehouse confirmed STOPPED after `prod`; auto-stop remains 15 minutes.

- 2026-11-21T22:56:15+00:00: Step 3 Check `demo_dev.gold.dim_product`: `{"rows": 8, "business_checksums": ["3066695588948966823", "5605987114479527784"]}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T22:56:31+00:00: Step 3 Check `demo_dev.gold.dim_package`: `{"rows": 5, "business_checksums": ["3141947863916145291", "3403105532562997435"]}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T22:56:45+00:00: Step 3 Check `demo_dev.gold.dim_channel`: `{"rows": 4, "business_checksums": ["1271150728838377667", "4171335430674441764"]}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T22:57:00+00:00: Step 3 Check `demo_dev.gold.dim_region`: `{"rows": 4, "business_checksums": ["1727677313948116024", "822969283677105475"]}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T22:57:17+00:00: Step 3 Check `demo_dev.gold.dim_partner`: `{"rows": 3, "business_checksums": ["1963812245698801643", "1531370492326189302"]}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T22:57:33+00:00: Step 3 Check `demo_dev.gold.fact_sales_monthly`: `{"rows": 9856, "business_checksums": ["5689566022483012007569", "5693480528515962777561"], "checksum": "4488091.02"}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T22:57:47+00:00: Step 3 Check `demo_dev.gold.fact_deliveries`: `{"rows": 6160, "business_checksums": ["3548235867544143132291", "3542565841620475078838"], "checksum": "4488094.60"}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T22:58:03+00:00: Step 3 Check `demo_test.gold.dim_product`: `{"rows": 8, "business_checksums": ["3066695588948966823", "5605987114479527784"]}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T22:58:20+00:00: Step 3 Check `demo_test.gold.dim_package`: `{"rows": 5, "business_checksums": ["3141947863916145291", "3403105532562997435"]}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T22:58:37+00:00: Step 3 Check `demo_test.gold.dim_channel`: `{"rows": 4, "business_checksums": ["1271150728838377667", "4171335430674441764"]}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T22:58:53+00:00: Step 3 Check `demo_test.gold.dim_region`: `{"rows": 4, "business_checksums": ["1727677313948116024", "822969283677105475"]}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T22:59:13+00:00: Step 3 Check `demo_test.gold.dim_partner`: `{"rows": 3, "business_checksums": ["1963812245698801643", "1531370492326189302"]}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T22:59:29+00:00: Step 3 Check `demo_test.gold.fact_sales_monthly`: `{"rows": 9856, "business_checksums": ["5689566022483012007569", "5693480528515962777561"], "checksum": "4488091.02"}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T22:59:48+00:00: Step 3 Check `demo_test.gold.fact_deliveries`: `{"rows": 6160, "business_checksums": ["3548235867544143132291", "3542565841620475078838"], "checksum": "4488094.60"}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T23:00:05+00:00: Step 3 Check `demo_prod.gold.dim_product`: `{"rows": 8, "business_checksums": ["3066695588948966823", "5605987114479527784"]}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T23:00:24+00:00: Step 3 Check `demo_prod.gold.dim_package`: `{"rows": 5, "business_checksums": ["3141947863916145291", "3403105532562997435"]}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T23:00:41+00:00: Step 3 Check `demo_prod.gold.dim_channel`: `{"rows": 4, "business_checksums": ["1271150728838377667", "4171335430674441764"]}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T23:00:56+00:00: Step 3 Check `demo_prod.gold.dim_region`: `{"rows": 4, "business_checksums": ["1727677313948116024", "822969283677105475"]}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T23:03:24+00:00: Step 3 Check `demo_dev.gold.dim_product`: `{"rows": 8, "business_checksums": ["3066695588948966823", "5605987114479527784"]}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T23:03:44+00:00: Step 3 Check `demo_dev.gold.dim_package`: `{"rows": 5, "business_checksums": ["3141947863916145291", "3403105532562997435"]}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T23:03:58+00:00: Step 3 Check `demo_dev.gold.dim_channel`: `{"rows": 4, "business_checksums": ["1271150728838377667", "4171335430674441764"]}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T23:04:15+00:00: Step 3 Check `demo_dev.gold.dim_region`: `{"rows": 4, "business_checksums": ["1727677313948116024", "822969283677105475"]}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T23:04:28+00:00: Step 3 Check `demo_dev.gold.dim_partner`: `{"rows": 3, "business_checksums": ["1963812245698801643", "1531370492326189302"]}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T23:04:45+00:00: Step 3 Check `demo_dev.gold.fact_sales_monthly`: `{"rows": 9856, "business_checksums": ["5689566022483012007569", "5693480528515962777561"], "checksum": "4488091.02"}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T23:04:59+00:00: Step 3 Check `demo_dev.gold.fact_deliveries`: `{"rows": 6160, "business_checksums": ["3548235867544143132291", "3542565841620475078838"], "checksum": "4488094.60"}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T23:05:14+00:00: Step 3 Check `demo_test.gold.dim_product`: `{"rows": 8, "business_checksums": ["3066695588948966823", "5605987114479527784"]}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T23:05:28+00:00: Step 3 Check `demo_test.gold.dim_package`: `{"rows": 5, "business_checksums": ["3141947863916145291", "3403105532562997435"]}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T23:05:42+00:00: Step 3 Check `demo_test.gold.dim_channel`: `{"rows": 4, "business_checksums": ["1271150728838377667", "4171335430674441764"]}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T23:05:56+00:00: Step 3 Check `demo_test.gold.dim_region`: `{"rows": 4, "business_checksums": ["1727677313948116024", "822969283677105475"]}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T23:06:11+00:00: Step 3 Check `demo_test.gold.dim_partner`: `{"rows": 3, "business_checksums": ["1963812245698801643", "1531370492326189302"]}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T23:06:26+00:00: Step 3 Check `demo_test.gold.fact_sales_monthly`: `{"rows": 9856, "business_checksums": ["5689566022483012007569", "5693480528515962777561"], "checksum": "4488091.02"}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T23:06:40+00:00: Step 3 Check `demo_test.gold.fact_deliveries`: `{"rows": 6160, "business_checksums": ["3548235867544143132291", "3542565841620475078838"], "checksum": "4488094.60"}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T23:06:54+00:00: Step 3 Check `demo_prod.gold.dim_product`: `{"rows": 8, "business_checksums": ["3066695588948966823", "5605987114479527784"]}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T23:07:08+00:00: Step 3 Check `demo_prod.gold.dim_package`: `{"rows": 5, "business_checksums": ["3141947863916145291", "3403105532562997435"]}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T23:07:25+00:00: Step 3 Check `demo_prod.gold.dim_channel`: `{"rows": 4, "business_checksums": ["1271150728838377667", "4171335430674441764"]}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T23:07:38+00:00: Step 3 Check `demo_prod.gold.dim_region`: `{"rows": 4, "business_checksums": ["1727677313948116024", "822969283677105475"]}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T23:07:53+00:00: Step 3 Check `demo_prod.gold.dim_partner`: `{"rows": 3, "business_checksums": ["1963812245698801643", "1531370492326189302"]}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T23:08:08+00:00: Step 3 Check `demo_prod.gold.fact_sales_monthly`: `{"rows": 9856, "business_checksums": ["5689566022483012007569", "5693480528515962777561"], "checksum": "4488091.02"}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T23:08:24+00:00: Step 3 Check `demo_prod.gold.fact_deliveries`: `{"rows": 6160, "business_checksums": ["3548235867544143132291", "3542565841620475078838"], "checksum": "4488094.60"}`; unique grain, stage, comments and no UC filters/masks PASS.

- 2026-11-21T23:08:24+00:00: Captured verified actual counts/checksums in seed/expected_counts.json.

- 2026-11-21T23:08:42+00:00: Owned verification warehouse confirmed STOPPED after Step 3 checks.

- 2026-11-21T23:16:19+00:00: Generated six deterministic forecast workbooks per stage plus one unuploaded live workbook; 4,928 unique baseline forecast grains per stage, one raw unknown-SKU reject and one intentional raw duplicate.

- 2026-11-21T23:16:52+00:00: Prepared owned single-tenant public client `app-demo-sharepoint-upload`, object `55db0d6a-4a8c-4760-8ad0-d8468fd54a5d`, for delegated site creation/selected-site access; no secrets or consent grants created. Human consent/login remains required.

## Step 4 - Forecast workbooks and SharePoint authentication

Status: SharePoint site, uploads and all Step 4 checks COMPLETE. Earlier human
file-protection and delegated-login checkpoints were resolved as recorded below.

- Verified DemoData site/default Documents library. Drive ID:
  `b!fl7D45miBEi-DN8YNgdCVLYZkNTPBsZKkNc3zApyYUs2ryRWykplRKoRpOUJJg1w`.
- Exactly six expected workbooks in each of Forecasts/Dev, Forecasts/Test and
  Forecasts/Prod: 18 uploaded total. Every uploaded workbook's complete sheet
  names and cell values matched its local source. December live file excluded.
- Final uploader rerun passed all three stage Checks with no create/upload
  writes, proving idempotence. Recorded per-file IDs, etags, source SHA256 and
  verification flags in configuration. No tokens or download URLs recorded.
- Commit/push uses explicit Step 4 paths and remote-HEAD verification before
  starting Step 5 Fabric item creation.

- Step 3 commit `6922f59e438b50f06a4615fc3830955c2176907b` pushed; remote HEAD
  verified and worktree was clean before Step 4.
- Added declared openpyxl dependency and restored requirements. Generated three
  standard and three messy workbooks per stage, plus one live December file
  outside the upload roots. All stages use identical canonical source data.
- Forecast baseline has 4,928 unique month/product/package/region/channel
  grains per stage. November and live December project corresponding 2025
  actuals with 4% YoY growth; Jan-Oct use actuals, with seeded 0.85-1.15 variation.
- WEST retail includes RETAIL and ECOM; separate raw files cover HORECA and
  WHOLESALE. Raw inputs deliberately retain comma decimals, title/merged rows,
  month text, one blank row, one unknown SKU and one exact duplicate.
- Found openpyxl Workbook.save overrides the fixed modified timestamp.
  Used ExcelWriter with fixed properties/canonical ZIP timestamps; in-memory
  cross-time binary determinism test PASS.
- `python -m unittest test_excel test_fabric -v`: 20 tests PASS before adding
  the explicit protected-container guard. Generator, auth preparation and initial
  uploader dry-runs PASS. Auth-preparation rerun verified no duplicate app/writes.
- Actual on-disk equality check FAILED: newly generated Dev/Test
  Planung_West_Handel.xlsx became OLE containers (`d0cf11e0a1b11ae1`) containing
  an EncryptedPackage, whereas the generated buffer and sampled Prod file were
  ordinary XLSX ZIPs. This indicates post-write Office file protection. Did not
  decrypt, remove labels, disable policies or relocate files to evade protection.
  Added readability guards before authentication and again before each upload.
- Prepared owned public client app-demo-sharepoint-upload, object
  `55db0d6a-4a8c-4760-8ad0-d8468fd54a5d`; requested delegated Sites.Create.All,
  Sites.Selected and User.Read only. No secret or consent grant created.
  Cached Azure CLI Graph token lacks Sites scopes; CI/CD app was not changed.
- Required human actions: appropriate organizational classification/protection
  review for these synthetic files, admin consent for the upload public client,
  authoritative DemoData site URL, then device-code/MFA sign-in. Live SharePoint
  six-files-per-stage Check remains pending; do not commit Step 4 as complete.
- User confirmed approved readable files and DEMO-tenant admin consent, and
  supplied `https://caldova30465160.sharepoint.com/sites/DemoData`. Verify these
  prerequisites before starting the required device-code/MFA authentication.
- User applied Public labels; all 18 upload workbooks then passed the readable
  XLSX preflight. Completed and verified delegated DEMO-admin sign-in; no
  authentication codes/tokens were saved to this log or Git.
- Graph accepted site creation with HTTP 202 but no acceptable Graph-origin
  operation Location. Failed closed rather than forwarding credentials.
  Read-only Graph Get Site by Path found the newly created DemoData site,
  created `2026-11-21T23:40:35.093Z`, ID
  `caldova30465160.sharepoint.com,e3c35e7e-a299-4804-be0c-df1836074254,d49019b6-06cf-4ac6-90d7-37cc0a72614b`.
  Recorded the actual site ID; did not resubmit creation.
- Added same-origin relative Location support. If an accepted site creation
  lacks a usable Graph operation URL, persist acceptance and verify the named
  site/default-drive readiness via documented Graph GETs. This is resource
  readiness, not a claim that an unavailable LRO status was polled.
- First file upload returned a valid XLSX but server package size was 52,409
  bytes versus 41,573 local bytes; IRM flags were false. A byte-size equality
  check is not appropriate for SharePoint Office package processing.
  Read-back showed creator application exactly matches the owned upload client.
  Replaced size equality with exact worksheet/cell-value verification through
  fresh same-tenant download URLs (no bearer forwarding/URL logging), and
  persist upload IDs before validation so partial successes remain tracked.
  Recover an unrecorded previous upload only when its creator app matches and
  its complete sheet/cell values match; never overwrite unknown files.

- 2026-11-21T23:22:04+00:00: SharePoint upload blocked: C:\Users\rishabhmonga\OneDrive - Microsoft\Customer\Retail - T8 - Eva\gerolsteiner\fabric-demo-platform\seed\excel\dev\raw\Planung_West_Handel.xlsx: not a readable XLSX ZIP container; protected/encrypted files require human policy review before upload.

- 2026-11-21T23:27:13+00:00: SharePoint upload blocked: C:\Users\rishabhmonga\OneDrive - Microsoft\Customer\Retail - T8 - Eva\gerolsteiner\fabric-demo-platform\seed\excel\dev\raw\Planung_West_Handel.xlsx: not a readable XLSX ZIP container; protected/encrypted files require human policy review before upload.

- 2026-11-21T23:39:46+00:00: Delegated SharePoint demo-admin login verified; encrypted token cache is outside Git; no SharePoint writes.

- 2026-11-21T23:40:39+00:00: SharePoint upload blocked: Accepted operation requires a same-origin Location header.

- 2026-11-21T23:45:32+00:00: SharePoint upload blocked: Uploaded workbook read-back shape/size differs: standard/forecast_EAST_2026.xlsx

- 2026-11-21T23:49:49+00:00: Recovered previously created `dev/standard/forecast_EAST_2026.xlsx` by verified creator-app identity and exact sheet/cell equality; no overwrite.

- 2026-11-21T23:49:57+00:00: Uploaded synthetic `dev/standard/forecast_NORTH_2026.xlsx`: `01ZWHYQXUXFZWE4OOOOVEYGE3H3UJBB7L5`.

- 2026-11-21T23:50:05+00:00: Uploaded synthetic `dev/standard/forecast_SOUTH_2026.xlsx`: `01ZWHYQXWKJBTNQCOUJVG2XCJOJTRLT2B3`.

- 2026-11-21T23:50:19+00:00: Uploaded synthetic `dev/raw/Planung_West_Handel.xlsx`: `01ZWHYQXXYKBZ6L3IIP5E2FFGWQOERDASO`.

- 2026-11-21T23:50:27+00:00: Uploaded synthetic `dev/raw/West-GFGH.xlsx`: `01ZWHYQXXHKQFY7AZG7ZGL25FBD3LYE2RW`.

- 2026-11-21T23:50:35+00:00: Uploaded synthetic `dev/raw/west_gastro_forecast_v3_FINAL.xlsx`: `01ZWHYQXWNDSIOFWNOINDKPWAPOIZVCJS2`.

- 2026-11-21T23:50:37+00:00: Step 4 Check `dev`: exactly six expected SharePoint workbooks PASS; live file absent.

- 2026-11-21T23:50:58+00:00: Uploaded synthetic `test/standard/forecast_EAST_2026.xlsx`: `01ZWHYQXSEPMKVEWTTLBC3VVJYHIPDTKPA`.

- 2026-11-21T23:51:06+00:00: Uploaded synthetic `test/standard/forecast_NORTH_2026.xlsx`: `01ZWHYQXVLHBURY45J7ZBIITSJIPB3VC7O`.

- 2026-11-21T23:51:13+00:00: Uploaded synthetic `test/standard/forecast_SOUTH_2026.xlsx`: `01ZWHYQXW62VNP4J2WIVAYLJBZ3DMRTO5D`.

- 2026-11-21T23:51:27+00:00: Uploaded synthetic `test/raw/Planung_West_Handel.xlsx`: `01ZWHYQXTHYRAU5A3C7BF2OPO6LJS62OCJ`.

- 2026-11-21T23:51:34+00:00: Uploaded synthetic `test/raw/West-GFGH.xlsx`: `01ZWHYQXTRYMVKWMZODJFKU4ZNZW6HWVPM`.

- 2026-11-21T23:51:42+00:00: Uploaded synthetic `test/raw/west_gastro_forecast_v3_FINAL.xlsx`: `01ZWHYQXS2HHHHTG4UFZGJVS23JTAXRL37`.

- 2026-11-21T23:51:44+00:00: Step 4 Check `test`: exactly six expected SharePoint workbooks PASS; live file absent.

- 2026-11-21T23:52:05+00:00: Uploaded synthetic `prod/standard/forecast_EAST_2026.xlsx`: `01ZWHYQXUZW573QBC5LFC3L45FXXPB2YWQ`.

- 2026-11-21T23:52:13+00:00: Uploaded synthetic `prod/standard/forecast_NORTH_2026.xlsx`: `01ZWHYQXQ6OJ66Q2LM35DJH2DO35WJYSTZ`.

- 2026-11-21T23:52:23+00:00: Uploaded synthetic `prod/standard/forecast_SOUTH_2026.xlsx`: `01ZWHYQXSYEG4T7HKFFJGYTHPZIFF3MXDB`.

- 2026-11-21T23:52:37+00:00: Uploaded synthetic `prod/raw/Planung_West_Handel.xlsx`: `01ZWHYQXXXXFHEZT2EVBFKSFAZF3IUJXPZ`.

- 2026-11-21T23:52:44+00:00: Uploaded synthetic `prod/raw/West-GFGH.xlsx`: `01ZWHYQXXFQFQMBGWVAVHKFP3KHR42IOS3`.

- 2026-11-21T23:52:52+00:00: Uploaded synthetic `prod/raw/west_gastro_forecast_v3_FINAL.xlsx`: `01ZWHYQXVW5DONFNODORGIR6VTKZLVB4SF`.

- 2026-11-21T23:52:54+00:00: Step 4 Check `prod`: exactly six expected SharePoint workbooks PASS; live file absent.

- 2026-11-21T23:55:03+00:00: Step 4 Check `dev`: exactly six expected SharePoint workbooks PASS; live file absent.

- 2026-11-21T23:55:10+00:00: Step 4 Check `test`: exactly six expected SharePoint workbooks PASS; live file absent.

- 2026-11-21T23:55:18+00:00: Step 4 Check `prod`: exactly six expected SharePoint workbooks PASS; live file absent.

- 2026-11-22T00:02:57+00:00: Created/verified owned Dev `LH_Landing`: `fd2d2f87-dff9-4974-b943-1d45cc2fcd90`; skill references: fabric-skills/common/COMMON-CORE.md; COMMON-CLI.md; SPARK-AUTHORING-CORE.md; skills/dataflows-cli/references/authoring/connection-management.md.

- 2026-11-22T00:03:25+00:00: Dev `LH_Landing` Check: schema-enabled dbo, OneLake paths and SQL endpoint Success PASS.

- 2026-11-22T00:03:38+00:00: Created/verified owned Dev `LH_Curated`: `a8a49dc0-330e-4a63-8280-dccb057b4cde`; skill references: fabric-skills/common/COMMON-CORE.md; COMMON-CLI.md; SPARK-AUTHORING-CORE.md; skills/dataflows-cli/references/authoring/connection-management.md.

- 2026-11-22T00:03:53+00:00: Dev `LH_Curated` Check: schema-enabled dbo, OneLake paths and SQL endpoint Success PASS.

- 2026-11-22T00:03:57+00:00: Live Databricks/SharePoint supportedConnectionTypes inspected. Organizational OAuth2 connections require interactive Fabric portal authoring; not attempted through the unsupported Create Connection credential union.

- 2026-11-22T00:03:57+00:00: Step 5 human prerequisite: create organizational connections conn-dbw-demo, conn-sp-demodata.

## Step 5 - Dev Fabric items

Status: IN PROGRESS. Source connections, Gold mirror and raw/Gold shortcuts are
verified; Excel preview transformation requires UI configuration.
Step 4 commit `8591cd6e6117ff30181814e903e9b224d83ea9fa` pushed and remote HEAD verified.

- Created schema-enabled LH_Landing (`fd2d2f87-dff9-4974-b943-1d45cc2fcd90`)
  and LH_Curated (`a8a49dc0-330e-4a63-8280-dccb057b4cde`) in DEMO-Analytics-Dev.
  Both report dbo default schema and SQL endpoint provisioning Success.
  Lakehouses are not yet populated; mirrors, shortcuts, notebooks and BI items
  still require the source connections. IDs/SQL endpoint IDs are in config.
- Loaded e2e-medallion-architecture and read COMMON-CORE, COMMON-CLI,
  SPARK-AUTHORING-CORE and infrastructure-orchestration references. All Fabric
  control-plane calls carry x-ms-fabric-skill: e2e-medallion-architecture.
  Read current Create/Get Lakehouse REST contracts before forming payloads.
- Added bootstrap_fabric_items.py with active-F8/workspace/ownership guards,
  schema-enabled creation, bounded Retry-After-aware LRO polling and readback.
  Dry-run, actual provisioning, and no-write ownership/schema rerun PASS.
  Six targeted JSON-API tests PASS, including optional response-info handling
  without changing existing callers' return shapes.
- Live supportedConnectionTypes confirms AzureDatabricksWorkspace uses
  AzureDatabricksWorkspace.Actions with required Text parameter url.
  This is not the Databricks SQL connector requiring host/httpPath.
  SharePoint exposes SharePointList with required Text sharePointSiteUrl.
- Both requested connections are missing. The requested organizational-account
  authentication is OAuth2. Skills reference
  skills/dataflows-cli/references/authoring/connection-management.md confirms
  OAuth2 is not in the Create Connection API credential union and must be
  authored interactively. No unsupported credential payload or PAT/secret
  substitute was attempted.
- Required human checkpoint: create conn-dbw-demo and conn-sp-demodata in
  Fabric using the DEMO admin organizational account. Then automate sharing,
  mirrored-catalog and shortcut binding, notebook execution and downstream BI.
  Step 5 is not complete and has not been committed as complete.
- User-created connections verified: conn-dbw-demo
  `9430fa8c-03d8-476b-aa2e-167b0fb804f6` (AzureDatabricksWorkspace, correct
  workspace URL) and conn-sp-demodata `5bb73026-8d9d-4ba1-9c44-91b68ac0bc95`
  (SharePoint, correct DemoData URL). Both ShareableCloud with OAuth2.
- Mirror dry-run stopped on the capacity guard before real sharing/create
  writes. User stated "i scaled down to f4". Read-back verified the same
  capacity `5332e7ad-fe3b-4c0b-a1b7-3f1975e7b2dd` is Active F4 and Dev retains
  the same completed assignment. Updated approved/current SKU to F4 only;
  automation did not resize or substitute capacity. Historical F8 checks above
  reflect the SKU at those earlier times.
- User requested skipping tests after every step to reduce elapsed time.
  Stop routine unit/regression reruns and exhaustive unchanged-artifact checks.
  Retain mandatory context/cost/ownership guards and minimal live success/source
  binding checks. Most earlier time was cloud execution/API verification rather
  than the sub-second unit suites.
- Accepted mirror creation returned no usable Location to the client. Added the
  documented x-ms-operation-id GUID fallback to the canonical Fabric operation
  endpoint; do not forward credentials to other origins.
- Read-only reconciliation found MIR_UC_Gold and its same-named automatic SQL
  endpoint. Corrected lookup to filter by item type, not display name alone.
  No second create or overwrite was attempted. Recorded discovered item and
  endpoint IDs during subsequent binding verification.
- MIR_UC_Gold created and definition read-back verified: item
  `6e1a3d67-2ba7-4580-ae56-4c811846d217`, SQL endpoint
  `e95c7d52-7aaf-4e61-a648-3d4d64dcf2ac`. Binding is demo_dev, Partial catalog
  mirroring with only gold/Full, and autoSync Enabled.
- Live SQL Endpoint MCP smoke check returned exactly seven gold tables.
  fact_sales_monthly has 9,856 rows, fact_deliveries 6,160; both show only
  env_marker=dev. These are actual Fabric query results, not Databricks job
  status. Connection IDs and verified CI/CD User role assignments are recorded.
- Created/read back LH_Landing Files/raw_forecasts to the actual SharePoint
  Dev/raw folder and LH_Curated Tables/gold schema shortcut to MIR_UC_Gold.
  Defaults use Abort conflict policy; no existing targets were overwritten.
- Current public Create Shortcut request/transform schema documents CSV only,
  not the Excel preview input shape. Do not invent Excel transformation fields.
  Official shortcut-transformations documentation describes the UI workflow.
  Public labels remain on local workbooks; inspected uploaded standard packages
  had no legacy MSIP_Label Name/Enabled custom properties. Actual Excel preview
  ingestion still needs its live UI configuration/readback; if labeling blocks
  it, request an approved approach rather than stripping protection.
- 2026-11-22 morning: user confirmed Excel shortcut creation. GET Shortcut
  verified excelToDelta, first-row headers, sheet Forecast, combineAllSheets,
  dynamic schema and mirror refresh. The shortcut exists, but SQL Endpoint
  reports no Landing base tables and OneLake output has no Delta files.
- Raw shortcut resolution returned all three WEST source workbooks. Inspection
  of an uploaded standard workbook found active Purview metadata in
  docMetadata/LabelInfo.xml (new format, not legacy MSIP custom properties).
  No label IDs or tenant-policy identifiers are logged here.
- Microsoft shortcut-transformations documentation explicitly excludes
  workbooks with Purview sensitivity labels; Public labeling is insufficient
  for this preview reader even though Python can read the unencrypted XLSX.
  Request a decision: approved unlabeled standard inputs, or retain Public
  labels and replace the empty Excel transformation with Python ingestion.
  Do not strip protection or silently remove the Excel demo feature.
- Correction: the user's current screenshot shows actual forecast_standard
  preview rows with the expected columns and values. Earlier SQL catalog/path
  checks did not prove transformation failure, and the sensitivity-label
  explanation was an unconfirmed diagnosis, not an observed refresh error.
  Preserve the automatic transformation. Investigate SQL visibility separately
  with a scoped metadata refresh, recreateTables=false; no shortcut replacement,
  source deletion or relabeling is authorized or performed.
- Resolved: scoped SQL metadata refresh returned Success. A subsequent live
  SQL query found forecast.forecast_standard with 3,696 rows, spanning
  January-November 2026. This proves the automatic transformation works in the
  current environment. The earlier label-based failure inference was wrong.
  Root issue was stale SQL metadata; the automatic shortcut and source labels
  remain unchanged. Resume Python cleaning/integration.
- Generated schema-validated pure-Python NB_Clean_Forecast and NB_Integrate
  Git sources. Parsing includes German headers/decimals/months, dimensional
  validation, rejects and full channel-grain deduplication. Integration uses
  an outer join at month/product/package/region/channel grain; partner_id is
  nullable to avoid multiplying sales by the separate delivery-partner grain.
- Deployed NB_Clean_Forecast (`f561f6f6-ebce-4c34-99c8-1457da45a9d8`) and
  captured run `7e5096d8-d7d8-4172-a77f-7a77dba9630a`. It failed with generic
  System_Cancelled_Session_Statements_Failed. No retry was submitted.
- Saved notebook metadata confirms jupyter/python3.11; execution session
  jobType=JupyterSession, runtimeVersion=jupyter1.0, so this is not an accidental
  Spark-kernel deployment despite the generic failure text.
- Spark Advisor and driver-log metadata endpoints returned 404 for this
  session; source-level metadata inspection had no retained cell outputs.
  Opened the documented notebook snapshot in VS Code's browser, which requires
  DEMO-admin sign-in. Need that login or the snapshot's exact failed-cell error
  before making a targeted fix; do not speculate or blindly rerun.
- User changed NB_Integrate to PySpark: Spark SQL for the join and PySpark for
  the Delta write, default Starter Pool, no custom Environment. Reason:
  "show Spark compatibility for a Databricks audience".
  NB_Clean_Forecast remains a pure Python notebook. Inputs and the
  LH_Curated.sales_vs_forecast output/schema remain unchanged, including the
  full channel grain, Decimal precisions and nullable partner_id.
- User snapshot identified the Python reader error: DeltaProtocolError for
  unsupported source reader features (vacuumProtocolCheck, deletionVectors,
  v2Checkpoint, catalogManaged). Do not downgrade source tables. Changed only
  NB_Clean_Forecast reads to the installed notebookutils.data SQL connector;
  its exact signature/query example was inspected in the Python runtime.
  Python-owned Delta writes remain delta-rs. NB_Integrate uses native Spark.
- Read-back of workspace Spark settings confirms defaultPool.name=Starter Pool,
  default runtime 2.0 and no named custom environment.
- NB_Clean_Forecast completed after switching its source reads to the inspected
  SQL connector. Live SQL shows forecast_clean=4,928 rows and
  forecast_rejects=1 row. Its pure-Python kernel is retained.
- NB_Integrate deployed with synapse_pyspark kernel, Spark SQL join and PySpark
  managed Delta write. Default Starter Pool/no custom environment verified.
  Output execution/readback follows; no test-suite rerun.
- Metadata refresh for Python outputs returned NotRun with a prior successful
  sync timestamp; live SQL verified both output tables. Treat that as an
  explicitly skipped already-synced operation, not a failed data write.
- First native Spark integration run failed before the join: driver stdout
  reported IllegalStateException "Couldn't locate commit coordinator" while
  reading the catalogManaged Gold source through its direct Delta shortcut.
  Spark Advisor was empty. No source protocol or table was changed.
- Use the preinstalled Fabric SQL-endpoint Spark connector to load the same
  Gold/clean-forecast inputs into Spark temporary views. The requested join
  remains Spark SQL and the output remains a PySpark managed Delta write, using
  default Starter Pool/no custom environment and the same output schema.
  This connector's documented Entra-user-only limitation must be considered
  when finalizing unattended CI/CD execution; it is not claimed as SP-compatible.
- NB_Integrate now completed successfully as PySpark on the verified default
  Starter Pool/runtime 2.0, without a custom environment. Live SQL read-back of
  LH_Curated.dbo.sales_vs_forecast returned 10,304 rows, January 2025 through
  November 2026, all env_marker=dev. All 14 columns match the prior output
  contract, including nullable fields, Date month, DECIMAL(12,2) volumes and
  DECIMAL(14,2) revenue/margin. Requested decision/reason is implemented.

- 2026-11-22T00:20:24+00:00: Mirror bootstrap blocked: Dev mirror workspace/capacity differs from approved Active F8.

- 2026-11-22T00:25:02+00:00: Verified user-created `conn-dbw-demo` connection `9430fa8c-03d8-476b-aa2e-167b0fb804f6` and CI/CD User access; credentials untouched. Skills: common/COMMON-CORE.md; skills/dataflows-cli/references/authoring/connection-management.md; official connections roleAssignments contract.

- 2026-11-22T00:25:12+00:00: Verified user-created `conn-sp-demodata` connection `5bb73026-8d9d-4ba1-9c44-91b68ac0bc95` and CI/CD User access; credentials untouched. Skills: common/COMMON-CORE.md; skills/dataflows-cli/references/authoring/connection-management.md; official connections roleAssignments contract.

- 2026-11-22T00:25:32+00:00: Mirror bootstrap blocked: Accepted operation requires a same-origin Location header.

- 2026-11-22T00:28:08+00:00: Verified user-created `conn-dbw-demo` connection `9430fa8c-03d8-476b-aa2e-167b0fb804f6` and CI/CD User access; credentials untouched. Skills: common/COMMON-CORE.md; skills/dataflows-cli/references/authoring/connection-management.md; official connections roleAssignments contract.

- 2026-11-22T00:28:11+00:00: Verified user-created `conn-sp-demodata` connection `5bb73026-8d9d-4ba1-9c44-91b68ac0bc95` and CI/CD User access; credentials untouched. Skills: common/COMMON-CORE.md; skills/dataflows-cli/references/authoring/connection-management.md; official connections roleAssignments contract.

- 2026-11-22T00:28:19+00:00: Mirror bootstrap blocked: Existing mirror is unowned/conflicting; no overwrite.

- 2026-11-22T00:29:45+00:00: Verified user-created `conn-dbw-demo` connection `9430fa8c-03d8-476b-aa2e-167b0fb804f6` and CI/CD User access; credentials untouched. Skills: common/COMMON-CORE.md; skills/dataflows-cli/references/authoring/connection-management.md; official connections roleAssignments contract.

- 2026-11-22T00:29:48+00:00: Verified user-created `conn-sp-demodata` connection `5bb73026-8d9d-4ba1-9c44-91b68ac0bc95` and CI/CD User access; credentials untouched. Skills: common/COMMON-CORE.md; skills/dataflows-cli/references/authoring/connection-management.md; official connections roleAssignments contract.

- 2026-11-22T00:30:32+00:00: Created/verified `MIR_UC_Gold`: `6e1a3d67-2ba7-4580-ae56-4c811846d217`, catalog `demo_dev`, gold only, autoSync Enabled. Skill: common/ITEM-DEFINITIONS-CORE.md Other Item Types and its mirrored Azure Databricks definition spec. Data-table verification pending.

- 2026-11-22T06:39:52+00:00: Dev `LH_Landing/Files/raw_forecasts` shortcut target read-back PASS. Skill: common/COMMON-CORE.md OneLake Shortcuts and Create Shortcut REST spec.

- 2026-11-22T06:40:10+00:00: Dev `LH_Curated/Tables/gold` shortcut target read-back PASS. Skill: common/COMMON-CORE.md OneLake Shortcuts and Create Shortcut REST spec.

- 2026-11-22T07:15:04+00:00: Scoped forecast.forecast_standard SQL metadata refresh Success; recreateTables=false; automatic Excel shortcut untouched.

- 2026-11-22T07:31:13+00:00: Deployed owned pure-Python `NB_Clean_Forecast`: `f561f6f6-ebce-4c34-99c8-1457da45a9d8`. Skill: spark-cli authoring/notebook-api-operations.md; SPARK-NOTEBOOK-AUTHORING-CORE.md. No redundant definition readback.

- 2026-11-22T07:31:22+00:00: Started/monitoring `NB_Clean_Forecast` run `7e5096d8-d7d8-4172-a77f-7a77dba9630a`.

- 2026-11-22T07:32:23+00:00: `NB_Clean_Forecast` run failed: `{"requestId": "e1f59699-78f4-490e-bdc8-4d6809574676", "errorCode": "System_Cancelled_Session_Statements_Failed", "message": "System cancelled the Spark session due to statement execution failures", "isRetriable": false}`.

- 2026-11-22T07:32:23+00:00: Forecast notebook bootstrap blocked: NB_Clean_Forecast: {"requestId": "e1f59699-78f4-490e-bdc8-4d6809574676", "errorCode": "System_Cancelled_Session_Statements_Failed", "message": "System cancelled the Spark session due to statement execution failures", "isRetriable": false}

- 2026-11-22T07:49:55+00:00: Deployed owned pure-Python `NB_Clean_Forecast`: `f561f6f6-ebce-4c34-99c8-1457da45a9d8`. Skill: spark-cli authoring/notebook-api-operations.md; SPARK-NOTEBOOK-AUTHORING-CORE.md. No redundant definition readback.

- 2026-11-22T07:50:05+00:00: Started/monitoring `NB_Clean_Forecast` run `3d65b53c-a3b5-4879-99e9-00557778fc81`.

- 2026-11-22T07:51:07+00:00: `NB_Clean_Forecast` run Completed; data smoke check next.

- 2026-11-22T07:56:21+00:00: Scoped LH_Curated.gold SQL metadata refresh Success for dim_package; recreateTables=false; source tables unchanged.

- 2026-11-22T07:57:14+00:00: Deployed owned `NB_Clean_Forecast`: `f561f6f6-ebce-4c34-99c8-1457da45a9d8`, kernel `jupyter`. Skill: spark-cli authoring/notebook-api-operations.md; SPARK-NOTEBOOK-AUTHORING-CORE.md. No redundant definition readback.

- 2026-11-22T07:57:24+00:00: Started/monitoring `NB_Clean_Forecast` run `fbdaa315-9e7b-435c-af7b-c78ab76c04cd`.

- 2026-11-22T07:58:29+00:00: `NB_Clean_Forecast` run Completed; data smoke check next.

- 2026-11-22T07:59:05+00:00: Deployed owned `NB_Integrate`: `a1fcd41e-f5b3-4f06-9f05-dd91004eed34`, kernel `synapse_pyspark`. Skill: spark-cli authoring/notebook-api-operations.md; SPARK-NOTEBOOK-AUTHORING-CORE.md. No redundant definition readback.

- 2026-11-22T08:00:17+00:00: Scoped SQL metadata refresh did not succeed: `[{"tableName": "forecast.forecast_clean", "status": "NotRun", "startDateTime": "2026-11-22T08:00:14.7229297Z", "endDateTime": "2026-11-22T08:00:14.7698098Z", "lastSuccessfulSyncDateTime": "2026-11-22T07:58:10.2538196Z"}, {"tableName": "forecast.forecast_rejects", "status": "NotRun", "startDateTime": "2026-11-22T08:00:14.7229297Z", "endDateTime": "2026-11-22T08:00:14.7698098Z", "lastSuccessfulSyncDateTime": "2026-11-22T07:58:10.2538196Z"}]`; source tables unchanged.

- 2026-11-22T08:00:17+00:00: Forecast metadata refresh blocked: Scoped SQL metadata refresh returned a non-success table status.

- 2026-11-22T08:05:08+00:00: Dev `LH_Landing/Files/raw_forecasts` shortcut target read-back PASS. Skill: common/COMMON-CORE.md OneLake Shortcuts and Create Shortcut REST spec.

- 2026-11-22T08:05:15+00:00: Dev `LH_Curated/Tables/gold` shortcut target read-back PASS. Skill: common/COMMON-CORE.md OneLake Shortcuts and Create Shortcut REST spec.

- 2026-11-22T08:05:31+00:00: Dev `LH_Curated/Tables/dbo/forecast_clean` shortcut target read-back PASS. Skill: common/COMMON-CORE.md OneLake Shortcuts and Create Shortcut REST spec.

- 2026-11-22T08:05:48+00:00: Deployed owned `NB_Clean_Forecast`: `f561f6f6-ebce-4c34-99c8-1457da45a9d8`, kernel `jupyter`. Skill: spark-cli authoring/notebook-api-operations.md; SPARK-NOTEBOOK-AUTHORING-CORE.md. No redundant definition readback.

- 2026-11-22T08:05:51+00:00: Deployed owned `NB_Integrate`: `a1fcd41e-f5b3-4f06-9f05-dd91004eed34`, kernel `synapse_pyspark`. Skill: spark-cli authoring/notebook-api-operations.md; SPARK-NOTEBOOK-AUTHORING-CORE.md. No redundant definition readback.

- 2026-11-22T08:06:00+00:00: Started/monitoring `NB_Integrate` run `e7961ad5-6169-4922-a08f-1ab92558213a`.

- 2026-11-22T08:07:02+00:00: `NB_Integrate` run failed: `{"requestId": "ee6f6597-5996-4267-b940-1f16174a454d", "errorCode": "System_Cancelled_Session_Statements_Failed", "message": "System cancelled the Spark session due to statement execution failures", "isRetriable": false}`.

- 2026-11-22T08:07:02+00:00: Forecast notebook bootstrap blocked: NB_Integrate: {"requestId": "ee6f6597-5996-4267-b940-1f16174a454d", "errorCode": "System_Cancelled_Session_Statements_Failed", "message": "System cancelled the Spark session due to statement execution failures", "isRetriable": false}

- 2026-11-22T08:15:30+00:00: Deployed owned `NB_Clean_Forecast`: `f561f6f6-ebce-4c34-99c8-1457da45a9d8`, kernel `jupyter`. Skill: spark-cli authoring/notebook-api-operations.md; SPARK-NOTEBOOK-AUTHORING-CORE.md. No redundant definition readback.

- 2026-11-22T08:16:03+00:00: Deployed owned `NB_Integrate`: `a1fcd41e-f5b3-4f06-9f05-dd91004eed34`, kernel `synapse_pyspark`. Skill: spark-cli authoring/notebook-api-operations.md; SPARK-NOTEBOOK-AUTHORING-CORE.md. No redundant definition readback.

- 2026-11-22T08:16:12+00:00: Started/monitoring `NB_Integrate` run `e7641dce-a129-4b61-85c7-974d0312bd9e`.

- 2026-11-22T08:19:29+00:00: `NB_Integrate` run Completed; data smoke check next.

- 2026-11-22T08:40:55+00:00: Created/updated owned PL_Refresh `923dd7b0-871f-4fde-8737-e11eca0e481e`; Python cleaning then PySpark integration, no pool/environment overrides. Skill: pipeline-migration/resources/notebook-activity-migration.md; common/ITEM-DEFINITIONS-CORE.md DataPipeline.

- 2026-11-22T08:41:04+00:00: Started/monitoring PL_Refresh `4d23e629-664f-4579-9cd9-30082193e14b`.

- 2026-11-22T08:48:47+00:00: PL_Refresh Completed; both notebook dependencies honored.

- 2026-11-22T09:07:57+00:00: Created complete MCP-authored SM_Sales `f3dd4c43-1c47-408c-92af-af5bea6fd78c` from exported TMDL; seven tables, seven measures, six relationships. Skill references: powerbi-authoring/skills/semantic-model-authoring/references/semantic-model-rest-api.md; connection-binding.md; direct-lake-guidelines.md; https://learn.microsoft.com/rest/api/power-bi/datasets/execute-queries-in-group.

- 2026-11-22T09:07:59+00:00: SM_Sales Automatic end-user SSO binding verified; no fixed-identity connection.

- 2026-11-22T09:08:09+00:00: Sales model bootstrap blocked: Accepted operation requires a same-origin Location header (received scheme='https', host='wabi-us-central-b-primary-redirect.analysis.windows.net', path='/v1.0/myorg/groups/3fa9b173-f000-4529-a4f7-00d0d6a8d136/datasets/f3dd4c43-1c47-408c-92af-af5bea6fd78c/refreshes/e97dcbb5-2d8e-4b01-b1e0-1ad98d186839').

- 2026-11-22T09:10:38+00:00: SM_Sales Automatic end-user SSO binding verified; no fixed-identity connection.

- 2026-11-22T09:10:40+00:00: Reconciled existing SM_Sales refresh `e97dcbb5-2d8e-4b01-b1e0-1ad98d186839`: Completed; no new refresh submission.

- 2026-11-22T09:10:49+00:00: SM_Sales initial refresh and seven-measure live check PASS: `{"[Actual hl]": 4488091.02, "[Forecast hl]": 2286058.24, "[Deviation hl]": -188035.14, "[Deviation %]": -0.0822529963191139, "[Revenue EUR]": 288517979.92, "[Margin EUR]": 76975278.66, "[Margin %]": 0.26679543050087773, "[Rows]": 10304, "[Calendar days]": 730, "[Stage]": "dev"}`.

### Step 5 semantic-model checkpoint - 2026-11-22

### Step 5 report publication - 2026-11-22

### Step 5 complete - workspace capture and source handoff

### Step 6 - Approved Prod rollout and metadata-only CI completed

Current status, 2026-11-22:

- All 11 requested Test items are deployed. The first Test pipeline completed;
  physical Curated output and the live model query both verified 10,304 rows,
  marker `test`, and the intended Jan 2025-Nov 2026 range.
- Test SM_Sales `52c8a3a4-5da4-4dde-b239-effa95b8ca55` refreshed successfully.
  Seven baseline measures and the 730-day calendar passed. The Data Agent
  references the Test ontology only; the report still uses SM_Sales.
- Test RPT_Sales `d2e7b370-490d-4be3-8c8e-7c82386e76a6` passed live binding,
  deployed-definition, and both-page screenshot checks. Margin % renders 26.7%.
  The deployed Margin footer now correctly says `Source: SM_Sales, Test.`
  Initial captures caught blank/faded page transitions; settled active-page
  captures proved complete rendering without changing the layout.
- Added the report stage-caption parameter and `--phase report`, so this
  correction republished only RPT_Sales through fabric-cicd. The successful
  pipeline/model refresh was not repeated. Report verification supports
  `--report-only --report-preview-dir <new-local-directory>` and uses the
  documented PBIR getDefinition endpoint plus CLI unpack.
- The report-only dry-run initially stopped on three out-of-scope,
  ontology-named supporting items: Eventhouse
  `14dc951b-770e-4d6a-a472-cea7e6e4d011`, GraphModel
  `20c9d46d-4686-4f49-999b-639a4d6cc362`, and KQLDatabase
  `3e73ccf4-acb0-41ea-9450-cdbfa1ec9854`. Narrowed ownership checks to the
  selected publish types; out-of-scope items remain untouched and orphan
  deletion remains disabled.
- Commands: `python -m py_compile tools\deploy.py tools\verify.py`;
  `python tools\verify.py --stage test --dry-run`;
  `python tools\verify.py --stage test`;
  `python tools\deploy.py --stage test --phase report --dry-run`;
  `python tools\deploy.py --stage test --phase report`;
  `python tools\verify.py --stage test --report-only --report-preview-dir ...`.
  Deployed PBIR validation passed with zero errors/warnings; service preview,
  both-page capture, and settled-image review passed against the Test model.
- Report skill loaded from
  `C:\Users\rishabhmonga\.copilot\installed-plugins\fabric-collection\powerbi-authoring\skills\powerbi-report-cli\SKILL.md`;
  references: `references/management.md`, `management-part-02.md`,
  `authoring.md`, and `authoring/preview*.md`, `screenshot-review.md`.
  Deployment references: fabric-skills `common/COMMON-CORE.md`,
  `common/COMMON-CLI.md`, and
  https://microsoft.github.io/fabric-cicd/latest/how_to/parameterization/.
- GitHub Actions deployment is not wired, Prod is not deployed, and Step 6
  is not complete. Hosted OIDC signs in as the approved service principal,
  which cannot satisfy the current local admin-user/CLI identity guard.
  That guard has not been relaxed. Microsoft also explicitly documents that
  the Spark SQL-endpoint connector supports interactive Entra users, not
  service principals:
  https://learn.microsoft.com/en-us/fabric/data-engineering/spark-data-warehouse-connector#authentication.
  Deployment/refresh identity and the initial Prod approval require an
  explicit decision; no SP-compatible Spark refresh is claimed.

Initial Prod deployment and CI split approved by the user after Test acceptance:

- Deploy initial Prod locally using fabric-cicd under the verified DEMO admin
  on the existing F4; verify items, stage-local rows, report rendering, and
  actual Data Agent answers.
- Then configure metadata-only GitHub Actions/OIDC with sp-fabric-demo-cicd.
  Keep data refresh and Spark SQL reads user-authenticated as a separate step,
  and document the split in README.
- Do not modify Dev or Test during this rollout. Stop for any new tenant
  setting or permission grant. No such change is currently authorized.

Prod checkpoint, 2026-11-22:

- All 11 requested Prod items were deployed, with IDs in environments.yml.
  MIR_UC_Gold is bound to `demo_prod.gold`; raw/standard SharePoint targets are
  `Forecasts/Prod/raw` and `Forecasts/Prod/standard`. The user created the Excel
  transformation in the Prod UI.
- First scoped forecast metadata refresh found no Delta log while the new
  transformation was still materializing. A later scoped refresh returned
  NotRun with a successful sync timestamp, and the SQL MCP verified **3,696**
  actual rows in `forecast.forecast_standard`. No table was recreated.
- The first Prod PL_Refresh completed once. SQL MCP verified
  `dbo.sales_vs_forecast`: **10,304** rows, only marker `prod`,
  Jan 2025-Nov 2026, actual hl **4,488,091.02**, revenue EUR
  **288,517,979.92**, and margin EUR **76,975,278.66**.
- Prod model initial refresh and seven-measure/calendar/stage checks passed.
  Deployed report PBIR passed validation with zero errors/warnings. Both pages
  passed actual screenshot review, including the settled **26.7%** margin card
  and correct `Source: SM_Sales, Prod.` caption. Temporary screenshots were
  cleaned and the visible Prod preview retained.
- Published the ontology-only Prod Data Agent for its public MCP endpoint,
  not Agent Store/M365. Added a genuine runtime verifier using the official
  MCP client. Corrected MCP 2 differences from older documentation examples:
  two transport streams and snake-case schema/error attributes. Focused
  context/API/MCP tests passed (20 tests); no full unchanged-data suite rerun.
- The tested **published MCP** question returned a content-unavailable refusal,
  not the expected baseline. That particular answer check did not pass.
  Microsoft lists a semantic-model-bound ontology issue, but this does not
  establish the cause. The user subsequently showed an ontology-only
  **draft UI** response with real historical trends. Corrected the earlier
  overbroad "Data Agent blocked" diagnosis: the draft can answer, and the
  published MCP result needs separate investigation. Both draft and published
  definition readback contain the same Prod ontology/workspace IDs. No safety
  control was bypassed, ontology rebound, V1 definition substituted, or
  standalone semantic-model source added.
- Metadata-only OIDC workflow and PR checks are implemented. GitHub Prod
  reviewer/main PR protection readback passed; existing Test environment and
  OIDC variables were preserved. No tenant setting or new permission grant
  was made. Read-only hosted OIDC/SDK verification is pending push/dispatch.
- At this earlier checkpoint, published Data Agent answer acceptance was still
  pending; the successful follow-up below supersedes that status.
  A checkpoint push uses `[skip ci]` so introducing the workflow/parameters
  does not automatically redeploy Test during this Prod-only rollout.

Hosted CI capacity verification:

- Pushed checkpoint `bdee4057ea98a3017d261ae19ee361e1677e56e0` with `[skip ci]`.
  Read-only OIDC run `45067822040` authenticated successfully as the approved
  app/main subject and passed tenant/application/repository identity guards,
  then stopped at capacity visibility. Fabric capacity listing requires
  capacity Administrator/Contributor access; the app did not have that access.
- Independently reconfirmed the same capacity Active F4 and Test's unchanged
  capacity assignment. The user explicitly approved **Azure Reader only on
  the one existing capacity resource**, not capacity administration,
  subscription-wide roles, or paid-resource changes.
- `grant_ci_capacity_reader.py --dry-run`, then
  `--approved-capacity-reader`, created/read back assignment
  `d0661003-3606-5499-82b6-f2438517dd4d`. Scope and assignment ID are in config.
  Initial CLI list validation rejected `--all` with `--scope`; corrected to
  the documented scoped list before making the grant.
- CI now verifies the live SKU/state through the official Azure capacity
  GET API using that limited Reader access. Local capacity verification
  remains through Fabric under the DEMO admin. Workspace/F4 checks are not
  skipped or weakened, and no resize/activation method is used.
  Reference:
  https://learn.microsoft.com/rest/api/microsoftfabric/fabric-capacities/get?view=rest-microsoftfabric-2023-11-01.

Data Agent empirical verification follow-up:

- The user's screenshot showed the **draft UI** generating ontology-grounded
  historical trends. Both draft/published definition readback referenced the
  same Prod ONT_Business and workspace. No ontology binding was changed.
- The same historical-trends question through **published Prod MCP** also
  generated a detailed business answer. Windows console CP1252 initially
  prevented printing a nonbreaking hyphen; captured the answer with UTF-8 and
  corrected the runtime verifier's output encoding. The earlier broad
  "semantic-model-bound ontology makes this agent unusable" conclusion was
  not supported by live evidence and was withdrawn.
- Ordinary business questions through Prod MCP returned exact actual volume
  **4,488,091.02 hl**, revenue **288,517,979.92 EUR**, margin
  **76,975,278.66 EUR**, and revenue-weighted margin **26.68%**, with the correct
  Jan 2025-Oct 2026 scope. Both answer checks passed and actual answers are in
  the config/audit log. The ontology-only source and report's model are preserved.
- No source rebinding, standalone semantic-model source, safety-control change,
  or new tenant setting was used to get these answers.

Earlier ingestion and source-handoff notes below are retained as audit history.

Final approved rollout result:

- Prod: all 11 requested items deployed; first refresh completed; 10,304 rows
  marked only `prod`; baseline totals/calendar/schema bindings verified; both
  actual report pages rendered; published ontology-only Data Agent returned
  the exact business totals and 26.68% weighted margin.
- Metadata-only GitHub workflow, PR checks, Prod required reviewer and main PR
  protection are pushed. Local admin-user checks remain unchanged. The only
  newly approved Azure permission is Reader on the single existing F4 resource.
- Hosted OIDC run **45071446452** passed under the approved application/tenant/
  immutable repository identities. It read the live Active F4 through the
  capacity-only Reader role and validated **Test ingest, Test analytics,
  Prod ingest and Prod analytics** with the actual fabric-cicd parser.
  https://github.com/rishabhmonga119/fabric-demo-platform/actions/runs/45071446452
- Both deployment jobs were intentionally skipped because this was
  `validate_only=true`; no Test/Dev change or duplicate Prod deployment was
  performed. This proves hosted identity/capacity/SDK preflight, not a new
  SP-driven publish or data refresh. Spark/data refresh remains a separate
  user-authenticated step documented in README.
- Checkpoints were pushed and remote main verified. Runtime/config/audit results
  are persisted. Agent Store/M365 publication and the partner/baseline steps
  remain separate subsequent work.

- Step 5 automation commit `ea291684c7914fd2ec5c556701246e8523b47633`
  was pushed and remote main verified.
- Created Test MIR_UC_Gold over `demo_test.gold`, schema-enabled LH_Landing
  and LH_Curated through their documented APIs. No stage data was copied.
- Published Test VL_Config, NB_Clean_Forecast, NB_Integrate and PL_Refresh
  using fabric-cicd. Parameters are narrowed to each publish phase so the
  library cannot silently skip notebook workspace/lakehouse replacements.
- Source staging includes only Git-tracked files, not live `.pbi` browser
  profiles. The library's regional LRO Location could not receive credentials;
  the repository's same-origin API/LRO transport was used instead. Accepted
  operations are recorded and resumed, not blindly resubmitted.
- Verified both notebooks have `stage = 'test'`, the Test workspace ID,
  and no Dev workspace reference. Verified raw SharePoint Test folder and
  Test Gold mirror shortcut targets, Starter Pool/no custom Environment,
  and active Variable Library value set `test`.
- SQL metadata check returned no `forecast.forecast_standard` table in
  Test LH_Landing. Excel preview transformation is not in the captured
  shortcut metadata and has no documented public creation payload.
  User chose to create it in Test UI after Computer Use detected active
  user input. The first pipeline run and analytics publish wait on that input.
- Prod has not been deployed. Its deployment remains gated after Test
  data/binding verification and production approval.

- All 11 requested Dev items are captured in Git at
  `1f6056d485fe57ad7f10c5b849e464be9ff954d6`. Workspace and remote heads match,
  with zero pending changes. GitHub credential write authorization was fixed
  by the user; no branch-protection or Fabric-item issue existed.
- The Data Agent definition contains
  `Files/Config/draft/ontologies/ONT_Business/ontology.json` with the expected
  ontology ID. It has no independently configured semantic-model source.
- Imported the exact workspace capture, including V2 ontology TMDL,
  user-authored model AI metadata, Data Agent ontology context, lakehouse
  shortcut metadata and actual portable logical IDs.
- Windows `core.autocrlf=true` changed line endings during archive extraction/
  staging and initially blocked fast-forward. Re-created the archive with
  `core.autocrlf=false`, retained mixed service line endings, and fast-forwarded
  successfully without discarding unrelated changes.
- Step 5 Check PASS: one source folder per requested item, initial workspace
  commit present, approved F4 unchanged. Repository is the source writer from
  this handoff onward; Dev becomes a downstream Git-update target.
- Next: Step 6 stage parameterization and Test deployment, followed by gated
  Prod deployment. No repeated data resets or full regression suite are needed.

- User changed the Data Agent source decision: ONT_Business only, without an
  independently added SM_Sales source. This applies to DA_Sales, not the report.
  Updated bootstrap defaults and added `tools/set_data_agent_ontology_only.py`
  with `--dry-run`. The real update succeeded and definition readback verified
  removal of the standalone model source and persistence of ontology-only
  routing. Other parts and published state were retained.
- The integrated browser could not complete Fabric SSO. The remaining
  supported setup is the authenticated UI action DA_Sales -> Sources ->
  Add sources -> Add an ontology -> ONT_Business. No legacy graph/GQL payload
  or undocumented experimental metadata was invented.

- Resumed after the user identified the unintended pause after report approval.
  Created `RPT_Sales` in Dev as `34ae3a5d-4c6a-4c8b-8504-bd47bf6d5f0f`.
  Actual publication, model binding and the two ordered pages were verified.
- Commands: `tools/generate_sales_report.py --spec <approved session spec>
  --dry-run`, generator execution, `powerbi-report-author validate`,
  service-host status/open and screenshots of both pages, then
  `tools/bootstrap_sales_report.py --dry-run` and `--render-reviewed`.
  A post-publication dry-run confirmed no new submission.
- Render review passed: populated monthly actual/forecast lines,
  product-by-package matrix, region/channel dropdowns, margin-by-channel bars
  and a complete 26.7% Margin % card. Initial page-transition captures were
  faded/incomplete; warm active-page captures verified settled rendering.
  No PBIR change was needed for that transient loading effect.
- Adapted the skill's base theme to the installed CLI's card-property metadata.
  Staging only the 21 validated files avoids copying locked/private `.pbi`
  browser caches. `.pbi/` and local settings are ignored by Git.
- Shared LRO extraction was checked with the single focused existing test;
  it passed in 0.004 seconds. No routine full suite was run.
- The reviewed temporary screenshot child was deleted. The completed headless
  validation host was closed; the verified detached visible preview remains
  open for the user.
- Next human prerequisite: new-experience V2 `ONT_Business` creation and
  configuration through the Fabric UI/Ontology agent. The installed ontology
  skill cannot author V2. Do not fake V2 definitions or fall back to V1.
  Step 5 remains incomplete; no Step 5 completion commit/push has been made.

- User confirmed terminology was added; the provided screenshot shows
  Prep data for AI -> Add AI instructions. Record this as user-authored
  terminology guidance, not verified dedicated field synonyms. Preserve it
  unchanged during Git capture and subsequent model deployment.
- User clarified that the demo's synonyms belong in the ontology. The earlier
  instruction conflated that requirement with Power BI AI instructions.
  Corrected the setup guidance; ontology synonyms remain pending Step 5.8.
  Loaded `ontology-cli/SKILL.md`: its automated authoring supports legacy V1
  only, not new-experience V2 creation. Do not invent a V2 payload.
- The report skill's required planning gate is complete: the user explicitly
  approved the two-page `RPT_Sales` spec and Dev publication. The canonical
  spec is in the session workspace, not the repository. No report has been
  authored or published yet; implementation is the next phase.

- `SM_Sales` was created once as `f3dd4c43-1c47-408c-92af-af5bea6fd78c`;
  the complete MCP-authored model is persisted as TMDL. Its six business tables
  use Direct Lake on OneLake; its contiguous calendar is an imported M table.
- The initial enhanced refresh succeeded. Its regional Location was rejected
  without forwarding credentials; canonical public-API history reconciled that
  same completed run. No duplicate refresh was submitted. The API now derives
  only the exact same-resource refresh GUID on the public Power BI origin.
- Lightweight validation: Python syntax and deployment dry-run passed; eight
  focused API-guard cases passed in 0.059 seconds. No routine regression suite
  or repeated Databricks/SharePoint checks were run.
- Human prerequisite at Step 5.7: configure the requested synonyms in
  `SM_Sales` -> Prep data for AI: actual volume = hl/hectolitre/volume,
  Package = Gebinde/package, Channel = Kanal/channel. The loaded
  `powerbi-authoring/skills/semantic-model-authoring/references/semantic-model-ai-readiness.md`
  requires user configuration in that UI; no opaque AI metadata was fabricated.
- The report folder is a PBIP scaffold only, not a deployed report. Ontology,
  data agent, Variable Library and Git capture remain pending. Step 5 is still
  incomplete and has not been committed or pushed as complete.

- 2026-11-22T09:14:03+00:00: LH_Curated OneLake baseline verified: only DefaultReader, Read on *, virtual ReadAll membership. Current OneLake documentation supplies this role by default; no extra enable payload or role overwrite. Skill: e2e-medallion-architecture; https://learn.microsoft.com/fabric/onelake/security/get-started-security; https://learn.microsoft.com/rest/api/fabric/core/onelake-data-access-security/list-data-access-roles.

- 2026-11-22T09:14:07+00:00: SM_Sales Automatic end-user SSO binding verified; no fixed-identity connection.

- 2026-11-22T09:39:59+00:00: Generated RPT_Sales from the approved report spec and official CLI shell: 2 FHD pages, 12 visuals, stable IDs, bound to existing SM_Sales. References: powerbi-report-cli/references/authoring-part-02.md; authoring/authoring-workflows.md; cartesian.md; table.md; slicers.md; card.md; card-part-02.md; textbox.md; theming.md.

- 2026-11-22T09:40:01+00:00: Sales report generation blocked: powerbi-report-author.CMD validate C:\Users\rishabhmonga\OneDrive - Microsoft\Customer\Retail - T8 - Eva\gerolsteiner\fabric-demo-platform\fabric\RPT_Sales.Report failed (exit 1): {"data":{"result":"failed","errorCount":6,"warningCount":0,"reportPath":"C:\\Users\\rishabhmonga\\OneDrive - Microsoft\\Customer\\Retail - T8 - Eva\\gerolsteiner\\fabric-demo-platform\\fabric\\RPT_Sales.Report","diagnostics":{"PBIR_THEME_VISUAL_PROP_UNKNOWN":{"severity":"error","items":[{"message":"Unknown theme property \"border.radius\" for \"cardVisual\": C:\\Users\\rishabhmonga\\OneDrive - Microsoft\\Customer\\Retail - T8 - Eva\\gerolsteiner\\fabric-demo-platform\\fabric\\RPT_Sales.Report\\StaticResources\\RegisteredResources\\SalesAnalytics-278371a8609b.json","file":"C:\\Users\\rishabhmonga\\OneDrive - Microsoft\\Customer\\Retail - T8 - Eva\\gerolsteiner\\fabric-demo-platform\\fabric\\RPT_Sales.Report\\StaticResources\\RegisteredResources\\SalesAnalytics-278371a8609b.json","path":"border.radius"},{"message":"Unknown theme property \"spacing.customizeSpacing\" for \"cardVisual\": C:\\Users\\rishabhmonga\\OneDrive - Microsoft\\Customer\\Retail - T8 - Eva\\gerolsteiner\\fabric-demo-platform\\fabric\\RPT_Sales.Report\\StaticResources\\RegisteredResources\\SalesAnalytics-278371a8609b.json","file":"C:\\Users\\rishabhmonga\\OneDrive - Microsoft\\Customer\\Retail - T8 - Eva\\gerolsteiner\\fabric-demo-platform\\fabric\\RPT_Sales.Report\\StaticResources\\RegisteredResources\\SalesAnalytics-278371a8609b.json","path":"spacing.customizeSpacing"},{"message":"Unknown theme property \"padding.top\" for \"cardVisual\": C:\\Users\\rishabhmonga\\OneDrive - Microsoft\\Customer\\Retail - T8 - Eva\\gerolsteiner\\fabric-demo-platform\\fabric\\RPT_Sales.Report\\StaticResources\\RegisteredResources\\SalesAnalytics-278371a8609b.json","file":"C:\\Users\\rishabhmonga\\OneDrive - Microsoft\\Customer\\Retail - T8 - Eva\\gerolsteiner\\fabric-demo-platform\\fabric\\RPT_Sales.Report\\StaticResources\\RegisteredResources\\SalesAnalytics-278371a8609b.json","path":"padding.top"},{"message":"Unknown theme property \"padding.bottom\" for \"cardVisual\": C:\\Users\\rishabhmonga\\OneDrive - Microsoft\\Customer\\Retail - T8 - Eva\\gerolsteiner\\fabric-demo-platform\\fabric\\RPT_Sales.Report\\StaticResources\\RegisteredResources\\SalesAnalytics-278371a8609b.json","file":"C:\\Users\\rishabhmonga\\OneDrive - Microsoft\\Customer\\Retail - T8 - Eva\\gerolsteiner\\fabric-demo-platform\\fabric\\RPT_Sales.Report\\StaticResources\\RegisteredResources\\SalesAnalytics-278371a8609b.json","path":"padding.bottom"},{"message":"Unknown theme property \"padding.left\" for \"cardVisual\": C:\\Users\\rishabhmonga\\OneDrive - Microsoft\\Customer\\Retail - T8 - Eva\\gerolsteiner\\fabric-demo-platform\\fabric\\RPT_Sales.Report\\StaticResources\\RegisteredResources\\SalesAnalytics-278371a8609b.json","file":"C:\\Users\\rishabhmonga\\OneDrive - Microsoft\\Customer\\Retail - T8 - Eva\\gerolsteiner\\fabric-demo-platform\\fabric\\RPT_Sales.Report\\StaticResources\\RegisteredResources\\SalesAnalytics-278371a8609b.json","path":"padding.left"},{"message":"Unknown theme property \"padding.right\" for \"cardVisual\": C:\\Users\\rishabhmonga\\OneDrive - Microsoft\\Customer\\Retail - T8 - Eva\\gerolsteiner\\fabric-demo-platform\\fabric\\RPT_Sales.Report\\StaticResources\\RegisteredResources\\SalesAnalytics-278371a8609b.json","file":"C:\\Users\\rishabhmonga\\OneDrive - Microsoft\\Customer\\Retail - T8 - Eva\\gerolsteiner\\fabric-demo-platform\\fabric\\RPT_Sales.Report\\StaticResources\\RegisteredResources\\SalesAnalytics-278371a8609b.json","path":"padding.right"}]}}}}

- 2026-11-22T09:40:36+00:00: Generated RPT_Sales from the approved report spec and official CLI shell: 2 FHD pages, 12 visuals, stable IDs, bound to existing SM_Sales. References: powerbi-report-cli/references/authoring-part-02.md; authoring/authoring-workflows.md; cartesian.md; table.md; slicers.md; card.md; card-part-02.md; textbox.md; theming.md.

- 2026-11-22T09:53:51+00:00: Sales report publication blocked: [('C:\\Users\\rishabhmonga\\OneDrive - Microsoft\\Customer\\Retail - T8 - Eva\\gerolsteiner\\fabric-demo-platform\\fabric\\RPT_Sales.Report\\.pbi\\preview\\profile-1380d6f71126b5c1-92c5d9bd-76b2-48c9-9cd1-c4906a8ec969\\Default\\Network\\Cookies', 'C:\\Users\\RISHAB~1\\AppData\\Local\\Temp\\fabric-publish-sales-_uk7j4bs\\RPT_Sales.Report\\.pbi\\preview\\profile-1380d6f71126b5c1-92c5d9bd-76b2-48c9-9cd1-c4906a8ec969\\Default\\Network\\Cookies', '[WinError 32] The process cannot access the file because it is being used by another process'), ('C:\\Users\\rishabhmonga\\OneDrive - Microsoft\\Customer\\Retail - T8 - Eva\\gerolsteiner\\fabric-demo-platform\\fabric\\RPT_Sales.Report\\.pbi\\preview\\profile-1380d6f71126b5c1-92c5d9bd-76b2-48c9-9cd1-c4906a8ec969\\Default\\Network\\Cookies-journal', 'C:\\Users\\RISHAB~1\\AppData\\Local\\Temp\\fabric-publish-sales-_uk7j4bs\\RPT_Sales.Report\\.pbi\\preview\\profile-1380d6f71126b5c1-92c5d9bd-76b2-48c9-9cd1-c4906a8ec969\\Default\\Network\\Cookies-journal', '[WinError 32] The process cannot access the file because it is being used by another process'), ('C:\\Users\\rishabhmonga\\OneDrive - Microsoft\\Customer\\Retail - T8 - Eva\\gerolsteiner\\fabric-demo-platform\\fabric\\RPT_Sales.Report\\.pbi\\preview\\profile-1380d6f71126b5c1-92c5d9bd-76b2-48c9-9cd1-c4906a8ec969\\Default\\Sessions\\Session_13439814559864639', 'C:\\Users\\RISHAB~1\\AppData\\Local\\Temp\\fabric-publish-sales-_uk7j4bs\\RPT_Sales.Report\\.pbi\\preview\\profile-1380d6f71126b5c1-92c5d9bd-76b2-48c9-9cd1-c4906a8ec969\\Default\\Sessions\\Session_13439814559864639', '[WinError 32] The process cannot access the file because it is being used by another process'), ('C:\\Users\\rishabhmonga\\OneDrive - Microsoft\\Customer\\Retail - T8 - Eva\\gerolsteiner\\fabric-demo-platform\\fabric\\RPT_Sales.Report\\.pbi\\preview\\profile-1380d6f71126b5c1-92c5d9bd-76b2-48c9-9cd1-c4906a8ec969\\Default\\Sessions_Encrypted\\Session_13439814559865837', 'C:\\Users\\RISHAB~1\\AppData\\Local\\Temp\\fabric-publish-sales-_uk7j4bs\\RPT_Sales.Report\\.pbi\\preview\\profile-1380d6f71126b5c1-92c5d9bd-76b2-48c9-9cd1-c4906a8ec969\\Default\\Sessions_Encrypted\\Session_13439814559865837', '[WinError 32] The process cannot access the file because it is being used by another process')]

- 2026-11-22T09:56:03+00:00: Accepted RPT_Sales creation: `https://api.fabric.microsoft.com/v1/operations/00e5d518-4b3e-402c-8498-17ffe8ebfdf6`; polling, never resubmitting.

- 2026-11-22T09:56:32+00:00: RPT_Sales `34ae3a5d-4c6a-4c8b-8504-bd47bf6d5f0f` publication PASS: correct SM_Sales binding, two ordered pages; live-data screenshot review passed before publication, including Margin %=26.7. URL: https://app.powerbi.com/groups/3fa9b173-f000-4529-a4f7-00d0d6a8d136/reports/34ae3a5d-4c6a-4c8b-8504-bd47bf6d5f0f. References: powerbi-report-cli/references/management.md; management-part-02.md; management-part-04.md; authoring/powerbi-report-author-cli.md; https://learn.microsoft.com/rest/api/power-bi/reports/get-report-in-group; https://learn.microsoft.com/rest/api/power-bi/reports/get-pages-in-group.

- 2026-11-22T10:20:45+00:00: Captured user-created V2 ONT_Business `2cf382af-fb83-45e5-8940-f3af5d85a6c7` metadata; entity/binding configuration confirmed by user, not inspected through a V1 API.

- 2026-11-22T10:21:20+00:00: Created/verified DA_Sales `a28d4922-889e-4330-b343-a8a90d0224c2` with owned definition; no unowned overwrite.

- 2026-11-22T10:21:50+00:00: Dev context bootstrap blocked: Data Agent instructions or semantic model binding did not persist.

- 2026-11-22T10:24:21+00:00: Captured user-created V2 ONT_Business `2cf382af-fb83-45e5-8940-f3af5d85a6c7` metadata; entity/binding configuration confirmed by user, not inspected through a V1 API.

- 2026-11-22T10:24:23+00:00: Created/verified DA_Sales `a28d4922-889e-4330-b343-a8a90d0224c2` with owned definition; no unowned overwrite.

- 2026-11-22T10:24:54+00:00: DA_Sales draft instructions and SM_Sales binding readback PASS. V2 Ontology context must be attached in the supported UI, not as graph/GQL. References: fabric-skills/common/COMMON-CORE.md; https://learn.microsoft.com/rest/api/fabric/dataagent/items/create-data-agent; https://learn.microsoft.com/rest/api/fabric/articles/item-management/definitions/data-agent-definition.

- 2026-11-22T10:25:31+00:00: Created/verified VL_Config `3ea7efa7-860b-4c2c-99ad-47625ad6c497` with owned definition; no unowned overwrite.

- 2026-11-22T10:26:16+00:00: VL_Config definition/readback and active dev value set PASS; no redundant dev overrides. Skill: variable-library-cli/references/authoring.md; operations.md.

- 2026-11-22T10:38:37+00:00: DA_Sales standalone SM_Sales source removed and verified. Ontology-only agent routing persisted; other definition parts and published state preserved. RPT_Sales/SM_Sales were not changed. Reference: common/COMMON-CORE.md; https://learn.microsoft.com/rest/api/fabric/dataagent/items/update-data-agent-definition.

- 2026-11-22T11:07:42+00:00: Dev Git capture PASS: all known items synced, no changes, workspace/remote head `1f6056d485fe57ad7f10c5b849e464be9ff954d6`. Skill: git-integration-operations-cli/SKILL.md, Commit to Git / Check Sync Status. Initial workspace capture is complete; subsequent source writer is the repository.

- 2026-11-22T11:15:23+00:00: Step 5 source capture integrated: all 11 item folders from Git commit `1f6056d485fe57ad7f10c5b849e464be9ff954d6`, actual logical IDs and opaque user-authored model/ontology/agent state preserved. No unrelated paths or preview caches touched.

- 2026-11-22T11:46:49+00:00: Step 5 source capture integrated: all 11 item folders from Git commit `1f6056d485fe57ad7f10c5b849e464be9ff954d6`, actual logical IDs and opaque user-authored model/ontology/agent state preserved. No unrelated paths or preview caches touched.

- 2026-11-22T16:59:06+00:00: Created/verified `MIR_UC_Gold`: `f9e0ebdb-f691-4b61-9e2d-033b6bdd6d70`, catalog `demo_test`, gold only, autoSync Enabled. Skill: common/ITEM-DEFINITIONS-CORE.md Other Item Types and its mirrored Azure Databricks definition spec. Data-table verification pending.

- 2026-11-22T17:00:40+00:00: Created/verified owned Test `LH_Landing`: `8f144ba3-441b-4d52-b511-c31e6723656f`; skill references: fabric-skills/common/COMMON-CORE.md; COMMON-CLI.md; SPARK-AUTHORING-CORE.md; skills/dataflows-cli/references/authoring/connection-management.md.

- 2026-11-22T17:00:55+00:00: Test `LH_Landing` Check: schema-enabled dbo, OneLake paths and SQL endpoint Success PASS.

- 2026-11-22T17:01:09+00:00: Created/verified owned Test `LH_Curated`: `131b3d5b-5c57-4f24-97de-2ba407db823d`; skill references: fabric-skills/common/COMMON-CORE.md; COMMON-CLI.md; SPARK-AUTHORING-CORE.md; skills/dataflows-cli/references/authoring/connection-management.md.

- 2026-11-22T17:01:24+00:00: Test `LH_Curated` Check: schema-enabled dbo, OneLake paths and SQL endpoint Success PASS.

- 2026-11-22T17:10:56+00:00: Starting test/ingest fabric-cicd deployment with per-write context guards. Lakehouse/mirror preparation and shortcuts use their supported post-deploy APIs; no orphan deletion or paid-resource creation.

- 2026-11-22T17:15:18+00:00: Starting test/ingest fabric-cicd deployment with per-write context guards. Lakehouse/mirror preparation and shortcuts use their supported post-deploy APIs; no orphan deletion or paid-resource creation.

- 2026-11-22T17:19:13+00:00: Stage deployment blocked: An unrecorded stage item exists; no overwrite.

- 2026-11-22T17:21:24+00:00: Recovered delayed visibility of owned test item `VL_Config`: `dc23655e-cfe6-481c-804a-1c3d2793138b`; no duplicate creation.

- 2026-11-22T17:21:27+00:00: Starting test/ingest fabric-cicd deployment with per-write context guards. Lakehouse/mirror preparation and shortcuts use their supported post-deploy APIs; no orphan deletion or paid-resource creation.

- 2026-11-22T17:28:02+00:00: Starting test/ingest fabric-cicd deployment with per-write context guards. Lakehouse/mirror preparation and shortcuts use their supported post-deploy APIs; no orphan deletion or paid-resource creation.

- 2026-11-22T17:29:49+00:00: test/ingest metadata deployment PASS: NB_Clean_Forecast, NB_Integrate, PL_Refresh, VL_Config. References: common/COMMON-CORE.md; https://microsoft.github.io/fabric-cicd/latest/how_to/parameterization/.

- 2026-11-22T17:36:48+00:00: test LH_Landing/raw_forecasts target binding PASS; reference: spark-cli common/COMMON-CORE.md OneLake Shortcuts.

- 2026-11-22T17:37:02+00:00: test LH_Curated/gold target binding PASS; reference: spark-cli common/COMMON-CORE.md OneLake Shortcuts.

- 2026-11-22T17:37:08+00:00: test ingestion metadata ready: stage shortcuts, Starter Pool/no custom Environment, active Variable Library value set verified. Excel preview standard transformation must be created in the UI if absent; no unsupported payload.

- 2026-11-22T18:04:56+00:00: Scoped LH_Landing.forecast SQL metadata refresh checked for forecast_standard; previously synced NotRun tables: []; recreateTables=false; source tables unchanged.

- 2026-11-22T18:07:59+00:00: Started/monitoring DEMO-Analytics-Test PL_Refresh `4efa540c-75c9-4a3e-b17b-ab6cec39ad0b`.

- 2026-11-22T18:10:43+00:00: DEMO-Analytics-Test PL_Refresh Completed; both notebook dependencies honored.

- 2026-11-22T18:20:38+00:00: test LH_Landing/raw_forecasts target binding PASS; reference: spark-cli common/COMMON-CORE.md OneLake Shortcuts.

- 2026-11-22T18:20:44+00:00: test LH_Curated/gold target binding PASS; reference: spark-cli common/COMMON-CORE.md OneLake Shortcuts.

- 2026-11-22T18:20:58+00:00: test LH_Curated/forecast_clean target binding PASS; reference: spark-cli common/COMMON-CORE.md OneLake Shortcuts.

- 2026-11-22T18:21:04+00:00: test ingestion metadata ready: stage shortcuts, Starter Pool/no custom Environment, active Variable Library value set verified. Excel preview standard transformation must be created in the UI if absent; no unsupported payload.

- 2026-11-22T18:21:37+00:00: Starting test/analytics fabric-cicd deployment with per-write context guards. Lakehouse/mirror preparation and shortcuts use their supported post-deploy APIs; no orphan deletion or paid-resource creation.

- 2026-11-22T18:26:03+00:00: Starting test/analytics fabric-cicd deployment with per-write context guards. Lakehouse/mirror preparation and shortcuts use their supported post-deploy APIs; no orphan deletion or paid-resource creation.

- 2026-11-22T18:29:50+00:00: test/analytics metadata deployment PASS: DA_Sales, ONT_Business, RPT_Sales, SM_Sales. References: common/COMMON-CORE.md; https://microsoft.github.io/fabric-cicd/latest/how_to/parameterization/.

- 2026-11-22T18:34:23+00:00: Started/monitoring SM_Sales refresh `2e43156a-d4e5-4bfd-b3a5-7700eca36389`.

- 2026-11-22T18:34:56+00:00: SM_Sales initial refresh and seven-measure live check PASS: `{"[Actual hl]": 4488091.02, "[Forecast hl]": 2286058.24, "[Deviation hl]": -188035.14, "[Deviation %]": -0.0822529963191139, "[Revenue EUR]": 288517979.92, "[Margin EUR]": 76975278.66, "[Margin %]": 0.26679543050087773, "[Rows]": 10304, "[Calendar days]": 730, "[Stage]": "test"}`.

- 2026-11-22T18:35:27+00:00: test analytics bindings PASS: stage-local Direct Lake/SSO, report model/pages, ontology-only Data Agent. Model live baseline query verified the stage marker and row count.

- 2026-11-22T18:44:28+00:00: Stage deployment blocked: An unrecorded stage item exists; no overwrite.

- 2026-11-22T18:46:47+00:00: Starting test/report fabric-cicd deployment with per-write context guards. Lakehouse/mirror preparation and shortcuts use their supported post-deploy APIs; no orphan deletion or paid-resource creation.

- 2026-11-22T18:47:37+00:00: test/report metadata deployment PASS: RPT_Sales. References: common/COMMON-CORE.md; https://microsoft.github.io/fabric-cicd/latest/how_to/parameterization/.

- 2026-11-22T18:50:00+00:00: test report binding and stage caption PASS; deployed PBIR retrieved for rendered review. Reference: powerbi-report-cli/references/management-part-02.md.

- 2026-11-22T19:06:32+00:00: Created/verified `MIR_UC_Gold`: `307c660c-fa6b-41cd-85e0-fdd085ed2520`, catalog `demo_prod`, gold only, autoSync Enabled. Skill: common/ITEM-DEFINITIONS-CORE.md Other Item Types and its mirrored Azure Databricks definition spec. Data-table verification pending.

- 2026-11-22T19:07:01+00:00: Created/verified owned Prod `LH_Landing`: `dffa5f8d-1221-4a23-9e5f-a693701b7eb7`; skill references: fabric-skills/common/COMMON-CORE.md; COMMON-CLI.md; SPARK-AUTHORING-CORE.md; skills/dataflows-cli/references/authoring/connection-management.md.

- 2026-11-22T19:07:16+00:00: Prod `LH_Landing` Check: schema-enabled dbo, OneLake paths and SQL endpoint Success PASS.

- 2026-11-22T19:07:28+00:00: Created/verified owned Prod `LH_Curated`: `4e5c9ace-eea9-4796-94b6-48e3c1e55d91`; skill references: fabric-skills/common/COMMON-CORE.md; COMMON-CLI.md; SPARK-AUTHORING-CORE.md; skills/dataflows-cli/references/authoring/connection-management.md.

- 2026-11-22T19:07:43+00:00: Prod `LH_Curated` Check: schema-enabled dbo, OneLake paths and SQL endpoint Success PASS.

- 2026-11-22T19:09:35+00:00: Starting prod/ingest fabric-cicd deployment with per-write context guards. Lakehouse/mirror preparation and shortcuts use their supported post-deploy APIs; no orphan deletion or paid-resource creation.

- 2026-11-22T19:11:24+00:00: prod/ingest metadata deployment PASS: NB_Clean_Forecast, NB_Integrate, PL_Refresh, VL_Config. References: common/COMMON-CORE.md; https://microsoft.github.io/fabric-cicd/latest/how_to/parameterization/.

- 2026-11-22T19:13:40+00:00: prod LH_Landing/raw_forecasts target binding PASS; reference: spark-cli common/COMMON-CORE.md OneLake Shortcuts.

- 2026-11-22T19:13:53+00:00: prod LH_Curated/gold target binding PASS; reference: spark-cli common/COMMON-CORE.md OneLake Shortcuts.

- 2026-11-22T19:13:58+00:00: prod ingestion metadata ready: stage shortcuts, Starter Pool/no custom Environment, active Variable Library value set verified. Excel preview standard transformation must be created in the UI if absent; no unsupported payload.

- 2026-11-22T19:46:31+00:00: Scoped SQL metadata refresh did not succeed: `[{"tableName": "forecast.forecast_standard", "status": "Failure", "startDateTime": "2026-11-22T19:46:27.459091Z", "endDateTime": "2026-11-22T19:46:29.6794232Z", "error": {"source": 0, "errorCode": "DeltaTableNotFound", "message": "Delta table 'Tables\\forecast\\forecast_standard\\_delta_log' not found."}}]`; source tables unchanged.

- 2026-11-22T19:46:31+00:00: Forecast metadata refresh blocked: Scoped SQL metadata refresh returned a non-success table status.

- 2026-11-22T19:52:04+00:00: Scoped LH_Landing.forecast SQL metadata refresh checked for forecast_standard; previously synced NotRun tables: ['forecast.forecast_standard']; recreateTables=false; source tables unchanged.

- 2026-11-22T19:53:16+00:00: Started/monitoring DEMO-Analytics-Prod PL_Refresh `c205819d-d65e-4bdb-a521-a4240136188f`.

- 2026-11-22T19:55:44+00:00: DEMO-Analytics-Prod PL_Refresh Completed; both notebook dependencies honored.

- 2026-11-22T19:58:34+00:00: prod LH_Landing/raw_forecasts target binding PASS; reference: spark-cli common/COMMON-CORE.md OneLake Shortcuts.

- 2026-11-22T19:58:39+00:00: prod LH_Curated/gold target binding PASS; reference: spark-cli common/COMMON-CORE.md OneLake Shortcuts.

- 2026-11-22T19:58:52+00:00: prod LH_Curated/forecast_clean target binding PASS; reference: spark-cli common/COMMON-CORE.md OneLake Shortcuts.

- 2026-11-22T19:58:59+00:00: prod ingestion metadata ready: stage shortcuts, Starter Pool/no custom Environment, active Variable Library value set verified. Excel preview standard transformation must be created in the UI if absent; no unsupported payload.

- 2026-11-22T19:59:49+00:00: Starting prod/analytics fabric-cicd deployment with per-write context guards. Lakehouse/mirror preparation and shortcuts use their supported post-deploy APIs; no orphan deletion or paid-resource creation.

- 2026-11-22T20:03:56+00:00: prod/analytics metadata deployment PASS: DA_Sales, ONT_Business, RPT_Sales, SM_Sales. References: common/COMMON-CORE.md; https://microsoft.github.io/fabric-cicd/latest/how_to/parameterization/.

- 2026-11-22T20:07:24+00:00: Started/monitoring SM_Sales refresh `f19053a1-fad7-42de-abbc-b4e3c01a8abf`.

- 2026-11-22T20:07:58+00:00: SM_Sales initial refresh and seven-measure live check PASS: `{"[Actual hl]": 4488091.02, "[Forecast hl]": 2286058.24, "[Deviation hl]": -188035.14, "[Deviation %]": -0.0822529963191139, "[Revenue EUR]": 288517979.92, "[Margin EUR]": 76975278.66, "[Margin %]": 0.26679543050087773, "[Rows]": 10304, "[Calendar days]": 730, "[Stage]": "prod"}`.

- 2026-11-22T20:08:29+00:00: prod analytics bindings PASS: stage-local Direct Lake/SSO, report model/pages, ontology-only Data Agent. Model live baseline query verified the stage marker and row count.

- 2026-11-22T20:11:34+00:00: Published Prod DA_Sales `40265df6-63e2-45a4-9dfa-865a134e3cdc` for MCP querying, not Agent Store/M365. Ontology-only draft preserved. References: fabric-skills/common/COMMON-CORE.md; https://learn.microsoft.com/rest/api/fabric/dataagent/items/publish-data-agent; https://learn.microsoft.com/fabric/data-science/fabric-data-agent-sdk.

- 2026-11-22T20:14:41+00:00: Prod Data Agent verification blocked: ExceptionGroup('unhandled errors in a TaskGroup', [ExceptionGroup('unhandled errors in a TaskGroup', [AttributeError("'Tool' object has no attribute 'inputSchema'")])])

- 2026-11-22T20:17:56+00:00: Prod Data Agent answer did not match the requested exact baseline. Question: Using ONT_Business and its bound data, for all regions, channels and packages from January 2025 through October 2026 inclusive, give total actual volume in hl, total revenue EUR, total contribution margin EUR, and env_marker. Use exact decimal totals, not abbreviated millions. State the period and units. Answer: There’s content here I can’t work with. Try asking a new question. If that doesn’t work, there might be an issue with the content in your source data.

- 2026-11-22T20:17:56+00:00: Prod Data Agent verification blocked: A real Data Agent answer omitted or differed from the verified baseline.

- 2026-11-22T20:30:02+00:00: GitHub metadata-only CI controls PASS: Prod environment `28183792552` requires owner review; main requires PR/validate with admin bypass. Existing Test environment and OIDC variables preserved; no tenant settings or permission grants. References: https://docs.github.com/rest/deployments/environments; https://docs.github.com/rest/branches/branch-protection; https://cli.github.com/manual/gh_variable_set.

- 2026-11-22T20:41:42+00:00: OIDC check FAILED: `https://github.com/rishabhmonga119/fabric-demo-platform/actions/runs/45067822040`.

- 2026-11-22T20:54:13+00:00: Capacity Reader grant blocked: az.CMD role assignment list --assignee-object-id e4234475-0f90-44c2-b256-20ce1b6c7614 --scope /subscriptions/61ab2275-fb68-4081-ac0f-076c87caf0c1/resourceGroups/fabric-demo-rg/providers/Microsoft.Fabric/capacities/capacityswitzerlandnorth --all --fill-principal-name false --output json failed (exit 1): ERROR: group or scope are not required when --all is used

- 2026-11-22T20:55:49+00:00: Explicitly approved capacity-only Azure Reader grant PASS: `/subscriptions/61ab2275-fb68-4081-ac0f-076c87caf0c1/resourceGroups/fabric-demo-rg/providers/Microsoft.Fabric/capacities/capacityswitzerlandnorth/providers/Microsoft.Authorization/roleAssignments/d0661003-3606-5499-82b6-f2438517dd4d` for `e4234475-0f90-44c2-b256-20ce1b6c7614` at `/subscriptions/61ab2275-fb68-4081-ac0f-076c87caf0c1/resourceGroups/fabric-demo-rg/providers/Microsoft.Fabric/capacities/capacityswitzerlandnorth`. No Contributor/Admin, subscription role, resize or resource creation. References: fabric-skills/common/COMMON-CORE.md; https://learn.microsoft.com/cli/azure/role/assignment#az-role-assignment-create.

- 2026-11-22T21:12:27+00:00: Prod Data Agent MCP answer PASS. Question: What are total actual sales volume in hl, total net revenue in EUR, and total contribution margin in EUR from January 2025 through October 2026 inclusive? Include all regions, channels, products and packages. Show exact decimal totals, not abbreviated millions, and state the period and units. Answer: Period and scope used:
- Period: January 2025 through October 2026 inclusive (monthly SalesPeriod data)
- Scope: All regions, all channels, all products, all packages

Totals (exact, not abbreviated):
- Total actual sales volume: **4,488,091.02 hl**
- Total net revenue: **288,517,979.92 EUR**
- Total contribution margin: **76,975,278.66 EUR**

- 2026-11-22T21:12:58+00:00: Prod Data Agent MCP answer PASS. Question: What is the revenue-weighted contribution margin percentage across all regions, channels and packages for January 2025 through October 2026 inclusive? Calculate total margin divided by total revenue, not an average of percentages. Show the percentage to two decimal places. Answer: Revenue-weighted contribution margin percentage from January 2025 through October 2026 (inclusive), across all regions, channels and packages is:

**26.68%**

- **Calculation:**  
  \[
  \text{Margin \%} = \frac{\sum \text{Margin (EUR)}}{\sum \text{Revenue (EUR)}} \times 100
  \]
  using all SalesPeriod rows from **2025-01-01** through **2026-10-01** (month is first-of-month).

- 2026-11-22T21:20:19+00:00: Step 6 metadata-only OIDC/SDK preflight for both PASS; no workspace changes; `https://github.com/rishabhmonga119/fabric-demo-platform/actions/runs/45071446452`.

- 2026-11-23T07:08:56+00:00: Step 7 prerequisite Check PASS: Prod identities/Active F4, Fabric-runtime publication, existing sales-group Viewer memberships and enabled Power BI/Copilot plans. No cloud writes, grants, licences or duplicate agent publication. Agent Store/Teams/Agent Builder/viewer-session checks require the human checkpoint. References: fabric-skills/common/COMMON-CORE.md; https://learn.microsoft.com/rest/api/fabric/dataagent/items/get-data-agent; https://learn.microsoft.com/rest/api/fabric/core/workspaces/list-workspace-role-assignments; https://learn.microsoft.com/fabric/data-science/data-agent-microsoft-365-copilot; https://learn.microsoft.com/fabric/iq/connectors/agent-builder-overview.
## 2026-11-23 - Step 9: Technical baseline preparation

Status: SNAPSHOTS AND PREPARED FALLBACK VERIFIED; the final gated aggregate
verification/sealing command is the remaining technical action. No final
baseline tag is claimed yet. The user explicitly said **"skip that step!"** in response to
the recordings prerequisite; recordings are skipped, not marked as recorded.

- `python tools/prepare_fallback.py` passed all three real query-scoped
  validations (computed result, zero actual, missing forecast) without
  persisting a measure or refreshing a model. Created/pushed
  `demo/forecast-accuracy-prepared` and `demo-prepared-change`, both verified
  remotely at **3e4ae643d714c36b757cf0ac85e7d75cbb857427**. Only the local
  prepared measure and draft agent instruction files changed; main/live
  models stayed baseline. The owned temporary worktree was removed.
- Final sealing command, executed after this readiness commit is pushed:
  `python tools/verify.py --all --seal`. It refuses to create the tag on any
  failed prerequisite/check, and verifies remote main/tag equality last.
  The actual tag and final stdout audit are authoritative for the result;
  appending another tracked log commit after sealing would break the required
  `main == demo-baseline` invariant.
- Captured actual OneLake policies/members for 10 items: Landing, Curated and
  Gold mirror in Dev/Test/Prod, plus LH_PartnerA. Snapshot:
  `config/onelake_roles.baseline.json`. Volatile server-generated role IDs are
  deliberately excluded from restore payloads/comparison; all decision rules,
  constraints and members are preserved. Approved Prod Curated sales-group
  baseline memberships are validated, not re-granted.
- Captured actual SharePoint metadata for exactly 18 known/verified standard
  and raw workbooks in `seed/manifest.json`, including IDs, ETags, sizes and
  independently known seed hashes. Live-only December files are absent.
  Existing changed versions require exact sheet/cell equality; unchanged
  uploaded versions are not needlessly downloaded again. No Graph writes,
  new consent or source file replacement.
- Added immutable, repository-bounded snapshot writing: dry-run has no file
  writes and a different existing baseline stops rather than being replaced.
  A Windows short-temp-path versus canonical-path test fixture was corrected.
  Roles/file dry-runs and captures passed. Existing independently verified
  `seed/expected_counts.json` is retained unchanged.
- Added `tools/verify.py --all` and optional `--seal`, with a non-deploying
  `tools/verify_baseline.py` implementation. It checks Git/main/prepared refs,
  actual Gold seed fingerprints/policies, actual SharePoint files and OneLake
  policies, all 11 items and bindings per stage, current seven-measure model
  results, report pages, last pipeline state, ontology-only agents, current
  physical SQL data and the completed scoped partner rehearsal.
- SQL checks use the documented global SQL Endpoint **MCP** through the
  installed SDK and the verified tenant-A CLI identity, with the sqldw skill
  header on every transport request. They do not use an unrelated browser
  account, saved credentials, sqlcmd, fabricated SQL REST payloads or cached
  notebook metrics as current table counts. A live probe of current partner
  output returned **1,232 / 1,121,803.72**. Exact CSV result parsing is tested.
- Existing model query validation and Gold verification are reused without
  refresh/deployment; Gold verification can send audit to stdout so final
  checks don't dirty the sealed Git worktree. Only the already-owned,
  guarded 2X-Small serverless Databricks verification warehouse is used and
  stopped afterward; F4 isn't resized.
- Added `tools/prepare_fallback.py`: only the Forecast Accuracy measure and
  draft Data Agent guidance are changed in an owned temporary worktree.
  The formula follows the supplied actual-denominator definition, returns 0
  for zero actual, and stays blank for missing actual/forecast. Three
  query-scoped validations don't persist any live measure. Existing opaque
  Prep data for AI metadata remains untouched. The agent-language alias is
  not misrepresented as a Power BI AI-schema synonym; that optional synonym
  requires supported human UI configuration.
- Validation so far: **6 focused baseline tests passed**, covering immutable
  snapshots, complete role preservation, durable manifest scope, exact MCP
  CSV shape/decimal preservation, seven-measure baseline enforcement and
  isolated feature generation. Aggregate/fallback `--dry-run` passed.
- Next bounded commands after a clean pushed checkpoint:
  `python tools/prepare_fallback.py`, then
  `python tools/verify.py --all --seal`. Sealing happens only after full
  technical checks pass; remote main/tag equality is checked last. Final
  audit remains in stdout/Git refs rather than moving main with another log
  commit after its tag.
- Full `tools/reset/` orchestration remains an unimplemented specification
  and is explicitly labelled as such, not falsely claimed delivered by
  baseline capture. Corrected stale reset workflow inputs and the demo's
  metadata-only CI/publication description.

## 2026-11-23 - Step 8: Output-only partner producer

Status: VERIFIED FOR THE SELECTED IQ SHARING PATH. The consumer baseline,
fresh post-revocation denial and consumer-side cleanup are user-confirmed.
The approved rehearsal producer Share was deleted and its absence verified.
No consumer
Share Subscription, B2B guest, workspace-role grant or partner reader-role
membership was created by this automation.
Step 9 remains pending; no baseline tag or recording is claimed.

- Consumer baseline follow-up: the user accepted into tenant B, confirms
  subscription/shared items Active, and confirms the SQL query returned the
  expected **1,232 rows and 1,121,803.72 hl**. The producer's recipient API
  independently reports **Accepted** (not the documentation example's
  `Active` recipient value). Consumer SQL values are user-confirmed, not an
  administrator query impersonating the consumer. Approved producer Share
  cleanup has completed. The user's fresh consumer query then failed with
  **Msg 24701: access denied on dbo.partner_a_deliveries** (and diagnostic
  Msg 15806), proving the shared data read was revoked. Its OneLake error
  identifies consumer Mirrored OneLake item
  `e2e0fb49-be9d-45d5-aa79-1a9b6882a630`. The user subsequently confirms the
  rehearsal subscription and related mirrored item have been removed.
  Existing tenant-B workspace and unrelated items were left intact.
  B2B guest/Partner_A_Read fallback is not configured in this selected-path
  baseline; it requires separately approved invitation and data grants.
- Cleanup commands: `python tools/manage_partner_share.py delete --dry-run`,
  then `python tools/manage_partner_share.py delete --approved-rehearsal-cleanup`.
  The exact asset/recipient/expiry was reread before deleting only Share
  `8343ea43-7fe0-4b23-9a1b-0c4ce64791ff`; API absence readback passed.
  No producer lakehouse, table, notebook, existing inbound workspace or
  consumer item was deleted by the automation. All 13 partner tests passed.
  Consumer-side deletion of the rehearsal Share Subscription unsubscribes and
  removes its related Mirrored OneLake items, per
  <https://learn.microsoft.com/fabric/onelake/iq-share/manage-share-subscription>.

- Tenant B details are now supplied and stored as IDs/domain/inbound workspace
  in configuration. Public OpenID discovery confirms the supplied domain maps
  to tenant `e3722af7-9524-4604-88d1-6940e5abe26c`. The user confirms Share
  Subscription is enabled and provides inbound workspace
  `8e547d7e-ac1f-4404-aaeb-427c11b8a8fc`; the actual consumer session/capacity
  and roles are not independently verified yet. Keep tenant-A CLI identities.
- User explicitly approved one rehearsal Share to the supplied named
  recipient, expiration **2026-11-30T23:59:59Z**, followed by scoped
  revocation/deletion after validation. The recipient address is held only in
  a process-local environment variable, not committed to this public repo.
- Created `SH_PartnerA_Rehearsal`
  `8343ea43-7fe0-4b23-9a1b-0c4ce64791ff` using the documented Share API and
  Microsoft's published `share.json`/common JSON schemas. GetDefinition
  readback exactly matches one asset (the output-only LH_PartnerA), one named
  tenant-B recipient, MirroredOneLake representation and the approved
  expiration. At creation, Share state was **Active** and recipient
  acceptance was **Pending**; see the accepted/query/cleanup follow-ups above.
  The private invitation URL is printed only to the caller, not logged or
  committed. No access to Prod or additional items was shared.
- Added `tools/manage_partner_share.py` with dry-run, explicit external-grant
  and cleanup gates, identity/capacity/ownership checks, complete paginated
  OneLake Tables/Files inventory, exact glossary-text verification, LRO
  operation persistence/resume, exact Share definition readback and
  recorded-ID-only cleanup. Read-only status reuses the existing Share.
  Commands: `python tools/manage_partner_share.py create --expires-utc 2026-11-30T23:59:59Z --dry-run`;
  the same command with `--approved-external-share`; `python tools/manage_partner_share.py status`.
- Diagnostics resolved before/after creation without expanding scope:
  List Tables rejects schema-enabled lakehouses, so preflight uses documented
  OneLake storage listing instead. Local Git CRLF versus Fabric LF required
  comparing glossary text as the notebook does. The live API returns
  `app.powerbi.com/iqshare/accept` rather than the conceptual documentation's
  `app.fabric.microsoft.com/share/invite/...`; validation supports both and
  binds the live Power BI URL to the exact producer tenant/workspace/Share IDs.
  The created Share was inspected, not recreated, after this URL-shape error.
- **13 focused partner tests passed**, including external grant approval
  gating, exact Share scope/expiry, whole-item disclosure guards and
  matching-first-party invitation validation. Skill references:
  `e2e-medallion-architecture/SKILL.md`, `common/COMMON-CORE.md`,
  `common/COMMON-CLI.md`. API/schema references:
  <https://learn.microsoft.com/rest/api/fabric/share/items/create-share>,
  <https://learn.microsoft.com/rest/api/fabric/share/items/get-share-definition>,
  <https://developer.microsoft.com/json-schemas/fabric/item/share/definition/share/1.0.0/schema.json>,
  <https://developer.microsoft.com/json-schemas/fabric/item/share/definition/common/1.0.0/schema.json>.
  Final status again reports recipient Pending, without a second create.
  `git diff --check` passed. A bounded repository check found neither the
  private recipient address nor the actual invitation URL in committed inputs.

- User approved **output-only LH_PartnerA**. Corrected the original delivery
  source mismatch: sales_vs_forecast has no delivery measures. The notebook
  reads the existing internal Prod Curated `gold.fact_deliveries` and
  `gold.dim_product` shortcuts without modifying Prod. It filters P-A before
  projecting the exact seven-column contract; it never joins deliveries
  through sales or stores unfiltered inputs in the partner lakehouse.
- This layout is required for IQ Sharing: the whole item is shared and the
  producer's OneLake security roles are not honored for consumer access.
  Corrected the current **+ New item -> Share (preview)** creation path,
  distinct from ordinary item Share, and the consumer-side lakehouse-shortcut
  requirement for notebook/model consumption.
  References:
  <https://learn.microsoft.com/fabric/onelake/iq-share/onelake-share-overview>,
  <https://learn.microsoft.com/fabric/onelake/iq-share/create-share>,
  <https://learn.microsoft.com/fabric/onelake/iq-share/accept-share>.
- Created owned schema-enabled `LH_PartnerA`
  `56048088-1c7a-42ab-8120-41da7f3879b3`, SQL endpoint
  `52a81fe9-2b65-4eb7-868a-29e7849932cb`, and pure-Python
  `NB_Partner_Extract` `cf84484d-58e7-4693-a622-caada58aaf0c` in the
  existing `DEMO-Partner-A` workspace on Active F4. No new Azure paid resource,
  Environment, Spark pool, capacity resize or Dev/Test/Prod mutation.
- The notebook compares every persisted Delta row to the filtered P-A
  projection, verifies the exact Arrow schema, and reads back the glossary.
  Actual completed-job exit metrics: **1,232 rows**, **1,121,803.72 hl**,
  Jan 2025-Oct 2026, regions EAST/NORTH. Columns exactly:
  `month, sku, product_name, package_code, region_code, delivered_hl, on_time_pct`.
  No revenue, margin, forecast or partner-id column is exported. A final live
  metadata read confirms **zero shortcuts** in the output lakehouse.
- Separate `partner/` definitions and glossary are source-controlled; local
  `tools/bootstrap_partner.py` supports dry-run and optional execution, owns
  its targets, validates source bindings, stores IDs/job IDs, prevents
  concurrent duplicate jobs and reuses recent unchanged completed runs.
  The existing pipeline job monitor was extracted into a shared item-job
  helper; focused tests preserve its Pipeline route and notebook resume
  behavior. Existing analytics runtime defaults remain unchanged; only the
  new notebook supplies partner workspace/lakehouse overrides.
- Commands: `python tools/bootstrap_partner.py --dry-run --run`;
  `python tools/bootstrap_partner.py --run`;
  `python -m unittest discover -s tests -p test_partner.py -v`.
  **8 focused tests passed**, covering projection and source/quality rejection,
  notebook binding, job routing/resume, exact baseline thresholds, exit-value
  shape and safe owned-item discovery.
- Two automation diagnostics were corrected without permission escalation:
  the live Python job returns `properties.exitValue`, whereas the Learn
  conceptual example shows top-level `exitValue`; both are validated strictly.
  The auto-created SQL endpoint shares the lakehouse's display name, so
  ownership resolution must filter by **type and name**, then verify owner/ID.
  The actual notebook jobs completed; these failures were in local readback
  and idempotent discovery, not permission or source-data failures.
- Read-only tenant-A preflight: `AllowExternalDataSharingSwitch` and
  `ArtifactIQSharePreview` are already enabled only for the existing Demo
  Fabric Admin/API groups. `ArtifactConsumerIQSharePreview` is disabled and
  was left unchanged: tenant A only needs to produce the share. Switzerland
  North isn't excluded by current IQ Sharing region documentation.
  Read-only skill reference:
  `onelake-catalog-cli/references/admin-audit.md`; existing settings API
  contract is also used by `tools/bootstrap_fabric.py`. Final existing-item
  `--dry-run --run` and `git diff --check` passed.
- Earlier producer-only human checkpoint (tenant-B details now supplied above):
  provide tenant B ID/domain, invited recipient and an
  existing capacity-backed `PARTNER-Inbound` workspace. Tenant B's admin must
  enable **Enable Share Subscription Item (preview)**, and the accepting
  recipient needs Admin/Member/Contributor on that workspace. Tenant B's
  settings/roles and actual acceptance aren't yet verified. Keep tenant-A CLI
  sign-ins unchanged. Share/guest creation and any new grant require approval;
  rehearsal revocation/deletion must be scoped to the artifacts we create.

## 2026-11-23 - Step 7: Copilot publication prerequisites

Status: VERIFIED. Publication, report/Fabric IQ, ontology instances and the
published ontology-backed DA_Sales viewer answer are user-confirmed.
Step 8 producer is built and verified; tenant B sharing is pending. Step 9 is pending.

Step 7 final viewer check: after both sales groups received the approved
Prod SM_Sales Read+Build grant, Aadi confirmed that SalesPeriod Instances load
successfully. A new published DA_Sales Copilot conversation then returned:
North **52,840.60 hl**, South **49,069.04 hl**, West **45,708.11 hl**,
East **41,653.64 hl**, total **189,271.39 hl** for October 2026.
All four regions and the total exactly match the verified baseline. This is
the actual ontology-backed Data Agent check, distinct from native Fabric IQ.
The earlier complete checkpoint covered the user's reported actions, but the
subsequent Plugins screenshot establishes that the distinct Data Agent path
still needed its own check. Do not treat Fabric IQ success as DA_Sales success.
The intermediate failure notes below are retained as investigation history,
not the current status.

- The viewer's `SalesPeriod` -> Instances screenshot shows a generic retrieval
  error, request ID `Ontology;7537e3d6-5c6f-4ec5-9b82-4a84fe3bfe21`.
  The read-only banner is expected for workspace Viewer, not proof that editing
  permission is needed. Supporting Eventhouse/KQL access is already
  Read+ReadData and GraphModel access is already Read for both sales groups.
  Their supporting item IDs are Eventhouse
  `1b63266b-53a5-4f8a-9ae2-550887dde490`, KQLDatabase
  `dee1b8e3-7c14-49f7-a93b-888aebc61230`, GraphModel
  `a97b801b-4dbc-493f-9343-1de1976f9a18`. No supporting-item grant was made.
- Read-only deployed ontology definition inspection confirms SalesPeriod
  binds to Prod SM_Sales `fcd20b15-77e8-4493-970e-0c4555b56cf7`
  in workspace `4cd2247c-ab4c-441a-9637-f3c3d525f4c1`, not Dev/Test.
  The specific Microsoft ontology documentation requires **Read and Build
  to query semantic models using ontology**:
  <https://learn.microsoft.com/fabric/iq/ontology/how-to-generate-from-semantic-models>.
  The earlier general Data Agent Read-only guidance was incomplete for this
  ontology-backed path. Missing Build is a documented prerequisite gap;
  it is not proof the entire runtime issue is resolved.
- User explicitly approved Read+Build on **Prod SM_Sales only, for both sales
  groups**, after disclosure that Build also enables report creation and
  Analyze in Excel. Implemented an approval-gated, idempotent script with
  dry-run, identity/capacity/item/Viewer checks and exact group permission
  readback. No Write/Reshare, workspace promotion, SSO or OneLake change,
  ontology replacement, or Dev/Test modification is authorized by this grant.
- Validation: 11 focused ontology-reader/shared API safety tests passed with
  `python -m unittest discover -s tests -p test_fabric.py -k OntologyReaderTests -k JsonApiGuardTests -v`.
  `python tools/grant_ontology_readers.py --dry-run` planned exactly two PUTs.
  `python tools/grant_ontology_readers.py --approved-prod-ontology-build`
  verified Azure/Fabric/GitHub identities before each PUT and read back
  **ReadExplore** for North and South. No Write or Reshare was granted.
  Config now records the group IDs and marks the real viewer check pending.
  A subsequent live `--dry-run` planned **zero** writes, verifying idempotence.
  `git diff --check` passed.

- The user reports that the previously supplied report link was wrong for
  their session. Opening the report from the Prod workspace worked as the
  configured North viewer, and M365 Copilot using Fabric IQ then returned data.
  Use the workspace-opened report as the verified viewer entry point. No
  further connection, credential, policy or permission change was made to
  obtain this successful result. The precise earlier link/context discrepancy
  was not independently established; do not claim a repaired credential fault.
- Microsoft Copilot publication and agent creation/sharing were previously
  confirmed by the user; admin Teams/M365 answers were evidenced in screenshots.
  The previously missing viewer report/Fabric IQ check is now user-confirmed.
- Fabric IQ/Sales Assistant uses Power BI report/semantic-model context.
  DA_Sales remains a separate ontology-only data agent. Native Fabric IQ
  success does not imply it queried DA_Sales.
- No baseline tag is created yet. Continue Step 8 before Step 9 acceptance.
- The viewer could query the model through Fabric IQ but did not find DA_Sales
  while searching Plugins. Publishing to Microsoft Copilot does not
  automatically install the agent for every viewer. Next supported action:
  copy DA_Sales's **Copilot agent** share link from the admin's Copilot and
  open/add it under the viewer account; use Agents, not only Plugins search.
  Do not substitute the report URL or assume new Fabric permissions are needed.
  No M365 access grant or tenant setting was changed.
- Step 8 read-only preparation verified an empty DEMO-Partner-A workspace on
  the existing F4 and the real Prod delivery source schema. P-A has 1,232
  delivery rows, Jan 2025-Oct 2026, 1,121,803.72 hl. No partner item has
  been created yet; no partner or cross-tenant access has been granted.

Follow-up from the user's live UI checks:

- The user reports the same authentication error after a fresh Aadik sign-in.
  A read-only, two-hour, latest-20 Entra sign-in query for the configured viewer
  showed a successful Microsoft Power BI interactive sign-in at 07:46:21 UTC,
  status code 0, Conditional Access success and MFA satisfied by token claim.
  This validates that interactive sign-in only, not the downstream OneLake
  connection or non-interactive token exchange. No new audit permission,
  account change or policy exception was requested or granted.
- Do not repeat browser sign-ins as the fix or broaden permissions. The next
  human credential diagnostic is the model owner's Gateway and cloud
  connections / Data source credentials settings. Preserve end-user SSO,
  ontology-only DA_Sales and existing data roles. Step 7 remains blocked;
  Steps 8-9 remain unstarted.
- Expanded viewer error at 2026-11-23 07:49 UTC: HTTP 400,
  `Premium_ASWL_Error`; Power BI says Entra ID authentication failed for the
  current user and explicitly requests signing into Power BI again to update
  credentials. Correlation ID `c10fd017-ecdc-2125-81df-5f2c854d0a45`.
  This is not evidence of an on-premises source. Existing approved OneLake
  memberships were independently read back and remained intact.
- Paused permission/connection changes and automated query retries for the
  credential error. Required human action is a fresh Power BI sign-in for
  the configured North viewer in its separate browser session, followed by
  opening the report before retrying Copilot. Do not change the automation's
  administrator sign-ins, disable SSO, or substitute administrator credentials.
- The user explicitly approved adding only the North/South sales groups to
  Prod LH_Curated DefaultReader. Added `tools/grant_baseline_readers.py`,
  ran its dry-run, then `--approved-prod-baseline-read`. The update used a
  fresh quoted role-collection ETag in If-Match and exact readback passed.
  Existing virtual members, other explicit members and unrestricted Read
  policy were preserved. No other role, mirror, connection, SSO, tenant,
  workspace role or Dev/Test item was changed. North viewer retest is pending.
- Extended the shared API helper to preserve ETags and accept If-Match.
  Focused API/concurrency and membership-addition/idempotency/restricted-policy
  guard tests passed (11). Updated Act 6 to remove North's unrestricted
  membership before applying its restricted role, because grants are additive.
- Commands: `python -m py_compile tools/grant_baseline_readers.py tools/http_api.py`;
  `python tools/grant_baseline_readers.py --dry-run`;
  `python tools/grant_baseline_readers.py --approved-prod-baseline-read`.
  Official role-update/member contract:
  https://learn.microsoft.com/rest/api/fabric/core/onelake-data-access-security/create-or-update-data-access-roles.
- Further M365 Copilot screenshot shows Sales Assistant returning the same
  correct regional figures and total under the administrator, with RPT_Sales
  Prod cited. Teams and M365 administrator paths are confirmed by the user's
  screenshots; the North-viewer source-data gap remains. Prerequisite reruns
  now preserve human/UI verification statuses instead of resetting them.
- The user initially confirmed the four M365 actions, then supplied a failed
  Fabric IQ response under the North viewer. Keep Step 7 open: prerequisite
  checks did not verify effective OneLake access for that viewer.
- The current Data Agent publish dialog says **Also publish to Microsoft
  Copilot**, not **Publish to Agent Store**. Updated the setup guidance and
  script output to match the supplied screenshot. Runtime publication and
  Microsoft Copilot availability remain distinct checks.
- User's administrator Teams screenshot and an independent Fabric IQ query
  both returned October 2026 actual hl by region: North 52,840.60, South
  49,069.04, West 45,708.11, East 41,653.64; total 189,271.39 hl.
  This verifies the administrator path, not Aadik's viewer-session path.
- Live model metadata shows `isOnPremGatewayRequired=false` and an Automatic
  AzureDataLakeStorage connection to Prod OneLake. Copilot's earlier
  "on-premises source" description is not supported by this configuration.
- Read-only item-access/OneLake role diagnostics found both sales groups
  have only Read/ViewOutput on LH_Curated, not ReadAll. Its only role,
  DefaultReader, includes virtual ReadAll members, with no explicit sales
  group members. MIR_UC_Gold's DefaultReader instead includes virtual Read
  members. Direct Lake on OneLake uses each viewer's identity and requires
  source data-plane access. No Build escalation is justified by Fabric IQ's
  documentation, which explicitly does not require Build.
- No permissions, connections, sources, tenant settings or Dev/Test items
  were changed by this diagnosis. A new OneLake membership grant requires
  explicit approval. If an unrestricted baseline role is granted, Act 6 must
  remove the North group from that role before adding its restricted role:
  grant roles are additive, not overriding restrictions.
- References:
  `onelake-catalog-cli/references/admin-audit.md`;
  `semantic-model-authoring/references/connection-binding.md`;
  https://learn.microsoft.com/rest/api/fabric/admin/items/list-item-access-details;
  https://learn.microsoft.com/fabric/fundamentals/direct-lake-security-integration;
  https://learn.microsoft.com/fabric/iq/connectors/fabric-iq-mcp.

- Resumed from pushed Step 6 checkpoint `6045baf56b6ac22f5e8e37d3560476abd235937e`.
  Worktree was clean; Azure/Fabric DEMO administrator and GitHub owner contexts
  passed. No Dev/Test item was changed.
- Added idempotent `tools/check_copilot_publication.py` with `--dry-run`.
  Verified the existing Prod workspace/item IDs, Active F4, and DA_Sales
  Fabric-runtime publication. That publication does not prove Agent Store
  publication or M365 discoverability.
- Verified the configured North/South users remain members of their approved
  sales groups and both groups have Prod Viewer, without granting access.
  Presenter and both viewer accounts have enabled Power BI Pro and M365
  Copilot service plans. No licence purchase or assignment is needed.
- Commands: `python tools/check_context.py --dry-run`;
  `python tools/check_demo_licenses.py --dry-run`;
  `python -m py_compile tools/check_copilot_publication.py`;
  `python tools/check_copilot_publication.py --dry-run`;
  `python tools/check_copilot_publication.py`.
  Syntax and minimal live prerequisite checks passed; no routine suite rerun.
- Stored Step 7 prerequisite results and explicit pending-human verification
  states in environments.yml. Do not mark the step complete on API prerequisites
  alone, and do not create the demo-baseline tag before Steps 7-9 acceptance.
- Required human actions: publish Prod DA_Sales to Agent Store, pin/test it in
  M365/Teams, create Sales Assistant with the native Fabric/Power BI capability
  and share it with both sales groups, then verify an October 2026 region query
  in a separate North-viewer browser session. Keep the CLI admin context intact.
- Preserve DA_Sales as ontology-only. Sales Assistant's Fabric IQ capability
  independently uses permitted Power BI artifacts; it is not a source change
  to DA_Sales.
- Skills loaded from
  `C:\Users\rishabhmonga\.copilot\installed-plugins\fabric-collection\fabric-skills\skills\e2e-medallion-architecture\SKILL.md`;
  Fabric reference: `fabric-skills/common/COMMON-CORE.md`.
  Official contracts:
  https://learn.microsoft.com/rest/api/fabric/dataagent/items/get-data-agent;
  https://learn.microsoft.com/rest/api/fabric/core/workspaces/list-workspace-role-assignments;
  https://learn.microsoft.com/fabric/data-science/data-agent-microsoft-365-copilot;
  https://learn.microsoft.com/fabric/iq/connectors/agent-builder-overview.


- 2026-11-23T07:43:04+00:00: Approved Step 7 Prod LH_Curated DefaultReader membership grant/readback PASS: SG-Demo-Sales-North, SG-Demo-Sales-South. Existing virtual ReadAll membership and unrestricted Read policy preserved; no Build/Contributor, SSO/connection, mirror, tenant or Dev/Test change. Viewer-session retest is still required. Skill: e2e-medallion-architecture/common references; https://learn.microsoft.com/rest/api/fabric/core/onelake-data-access-security/create-or-update-data-access-roles.

- 2026-11-23T09:00:04+00:00: Approved Step 7 ontology reader PUT: Prod SM_Sales (fcd20b15-77e8-4493-970e-0c4555b56cf7), group ad4dc1e3-8180-4f7f-98fa-1134f37cc239, ReadExplore. No Write/Reshare or workspace-role change.

- 2026-11-23T09:00:13+00:00: Approved Step 7 ontology reader PUT: Prod SM_Sales (fcd20b15-77e8-4493-970e-0c4555b56cf7), group 199f4419-549f-4f29-9e4a-33a25afc0a36, ReadExplore. No Write/Reshare or workspace-role change.

- 2026-11-23T09:00:16+00:00: Approved Step 7 Prod SM_Sales Read+Build readback PASS for both sales groups. Ontology-bound semantic-model queries require Read+Build, unlike the general direct Data Agent semantic-model Read prerequisite. Workspace Viewer, SSO, OneLake roles, ontology-only DA_Sales and Dev/Test are unchanged. Real North viewer instance and agent checks remain pending. References: semantic-model-authoring/references/semantic-model-rest-api.md, Permissions; https://learn.microsoft.com/fabric/iq/ontology/how-to-generate-from-semantic-models; https://learn.microsoft.com/rest/api/power-bi/datasets/put-dataset-user-in-group; https://learn.microsoft.com/rest/api/power-bi/datasets/post-dataset-user-in-group.

- 2026-11-23T09:24:28+00:00: Step 8 output-only producer items ready: LH_PartnerA 56048088-1c7a-42ab-8120-41da7f3879b3, NB_Partner_Extract cf84484d-58e7-4693-a622-caada58aaf0c, Python kernel, existing F4. No shortcuts in output, permissions, external sharing or Prod writes. References: spark-cli/references/authoring.md; spark-cli/references/authoring/resources/notebook-api-operations.md; fabric-skills/common/COMMON-CORE.md; SPARK-AUTHORING-CORE.md; https://learn.microsoft.com/fabric/onelake/iq-share/onelake-share-overview.

- 2026-11-23T09:24:38+00:00: Started/monitoring DEMO-Partner-A NB_Partner_Extract `46ce5bda-669a-4126-b179-f3f0cf659b1d`.

- 2026-11-23T09:25:40+00:00: DEMO-Partner-A NB_Partner_Extract Completed.

- 2026-11-23T09:25:42+00:00: Step 8 partner producer blocked: Completed notebook has no documented verification exit value.

- 2026-11-23T09:30:11+00:00: Step 8 partner producer blocked: Existing LH_PartnerA is unowned or conflicts with configuration.

- 2026-11-23T09:34:12+00:00: Step 8 output-only producer items ready: LH_PartnerA 56048088-1c7a-42ab-8120-41da7f3879b3, NB_Partner_Extract cf84484d-58e7-4693-a622-caada58aaf0c, Python kernel, existing F4. No shortcuts in output, permissions, external sharing or Prod writes. References: spark-cli/references/authoring.md; spark-cli/references/authoring/resources/notebook-api-operations.md; fabric-skills/common/COMMON-CORE.md; SPARK-AUTHORING-CORE.md; https://learn.microsoft.com/fabric/onelake/iq-share/onelake-share-overview.

- 2026-11-23T09:34:21+00:00: Started/monitoring DEMO-Partner-A NB_Partner_Extract `d65c4002-dc26-4e13-9b05-97b2261d9ef8`.

- 2026-11-23T09:35:23+00:00: DEMO-Partner-A NB_Partner_Extract Completed.

- 2026-11-23T09:35:26+00:00: Step 8 producer Check PASS: notebook completed after exact persisted Delta row comparison against P-A filtered delivery/product projection and exact glossary file readback. Actual exit-value metrics: {"check": "PASS", "table": "dbo.partner_a_deliveries", "rows": 1232, "columns": ["month", "sku", "product_name", "package_code", "region_code", "delivered_hl", "on_time_pct"], "delivered_hl": "1121803.72", "min_month": "2025-01-01", "max_month": "2026-10-01", "regions": ["EAST", "NORTH"], "exact_filtered_row_readback": true, "glossary_readback": true}. Tenant B/sharing/security acceptance remains a human checkpoint; no Share, guest or new grants created.

- 2026-11-23T10:06:33+00:00: Created owned rehearsal IQ Share 8343ea43-7fe0-4b23-9a1b-0c4ce64791ff for the one approved tenant-B recipient; source only LH_PartnerA; expiry 2026-11-30T23:59:59Z. Recipient/invitation kept out of public configuration and logs. References: e2e-medallion-architecture/SKILL.md; fabric-skills/common/COMMON-CORE.md; COMMON-CLI.md; https://learn.microsoft.com/rest/api/fabric/share/items/create-share; https://learn.microsoft.com/rest/api/fabric/share/items/get-share-definition; https://learn.microsoft.com/rest/api/fabric/share/items/delete-share; https://developer.microsoft.com/json-schemas/fabric/item/share/definition/share/1.0.0/schema.json.

- 2026-11-23T10:06:53+00:00: Partner IQ Share action blocked: Share is not Active with a documented Fabric invitation URL.

- 2026-11-23T10:10:42+00:00: Rehearsal Share 8343ea43-7fe0-4b23-9a1b-0c4ce64791ff readback PASS: exact single asset/recipient/expiration, Active invitation. Consumer acceptance/query not yet verified.

- 2026-11-23T10:14:22+00:00: Rehearsal Share 8343ea43-7fe0-4b23-9a1b-0c4ce64791ff readback PASS: exact single asset/recipient/expiration, Active invitation, recipient acceptance Pending. Source readback does not itself verify a consumer query.

- 2026-11-23T10:20:25+00:00: Rehearsal Share 8343ea43-7fe0-4b23-9a1b-0c4ce64791ff readback PASS: exact single asset/recipient/expiration, Active invitation, recipient acceptance Accepted. Source readback does not itself verify a consumer query.

- 2026-11-23T10:30:58+00:00: Approved rehearsal Share 8343ea43-7fe0-4b23-9a1b-0c4ce64791ff deletion/absence verified. No producer data or consumer-tenant item was deleted.

- 2026-11-23T13:17:30+00:00: Step 9 actual SharePoint manifest captured at seed\manifest.json: 18 owned stage workbooks, current IDs/ETags/sizes and independently known seed hashes. Changed versions require exact workbook cell equality. No Graph writes. References: https://learn.microsoft.com/graph/api/driveitem-list-children; https://learn.microsoft.com/graph/api/driveitem-get; tools/upload_sharepoint.py.

- 2026-11-23T13:18:22+00:00: Step 9 actual OneLake role baseline captured at config\onelake_roles.baseline.json: 3 stages and partner; server role IDs omitted, all policy/member content retained, approved Prod sales memberships verified. No access writes. References: e2e-medallion-architecture/SKILL.md; fabric-skills/common/COMMON-CORE.md; https://learn.microsoft.com/rest/api/fabric/core/onelake-data-access-security/list-data-access-roles.
