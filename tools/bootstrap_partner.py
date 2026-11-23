"""Build and optionally execute the output-only Partner A lakehouse and notebook."""

import argparse
from base64 import b64encode
from decimal import Decimal
from hashlib import sha256
import json
import sys
import time
from uuid import NAMESPACE_URL, uuid5

import nbformat

from bootstrap_fabric_items import MARKER, create_item, create_lakehouse, post_and_wait
from bootstrap_refresh_pipeline import run_item_job
from capacity_guard import verify_stage_capacity
from common import ContextError, ROOT, is_metadata_ci, load_config, verify_context
from generate_fabric_notebooks import git_source
from http_api import Api, ApiError
from post_deploy import same_target
from partner_logic import PARTNER_COLUMNS

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config

REFERENCES = (
    "spark-cli/references/authoring.md; spark-cli/references/authoring/resources/notebook-api-operations.md; "
    "fabric-skills/common/COMMON-CORE.md; SPARK-AUTHORING-CORE.md; "
    "https://learn.microsoft.com/fabric/onelake/iq-share/onelake-share-overview"
)


def platform(name: str, kind: str) -> dict:
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": kind, "displayName": name,
                     "description": MARKER + ": output-only Partner A extraction."},
        "config": {"version": "2.0", "logicalId": str(uuid5(
            NAMESPACE_URL, f"fabric-demo-platform/partner/{name}"))},
    }


def write_source(name: str, kind: str, files: dict[str, str]) -> bytes:
    folder = ROOT / "partner" / f"{name}.{kind}"
    marker = platform(name, kind)
    if folder.exists():
        existing = folder / ".platform"
        if not existing.exists() or not json.loads(existing.read_text(encoding="utf-8"))[
                "metadata"]["description"].startswith(MARKER):
            raise ContextError(f"Refusing to overwrite unowned partner source {name}.")
    folder.mkdir(parents=True, exist_ok=True)
    content = json.dumps(marker, indent=2) + "\n"
    for name, text in {".platform": content, **files}.items():
        (folder / name).write_text(text, encoding="utf-8")
    return content.encode()


def make_notebook(config: dict):
    partner, source = config["partner"], config["environments"]["prod"]
    parameters = "\n".join(f"{key} = {value!r}" for key, value in {
        "expected_tenant": config["tenant"]["id"],
        "allowed_actors": [config["tenant"]["admin_object_id"]],
        "partner_workspace_name": partner["workspace_name"],
        "source_workspace_id": source["workspace_id"],
        "source_lakehouse_id": source["items"]["LH_Curated"]["id"],
        "partner_glossary": (ROOT / "partner" / "context" / "partner_glossary.md").read_text(
            encoding="utf-8"),
    }.items()) + "\n"
    cells = []
    sources = [parameters] + [(ROOT / "tools" / name).read_text(encoding="utf-8") for name in (
        "partner_logic.py", "fabric_notebook_runtime.py", "fabric_partner_extract_cell.py")]
    for index, code in enumerate(sources):
        compile(code, f"partner-cell-{index}", "exec")
        cell = nbformat.v4.new_code_cell(
            code, id=uuid5(NAMESPACE_URL, f"NB_Partner_Extract/{index}").hex[:12])
        cell.metadata.update({"language": "python", "language_group": "jupyter_python"})
        if index == 0:
            cell.metadata["tags"] = ["parameters"]
        cells.append(cell)
    notebook = nbformat.v4.new_notebook(cells=cells, metadata={
        "kernel_info": {"name": "jupyter", "jupyter_kernel_name": "python3.11"},
        "kernelspec": {"name": "python3.11", "display_name": "Python 3.11", "language": "python"},
        "language_info": {"name": "python"},
        "dependencies": {"lakehouse": {
            "default_lakehouse": partner["items"]["LH_PartnerA"]["id"],
            "default_lakehouse_name": "LH_PartnerA",
            "default_lakehouse_workspace_id": partner["workspace_id"],
        }},
    })
    nbformat.validate(notebook)
    return notebook


