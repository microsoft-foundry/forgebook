---
id: pm-2026-06-rotation-grace-window
title: "Postmortem: rotation grace window dropped on v3.0 (June 2026)"
doc_type: postmortem
api_versions: "v3"
last_updated: "2026-06-18"
---

**Date:** 2026-06-11. **Regions:** all. **Duration:** 14:02 to 16:10 UTC (2 hours 8 minutes). **Affected version:** v3.0 only.

## What happened

On v3.0, a secret rotation during an active retry sequence could produce deliveries that carried only the **new** signature. The retry path read the secret list from a cache that did not yet include the grace-window secret. Receivers that still used the old secret rejected those deliveries.

About 9% of deliveries to endpoints that rotated during the window failed verification.

## Resolution

The fix shipped in **v3.1**. It reads the secret list from the same source as first attempts. Endpoints on v3.1 or later are not affected.

## Customer guidance

Replay the rejected deliveries from the DLQ after you update your receiver. See the replay runbook.

## Follow-ups

- Add an integration test that rotates a secret while deliveries are retrying.
- Alarm on signature verification failures that follow a rotation.
