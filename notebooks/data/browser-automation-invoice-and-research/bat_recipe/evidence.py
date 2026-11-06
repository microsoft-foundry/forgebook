from datetime import date, datetime
import json
import re
from pydantic import ValidationError

from .contracts import Invoice, PageState, ProbeResult, SiteResult, allowed_url, verify_page_state
from .browser_evidence import browser_observations, WORKSPACE_MCP_LABEL, WORKSPACE_READ_TOOLS


def output_text(evidence: list[dict]) -> str:
    return "\n".join(item.output for item in browser_observations(evidence))


def verify_probe(result: ProbeResult, evidence: list[dict], url: str, expected: str) -> None:
    if not expected:
        raise ValueError("Expected marker is required")
    if not allowed_url(result.page_url, url, exact=True):
        raise ValueError("Probe readback URL is off-scope")
    if result.marker != expected:
        raise ValueError("Probe marker does not match the hosted page")
    actual_output = output_text(evidence)
    verify_read_only_calls(evidence)
    if expected not in actual_output:
        raise ValueError("Marker appears only in the model claim, not in BAT output")
    if url not in actual_output:
        raise ValueError("Observed page URL is absent from actual BAT output")
    verify_workspace_sessions(evidence)
    verify_navigation_scope(evidence, url, exact=True)


def json_objects(text: str):
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char in '{"':
            try:
                value, _ = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                yield value
            elif isinstance(value, str) and "{" in value:
                yield from json_objects(value)


def nested_objects(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from nested_objects(item)
    elif isinstance(value, list):
        for item in value:
            yield from nested_objects(item)
    elif isinstance(value, str):
        for item in json_objects(value):
            yield from nested_objects(item)


def verify_invoice_evidence(evidence: list[dict], invoice: Invoice, expected_marker: str,
                            *, form_url: str | None = None) -> PageState:
    text = output_text(evidence)
    verify_workspace_sessions(evidence)
    if form_url is not None:
        verify_navigation_scope(evidence, form_url, exact=True)
    latest_state = None
    for candidate in json_objects(text):
        for value in nested_objects(candidate):
            if not {"fields", "submission_attempts", "demo_marker"} <= value.keys():
                continue
            try:
                state = PageState.model_validate(value)
            except ValidationError:
                continue
            if state.demo_marker == expected_marker:
                latest_state = state
    if latest_state is not None:
        verify_page_state(latest_state, invoice)
        return latest_state
    raise ValueError("No independently readable invoice state with the hosted marker in BAT output")


def verify_research_evidence(result: SiteResult, evidence: list[dict],
                             *, source: str | None = None) -> None:
    observations = browser_observations(evidence)
    verify_workspace_sessions(evidence)
    verify_navigation_scope(evidence, source or result.url)
    verify_read_only_calls(evidence)
    for finding in result.findings:
        matching_outputs = [
            item.output for item in observations
            if finding.url in item.output and finding.evidence_quote in item.output
        ]
        if not matching_outputs:
            raise ValueError("Research finding lacks its direct URL and quote in actual BAT output")
        if finding.published_or_updated == "date_not_verified":
            continue
        quote = finding.date_evidence_quote
        if not quote or not any(quote in output for output in matching_outputs):
            raise ValueError("Research date lacks its excerpt in the same direct-source BAT output")
        published = date.fromisoformat(finding.published_or_updated)
        if published not in publication_dates(quote):
            raise ValueError("Research date differs from the observed publication/update date")


def publication_dates(quote: str) -> set[date]:
    matches = re.finditer(
        r"\b(?:published|updated|released|publication\s+date|release\s+date)"
        r"\s*(?:on\s+)?[:\-]?\s*"
        r"(\d{4}-\d{2}-\d{2}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}"
        r"|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\b",
        quote, re.IGNORECASE,
    )
    dates = set()
    for match in matches:
        for format in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y",
                       "%B %d %Y", "%b %d %Y", "%d %B %Y", "%d %b %Y"):
            try:
                dates.add(datetime.strptime(match[1], format).date())
                break
            except ValueError:
                continue
    return dates


def verify_workspace_sessions(evidence: list[dict]) -> list[str]:
    calls = [item for item in evidence
             if item.get("type") == "mcp_call" and item.get("server_label") == WORKSPACE_MCP_LABEL]
    if not calls:
        return []
    browser_observations(evidence, mode="workspace-mcp")
    created, open_sessions = set(), set()
    for call in calls:
        if call["name"] == "create_browser_session":
            ids = {
                value["browserSessionId"]
                for value in nested_objects(call["output"])
                if isinstance(value.get("browserSessionId"), str)
            }
            if len(ids) != 1 or ids & created:
                raise ValueError("Created browser session is missing, ambiguous or duplicated")
            created.update(ids)
            open_sessions.update(ids)
            continue
        arguments = json.loads(call.get("arguments", "{}"))
        session = arguments.get("browserSessionId")
        if session not in open_sessions:
            raise ValueError("Browser operation does not use its open, same-task session")
        if call["name"] == "close_browser_session":
            open_sessions.remove(session)
    if not created or open_sessions:
        raise ValueError("Workspace browser session closure is not verified")
    return sorted(created)


def verify_navigation_scope(evidence: list[dict], source: str, *, exact=False) -> None:
    for call in evidence:
        if call.get("type") != "mcp_call" or call.get("name") != "browser_navigate":
            continue
        arguments = json.loads(call.get("arguments", "{}"))
        url = arguments.get("url")
        if not isinstance(url, str) or not allowed_url(url, source, exact=exact):
            raise ValueError("Actual MCP navigation left the assigned URL scope")


def verify_read_only_calls(evidence: list[dict]) -> None:
    if any(call.get("type") == "mcp_call" and call.get("server_label") == WORKSPACE_MCP_LABEL
           and call.get("name") not in WORKSPACE_READ_TOOLS for call in evidence):
        raise ValueError("Read-only browser task used a draft/write tool")
