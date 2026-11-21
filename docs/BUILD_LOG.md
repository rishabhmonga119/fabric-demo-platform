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
