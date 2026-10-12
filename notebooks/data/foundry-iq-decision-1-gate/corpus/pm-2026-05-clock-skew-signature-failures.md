---
id: pm-2026-05-clock-skew-signature-failures
title: "Postmortem: signature failures from clock skew (May 2026)"
doc_type: postmortem
api_versions: "v3"
last_updated: "2026-05-26"
---

**Date:** 2026-05-19. **Region:** us-east. **Duration:** 22 minutes (09:41 to 10:03 UTC). **Impact:** about 2% of deliveries in us-east carried a timestamp that receivers rejected.

## What happened

One signing node's clock drifted 7 minutes ahead of real time. Receivers that enforce the recommended 5-minute timestamp tolerance rejected every delivery signed by that node with a 401 or 403. Relay does not retry those responses on v3, so the rejected deliveries went to the DLQ.

## Resolution

We removed the node from rotation at 10:03 UTC. On 2026-05-20 Relay replayed all affected deliveries into the customers' endpoints automatically.

## Customer guidance

Keep your tolerance at 5 minutes. Do not widen it to fix a one-time skew: a wide window lets an attacker replay a captured request for longer.

## Follow-ups

- Alarm on signing-node clock drift above 30 seconds.
- Sign from the node's synchronized time source only.
