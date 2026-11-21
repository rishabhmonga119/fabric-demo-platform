"""Authenticated Graph/Fabric JSON requests with context and origin guards."""

import json
import time
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from azure.identity import AzureCliCredential
from azure.core.credentials import TokenCredential

from common import ContextError, verify_context


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
        if base not in ("https://graph.microsoft.com", "https://api.fabric.microsoft.com"):
            raise ContextError("Unsupported authenticated API origin.")
        if base == "https://api.fabric.microsoft.com" and not skill:
            raise ContextError("Fabric requests require an installed skill attribution.")
        self.base = base
        self.skill = skill
        self.credential = credential if credential is not None else AzureCliCredential(tenant_id=tenant_id)
        self.opener = build_opener(NoRedirects())

    def request(self, method: str, endpoint: str, payload: dict | bytes | None = None,
                *, dry_run: bool = False, content_type: str = "application/json",
                accept_operation: bool = False) -> dict | None:
        url = endpoint if endpoint.startswith("https://") else self.base + endpoint
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != urlparse(self.base).netloc:
            raise ContextError("Refusing credentials for an unexpected API origin.")
        mutation = method != "GET"
        for attempt in range(3):
            if mutation:
                verify_context()
            if dry_run and mutation:
                print(f"DRY-RUN: {method} {url}")
                return None
            token = self.credential.get_token(self.base + "/.default")
            headers = {"Authorization": "Bearer " + token.token, "Content-Type": content_type}
            # Skills for Fabric: fabric-skills/common/COMMON-CORE.md, auth/REST/rate limits.
            if self.skill:
                headers["x-ms-fabric-skill"] = self.skill
            body = payload if isinstance(payload, bytes) else \
                None if payload is None else json.dumps(payload).encode("utf-8")
            try:
                with self.opener.open(Request(url, data=body, headers=headers, method=method),
                                      timeout=120) as response:
                    content = response.read()
                    if response.status == 202:
                        if accept_operation:
                            location = response.headers.get("Location")
                            resolved = urljoin(url, location) if location else ""
                            operation = urlparse(resolved)
                            if operation.scheme != "https" or operation.netloc != urlparse(self.base).netloc:
                                raise AcceptedWithoutGraphLocation("Accepted operation requires a same-origin Location header.")
                            return {"operation_uri": resolved}
                        raise ApiError(
                            f"{method} {parsed.path}: asynchronous response requires documented LRO polling."
                        )
                    if not 200 <= response.status < 300:
                        raise ApiError(f"{method} {parsed.path}: HTTP {response.status}")
                    if not content:
                        return None
                    result = json.loads(content)
                    if not isinstance(result, dict):
                        raise ApiError(f"{method} {parsed.path}: expected a JSON object.")
                    return result
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
