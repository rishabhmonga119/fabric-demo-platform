"""Prepare the local-only Forecast Accuracy fallback branch/tag without changing Fabric."""

import argparse
from decimal import Decimal
import json
import math
from pathlib import Path
import re
import sys
import tempfile

from capacity_guard import verify_stage_capacity
from common import ContextError, ROOT, cli, is_metadata_ci, load_config, mutate, run, verify_context
from http_api import Api, ApiError

EXPRESSION = (
    "VAR _Actual = [Actual hl] VAR _Forecast = [Forecast hl] "
    "RETURN IF(ISBLANK(_Actual) || ISBLANK(_Forecast), BLANK(), "
    "IF(_Actual = 0, 0, DIVIDE(_Actual - ABS(_Actual - _Forecast), _Actual)))"
)
MODEL = Path("fabric") / "SM_Sales.SemanticModel" / "definition" / "tables" / "Sales vs Forecast.tmdl"
AGENT = Path("fabric") / "DA_Sales.DataAgent" / "Files" / "Config" / "draft" / "stage_config.json"
GUIDANCE = (
    "\nForecast accuracy (also called accuracy) means [Forecast Accuracy %] when that measure "
    "exists: 1 - ABS([Actual hl] - [Forecast hl]) / [Actual hl]. Return 0 when actual is zero; "
    "leave the result unavailable if actual or forecast is missing. This is not [Deviation %]. "
    "Resolve and query this metric through ONT_Business; do not add a standalone semantic-model source.\n"
)


def feature_sources(root: Path = ROOT) -> dict[Path, str]:
    table = (root / MODEL).read_text(encoding="utf-8")
    if re.search(r"(?m)^\s*measure 'Forecast Accuracy %'\s*=", table):
        raise ContextError("Main already contains the demo measure; it is not the baseline.")
    first_column = re.search(r"(?m)^(?:\t///[^\n]*\n)*\tcolumn ", table)
    if first_column is None:
        raise ContextError("Cannot locate the existing table's first column safely.")
    measure = (
        "\t/// Forecast accuracy relative to actual volume: 1 minus absolute error / actual. "
        "Zero for zero actual; blank when actual or forecast is missing.\n"
        f"\tmeasure 'Forecast Accuracy %' = {EXPRESSION}\n"
        "\t\tformatString: 0.0%\n\t\tdisplayFolder: Forecast\n\n"
    )
    agent = json.loads((root / AGENT).read_text(encoding="utf-8"))
    if not isinstance(agent.get("aiInstructions"), str) or GUIDANCE in agent["aiInstructions"]:
        raise ContextError("The baseline agent instructions are missing or already contain the feature.")
    agent["aiInstructions"] += GUIDANCE
    position = first_column.start()
    return {MODEL: table[:position] + measure + table[position:],
            AGENT: json.dumps(agent, indent=2) + "\n"}


