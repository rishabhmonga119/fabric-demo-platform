# Demo environment build log

## 2026-11-21 - Step 0: workstation, repository and guardrails

Status: local setup complete; final checks and remote commit/push pending.
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
- Step 1 has not started.
