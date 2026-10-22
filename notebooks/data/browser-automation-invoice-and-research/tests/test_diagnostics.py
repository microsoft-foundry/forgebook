from contextlib import nullcontext
import asyncio
from datetime import date, timedelta
import json
from pathlib import Path
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts.render_demo import render
from scripts.summarize_run import summarize
from scripts import diagnose_bat
from scripts.diagnose_bat import require_validation_gate
from bat_recipe.paths import ASSETS, CHECKOUT_ROOT, RECIPE_ROOT
from bat_recipe.contracts import Invoice, ProbeResult, SiteResult, SOURCES
from bat_recipe.evidence import (
    verify_invoice_evidence, verify_probe, verify_research_evidence, verify_workspace_sessions,
    verify_navigation_scope,
)
from bat_recipe.workflows import draft_invoice, research_all
from bat_recipe.runner import (
    RequestBudget, Runner, ServiceResponseError, correlation_headers, reconcile_tool_items,
    verify_browser_outputs,
    make_browser_tool, scrub,
)


def tool_items(output="observed"):
    return [
        {"id": "call-item", "type": "browser_automation_preview_call",
         "call_id": "one", "status": "completed"},
        {"id": "output-item", "type": "browser_automation_preview_call_output",
         "call_id": "one", "status": "completed", "output": output},
    ]


@pytest.mark.parametrize("output", [" ", "\n\t", None, {}, []])
def test_unsupported_outputs(output):
    with pytest.raises(RuntimeError):
        verify_browser_outputs(tool_items(output))


def test_nonempty_tool_error_is_not_success():
    with pytest.raises(RuntimeError, match="tool error"):
        verify_browser_outputs(tool_items('{"status":"error","message":"forbidden"}'))


def test_terminal_output_replaces_incomplete_stream_output():
    early = tool_items("")
    final = tool_items("actual output")
    combined = reconcile_tool_items(early, final)
    assert len(combined) == 2
    assert verify_browser_outputs(combined) == 1


def test_only_allowlisted_correlation_headers():
    result = correlation_headers({
        "X-MS-Request-ID": "id", "Authorization": "secret", "Set-Cookie": "secret"
    })
    assert result == {"x-ms-request-id": "id"}


@pytest.mark.parametrize("page,marker,evidence", [
    ("https://wrong.example/form", "expected", tool_items("expected")),
    ("https://demo.example/form", "incorrect", tool_items("expected")),
    ("https://demo.example/form", "expected", tool_items("nothing observed")),
])
def test_probe_claims_without_real_readback_rejected(page, marker, evidence):
    with pytest.raises(ValueError):
        verify_probe(ProbeResult(page_url=page, marker=marker),
                     evidence, "https://demo.example/form", "expected")


def test_actual_marker_readback():
    verify_probe(ProbeResult(page_url="https://demo.example/form", marker="expected"),
                 tool_items("https://demo.example/form page marker: expected"),
                 "https://demo.example/form", "expected")


def test_invoice_evidence_comes_from_actual_output():
    invoice = Invoice.model_validate_json((ASSETS / "expected_invoice_result.json").read_text())
    state = {
        "fields": {key: str(value) for key, value in invoice.model_dump(mode="json").items()},
        "submission_attempts": 0, "demo_marker": "unique",
    }
    observed = verify_invoice_evidence(tool_items(json.dumps(state)), invoice, "unique")
    assert observed.demo_marker == "unique"
    with pytest.raises(ValueError, match="independently"):
        verify_invoice_evidence(tool_items("agent claims form was filled"), invoice, "unique")


def test_marker_is_rendered_without_modifying_source(tmp_path):
    marker = render(tmp_path)
    assert len(marker) == 32
    assert marker in (tmp_path / "invoice-entry.html").read_text()
    with pytest.raises(FileExistsError):
        render(tmp_path)


class Item:
    def __init__(self, data):
        self.data = data
        self.type = data["type"]

    def model_dump(self, **kwargs):
        return self.data


