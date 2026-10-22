import argparse
import asyncio
from datetime import date
import json
import os
from pathlib import Path

from bat_recipe.contracts import Invoice, ProbeResult
from bat_recipe.evidence import verify_probe
from bat_recipe.paths import ASSETS
from bat_recipe.runner import Runner, verify_browser_outputs
from bat_recipe.workflows import draft_invoice, merge_research, research_all


def probe(runner: Runner, non_stream: bool) -> None:
    ledger = runner.artifacts / "request-reservations.jsonl"
    reservations = [json.loads(line) for line in ledger.read_text().splitlines()] if ledger.exists() else []
    used = sum(item["case"].startswith("diagnostic-probe-") for item in reservations)
    if used >= 2:
        raise RuntimeError("The two-call diagnostic stage is exhausted")
    if not runner.expected_marker:
        raise ValueError("DEMO_EXPECTED_MARKER must match the locally rendered form")
    case = f"diagnostic-probe-{used + 1}"
    task = (
        f"Open only {runner.form_url}. Read the actual text in #demo-marker and "
        "return it as marker with the observed page_url. Do not click, fill, download, "
        "submit, navigate elsewhere or invent the marker. It must come from the page."
    )
    if runner.browser_mode == "workspace-mcp":
        task += (
            " Create a browser session, reuse its browserSessionId for navigation and "
            "snapshot inspection, and close that session after readback, including on failure. "
            "The snapshot must include the observed URL and #demo-marker text."
        )
    result, evidence = runner.browser_task(
        case, task, ProbeResult,
        max_output_tokens=2000 if runner.browser_mode == "workspace-mcp" else 700,
        stream_response=not non_stream,
    )
    verify_probe(result, evidence, runner.form_url, runner.expected_marker)
    runner.write(f"{case}-verification", {
        "status": "passed", "marker_verified_in_actual_tool_output": True,
        "streaming": not non_stream, "page_url": result.page_url,
        "context": runner.verification_context(),
    })
    runner.write("diagnostic-gate", {
        "status": "passed", "case_id": case, "context": runner.verification_context(),
    })
    print(f"{case}: actual page marker verified in BAT output")


def require_validation_gate(runner: Runner) -> None:
    gate = runner.artifacts / "diagnostic-gate.json"
    if not gate.exists() or json.loads(gate.read_text())["status"] != "passed":
        raise RuntimeError("Validation is blocked until the actual browser marker probe succeeds")
    data = json.loads(gate.read_text())
    if data.get("context") != runner.verification_context():
        raise RuntimeError("Diagnostic gate belongs to a different marker, URL, connection or mode")
    case = data["case_id"]
    result = ProbeResult.model_validate_json((runner.artifacts / f"{case}.json").read_text())
    evidence = json.loads((runner.artifacts / f"{case}-tool-evidence.json").read_text())
    verify_browser_outputs(evidence, mode=runner.browser_mode)
    verify_probe(result, evidence, runner.form_url, runner.expected_marker)


def research_window_start() -> date:
    value = os.environ.get("RESEARCH_WINDOW_START", "")
    try:
        since = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("RESEARCH_WINDOW_START is required in YYYY-MM-DD format") from exc
    if since.isoformat() != value:
        raise ValueError("RESEARCH_WINDOW_START must use YYYY-MM-DD format")
    if since > date.today():
        raise ValueError("RESEARCH_WINDOW_START must not be in the future")
    return since


def validate(runner: Runner) -> None:
    since = research_window_start()
    require_validation_gate(runner)
    existing = runner.artifacts / "request-reservations.jsonl"
    records = [json.loads(line) for line in existing.read_text().splitlines()]
    if any(not item["case"].startswith("diagnostic-probe-") for item in records):
        raise RuntimeError("The approved validation stage was already started; no automatic repeat")
    invoice = runner.extract("happy", ASSETS / "happy_invoice.pdf")
    expected = Invoice.model_validate_json(
        (ASSETS / "expected_invoice_result.json").read_text(encoding="utf-8")
    )
    if invoice != expected:
        raise ValueError("Synthetic PDF extraction differs from the fixture")
    runner.write("happy-extraction-verification", {"status": "passed"})
    draft_invoice(runner, "happy-draft", invoice)
    runner.create_agent()
    results = asyncio.run(research_all(runner, since))
    merge_research(runner, results, since)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("probe", "validate"))
    parser.add_argument("--non-stream", action="store_true")
    args = parser.parse_args(argv)
    from dotenv import load_dotenv
    from bat_recipe.paths import RECIPE_ROOT

    load_dotenv(RECIPE_ROOT / ".env")
    if os.environ.get("LIVE_APPROVED") != "1":
        raise RuntimeError("Authorize live execution and review pricing before creating an agent")
    if args.stage == "validate":
        research_window_start()
    runner = Runner()
    try:
        if args.stage == "validate":
            require_validation_gate(runner)
        runner.create_agent(draft=args.stage == "validate")
        if args.stage == "probe":
            probe(runner, args.non_stream)
        else:
            validate(runner)
    finally:
        runner.close()


if __name__ == "__main__":
    main()
