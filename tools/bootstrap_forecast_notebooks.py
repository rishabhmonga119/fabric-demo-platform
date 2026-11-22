"""Deploy/run Python cleaning and PySpark integration notebooks with bounded jobs."""

import argparse
from base64 import b64encode
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import sys
import time
from urllib.parse import urlparse

import nbformat

from bootstrap_fabric_items import MARKER, create_item, post_and_wait
from common import ContextError, ROOT, load_config, verify_context
from generate_fabric_notebooks import notebooks
from http_api import Api, ApiError

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--run", choices=("clean", "integrate", "both"))
    parser.add_argument("--inspect-sql-api", action="store_true",
                        help="Run a metadata-only cell to inspect the built-in Python SQL connector.")
    args = parser.parse_args()
    verify_context()
    config = load_config()
    stage = config["environments"]["dev"]
    workspace_id = stage["workspace_id"]
    api = Api("https://api.fabric.microsoft.com", config["tenant"]["id"], skill="spark-cli")
    workspace = api.request("GET", f"/v1/workspaces/{workspace_id}")
    selected = [capacity for capacity in api.list("/v1/capacities")
                if capacity["id"] == config["fabric"]["capacity_id"]]
    if workspace["capacityId"] != config["fabric"]["capacity_id"] or len(selected) != 1 or \
            selected[0]["state"] != "Active" or selected[0]["sku"] != config["cost_guardrails"]["fabric_sku"]:
        raise ContextError("Notebook workspace/capacity differs from approved active configuration.")
    existing = api.list(f"/v1/workspaces/{workspace_id}/items?type=Notebook")
    for name, notebook in notebooks(config).items():
        if args.inspect_sql_api:
            if name != "NB_Clean_Forecast":
                continue
            notebook.cells[-1].source = """
import inspect
from pathlib import Path

result = {"owner": OWNER_MARKER, "module_available": hasattr(notebookutils, "data")}
if result["module_available"]:
    module = notebookutils.data
    result["methods"] = [name for name in dir(module) if not name.startswith("_")]
    if hasattr(module, "connect_to_artifact"):
        method = module.connect_to_artifact
        result["signature"] = str(inspect.signature(method))
        result["documentation"] = inspect.getdoc(method)
path = Path("/lakehouse/default/Files/context/fabric_demo_sql_api.json")
path.parent.mkdir(parents=True, exist_ok=True)
if path.exists() and json.loads(path.read_text()).get("owner") != OWNER_MARKER:
    raise RuntimeError("Refusing to overwrite unowned connector diagnostic metadata.")
path.write_text(json.dumps(result), encoding="utf-8")
print("SQL connector metadata saved; no table data read or changed.")
"""
        if name == "NB_Integrate":
            settings = api.request("GET", f"/v1/workspaces/{workspace_id}/spark/settings")
            if settings["pool"]["defaultPool"]["name"] != "Starter Pool" or settings["environment"].get("name"):
                raise ContextError("NB_Integrate requires the default Starter Pool and no custom environment.")
        nbformat.validate(notebook)
        content = nbformat.writes(notebook)
        digest = sha256(content.encode()).hexdigest()
        definition = {"format": "ipynb", "parts": [
            {"path": "notebook-content.ipynb", "payload": b64encode(content.encode()).decode(),
             "payloadType": "InlineBase64"}]}
        matches = [item for item in existing if item["displayName"] == name]
        configured = stage["items"].get(name, {})
        if matches:
            if len(matches) != 1 or not (matches[0].get("description") or "").startswith(MARKER) or \
                    configured.get("id") not in (None, matches[0]["id"]):
                raise ContextError(f"Existing {name} is unowned/conflicting.")
            item = matches[0]
            if configured.get("definition_sha256") != digest:
                # spark-cli notebook-api-operations.md: Succeeded is sufficient; no post-upload getDefinition.
                post_and_wait(api, f"/v1/workspaces/{workspace_id}/notebooks/{item['id']}/updateDefinition",
                              {"definition": definition}, args.dry_run, name, retrieve_result=False)
        else:
            platform = (ROOT / "fabric" / f"{name}.Notebook" / ".platform").read_bytes()
            initial_definition = {"format": "ipynb", "parts": [
                *definition["parts"], {"path": ".platform", "payload": b64encode(platform).decode(),
                                       "payloadType": "InlineBase64"}]}
            item = create_item(api, f"/v1/workspaces/{workspace_id}/items",
                               {"displayName": name, "type": "Notebook",
                                "description": MARKER + (": Spark SQL join and PySpark Delta write."
                                                         if name == "NB_Integrate" else ": pure Python forecast cleaning."),
                                "definition": initial_definition}, args.dry_run)
            if args.dry_run:
                continue
        if not args.dry_run:
            configured = stage["items"].setdefault(name, {})
            configured.update({"id": item["id"], "type": "Notebook", "definition_sha256": digest})
            save_config(config)
            record(f"Deployed owned `{name}`: `{item['id']}`, kernel `{notebook.metadata['kernel_info']['name']}`. Skill: spark-cli authoring/notebook-api-operations.md; SPARK-NOTEBOOK-AUTHORING-CORE.md. No redundant definition readback.")
        should_run = args.inspect_sql_api or args.run == "both" or args.run == ("clean" if name == "NB_Clean_Forecast" else "integrate")
        if not should_run:
            continue
        root = f"/v1/workspaces/{workspace_id}/items/{item['id']}/jobs"
        jobs = api.list(root + "/instances")
        recent = []
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
        for job in jobs:
            started = datetime.fromisoformat(job["startTimeUtc"].replace("Z", "+00:00"))
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            if started >= cutoff and job["jobType"] == "RunNotebook":
                recent.append(job)
        active = [job for job in jobs if job["jobType"] == "RunNotebook" and
                  job["status"] not in ("Completed", "Failed", "Cancelled", "Deduped")]
        if len(active) > 1:
            raise ContextError("Multiple active owned notebook runs; no duplicate submission.")
        if args.dry_run:
            api.request("POST", root + "/instances?jobType=RunNotebook", {}, dry_run=True)
            continue
        if not active and configured.get("last_run_definition_sha256") == digest and any(
                job["id"] == configured.get("last_run_id") and job["status"] == "Completed" for job in recent):
            print(f"{name}: reusing recent Completed run for unchanged notebook content.")
            continue
        if active:
            run_uri = api.base + root + "/instances/" + active[0]["id"]
            first_delay = 10
        else:
            # spark-cli authoring: documented backward-compatible RunNotebook query path.
            submitted = api.request("POST", root + "/instances?jobType=RunNotebook", {},
                                    accept_operation=True, with_response_info=True)
            run_uri = submitted["body"]["operation_uri"]
            raw_delay = submitted["retry_after"]
            first_delay = int(raw_delay) if isinstance(raw_delay, str) and raw_delay.isdigit() else 10
        configured["last_run_uri"] = run_uri
        configured["last_run_id"] = urlparse(run_uri).path.rstrip("/").split("/")[-1]
        configured["last_run_definition_sha256"] = digest
        save_config(config)
        record(f"Started/monitoring `{name}` run `{configured['last_run_id']}`.")
        deadline = time.monotonic() + 1200
        time.sleep(max(1, first_delay))
        while time.monotonic() < deadline:
            result = api.request("GET", run_uri)
            print(f"{name}: {result['status']}", flush=True)
            if result["status"] == "Completed":
                configured["last_run_state"] = "Completed"
                save_config(config)
                record(f"`{name}` run Completed; data smoke check next.")
                break
            if result["status"] in ("Failed", "Cancelled", "Deduped"):
                record(f"`{name}` run failed: `{json.dumps(result.get('failureReason'))}`.")
                raise ApiError(f"{name}: {json.dumps(result.get('failureReason'))}")
            time.sleep(15)
        else:
            raise TimeoutError("Notebook run exceeded the 20-minute monitoring deadline.")
    print("DRY-RUN complete." if args.dry_run else "Requested forecast notebook deployment/runs completed.")


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ApiError) as error:
        record(f"Forecast notebook bootstrap blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
