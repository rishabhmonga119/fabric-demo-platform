"""Create, inspect or delete only the approved Partner A rehearsal IQ Share."""

import argparse
from base64 import b64decode, b64encode
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
import sys
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request
from uuid import UUID

from bootstrap_fabric_items import MARKER, post_and_wait, wait_operation
from capacity_guard import verify_stage_capacity
from common import ContextError, ROOT, is_metadata_ci, load_config, verify_context
from http_api import Api, ApiError

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config

NAME = "SH_PartnerA_Rehearsal"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/share/definition/share/1.0.0/schema.json"
REFERENCES = (
    "e2e-medallion-architecture/SKILL.md; fabric-skills/common/COMMON-CORE.md; COMMON-CLI.md; "
    "https://learn.microsoft.com/rest/api/fabric/share/items/create-share; "
    "https://learn.microsoft.com/rest/api/fabric/share/items/get-share-definition; "
    "https://learn.microsoft.com/rest/api/fabric/share/items/delete-share; " + SCHEMA
)


def share_document(config: dict, recipient: str, expires: str) -> dict:
    partner = config["partner"]
    if UUID(partner["tenant_b_id"]) == UUID(config["tenant"]["id"]):
        raise ContextError("The partner tenant must differ from the DEMO producer tenant.")
    if recipient.count("@") != 1 or \
            recipient.split("@")[1].casefold() != partner["tenant_b_domain"].casefold():
        raise ContextError("Recipient UPN must belong to the explicitly configured tenant-B domain.")
    expiry = datetime.fromisoformat(expires.replace("Z", "+00:00"))
    if not expires.endswith("Z") or expiry.tzinfo is None:
        raise ContextError("Share expiration must be an explicit UTC timestamp ending in Z.")
    return {
        "$schema": SCHEMA,
        "assets": [{"item": {"referenceType": "ById", "workspaceId": partner["workspace_id"],
                             "itemId": partner["items"]["LH_PartnerA"]["id"]},
                    "shareAs": "MirroredOneLake"}],
        "recipients": [{"type": "User", "userPrincipalName": recipient,
                        "tenantId": partner["tenant_b_id"]}],
        "sharePolicies": [{"type": "ShareExpiration", "properties": {
            "expirationDateTime": expiry.strftime("%Y-%m-%dT%H:%M:%SZ")}}],
    }


