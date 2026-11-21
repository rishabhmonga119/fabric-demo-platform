"""Create only the owned single-tenant public client needed for delegated uploads."""

import argparse
import sys
from urllib.parse import urlencode

from common import ContextError, ROOT, load_config, verify_context
from http_api import Api

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config

GRAPH = "00000003-0000-0000-c000-000000000000"
SCOPES = ("Sites.Create.All", "Sites.Selected", "User.Read")
NAME = "app-demo-sharepoint-upload"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    verify_context()
    config = load_config()
    graph = Api("https://graph.microsoft.com", config["tenant"]["id"])
    services = graph.list("/v1.0/servicePrincipals?" + urlencode({"$filter": f"appId eq '{GRAPH}'"}))
    if len(services) != 1:
        raise ContextError("Expected one Microsoft Graph service principal.")
    scope_ids = {item["value"]: item["id"] for item in services[0]["oauth2PermissionScopes"]
                 if item["isEnabled"]}
    if any(scope not in scope_ids for scope in SCOPES):
        raise ContextError("Required documented Graph delegated site scopes are unavailable.")
    tags = ["copilot-demo-build", f"demoOwner:{config['github']['owner']}/{config['github']['repository']}"]
    payload = {
        "displayName": NAME, "signInAudience": "AzureADMyOrg", "isFallbackPublicClient": True,
        "tags": tags, "description": "Delegated demo-site provisioning and synthetic forecast uploads; no client secret.",
        "requiredResourceAccess": [{"resourceAppId": GRAPH,
                                   "resourceAccess": [{"id": scope_ids[scope], "type": "Scope"}
                                                      for scope in SCOPES]}],
    }
    # https://learn.microsoft.com/graph/api/application-post-applications
    # https://learn.microsoft.com/graph/api/resources/application
    apps = graph.list("/v1.0/applications?" + urlencode({"$filter": f"displayName eq '{NAME}'"}))
    if len(apps) > 1:
        raise ContextError("Multiple matching SharePoint upload applications.")
    if apps:
        app = apps[0]
        if set(app.get("tags", [])) != set(tags) or app["signInAudience"] != "AzureADMyOrg":
            raise ContextError("Existing same-name application is not the owned single-tenant demo client.")
        actual = {(resource["resourceAppId"], permission["id"], permission["type"])
                  for resource in app["requiredResourceAccess"] for permission in resource["resourceAccess"]}
        expected = {(GRAPH, scope_ids[scope], "Scope") for scope in SCOPES}
        if app.get("isFallbackPublicClient") is not True or actual != expected:
            raise ContextError("Existing upload app authentication/permissions differ; no silent rewrite.")
    else:
        app = graph.request("POST", "/v1.0/applications", payload, dry_run=args.dry_run)
        if args.dry_run:
            print("DRY-RUN: one secret-free public client, delegated Sites.Create.All, Sites.Selected, User.Read; human consent/device login required.")
            return
    if args.dry_run:
        print("DRY-RUN: existing owned upload public client is correctly configured; no writes.")
        return
    configured = config["sharepoint"].get("application", {})
    if configured.get("object_id") not in (None, app["id"]):
        raise ContextError("Configured upload application differs from the discovered owned client.")
    config["sharepoint"]["application"] = {
        "name": NAME, "client_id": app["appId"], "object_id": app["id"],
        "delegated_scopes": list(SCOPES),
    }
    save_config(config)
    record(f"Prepared owned single-tenant public client `{NAME}`, object `{app['id']}`, for delegated site creation/selected-site access; no secrets or consent grants created. Human consent/login remains required.")
    print("Upload public client ready. Human admin consent/device-code sign-in is required before SharePoint writes.")


if __name__ == "__main__":
    try:
        main()
    except ContextError as error:
        record(f"SharePoint authentication preparation blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
