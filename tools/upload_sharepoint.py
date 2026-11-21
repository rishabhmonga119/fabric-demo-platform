"""Create the demo site and upload exactly six stage workbooks via delegated Graph."""

import argparse
from hashlib import sha256
from io import BytesIO
import sys
import time
from urllib.parse import quote, urlencode, urlparse
from urllib.error import HTTPError
from urllib.request import Request, build_opener
from zipfile import ZipFile, is_zipfile

from azure.identity import AuthenticationRecord, DeviceCodeCredential, TokenCachePersistenceOptions
from openpyxl import load_workbook

from common import ContextError, ROOT, load_config, verify_context
from http_api import AcceptedWithoutGraphLocation, Api, ApiError, NoRedirects
from prepare_sharepoint_auth import SCOPES

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config


def assert_readable_xlsx(content: bytes, name: str) -> None:
    if not is_zipfile(BytesIO(content)):
        raise ContextError(f"{name}: not a readable XLSX ZIP container; protected/encrypted files require human policy review before upload.")
    with ZipFile(BytesIO(content)) as archive:
        if not {"[Content_Types].xml", "xl/workbook.xml"}.issubset(archive.namelist()):
            raise ContextError(f"{name}: ZIP contents are not a normal XLSX workbook.")


def workbook_values(content: bytes) -> dict:
    book = load_workbook(BytesIO(content), read_only=True)
    try:
        return {sheet.title: list(sheet.values) for sheet in book.worksheets}
    finally:
        book.close()


