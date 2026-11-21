"""Validate/deploy/run stage-isolated DABs with compute and ownership checks."""

import argparse
import json
import sys
import time

from check_databricks import workspace_environment
from check_managed_storage import check_warehouse
from common import ContextError, ROOT, cli, load_config, mutate, run, verify_context
from databricks_sql import DatabricksSql

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stages", default="dev,test,prod")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    stages = args.stages.split(",")
    if len(stages) != len(set(stages)) or any(stage not in ("dev", "test", "prod") for stage in stages):
        parser.error("Use unique stages from dev,test,prod.")
    verify_context()
    config = load_config()
    environment = workspace_environment(config)
    executable = cli("databricks")
    warehouse_id = config["azure"]["databricks_sql_warehouse_id"]
    owner = f"{config['github']['owner']}/{config['github']['repository']}"
    bundle_root = ROOT / "databricks"
    sql_client = DatabricksSql(config, warehouse_id)

    def read(*arguments: str):
        return json.loads(run([executable, *arguments, "--output", "json"], env=environment))

    check_warehouse(read("warehouses", "get", warehouse_id), owner)
    variable = f"warehouse_id={warehouse_id}"
    for stage in stages:
        stage_config = config["environments"][stage]
        if stage_config["databricks_catalog"] != f"demo_{stage}":
            raise ContextError("Stage/catalog binding differs from the fixed bundle targets.")
        # https://learn.microsoft.com/azure/databricks/dev-tools/bundles/settings
        validate = [executable, "bundle", "validate", "-t", stage, "--var", variable, "--output", "json"]
        run(validate, env=environment, cwd=bundle_root)
        if not args.dry_run:
            record(f"DAB target `{stage}` validation: PASS.")
        for key in ("seed_data", "build_medallion", "reset"):
            name = f"demo_{stage}_{key}"
            matches = read("jobs", "list", "--name", name)
            if len(matches) > 1:
                raise ContextError(f"Multiple existing {name} jobs; no ambiguous deploy.")
            for match in matches:
                job = read("jobs", "get", str(match["job_id"]))
                tags = job["settings"].get("tags", {})
                if tags.get("demoOwner") != owner or tags.get("createdBy") != "copilot-demo-build":
                    raise ContextError(f"STOP: existing job {name} is unowned; no deploy overwrite.")
        remote_root = f"/Shared/fabric-demo-platform/{stage}"
        recorded_root = stage_config.get("databricks_bundle_root")
        if recorded_root is not None and recorded_root != remote_root:
            raise ContextError("Recorded bundle root differs from the fixed stage path.")
        if recorded_root is None:
            shared = read("workspace", "list", "/Shared")
            if any(item["path"] == "/Shared/fabric-demo-platform" for item in shared):
                children = read("workspace", "list", "/Shared/fabric-demo-platform")
                pending = [remote_root] if any(item["path"] == remote_root for item in children) else []
                while pending:
                    for item in read("workspace", "list", pending.pop()):
                        if item["object_type"] != "DIRECTORY":
                            raise ContextError(f"STOP: unrecorded existing bundle artifact {item['path']}; no overwrite.")
                        pending.append(item["path"])
        deploy = [executable, "bundle", "deploy", "-t", stage, "--var", variable]
        if args.dry_run:
            mutate(deploy, dry_run=True, env=environment, cwd=bundle_root)
            mutate([executable, "jobs", "run-now", "<deployed-reset-job-id>", "--no-wait", "--output", "json"],
                   dry_run=True, env=environment, cwd=bundle_root)
            continue
        if recorded_root is None:
            stage_config["databricks_bundle_root"] = remote_root
            save_config(config)
            record(f"Reserved verified-empty bundle path `{remote_root}` for owned stage deployment.")
        mutate(deploy, env=environment, cwd=bundle_root)
        job_ids = {}
        for key in ("seed_data", "build_medallion", "reset"):
            matches = read("jobs", "list", "--name", f"demo_{stage}_{key}")
            if len(matches) != 1:
                raise ContextError(f"Expected one deployed {key} job for {stage}.")
            job_id = matches[0]["job_id"]
            job = read("jobs", "get", str(job_id))["settings"]
            if job.get("job_clusters"):
                raise ContextError("Unexpected classic job-cluster definition; only serverless tasks expected.")
            for task in job["tasks"]:
                if any(task.get(field) for field in ("new_cluster", "existing_cluster_id", "job_cluster_key")):
                    raise ContextError("Unexpected cluster compute in the serverless bundle.")
                sql_warehouse = task.get("notebook_task", {}).get("warehouse_id")
                if sql_warehouse is not None and sql_warehouse != warehouse_id:
                    raise ContextError("SQL notebook points to an unapproved warehouse.")
            job_ids[key] = job_id
            record(f"DAB `{stage}` job `{key}` = `{job_id}`.")
        stage_config["databricks_job_ids"] = job_ids
        save_config(config)
        active = read("jobs", "list-runs", "--job-id", str(job_ids["reset"]), "--active-only")
        if len(active) > 1:
            raise ContextError("Multiple active reset runs; no duplicate submission.")
        if active:
            run_id = active[0]["run_id"]
            record(f"Waiting for existing active `{stage}` reset run `{run_id}`.")
        else:
            # bundle run --no-wait submits successfully but does not print a JSON run ID.
            # https://learn.microsoft.com/azure/databricks/dev-tools/cli/reference/jobs-commands
            submitted = json.loads(mutate(
                [executable, "jobs", "run-now", str(job_ids["reset"]), "--no-wait", "--output", "json"],
                env=environment, cwd=bundle_root
            ))
            run_id = submitted["run_id"]
            record(f"Started DAB `{stage}` reset run `{run_id}`.")
        stage_config["databricks_last_reset_run_id"] = run_id
        save_config(config)
        try:
            deadline = time.monotonic() + 3600
            while time.monotonic() < deadline:
                result = read("jobs", "get-run", str(run_id))
                state = result["state"]
                print(f"{stage} reset {run_id}: {state['life_cycle_state']}", flush=True)
                if state["life_cycle_state"] in ("TERMINATED", "SKIPPED", "INTERNAL_ERROR"):
                    if state.get("result_state") != "SUCCESS":
                        record(f"DAB `{stage}` reset FAILED: `{json.dumps(state)}`.")
                        raise RuntimeError(f"DAB run failed: {json.dumps(state)}")
                    stage_config["databricks_last_reset_state"] = "SUCCESS"
                    save_config(config)
                    record(f"DAB `{stage}` reset run `{run_id}`: SUCCESS.")
                    break
                time.sleep(15)
            else:
                raise TimeoutError("DAB reset did not finish within one hour.")
        finally:
            sql_client.stop()
            record(f"Owned SQL warehouse confirmed STOPPED after `{stage}`; auto-stop remains 15 minutes.")
    print("DRY-RUN: DAB plan complete; no deployment/runs." if args.dry_run
          else "DAB reset jobs: SUCCESS for all requested stages; verify gold data next.")


if __name__ == "__main__":
    try:
        main()
    except ContextError as error:
        record(f"DAB execution blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
