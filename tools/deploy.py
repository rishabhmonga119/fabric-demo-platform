"""Deploy stage-bound Fabric definitions while preserving identity and cost guards."""

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
from azure.identity import AzureCliCredential
import yaml

from common import ContextError, ROOT, cli, is_metadata_ci, load_config, run, verify_context
from bootstrap_fabric_items import MARKER, wait_operation
from http_api import Api, ApiError

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config

PHASES = {"ingest": ["VariableLibrary", "Notebook", "DataPipeline"],
          "analytics": ["SemanticModel", "Report", "Ontology", "DataAgent"],
          "report": ["Report"]}


def phase_parameters(parameter: dict, types: list[str]) -> dict:
    scoped = {"find_replace": []}
    for entry in parameter["find_replace"]:
        filters = entry.get("item_type", types)
        filters = filters if isinstance(filters, list) else [filters]
        applicable = [kind for kind in filters if kind in types]
        if applicable:
            scoped["find_replace"].append({**entry, "item_type": applicable})
    return scoped


def validate_parameters(stage: str) -> None:
    from fabric_cicd._parameter._parameter import Parameter
    parameter = yaml.safe_load((ROOT / "fabric" / "parameter.yml").read_text(encoding="utf-8"))
    if not parameter.get("find_replace") or any(
            stage not in entry["replace_value"] for entry in parameter["find_replace"]):
        raise ContextError("Stage parameter replacements are incomplete.")
    for name, types in PHASES.items():
        scoped = phase_parameters(parameter, types)
        with tempfile.TemporaryDirectory(prefix="fabric-validate-parameters-") as directory:
            path = Path(directory) / "parameter.yml"
            path.write_text(yaml.safe_dump(scoped, sort_keys=False), encoding="utf-8")
            validator = Parameter(ROOT / "fabric", types, stage, parameter_file_path=str(path))
            if len(validator.environment_parameter.get("find_replace", [])) != len(scoped["find_replace"]):
                raise ContextError(f"fabric-cicd skipped a required {stage}/{name} parameter.")
    print(f"PASS: offline fabric-cicd parameter validation for {stage}; no authentication or cloud changes.")


