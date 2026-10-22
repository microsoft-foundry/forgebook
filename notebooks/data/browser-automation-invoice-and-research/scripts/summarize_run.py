import argparse
import json
from pathlib import Path

from bat_recipe.runner import verify_browser_outputs
from bat_recipe.evidence import verify_workspace_sessions


def summarize(root: Path) -> dict:
    records = [json.loads(line) for line in (root / "run-log.jsonl").read_text().splitlines()]
    known_usage = [record["usage"] for record in records if isinstance(record.get("usage"), dict)]
    input_tokens = sum(usage.get("input_tokens", 0) for usage in known_usage)
    output_tokens = sum(usage.get("output_tokens", 0) for usage in known_usage)
    browser_results = []
    for record in records:
        if not record.get("browser_requested", bool(record.get("browser_calls"))):
            continue
        case = record["case_id"]
        path = root / f"{case}-tool-evidence.json"
        if not path.exists():
            verdict = {"case_id": case, "status": "inconclusive", "reason": "Tool artifact missing"}
        else:
            evidence = json.loads(path.read_text(encoding="utf-8"))
            try:
                verify_browser_outputs(evidence, mode=record.get("browser_mode"))
                verify_workspace_sessions(evidence)
            except (RuntimeError, ValueError) as exc:
                verdict = {"case_id": case, "status": "inconclusive", "reason": str(exc)}
            else:
                verified = root / f"{case}-verification.json"
                proof = json.loads(verified.read_text()) if verified.exists() else {}
                verdict = {
                    "case_id": case,
                    "status": (
                        proof["status"] if proof.get("status") in {"passed", "no_verified_findings"}
                        else "requires_evidence_review"
                    ),
                    "limitations": proof.get("limitations", []),
                }
        browser_results.append(verdict)
    failed_requests = [record["case_id"] for record in records if record["status"] == "failed"]
    expected_safety_blocks = []
    for record in records:
        blocked = root / f"{record['case_id'].removesuffix('-extract')}-blocked.json"
        if record.get("service_reason") == "content_filter" and blocked.exists():
            outcome = json.loads(blocked.read_text())
            if outcome.get("expected_safety_block") is True:
                expected_safety_blocks.append(record["case_id"])
    passed = (bool(browser_results) and not failed_requests
              and all(item["status"] == "passed" for item in browser_results))
    workflow_failures = [case for case in failed_requests
                         if not case.startswith("diagnostic-probe-")
                         and case not in expected_safety_blocks]
    invoice_verified = any(item["case_id"] == "happy-draft" and item["status"] == "passed"
                           for item in browser_results)
    workflow_cases = [item for item in browser_results
                      if not item["case_id"].startswith("diagnostic-probe-")]
    research_complete = (
        {"research-0", "research-1", "research-2"} <= {
            item["case_id"] for item in workflow_cases
        }
        and any(record["case_id"] == "research-synthesis" and record["status"] == "completed"
                for record in records)
        and (root / "web-change-report.json").exists()
    )
    if invoice_verified and not workflow_failures and all(
        item["status"] in {"passed", "no_verified_findings"} for item in workflow_cases
    ):
        if not research_complete:
            overall = "invoice_verified_research_validation_incomplete"
        else:
            overall = ("invoice_verified_with_research_limitations"
                       if any(item["status"] == "no_verified_findings" for item in workflow_cases)
                       else "invoice_and_research_verified")
    else:
        overall = "browser_checks_verified" if passed else "cloud_browser_outcomes_not_verified"
    return {
        "overall": overall,
        "top_level_requests_used": len(records),
        "top_level_request_limit": 8,
        "failed_requests": failed_requests,
        "workflow_failed_requests": workflow_failures,
        "expected_safety_blocks": expected_safety_blocks,
        "browser_cases": browser_results,
        "research_completed": research_complete,
        "usage_visible_in_top_level_responses": {
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "requests_without_usage": len(records) - len(known_usage),
            "known_usage_model_cost_estimate_usd": round(
                input_tokens * 0.75 / 1_000_000 + output_tokens * 4.5 / 1_000_000, 6
            ),
        },
        "billing_confirmed": False,
        "cost_limitations": "Missing usage and internal browser/tool charges remain unknown, not zero.",
        "historical_preview_empty_output_cause": "unconfirmed",
        "verified_mode": "workspace-mcp" if invoice_verified else None,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_dir", type=Path)
    args = parser.parse_args()
    root = args.artifact_dir.resolve()
    summary = summarize(root)
    (root / "demo-results.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
