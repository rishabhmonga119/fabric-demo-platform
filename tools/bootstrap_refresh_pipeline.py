"""Create the owned sequential forecast refresh pipeline and optionally execute it."""

import argparse
from base64 import b64encode
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import sys
import time
from urllib.parse import urlparse
from uuid import NAMESPACE_URL, uuid5

from bootstrap_fabric_items import MARKER, create_item, post_and_wait
from common import ContextError, ROOT, load_config, verify_context
from http_api import Api, ApiError

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config


def run_pipeline(api: Api, config: dict, stage: dict, item: dict, dry_run: bool) -> None:
    run_item_job(api, config, stage, item, dry_run, name="PL_Refresh", job_type="Pipeline")


def run_item_job(api: Api, config: dict, stage: dict, item: dict, dry_run: bool, *,
                 name: str, job_type: str, definition_sha256: str | None = None) -> dict | None:
    jobs_root = f"/v1/workspaces/{stage['workspace_id']}/items/{item['id']}/jobs"
    jobs = api.list(jobs_root + "/instances")
    active = [job for job in jobs if job["status"] not in ("Completed", "Failed", "Cancelled", "Deduped")]
    if len(active) > 1:
        raise ContextError(f"Multiple active {name} runs; no duplicate submission.")
    if dry_run:
        api.request("POST", jobs_root + f"/instances?jobType={job_type}", {}, dry_run=True)
        return
    configured = stage["items"][name]
    if job_type == "RunNotebook" and not active and definition_sha256 and \
            configured.get("last_run_definition_sha256") == definition_sha256:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
        recent = []
        for job in jobs:
            if job["id"] != configured.get("last_run_id") or job["status"] != "Completed":
                continue
            started = datetime.fromisoformat(job["startTimeUtc"].replace("Z", "+00:00"))
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            if started >= cutoff:
                recent.append(job)
        if recent:
            print(f"{name}: reusing recent Completed run of unchanged content.")
            return api.request("GET", jobs_root + "/instances/" + recent[0]["id"])
    if active:
        uri = api.base + jobs_root + "/instances/" + active[0]["id"]
        delay = 10
    else:
        response = api.request("POST", jobs_root + f"/instances?jobType={job_type}", {},
                               accept_operation=True, with_response_info=True)
        uri = response["body"]["operation_uri"]
        raw = response["retry_after"]
        delay = int(raw) if isinstance(raw, str) and raw.isdigit() else 10
    configured["last_run_id"] = urlparse(uri).path.rstrip("/").split("/")[-1]
    configured["last_run_uri"] = uri
    if definition_sha256:
        configured["last_run_definition_sha256"] = definition_sha256
    save_config(config)
    record(f"Started/monitoring {stage['workspace_name']} {name} `{configured['last_run_id']}`.")
    deadline = time.monotonic() + 1800
    time.sleep(max(1, delay))
    while time.monotonic() < deadline:
        result = api.request("GET", uri)
        print(f"{name}: {result['status']}", flush=True)
        if result["status"] == "Completed":
            configured["last_run_state"] = "Completed"
            save_config(config)
            record(f"{stage['workspace_name']} {name} Completed.")
            return result
        if result["status"] in ("Failed", "Cancelled", "Deduped"):
            record(f"{name} failed: `{json.dumps(result.get('failureReason'))}`.")
            raise ApiError(f"{name}: {json.dumps(result.get('failureReason'))}")
        time.sleep(15)
    raise TimeoutError(f"{name} did not finish within 30 minutes.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--stage", choices=("dev", "test", "prod"), default="dev")
    parser.add_argument("--approved-prod", action="store_true")
    args = parser.parse_args()
    verify_context()
    if args.stage == "prod" and not args.approved_prod:
        raise ContextError("Production pipeline execution requires deployment approval.")
    config = load_config()
    stage = config["environments"][args.stage]
    workspace_id = stage["workspace_id"]
    api = Api("https://api.fabric.microsoft.com", config["tenant"]["id"],
              skill="pipeline-migration" if args.stage == "dev" else "e2e-medallion-architecture")
    workspace = api.request("GET", f"/v1/workspaces/{workspace_id}")
    capacities = [item for item in api.list("/v1/capacities")
                  if item["id"] == config["fabric"]["capacity_id"]]
    if workspace["capacityId"] != config["fabric"]["capacity_id"] or len(capacities) != 1 or \
            capacities[0]["sku"] != config["cost_guardrails"]["fabric_sku"] or capacities[0]["state"] != "Active":
        raise ContextError("Refresh pipeline requires the approved active workspace/capacity.")
    if args.stage != "dev":
        if not args.run:
            raise ContextError("Stage pipelines are deployed by fabric-cicd; this command runs an existing pipeline only.")
        matches = [item for item in api.list(f"/v1/workspaces/{workspace_id}/items?type=DataPipeline")
                   if item["displayName"] == "PL_Refresh"]
        if len(matches) != 1 or matches[0]["id"] != stage["items"]["PL_Refresh"]["id"] or \
                not (matches[0].get("description") or "").startswith(MARKER):
            raise ContextError("Existing stage refresh pipeline is unowned/conflicting.")
        run_pipeline(api, config, stage, matches[0], args.dry_run)
        return
    notebooks = api.list(f"/v1/workspaces/{workspace_id}/items?type=Notebook")
    activities = []
    for name in ("NB_Clean_Forecast", "NB_Integrate"):
        matches = [item for item in notebooks if item["displayName"] == name]
        if len(matches) != 1 or matches[0]["id"] != stage["items"][name]["id"]:
            raise ContextError("Pipeline notebook IDs differ from the verified inputs.")
        depends_on = [] if not activities else [
            {"activity": "NB_Clean_Forecast", "dependencyConditions": ["Succeeded"]}]
        activities.append({
            "name": name, "type": "TridentNotebook", "dependsOn": depends_on,
            "policy": {"timeout": "0.00:30:00", "retry": 0, "retryIntervalInSeconds": 30,
                       "secureOutput": False, "secureInput": False},
            "typeProperties": {"notebookId": matches[0]["id"], "workspaceId": workspace_id},
        })
    content = {"properties": {"description": MARKER + ": clean forecasts, then integrate.",
                              "activities": activities}}
    text = json.dumps(content, indent=2) + "\n"
    digest = sha256(text.encode()).hexdigest()
    folder = ROOT / "fabric" / "PL_Refresh.DataPipeline"
    platform = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "DataPipeline", "displayName": "PL_Refresh",
                     "description": MARKER + ": sequential Python clean and PySpark integration."},
        "config": {"version": "2.0", "logicalId": str(uuid5(NAMESPACE_URL, "fabric-demo-platform/PL_Refresh"))},
    }
    if folder.exists():
        marker = folder / ".platform"
        if not marker.exists() or not json.loads(marker.read_text(encoding="utf-8"))["metadata"]["description"].startswith(MARKER):
            raise ContextError("Existing local PL_Refresh folder is unowned.")
    part = {"path": "pipeline-content.json", "payload": b64encode(text.encode()).decode(),
            "payloadType": "InlineBase64"}
    definition = {"parts": [part]}
    matches = [item for item in api.list(f"/v1/workspaces/{workspace_id}/items?type=DataPipeline")
               if item["displayName"] == "PL_Refresh"]
    configured = stage["items"].get("PL_Refresh", {})
    if matches:
        if len(matches) != 1 or not (matches[0].get("description") or "").startswith(MARKER) or \
                configured.get("id") not in (None, matches[0]["id"]):
            raise ContextError("Existing PL_Refresh is unowned/conflicting; no overwrite.")
        item = matches[0]
        if configured.get("definition_sha256") != digest:
            post_and_wait(api, f"/v1/workspaces/{workspace_id}/items/{item['id']}/updateDefinition",
                          {"definition": definition}, args.dry_run, "PL_Refresh",
                          retrieve_result=False)
    else:
        initial = {"parts": [part, {"path": ".platform",
                                   "payload": b64encode(json.dumps(platform).encode()).decode(),
                                   "payloadType": "InlineBase64"}]}
        # ITEM-DEFINITIONS-CORE.md DataPipeline; notebook-activity-migration.md TridentNotebook.
        item = create_item(api, f"/v1/workspaces/{workspace_id}/items", {
            "displayName": "PL_Refresh", "type": "DataPipeline",
            "description": platform["metadata"]["description"], "definition": initial}, args.dry_run)
        if args.dry_run:
            print("DRY-RUN: sequential Python cleaning -> PySpark integration pipeline.")
            return
    if not args.dry_run:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "pipeline-content.json").write_text(text, encoding="utf-8")
        (folder / ".platform").write_text(json.dumps(platform, indent=2) + "\n", encoding="utf-8")
        configured = stage["items"].setdefault("PL_Refresh", {})
        configured.update({"id": item["id"], "type": "DataPipeline", "definition_sha256": digest})
        save_config(config)
        record(f"Created/updated owned PL_Refresh `{item['id']}`; Python cleaning then PySpark integration, no pool/environment overrides. Skill: pipeline-migration/resources/notebook-activity-migration.md; common/ITEM-DEFINITIONS-CORE.md DataPipeline.")
    if not args.run:
        return
    run_pipeline(api, config, stage, item, args.dry_run)


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ApiError) as error:
        record(f"Refresh pipeline blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
