"""Fail-closed context checks shared by demo automation."""

import json
import os
from base64 import urlsafe_b64decode
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import unquote, urlparse

import yaml


ROOT = Path(__file__).resolve().parents[1]


class ContextError(RuntimeError):
    pass


def load_config() -> dict:
    with (ROOT / "config" / "environments.yml").open(encoding="utf-8") as source:
        config = yaml.safe_load(source)
    if not isinstance(config, dict):
        raise ValueError("config/environments.yml must contain a mapping.")
    return config


def write_snapshot(path: Path, payload: dict, *, dry_run: bool = False) -> None:
    target = (ROOT / path).resolve()
    if not target.is_relative_to(ROOT) or target == ROOT:
        raise ContextError("Baseline snapshots must remain inside the repository.")
    content = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if target.exists() and target.read_text(encoding="utf-8") != content:
        raise ContextError(f"Existing baseline differs: {path}; review before overwriting.")
    if not dry_run and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    print(f"{'DRY-RUN: ' if dry_run else ''}Verified snapshot: {path}")


def cli(name: str) -> str:
    candidates = [ROOT / ".venv" / "Scripts" / f"{name}.exe"]
    if name == "gh":
        candidates.append(Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
                          / "GitHub CLI" / "gh.exe")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    installed = shutil.which(name)
    if installed:
        return installed
    raise ContextError(f"Required CLI not found: {name}. Run infra/prepare_workstation.py.")


