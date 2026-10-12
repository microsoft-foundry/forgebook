---
id: runbook-endpoint-auto-disabled
title: "Runbook: endpoint auto-disabled"
doc_type: runbook
api_versions: "v3"
last_updated: "2026-09-09"
---

Relay disables an endpoint automatically to protect it and your workspace from a failing receiver. An endpoint is disabled when it has **100 consecutive failed attempts** (50 before v3.4) or when it returns HTTP 410.

A disabled endpoint shows the status `disabled_auto` in the console and in `relayctl endpoints list`.

## What happens to new events

Events published while the endpoint is disabled are **held**, not dropped: for 24 hours on Free and for 7 days on Pro and Enterprise. When the hold period ends, the held events are discarded and the log records `held_expired`.

## Steps

1. Find out why the endpoint failed. See *Runbook: spike in failed deliveries*.
2. Fix the receiver. Confirm with `relayctl test-event <endpoint-id>`.
3. Re-enable the endpoint with `relayctl endpoints enable <endpoint-id>`.
4. Held events then flow in publish order, subject to the endpoint's concurrency limit.
5. Check the DLQ for deliveries that failed before the endpoint was disabled and replay them.

If the endpoint returned 410 on purpose because you retired it, delete the endpoint instead of re-enabling it.
