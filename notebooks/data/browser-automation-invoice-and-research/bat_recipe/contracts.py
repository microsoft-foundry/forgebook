from datetime import date
from decimal import Decimal
import re
from typing import Literal
from urllib.parse import unquote, urlsplit

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Invoice(Contract):
    vendor_name: str = Field(min_length=1, max_length=120)
    invoice_number: str = Field(min_length=1, max_length=40)
    invoice_date: date
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    subtotal: Decimal = Field(ge=0, decimal_places=2)
    tax: Decimal = Field(ge=0, decimal_places=2)
    total: Decimal = Field(ge=0, decimal_places=2)
    purchase_order: str = Field(pattern=r"^PO-\d+$")
    due_date: date


class Validation(Contract):
    invoice_total_matches: bool
    duplicate_check: Literal["not_performed"]
    warnings: list[str]


class PageState(Contract):
    fields: dict[str, str]
    submission_attempts: int = Field(ge=0)
    demo_marker: str | None = None


class ProbeResult(Contract):
    page_url: str
    marker: str = Field(min_length=1)


class FormDraft(Contract):
    url: str
    fields_filled: list[str]
    page_state: PageState


class Draft(Contract):
    status: Literal["awaiting_human_approval"]
    validation: Validation
    extracted_invoice: Invoice
    form_draft: FormDraft
    next_action: str


class Finding(Contract):
    title: str = Field(min_length=1)
    published_or_updated: str
    url: str
    observed_change: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)
    evidence_quote: str = Field(min_length=1, max_length=400)
    date_evidence_quote: str | None = Field(min_length=1, max_length=400)


class SiteResult(Contract):
    site: str
    url: str
    findings: list[Finding] = Field(max_length=1)
    limitations: list[str]


class Report(Contract):
    research_topic: str
    research_window_start: date
    sources: list[SiteResult]
    cross_site_summary: list[str]
    limitations: list[str]


SOURCES = (
    "https://learn.microsoft.com/azure/foundry/",
    "https://azure.microsoft.com/updates/",
    "https://github.com/microsoft-foundry/",
)


def validate_invoice(invoice: Invoice) -> Validation:
    if invoice.due_date < invoice.invoice_date:
        raise ValueError("Due date precedes invoice date; browser access blocked")
    if invoice.subtotal + invoice.tax != invoice.total:
        raise ValueError("Invoice totals mismatch; browser access blocked")
    return Validation(invoice_total_matches=True, duplicate_check="not_performed", warnings=[])


def allowed_url(url: str, source: str, *, exact: bool = False) -> bool:
    try:
        candidate, root = urlsplit(url), urlsplit(source)
        if (
            candidate.scheme != "https"
            or candidate.username is not None
            or candidate.password is not None
            or candidate.hostname != root.hostname
            or candidate.port not in (None, 443)
        ):
            return False
        if exact:
            return url == source
        path = unquote(candidate.path)
        if "\\" in path or "%" in path or any(part in {".", ".."} for part in path.split("/")):
            return False
        if root.hostname in {"learn.microsoft.com", "azure.microsoft.com"}:
            path = re.sub(r"^/[a-z]{2}-[a-z]{2}/", "/", path)
        return path.startswith(root.path)
    except ValueError:
        return False


def verify_page_state(state: PageState, invoice: Invoice) -> None:
    if state.submission_attempts != 0:
        raise ValueError("Submission attempt observed")
    expected = invoice.model_dump(mode="json")
    if set(state.fields) != set(expected):
        raise ValueError("Form field coverage mismatch")
    for key, value in expected.items():
        actual = state.fields[key]
        if key in {"subtotal", "tax", "total"}:
            if Decimal(actual) != Decimal(str(value)):
                raise ValueError(f"Filled amount differs: {key}")
        elif actual != str(value):
            raise ValueError(f"Filled field differs: {key}")


def verify_draft(draft: Draft, invoice: Invoice, url: str) -> None:
    if not allowed_url(draft.form_draft.url, url, exact=True):
        raise ValueError("Draft form URL is off-scope")
    if draft.extracted_invoice != invoice:
        raise ValueError("Draft changed the validated invoice")
    if draft.validation != validate_invoice(invoice):
        raise ValueError("Draft validation differs from code validation")
    if set(draft.form_draft.fields_filled) != set(Invoice.model_fields):
        raise ValueError("Draft does not cover every invoice field")
    verify_page_state(draft.form_draft.page_state, invoice)


def verify_site(result: SiteResult, source: str, since: date) -> None:
    if not allowed_url(result.url, source):
        raise ValueError("Source URL is off-scope")
    if not result.findings and not result.limitations:
        raise ValueError("No findings without an explicit limitation")
    for finding in result.findings:
        if not allowed_url(finding.url, source):
            raise ValueError("Finding URL is off-scope")
        if finding.published_or_updated != "date_not_verified":
            published = date.fromisoformat(finding.published_or_updated)
            if not since <= published <= date.today():
                raise ValueError("Finding is outside the research date window")
        elif not result.limitations:
            raise ValueError("Unverified date requires an explicit limitation")


def strict_schema(model: type[Contract]) -> dict:
    schema = model.model_json_schema()
    # OpenAI strict output requires every object property to be required.
    def visit(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                if "properties" in node:
                    node["required"] = list(node["properties"])
                    node["additionalProperties"] = False
                elif node.get("additionalProperties") is not False:
                    raise ValueError("Dynamic mappings cannot be strict model output schemas")
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)
    visit(schema)
    return schema