def validate_expression(config: dict) -> None:
    stage = config["environments"]["dev"]
    api = Api("https://api.fabric.microsoft.com", config["tenant"]["id"],
              skill="semantic-model-authoring")
    workspace = stage["workspace_id"]
    verify_stage_capacity(api, config, api.request("GET", f"/v1/workspaces/{workspace}"), stage)
    pbi = Api("https://api.powerbi.com", config["tenant"]["id"], skill="semantic-model-authoring")
    endpoint = f"/v1.0/myorg/groups/{workspace}/datasets/{stage['items']['SM_Sales']['id']}/executeQueries"
    for overrides, expected in (
        ("", "computed"),
        ("MEASURE 'Sales vs Forecast'[Actual hl] = 0\n"
         "MEASURE 'Sales vs Forecast'[Forecast hl] = 100\n", "zero"),
        ("MEASURE 'Sales vs Forecast'[Actual hl] = 100\n"
         "MEASURE 'Sales vs Forecast'[Forecast hl] = BLANK()\n", "blank"),
    ):
        query = ("DEFINE\n" + overrides +
                 f"MEASURE 'Sales vs Forecast'[Forecast Accuracy %] = {EXPRESSION}\n"
                 'EVALUATE ROW("Accuracy", [Forecast Accuracy %], "Actual", [Actual hl], '
                 '"Forecast", [Forecast hl])')
        result = pbi.request("POST", endpoint, {
            "queries": [{"query": query}], "serializerSettings": {"includeNulls": True}})
        if result.get("error") or len(result.get("results", [])) != 1:
            raise ApiError("Query-scoped Forecast Accuracy validation failed.")
        entry = result["results"][0]
        tables = entry.get("tables", [])
        if entry.get("error") or len(tables) != 1 or tables[0].get("error") or \
                len(tables[0].get("rows", [])) != 1:
            raise ApiError("Forecast Accuracy validation returned an incomplete result.")
        row = tables[0]["rows"][0]
        if "[Accuracy]" not in row:
            raise ApiError("Accuracy result is missing, not an explicit BLANK.")
        if expected == "blank":
            valid = row["[Accuracy]"] is None
        elif expected == "zero":
            valid = row["[Accuracy]"] == 0
        else:
            actual, forecast = Decimal(str(row["[Actual]"])), Decimal(str(row["[Forecast]"]))
            value = (actual - abs(actual - forecast)) / actual
            valid = isinstance(row["[Accuracy]"], (int, float)) and math.isclose(
                row["[Accuracy]"], float(value), rel_tol=1e-12, abs_tol=1e-12)
        if not valid:
            raise ApiError(f"Forecast Accuracy {expected} validation differs from the intended formula.")
        print(f"PASS query-scoped accuracy: {expected}; no persisted measure or refresh.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if is_metadata_ci():
        raise ContextError("Fallback preparation requires the DEMO administrator, not metadata CI.")
    verify_context()
    config = load_config()
    git = cli("git")
    github = config["github"]
    if run([git, "branch", "--show-current"]).strip() != github["branch"] or \
            run([git, "remote", "get-url", "--push", "origin"]).strip() != \
            f"https://github.com/{github['owner']}/{github['repository']}.git":
        raise ContextError("Fallback preparation requires the configured main branch and push remote.")
    sources = feature_sources()
    branch, tag = config["baseline"]["prepared_branch"], config["baseline"]["prepared_tag"]
    existing = run([git, "for-each-ref", "--format=%(objectname)", f"refs/heads/{branch}"]).strip()
    if args.dry_run:
        print(f"DRY-RUN: validate three query-scoped DAX cases, prepare only {MODEL} and {AGENT}, "
              f"commit/push {branch} and {tag}; do not deploy, refresh or edit opaque AI metadata.")
        return
    if run([git, "status", "--porcelain"]).strip():
        raise ContextError("Commit the baseline tooling/snapshots before preparing the fallback branch.")
    validate_expression(config)
    if not existing:
        remote = run([git, "ls-remote", "origin", f"refs/heads/{branch}", f"refs/tags/{tag}"]).strip()
        if remote:
            raise ContextError("A remote prepared ref already exists; no automatic overwrite.")
        with tempfile.TemporaryDirectory(prefix="fabric-demo-fallback-") as directory:
            target = Path(directory).resolve()
            mutate([git, "worktree", "add", "-b", branch, str(target), "HEAD"])
            try:
                for path, content in sources.items():
                    (target / path).write_text(content, encoding="utf-8")
                mutate([git, "-C", str(target), "add", "--", *map(str, sources)])
                message = ("step 9: prepare forecast accuracy fallback [skip ci]\n\n"
                           "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>")
                mutate([git, "-C", str(target), "commit", "-m", message])
            finally:
                mutate([git, "worktree", "remove", "--force", str(target)])
    for path, content in sources.items():
        if run([git, "show", f"{branch}:{path.as_posix()}"]) != content:
            raise ContextError("Existing prepared branch differs from the approved feature; no overwrite.")
    commit = run([git, "rev-parse", branch]).strip()
    tagged = run([git, "for-each-ref", "--format=%(objectname)", f"refs/tags/{tag}"]).strip()
    if tagged and tagged != commit:
        raise ContextError("Existing prepared tag differs; no retag or force-push.")
    if not tagged:
        mutate([git, "tag", tag, commit])
    mutate([git, "push", "origin", branch, f"refs/tags/{tag}"])
    refs = dict(line.split()[::-1] for line in run([
        git, "ls-remote", "origin", f"refs/heads/{branch}", f"refs/tags/{tag}"]).splitlines())
    if refs != {f"refs/heads/{branch}": commit, f"refs/tags/{tag}": commit}:
        raise ContextError("Prepared branch/tag remote verification failed.")
    print(f"PASS prepared fallback branch/tag: {commit}. Main and Fabric remain unchanged.")
    print("The optional Power BI AI-schema synonym 'accuracy' requires user UI configuration; "
          "the fallback adds an agent-language alias, not a fabricated model synonym.")


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ApiError, OSError, ValueError) as error:
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
