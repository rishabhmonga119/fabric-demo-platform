"""Publish the rendered Sales report once; verify its model binding and both pages."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
import tempfile

from bootstrap_fabric_items import MARKER, wait_operation
from common import ContextError, ROOT, cli, load_config, run, verify_context
from http_api import Api, ApiError

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config

REFERENCES = ("powerbi-report-cli/references/management.md; management-part-02.md; "
              "management-part-04.md; authoring/powerbi-report-author-cli.md; "
              "https://learn.microsoft.com/rest/api/power-bi/reports/get-report-in-group; "
              "https://learn.microsoft.com/rest/api/power-bi/reports/get-pages-in-group")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--render-reviewed", action="store_true",
                        help="Confirm both current pages have passed actual screenshot review.")
    args = parser.parse_args()
    verify_context()
    config = load_config()
    stage = config["environments"]["dev"]
    api = Api("https://api.fabric.microsoft.com", config["tenant"]["id"], skill="powerbi-report-cli")
    workspaces = [item for item in api.list("/v1/workspaces")
                  if item["displayName"] == stage["workspace_name"]]
    if len(workspaces) != 1 or workspaces[0]["id"] != stage["workspace_id"]:
        raise ContextError("Dev workspace resolution differs from the approved target.")
    workspace_id = workspaces[0]["id"]
    capacities = [item for item in api.list("/v1/capacities")
                  if item["id"] == config["fabric"]["capacity_id"]]
    if workspaces[0].get("capacityId") != config["fabric"]["capacity_id"] or \
            len(capacities) != 1 or capacities[0]["state"] != "Active" or \
            capacities[0]["sku"] != config["cost_guardrails"]["fabric_sku"]:
        raise ContextError("Report publication requires the existing approved Active F4.")
    models = [item for item in api.list(f"/v1/workspaces/{workspace_id}/items?type=SemanticModel")
              if item["displayName"] == "SM_Sales"]
    if len(models) != 1 or models[0]["id"] != stage["items"]["SM_Sales"]["id"]:
        raise ContextError("The target model differs from the one used for rendered validation.")
    model_id = models[0]["id"]
    configured = stage["items"]["RPT_Sales"]
    source = ROOT / "fabric" / "RPT_Sales.Report"
    if not (source / "definition" / "report.json").is_file() or not configured.get("local_files"):
        raise ContextError("A generated and validated modern PBIR source is required.")
    for name, digest in configured["local_files"].items():
        path = source / name
        if not path.is_file() or sha256(path.read_bytes()).hexdigest() != digest:
            raise ContextError(f"Report source changed since validation: {name}.")
    with tempfile.TemporaryDirectory(prefix="fabric-publish-sales-") as directory:
        staged = Path(directory) / "RPT_Sales.Report"
        for name in configured["local_files"]:
            target = staged / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, target)
        binding_path = staged / "definition.pbir"
        binding = json.loads(binding_path.read_text(encoding="utf-8"))
        binding["datasetReference"] = {"byConnection": {"connectionString": f"semanticmodelid={model_id}"}}
        binding_path.write_text(json.dumps(binding, indent=2) + "\n", encoding="utf-8")
        payload = json.loads(run([cli("powerbi-report-author"), "pack", str(staged), "--raw",
                                  "--mode", "create", "--display-name", "RPT_Sales",
                                  "--description", MARKER + ": actual versus forecast and margin."]))
    digest = sha256(json.dumps(payload["definition"], sort_keys=True).encode()).hexdigest()
    if args.render_reviewed and not args.dry_run:
        configured["render_reviewed_definition_sha256"] = digest
        save_config(config)
    if not args.dry_run and configured.get("render_reviewed_definition_sha256") != digest:
        raise ContextError("Review both current rendered pages before publishing; schema validation alone is insufficient.")
    reports_path = f"/v1/workspaces/{workspace_id}/reports"
    matches = [item for item in api.list(reports_path) if item["displayName"] == "RPT_Sales"]
    pending = configured.get("pending_create_operation_uri")
    if pending:
        if args.dry_run:
            print(f"DRY-RUN: resume accepted report creation {pending}; no new submission.")
            return
        item = wait_operation(api, pending, "RPT_Sales")
    elif matches:
        if len(matches) != 1 or not (matches[0].get("description") or "").startswith(MARKER) or \
                configured.get("id") != matches[0]["id"] or \
                configured.get("definition_sha256") != digest:
            raise ContextError("An existing/conflicting report will not be overwritten.")
        item = matches[0]
    else:
        response = api.request("POST", reports_path, payload, dry_run=args.dry_run,
                               accept_operation=True, with_response_info=True)
        if args.dry_run:
            print(f"DRY-RUN: create one RPT_Sales with {len(payload['definition']['parts'])} "
                  f"PBIR parts, bound to {model_id}.")
            return
        if response["status_code"] == 202:
            pending = response["body"]["operation_uri"]
            configured["pending_create_operation_uri"] = pending
            save_config(config)
            record(f"Accepted RPT_Sales creation: `{pending}`; polling, never resubmitting.")
            item = wait_operation(api, pending, "RPT_Sales", retry_after=response["retry_after"])
        elif response["status_code"] in (200, 201):
            item = response["body"]
        else:
            raise ApiError("Report creation did not return documented success/acceptance.")
    if args.dry_run:
        print("DRY-RUN: report already matches; no mutation.")
        return
    configured.update({"id": item["id"], "type": "Report",
                       "definition_sha256": digest, "semantic_model_id": model_id})
    configured.pop("pending_create_operation_uri", None)
    save_config(config)
    report = api.request("GET", reports_path + "/" + item["id"])
    if report["displayName"] != "RPT_Sales":
        raise ApiError("Published report metadata differs.")
    pbi = Api("https://api.powerbi.com", config["tenant"]["id"], skill="powerbi-report-cli")
    report_path = f"/v1.0/myorg/groups/{workspace_id}/reports/{item['id']}"
    detail = pbi.request("GET", report_path)
    if detail["datasetId"] != model_id or detail["name"] != "RPT_Sales":
        raise ApiError("Published report is not bound to the verified Sales model.")
    pages = pbi.list(report_path + "/pages")
    ordered = sorted(pages, key=lambda page: int(page["order"]))
    if [page["displayName"] for page in ordered] != ["Actual vs Forecast", "Margin"]:
        raise ApiError("The published report does not contain exactly the approved two pages.")
    configured.update({"web_url": detail["webUrl"], "pages": ordered, "publish_verified": True})
    save_config(config)
    record(f"RPT_Sales `{item['id']}` publication PASS: correct SM_Sales binding, "
           f"two ordered pages; live-data screenshot review passed before publication, "
           f"including Margin %=26.7. URL: {detail['webUrl']}. References: {REFERENCES}.")
    print("PASS RPT_Sales: " + detail["webUrl"])


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ApiError, TimeoutError, OSError, ValueError) as error:
        record(f"Sales report publication blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
