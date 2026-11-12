"""Approved, bounded data-plane operations. Default command is offline rendering."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from socket import gaierror
from ssl import SSLError
import time
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.error import HTTPError, URLError

from definitions import (API, SAMPLE_FILES, digest, validate_config, source_definition,
                         kb_definition, prompt_connection, prompt_definition, toolbox_definition, retrieve_body)


class ServiceFailure(RuntimeError):
    def __init__(self, status: int | None, operation: str):
        super().__init__(f"{operation} failed; HTTP status={status}; inspect private receipt")
        self.status = status


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def private_directory(path: Path) -> Path:
    resolved = path.resolve(strict=True)
    repo = Path(__file__).resolve().parents[3]
    if resolved == repo or repo in resolved.parents or not resolved.is_dir():
        raise ValueError("Use an existing access-controlled evidence directory outside the checkout")
    return resolved


def approval(path: Path, plan: dict) -> None:
    a = json.loads(path.read_text(encoding="utf-8"))
    if (a.get("approved") is not True or a.get("plan_digest") != digest(plan)
            or a.get("new_disposable_lab") is not True or not a.get("cost_approval_reference")
            or not a.get("support_review_reference")):
        raise PermissionError("BLOCKED: exact operation, cost, new-lab and support approval required")
    expiry = datetime.fromisoformat(a["expires_at"].replace("Z", "+00:00"))
    if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
        raise PermissionError("BLOCKED: approval expired")


class Client:
    def __init__(self, credential, evidence: Path):
        self.credential = credential
        self.evidence = private_directory(evidence)
        self.counter = 0
        self.opener = build_opener(NoRedirectHandler())

    def request(self, method: str, url: str, scope: str, body=None, *, headers=None):
        token = self.credential.get_token(scope).token
        h = {"Authorization": "Bearer " + token, "Content-Type": "application/json", **(headers or {})}
        data = json.dumps(body).encode() if body is not None else None
        request = Request(url, data=data, headers=h, method=method)
        self.counter += 1
        raw, status, server_id, transport_error = b"", None, None, None
        try:
            with self.opener.open(request, timeout=60) as response:
                raw, status = response.read(), response.status
                server_id = response.headers.get("x-ms-request-id") or response.headers.get("request-id")
        except HTTPError as error:
            raw, status = error.read(), error.code
            server_id = error.headers.get("x-ms-request-id") or error.headers.get("request-id")
        except (URLError, TimeoutError) as error:
            cause = error.reason if isinstance(error, URLError) else error
            if isinstance(cause, gaierror):
                transport_error = {"category": "dns", "exception_type": "gaierror"}
            elif isinstance(cause, TimeoutError):
                transport_error = {"category": "timeout", "exception_type": "TimeoutError"}
            elif isinstance(cause, SSLError):
                transport_error = {"category": "tls", "exception_type": "SSLError"}
            else:
                transport_error = {"category": "transport", "exception_type": "URLError"}
        # Request headers/tokens are never serialized. The body may contain private resource mappings.
        receipt = {"at": datetime.now(timezone.utc).isoformat(), "method": method, "url": url,
                   "request_digest": digest(body), "status_code": status,
                   "server_request_id": server_id, "response": raw.decode("utf-8", errors="replace")}
        if transport_error is not None:
            receipt["transport_error"] = transport_error
        filename = self.evidence / f"{time.time_ns()}-{self.counter}.json"
        with filename.open("x", encoding="utf-8") as output:
            json.dump(receipt, output, indent=2)
        if status is None or not 200 <= status < 300:
            raise ServiceFailure(status, method) from None
        return json.loads(raw) if raw else {}


def create_absent(client: Client, url: str, scope: str, definition: dict) -> dict:
    try:
        client.request("GET", url, scope)
    except ServiceFailure as error:
        if error.status != 404:
            raise
    else:
        raise RuntimeError("BLOCKED: object already exists; compare exact readback, do not overwrite/recreate")
    return client.request("PUT", url, scope, definition, headers={"If-None-Match": "*"})


def wait_for_sync(client: Client, c: dict, *, attempts: int = 20, delay: float = 30) -> dict:
    if not 1 <= attempts <= 20 or not 0 <= delay <= 30:
        raise ValueError("Polling is bounded to 20 attempts, 30 seconds apart")
    url = f'{c["search_endpoint"].rstrip("/")}/knowledgesources/{c["source"]}/status?api-version={API}'
    for i in range(attempts):
        status = client.request("GET", url, "https://search.azure.com/.default")
        state = status.get("lastSynchronizationState", {})
        if state.get("endTime"):
            if state.get("status") != "success" or state.get("itemsUpdatesFailed") != 0 or state.get("errors"):
                raise RuntimeError("Ingestion failed; preserve the first failure and inspect private receipts")
            return status
        if i + 1 < attempts:
            time.sleep(delay)
    raise TimeoutError("BLOCKED: synchronization did not finish within the approved polling window")


def plan_for(c: dict, operation: str, fixture_dir: Path) -> dict:
    validate_config(c)
    return {"operation": operation, "config": c, "api": API,
            "source": source_definition(c), "kb": kb_definition(c),
            "prompt_connection": prompt_connection(c), "prompt": prompt_definition(c),
            "toolbox": toolbox_definition(c),
            "fixtures": {name: digest((fixture_dir / name).read_text(encoding="utf-8")) for name in SAMPLE_FILES}}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("operation", choices=["render", "upload", "source", "kb", "retrieve"])
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--evidence-dir", type=Path, required=True)
    p.add_argument("--approval", type=Path)
    args = p.parse_args()
    c = json.loads(args.config.read_text(encoding="utf-8"))
    folder = Path(__file__).resolve().parent
    plan = plan_for(c, args.operation, folder)
    evidence = private_directory(args.evidence_dir)
    if args.operation == "render":
        with (evidence / "definitions.json").open("x", encoding="utf-8") as file:
            json.dump(plan, file, indent=2)
        print("Offline definitions written privately; no Azure calls")
        return 0
    if not args.approval:
        raise PermissionError("BLOCKED: no separate approval provided")
    approval(args.approval, plan)
    from azure.identity import DefaultAzureCredential
    with DefaultAzureCredential() as credential:
        client = Client(credential, evidence)
        scope = "https://search.azure.com/.default"
        endpoint = c["search_endpoint"].rstrip("/")
        if args.operation == "upload":
            from azure.storage.blob import BlobServiceClient, ContentSettings
            with BlobServiceClient(c["storage_endpoint"], credential=credential) as blobs:
                container = blobs.get_container_client(c["container"])
                for name in SAMPLE_FILES:
                    container.upload_blob(f'{c["folder"]}/{name}', (folder / name).read_bytes(), overwrite=False,
                                          content_settings=ContentSettings(content_type="text/markdown"))
        elif args.operation == "source":
            create_absent(client, f'{endpoint}/knowledgesources/{c["source"]}?api-version={API}', scope, source_definition(c))
            wait_for_sync(client, c)
        elif args.operation == "kb":
            create_absent(client, f'{endpoint}/knowledgebases/{c["knowledge_base"]}?api-version={API}', scope, kb_definition(c))
        elif args.operation == "retrieve":
            client.request("POST", f'{endpoint}/knowledgebases/{c["knowledge_base"]}/retrieve?api-version={API}', scope,
                           retrieve_body("According to the fictional policy, when is access revoked after termination?"))
    print("Operation finished; configuration or HTTP success is not a live control PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