def verify_uploaded_workbook(item: dict, content: bytes, site_host: str, filename: str) -> None:
    if item["name"] != filename or "file" not in item or item["size"] <= 0:
        raise ApiError(f"Uploaded workbook identity/type/size is invalid: {filename}")
    download_url = item.get("@microsoft.graph.downloadUrl")
    parsed = urlparse(download_url or "")
    if parsed.scheme != "https" or parsed.netloc.casefold() != site_host.casefold():
        raise ApiError("Workbook verification requires a fresh same-tenant SharePoint download URL.")
    # The short-lived Graph URL is already authorized; never send a bearer token or log it.
    with build_opener(NoRedirects()).open(Request(download_url), timeout=120) as response:
        remote = response.read()
    assert_readable_xlsx(remote, filename)
    if workbook_values(remote) != workbook_values(content):
        raise ApiError(f"Uploaded workbook sheet/cell values differ: {filename}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--authenticate", action="store_true",
                        help="Permit the human device-code/consent prompt; no SharePoint writes.")
    parser.add_argument("--site-url", help="Authoritative DemoData site URL; required before creation.")
    parser.add_argument("--inspect-site", action="store_true",
                        help="Read only the named site's metadata without creating/uploading anything.")
    parser.add_argument("--inspect-file",
                        help="Read only a drive-relative file's identity/size/type metadata.")
    args = parser.parse_args()
    verify_context()
    config = load_config()
    application = config["sharepoint"].get("application")
    if not application:
        raise ContextError("Run prepare_sharepoint_auth.py first.")
    inputs = {}
    for stage in config["environments"]:
        inputs[stage] = sorted((ROOT / "seed" / "excel" / stage).glob("*\\*.xlsx"))
        if len(inputs[stage]) != 6:
            raise ContextError(f"Expected six local standard/raw workbooks for {stage}.")
        for path in inputs[stage]:
            assert_readable_xlsx(path.read_bytes(), str(path))
    if args.dry_run:
        print("DRY-RUN: delegated demo-admin login; create only DemoData through Graph beta and poll its operation; upload three standard and three raw files per stage. Live workbook excluded; unowned file conflicts STOP.")
        return
    auth_path = ROOT / ".venv" / "sharepoint-authentication-record.json"

    def prompt(uri, code, expires_on):
        if not args.authenticate:
            raise ContextError("Human consent/device sign-in required: run upload_sharepoint.py --authenticate.")
        print(f"HUMAN ACTION: open {uri} and enter {code}; sign in as {config['tenant']['admin_upn']} and consent only to the displayed demo upload permissions.", flush=True)

    authentication_record = AuthenticationRecord.deserialize(auth_path.read_text(encoding="utf-8")) \
        if auth_path.exists() else None
    credential = DeviceCodeCredential(
        tenant_id=config["tenant"]["id"], client_id=application["client_id"],
        prompt_callback=prompt, authentication_record=authentication_record,
        cache_persistence_options=TokenCachePersistenceOptions(
            name="fabric-demo-sharepoint", allow_unencrypted_storage=False),
    )
    scopes = [f"https://graph.microsoft.com/{scope}" for scope in SCOPES]
    if args.authenticate:
        authenticated = credential.authenticate(scopes=scopes)
        auth_path.write_text(authenticated.serialize(), encoding="utf-8")
    graph = Api("https://graph.microsoft.com", config["tenant"]["id"], credential=credential)
    identity = graph.request("GET", "/v1.0/me?$select=id,userPrincipalName")
    if identity["userPrincipalName"].casefold() != config["tenant"]["admin_upn"].casefold():
        raise ContextError("Delegated SharePoint identity differs from the required demo admin.")
    if args.authenticate:
        record("Delegated SharePoint demo-admin login verified; encrypted token cache is outside Git; no SharePoint writes.")
        print("SharePoint authentication verified. Run upload_sharepoint.py with the DemoData site URL next.")
        return
    sharepoint = config["sharepoint"]
    site_url = args.site_url or sharepoint.get("site_url")
    parsed = urlparse(site_url or "")
    if parsed.scheme != "https" or not parsed.netloc.endswith(".sharepoint.com") or \
            parsed.path.casefold() != "/sites/demodata" or parsed.query or parsed.fragment:
        raise ContextError("Provide the authoritative HTTPS SharePoint /sites/DemoData URL.")
    if sharepoint.get("site_url") not in (None, site_url):
        raise ContextError("Configured DemoData site URL differs; no rebinding.")
    if args.inspect_site:
        site = graph.request("GET", f"/v1.0/sites/{parsed.netloc}:{parsed.path}")
        print({key: site.get(key) for key in ("id", "webUrl", "displayName", "createdDateTime")})
        return
    if args.inspect_file:
        if not sharepoint.get("drive_id"):
            raise ContextError("Recorded document library is required for file inspection.")
        item = graph.request("GET", f"/v1.0/drives/{sharepoint['drive_id']}/root:/{quote(args.inspect_file, safe='/')}")
        print({key: item.get(key) for key in ("id", "name", "size", "file", "createdBy", "createdDateTime")})
        return
    if not sharepoint.get("site_id"):
        if sharepoint.get("creation_operation"):
            operation_uri = sharepoint["creation_operation"]
        elif sharepoint.get("creation_accepted"):
            operation_uri = None
        else:
            # https://learn.microsoft.com/graph/api/site-post-sites?view=graph-rest-beta
            try:
                response = graph.request("POST", "/beta/sites", {
                    "name": sharepoint["site_name"], "webUrl": site_url, "locale": "en-US",
                    "shareByEmailEnabled": False, "description": "Synthetic beverage demo forecasts.",
                    "template": "sitepagepublishing",
                    "ownerIdentityToResolve": {"email": config["tenant"]["admin_upn"]},
                }, accept_operation=True)
                operation_uri = response["operation_uri"]
                sharepoint["creation_operation"] = operation_uri
            except AcceptedWithoutGraphLocation:
                operation_uri = None
                record("Graph accepted DemoData creation without a usable Graph-origin operation Location; no credentials forwarded to another origin. Verify named site/default-drive readiness through Graph instead; do not claim a terminal LRO status.")
            sharepoint["creation_accepted"] = True
            sharepoint["site_url"] = site_url
            save_config(config)
            record("Submitted owned DemoData site creation; waiting for documented Graph operation.")
        deadline = time.monotonic() + 900
        while operation_uri and time.monotonic() < deadline:
            # https://learn.microsoft.com/graph/api/site-getoperationstatus?view=graph-rest-beta
            status = graph.request("GET", operation_uri)["status"]
            if status == "succeeded":
                break
            if status == "failed":
                raise ApiError("DemoData site creation operation failed.")
            if status not in ("notStarted", "running"):
                raise ApiError(f"Unsupported site creation operation state: {status}")
            time.sleep(10)
        if operation_uri and time.monotonic() >= deadline:
            raise TimeoutError("DemoData site creation did not complete within 15 minutes.")
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            try:
                site = graph.request("GET", f"/v1.0/sites/{parsed.netloc}:{parsed.path}")
                graph.request("GET", f"/v1.0/sites/{site['id']}/drive")
                break
            except ApiError as error:
                if not isinstance(error.__cause__, HTTPError) or error.__cause__.code != 404:
                    raise
                time.sleep(10)
        else:
            raise TimeoutError("Accepted DemoData site/default drive did not become readable within 15 minutes.")
        if site["webUrl"].rstrip("/").casefold() != site_url.rstrip("/").casefold():
            raise ContextError("Created site read-back differs from the requested DemoData URL.")
        sharepoint["site_id"] = site["id"]
        save_config(config)
        record(f"DemoData site creation/read-back verified: `{site['id']}`.")
    site = graph.request("GET", f"/v1.0/sites/{sharepoint['site_id']}")
    if site["webUrl"].rstrip("/").casefold() != site_url.rstrip("/").casefold():
        raise ContextError("Configured site identity differs from DemoData.")
    drive = graph.request("GET", f"/v1.0/sites/{sharepoint['site_id']}/drive")
    if sharepoint.get("drive_id") not in (None, drive["id"]):
        raise ContextError("Configured document library differs; no rebind.")
    sharepoint["drive_id"] = drive["id"]
    save_config(config)
    drive_root = f"/v1.0/drives/{drive['id']}"

    def children(parent: str) -> list:
        return graph.list(f"{drive_root}/items/{parent}/children")

    def folder(parent: str, name: str) -> str:
        matches = [item for item in children(parent) if item["name"] == name]
        if matches:
            if len(matches) != 1 or "folder" not in matches[0]:
                raise ContextError(f"Folder path conflict: {name}")
            return matches[0]["id"]
        # https://learn.microsoft.com/graph/api/driveitem-post-children
        created = graph.request("POST", f"{drive_root}/items/{parent}/children",
                                {"name": name, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"})
        return created["id"]

    parent = folder(graph.request("GET", drive_root + "/root")["id"], "Forecasts")
    for stage, files in inputs.items():
        stage_config = config["environments"][stage]
        stage_parent = folder(parent, stage_config["sharepoint_folder"].split("/")[-1])
        registered = stage_config.setdefault("sharepoint_files", {})
        for layout in ("standard", "raw"):
            destination = folder(stage_parent, layout)
            for path in [file for file in files if file.parent.name == layout]:
                content = path.read_bytes()
                assert_readable_xlsx(content, str(path))
                digest = sha256(content).hexdigest()
                key = layout + "/" + path.name
                existing = [item for item in children(destination) if item["name"] == path.name]
                entry = registered.get(key)
                if existing:
                    if len(existing) != 1:
                        raise ContextError(f"Refusing to overwrite unowned SharePoint file: {key}")
                    if not entry:
                        creator = existing[0].get("createdBy", {}).get("application", {}).get("id")
                        if creator != application["client_id"]:
                            raise ContextError(f"Refusing to overwrite unowned SharePoint file: {key}")
                        recovered = graph.request("GET", f"{drive_root}/items/{existing[0]['id']}")
                        verify_uploaded_workbook(recovered, content, parsed.netloc, path.name)
                        registered[key] = {"id": recovered["id"], "etag": recovered["eTag"],
                                           "sha256": digest, "verified": True}
                        save_config(config)
                        record(f"Recovered previously created `{stage}/{key}` by verified creator-app identity and exact sheet/cell equality; no overwrite.")
                        continue
                    if entry["id"] != existing[0]["id"]:
                        raise ContextError(f"Refusing to overwrite unowned SharePoint file: {key}")
                    if entry.get("verified") and entry["sha256"] == digest and entry.get("etag") == existing[0]["eTag"]:
                        continue
                    endpoint = f"{drive_root}/items/{entry['id']}/content"
                else:
                    # driveItem resource: explicit fail avoids PUT's default replace behavior.
                    query = urlencode({"@microsoft.graph.conflictBehavior": "fail"})
                    endpoint = f"{drive_root}/items/{destination}:/{quote(path.name)}:/content?{query}"
                # https://learn.microsoft.com/graph/api/driveitem-put-content
                uploaded = graph.request("PUT", endpoint, content,
                                         content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                registered[key] = {"id": uploaded["id"], "sha256": digest, "verified": False}
                save_config(config)
                verified = graph.request("GET", f"{drive_root}/items/{uploaded['id']}")
                verify_uploaded_workbook(verified, content, parsed.netloc, path.name)
                registered[key] = {"id": verified["id"], "etag": verified["eTag"],
                                   "sha256": digest, "verified": True}
                save_config(config)
                record(f"Uploaded synthetic `{stage}/{key}`: `{verified['id']}`.")
        actual = [(layout, item["name"]) for layout in ("standard", "raw")
                  for item in children(folder(stage_parent, layout)) if "file" in item]
        expected = [(file.parent.name, file.name) for file in files]
        if sorted(actual) != sorted(expected):
            raise ApiError(f"Stage {stage} does not contain exactly the six expected SharePoint files.")
        record(f"Step 4 Check `{stage}`: exactly six expected SharePoint workbooks PASS; live file absent.")
    print("Step 4 SharePoint file checks: PASS for all three stages.")


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ApiError) as error:
        record(f"SharePoint upload blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
