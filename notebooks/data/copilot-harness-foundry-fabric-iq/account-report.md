# Synthetic account report: Adatum Corporation

**Fictional demo content, not a real customer engagement or sales forecast.**
This report is redistributable under this repository's license.

Customer ID: **CUST-001**

Report reference: **FSR-CUST-001-20261105**

Report date: **2026-11-05**

## Account context

The fictional evaluation concerns a support-team knowledge assistant. The
proposed objective is to help reviewers find an approved answer with its source.
Support operations and an application owner are illustrative stakeholders, not
named people or confirmed participants. Budget, contract value, procurement
date, and current deployment or adoption are unrecorded.

## Recorded evidence

These facts come from the three CSV files beside this report, filtered to
`customer_id = CUST-001`. They describe sparse historical samples, not current
health or a continuous monitoring period.

| Record | Latest sampled observation |
|---|---|
| KB-001-01, Product Support KB, idx-001-01 | TS-009967, 2026-11-05T16:15:00Z, Healthy, sampled p95 455 ms |
| KB-001-02, Employee Knowledge Hub, idx-001-02 | TS-009924, 2026-11-05T12:40:00Z, Healthy, sampled p95 471 ms |

Across 283 sampled intervals, the highest sampled p95 is **4,609 ms**:
`TS-004243`, `KB-001-02`, `idx-001-02`, `2026-10-16T19:15:00Z`, status
`Degraded`. This is not a period-wide p95, confirmed outage, root cause, or SLA
breach. The samples do not establish whether the condition recurred or was
remediated. Repeated customer inventory values must not be summed; sampled p95
values must not be averaged into a global percentile.

## Proposed next step

The proposed next step is a small set of approved support scenarios with a reviewer-scored answer-quality rubric.

Confirm the business question and content owner before this evaluation. Review
the cited historical samples separately from answer quality. Any expansion or
configuration change remains conditional on new evidence; none is approved or
completed by this report.

## Correlation and limits

Use the stable `customer_id` to correlate this writeup with the structured
records. The ID is not a permission check. This public, single-customer fixture
contains no sensitive customer documents. It is not a product telemetry contract
or evidence that any real customer uses these services.
