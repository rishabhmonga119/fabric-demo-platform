"""Create Step 2 demo groups, OIDC application and users without persisting secrets."""

import argparse
import json
import secrets
import string
import sys
import time
from urllib.parse import urlencode

from common import ContextError, ROOT, cli, load_config, run, verify_context
from http_api import Api, ApiError

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config


def unique(items: list, field: str, value: str) -> dict | None:
    found = [item for item in items if item.get(field, "").casefold() == value.casefold()]
    if len(found) > 1:
        raise ContextError(f"Ambiguous existing object: {value}")
    return found[0] if found else None


def initial_password() -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "Aa1!" + "".join(secrets.choice(alphabet) for _ in range(28))


def has_membership(api: Api, group_id: str, member_id: str) -> bool:
    # v1.0 /groups/id/members omits SPs; this documented API supports them.
    # https://learn.microsoft.com/graph/api/directoryobject-checkmembergroups
    result = api.request("POST", f"/v1.0/directoryObjects/{member_id}/checkMemberGroups",
                         {"groupIds": [group_id]})
    if result is None or not isinstance(result.get("value"), list):
        raise ApiError("Graph membership-check response is missing its value collection.")
    return group_id in result["value"]


def federation_subjects(repository: dict, oidc: dict) -> dict[str, str]:
    owner, name = repository["full_name"].split("/")
    if oidc.get("use_default") is not True:
        raise ContextError("Custom GitHub OIDC subjects require an explicit verified template.")
    if oidc.get("use_immutable_subject") is True:
        prefix = f"repo:{owner}@{repository['owner']['id']}/{name}@{repository['id']}"
    else:
        prefix = f"repo:{owner}/{name}"
    if oidc.get("sub_claim_prefix", prefix) != prefix:
        raise ContextError("GitHub OIDC prefix does not match the verified repository/owner IDs.")
    return {
        "github-test": prefix + ":environment:test",
        "github-prod": prefix + ":environment:prod",
        "github-main": prefix + ":ref:refs/heads/main",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    verify_context()
    config = load_config()
    api = Api("https://graph.microsoft.com", config["tenant"]["id"])
    owner = f"{config['github']['owner']}/{config['github']['repository']}"
    description = f"Demo automation owned by {owner}"
    me = api.request("GET", "/v1.0/me?$select=id,userPrincipalName")
    if me is None or me["userPrincipalName"].casefold() != config["tenant"]["admin_upn"].casefold():
        raise ContextError("Graph identity does not match the demo administrator.")

    def objects(collection: str, field: str, value: str, select: str) -> list:
        escaped = value.replace("'", "''")
        query = urlencode({"$filter": f"{field} eq '{escaped}'", "$select": select})
        return api.list(f"/v1.0/{collection}?{query}")

    # https://learn.microsoft.com/graph/api/group-post-groups
    for key, group_config in config["entra"]["groups"].items():
        group = unique(objects("groups", "displayName", group_config["name"],
                               "id,displayName,description,securityEnabled"), "displayName",
                       group_config["name"])
        if group:
            if group["description"] != description or group["securityEnabled"] is not True:
                raise ContextError(f"STOP: existing group {group_config['name']} is not owned by this automation.")
            if group_config["id"] and group_config["id"] != group["id"]:
                raise ContextError("Configured group ID differs from the existing group.")
        else:
            payload = {
                "displayName": group_config["name"], "description": description,
                "mailEnabled": False, "mailNickname": group_config["name"],
                "securityEnabled": True, "groupTypes": [],
                "owners@odata.bind": [f"https://graph.microsoft.com/v1.0/users/{me['id']}"],
            }
            if key == "admins":
                payload["members@odata.bind"] = [
                    f"https://graph.microsoft.com/v1.0/users/{me['id']}"
                ]
            group = api.request("POST", "/v1.0/groups", payload, dry_run=args.dry_run)
        if group is not None and not args.dry_run:
            group_config["id"] = group["id"]
            save_config(config)
            record(f"Verified security group `{group_config['name']}`: `{group['id']}`.")

    application = config["entra"]["application"]
    app = unique(objects("applications", "displayName", application["name"],
                         "id,appId,displayName,description,signInAudience"),
                 "displayName", application["name"])
    if app:
        if app["description"] != description or app["signInAudience"] != "AzureADMyOrg":
            raise ContextError("STOP: existing CI/CD application is not owned/single-tenant.")
        if application["object_id"] and application["object_id"] != app["id"]:
            raise ContextError("Configured application object ID differs.")
    else:
        # https://learn.microsoft.com/graph/api/application-post-applications
        app = api.request("POST", "/v1.0/applications", {
            "displayName": application["name"], "description": description,
            "signInAudience": "AzureADMyOrg",
        }, dry_run=args.dry_run)
    if app is not None:
        if not args.dry_run:
            application["object_id"], application["client_id"] = app["id"], app["appId"]
            save_config(config)
        principals = objects("servicePrincipals", "appId", app["appId"], "id,appId,displayName")
        principal = unique(principals, "appId", app["appId"])
        if principal is None:
            # https://learn.microsoft.com/graph/api/serviceprincipal-post-serviceprincipals
            principal = api.request("POST", "/v1.0/servicePrincipals",
                                    {"appId": app["appId"]}, dry_run=args.dry_run)
        if principal is not None and not args.dry_run:
            application["service_principal_id"] = principal["id"]
            save_config(config)
            record(f"Verified CI/CD application `{application['name']}` and SP `{principal['id']}`.")
        existing = api.list(f"/v1.0/applications/{app['id']}/federatedIdentityCredentials")
        repository_name = f"{config['github']['owner']}/{config['github']['repository']}"
        repository = json.loads(run([cli("gh"), "api", f"repos/{repository_name}"]))
        if repository["full_name"].casefold() != repository_name.casefold():
            raise ContextError("GitHub repository differs from the approved repository.")
        oidc = json.loads(run([cli("gh"), "api", f"repos/{repository_name}/actions/oidc/customization/sub"]))
        # https://learn.microsoft.com/entra/workload-id/workload-identities-github-immutable-subjects
        subjects = federation_subjects(repository, oidc)
        if not args.dry_run:
            config["github"]["owner_id"] = repository["owner"]["id"]
            config["github"]["repository_id"] = repository["id"]
            config["github"]["oidc_subject_prefix"] = oidc.get("sub_claim_prefix")
            save_config(config)
        # https://learn.microsoft.com/graph/api/federatedidentitycredential-post
        for name, subject in subjects.items():
            payload = {"name": name, "issuer": "https://token.actions.githubusercontent.com",
                       "subject": subject, "audiences": ["api://AzureADTokenExchange"]}
            credential = unique(existing, "name", name)
            if credential:
                if any(credential[key] != payload[key] for key in ("name", "issuer", "audiences")):
                    raise ContextError(f"STOP: existing federated credential {name} differs.")
                if credential["subject"] != subject:
                    recorded = application.get("federated_credential_ids", {}).get(name)
                    if credential["id"] != recorded:
                        raise ContextError("STOP: cannot update an unowned federated credential.")
                    suffix = {"github-test": "environment:test", "github-prod": "environment:prod",
                              "github-main": "ref:refs/heads/main"}[name]
                    if credential["subject"] != f"repo:{repository_name}:{suffix}":
                        raise ContextError("STOP: existing federated trust is not the expected legacy subject.")
                    # Only migrate our newly created trust to this repo's actual immutable claim.
                    # https://learn.microsoft.com/graph/api/federatedidentitycredential-update
                    api.request(
                        "PATCH", f"/v1.0/applications/{app['id']}/federatedIdentityCredentials/{credential['id']}",
                        {"subject": subject}, dry_run=args.dry_run
                    )
                    if not args.dry_run:
                        credential = api.request(
                            "GET", f"/v1.0/applications/{app['id']}/federatedIdentityCredentials/{credential['id']}"
                        )
                        if credential is None or credential["subject"] != subject:
                            raise ApiError("Immutable OIDC subject read-back failed.")
            else:
                credential = api.request(
                    "POST", f"/v1.0/applications/{app['id']}/federatedIdentityCredentials",
                    payload, dry_run=args.dry_run
                )
            if credential is not None and not args.dry_run:
                application.setdefault("federated_credential_ids", {})[name] = credential["id"]
                save_config(config)
                record(f"Verified OIDC credential `{name}`: `{credential['id']}`; subject `{subject}`.")
    else:
        print("DRY-RUN: create the app's SP and three GitHub OIDC credentials after resolving its new ID.")

    def membership(group_id: str, member_id: str) -> None:
        if not has_membership(api, group_id, member_id):
            # https://learn.microsoft.com/graph/api/group-post-members
            api.request("POST", f"/v1.0/groups/{group_id}/members/$ref",
                        {"@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{member_id}"},
                        dry_run=args.dry_run)
        if not args.dry_run:
            for attempt in range(3):
                if has_membership(api, group_id, member_id):
                    break
                time.sleep(5 * (attempt + 1))
            else:
                raise ApiError(f"Group membership read-back failed: {group_id}, member {member_id}.")

    if not args.dry_run:
        membership(config["entra"]["groups"]["admins"]["id"], me["id"])
        membership(config["entra"]["groups"]["api"]["id"], application["service_principal_id"])
    for region, user_config in config["entra"]["users"].items():
        users = objects("users", "userPrincipalName", user_config["upn"],
                        "id,userPrincipalName,accountEnabled")
        user = unique(users, "userPrincipalName", user_config["upn"])
        if user is None and user_config.get("reuse_existing") is True:
            raise ContextError("Explicitly reused account is missing; it will not be recreated.")
        if user:
            if user_config["id"] != user["id"] or user["accountEnabled"] is not True:
                raise ContextError(f"STOP: existing user {user_config['upn']} is unowned or disabled.")
        elif args.dry_run:
            print(f"DRY-RUN: create {user_config['upn']} with a generated, unlogged password.")
        else:
            # https://learn.microsoft.com/graph/api/user-post-users
            user = api.request("POST", "/v1.0/users", {
                "accountEnabled": True, "displayName": f"Demo {region.title()}",
                "mailNickname": f"demo.{region}", "userPrincipalName": user_config["upn"],
                "passwordProfile": {"forceChangePasswordNextSignIn": True,
                                    "password": initial_password()},
            })
        if user is not None and not args.dry_run:
            user_config["id"] = user["id"]
            save_config(config)
            membership(config["entra"]["groups"][f"sales_{region}"]["id"], user["id"])
            record(f"Verified test user `{user_config['upn']}`: `{user['id']}`; password not stored; licences pending.")
    if args.dry_run:
        print("DRY-RUN: Entra plan complete; no identities, memberships or configuration changed.")
    else:
        print("Entra bootstrap: PASS. Assign licences/reset initial passwords at the human checkpoint.")


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ApiError) as error:
        record(f"Entra bootstrap blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