def canonical(document: dict) -> dict:
    result = deepcopy(document)
    for asset in result["assets"]:
        asset.setdefault("shareAs", "MirroredOneLake")
        asset["item"].setdefault("referenceType", "ById")
    for recipient in result["recipients"]:
        for field in ("userPrincipalName", "email"):
            if field in recipient:
                recipient[field] = recipient[field].casefold()
    for policy in result.get("sharePolicies", []):
        value = policy["properties"]["expirationDateTime"]
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            raise ApiError("Returned expiration has no timezone.")
        policy["properties"]["expirationDateTime"] = moment.astimezone(
            timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return result


def guard_shared_inventory(tables: set[str], files: set[str], lakehouse: str) -> None:
    root = f"{lakehouse}/Tables"
    expected = root + "/dbo/partner_a_deliveries"
    parents = {root, root + "/dbo", expected}
    if not any(path.startswith(expected + "/_delta_log/") for path in tables) or \
            any(path not in parents and not path.startswith(expected + "/") for path in tables):
        raise ContextError("The shared Tables tree must contain only the P-A Delta output.")
    if files != {f"{lakehouse}/Files/context/partner_glossary.md"}:
        raise ContextError("The shared item contains missing/unapproved files; no external Share.")


def onelake_read(api: Api, url: str) -> tuple[bytes, str | None]:
    token = api.credential.get_token("https://storage.azure.com/.default")
    request = Request(url, headers={"Authorization": "Bearer " + token.token,
                                   "x-ms-version": "2021-06-08"})
    with api.opener.open(request, timeout=60) as response:
        content = response.read(1048577)
        if len(content) > 1048576:
            raise ApiError("OneLake preflight response exceeds the small-demo size limit.")
        return content, response.headers.get("x-ms-continuation")


def list_paths(api: Api, base: str, workspace: str, directory: str) -> list[dict]:
    result, seen = [], set()
    continuation = None
    for _ in range(100):
        query = {"resource": "filesystem", "recursive": "true", "directory": directory}
        if continuation:
            query["continuation"] = continuation
        data, continuation = onelake_read(api, base + "/" + workspace + "?" + urlencode(query))
        result.extend(json.loads(data)["paths"])
        if not continuation:
            return result
        if continuation in seen:
            raise ApiError("Repeated OneLake file-list continuation token.")
        seen.add(continuation)
    raise ApiError("OneLake inventory exceeds the bounded demo page limit.")


def inventory(api: Api, config: dict, workspace: dict) -> None:
    partner = config["partner"]
    lakehouse = partner["items"]["LH_PartnerA"]["id"]
    root = f"/v1/workspaces/{partner['workspace_id']}"
    if partner.get("producer_verification") != "passed-notebook-exact-delta-and-glossary-readback":
        raise ContextError("The exact partner producer output must be verified before sharing.")
    target = api.request("GET", root + f"/items/{lakehouse}")
    if target["displayName"] != "LH_PartnerA" or target["type"] != "Lakehouse" or \
            not (target.get("description") or "").startswith(MARKER):
        raise ContextError("Only the owned, approved LH_PartnerA may be shared.")
    if api.list(root + f"/items/{lakehouse}/shortcuts"):
        raise ContextError("The partner item contains shortcuts; no external Share.")
    base = workspace["oneLakeEndpoints"]["dfsEndpoint"].rstrip("/")
    endpoint = urlparse(base)
    host = endpoint.hostname or ""
    if endpoint.scheme != "https" or endpoint.port not in (None, 443) or \
            not (host == "onelake.dfs.fabric.microsoft.com" or
                 host.endswith("-onelake.dfs.fabric.microsoft.com")):
        raise ContextError("Unexpected authenticated OneLake endpoint.")
    tables = {path["name"] for path in list_paths(
        api, base, partner["workspace_id"], lakehouse + "/Tables")}
    files = {path["name"] for path in list_paths(
        api, base, partner["workspace_id"], lakehouse + "/Files")
        if str(path.get("isDirectory", False)).casefold() != "true"}
    guard_shared_inventory(tables, files, lakehouse)
    glossary, _ = onelake_read(api, base + "/" + partner["workspace_id"] + "/" + lakehouse +
                               "/Files/context/partner_glossary.md")
    if glossary.decode("utf-8") != (ROOT / "partner" / "context" / "partner_glossary.md").read_text(
            encoding="utf-8"):
        raise ContextError("The actual shared glossary differs from the approved source.")
    print("PASS: whole-item inventory is one P-A Delta table and the exact glossary; no shortcuts.")


def inspect(api: Api, root: str, item: dict, expected: dict) -> tuple[dict, str]:
    definition = post_and_wait(api, root + f"/shares/{item['id']}/getDefinition", {},
                               False, "Rehearsal Share definition")
    parts = definition["definition"]["parts"]
    documents = [json.loads(b64decode(part["payload"])) for part in parts if part["path"] == "share.json"]
    if len(documents) != 1 or any(part["path"] not in ("share.json", ".platform") for part in parts) or \
            canonical(documents[0]) != canonical(expected):
        raise ContextError("Share assets, recipient or expiration differ; no overwrite or cleanup.")
    recipients = api.list(root + f"/shares/{item['id']}/recipients?beta=true")
    if len(recipients) != 1:
        raise ContextError("Rehearsal Share has an unexpected recipient count.")
    detail = api.request("GET", root + f"/shares/{item['id']}")
    print("RECIPIENT_ACCEPTANCE=" + recipients[0]["invitationAcceptanceStatus"])
    return detail, recipients[0]["invitationAcceptanceStatus"]


def invitation_url(detail: dict, tenant: str, workspace: str) -> str:
    properties = detail["properties"]
    invitation = properties.get("invitationUrl") or ""
    parsed = urlparse(invitation)
    fabric_path = parsed.hostname == "app.fabric.microsoft.com" and \
        parsed.path == "/share/invite/" + detail["id"] and not parsed.query
    powerbi_path = parsed.hostname == "app.powerbi.com" and parsed.path == "/iqshare/accept" and \
        parse_qs(parsed.query) == {
            "providerTenantId": [tenant], "workspaceId": [workspace], "shareId": [detail["id"]]}
    if properties["shareStatus"] != "Active" or parsed.scheme != "https" or \
            parsed.port not in (None, 443) or parsed.username or parsed.password or parsed.fragment or \
            not (fabric_path or powerbi_path):
        raise ApiError("Share is not Active with a matching first-party invitation URL.")
    return invitation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("create", "status", "delete"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--expires-utc")
    parser.add_argument("--approved-external-share", action="store_true")
    parser.add_argument("--approved-rehearsal-cleanup", action="store_true")
    args = parser.parse_args()
    if is_metadata_ci():
        raise ContextError("Metadata CI cannot create or manage external Shares.")
    verify_context()
    config = load_config()
    partner = config["partner"]
    configured = partner.setdefault("rehearsal_share", {})
    recipient = os.environ.get(partner["recipient_upn_env"], "").strip()
    if not recipient:
        raise ContextError("Set the configured recipient UPN environment variable locally; never commit it.")
    expires = args.expires_utc or configured.get("expires_utc")
    if not expires:
        raise ContextError("An explicit approved Share expiration is required.")
    expected = share_document(config, recipient, expires)
    if args.action == "create" and datetime.fromisoformat(
            expires.replace("Z", "+00:00")) <= datetime.now(timezone.utc):
        raise ContextError("New Share expiration must be in the future.")
    if not args.dry_run and ((args.action == "create" and not args.approved_external_share) or
                            (args.action == "delete" and not args.approved_rehearsal_cleanup)):
        raise ContextError("The requested external grant or scoped cleanup requires explicit approval.")
    api = Api("https://api.fabric.microsoft.com", config["tenant"]["id"],
              skill="e2e-medallion-architecture")
    root = f"/v1/workspaces/{partner['workspace_id']}"
    workspace = api.request("GET", root)
    verify_stage_capacity(api, config, workspace, partner)
    if configured.get("create_operation_uri"):
        if args.dry_run:
            print("DRY-RUN: resume the recorded Share create operation before any further action.")
            return
        result = wait_operation(api, configured["create_operation_uri"], NAME)
        configured["id"] = result["id"]
        configured.pop("create_operation_uri")
        save_config(config)
    matches = [item for item in api.list(root + "/items?type=Share") if item["displayName"] == NAME]
    if len(matches) > 1 or matches and (
            not (matches[0].get("description") or "").startswith(MARKER) or
            configured.get("id") not in (None, matches[0]["id"])):
        raise ContextError("Rehearsal Share is unowned or conflicts with its recorded ID.")
    if not matches:
        if args.action == "delete" and configured.get("state") == "Deleted":
            print("PASS: recorded rehearsal Share is already absent.")
            return
        if args.action != "create" or configured.get("id") and configured.get("state") != "Deleted":
            raise ContextError("The configured rehearsal Share is missing; no automatic replacement.")
        inventory(api, config, workspace)
        definition = {"parts": [{"path": "share.json", "payloadType": "InlineBase64",
                                 "payload": b64encode(json.dumps(expected).encode()).decode()}]}
        submitted = api.request("POST", root + "/shares", {
            "displayName": NAME, "description": MARKER + ": temporary P-A-only cross-tenant rehearsal.",
            "definition": definition}, dry_run=args.dry_run,
            accept_operation=True, with_response_info=True)
        if args.dry_run:
            print("DRY-RUN: one output-only asset, one approved tenant-B recipient, exact expiration.")
            return
        configured["expires_utc"] = expires
        if submitted["status_code"] == 202:
            configured["create_operation_uri"] = submitted["body"]["operation_uri"]
            save_config(config)
            item = wait_operation(api, configured["create_operation_uri"], NAME,
                                  retry_after=submitted["retry_after"])
            configured.pop("create_operation_uri")
        else:
            item = submitted["body"]
        configured.update({"id": item["id"], "state": "Created"})
        save_config(config)
        record(f"Created owned rehearsal IQ Share {item['id']} for the one approved tenant-B "
               f"recipient; source only LH_PartnerA; expiry {expires}. Recipient/invitation "
               f"kept out of public configuration and logs. References: {REFERENCES}.")
    else:
        item = matches[0]
        if args.action == "create":
            inventory(api, config, workspace)
    detail, acceptance = inspect(api, root, item, expected)
    if args.action == "delete":
        if configured.get("id") != item["id"]:
            raise ContextError("Only a recorded Share created by this automation can be deleted.")
        api.request("DELETE", root + f"/shares/{item['id']}", dry_run=args.dry_run)
        if not args.dry_run:
            if any(row["id"] == item["id"] for row in api.list(root + "/items?type=Share")):
                raise ApiError("Deleted rehearsal Share is still present in item readback.")
            configured["state"] = "Deleted"
            save_config(config)
            record(f"Approved rehearsal Share {item['id']} deletion/absence verified. "
                   "No producer data or consumer-tenant item was deleted.")
        return
    invitation = invitation_url(detail, config["tenant"]["id"], partner["workspace_id"])
    if not args.dry_run:
        configured.update({"id": item["id"], "expires_utc": expires, "state": "Active",
                           "recipient_acceptance_status": acceptance})
        if not partner.get("sharing_verification", "").startswith(("verified", "user-confirmed")):
            partner["sharing_verification"] = "pending-consumer-query" if acceptance == "Active" else \
                "pending-consumer-acceptance-and-query"
        save_config(config)
        record(f"Rehearsal Share {item['id']} readback PASS: exact single asset/recipient/expiration, "
               f"Active invitation, recipient acceptance {acceptance}. "
               "Source readback does not itself verify a consumer query.")
    print("INVITATION_URL=" + invitation)


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ApiError, OSError, ValueError, TimeoutError) as error:
        if "--dry-run" not in sys.argv:
            record(f"Partner IQ Share action blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
