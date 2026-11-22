"""Publish the approved Prod agent and verify answers through its real MCP endpoint."""

import argparse
import asyncio
from base64 import b64decode
from decimal import Decimal
from hashlib import sha256
import json
import re
import sys

from bootstrap_fabric_items import post_and_wait
from common import ContextError, ROOT, is_metadata_ci, load_config, verify_context
from http_api import Api, ApiError

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config

REFERENCES = (
    "fabric-skills/common/COMMON-CORE.md; "
    "https://learn.microsoft.com/rest/api/fabric/dataagent/items/publish-data-agent; "
    "https://learn.microsoft.com/fabric/data-science/fabric-data-agent-sdk"
)
QUESTIONS = [
    (
        "What are total actual sales volume in hl, total net revenue in EUR, and total "
        "contribution margin in EUR from January 2025 through October 2026 inclusive? "
        "Include all regions, channels, products and packages. Show exact decimal totals, "
        "not abbreviated millions, and state the period and units.",
        (Decimal("4488091.02"), Decimal("288517979.92"), Decimal("76975278.66")),
    ),
    (
        "What is the revenue-weighted contribution "
        "margin percentage across all regions, channels and packages for January 2025 "
        "through October 2026 inclusive? Calculate total margin divided by total revenue, "
        "not an average of percentages. Show the percentage to two decimal places.",
        (Decimal("26.68"),),
    ),
]


async def query_agent(url: str, headers: dict[str, str], question: str) -> str:
    import httpx2
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with httpx2.AsyncClient(headers=headers, timeout=300, follow_redirects=False) as client:
        async with streamable_http_client(url, http_client=client) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=300) as session:
                await session.initialize()
                result = await session.list_tools()
                if len(result.tools) != 1:
                    raise ApiError("The Data Agent MCP did not expose exactly its documented single tool.")
                tool = result.tools[0]
                properties = tool.input_schema.get("properties", {})
                required = tool.input_schema.get("required", [])
                candidates = [name for name, value in properties.items()
                              if value.get("type") == "string" and (not required or name in required)]
                if len(candidates) != 1:
                    raise ApiError("The discovered Data Agent question argument is ambiguous.")
                answer = await session.call_tool(tool.name, {candidates[0]: question})
                text = "\n".join(block.text for block in answer.content if block.type == "text")
                if answer.is_error or not text:
                    raise ApiError(f"Data Agent returned an error or no answer: {text}")
                return text


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("prod",), required=True)
    parser.add_argument("--approved-prod", action="store_true")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if is_metadata_ci():
        raise ContextError("Data Agent answer checks require the verified DEMO user, not metadata CI.")
    verify_context()
    if not args.approved_prod:
        raise ContextError("Production publication/answer checks require the approved initial rollout.")
    config = load_config()
    stage = config["environments"][args.stage]
    workspace = stage["workspace_id"]
    agent = stage["items"]["DA_Sales"]
    api = Api("https://api.fabric.microsoft.com", config["tenant"]["id"],
              skill="e2e-medallion-architecture")
    live = api.request("GET", f"/v1/workspaces/{workspace}")
    capacities = [item for item in api.list("/v1/capacities")
                  if item["id"] == config["fabric"]["capacity_id"]]
    if live["displayName"] != stage["workspace_name"] or \
            live["capacityId"] != config["fabric"]["capacity_id"] or len(capacities) != 1 or \
            capacities[0]["state"] != "Active" or capacities[0]["sku"] != config["cost_guardrails"]["fabric_sku"]:
        raise ContextError("Agent verification target differs from the approved existing Active F4.")
    matches = [item for item in api.list(f"/v1/workspaces/{workspace}/items?type=DataAgent")
               if item["displayName"] == "DA_Sales"]
    if len(matches) != 1 or matches[0]["id"] != agent["id"]:
        raise ContextError("The Prod Data Agent identity differs from the deployed item.")
    url = f"{api.base}/v1/mcp/workspaces/{workspace}/dataagents/{agent['id']}/agent"
    if args.dry_run:
        print(f"DRY-RUN: verify ontology-only context, optionally publish Prod staging, "
              f"then ask {len(QUESTIONS)} real questions at {url}; no writes or runtime calls.")
        return
    definition = post_and_wait(api, f"/v1/workspaces/{workspace}/dataAgents/{agent['id']}/getDefinition",
                               {}, False, "Prod agent source guard")
    draft = [part for part in definition["definition"]["parts"]
             if part["path"].startswith("Files/Config/draft/")]
    ontologies = []
    for part in draft:
        if part["path"].endswith("ontology.json"):
            ontologies.append(json.loads(b64decode(part["payload"])))
        elif part["path"].endswith("datasource.json") and \
                json.loads(b64decode(part["payload"])).get("type") == "semantic_model":
            raise ContextError("A standalone semantic-model source is not permitted for DA_Sales.")
    if len(ontologies) != 1 or ontologies[0]["artifactId"] != stage["items"]["ONT_Business"]["id"] or \
            ontologies[0]["workspaceId"] != workspace:
        raise ContextError("Prod agent is not grounded in the stage-local ontology.")
    digest = sha256(json.dumps(draft, sort_keys=True).encode()).hexdigest()
    if args.publish and agent.get("published_definition_sha256") != digest:
        description = "Prod sales analytics grounded in ONT_Business; synthetic demo data."
        result = api.request("POST", f"/v1/workspaces/{workspace}/dataAgents/{agent['id']}/staging/publish",
                             {"publishedDescription": description})
        if result.get("publishedDescription") != description:
            raise ApiError("The Data Agent publish response did not confirm the requested description.")
        agent["published_definition_sha256"] = digest
        agent["mcp_url"] = url
        save_config(config)
        record(f"Published Prod DA_Sales `{agent['id']}` for MCP querying, not Agent Store/M365. "
               f"Ontology-only draft preserved. References: {REFERENCES}.")
    if agent.get("published_definition_sha256") != digest:
        raise ContextError("Publish the current approved Prod staging before querying its MCP endpoint.")
    for question, expected in QUESTIONS:
        verify_context()
        token = api.credential.get_token("https://api.fabric.microsoft.com/.default")
        headers = {"Authorization": "Bearer " + token.token,
                   "x-ms-fabric-skill": "e2e-medallion-architecture"}
        answer = asyncio.run(query_agent(url, headers, question))
        print(answer, flush=True)
        numbers = {Decimal(value.replace(",", ""))
                   for value in re.findall(r"-?\d[\d,]*(?:\.\d+)?", answer)}
        if not all(value in numbers for value in expected):
            record(f"Prod Data Agent answer did not match the requested exact baseline. "
                   f"Question: {question} Answer: {answer}")
            raise ApiError("A real Data Agent answer omitted or differed from the verified baseline.")
        agent.setdefault("verified_answers", {})[question] = answer
        save_config(config)
        record(f"Prod Data Agent MCP answer PASS. Question: {question} Answer: {answer}")
    agent["runtime_verification_state"] = "passed"
    agent.pop("runtime_verification_reason", None)
    save_config(config)
    print("PASS: Prod Data Agent returned both real ontology-grounded baseline answers.")


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ApiError, TimeoutError, OSError, ValueError, ExceptionGroup) as error:
        message = repr(error) if isinstance(error, ExceptionGroup) else str(error)
        record(f"Prod Data Agent verification blocked: {message}")
        print(f"STOP: {message}", file=sys.stderr)
        raise SystemExit(1) from error
