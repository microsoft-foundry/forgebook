"""Fail-closed acceptance checks for the account-brief recipe.

These inspect returned evidence; they neither dispatch tools nor enforce order.
Structural checks always run. Fact checks compare the brief and tool results with
EXPECTED_FACTS. To brief a different customer, edit EXPECTED_FACTS and the question.
"""

import json
import re
from urllib.parse import urlparse


EXPECTED_FACTS = {
    "customer_name": "Adatum Corporation",
    "customer_id": "CUST-001",
    # Values the ID-scoped Fabric IQ result must contain (commas are ignored).
    "structured_evidence": [
        "KB-001-01", "KB-001-02", "Product Support KB", "Employee Knowledge Hub",
        "TS-009967", "TS-009924", "TS-004243", "455", "471", "4609",
    ],
    "report_reference": "FSR-CUST-001-20261105",
    "report_date": "2026-11-05",
    "next_step_quote": (
        "The proposed next step is a small set of approved support scenarios "
        "with a reviewer-scored answer-quality rubric."
    ),
    # Values the brief itself must state.
    "brief_must_mention": ["CUST-001", "TS-004243", "FSR-CUST-001-20261105", "2026-11-05"],
}

TOOLS = {
    "skill": "skill",
    "Fabric IQ": "fabriciq-ontology___ask_ontology",
    "Foundry IQ": "field-sales-reports___knowledge_base_retrieve",
}
MAX_WORDS = 250


def walk(value):
    """Include nested MCP JSON text without treating ordinary prose as JSON."""
    if isinstance(value, str) and value.lstrip().startswith(("{", "[")):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            pass
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def inspect_trace(items):
    """Pair function results by ID; preserve MCP results that have no call_id."""
    outputs = {
        item["call_id"]: item for item in items
        if item.get("type") == "function_call_output"
    }
    records = []
    for call in items:
        if call.get("type") not in {"function_call", "mcp_call"}:
            continue
        result = outputs.get(call.get("call_id"), {}) if call["type"] == "function_call" else call
        output = result.get("output")
        errors = []
        for node in walk([call.get("error"), result.get("error"), output]):
            if isinstance(node, dict):
                if (node.get("isError") is True or node.get("error")
                        or node.get("errors") or node.get("errorCode")):
                    errors.append(node)
                if node.get("status") in {"failed", "error", "cancelled", "incomplete"}:
                    errors.append(node)
                code = node.get("statusCode", node.get("status_code"))
                if str(code).isdigit() and int(code) >= 400:
                    errors.append(node)
            elif isinstance(node, str) and re.search(
                r"(?:\bHTTP(?:/\d(?:\.\d)?)?\s*[45]\d\d\b|\b[45]\d\d\s+(?:Forbidden|Unauthorized|Internal Server Error)\b|\bError:\s|\bTraceback \(most recent call last\))",
                node, re.IGNORECASE,
            ):
                errors.append(node)
        error = call.get("error") or result.get("error") or (errors[0] if errors else None)
        state = "available"
        if (error or not output or call.get("status") not in {None, "completed"}
                or result.get("status") not in {None, "completed"}):
            state = "unavailable"
        elif any(
            isinstance(node, dict) and any(node.get(key) == [] for key in ("rows", "results", "documents"))
            for node in walk(output)
        ):
            state = "no-match"
        records.append({
            "tool": call["name"], "arguments": call.get("arguments"),
            "status": call.get("status"), "error": error, "output": output, "source_state": state,
        })
    return records


