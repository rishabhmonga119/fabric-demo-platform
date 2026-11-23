"""Aggregate live, non-deploying baseline checks and optional final Git sealing."""

import asyncio
from base64 import b64decode
from decimal import Decimal
import json
import math
import re

from bootstrap_fabric_items import post_and_wait
from bootstrap_mirror import mirror_definition
from bootstrap_sales_model import query_and_check
from build_expected_counts import verify_gold
from build_manifest import capture_manifest, manifest_file_sets
from capacity_guard import verify_stage_capacity
from common import ContextError, ROOT, cli, is_metadata_ci, load_config, mutate, run, verify_context
from export_roles import capture_roles
from fabric_sql import sql_reader
from http_api import Api
from manage_partner_share import inventory
from partner_logic import PARTNER_COLUMNS
from prepare_fallback import feature_sources

MEASURES = {"Actual hl", "Forecast hl", "Deviation hl", "Deviation %",
            "Revenue EUR", "Margin EUR", "Margin %"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContextError(message)


def definition(api: Api, workspace: str, item: dict, kind: str = "items") -> dict:
    return post_and_wait(api, f"/v1/workspaces/{workspace}/{kind}/{item['id']}/getDefinition",
                          {}, False, item["type"] + " baseline readback")["definition"]


def assert_baseline_measures(parts: list[dict]) -> None:
    names = set()
    for part in parts:
        if part["path"].endswith(".tmdl"):
            names.update(re.findall(r"(?m)^\s*measure\s+'([^']+)'\s*=",
                                     b64decode(part["payload"]).decode("utf-8")))
    require(names == MEASURES, "Live model measures differ from the seven-measure baseline.")


def git_ready(config: dict) -> tuple[str, dict[str, str]]:
    git, github = cli("git"), config["github"]
    require(run([git, "branch", "--show-current"]).strip() == github["branch"],
            "Baseline verification requires the configured main branch.")
    require(not run([git, "status", "--porcelain"]).strip(), "Baseline worktree is not clean.")
    require(run([git, "remote", "get-url", "--push", "origin"]).strip() ==
            f"https://github.com/{github['owner']}/{github['repository']}.git", "Unexpected push remote.")
    baseline = config["baseline"]
    refs = dict(line.split()[::-1] for line in run([
        git, "ls-remote", "origin", f"refs/heads/{github['branch']}",
        f"refs/heads/{baseline['prepared_branch']}", f"refs/tags/{baseline['prepared_tag']}",
        f"refs/tags/{baseline['tag']}"]).splitlines())
    head = run([git, "rev-parse", "HEAD"]).strip()
    require(refs.get(f"refs/heads/{github['branch']}") == head, "Remote main differs from local HEAD.")
    prepared = refs.get(f"refs/heads/{baseline['prepared_branch']}")
    require(bool(prepared) and refs.get(f"refs/tags/{baseline['prepared_tag']}") == prepared,
            "The prepared fallback branch/tag are missing or disagree.")
    for path, content in feature_sources().items():
        require(run([git, "show", f"{baseline['prepared_branch']}:{path.as_posix()}"]) == content,
                "Prepared fallback model/instructions differ from the current baseline plus feature.")
    changed = set(run([git, "diff", "--name-only",
                       f"HEAD...{baseline['prepared_branch']}"]).splitlines())
    require(changed == {path.as_posix() for path in feature_sources()},
            "Prepared fallback has unrelated changes.")
    prs = json.loads(run([cli("gh"), "pr", "list", "--repo",
                         f"{github['owner']}/{github['repository']}",
                         "--state", "open", "--limit", "1", "--json", "number"]))
    require(not prs, "Open pull requests remain; no automatic PR closure.")
    return head, refs


def check_stage(config: dict, name: str, api: Api, pbi: Api) -> None:
    stage = config["environments"][name]
    workspace = stage["workspace_id"]
    root = f"/v1/workspaces/{workspace}"
    verify_stage_capacity(api, config, api.request("GET", root), stage)
    items = api.list(root + "/items")
    require(len(stage["items"]) == 11, f"{name}: configuration is not the 11-item baseline.")
    for display_name, item in stage["items"].items():
        matches = [actual for actual in items if actual["displayName"] == display_name and
                   actual["type"] == item["type"] and actual["id"] == item["id"]]
        require(len(matches) == 1, f"{name}/{display_name}: missing or mismatched item identity.")
    mirror = definition(api, workspace, stage["items"]["MIR_UC_Gold"])
    encoded = [part for part in mirror["parts"] if part["path"] == "definition.json"]
    require(len(encoded) == 1, f"{name}: missing mirror definition.")
    actual = json.loads(b64decode(encoded[0]["payload"]))
    expected = mirror_definition(stage["databricks_catalog"], config["fabric"]["connections"]["databricks"]["id"])
    require(all(actual.get(key) == value for key, value in expected.items() if key != "$schema"),
            f"{name}: mirror is not bound to the stage's Gold catalog.")
    landing = stage["items"]["LH_Landing"]["id"]
    shortcuts = api.list(root + f"/items/{landing}/shortcuts")
    from urllib.parse import unquote
    sources = [entry["target"]["oneDriveSharePoint"] for entry in shortcuts
               if "oneDriveSharePoint" in entry["target"]]
    require(bool(sources) and all(stage["sharepoint_folder"].casefold() in
            unquote(source.get("location", "") + "/" + source.get("subpath", "")).casefold()
            for source in sources), f"{name}: forecast shortcuts are missing or cross-stage.")
    model = stage["items"]["SM_Sales"]
    connections = api.list(root + f"/items/{model['id']}/connections")
    require(len(connections) == 1 and connections[0]["connectivityType"] == "Automatic" and
            stage["items"]["LH_Curated"]["id"] in connections[0]["connectionDetails"]["path"],
            f"{name}: Direct Lake Automatic SSO source is not stage local.")
    model_api = Api("https://api.fabric.microsoft.com", config["tenant"]["id"],
                    skill="semantic-model-authoring")
    assert_baseline_measures(definition(model_api, workspace, model, "semanticModels")["parts"])
    model_root = f"/v1.0/myorg/groups/{workspace}/datasets/{model['id']}"
    row = query_and_check(pbi, model_root, name)
    for measure in MEASURES:
        key = f"[{measure}]"
        require(math.isclose(float(row[key]), float(model["baseline_query"][key]),
                             rel_tol=1e-12, abs_tol=1e-10),
                f"{name}: {measure} differs from its verified baseline.")
    report_root = f"/v1.0/myorg/groups/{workspace}/reports/{stage['items']['RPT_Sales']['id']}"
    require(pbi.request("GET", report_root)["datasetId"] == model["id"],
            f"{name}: report points at another model.")
    pages = pbi.list(report_root + "/pages")
    require([page["displayName"] for page in sorted(pages, key=lambda value: int(value["order"]))] ==
            ["Actual vs Forecast", "Margin"], f"{name}: report baseline pages differ.")
    jobs = api.list(root + f"/items/{stage['items']['PL_Refresh']['id']}/jobs/instances")
    require(bool(jobs) and max(jobs, key=lambda job: job["startTimeUtc"])["status"] == "Completed",
            f"{name}: latest pipeline run is not Completed.")
    agent = definition(api, workspace, stage["items"]["DA_Sales"], "dataAgents")
    ontologies = []
    for part in agent["parts"]:
        if part["path"].startswith("Files/Config/draft/") and part["path"].endswith("ontology.json"):
            ontologies.append(json.loads(b64decode(part["payload"])))
        elif part["path"].startswith("Files/Config/draft/") and part["path"].endswith("datasource.json"):
            require(json.loads(b64decode(part["payload"])).get("type") != "semantic_model",
                    f"{name}: agent has an independent semantic-model source.")
    require(len(ontologies) == 1 and ontologies[0]["workspaceId"] == workspace and
            ontologies[0]["artifactId"] == stage["items"]["ONT_Business"]["id"],
            f"{name}: agent ontology is not stage local.")
    if name == "prod":
        published = api.request("GET", root + f"/dataAgents/{stage['items']['DA_Sales']['id']}")
        require(bool(published.get("properties", {}).get("publishedDescription")),
                "Prod agent is not published to its Fabric runtime.")
        users = pbi.list(model_root + "/users")
        for key in ("sales_north", "sales_south"):
            group = config["entra"]["groups"][key]["id"]
            require(any(user["identifier"] == group and user["principalType"] == "Group" and
                        user["datasetUserAccessRight"] == "ReadExplore" for user in users),
                    "Prod ontology readers no longer have exactly the approved Read+Build grant.")
    print(f"PASS {name}: 11 items, mirror/shortcuts/SSO, seven live measures, report, pipeline, ontology.")


async def check_sql(config: dict, api: Api) -> None:
    async with sql_reader(config) as query:
        for name, stage in config["environments"].items():
            endpoints = {}
            for lakehouse in ("LH_Landing", "LH_Curated"):
                item = stage["items"][lakehouse]
                detail = api.request("GET", f"/v1/workspaces/{stage['workspace_id']}/lakehouses/{item['id']}")
                endpoints[lakehouse] = detail["properties"]["sqlEndpointProperties"]["id"]
                require(endpoints[lakehouse] == item["sql_endpoint_id"], "SQL endpoint identity changed.")
            rows = await query(stage["workspace_id"], endpoints["LH_Landing"],
                "SELECT 'forecast_standard' AS table_name, COUNT(*) AS row_count FROM forecast.forecast_standard "
                "UNION ALL SELECT 'forecast_clean', COUNT(*) FROM forecast.forecast_clean "
                "UNION ALL SELECT 'forecast_rejects', COUNT(*) FROM forecast.forecast_rejects ORDER BY table_name")
            require({row["table_name"]: int(row["row_count"]) for row in rows} ==
                    {"forecast_standard": 3696, "forecast_clean": 4928, "forecast_rejects": 1},
                    f"{name}: actual landing row counts differ.")
            rows = await query(stage["workspace_id"], endpoints["LH_Curated"],
                "SELECT COUNT(*) AS row_count, COUNT(DISTINCT env_marker) AS marker_count, "
                "MIN(env_marker) AS marker, SUM(actual_hl) AS actual_hl "
                "FROM dbo.sales_vs_forecast")
            require(len(rows) == 1 and int(rows[0]["row_count"]) == 10304 and
                    int(rows[0]["marker_count"]) == 1 and rows[0]["marker"] == name and
                    Decimal(rows[0]["actual_hl"]) == Decimal("4488091.02"),
                    f"{name}: actual curated count/stage/checksum differs.")
            print(f"PASS {name}: actual SQL landing/curated baseline data.")
        partner = config["partner"]
        item = partner["items"]["LH_PartnerA"]
        detail = api.request("GET", f"/v1/workspaces/{partner['workspace_id']}/lakehouses/{item['id']}")
        endpoint = detail["properties"]["sqlEndpointProperties"]["id"]
        require(endpoint == item["sql_endpoint_id"], "Partner SQL endpoint identity changed.")
        rows = await query(partner["workspace_id"], endpoint,
            "SELECT COUNT(*) AS row_count, SUM(delivered_hl) AS delivered_hl FROM dbo.partner_a_deliveries")
        require(len(rows) == 1 and int(rows[0]["row_count"]) == 1232 and
                Decimal(rows[0]["delivered_hl"]) == Decimal("1121803.72"),
                "Current partner output differs from the baseline.")
        columns = await query(partner["workspace_id"], endpoint,
            "SELECT TOP (20) COLUMN_NAME AS column_name FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'partner_a_deliveries' ORDER BY ORDINAL_POSITION")
        require([column["column_name"] for column in columns] == list(PARTNER_COLUMNS),
                "Actual partner output has unexpected/missing columns.")
        print("PASS partner: current SQL row count, exact volume and seven columns.")


def verify_all(*, dry_run: bool = False, seal: bool = False) -> None:
    if is_metadata_ci():
        raise ContextError("Full baseline verification requires the DEMO user, not metadata CI.")
    verify_context()
    config = load_config()
    require(config.get("baseline", {}).get("recordings_verification") ==
            "skipped-by-explicit-user-request", "Recordings readiness requires explicit human confirmation.")
    paths = [ROOT / "config" / "onelake_roles.baseline.json", ROOT / "seed" / "manifest.json",
             ROOT / "seed" / "expected_counts.json"]
    require(all(path.is_file() for path in paths), "Required baseline snapshots are missing.")
    if dry_run:
        print("DRY-RUN: verify Git/fallback, actual Gold fingerprints/policies, SharePoint manifest, "
              "OneLake roles, all stage bindings/model measures/SQL data, Prod publication/viewer checks "
              f"and partner cleanup. seal={seal}. No queries, refreshes, deployments or tags.")
        return
    head, refs = git_ready(config)
    tag = config["baseline"]["tag"]
    existing_tag = refs.get(f"refs/tags/{tag}")
    require(existing_tag in (None, head) if seal else existing_tag == head,
            "demo-baseline is missing or points elsewhere; never overwrite an existing baseline tag.")
    print("PASS Git readiness: clean pushed main, no open PRs, exact prepared branch/tag.")
    require(manifest_file_sets(capture_manifest(config)) ==
            manifest_file_sets(json.loads(paths[1].read_text(encoding="utf-8"))),
            "Actual SharePoint file set differs from its manifest.")
    require(capture_roles(config) == json.loads(paths[0].read_text(encoding="utf-8")),
            "Actual OneLake policies/members differ from the baseline.")
    api = Api("https://api.fabric.microsoft.com", config["tenant"]["id"],
              skill="e2e-medallion-architecture")
    pbi = Api("https://api.powerbi.com", config["tenant"]["id"], skill="semantic-model-authoring")
    for stage in config["environments"]:
        check_stage(config, stage, api, pbi)
    asyncio.run(check_sql(config, api))
    partner = config["partner"]
    workspace = api.request("GET", f"/v1/workspaces/{partner['workspace_id']}")
    verify_stage_capacity(api, config, workspace, partner)
    inventory(api, config, workspace)
    require(not api.list(f"/v1/workspaces/{partner['workspace_id']}/items?type=Share"),
            "Partner Share items remain; no automatic deletion during verification.")
    require(partner["sharing_verification"] == "user-confirmed-inbound-read-revocation-and-cleanup" and
            partner["rehearsal_share"]["state"] == "Deleted",
            "Actual rehearsal acceptance/read/revocation/cleanup checkpoints are incomplete.")
    checkpoint = config["copilot"]["step7"]
    require(checkpoint["north_viewer_data_agent_verification"] == "user-confirmed-copilot-answer" and
            checkpoint["north_viewer_ontology_instances_verification"] == "user-confirmed",
            "Real viewer ontology/Data Agent acceptance is not confirmed.")
    print("PASS human evidence: viewer agent/instances and cross-tenant read/revocation/cleanup.")
    actual_gold = verify_gold(config, list(config["environments"]), log=print)
    require(json.loads(json.dumps(actual_gold)) == json.loads(paths[2].read_text(encoding="utf-8")),
            "Actual Gold data differs from the captured expected-count baseline.")
    print("PASS Databricks: all Gold rows/grains/fingerprints/comments, no UC filters/masks; warehouse stopped.")
    require(not run([cli("git"), "status", "--porcelain"]).strip(),
            "Verification unexpectedly changed repository files; no baseline sealing.")
    if seal and not existing_tag:
        local = run([cli("git"), "for-each-ref", "--format=%(objectname)", f"refs/tags/{tag}"]).strip()
        require(local in ("", head), "A different local baseline tag exists; no overwrite.")
        if not local:
            mutate([cli("git"), "tag", tag, head])
        mutate([cli("git"), "push", "origin", f"refs/tags/{tag}"])
    final = dict(line.split()[::-1] for line in run([
        cli("git"), "ls-remote", "origin", f"refs/heads/{config['github']['branch']}",
        f"refs/tags/{tag}"]).splitlines())
    require(final.get(f"refs/tags/{tag}") == head ==
            final.get(f"refs/heads/{config['github']['branch']}"),
            "Final remote main/demo-baseline verification failed.")
    print(f"PASS remote main == {tag} == {head}")
    print("ALL TECHNICAL BASELINE CHECKS PASS. Recordings explicitly skipped by the user.")
