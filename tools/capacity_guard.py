"""Verify stage assignment and live capacity state without granting CI administration."""

import json

from common import ContextError, cli, is_metadata_ci, run
from http_api import Api


def verify_stage_capacity(api: Api, config: dict, workspace: dict, stage: dict) -> None:
    expected_id = config["fabric"]["capacity_id"]
    expected_sku = config["cost_guardrails"]["fabric_sku"]
    if workspace["displayName"] != stage["workspace_name"] or workspace["capacityId"] != expected_id:
        raise ContextError("Stage workspace name/capacity differs from the approved assignment.")
    if is_metadata_ci():
        resource_id = config["fabric"].get("capacity_resource_id")
        reader = config["github"].get("capacity_reader", {})
        prefix = f"/subscriptions/{config['azure']['subscription_id']}/resourceGroups/"
        if not resource_id or not resource_id.startswith(prefix) or \
                "/providers/Microsoft.Fabric/capacities/" not in resource_id or \
                reader.get("scope") != resource_id or \
                reader.get("principal_id") != config["entra"]["application"]["service_principal_id"]:
            raise ContextError("CI requires the explicitly approved capacity-only Reader scope.")
        # Official ARM GET: 2023-11-01; no capacity administration or resize request.
        capacity = json.loads(run([cli("az"), "resource", "show", "--ids", resource_id,
                                   "--api-version", "2023-11-01", "--output", "json"]))
        if capacity.get("id", "").casefold() != resource_id.casefold() or \
                capacity.get("sku", {}).get("name") != expected_sku or \
                capacity.get("properties", {}).get("state") != "Active":
            raise ContextError("Azure capacity Reader check differs from the approved live Active SKU.")
        print(f"Azure capacity-only Reader guard: Active {expected_sku} PASS")
        return
    capacities = [item for item in api.list("/v1/capacities") if item["id"] == expected_id]
    if len(capacities) != 1 or capacities[0]["state"] != "Active" or capacities[0]["sku"] != expected_sku:
        raise ContextError("Stage capacity differs from the approved existing Active SKU.")