class RepositoryEndpoint:
    def __init__(self, api: Api, config: dict, stage: dict):
        self.api, self.config, self.stage = api, config, stage
        self.lock = threading.Lock()

    def invoke(self, method, url, body="{}", files=None, poll_long_running=True, **kwargs):
        if files:
            raise ApiError("Multipart deployment is outside this demo's item scope.")
        payload = json.loads(body) if isinstance(body, str) else body
        response = self.api.request(method, url, None if method.upper() == "GET" else payload,
                                    accept_operation=True, with_response_info=True)
        headers = {}
        if response["status_code"] == 202:
            uri = response["body"]["operation_uri"]
            with self.lock:
                self.stage.setdefault("deployment_operations", {})[uri] = {"method": method}
                save_config(self.config)
            headers["Location"] = uri
            if not poll_long_running:
                return {"status_code": 202, "body": response["body"], "header": headers}
            result = wait_operation(self.api, uri, "Stage item operation",
                                    retry_after=response["retry_after"],
                                    retrieve_result=not url.split("?")[0].endswith("/updateDefinition"))
            with self.lock:
                self.stage["deployment_operations"].pop(uri)
                save_config(self.config)
            return {"status_code": 200, "body": result, "header": headers}
        return {"status_code": response["status_code"], "body": response["body"], "header": headers}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("test", "prod"), required=True)
    parser.add_argument("--phase", choices=tuple(PHASES), default="ingest")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--approved-prod", action="store_true")
    parser.add_argument("--validate-only", action="store_true",
                        help="Run fabric-cicd's parameter parser for every phase without cloud access.")
    args = parser.parse_args()
    if args.validate_only:
        validate_parameters(args.stage)
        return
    verify_context()
    if args.stage == "prod" and not args.approved_prod:
        raise ContextError("Production deployment requires the protected environment approval.")
    config = load_config()
    stage = config["environments"][args.stage]
    api = Api("https://api.fabric.microsoft.com", config["tenant"]["id"],
              skill="e2e-medallion-architecture")
    pending = stage.get("deployment_operation_uri")
    if pending and not args.dry_run:
        wait_operation(api, pending, "Resume accepted stage operation", retrieve_result=False)
        stage.pop("deployment_operation_uri")
        save_config(config)
    for uri in list(stage.get("deployment_operations", {})):
        if args.dry_run:
            raise ContextError("A recorded deployment operation must finish before another deployment.")
        wait_operation(api, uri, "Resume accepted stage operation", retrieve_result=False)
        stage["deployment_operations"].pop(uri)
        save_config(config)
    workspace = api.request("GET", f"/v1/workspaces/{stage['workspace_id']}")
    capacities = [item for item in api.list("/v1/capacities")
                  if item["id"] == config["fabric"]["capacity_id"]]
    if workspace["displayName"] != stage["workspace_name"] or \
            workspace["capacityId"] != config["fabric"]["capacity_id"] or len(capacities) != 1 or \
            capacities[0]["state"] != "Active" or capacities[0]["sku"] != config["cost_guardrails"]["fabric_sku"]:
        raise ContextError("Stage workspace/capacity differs from the approved existing Active F4.")
    existing = api.list(f"/v1/workspaces/{stage['workspace_id']}/items")
    for item in existing:
        if item["type"] not in PHASES[args.phase]:
            continue
        if stage["items"].get(item["displayName"], {}).get("id") != item["id"]:
            source = ROOT / "fabric" / f"{item['displayName']}.{item['type']}"
            if stage["items"].get(item["displayName"], {}).get("id") or \
                    item["type"] not in PHASES[args.phase] or not source.is_dir() or \
                    not (item.get("description") or "").startswith(MARKER):
                raise ContextError("An unrecorded stage item exists; no overwrite.")
            if not args.dry_run:
                stage["items"].setdefault(item["displayName"], {}).update({"id": item["id"], "type": item["type"]})
                save_config(config)
                record(f"Recovered delayed visibility of owned {args.stage} item "
                       f"`{item['displayName']}`: `{item['id']}`; no duplicate creation.")
    for name in ("LH_Landing", "LH_Curated", "MIR_UC_Gold"):
        if not stage["items"].get(name, {}).get("id"):
            raise ContextError("Prepare the stage lakehouses and mirror before definition deployment.")
    parameter = yaml.safe_load((ROOT / "fabric" / "parameter.yml").read_text(encoding="utf-8"))
    if not parameter.get("find_replace") or any(
            args.stage not in item["replace_value"] for item in parameter["find_replace"]):
        raise ContextError("Stage parameter replacements are incomplete; no skipped-value fallback.")
    os.environ["FABRIC_CICD_HTTP_TRACE_ENABLED"] = "0"
    os.environ["DEFAULT_API_ROOT_URL"] = "https://api.fabric.microsoft.com"
    os.environ["FABRIC_API_ROOT_URL"] = "https://api.fabric.microsoft.com"
    from fabric_cicd import FabricWorkspace, publish_all_items
    from fabric_cicd import constants
    constants.DEFAULT_API_ROOT_URL = "https://api.fabric.microsoft.com"
    types = PHASES[args.phase]
    scoped = phase_parameters(parameter, types)
    with tempfile.TemporaryDirectory(prefix="fabric-stage-parameters-") as directory:
        repository = Path(directory).resolve() / "fabric"
        tracked = run([cli("git"), "ls-files", "-z", "--", "fabric"]).split("\0")
        for name in (name for name in tracked if name):
            relative = Path(*name.split("/")).relative_to("fabric")
            if ".pbi" in relative.parts:
                raise ContextError("A private preview cache is unexpectedly tracked.")
            target = repository / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        path = os.path.join(directory, "parameter.yml")
        with open(path, "w", encoding="utf-8") as stream:
            yaml.safe_dump(scoped, stream, sort_keys=False)
        client = FabricWorkspace(repository_directory=str(repository),
                                 workspace_id=stage["workspace_id"], environment=args.stage,
                                 item_type_in_scope=types, parameter_file_path=path,
                                 token_credential=AzureCliCredential(
                                     process_timeout=30,
                                     **({} if is_metadata_ci() else {"tenant_id": config["tenant"]["id"]})))
        client.endpoint = RepositoryEndpoint(api, config, stage)
        if len(client.environment_parameter.get("find_replace", [])) != len(scoped["find_replace"]):
            raise ContextError("Deployment library skipped a required phase parameter.")
        if args.dry_run:
            print(f"DRY-RUN: {args.stage}/{args.phase}: {', '.join(types)}; no resource writes.")
            return
        record(f"Starting {args.stage}/{args.phase} fabric-cicd deployment with per-write context guards. "
               "Lakehouse/mirror preparation and shortcuts use their supported post-deploy APIs; "
               "no orphan deletion or paid-resource creation.")
        try:
            publish_all_items(client)
        finally:
            # Persist partial successes so a retry never treats created items as unowned.
            actual = api.list(f"/v1/workspaces/{stage['workspace_id']}/items")
            for item in actual:
                if item["type"] in types and (ROOT / "fabric" / f"{item['displayName']}.{item['type']}").is_dir():
                    stage["items"].setdefault(item["displayName"], {}).update({"id": item["id"], "type": item["type"]})
            save_config(config)
    actual_names = {item["displayName"] for item in actual if item["type"] in types}
    expected_names = {json.loads((folder / ".platform").read_text(encoding="utf-8"))["metadata"]["displayName"]
                      for folder in (ROOT / "fabric").iterdir() if folder.is_dir()
                      and folder.suffix.lstrip(".") in types}
    if not expected_names.issubset(actual_names):
        raise ApiError("Deployment returned without all requested phase items.")
    record(f"{args.stage}/{args.phase} metadata deployment PASS: {', '.join(sorted(expected_names))}. "
           "References: common/COMMON-CORE.md; https://microsoft.github.io/fabric-cicd/latest/how_to/parameterization/.")
    print(f"PASS {args.stage}/{args.phase}: {', '.join(sorted(expected_names))}")


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ApiError, ValueError, OSError) as error:
        record(f"Stage deployment blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
