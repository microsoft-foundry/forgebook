"""Fail-closed acceptance checks for this public, single-customer example.

These inspect returned evidence; they neither dispatch tools nor enforce order.
Keep the original SDK objects and native annotations for independent inspection.
"""

import json
import re
from urllib.parse import urlparse


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


def verify_sample(answer, records, report_text, report_url):
    """Require supported sample facts and a matching retrieved source passage."""
    problems = []
    if len(answer.split()) >= 250:
        problems.append("The brief must contain fewer than 250 whitespace-separated words")
    skill = [r for r in records if r["tool"] == "skill"]
    ontology = [r for r in records if r["tool"] == "fabriciq-ontology___ask_ontology"]
    retrieval = [r for r in records if r["tool"] == "field-sales-reports___knowledge_base_retrieve"]
    sources = {}
    for label, calls in (("skill", skill), ("Fabric IQ", ontology), ("Foundry IQ", retrieval)):
        sources[label] = "unavailable" if not calls else calls[-1]["source_state"]
        if not calls or any(call["source_state"] != "available" for call in calls):
            problems.append(f"{label}: required call/result missing, failed, or returned no match")
    name_calls = [r for r in ontology if "Adatum" in str(r["arguments"])]
    id_calls = [r for r in ontology if "CUST-001" in str(r["arguments"])]
    if not name_calls or "CUST-001" not in str(name_calls[0]["output"]):
        problems.append("Fabric IQ did not resolve Adatum to CUST-001")
    if not id_calls or not retrieval or "CUST-001" not in str(retrieval[-1]["arguments"]):
        problems.append("Separate ID-scoped record lookup and retrieval are required")
    if skill and name_calls and id_calls and retrieval:
        if not (records.index(skill[0]) < records.index(name_calls[0])
                < records.index(id_calls[0]) < records.index(retrieval[0])):
            problems.append("Observed calls did not follow the example investigation")
    structured = " ".join(str(r["output"]) for r in id_calls)
    required = (
        "CUST-001", "KB-001-01", "KB-001-02", "Product Support KB", "Employee Knowledge Hub",
        "TS-009967", "TS-009924", "TS-004243", "455", "471", "4609",
    )
    for fact in required:
        if fact not in structured.replace(",", ""):
            problems.append(f"Missing structured source evidence: {fact}")
    quote = (
        "The proposed next step is a small set of approved support scenarios "
        "with a reviewer-scored answer-quality rubric."
    )
    normalized_answer = answer.replace("\u201c", '"').replace("\u201d", '"')
    if f'"{quote}"' not in normalized_answer or quote not in report_text:
        problems.append("Next-step quotation differs from the published report")
    for fact in ("CUST-001", "TS-004243", "FSR-CUST-001-20261105", "2026-11-05"):
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
            if (quote in passage and "CUST-001" in passage
                    and "FSR-CUST-001-20261105" in passage and "2026-11-05" in passage):
                if url == report_url and urlparse(url).scheme == "https":
                    references.append(node)
    if not references:
        problems.append("No retrieved reference ties the quote, account, report/date, and expected source URL together")
    return {"sources": sources, "problems": problems, "supporting_references": references}
