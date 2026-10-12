---
id: release-notes-v3-0
title: "Release notes: API v3.0"
doc_type: release-notes
api_versions: "v3"
last_updated: "2026-06-18"
---

**v3.0 is generally available (2026-01-20).**

## New

- **Retry schedule.** Deliveries now get 8 attempts over about 20.6 hours, up from 5 attempts on v2. Non-retryable 4xx responses go straight to the DLQ.
- **Delivery timeout.** Reduced from 30 seconds to 10 seconds.
- **Signing secret rotation with a grace window.** The old secret stays valid for 24 hours and deliveries carry both signatures.
- **Event filtering.** JMESPath filters on subscriptions.
- **Batch publish.** Up to 100 events per request.
- **Plan payload limits.** Free 256 KB, Pro 1 MB, Enterprise 5 MB.
- **DLQ retention.** Free 3 days, Pro 7 days, Enterprise 30 days.

## Deprecation

**API v2 reaches end of support on 2027-03-31.** After that date Relay will not publish security fixes for v2.

## Known issue

Secret rotation on v3.0 can drop the old signature for retried deliveries. This is fixed in v3.1. See the June 2026 postmortem.
