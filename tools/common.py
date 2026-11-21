"""Fail-closed context checks shared by demo automation."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess

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


def verify_context() -> None:
    config = load_config()
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
    verify_context()
    print(("DRY-RUN: " if dry_run else "RUN: ") + subprocess.list2cmdline(command))
    if dry_run:
        return ""
    return run(command, env=env, cwd=cwd)