def owned_item(items: list[dict], partner: dict, name: str, kind: str):
    matches = [item for item in items if item["displayName"] == name and item["type"] == kind]
    if not matches:
        if partner["items"].get(name, {}).get("id"):
            raise ContextError(f"Configured {name} is missing; no automatic replacement.")
        return None
    if len(matches) != 1 or \
            not (matches[0].get("description") or "").startswith(MARKER) or \
            partner["items"].get(name, {}).get("id") not in (None, matches[0]["id"]):
        raise ContextError(f"Existing {name} is unowned or conflicts with configuration.")
    return matches[0]


def verification_metrics(details: dict, *, initial_baseline: bool) -> dict:
    exit_value = details.get("exitValue")
    if exit_value is None and isinstance(details.get("properties"), dict):
        exit_value = details["properties"].get("exitValue")
    if details["status"] != "Completed" or not isinstance(exit_value, str):
        raise ApiError("Completed notebook has no verification exit value.")
    metrics = json.loads(exit_value)
    if not isinstance(metrics, dict):
        raise ApiError("Notebook verification exit value must be a JSON object.")
    if metrics.get("check") != "PASS" or metrics.get("columns") != list(PARTNER_COLUMNS) or \
            metrics.get("table") != "dbo.partner_a_deliveries" or \
            metrics.get("exact_filtered_row_readback") is not True or \
            metrics.get("glossary_readback") is not True:
        raise ApiError("Notebook did not verify the exact persisted partner output.")
    if initial_baseline and (
            metrics["rows"] != 1232 or Decimal(metrics["delivered_hl"]) != Decimal("1121803.72")
            or metrics["min_month"] != "2025-01-01" or metrics["max_month"] != "2026-10-01"
            or metrics["regions"] != ["EAST", "NORTH"]):
        raise ApiError("Initial Partner A data differs from the verified source baseline.")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if is_metadata_ci():
        raise ContextError("Partner deployment requires the DEMO administrator, not metadata CI.")
    verify_context()
    config = load_config()
    partner, source = config["partner"], config["environments"]["prod"]
    workspace = partner["workspace_id"]
    api = Api("https://api.fabric.microsoft.com", config["tenant"]["id"], skill="spark-cli")
    root = f"/v1/workspaces/{workspace}"
    verify_stage_capacity(api, config, api.request("GET", root), partner)
    source_items = api.list(f"/v1/workspaces/{source['workspace_id']}/items?type=Lakehouse")
    matches = [item for item in source_items if item["displayName"] == "LH_Curated"]
    if len(matches) != 1 or matches[0]["id"] != source["items"]["LH_Curated"]["id"]:
        raise ContextError("Prod Curated source identity differs from the approved binding.")
    shortcuts = api.list(f"/v1/workspaces/{source['workspace_id']}/items/{matches[0]['id']}/shortcuts")
    gold = [item for item in shortcuts if item["path"].strip("/") == "Tables" and item["name"] == "gold"]
    expected = {"oneLake": {"workspaceId": source["workspace_id"],
                            "itemId": source["items"]["MIR_UC_Gold"]["id"], "path": "Tables/gold"}}
    if len(gold) != 1 or not same_target(gold[0]["target"], expected):
        raise ContextError("Existing internal Gold shortcut differs; no source modification.")
    items = api.list(root + "/items")
    lakehouse = owned_item(items, partner, "LH_PartnerA", "Lakehouse")
    notebook_item = owned_item(items, partner, "NB_Partner_Extract", "Notebook")
    if not lakehouse:
        lakehouse = create_lakehouse(
            api, workspace, "LH_PartnerA", MARKER + ": P-A-only deliveries and glossary; no inputs.",
            args.dry_run)
        if args.dry_run:
            print("DRY-RUN: then generate/create NB_Partner_Extract bound to the returned lakehouse ID; "
                  f"run={args.run}. No local writes, sharing, permissions or source modifications.")
            return
    if not args.dry_run:
        partner["items"].setdefault("LH_PartnerA", {}).update(
            {"id": lakehouse["id"], "type": "Lakehouse"})
        save_config(config)
    detail = api.request("GET", root + f"/lakehouses/{lakehouse['id']}")
    deadline = time.monotonic() + 300
    while detail["properties"]["sqlEndpointProperties"]["provisioningStatus"] == "InProgress":
        if time.monotonic() >= deadline:
            raise TimeoutError("Partner SQL endpoint did not provision within five minutes.")
        time.sleep(10)
        detail = api.request("GET", root + f"/lakehouses/{lakehouse['id']}")
    if detail["properties"].get("defaultSchema") != "dbo" or \
            detail["properties"]["sqlEndpointProperties"]["provisioningStatus"] != "Success":
        raise ContextError("Partner lakehouse schema/SQL provisioning differs from the expected state.")
    if api.list(root + f"/items/{lakehouse['id']}/shortcuts"):
        raise ContextError("Partner output lakehouse contains shortcuts; do not share unfiltered sources.")
    if args.dry_run:
        print(f"DRY-RUN: verify/update owned NB_Partner_Extract; run={args.run}; no local/cloud writes.")
        return
    partner["items"]["LH_PartnerA"]["sql_endpoint_id"] = detail["properties"]["sqlEndpointProperties"]["id"]
    write_source("LH_PartnerA", "Lakehouse", {"lakehouse.metadata.json": '{"defaultSchema":"dbo"}\n'})
    notebook = make_notebook(config)
    content = nbformat.writes(notebook)
    digest = sha256(content.encode()).hexdigest()
    marker = write_source("NB_Partner_Extract", "Notebook", {"notebook-content.py": git_source(notebook)})
    definition = {"format": "ipynb", "parts": [{
        "path": "notebook-content.ipynb", "payload": b64encode(content.encode()).decode(),
        "payloadType": "InlineBase64",
    }]}
    configured = partner["items"].setdefault("NB_Partner_Extract", {})
    if notebook_item:
        if configured.get("definition_sha256") != digest:
            post_and_wait(api, root + f"/notebooks/{notebook_item['id']}/updateDefinition",
                          {"definition": definition}, False, "NB_Partner_Extract", retrieve_result=False)
    else:
        initial = {"format": "ipynb", "parts": [*definition["parts"], {
            "path": ".platform", "payload": b64encode(marker).decode(), "payloadType": "InlineBase64"}]}
        notebook_item = create_item(api, root + "/items", {
            "displayName": "NB_Partner_Extract", "type": "Notebook",
            "description": MARKER + ": pure Python, P-A only, exact seven-column Delta readback.",
            "definition": initial}, False)
    configured.update({"id": notebook_item["id"], "type": "Notebook", "definition_sha256": digest})
    save_config(config)
    record(f"Step 8 output-only producer items ready: LH_PartnerA {lakehouse['id']}, "
           f"NB_Partner_Extract {notebook_item['id']}, Python kernel, existing F4. "
           f"No shortcuts in output, permissions, external sharing or Prod writes. References: {REFERENCES}.")
    if args.run:
        run_item_job(api, config, partner, notebook_item, False, name="NB_Partner_Extract",
                     job_type="RunNotebook", definition_sha256=digest)
        job_id = configured["last_run_id"]
        details = api.request("GET", root +
                              f"/notebooks/{notebook_item['id']}/jobs/execute/instances/{job_id}?beta=true")
        metrics = verification_metrics(details, initial_baseline=not partner.get("producer_verification"))
        partner["producer_metrics"] = metrics
        partner["producer_verification"] = "passed-notebook-exact-delta-and-glossary-readback"
        partner["sharing_verification"] = "pending-tenant-b-and-approved-sharing"
        save_config(config)
        record("Step 8 producer Check PASS: notebook completed after exact persisted Delta row comparison "
               "against P-A filtered delivery/product projection and exact glossary file readback. "
               f"Actual exit-value metrics: {json.dumps(metrics)}. Tenant B/sharing/security acceptance "
               "remains a human checkpoint; no Share, guest or new grants created.")
    print("Partner producer ready; external sharing remains unconfigured.")


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ApiError, TimeoutError, OSError, ValueError) as error:
        record(f"Step 8 partner producer blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
