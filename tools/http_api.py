"""Authenticated Graph/Fabric/Power BI JSON requests with context and origin guards."""

import json
import time
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID

from azure.identity import AzureCliCredential
from azure.core.credentials import TokenCredential

from common import ContextError, is_metadata_ci, verify_context, verify_metadata_request


class ApiError(RuntimeError):
    pass


class AcceptedWithoutGraphLocation(ApiError):
    pass


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ApiError("Unexpected HTTP redirect; no authentication forwarded.")


class Api:
    def __init__(self, base: str, tenant_id: str, *, skill: str | None = None,
                 credential: TokenCredential | None = None):
        if base not in ("https://graph.microsoft.com", "https://api.fabric.microsoft.com",
                        "https://api.powerbi.com"):
            raise ContextError("Unsupported authenticated API origin.")
        if base == "https://api.fabric.microsoft.com" and not skill:
            raise ContextError("Fabric requests require an installed skill attribution.")
        self.base = base
        self.skill = skill
        self.credential = credential if credential is not None else \
            AzureCliCredential(process_timeout=30, **({} if is_metadata_ci() else {"tenant_id": tenant_id}))
        self.opener = build_opener(NoRedirects())

    def request(self, method: str, endpoint: str, payload: dict | bytes | None = None,
                *, dry_run: bool = False, content_type: str = "application/json",
                accept_operation: bool = False, with_response_info: bool = False) -> dict | None:
        url = endpoint if endpoint.startswith("https://") else self.base + endpoint
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != urlparse(self.base).netloc:
            raise ContextError("Refusing credentials for an unexpected API origin.")
        verify_metadata_request(method, url, payload)
        mutation = method != "GET"
        for attempt in range(3):
            if mutation:
                verify_context()
            if dry_run and mutation:
                print(f"DRY-RUN: {method} {url}")
                return None
            audience = "https://analysis.windows.net/powerbi/api" \
                if self.base == "https://api.powerbi.com" else self.base
            token = self.credential.get_token(audience + "/.default")
            headers = {"Authorization": "Bearer " + token.token, "Content-Type": content_type}
            # Skills for Fabric: fabric-skills/common/COMMON-CORE.md, auth/REST/rate limits.
            if self.skill:
                headers["x-ms-fabric-skill"] = self.skill
            body = payload if isinstance(payload, bytes) else \
                None if payload is None else json.dumps(payload).encode("utf-8")
            try:
                with self.opener.open(Request(url, data=body, headers=headers, method=method),
                                      timeout=120) as response:
                    def result_with_info(data):
                        if with_response_info:
                            return {"status_code": response.status, "retry_after": response.headers.get("Retry-After"),
                                    "body": data}
                        return data

                    content = response.read()
                    if response.status == 202:
                        if accept_operation:
                            location = response.headers.get("Location")
                            resolved = urljoin(url, location) if location else ""
                            operation = urlparse(resolved)
                            origin = urlparse(self.base)
                            trusted = operation.scheme == "https" and \
                                operation.hostname == origin.hostname and operation.port in (None, 443)
                            if not trusted and self.base == "https://api.fabric.microsoft.com":
                                operation_id = response.headers.get("x-ms-operation-id")
                                if operation_id:
                                    try:
                                        validated_id = str(UUID(operation_id))
                                    except (ValueError, AttributeError) as error:
                                        raise ApiError("Accepted Fabric operation has an invalid operation ID.") from error
                                    # COMMON-CORE.md LRO: canonical poll URI from the documented GUID header.
                                    resolved = self.base + "/v1/operations/" + validated_id
                                    trusted = True
                            if not trusted and self.base == "https://api.powerbi.com" and \
                                    parsed.path.endswith("/refreshes") and \
                                    operation.scheme == "https" and operation.port in (None, 443) and \
                                    not operation.query and not operation.fragment:
                                candidate = operation.path.removeprefix(parsed.path + "/")
                                try:
                                    refresh_id = str(UUID(candidate))
                                except ValueError:
                                    refresh_id = None
                                if refresh_id and operation.path == parsed.path + "/" + refresh_id:
                                    # Public refresh-detail endpoint; never authenticate to a regional Location host.
                                    resolved = self.base + operation.path
                                    trusted = True
                            if not trusted:
                                raise AcceptedWithoutGraphLocation(
                                    f"Accepted operation requires a same-origin Location header "
                                    f"(received scheme={operation.scheme!r}, host={operation.hostname!r}, path={operation.path!r})."
                                )
                            return result_with_info({"operation_uri": resolved})
                        raise ApiError(
                            f"{method} {parsed.path}: asynchronous response requires documented LRO polling."
                        )
                    if not 200 <= response.status < 300:
                        raise ApiError(f"{method} {parsed.path}: HTTP {response.status}")
                    if not content:
                        return result_with_info(None)
                    result = json.loads(content)
                    if not isinstance(result, dict):
                        raise ApiError(f"{method} {parsed.path}: expected a JSON object.")
                    return result_with_info(result)
            except HTTPError as error:
                if error.code in (429, 500, 502, 503, 504) and attempt < 2:
                    delay = error.headers.get("Retry-After", "")
                    time.sleep(int(delay) if delay.isdigit() else 2 ** (attempt + 1))
                    continue
                content = error.read()
                details = json.loads(content) if content else {}
                code = details.get("errorCode") or details.get("error", {}).get("code") or "HTTPError"
                # Error codes only: never echo credential-bearing request bodies.
                raise ApiError(f"{method} {parsed.path}: HTTP {error.code}, {code}") from error
        raise ApiError("API retry budget exhausted.")

    def list(self, endpoint: str, field: str = "value") -> list:
        url = self.base + endpoint
        seen = set()
        result = []
        while url:
            if url in seen:
                raise ApiError("Repeated API pagination URI.")
            seen.add(url)
            data = self.request("GET", url)
            if data is None or not isinstance(data.get(field), list):
                raise ApiError(f"Missing {field} collection from {endpoint}.")
            result.extend(data[field])
            if data.get("@odata.nextLink") or data.get("continuationUri"):
                url = data.get("@odata.nextLink") or data["continuationUri"]
            elif data.get("continuationToken"):
                initial = urlparse(self.base + endpoint)
                query = dict(parse_qsl(initial.query))
                query["continuationToken"] = data["continuationToken"]
                url = urlunparse(initial._replace(query=urlencode(query)))
            else:
                url = ""
        return result
