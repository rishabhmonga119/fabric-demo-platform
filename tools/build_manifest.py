"""Snapshot the actual owned SharePoint baseline file lists without changing files."""

import argparse
from hashlib import sha256
from pathlib import Path
import sys
from urllib.parse import urlparse

from azure.core.exceptions import ClientAuthenticationError

from bootstrap_fabric_items import MARKER
from common import ContextError, ROOT, is_metadata_ci, load_config, verify_context, write_snapshot
from http_api import Api, ApiError
from upload_sharepoint import graph_credential, verify_uploaded_workbook

sys.path.insert(0, str(ROOT))
from infra.deploy import record


def capture_manifest(config: dict) -> dict:
    def prompt(uri, code, expires_on):
        raise ContextError("Human SharePoint sign-in required: run upload_sharepoint.py --authenticate.")

    graph = Api("https://graph.microsoft.com", config["tenant"]["id"],
                credential=graph_credential(config, prompt))
    me = graph.request("GET", "/v1.0/me?$select=id,userPrincipalName")
    if me["userPrincipalName"].casefold() != config["tenant"]["admin_upn"].casefold():
        raise ContextError("SharePoint baseline identity differs from the DEMO administrator.")
    sharepoint = config["sharepoint"]
    drive = graph.request("GET", f"/v1.0/sites/{sharepoint['site_id']}/drive")
    if drive["id"] != sharepoint["drive_id"]:
        raise ContextError("SharePoint document-library identity differs; no baseline rebind.")
    host = urlparse(sharepoint["site_url"]).netloc
    root = f"/v1.0/drives/{drive['id']}"
    result = {"owner": MARKER, "version": 1, "site_id": sharepoint["site_id"],
              "drive_id": drive["id"], "stages": {}}
    for name, stage in config["environments"].items():
        folder = stage["sharepoint_folder"]
        if folder != "Forecasts/" + name.title():
            raise ContextError("Forecast folder is not stage isolated.")
        files = {}
        for layout in ("standard", "raw"):
            directory = graph.request("GET", root + f"/root:/{folder}/{layout}")
            children = graph.list(root + f"/items/{directory['id']}/children")
            local = sorted((ROOT / "seed" / "excel" / name / layout).glob("*.xlsx"))
            if len(local) != 3 or sorted(item["name"] for item in children) != [path.name for path in local] or \
                    any("file" not in item for item in children):
                raise ContextError(f"{name}/{layout} differs from the exact three baseline workbooks.")
            by_name = {item["name"]: item for item in children}
            for path in local:
                key = layout + "/" + path.name
                known = stage["sharepoint_files"].get(key)
                item = by_name[path.name]
                content = path.read_bytes()
                digest = sha256(content).hexdigest()
                if not known or not known.get("verified") or known["id"] != item["id"] or \
                        known["sha256"] != digest:
                    raise ContextError(f"{name}/{key} is unowned, unverified or differs from its seed.")
                if item["eTag"] != known["etag"]:
                    detail = graph.request("GET", root + f"/items/{item['id']}")
                    verify_uploaded_workbook(detail, content, host, path.name)
                files[key] = {"item_id": item["id"], "etag": item["eTag"],
                              "size": item["size"], "seed_sha256": digest}
        result["stages"][name] = {"folder": folder, "files": files}
        print(f"PASS SharePoint {name}: exactly six owned baseline workbooks; late file absent.")
    return result


def manifest_file_sets(manifest: dict) -> dict:
    return {"site_id": manifest["site_id"], "drive_id": manifest["drive_id"], "stages": {
        stage: {"folder": value["folder"], "files": {
        name: entry["seed_sha256"] for name, entry in value["files"].items()}}
        for stage, value in manifest["stages"].items()}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("seed") / "manifest.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if is_metadata_ci():
        raise ContextError("SharePoint baseline capture requires the delegated DEMO administrator.")
    verify_context()
    write_snapshot(args.out, capture_manifest(load_config()), dry_run=args.dry_run)
    if not args.dry_run:
        record(f"Step 9 actual SharePoint manifest captured at {args.out}: 18 owned stage workbooks, "
               "current IDs/ETags/sizes and independently known seed hashes. Changed versions "
               "require exact workbook cell equality. No Graph writes. References: "
               "https://learn.microsoft.com/graph/api/driveitem-list-children; "
               "https://learn.microsoft.com/graph/api/driveitem-get; tools/upload_sharepoint.py.")


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ApiError, OSError, ValueError, ClientAuthenticationError) as error:
        message = "Delegated Graph cache requires human reauthentication." \
            if isinstance(error, ClientAuthenticationError) else str(error)
        if "--dry-run" not in sys.argv:
            record(f"SharePoint baseline manifest blocked: {message}")
        print(f"STOP: {message}", file=sys.stderr)
        raise SystemExit(1) from error