def fake_runner(tmp_path, monkeypatch, *, output, stream):
    monkeypatch.setenv("LIVE_APPROVED", "1")
    runner = Runner.__new__(Runner)
    runner.artifacts = tmp_path
    runner.model = "test-model"
    runner.agent = SimpleNamespace(name="test-agent", version="1")
    runner.budget = RequestBudget(tmp_path / "ledger.jsonl")
    runner.log_lock = threading.Lock()
    response = SimpleNamespace(
        id="response-one", status="completed", usage=None,
        output=[Item(item) for item in tool_items(output)],
        output_text='{"marker":"actual"}',
    )
    parsed = (nullcontext([SimpleNamespace(type="response.completed", response=response)])
              if stream else response)
    raw = SimpleNamespace(headers={"x-request-id": "correlation", "Authorization": "secret"},
                          parse=lambda: parsed)
    create = Mock(return_value=raw)
    runner.openai = SimpleNamespace(
        responses=SimpleNamespace(with_raw_response=SimpleNamespace(create=create))
    )
    return runner


def test_non_stream_failure_records_response_and_counts(tmp_path, monkeypatch):
    runner = fake_runner(tmp_path, monkeypatch, output="", stream=False)
    with pytest.raises(RuntimeError, match="empty"):
        runner.request("probe", browser=True, stream_response=False, input="read")
    record = json.loads((tmp_path / "run-log.jsonl").read_text())
    assert record["response_id"] == "response-one"
    assert record["browser_calls"] == 1
    assert record["correlation_headers"] == {"x-request-id": "correlation"}
    summary = summarize(tmp_path)
    assert summary["usage_visible_in_top_level_responses"]["requests_without_usage"] == 1
    assert summary["browser_cases"][0]["status"] == "inconclusive"


def test_stream_terminal_only_tool_results_are_captured(tmp_path, monkeypatch):
    runner = fake_runner(tmp_path, monkeypatch, output="actual", stream=True)
    result, evidence = runner.request("probe", browser=True, input="read")
    assert result["marker"] == "actual"
    assert len(evidence) == 2


def test_partial_evidence_survives_stream_error(tmp_path):
    runner = Runner.__new__(Runner)
    calls = []
    record = {"case_id": "test", "browser_calls": 0}
    events = [
        SimpleNamespace(type="response.output_item.done", item=Item(tool_items()[0])),
        SimpleNamespace(type="response.incomplete", response=SimpleNamespace(
            incomplete_details=SimpleNamespace(reason="content_filter"), usage=None,
        )),
    ]
    with pytest.raises(ServiceResponseError):
        runner.consume_stream(events, record, calls)
    assert record["browser_calls"] == 1
    assert calls[0]["call_id"] == "one"


@pytest.mark.parametrize("evidence", [
    [None], [{}], tool_items() + [tool_items()[1]],
    tool_items() + [{**tool_items()[1], "call_id": "orphan"}],
])
def test_malformed_and_orphaned_evidence_rejected(evidence):
    with pytest.raises(RuntimeError):
        verify_browser_outputs(evidence)


def test_missing_marker_stops_before_invoice_call():
    invoice = Invoice.model_validate_json((ASSETS / "expected_invoice_result.json").read_text())
    runner = Mock(form_url="https://demo.example/form", expected_marker=None)
    with pytest.raises(ValueError, match="marker"):
        draft_invoice(runner, "draft", invoice)
    runner.browser_task.assert_not_called()


def test_research_claim_requires_actual_quote_and_url():
    result = SiteResult.model_validate({
        "site": "Learn", "url": "https://learn.microsoft.com/azure/foundry/",
        "findings": [{
            "title": "Synthetic change", "published_or_updated": "date_not_verified",
            "url": "https://learn.microsoft.com/azure/foundry/example",
            "observed_change": "Observed change", "why_it_matters": "Reason",
            "evidence_quote": "Quoted page text",
            "date_evidence_quote": None,
        }],
        "limitations": ["Date unverified"],
    })
    with pytest.raises(ValueError, match="actual BAT output"):
        verify_research_evidence(result, tool_items("No source evidence"))
    verify_research_evidence(result, tool_items(
        "https://learn.microsoft.com/azure/foundry/example\nQuoted page text"
    ))


@pytest.fixture
def dated_research():
    return SiteResult.model_validate({
        "site": "Learn", "url": SOURCES[0], "limitations": [],
        "findings": [{
            "title": "Synthetic change", "published_or_updated": "2026-09-15",
            "url": SOURCES[0] + "example", "observed_change": "Observed change",
            "why_it_matters": "Reason", "evidence_quote": "Quoted page text",
            "date_evidence_quote": "Updated: 2026-09-15",
        }],
    })


