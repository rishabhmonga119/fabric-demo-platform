"""Read-only Fabric SQL Endpoint MCP client using the verified DEMO CLI identity."""

from contextlib import asynccontextmanager
import csv
from io import StringIO
import re
from uuid import UUID

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import EmbeddedResource, TextResourceContents

from common import is_metadata_ci, ContextError, verify_context
from http_api import Api, ApiError

URL = "https://api.fabric.microsoft.com/v1/mcp/dataPlane/sqlEndpoint"
REFERENCES = "sqldw-cli/references/consumption.md; fabric-skills/common/SQLDW-CONSUMPTION-CORE.md"


def csv_rows(answer) -> list[dict[str, str]]:
    resources = [block.resource for block in answer.content
                 if isinstance(block, EmbeddedResource) and
                 isinstance(block.resource, TextResourceContents) and
                 (block.resource.mime_type or "").split(";")[0] == "text/csv"]
    if answer.is_error or len(resources) != 1:
        messages = "\n".join(block.text for block in answer.content if block.type == "text")
        raise ApiError("SQL MCP did not return one successful CSV result: " + messages)
    reader = csv.DictReader(StringIO(resources[0].text.lstrip("\ufeff")), strict=True)
    rows = list(reader)
    if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames) or \
            len(rows) >= 10000 or any(None in row or None in row.values() for row in rows):
        raise ApiError("SQL MCP result is malformed, ambiguous or potentially truncated.")
    return rows


@asynccontextmanager
async def sql_reader(config: dict):
    if is_metadata_ci():
        raise ContextError("SQL data checks require the DEMO user, not metadata CI.")
    verify_context()
    api = Api("https://api.fabric.microsoft.com", config["tenant"]["id"], skill="sqldw-cli")
    token = api.credential.get_token("https://api.fabric.microsoft.com/.default")
    headers = {"Authorization": "Bearer " + token.token, "x-ms-fabric-skill": "sqldw-cli"}
    async with httpx2.AsyncClient(headers=headers, timeout=330, follow_redirects=False) as client:
        async with streamable_http_client(URL, http_client=client) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=330) as session:
                await session.initialize()
                available = await session.list_tools()
                tools = [tool for tool in available.tools if tool.name.endswith("execute_query") and
                         {"workspaceId", "itemId", "query"}.issubset(
                             tool.input_schema.get("properties", {}))]
                if len(tools) != 1:
                    raise ApiError("SQL MCP execute_query schema is missing or ambiguous.")

                async def query(workspace: str, endpoint: str, statement: str):
                    UUID(workspace)
                    UUID(endpoint)
                    if not statement.lstrip().upper().startswith("SELECT") or re.search(
                            r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|TRUNCATE|COPY|"
                            r"EXEC(?:UTE)?|INTO|GRANT|DENY|REVOKE)\b", statement, re.IGNORECASE):
                        raise ContextError("Baseline SQL accepts SELECT-only statements.")
                    result = await session.call_tool(tools[0].name, {
                        "workspaceId": workspace, "itemId": endpoint, "query": statement})
                    return csv_rows(result)

                yield query
