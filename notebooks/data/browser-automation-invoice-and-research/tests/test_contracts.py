from datetime import date
from decimal import Decimal
import json
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from bat_recipe.paths import ASSETS
from bat_recipe.contracts import (
    Draft, Finding, Invoice, PageState, Report, SiteResult, SOURCES, allowed_url,
    strict_schema, validate_invoice, verify_page_state, verify_site,
)
from bat_recipe.runner import RequestBudget, ServiceResponseError, scrub, verify_browser_outputs
from bat_recipe.workflows import draft_invoice, invoice_task


@pytest.fixture
def values():
    return json.loads((ASSETS / "expected_invoice_result.json").read_text(encoding="utf-8"))


def test_valid_invoice(values):
    assert validate_invoice(Invoice.model_validate(values)).invoice_total_matches


def test_mismatch_never_calls_browser(values):
    values["total"] = 1600
    runner = Mock()
    with pytest.raises(ValueError, match="totals mismatch"):
        draft_invoice(runner, "mismatch", Invoice.model_validate(values))
    runner.browser_task.assert_not_called()


def test_exact_decimal_arithmetic(values):
    values.update(subtotal=0.1, tax=0.2, total=0.3)
    assert validate_invoice(Invoice.model_validate(values)).invoice_total_matches


def test_one_cent_mismatch_is_rejected(values):
    values["total"] = 1475.01
    with pytest.raises(ValueError):
        validate_invoice(Invoice.model_validate(values))


@pytest.mark.parametrize("key,value", [
    ("due_date", "2026-01-01"), ("invoice_date", "not-a-date"),
    ("purchase_order", "PO-bad"), ("subtotal", -1), ("total", "NaN"),
    ("currency", "usd"), ("vendor_name", ""),
])
def test_invalid_invoice(values, key, value):
    values[key] = value
    with pytest.raises((ValueError, ValidationError)):
        validate_invoice(Invoice.model_validate(values))


def test_extra_fields_rejected(values):
    values["bank_account"] = "unwanted"
    with pytest.raises(ValidationError):
        Invoice.model_validate(values)


@pytest.mark.parametrize("url", [
    "http://github.com/microsoft-foundry/",
    "https://github.com.attacker.example/microsoft-foundry/",
    "https://github.com/another-org/",
    "https://user:pass@github.com/microsoft-foundry/",
    "https://github.com:444/microsoft-foundry/",
    "https://github.com:bad/microsoft-foundry/",
    "https://github.com/microsoft-foundry/../another-org/",
    "https://github.com/microsoft-foundry/%2e%2e/another-org/",
])
def test_off_scope_urls(url):
    assert not allowed_url(url, SOURCES[2])


def test_localized_learn_url():
    assert allowed_url(
        "https://learn.microsoft.com/en-us/azure/foundry/agents/overview", SOURCES[0]
    )


def test_localized_azure_updates_url():
    assert allowed_url(
        "https://azure.microsoft.com/en-us/updates/?id=example", SOURCES[1]
    )


def test_empty_site_requires_limitation():
    result = SiteResult(site="Learn", url=SOURCES[0], findings=[], limitations=[])
    with pytest.raises(ValueError, match="explicit limitation"):
        verify_site(result, SOURCES[0], date(2026, 9, 1))


@pytest.mark.parametrize("marker", ["", "2026-08-01", "2099-01-01", "not-a-date"])
def test_research_date_rejection(marker):
    result = SiteResult(
        site="Learn", url=SOURCES[0], limitations=[],
        findings=[Finding(
            title="Change", published_or_updated=marker,
            url=SOURCES[0] + "agents/overview",
            observed_change="Observed", why_it_matters="Interpretation", evidence_quote="Quote",
            date_evidence_quote=None,
        )],
    )
    with pytest.raises(ValueError):
        verify_site(result, SOURCES[0], date(2026, 9, 1))


def test_page_state_readback(values):
    invoice = Invoice.model_validate(values)
    fields = {key: str(value) for key, value in invoice.model_dump(mode="json").items()}
    verify_page_state(PageState(fields=fields, submission_attempts=0), invoice)
    fields["total"] = "999"
    with pytest.raises(ValueError, match="amount differs"):
        verify_page_state(PageState(fields=fields, submission_attempts=0), invoice)


def test_submission_sentinel(values):
    invoice = Invoice.model_validate(values)
    with pytest.raises(ValueError, match="Submission attempt"):
        verify_page_state(PageState(fields={}, submission_attempts=1), invoice)


def test_prompt_uses_only_validated_values(values):
    prompt = invoice_task(Invoice.model_validate(values), "https://demo.example/invoice-entry.html")
    assert "VALIDATED_FIELDS" in prompt
    assert "Do not submit" in prompt
    assert "Ignore previous instructions" not in prompt


def test_budget_survives_restart(tmp_path):
    path = tmp_path / "requests.jsonl"
    RequestBudget(path, maximum=1).reserve("first")
    with pytest.raises(RuntimeError, match="budget exhausted"):
        RequestBudget(path, maximum=1).reserve("second")
    assert len(path.read_text().splitlines()) == 1


def test_scrubbing_preserves_usage():
    result = scrub({"api_key": "secret", "input_tokens": 100, "url": "https://a.example/?sig=secret"})
    assert result["api_key"] == "[REDACTED]"
    assert result["input_tokens"] == 100
    assert "secret" not in result["url"]


def test_strict_model_output_schemas():
    assert strict_schema(Invoice)["additionalProperties"] is False
    assert strict_schema(Report)["additionalProperties"] is False
    with pytest.raises(ValueError, match="Dynamic mappings"):
        strict_schema(Draft)


def test_missing_browser_invocation_rejected():
    with pytest.raises(RuntimeError, match="not invoked"):
        verify_browser_outputs([])


@pytest.mark.parametrize("output", [None, ""])
def test_empty_tool_output_rejected(output):
    evidence = [
        {"type": "browser_automation_preview_call", "call_id": "one", "status": "completed"},
        {"type": "browser_automation_preview_call_output", "call_id": "one",
         "status": "completed", "output": output},
    ]
    with pytest.raises(RuntimeError, match="empty or missing"):
        verify_browser_outputs(evidence)


def test_missing_matching_call_output_rejected():
    evidence = [
        {"type": "browser_automation_preview_call", "call_id": "one", "status": "completed"},
        {"type": "browser_automation_preview_call_output", "call_id": "another",
         "status": "completed", "output": "data"},
    ]
    with pytest.raises(RuntimeError, match="correlation"):
        verify_browser_outputs(evidence)


def test_completed_call_requires_nonempty_output():
    evidence = [
        {"type": "browser_automation_preview_call", "call_id": "one", "status": "completed"},
        {"type": "browser_automation_preview_call_output", "call_id": "one",
         "status": "completed", "output": "observed page state"},
    ]
    assert verify_browser_outputs(evidence) == 1


def test_content_filter_error_is_explicit():
    error = ServiceResponseError("response.incomplete", "content_filter")
    assert error.reason == "content_filter"
    assert "content_filter" in str(error)