@pytest.mark.parametrize("statement", [
    "Updated: 2026-09-15", "Last updated on September 15, 2026",
    "Published 15 Sep 2026", "Released: Sep 15 2026",
])
def test_research_date_is_supported_by_direct_page_excerpt(dated_research, statement):
    finding = dated_research.findings[0]
    finding.date_evidence_quote = statement
    verify_research_evidence(dated_research, tool_items(
        f"{finding.url}\n{finding.evidence_quote}\n{statement}"
    ))


@pytest.mark.parametrize("statement,observed", [
    (None, ""),
    ("Updated: 2026-09-15", ""),
    ("Updated: 2026-09-14", "Updated: 2026-09-14"),
    ("Conference starts 2026-09-15", "Conference starts 2026-09-15"),
    ("Updated: 2026-02-30", "Updated: 2026-02-30"),
])
def test_research_rejects_unsupported_date_claims(dated_research, statement, observed):
    finding = dated_research.findings[0]
    finding.date_evidence_quote = statement
    with pytest.raises(ValueError, match="Research date"):
        verify_research_evidence(dated_research, tool_items(
            f"{finding.url}\n{finding.evidence_quote}\n{observed}"
        ))


def test_research_date_from_another_observation_is_not_source_proof(dated_research):
    finding = dated_research.findings[0]
    evidence = tool_items(f"{finding.url}\n{finding.evidence_quote}")
    unrelated = tool_items("https://unrelated.example/\nUpdated: 2026-09-15")
    for item in unrelated:
        item["id"] += "-other"
        item["call_id"] = "other"
    with pytest.raises(ValueError, match="same direct-source"):
        verify_research_evidence(dated_research, evidence + unrelated)


def test_undated_research_is_not_logged_as_verified_in_window():
    def browser_task(case, task, model):
        source = SOURCES[int(case.rsplit("-", 1)[1])]
        url = source + "example"
        result = SiteResult.model_validate({
            "site": source, "url": source,
            "findings": [{
                "title": "Change", "published_or_updated": "date_not_verified",
                "url": url, "observed_change": "Observed", "why_it_matters": "Reason",
                "evidence_quote": "Quoted text", "date_evidence_quote": None,
            }],
            "limitations": ["Date is not verified as an in-window change."],
        })
        return result, tool_items(f"{url}\nQuoted text")

    runner = SimpleNamespace(browser_task=browser_task, write=Mock())
    results = asyncio.run(research_all(runner, date(2026, 9, 1)))
    assert len(results) == 3
    for call in runner.write.call_args_list:
        proof = call.args[1]
        assert proof["status"] == "no_verified_findings"
        assert proof["publication_dates_verified"] is False
        assert proof["limitations"]


@pytest.mark.parametrize("start", [
    None, "not-a-date", "20260901", (date.today() + timedelta(days=1)).isoformat(),
])
def test_invalid_research_configuration_precedes_all_validation_work(monkeypatch, start):
    if start is None:
        monkeypatch.delenv("RESEARCH_WINDOW_START", raising=False)
    else:
        monkeypatch.setenv("RESEARCH_WINDOW_START", start)
    runner = Mock()
    with pytest.raises(ValueError, match="RESEARCH_WINDOW_START"):
        diagnose_bat.validate(runner)
    assert runner.mock_calls == []

    monkeypatch.setenv("LIVE_APPROVED", "1")
    monkeypatch.setattr("dotenv.load_dotenv", Mock())
    constructor = Mock()
    monkeypatch.setattr(diagnose_bat, "Runner", constructor)
    with pytest.raises(ValueError, match="RESEARCH_WINDOW_START"):
        diagnose_bat.main(["validate"])
    constructor.assert_not_called()


def test_marker_probe_does_not_require_a_research_window(monkeypatch):
    monkeypatch.setenv("LIVE_APPROVED", "1")
    monkeypatch.setenv("RESEARCH_WINDOW_START", "not-a-date")
    monkeypatch.setattr("dotenv.load_dotenv", Mock())
    runner = Mock()
    monkeypatch.setattr(diagnose_bat, "Runner", Mock(return_value=runner))
    probe = Mock()
    monkeypatch.setattr(diagnose_bat, "probe", probe)
    diagnose_bat.main(["probe"])
    probe.assert_called_once_with(runner, False)
    runner.create_agent.assert_called_once_with(draft=False)
    runner.close.assert_called_once()