def check_structure(answer, records, annotations=None):
    """Customer-independent checks: required calls, their states, order, citations, length."""
    problems = []
    if len(answer.split()) >= MAX_WORDS:
        problems.append(f"The brief must contain fewer than {MAX_WORDS} whitespace-separated words")
    sources = {}
    firsts = []
    for label, tool in TOOLS.items():
        calls = [r for r in records if r["tool"] == tool]
        states = [call["source_state"] for call in calls]
        sources[label] = states[-1] if states else "not called"
        if not calls:
            problems.append(f"{label}: required call is missing")
        elif "unavailable" in states:
            problems.append(f"{label}: call failed or returned an error (source unavailable)")
        elif "no-match" in states:
            problems.append(f"{label}: call succeeded but found no matching record (no match)")
        if calls:
            firsts.append(records.index(calls[0]))
    if len(firsts) == len(TOOLS) and firsts != sorted(firsts):
        problems.append("Expected the skill, then Fabric IQ, then Foundry IQ")
    if annotations is not None and not any(
        a.get("type") == "url_citation" and urlparse(a.get("url", "")).scheme == "https"
        for a in annotations
    ):
        problems.append("The brief has no native url_citation annotation")
    return {"sources": sources, "problems": problems}


def check_facts(answer, records, report_text, report_url, facts=EXPECTED_FACTS):
    """Customer-specific checks driven by EXPECTED_FACTS."""
    problems = []
    customer_id = facts["customer_id"]
    name_token = facts["customer_name"].split()[0]
    ontology = [r for r in records if r["tool"] == TOOLS["Fabric IQ"]]
    retrieval = [r for r in records if r["tool"] == TOOLS["Foundry IQ"]]
    name_calls = [r for r in ontology if name_token in str(r["arguments"])]
    id_calls = [r for r in ontology if customer_id in str(r["arguments"])]
    if not name_calls or customer_id not in str(name_calls[0]["output"]):
        problems.append(f"Fabric IQ did not resolve {facts['customer_name']} to {customer_id}")
    if not id_calls or not retrieval or customer_id not in str(retrieval[-1]["arguments"]):
        problems.append(f"Separate {customer_id}-scoped record lookup and retrieval are required")
    if name_calls and id_calls and retrieval:
        if not (records.index(name_calls[0]) < records.index(id_calls[0]) < records.index(retrieval[0])):
            problems.append("Resolve the name, then look up the ID, then retrieve the report")
    structured = " ".join(str(r["output"]) for r in id_calls).replace(",", "")
    for fact in [customer_id, *facts["structured_evidence"]]:
        if fact.replace(",", "") not in structured:
            problems.append(f"Missing structured source evidence: {fact}")
    quote = facts["next_step_quote"]
    normalized_answer = answer.replace("\u201c", '"').replace("\u201d", '"')
    if f'"{quote}"' not in normalized_answer or quote not in report_text:
        problems.append("Next-step quotation differs from the published report")
    for fact in facts["brief_must_mention"]:
        if fact not in answer:
            problems.append(f"Missing required brief fact: {fact}")
    references = []
    for call in retrieval:
        for node in walk(call["output"]):
            if not isinstance(node, dict) or not isinstance(node.get("sourceData"), dict):
                continue
            data = node["sourceData"]
            passage = " ".join(str(data.get(key, "")) for key in ("content", "snippet"))
            url = data.get("url") or data.get("doc_url") or data.get("docUrl")
            if (quote in passage and customer_id in passage
                    and facts["report_reference"] in passage and facts["report_date"] in passage
                    and url == report_url and urlparse(url).scheme == "https"):
                references.append(node)
    if not references:
        problems.append("No retrieved reference ties the quote, account, report/date, and expected source URL together")
    return {"problems": problems, "supporting_references": references}


def verify_sample(answer, records, report_text, report_url, annotations=None, facts=EXPECTED_FACTS):
    """Run both layers; any problem means the brief is not verified."""
    structure = check_structure(answer, records, annotations)
    fact_checks = check_facts(answer, records, report_text, report_url, facts)
    return {
        "sources": structure["sources"],
        "structural_problems": structure["problems"],
        "fact_problems": fact_checks["problems"],
        "problems": structure["problems"] + fact_checks["problems"],
        "supporting_references": fact_checks["supporting_references"],
    }
