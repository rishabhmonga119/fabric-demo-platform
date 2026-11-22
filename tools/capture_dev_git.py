"""Commit the authoritative Dev workspace once and verify its Git sync state."""

import argparse
import json
import sys
import time

from bootstrap_fabric_items import wait_operation
from common import ContextError, ROOT, load_config, verify_context
from http_api import Api, ApiError

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config

COMMENT = ("step 5: capture Dev Fabric items\n\n"
           "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>")


def git_status(api: Api, workspace: str) -> dict:
    response = api.request("GET", f"/v1/workspaces/{workspace}/git/status",
                           accept_operation=True, with_response_info=True)
    if response["status_code"] == 202:
        return wait_operation(api, response["body"]["operation_uri"], "Dev Git status",
                              retry_after=response["retry_after"])
    return response["body"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    verify_context()
    config = load_config()
    stage = config["environments"]["dev"]
    workspace = stage["workspace_id"]
    api = Api("https://api.fabric.microsoft.com", config["tenant"]["id"],
              skill="git-integration-operations-cli")
    detail = api.request("GET", f"/v1/workspaces/{workspace}")
    capacities = [item for item in api.list("/v1/capacities")
                  if item["id"] == config["fabric"]["capacity_id"]]
    if detail["displayName"] != stage["workspace_name"] or \
            detail["capacityId"] != config["fabric"]["capacity_id"] or len(capacities) != 1 or \
            capacities[0]["state"] != "Active" or capacities[0]["sku"] != config["cost_guardrails"]["fabric_sku"]:
        raise ContextError("Git capture target differs from the approved Dev workspace/Active F4.")
    connection = api.request("GET", f"/v1/workspaces/{workspace}/git/connection")
    provider = connection.get("gitProviderDetails") or {}
    expected = {"gitProviderType": "GitHub", "ownerName": config["github"]["owner"],
                "repositoryName": config["github"]["repository"], "branchName": "main"}
    if any(provider.get(key) != value for key, value in expected.items()) or \
            provider.get("directoryName", "").strip("/") != config["github"]["fabric_directory"] or \
            connection["gitConnectionState"] != "ConnectedAndInitialized":
        raise ContextError("Dev is not initialized against the expected GitHub main/fabric root.")
    pending = stage.get("git_capture_operation_uri")
    if pending:
        if args.dry_run:
            print("DRY-RUN: resume the recorded Git operation; no duplicate commit.")
            return
        wait_operation(api, pending, "Resume Dev Git capture", retrieve_result=False)
        stage.pop("git_capture_operation_uri")
        save_config(config)
    status = git_status(api, workspace)
    if not status.get("workspaceHead") or status["workspaceHead"] != status["remoteCommitHash"]:
        raise ContextError("Git heads differ; no concurrent or conflicting capture will be submitted.")
    changes = status["changes"]
    expected_ids = {value["id"] for value in stage["items"].values() if value.get("id")}
    for change in changes:
        item = change["itemMetadata"]["itemIdentifier"]
        if item["objectId"] not in expected_ids or change.get("remoteChange") or \
                change.get("conflictType") != "None":
            raise ContextError("Unexpected/unowned/remote Git change; no overwrite.")
        if not args.dry_run:
            name = change["itemMetadata"]["displayName"]
            if stage["items"].get(name, {}).get("id") != item["objectId"]:
                raise ContextError("Git item name/identity does not match configuration.")
            stage["items"][name]["logical_id"] = item["logicalId"]
    if changes:
        if len(COMMENT.encode("utf-16-le")) // 2 > 300:
            raise ContextError("Git comment exceeds the service limit.")
        if not args.dry_run:
            record("Retrying initial Dev workspace-to-Git capture after user updated GitHub credentials.")
        response = api.request("POST", f"/v1/workspaces/{workspace}/git/commitToGit",
                               {"mode": "All", "workspaceHead": status["workspaceHead"], "comment": COMMENT},
                               dry_run=args.dry_run, accept_operation=True, with_response_info=True)
        if args.dry_run:
            print(f"DRY-RUN: commit {len(changes)} known Dev items; no remote change.")
            return
        if response["status_code"] == 202:
            uri = response["body"]["operation_uri"]
            stage["git_capture_operation_uri"] = uri
            save_config(config)
            wait_operation(api, uri, "Dev Git capture", retry_after=response["retry_after"],
                           retrieve_result=False)
        elif response["status_code"] not in (200, 201):
            raise ApiError("Git capture did not return documented success/acceptance.")
    elif args.dry_run:
        print("DRY-RUN: Dev already has no pending changes; no commit.")
        return
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        status = git_status(api, workspace)
        if status["workspaceHead"] == status["remoteCommitHash"] and not status["changes"]:
            stage["git_capture_commit"] = status["remoteCommitHash"]
            stage.pop("git_capture_operation_uri", None)
            credentials = api.request("GET", f"/v1/workspaces/{workspace}/git/myGitCredentials")
            if credentials.get("source") != "ConfiguredConnection" or not credentials.get("connectionId"):
                raise ApiError("GitHub configured connection reference is missing.")
            config["github"]["fabric_connection_id"] = credentials["connectionId"]
            save_config(config)
            record(f"Dev Git capture PASS: all known items synced, no changes, "
                   f"workspace/remote head `{status['remoteCommitHash']}`. "
                   "Skill: git-integration-operations-cli/SKILL.md, Commit to Git / Check Sync Status. "
                   "Initial workspace capture is complete; subsequent source writer is the repository.")
            print("PASS Dev Git capture: " + status["remoteCommitHash"])
            return
        print("Waiting for Git heads/changes to settle.", flush=True)
        time.sleep(5)
    raise TimeoutError("Git capture did not reach matching heads with zero changes.")


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ApiError, TimeoutError) as error:
        record(f"Dev Git capture blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
