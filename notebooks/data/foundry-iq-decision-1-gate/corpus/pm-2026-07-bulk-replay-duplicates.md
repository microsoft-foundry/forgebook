---
id: pm-2026-07-bulk-replay-duplicates
title: "Postmortem: duplicate deliveries from bulk replay (July 2026)"
doc_type: postmortem
api_versions: "v3"
last_updated: "2026-07-15"
---

**Date:** 2026-07-08. **Region:** us-east. **Affected version:** v3.2. **Impact:** about 1,200 events were delivered twice.

## What happened

A bulk replay request (`POST /v3/replays`) timed out on the client side after Relay had already accepted it. The customer's script retried the call, which started a second replay of the same deliveries.

## Resolution

v3.3 added support for the `Idempotency-Key` header on `POST /v3/replays` and on publish. A repeated request with the same key returns the original replay instead of starting a new one.

## Customer guidance

- Send an `Idempotency-Key` on every bulk replay request.
- De-duplicate on `Relay-Event-Id` in the receiver. Delivery is at-least-once.
- If a bulk replay call times out, list your replays before you retry it.

## Follow-ups

- Return the replay id from the first response faster, before the scan completes.
