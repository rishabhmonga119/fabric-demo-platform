"""Dispatch and verify the read-only GitHub OIDC Fabric access workflow."""

import argparse
from datetime import datetime, timedelta, timezone
import json
import sys
import time

from common import ContextError, ROOT, cli, load_config, mutate, run, verify_context

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--metadata-validation", action="store_true",
                        help="Validate the metadata deployment workflow with no workspace writes.")
    parser.add_argument("--stage", choices=("test", "prod", "both"), default="prod")
    args = parser.parse_args()
    verify_context()
    config = load_config()
    gh = cli("gh")
    repository = f"{config['github']['owner']}/{config['github']['repository']}"
    workflow = "deploy.yml" if args.metadata_validation else "oidc-check.yml"
    command = [gh, "workflow", "run", workflow, "--repo", repository, "--ref", "main"]
    if args.metadata_validation:
        command += ["-f", f"stage={args.stage}", "-f", "validate_only=true"]
    if args.dry_run:
        mutate(command, dry_run=True)
        print("DRY-RUN: poll the matching workflow run; no dispatch performed.")
        return
    sha = run([cli("git"), "rev-parse", "HEAD"]).strip()
    started = datetime.now(timezone.utc) - timedelta(seconds=2)
    mutate(command)
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        runs = json.loads(run([
            gh, "run", "list", "--repo", repository, "--workflow", workflow,
            "--branch", "main", "--event", "workflow_dispatch", "--limit", "10",
            "--json", "databaseId,status,conclusion,url,headSha,createdAt"
        ]))
        matching = [
            item for item in runs
            if item["headSha"] == sha
            and datetime.fromisoformat(item["createdAt"].replace("Z", "+00:00")) >= started
        ]
        if len(matching) > 1:
            raise ContextError("Multiple matching OIDC checks were dispatched; do not guess a run.")
        if matching:
            item = matching[0]
            print(f"OIDC run {item['databaseId']}: {item['status']}", flush=True)
            if item["status"] == "completed":
                if item["conclusion"] != "success":
                    record(f"OIDC check FAILED: `{item['url']}`.")
                    raise ContextError(f"OIDC workflow failed: {item['url']}")
                state_key = "metadata_validation" if args.metadata_validation else "oidc_check"
                config["github"][state_key] = {
                    "run_id": item["databaseId"], "url": item["url"],
                    "commit": sha, "result": "success",
                }
                save_config(config)
                message = f"Step 6 metadata-only OIDC/SDK preflight for {args.stage} PASS; no workspace changes" \
                    if args.metadata_validation else "Step 2 Check: GitHub OIDC SP lists Test items PASS"
                record(f"{message}; `{item['url']}`.")
                print(f"OIDC access check: PASS ({item['url']})")
                return
        time.sleep(10)
    raise TimeoutError("OIDC workflow did not finish within 15 minutes.")


if __name__ == "__main__":
    try:
        main()
    except ContextError as error:
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
