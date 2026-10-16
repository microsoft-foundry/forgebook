"""Fail-closed evaluation of normalized, credential-free receipts; no Azure calls."""
from __future__ import annotations

import argparse
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import StrEnum
import json
from pathlib import Path
import re
from urllib.parse import parse_qsl, urlsplit

from definitions import API


class Status(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class Result:
    status: Status
    reason: str


REQUIRED = (
    "configuration", "private-ingestion", "hybrid-embeddings", "dns-routing",
    "paired-kb-retrieve", "paired-kb-mcp", "paired-prompt-ingress", "paired-hosted-ingress",
    "dependent-data-planes", "prompt-grounding", "hosted-grounding", "authorization",
    "hosted-egress", "prompt-tool-egress", "failure-behavior", "repeatability", "private-image-pull",
)
REQUEST_FIELDS = ("method", "path", "body_digest", "api_version", "resource_alias",
                  "audience", "principal_alias", "permissions_digest")


def paired(inside: dict, outside: dict, *, control: str = "paired-kb-retrieve") -> Result:
    endpoints = {"paired-kb-retrieve": "retrieve", "paired-kb-mcp": "mcp"}
    if control not in endpoints:
        return Result(Status.BLOCKED, "No supported service adapter for this control")
    for receipt in (inside, outside):
        if receipt.get("service") != "search":
            return Result(Status.BLOCKED, "Both receipts must identify the supported Search service")
        if not all(receipt.get("request", {}).get(k) for k in REQUEST_FIELDS):
            return Result(Status.BLOCKED, "Missing paired request contract")
        if not all(receipt.get(k) for k in ("identity_evidence", "route_evidence", "server_request_id")):
            return Result(Status.BLOCKED, "Missing observed identity, route or server provenance")
    if inside.get("context") != "inside" or outside.get("context") != "outside":
        return Result(Status.BLOCKED, "Paired contexts must be inside and genuinely outside")
    if any(inside["request"][k] != outside["request"][k] for k in REQUEST_FIELDS):
        return Result(Status.BLOCKED, "Requests or effective authorization differ")
    request = inside["request"]
    if not isinstance(request["path"], str):
        return Result(Status.BLOCKED, "A normalized Search request path is required")
    try:
        url = urlsplit(request["path"])
        query = parse_qsl(url.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return Result(Status.BLOCKED, "Malformed Search request path or query")
    expected_path = rf"/knowledgebases/[a-z0-9][a-z0-9-]{{0,127}}/{endpoints[control]}"
    if (url.scheme or url.netloc or url.fragment or not re.fullmatch(expected_path, url.path)
            or request["api_version"] != API
            or query not in ([], [("api-version", API)])):
        return Result(Status.BLOCKED, "Request does not match this Search control's endpoint/API contract")
    if request["method"] != "POST":
        return Result(Status.BLOCKED, "KB retrieve and MCP controls require POST on both sides")
    if inside.get("status_code") != 200 or inside.get("content_validated") is not True:
        return Result(Status.BLOCKED, "Private positive control did not succeed with validated content")
    code = outside.get("status_code")
    if isinstance(code, int) and 200 <= code < 300:
        return Result(Status.FAIL, "Public data-plane request succeeded")
    if code == 401:
        return Result(Status.BLOCKED, "Authentication failure is not network isolation")
    # The raw service error remains private. This exact discriminator is for Search only.
    # Other services require a separately documented adapter; a generic 403 is insufficient.
    if (code == 403 and outside.get("service") == "search"
            and outside.get("denial_signature") == "publicNetworkAccess: Disabled"
            and outside.get("network_diagnostic_evidence")
            and outside.get("network_diagnostic_correlated") is True):
        return Result(Status.PASS, "Matched Search network denial with private positive control")
    return Result(Status.INCONCLUSIVE, "Error does not independently prove network denial")


def ingestion(observation: dict, not_before: str) -> Result:
    required = ("source", "indexer", "status", "shared_links", "expected_targets", "source_content_evidence", "embedding_evidence", "sku")
    if not all(observation.get(k) for k in required):
        return Result(Status.BLOCKED, "Missing ingestion readback, source content or embedding evidence")
    if observation["sku"] not in ("standard2", "standard3", "storage_optimized_l1", "storage_optimized_l2"):
        return Result(Status.FAIL, "Private ingestion needs S2/S3/L1/L2")
    config = observation["source"].get("azureBlobParameters", {}).get("ingestionParameters", {})
    if config.get("networkAccessMode") != "private" or not config.get("embeddingModel"):
        return Result(Status.FAIL, "Source is not configured for private vector ingestion")
    if observation["indexer"].get("executionEnvironment") != "private":
        return Result(Status.FAIL, "Generated indexer did not confirm private execution")
    for group, target in observation["expected_targets"].items():
        if not any(link.get("groupId") == group and link.get("target") == target
                   and link.get("status") == "Approved" and link.get("provisioningState") == "Succeeded"
                   for link in observation["shared_links"]):
            return Result(Status.BLOCKED, "A required shared link is missing, pending or wrongly targeted")
    if set(observation["expected_targets"]) != {"blob", "openai_account"}:
        return Result(Status.BLOCKED, "Both Blob and model private links are required")
    state = observation["status"].get("lastSynchronizationState", {})
    if not state.get("endTime"):
        return Result(Status.BLOCKED, "Synchronization has not completed")
    try:
        end = datetime.fromisoformat(state["endTime"].replace("Z", "+00:00"))
        start = datetime.fromisoformat(not_before.replace("Z", "+00:00"))
        if end.tzinfo is None or start.tzinfo is None or end < start or end > datetime.now(timezone.utc):
            return Result(Status.BLOCKED, "Synchronization is stale or has invalid time provenance")
    except (ValueError, TypeError):
        return Result(Status.BLOCKED, "Malformed synchronization timestamps")
    if state.get("status") != "success" or state.get("itemsUpdatesFailed") != 0 or state.get("errors"):
        return Result(Status.FAIL, "Synchronization was not a zero-failure success")
    return Result(Status.PASS, "Fresh private ingestion readback plus content and embedding evidence")


def grounding(receipt: dict, *, unsupported: bool) -> Result:
    if receipt.get("tool_error"):
        return Result(Status.FAIL, "Retrieval failure cannot become abstention")
    if (receipt.get("tool_name") != "knowledge_base_retrieve" or receipt.get("tool_success") is not True
            or not all(receipt.get(k) for k in ("invocation_id", "tool_call_id", "agent_version", "runtime_principal_evidence", "tool_payload_evidence"))):
        return Result(Status.BLOCKED, "Missing correlated tool payload, runtime identity or pinned version")
    if receipt.get("correlated") is not True:
        return Result(Status.BLOCKED, "Tool call is not correlated to this invocation")
    if unsupported:
        if receipt.get("answer") != "I don't know." or receipt.get("citations"):
            return Result(Status.FAIL, "Unsupported answer must abstain without citations")
        return Result(Status.PASS, "Successful retrieval followed by unsupported-question abstention")
    citations = receipt.get("citations", [])
    if not citations or not receipt.get("claims"):
        return Result(Status.FAIL, "No source-supported claims")
    for claim in receipt["claims"]:
        if not any(c.get("source_file") == claim.get("source_file") and c.get("source_version")
                   and claim.get("supporting_quote") and claim["supporting_quote"] in c.get("source_text", "")
                   and claim.get("faithfulness_review") == "supported" and claim.get("review_evidence")
                   for c in citations):
            return Result(Status.BLOCKED, "Citation marker alone does not establish factual support")
    return Result(Status.PASS, "Citations resolve to source text and each claim has a support review")


def egress(receipt: dict, context: str) -> Result:
    if context not in ("hosted-runtime", "prompt-tool-service") or receipt.get("context") != context:
        return Result(Status.BLOCKED, "A jumpbox cannot stand in for either agent egress path")
    if receipt.get("canary_received") is True:
        return Result(Status.FAIL, "Unapproved destination received the harmless nonce")
    keys = ("invocation_id", "canary_positive_control", "canary_ownership_evidence",
            "allowed_dependency_success", "network_deny_evidence", "runtime_identity_evidence")
    if not all(receipt.get(k) for k in keys) or receipt.get("canary_received") is not False:
        return Result(Status.INCONCLUSIVE, "Need allowed dependency, positive control and correlated deny evidence")
    return Result(Status.PASS, "Task-owned canary denial corroborated from the required runtime")


def public_bundle(results: dict[str, Result], run_alias: str = "offline-draft") -> dict:
    if not re.fullmatch(r"[a-z0-9-]{1,48}", run_alias):
        raise ValueError("Use a nonidentifying run alias")
    # Closed projection: no endpoints, IDs, arbitrary reasons, raw logs or credentials can pass through.
    controls = [{"control": key, "status": str(results.get(key, Result(Status.BLOCKED, "missing")).status)} for key in REQUIRED]
    return {"schema_version": "1.0", "run_alias": run_alias, "live_run": False,
            "observed_at": None,
            "versions": {"search_api": "2026-08-01-preview", "project_sdk": "2.3.0",
                         "hosted_adapter": "1.0.0b260821", "hosted_python": "3.13"},
            "controls": controls, "publish_ready": False}


def exit_code(results: dict[str, Result]) -> int:
    return 0 if all(results.get(k, Result(Status.BLOCKED, "Missing")).status == Status.PASS for k in REQUIRED) else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Private normalized receipt file, not a hand-written PASS list")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results: dict[str, Result] = {}
    if args.input:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        for control, pair in payload.get("pairs", {}).items():
            if control not in ("paired-kb-retrieve", "paired-kb-mcp", "paired-prompt-ingress", "paired-hosted-ingress", "dependent-data-planes"):
                raise ValueError("Unknown control")
            results[control] = paired(pair["inside"], pair["outside"], control=control)
        if "ingestion" in payload:
            results["private-ingestion"] = ingestion(payload["ingestion"], payload["not_before"])
        for control, context in (("hosted-egress", "hosted-runtime"), ("prompt-tool-egress", "prompt-tool-service")):
            if control in payload:
                results[control] = egress(payload[control], context)
    args.output.write_text(json.dumps(public_bundle(results), indent=2) + "\n", encoding="utf-8")
    print("BLOCKED: full live matrix requires approved execution and reviewed evidence adapters")
    return exit_code(results)


if __name__ == "__main__":
    raise SystemExit(main())