def run(
    command: list[str], *, include_stderr: bool = False,
    env: dict[str, str] | None = None, cwd: Path = ROOT
) -> str:
    execution = command
    if os.name == "nt" and Path(command[0]).name.casefold() == "az.cmd":
        python = Path(command[0]).parent.parent / "python.exe"
        if not python.is_file():
            raise ContextError("Azure CLI's bundled Python executable is missing.")
        # Avoid cmd.exe interpreting '&' or '%' in API query strings.
        execution = [str(python), "-IBm", "azure.cli", *command[1:]]
        env = dict(os.environ if env is None else env)
        env["AZ_INSTALLER"] = "MSI"
    result = subprocess.run(
        execution, cwd=cwd, check=False, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180, env=env
    )
    if result.returncode != 0:
        raise ContextError(
            f"{Path(command[0]).name} {' '.join(command[1:])} failed "
            f"(exit {result.returncode}): {result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout + result.stderr if include_stderr else result.stdout


def is_metadata_ci() -> bool:
    return os.environ.get("FABRIC_METADATA_CI") == "true"


def verify_metadata_context(config: dict) -> None:
    github = config["github"]
    stage = os.environ.get("FABRIC_DEPLOY_STAGE")
    required = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": f"{github['owner']}/{github['repository']}",
        "GITHUB_ACTOR": github["owner"],
        "GITHUB_ACTOR_ID": str(github["owner_id"]),
        "GITHUB_REF": f"refs/heads/{github['branch']}",
        "AZURE_CLIENT_ID": config["entra"]["application"]["client_id"],
        "AZURE_TENANT_ID": config["tenant"]["id"],
        "FABRIC_CAPACITY_ID": config["fabric"]["capacity_id"],
    }
    if stage not in ("test", "prod") or any(os.environ.get(key) != value
                                           for key, value in required.items()):
        raise ContextError("Metadata CI requires the approved owner/main workflow, stage and OIDC variables.")
    account = json.loads(run([cli("az"), "account", "show", "--output", "json"]))
    application = config["entra"]["application"]
    if account.get("tenantId") != config["tenant"]["id"] or \
            account.get("user", {}).get("type") != "servicePrincipal" or \
            account.get("user", {}).get("name", "").casefold() != application["client_id"].casefold():
        raise ContextError("CI Azure identity differs from the approved DEMO service principal.")
    print("Azure OIDC context: PASS")
    from azure.identity import AzureCliCredential
    token = AzureCliCredential(process_timeout=30).get_token("https://api.fabric.microsoft.com/.default")
    try:
        encoded = token.token.split(".")[1]
        claims = json.loads(urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    except (IndexError, ValueError) as error:
        raise ContextError("Azure CLI returned an unreadable Fabric identity token.") from error
    # Cross-check the CLI-acquired identity; Fabric validates the token signature.
    if claims.get("tid") != config["tenant"]["id"] or \
            (claims.get("appid") or claims.get("azp")) != application["client_id"] or \
            claims.get("oid") != application["service_principal_id"]:
        raise ContextError("Fabric token does not identify the approved DEMO CI application.")
    print("Fabric service-principal context: PASS")
    repository = json.loads(run([cli("gh"), "api",
                                 f"repos/{github['owner']}/{github['repository']}"]))
    if repository.get("id") != github["repository_id"] or \
            repository.get("owner", {}).get("id") != github["owner_id"]:
        raise ContextError("CI GitHub token resolved a different repository or owner.")
    print("GitHub owner/repository workflow context: PASS")


def verify_metadata_request(method: str, url: str, payload: dict | bytes | None) -> None:
    if not is_metadata_ci():
        return
    config = load_config()
    stage_name = os.environ.get("FABRIC_DEPLOY_STAGE")
    if stage_name not in ("test", "prod"):
        raise ContextError("Metadata CI has no approved target stage.")
    workspace = config["environments"][stage_name]["workspace_id"].casefold()
    parsed = urlparse(url)
    path = unquote(parsed.path).casefold()
    method = method.upper()
    if parsed.netloc not in ("api.fabric.microsoft.com", "api.powerbi.com"):
        raise ContextError("Metadata CI cannot access Graph or Azure resource APIs.")
    if "/workspaces/" in path and not path.startswith(f"/v1/workspaces/{workspace}/") and \
            path != f"/v1/workspaces/{workspace}":
        raise ContextError("Metadata CI cannot access another workspace.")
    if "/groups/" in path and not path.startswith(f"/v1.0/myorg/groups/{workspace}/"):
        raise ContextError("Metadata CI cannot access another Power BI group.")
    forbidden = ("jobs", "schedules", "shortcuts", "roleassignments", "refreshes", "connections", "staging")
    if any(part in forbidden for part in path.strip("/").split("/")):
        if method != "GET":
            raise ContextError("Metadata CI cannot refresh data, alter shortcuts or grant permissions.")
    if method == "GET":
        return
    if method == "DELETE" or parsed.netloc != "api.fabric.microsoft.com":
        raise ContextError("Metadata CI cannot delete items or mutate Power BI runtime data.")
    if os.environ.get("FABRIC_METADATA_READ_ONLY") == "true" and not path.endswith("/getdefinition"):
        raise ContextError("OIDC validation is read-only.")
    prefix = f"/v1/workspaces/{workspace}/"
    collections = ("items", "notebooks", "semanticmodels", "reports", "ontologies",
                   "dataagents", "variablelibraries", "datapipelines", "folders")
    if not path.startswith(prefix) or path[len(prefix):].split("/")[0] not in collections:
        raise ContextError("CI writes are limited to stage-local Fabric item metadata.")
    if path == prefix + "items" and method == "POST":
        allowed = {"Notebook", "SemanticModel", "Report", "Ontology", "DataAgent",
                   "VariableLibrary", "DataPipeline"}
        if not isinstance(payload, dict) or payload.get("type") not in allowed:
            raise ContextError("CI cannot create lakehouses, mirrors or other infrastructure.")
    if path.endswith("/bindconnection") and (not isinstance(payload, dict) or
            payload.get("connectionBinding", {}).get("connectivityType") != "Automatic" or
            "id" in payload.get("connectionBinding", {})):
        raise ContextError("CI connection binding is limited to automatic end-user SSO.")


def verify_context() -> None:
    config = load_config()
    if is_metadata_ci():
        verify_metadata_context(config)
        return
    tenant = config["tenant"]
    account = json.loads(run([cli("az"), "account", "show", "--output", "json"]))
    if (
        account.get("tenantId") != tenant["id"]
        or account.get("id") != config["azure"]["subscription_id"]
        or account.get("user", {}).get("name", "").casefold()
        != tenant["admin_upn"].casefold()
        or account.get("user", {}).get("type") != "user"
    ):
        raise ContextError("Azure context differs from the required demo tenant/admin/subscription.")
    print("Azure context: PASS")

    # Skill reference: fabric-skills/common/COMMON-CLI.md, Authentication Recipes.
    # Official CLI reference: https://microsoft.github.io/fabric-cli/examples/auth_examples/
    status = run([cli("fab"), "auth", "status"])
    required = {
        "Logged In": "True",
        "Account": tenant["admin_upn"],
        "Tenant ID": tenant["id"],
    }
    for label, expected in required.items():
        matches = re.findall(rf"^{re.escape(label)}:\s*(.+?)\s*$", status, re.MULTILINE)
        if len(matches) != 1 or matches[0].casefold() != expected.casefold():
            raise ContextError(f"Fabric context missing or mismatched: {label}. STOP.")
    print("Fabric context: PASS")

    status = run(
        [cli("gh"), "auth", "status", "--active", "--hostname", "github.com"],
        include_stderr=True
    )
    expected = re.escape(config["github"]["owner"])
    if (
        not re.search(rf"Logged in to github\.com account {expected}(?:\s|$)", status)
        or not re.search(r"Active account:\s*true\b", status)
    ):
        raise ContextError("GitHub active account differs from the required demo owner. STOP.")
    print("GitHub context: PASS")


def mutate(
    command: list[str], dry_run: bool = False, *, env: dict[str, str] | None = None,
    cwd: Path = ROOT
) -> str:
    if is_metadata_ci():
        raise ContextError("CLI mutations are disabled in metadata CI; use the guarded Fabric metadata API.")
    verify_context()
    print(("DRY-RUN: " if dry_run else "RUN: ") + subprocess.list2cmdline(command))
    if dry_run:
        return ""
    return run(command, env=env, cwd=cwd)
