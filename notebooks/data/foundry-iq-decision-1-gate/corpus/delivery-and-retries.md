---
id: delivery-and-retries
title: "Delivery and retries"
doc_type: guide
api_versions: "v3"
last_updated: "2026-09-09"
---

Relay delivers every event **at least once**. A delivery attempt succeeds when your endpoint returns an HTTP 2xx status within **10 seconds**.

## Retry schedule (API v3)

If an attempt fails, Relay retries on an exponential schedule. A delivery gets **8 attempts in total**. The wait between attempts is 10 seconds, 1 minute, 5 minutes, 30 minutes, 2 hours, 6 hours, then 12 hours, so the last attempt happens about 20.6 hours after the first.

Relay retries after network errors, timeouts, HTTP 408, HTTP 429, and any 5xx response. Every other 4xx response is **not retried**: the delivery goes straight to the dead-letter queue (DLQ). That includes 400, 401, 403, and 404 responses from your endpoint.

An HTTP 410 (Gone) response is a special case. Relay moves the delivery to the DLQ and immediately disables the endpoint.

## Concurrency

Relay sends at most 50 deliveries at a time to a single endpoint. Free workspaces are fixed at 50. Pro workspaces can raise the limit up to 200. Enterprise workspaces can raise it up to 1,000 (v3.4 and later).

## Delivery logs

Delivery attempts are kept in the delivery log for 24 hours on Free, 7 days on Pro, and 30 days on Enterprise. Each attempt records the status code, latency, and the first 4 KB of your response body.

Relay includes an event id (`Relay-Event-Id`) and a delivery id (`Relay-Delivery-Id`) on every request. Because delivery is at-least-once, receivers should de-duplicate on `Relay-Event-Id`.
