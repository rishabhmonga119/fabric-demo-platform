"""Verify the newly deployed stage bindings and refresh its initial Direct Lake model."""

import argparse
from base64 import b64decode
import json
from pathlib import Path
import sys
import tempfile

from bootstrap_fabric_items import post_and_wait
from bootstrap_sales_model import refresh_and_check
from common import ContextError, ROOT, cli, is_metadata_ci, load_config, run, verify_context
from http_api import Api, ApiError

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("test", "prod"), required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--approved-prod", action="store_true")
    parser.add_argument("--report-only", action="store_true",
                        help="Verify report bindings and caption without rerunning the model refresh.")
    parser.add_argument("--report-preview-dir", type=Path,
                        help="Unpack the deployed PBIR into a new local directory for rendered review.")
    parser.add_argument("--metadata-only", action="store_true",
                        help="Check bindings without refreshing the model or querying business data.")
    args = parser.parse_args()
    if is_metadata_ci() and not args.metadata_only:
        raise ContextError("OIDC verification requires --metadata-only; data checks require the DEMO user.")
    verify_context()
    if args.stage == "prod" and not args.approved_prod:
        raise ContextError("Production initialization requires deployment approval.")
    config = load_config()
    stage = config["environments"][args.stage]
    workspace = stage["workspace_id"]
    api = Api("https://api.fabric.microsoft.com", config["tenant"]["id"],
              skill="semantic-model-authoring")
    live_workspace = api.request("GET", f"/v1/workspaces/{workspace}")
    capacities = [item for item in api.list("/v1/capacities")
                  if item["id"] == config["fabric"]["capacity_id"]]
    if live_workspace["displayName"] != stage["workspace_name"] or \
            live_workspace["capacityId"] != config["fabric"]["capacity_id"] or len(capacities) != 1 or \
            capacities[0]["state"] != "Active" or capacities[0]["sku"] != config["cost_guardrails"]["fabric_sku"]:
        raise ContextError("Stage initialization target differs from the approved existing Active F4.")
    items = api.list(f"/v1/workspaces/{workspace}/items")
    for name in config["environments"]["dev"]["items"]:
        matches = [item for item in items if item["displayName"] == name and
                   item["type"] == stage["items"].get(name, {}).get("type")]
        if len(matches) != 1 or matches[0]["id"] != stage["items"][name]["id"]:
            raise ContextError(f"{name} is missing or has a different stage identity.")
    model = stage["items"]["SM_Sales"]
    connections = api.list(f"/v1/workspaces/{workspace}/items/{model['id']}/connections")
    if len(connections) != 1 or stage["items"]["LH_Curated"]["id"] not in \
            connections[0]["connectionDetails"]["path"]:
        raise ApiError("Model is not connected to the stage Curated lakehouse.")
    if connections[0]["connectivityType"] != "Automatic":
        if connections[0]["connectivityType"] != "None":
            raise ContextError("A non-SSO model connection will not be overwritten.")
        api.request("POST", f"/v1/workspaces/{workspace}/semanticModels/{model['id']}/bindConnection",
                    {"connectionBinding": {"connectivityType": "Automatic",
                                           "connectionDetails": connections[0]["connectionDetails"]}},
                    dry_run=args.dry_run)
        if not args.dry_run:
            connections = api.list(f"/v1/workspaces/{workspace}/items/{model['id']}/connections")
    pbi = Api("https://api.powerbi.com", config["tenant"]["id"], skill="semantic-model-authoring")
    report_id = stage["items"]["RPT_Sales"]["id"]
    root = f"/v1.0/myorg/groups/{workspace}/reports/{report_id}"
    report = pbi.request("GET", root)
    if report["datasetId"] != model["id"]:
        raise ApiError("Report model binding leaks to another stage.")
    pages = pbi.list(root + "/pages")
    if [page["displayName"] for page in sorted(pages, key=lambda page: int(page["order"]))] != \
            ["Actual vs Forecast", "Margin"]:
        raise ApiError("Stage report does not contain the two baseline pages.")
    if args.dry_run:
        print(f"DRY-RUN: {args.stage} item/model/report bindings checked; no model refresh.")
        return
    report_api = Api("https://api.fabric.microsoft.com", config["tenant"]["id"],
                     skill="powerbi-report-cli")
    get_definition_uri = f"/v1/workspaces/{workspace}/reports/{report_id}/getDefinition?format=PBIR"
    definition = post_and_wait(report_api, get_definition_uri, {}, False,
                               f"{args.stage} report definition")
    if definition["definition"].get("format") != "PBIR":
        raise ApiError("Stage report did not return the requested modern PBIR definition.")
    visuals = [b64decode(part["payload"]).decode("utf-8")
               for part in definition["definition"]["parts"]
               if part["path"].endswith("/visual.json")]
    expected_caption = f"Source: SM_Sales, {args.stage.title()}."
    if not any(expected_caption in visual for visual in visuals) or \
            any("Source: SM_Sales, Dev." in visual for visual in visuals):
        raise ApiError("Report source caption does not identify the deployed stage.")
    if args.report_preview_dir:
        with tempfile.TemporaryDirectory(prefix="fabric-report-readback-") as directory:
            payload = Path(directory) / "definition.json"
            payload.write_text(json.dumps(definition), encoding="utf-8")
            print(run([cli("powerbi-report-author"), "unpack",
                       str(args.report_preview_dir.resolve()), "--input", str(payload)]))
    if args.report_only:
        record(f"{args.stage} report binding and stage caption PASS; deployed PBIR retrieved "
               "for rendered review. Reference: powerbi-report-cli/references/management-part-02.md.")
        print(f"PASS {args.stage} report: {report['webUrl']}")
        return
    if connections[0]["connectivityType"] != "Automatic":
        raise ApiError("Stage model Automatic SSO did not persist.")
    model["connection_binding"] = connections[0]
    stage["items"]["RPT_Sales"]["web_url"] = report["webUrl"]
    save_config(config)
    if not args.metadata_only:
        refresh_and_check(pbi, f"/v1.0/myorg/groups/{workspace}/datasets/{model['id']}",
                          model, config, args.stage)
    agent_api = Api("https://api.fabric.microsoft.com", config["tenant"]["id"],
                    skill="e2e-medallion-architecture")
    agent = stage["items"]["DA_Sales"]
    definition = post_and_wait(
        agent_api, f"/v1/workspaces/{workspace}/dataAgents/{agent['id']}/getDefinition",
        {}, False, f"{args.stage} Data Agent context")
    ontologies = []
    for part in definition["definition"]["parts"]:
        if part["path"].startswith("Files/Config/draft/ontologies/") and part["path"].endswith("ontology.json"):
            ontologies.append(json.loads(b64decode(part["payload"])))
        elif part["path"].startswith("Files/Config/draft/") and part["path"].endswith("datasource.json"):
            source = json.loads(b64decode(part["payload"]))
            if source.get("type") == "semantic_model":
                raise ApiError("The Data Agent has an independently configured semantic-model source.")
    if len(ontologies) != 1 or ontologies[0]["artifactId"] != stage["items"]["ONT_Business"]["id"] or \
            ontologies[0]["workspaceId"] != workspace:
        raise ApiError("Data Agent ontology context points at another stage.")
    agent["ontology_context_pending"] = False
    save_config(config)
    detail = "No refresh or business-data query was executed." if args.metadata_only else \
        "Model live baseline query verified the stage marker and row count."
    record(f"{args.stage} analytics bindings PASS: stage-local Direct Lake/SSO, report model/pages, "
           f"ontology-only Data Agent. {detail}")
    if args.metadata_only:
        print("METADATA ONLY: row counts, env_marker, rendered pages and Data Agent answers require user verification.")
    print(f"PASS {args.stage}: {report['webUrl']}")


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ApiError, TimeoutError, OSError, ValueError) as error:
        record(f"Stage verification blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
