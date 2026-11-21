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

Keep the existing Fabric F4 capacity unchanged. Provision only Step 1's storage,
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

Do not start Step 2 until Unity Catalog, external-access grants and storage
checks pass. An ARM deployment marked `Succeeded` alone is not a completed step.
