"""Configure Step 1 Unity Catalog and verify managed storage with tiny probes."""

import argparse
import json
from pathlib import Path
import sys
import tempfile
import time

from check_databricks import workspace_environment
from common import ContextError, ROOT, cli, load_config, mutate, run, verify_context

sys.path.insert(0, str(ROOT))
from infra.deploy import ensure_storage_network, record, save_config


def explicit_privileges(response: dict, principal: str) -> set[str]:
    privileges = set()
    for assignment in response.get("privilege_assignments", []):
        if assignment["principal"].casefold() == principal.casefold():
            privileges.update(assignment["privileges"])
    return privileges


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    verify_context()
    config = load_config()
    azure = config["azure"]
    environment = workspace_environment(config)
    executable = cli("databricks")
    owner = f"{config['github']['owner']}/{config['github']['repository']}"
    comment = f"Demo bootstrap owned by {owner}"

    def read(*arguments: str):
        return json.loads(run([executable, *arguments, "--output", "json"], env=environment))

    def write(method: str, endpoint: str, payload: dict):
        command = [executable, "api", method, endpoint, "--output", "json"]
        if args.dry_run:
            mutate([*command, "--json", json.dumps(payload)], dry_run=True, env=environment)
            return None
        with tempfile.TemporaryDirectory(prefix="demo-databricks-body-") as directory:
            body = Path(directory) / "body.json"
            body.write_text(json.dumps(payload), encoding="utf-8")
            result = json.loads(mutate([*command, "--json", f"@{body}"], env=environment))
        record(f"Databricks `{method.upper()} {endpoint}`: completed.")
        return result

    def ensure(group: str, endpoint: str, payload: dict, existing: list):
        matches = [item for item in existing if item["name"] == payload["name"]]
        if len(matches) > 1:
            raise ContextError(f"Ambiguous existing {group}: {payload['name']}")
        if matches:
            item = matches[0]
            if item.get("comment") != comment:
                raise ContextError(f"STOP: {group} {payload['name']} was not created by us.")
            for key in ("storage_root", "url", "credential_name"):
                if key in payload:
                    actual = item.get(key)
                    if not isinstance(actual, str) or actual.rstrip("/") != payload[key].rstrip("/"):
                        raise ContextError(f"STOP: existing {payload['name']} has a different {key}.")
            print(f"Reuse {group}: {payload['name']}", flush=True)
            return item
        return write("post", endpoint, {**payload, "comment": comment})

    identity = read("current-user", "me")
    principal = identity["userName"]
    if principal.casefold() != config["tenant"]["admin_upn"].casefold():
        raise ContextError("Databricks identity differs from the approved demo administrator.")
    ensure_storage_network(config, dry_run=args.dry_run)
    assignment = read("metastores", "current")
    if assignment["metastore_id"] != azure["databricks_metastore_id"]:
        raise ContextError("Assigned metastore differs from the explicitly approved metastore.")
    metastore = read("metastores", "get", assignment["metastore_id"])
    if metastore["external_access_enabled"] is not True:
        if azure.get("metastore_external_access_approved") is not True:
            raise ContextError("Human approval is required before changing this existing metastore.")
        # https://docs.databricks.com/api/uc-metastores/v1/update-metastore
        write("patch", f"/api/2.1/unity-catalog/metastores/{assignment['metastore_id']}",
              {"external_access_enabled": True})
        if not args.dry_run:
            metastore = read("metastores", "get", assignment["metastore_id"])
            if metastore["external_access_enabled"] is not True:
                raise RuntimeError("Metastore external-access read-back failed.")
            record("Approved metastore external access: PASS (enabled; no other settings changed).")

    # https://docs.databricks.com/api/uc-credentials/v1/create-storage-credential
    credentials = read("storage-credentials", "list")
    credential = ensure("credential", "/api/2.1/unity-catalog/storage-credentials", {
        "name": "sc_demo",
        "azure_managed_identity": {"access_connector_id": azure["access_connector_id"]},
        "read_only": False,
    }, credentials)
    if credential is not None:
        connector = credential["azure_managed_identity"]["access_connector_id"]
        if connector.casefold() != azure["access_connector_id"].casefold():
            raise ContextError("Existing sc_demo points to a different access connector.")
        if not args.dry_run:
            azure["databricks_storage_credential_id"] = credential["id"]
            save_config(config)

    locations = read("external-locations", "list")
    catalogs = read("catalogs", "list")
    for stage, stage_config in config["environments"].items():
        catalog_name = stage_config["databricks_catalog"]
        root = (f"abfss://{stage_config['storage_container']}@"
                f"{azure['storage_account_name']}.dfs.core.windows.net/")
        # https://docs.databricks.com/api/uc-external-locations/v1/create-external-location
        location = ensure("external location", "/api/2.1/unity-catalog/external-locations", {
            "name": f"el_uc_{stage}", "url": root, "credential_name": "sc_demo",
            "enable_file_events": False,
        }, locations)
        if location is not None and (
            location.get("enable_file_events") is True
            or location.get("effective_enable_file_events") is True
        ):
            raise RuntimeError("File events must stay disabled: no extra Azure queue/Event Grid resources.")
        # https://docs.databricks.com/api/uc-catalogs/v1/create-catalog
        catalog = ensure("catalog", "/api/2.1/unity-catalog/catalogs", {
            "name": catalog_name, "storage_root": root,
        }, catalogs)
        if not args.dry_run:
            stage_config["databricks_managed_location"] = root
            stage_config["databricks_catalog_storage_location"] = catalog["storage_location"]
            stage_config["databricks_external_location"] = f"el_uc_{stage}"
            save_config(config)
        schemas = read("schemas", "list", catalog_name) if catalog is not None else []
        for schema in ("bronze", "silver", "gold"):
            # https://docs.databricks.com/api/uc-schemas/v1/create-schema
            created = ensure("schema", "/api/2.1/unity-catalog/schemas", {
                "name": schema, "catalog_name": catalog_name,
            }, schemas)
            if created is not None and not args.dry_run:
                stage_config.setdefault("databricks_schema_ids", {})[schema] = created["schema_id"]
                save_config(config)
        # https://docs.databricks.com/api/uc-grants/v1/update-permissions
        for kind, name, privileges in (
            ("catalog", catalog_name, ["USE_CATALOG"]),
            ("schema", f"{catalog_name}.gold", ["USE_SCHEMA", "SELECT", "EXTERNAL_USE_SCHEMA"]),
        ):
            if catalog is None:
                missing = privileges
            else:
                grants = read("grants", "get", kind, name, "--principal", principal)
                assigned = explicit_privileges(grants, principal)
                missing = [privilege for privilege in privileges if privilege not in assigned]
            if missing:
                write("patch", f"/api/2.1/unity-catalog/permissions/{kind}/{name}",
                      {"changes": [{"principal": principal, "add": missing}]})
        if not args.dry_run:
            grants = read("grants", "get", "schema", f"{catalog_name}.gold", "--principal", principal)
            if "EXTERNAL_USE_SCHEMA" not in explicit_privileges(grants, principal):
                record(f"Explicit EXTERNAL USE SCHEMA on `{catalog_name}.gold`: FAILED.")
                raise RuntimeError(f"Explicit EXTERNAL USE SCHEMA check failed: {catalog_name}.gold")
            record(f"Explicit EXTERNAL USE SCHEMA on `{catalog_name}.gold`: PASS.")

    if args.dry_run:
        print("DRY-RUN: Unity Catalog plan complete; no IDs, settings or data changed.")
        print("DRY-RUN: storage probes will use one owned serverless 2X-Small warehouse, auto-stop 15 minutes.")
        return
    record("Unity Catalog credentials, stage locations/catalogs/schemas and explicit grants: PASS.")
    print("Unity Catalog setup: PASS. First-table managed-storage check remains to run.")


if __name__ == "__main__":
    try:
        main()
    except ContextError as error:
        record(f"Databricks bootstrap blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