def test_today_is_a_valid_window_start_before_the_marker_gate(monkeypatch):
    monkeypatch.setenv("RESEARCH_WINDOW_START", date.today().isoformat())
    gate = Mock(side_effect=RuntimeError("Synthetic gate is not ready"))
    monkeypatch.setattr(diagnose_bat, "require_validation_gate", gate)
    runner = Mock()
    with pytest.raises(RuntimeError, match="Synthetic gate"):
        diagnose_bat.validate(runner)
    gate.assert_called_once_with(runner)
    assert runner.mock_calls == []


@pytest.fixture
def runner_clients(monkeypatch, tmp_path):
    for key, value in {
        "PROJECT_ENDPOINT": "https://example.services.ai.azure.com/api/projects/example",
        "MODEL_DEPLOYMENT": "test-model",
        "BROWSER_CONNECTION_ID": "/subscriptions/example/connections/browser",
        "DEMO_FORM_URL": "https://demo.example/form",
        "DEMO_EXPECTED_MARKER": "synthetic-marker",
        "BROWSER_MODE": "workspace-mcp",
        "BROWSER_WORKSPACE_MCP_URL": (
            "https://eastus.mcp.playwright.microsoft.com/playwrightworkspaces/"
            "00000000-0000-0000-0000-000000000000/mcp"
        ),
        "AZURE_SUBSCRIPTION_ID": "00000000-0000-0000-0000-000000000000",
        "ARTIFACT_DIR": str(tmp_path / "external-artifacts"),
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr("bat_recipe.runner.load_dotenv", Mock())
    project, credential = Mock(), Mock()
    monkeypatch.setattr("bat_recipe.runner.AIProjectClient", project)
    monkeypatch.setattr("bat_recipe.runner.AzureCliCredential", credential)
    return project, credential


@pytest.mark.parametrize("directory", [
    str(CHECKOUT_ROOT), str(RECIPE_ROOT), str(RECIPE_ROOT / "artifacts"), "",
])
def test_runner_rejects_source_artifacts_before_writes_or_clients(
    monkeypatch, runner_clients, directory,
):
    monkeypatch.setenv("ARTIFACT_DIR", directory)
    mkdir = Mock()
    monkeypatch.setattr(Path, "mkdir", mkdir)
    with pytest.raises(ValueError, match="ARTIFACT_DIR.*outside"):
        Runner()
    mkdir.assert_not_called()
    for client in runner_clients:
        client.assert_not_called()


def test_runner_accepts_an_external_artifact_directory(runner_clients, tmp_path):
    runner = Runner()
    assert runner.artifacts == (tmp_path / "external-artifacts").resolve()
    assert runner.artifacts.is_dir()
    for client in runner_clients:
        client.assert_called_once()


def mcp_items(**overrides):
    return [{
        "id": "mcp-one", "type": "mcp_call", "server_label": "bat_toolbox",
        "name": "browser_automation", "status": "completed", "error": None,
        "output": "https://demo.example/form marker: expected", **overrides,
    }]


def test_ga_tool_serialization():
    tool = make_browser_tool("native-ga", "connection").as_dict()
    assert tool["type"] == "browser_automation"
    assert "browser_automation_preview" not in tool
    assert tool["browser_automation"]["connection"]["project_connection_id"] == "connection"


def test_mcp_tool_is_allowlisted():
    tool = make_browser_tool("toolbox-mcp", "inner", "https://project/toolbox", "outer").as_dict()
    assert tool["allowed_tools"] == ["browser_automation"]
    assert tool["project_connection_id"] == "outer"


def test_ga_evidence_pair():
    evidence = tool_items("observed")
    for item in evidence:
        item["type"] = item["type"].replace("_preview", "")
    assert verify_browser_outputs(evidence, mode="native-ga") == 1


def test_mcp_evidence_is_not_fabricated_native_output():
    evidence = mcp_items()
    assert verify_browser_outputs(evidence, mode="toolbox-mcp") == 1
    verify_probe(ProbeResult(page_url="https://demo.example/form", marker="expected"),
                 evidence, "https://demo.example/form", "expected")
    assert evidence[0]["type"] == "mcp_call"


@pytest.mark.parametrize("change", [
    {"server_label": "other"}, {"name": "unrelated"},
    {"status": "in_progress"}, {"error": {"code": "forbidden"}},
    {"output": ""}, {"output": '{"isError":true}'}, {"id": None},
])
def test_invalid_mcp_results(change):
    with pytest.raises(RuntimeError):
        verify_browser_outputs(mcp_items(**change))


def test_mcp_discovery_and_approval_are_not_browser_proof():
    for kind in ("mcp_list_tools", "mcp_approval_request"):
        with pytest.raises(RuntimeError):
            verify_browser_outputs([{"type": kind, "id": "metadata"}])


def test_mode_mismatch_rejected():
    with pytest.raises(RuntimeError, match="configured"):
        verify_browser_outputs(mcp_items(), mode="native-ga")


def test_authorization_headers_redacted():
    result = scrub({"authorization": "opaque-token", "headers": {
        "Authorization": "opaque-token", "Cookie": "session-secret", "x-request-id": "trace",
    }})
    assert result["authorization"] == "[REDACTED]"
    assert result["headers"]["Authorization"] == "[REDACTED]"
    assert result["headers"]["Cookie"] == "[REDACTED]"
    assert result["headers"]["x-request-id"] == "trace"


def test_marker_without_actual_url_rejected():
    with pytest.raises(ValueError, match="URL"):
        verify_probe(ProbeResult(page_url="https://demo.example/form", marker="expected"),
                     tool_items("expected"), "https://demo.example/form", "expected")


def test_stale_gate_rejected_before_validation(tmp_path):
    (tmp_path / "diagnostic-gate.json").write_text(json.dumps({
        "status": "passed", "context": {"mode": "old"},
    }))
    runner = SimpleNamespace(artifacts=tmp_path, verification_context=lambda: {"mode": "new"})
    with pytest.raises(RuntimeError, match="different"):
        require_validation_gate(runner)


def workspace_evidence(*, close=True):
    items = []
    for name, output in [
        ("create_browser_session", '{"browserSessionId":"session-one"}'),
        ("browser_snapshot", "https://demo.example/form expected"),
        ("close_browser_session", '{"closed":true}'),
    ]:
        if not close and name == "close_browser_session":
            continue
        items.append({
            **mcp_items()[0], "id": name, "server_label": "bat_workspace", "name": name,
            "output": output,
            "arguments": "{}" if name == "create_browser_session"
            else '{"browserSessionId":"session-one"}',
        })
    return items


def test_workspace_mcp_only_allows_read_tools_for_probe():
    tool = make_browser_tool("workspace-mcp", "connection",
                             workspace_url="https://eastus.mcp.playwright.microsoft.com/test").as_dict()
    assert "browser_fill_form" not in tool["allowed_tools"]
    assert "browser_click" not in tool["allowed_tools"]
    assert "browser_evaluate" not in tool["allowed_tools"]
    draft = make_browser_tool("workspace-mcp", "connection",
                              workspace_url="https://eastus.mcp.playwright.microsoft.com/test",
                              draft=True).as_dict()
    assert "browser_fill_form" in draft["allowed_tools"]


def test_workspace_session_closure_and_marker():
    evidence = workspace_evidence()
    assert verify_workspace_sessions(evidence) == ["session-one"]
    verify_probe(ProbeResult(page_url="https://demo.example/form", marker="expected"),
                 evidence, "https://demo.example/form", "expected")


def test_unclosed_session_cannot_pass_marker_gate():
    with pytest.raises(ValueError, match="closure"):
        verify_probe(ProbeResult(page_url="https://demo.example/form", marker="expected"),
                     workspace_evidence(close=False), "https://demo.example/form", "expected")


def test_wrong_session_rejected():
    evidence = workspace_evidence()
    evidence[1]["arguments"] = '{"browserSessionId":"unrelated-session"}'
    with pytest.raises(ValueError, match="same-task"):
        verify_workspace_sessions(evidence)


def test_nested_json_credentials_are_redacted():
    result = scrub({"output": json.dumps({"accessToken": "opaque-secret",
                                          "liveViewUrl": "https://view/?access_token=opaque"})})
    assert "opaque" not in result["output"]
    assert "[REDACTED]" in result["output"]


def test_invoice_uses_final_actual_state_not_initial_empty_snapshot():
    invoice = Invoice.model_validate_json((ASSETS / "expected_invoice_result.json").read_text())
    initial = {"fields": {key: "" for key in Invoice.model_fields},
               "submission_attempts": 0, "demo_marker": "unique"}
    final = {**initial, "fields": {
        key: str(value) for key, value in invoice.model_dump(mode="json").items()
    }}
    text = json.dumps(initial) + "\n" + json.dumps(json.dumps(final))
    assert verify_invoice_evidence(tool_items(text), invoice, "unique").fields == final["fields"]
    with pytest.raises(ValueError):
        verify_invoice_evidence(tool_items(json.dumps(final) + "\n" + json.dumps({
            **final, "submission_attempts": 1,
        })), invoice, "unique")


def test_actual_navigation_scope_not_just_final_claim():
    evidence = workspace_evidence()
    evidence[1]["name"] = "browser_navigate"
    evidence[1]["arguments"] = json.dumps({
        "browserSessionId": "session-one", "url": "https://unapproved.example/form",
    })
    with pytest.raises(ValueError, match="navigation"):
        verify_navigation_scope(evidence, "https://demo.example/form", exact=True)


def test_corrected_invoice_summary_retains_failed_diagnostic(tmp_path):
    records = [
        {"case_id": "diagnostic-probe-1", "status": "failed", "browser_calls": 0},
        {"case_id": "happy-draft", "status": "completed", "browser_calls": 1},
    ]
    (tmp_path / "run-log.jsonl").write_text("\n".join(json.dumps(r) for r in records))
    (tmp_path / "happy-draft-tool-evidence.json").write_text(json.dumps(tool_items()))
    (tmp_path / "happy-draft-verification.json").write_text('{"status":"passed"}')
    summary = summarize(tmp_path)
    assert summary["overall"] == "invoice_verified_research_validation_incomplete"
    assert summary["research_completed"] is False
    assert summary["failed_requests"] == ["diagnostic-probe-1"]
    assert summary["workflow_failed_requests"] == []


def test_filtered_pdf_is_not_successful_extraction_or_browser_outage(tmp_path):
    (tmp_path / "run-log.jsonl").write_text(json.dumps({
        "case_id": "injection-extract", "status": "failed", "browser_calls": 0,
        "service_reason": "content_filter", "usage": None,
    }))
    (tmp_path / "injection-blocked.json").write_text(json.dumps({
        "status": "blocked", "reason": "content_filter", "browser_access": "not_attempted",
        "expected_safety_block": True,
    }))
    summary = summarize(tmp_path)
    assert summary["failed_requests"] == ["injection-extract"]
    assert summary["expected_safety_blocks"] == ["injection-extract"]
    assert summary["workflow_failed_requests"] == []
    assert summary["overall"] != "browser_checks_verified"


def test_probe_cannot_use_fill_tool():
    evidence = workspace_evidence()
    evidence[1]["name"] = "browser_fill_form"
    with pytest.raises(ValueError, match="Read-only"):
        verify_probe(ProbeResult(page_url="https://demo.example/form", marker="expected"),
                     evidence, "https://demo.example/form", "expected")


def test_switching_to_read_agent_deletes_previous_owned_version(tmp_path):
    runner = Runner.__new__(Runner)
    runner.artifacts = tmp_path
    runner.agent = SimpleNamespace(name="owned-draft", version="1")
    runner.browser_mode = "workspace-mcp"
    runner.connection = "connection"
    runner.workspace_mcp_url = "https://eastus.mcp.playwright.microsoft.com/test"
    runner.toolbox_url = runner.toolbox_connection = None
    runner.model = "test-model"
    runner.project = Mock()
    runner.project.agents.create_version.return_value = SimpleNamespace(name="owned-read", version="1")
    runner.create_agent()
    runner.project.agents.delete_version.assert_called_once_with(
        agent_name="owned-draft", agent_version="1",
    )
    tool = runner.project.agents.create_version.call_args.kwargs["definition"].tools[0].as_dict()
    assert "browser_fill_form" not in tool["allowed_tools"]
    assert (tmp_path / "agent-cleanup-owned-draft.json").exists()
