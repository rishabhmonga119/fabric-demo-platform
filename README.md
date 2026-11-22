# Fabric + Databricks Demo Platform

Reusable, synthetic beverage analytics demo with isolated Dev, Test and Prod
sources. No customer data or credentials belong in this repository.

Start with the [documentation overview](docs/00-README.md), then follow
[base setup](docs/01-base-setup-copilot.md) in order. Execution results are recorded
in the [build log](docs/BUILD_LOG.md).

## Local setup

Python 3.11 or newer is required; automation targets Python 3.11-compatible code.
Tooling is installed in a repository-local, git-ignored virtual environment:

```powershell
python .\infra\prepare_workstation.py --dry-run
python .\infra\prepare_workstation.py
.\.venv\Scripts\fab.exe auth status
.\.venv\Scripts\python.exe .\tools\check_context.py --dry-run
```

The installer also installs the official, checksum-verified Databricks CLI
release in `.venv\Scripts`. Azure CLI, Git and GitHub CLI must already be installed.
If GitHub CLI is not on
PATH, its standard Windows installation is `C:\Program Files\GitHub CLI\gh.exe`.
Never proceed with cloud changes until all three authenticated contexts match
[environment configuration](config/environments.yml).

Fabric CLI installation and authentication follow the
[official CLI guide](https://microsoft.github.io/fabric-cli/) and
[authentication examples](https://microsoft.github.io/fabric-cli/examples/auth_examples/).

## Repository layout

- `infra/`: local setup and Azure infrastructure automation.
- `tools/`: deployment, verification and reset automation.
- `config/`: generic branding, stage bindings and non-secret resource IDs.
- `databricks/`: Asset Bundle and medallion jobs, populated in Step 3.
- `seed/excel/`: generated stage-specific forecasts, populated in Step 4.
- `fabric/`: Fabric Git definitions, populated in Step 5.
- `.github/workflows/`: validation and OIDC deployment, populated in Step 6.

## Cost and safety

Use the existing Fabric capacity at its explicitly approved configured SKU
(currently F4); automation must not resize it. Provision only Step 1's storage,
access connector and one Premium Databricks workspace. Use serverless or
single-node compute; persistent compute must auto-terminate after 15 minutes.
Never delete or overwrite pre-existing resources without explicit permission.

## Step 1 automation

```powershell
.\infra\deploy.ps1 --region northeurope --dry-run
.\infra\deploy.ps1 --region northeurope
.\.venv\Scripts\python.exe .\tools\check_databricks.py --dry-run --wait-ready 300
```

West Europe rejected this tenant's new resources; North Europe is the documented
alternative selected for the build. See the [build log](docs/BUILD_LOG.md) for
resource IDs, checks and the current checkpoint.

The read-only `--rest` diagnostic on `check_databricks.py` bypasses SDK tenant
discovery. `deploy.ps1 --repair-network-only --dry-run` previews reapplying the
required public storage endpoint without redeploying infrastructure; anonymous
blob access must remain disabled.
The documented direct ARM alternative is
`deploy.ps1 --repair-network-only --network-method arm`; it has the same
ownership, context, dry-run and exact read-back checks.

An explicitly approved exception can be applied with
`python infra/exempt_storage_policy.py --dry-run`, then without `--dry-run`.
It snapshots only the existing storage accounts in the verified subscription
and creates a separate, resource-scoped exemption for the public-network rule.
Other security rules, storage settings and future accounts are not exempted.

Unity Catalog setup continues with:

```powershell
.\.venv\Scripts\python.exe .\tools\bootstrap_databricks.py --dry-run
.\.venv\Scripts\python.exe .\tools\bootstrap_databricks.py
```

Enabling external data access requires metastore-administrator privileges;
workspace-administrator privileges alone are insufficient. The script changes
that existing flag only after the recorded explicit approval. It then creates
owned credentials, per-stage managed locations/catalogs/schemas and grants.
File events stay disabled to avoid additional queue/Event Grid resources.

Complete Step 1's physical-storage and SQL-grant checks with:

```powershell
.\.venv\Scripts\python.exe .\tools\check_managed_storage.py --dry-run
.\.venv\Scripts\python.exe .\tools\check_managed_storage.py
```

This creates one-row bronze infrastructure probes per stage and verifies their
actual files under each container's `__unitystorage` path. Its owned serverless
2X-Small warehouse is limited to one cluster, auto-stops after 15 minutes, and
is explicitly stopped after verification. The starter warehouse is untouched.

## Step 2 preflight

```powershell
.\.venv\Scripts\python.exe .\tools\fabric_preflight.py --dry-run
```

This reads the existing F4, active workspace/domain inventory and relevant tenant
settings with installed Skills for Fabric references. It never creates or resizes
a capacity, and no settings are changed until existing scopes and domain
governance choices are explicitly approved.

After approval, run the idempotent identity and Fabric bootstraps:

```powershell
.\.venv\Scripts\python.exe .\tools\bootstrap_entra.py --dry-run
.\.venv\Scripts\python.exe .\tools\bootstrap_entra.py
.\.venv\Scripts\python.exe .\tools\bootstrap_fabric.py --dry-run
.\.venv\Scripts\python.exe .\tools\bootstrap_fabric.py
```

OIDC uses federated credentials, not a client secret. Test-user passwords are
generated only in memory and must be reset in Entra before use; never store them.
The Fabric bootstrap preserves existing enabled tenant scopes, verifies exact
domain/workspace roles, and stops if the selected capacity differs from its
explicitly approved configured SKU.

The read-only OIDC proof is provisioned with `tools/setup_oidc_check.py` and
dispatched with `tools/run_oidc_check.py`; both support `--dry-run`. The workflow
uses GitHub OIDC and verifies the configured SP can list Test items, without
granting Azure subscription roles or using a client secret.
The Entra bootstrap discovers GitHub's current OIDC subject prefix (including
immutable owner/repository IDs where enabled) instead of assuming legacy subjects.

Existing licensed test accounts can be selected with
`tools/select_test_users.py --north <UPN> --south <UPN> --dry-run`, then without
`--dry-run`. It verifies licence capabilities and rejects privileged Prod access,
changes only the corresponding sales-group memberships, and records runtime
personas. Existing licences/passwords are not moved or reset.

`tools/check_demo_licenses.py --dry-run` checks actual service-plan capabilities
for the presenter and demo users. Licence purchases/reallocation and initial
password resets remain human checkpoints; secrets must never be saved here.

Do not start Step 2 until Unity Catalog, external-access grants and storage
checks pass. An ARM deployment marked `Succeeded` alone is not a completed step.

## Deployment and refresh identities

[The deployment workflow](.github/workflows/deploy.yml) uses GitHub OIDC and
`sp-fabric-demo-cicd` for **metadata-only** Test/Prod deployment with fabric-cicd.
It publishes the Variable Library, notebooks, pipeline, model, report, ontology,
and Data Agent definitions. It does not update Dev, run Spark, refresh business
data, or claim that row counts and `env_marker` were checked. Prod requires the
repository owner's environment approval. No client secret or Azure subscription
role is required.

CI has its own explicit guard: approved tenant/application/SP object, immutable
repository/owner IDs, owner-triggered main-branch workflow, target stage and F4.
The original Azure/Fabric/GitHub **admin-user checks remain unchanged locally**.
CI API guards reject cross-stage writes, data-refresh jobs, shortcuts,
infrastructure creation, deletions, and permission changes.

The current Spark SQL-endpoint reader supports interactive Entra users, not
service principals. Keep `NB_Clean_Forecast` as Python and `NB_Integrate` as
PySpark with Spark SQL joins/PySpark writes on the Starter Pool, without a custom
Environment. Refresh and data acceptance are a **separate user-authenticated
step**, not a skipped or falsely successful CI task:

```powershell
.\.venv\Scripts\python.exe .\tools\check_context.py --dry-run
.\.venv\Scripts\python.exe .\tools\bootstrap_refresh_pipeline.py --stage prod --run --approved-prod --dry-run
.\.venv\Scripts\python.exe .\tools\bootstrap_refresh_pipeline.py --stage prod --run --approved-prod
.\.venv\Scripts\python.exe .\tools\post_deploy.py --stage prod --approved-prod
.\.venv\Scripts\python.exe .\tools\verify.py --stage prod --approved-prod
.\.venv\Scripts\python.exe .\tools\verify_data_agent.py --stage prod --approved-prod --publish --dry-run
.\.venv\Scripts\python.exe .\tools\verify_data_agent.py --stage prod --approved-prod --publish
```

Use `--stage test` without the Prod approval flag for Test. After data acceptance,
check both rendered report pages and actual Data Agent answers. External mirror,
lakehouse and shortcut preparation are initial-stage prerequisites, not OIDC
metadata deployment.

Read-only OIDC validation can be dispatched without deploying either workspace:

```powershell
.\.venv\Scripts\python.exe .\tools\run_oidc_check.py --metadata-validation --stage both --dry-run
.\.venv\Scripts\python.exe .\tools\run_oidc_check.py --metadata-validation --stage both
```

[PR checks](.github/workflows/pr-check.yml) run the repository tests and the same
fabric-cicd parameter parser offline, without cloud credentials.

Configure the owned GitHub Prod reviewer and main PR protection with
`tools/setup_deployment_workflow.py --dry-run`, then without `--dry-run`.
It preserves the existing Test environment/OIDC variables and makes no Fabric
workspace or tenant-permission changes. Publishing DA_Sales for MCP queries does
not publish it to Agent Store or Microsoft 365.

### Current Data Agent blocker

Prod's items, pipeline, physical rows, semantic-model measures and both report
pages are verified. The Data Agent is published and points only to ONT_Business,
but its real MCP answer check is **blocked**, not passed. Microsoft documents
[a current known issue](https://learn.microsoft.com/fabric/iq/ontology/resources-troubleshooting#troubleshoot-ontology-as-data-agent-source):
Data Agent doesn't work with an ontology that uses semantic models for binding.
The captured ontology has those bindings. A fix requires supported V2 authoring
to bind the ontology to managed lakehouse tables; external shortcut tables aren't
supported by the ontology graph either. Keep the report on SM_Sales and don't
add a standalone semantic-model source to the Data Agent as a workaround.
