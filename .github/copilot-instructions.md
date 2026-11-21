# Demo build guardrails

- Read docs/00-README.md through docs/04-sample-data.md. Build Steps 0-9 in order.
- Before every Azure, Fabric, Entra or GitHub mutation, run `az account show`,
  `fab auth status` and `gh auth status`. Require the tenant ID and administrator
  in config/environments.yml and active GitHub account `rishabhmonga119`.
  Fail closed on missing, expired, ambiguous or mismatched authentication.
- Use installed Skills for Fabric for every Fabric REST/CLI call and item
  definition. Read the relevant skill and reference before writing code; cite
  the reference file. Never guess payloads.
- Send `x-ms-fabric-skill` on every Fabric control-plane request, including polls
  and retries. Use official Azure, Graph, Databricks and GitHub documentation.
- Target workspaces: DEMO-Analytics-Dev, DEMO-Analytics-Test,
  DEMO-Analytics-Prod and DEMO-Partner-A.
- Fixed stage item names: MIR_UC_Gold, LH_Landing, LH_Curated,
  NB_Clean_Forecast, NB_Integrate, PL_Refresh, SM_Sales, RPT_Sales,
  ONT_Business, DA_Sales and VL_Config.
- Never copy data between stages. Bind each stage to its own catalog and
  SharePoint folder using config/environments.yml.
- Target Python 3.11-compatible code. Use azure-identity; load IDs from config
  or environment variables. Never commit secrets, tokens or passwords.
- Keep company branding generic in config/demo_profile.yml.
- Every automation script must be idempotent, support `--dry-run`, report
  failures explicitly and stop on the first unrecovered failure.
- Prefer Python notebooks without Spark for small data; use the explicitly
  approved existing capacity/SKU in config/environments.yml (currently F8).
- Create at most one Premium Databricks workspace. Use serverless or single-node
  compute only; require 15-minute auto-termination for persistent compute.
  No paid Azure resources outside Step 1; do not resize Fabric capacity.
- Stop for human licences, consent, MFA/device code, tenant B and Agent Store
  publication. Stop if the same error persists after three distinct fixes.
- Never delete or overwrite objects not created by this automation; stop for
  explicit permission if a conflict requires either action.
- Record commands, resource names/IDs, checks, problems and decisions in
  docs/BUILD_LOG.md. Store discovered IDs in config/environments.yml.
- After each successful step, commit only its changes as `step N: ...`, include
  the Copilot co-author trailer, and push. Do not label blocked steps complete.
