---
id: pm-2026-09-publish-429-storm
title: "Postmortem: publish 429 retry storm (September 2026)"
doc_type: postmortem
api_versions: "v3"
last_updated: "2026-09-09"
---

**Date:** 2026-09-02. **Region:** us-east. **Duration:** 38 minutes. **Impact:** several workspaces saw sustained HTTP 429 responses from the publish API. No data was lost and rate limits were not changed.

## What happened

A client library retried failed publishes immediately and without jitter. When a brief traffic spike pushed several workspaces over their limit, every client retried at the same instant. The retries kept those workspaces above their limit long after the spike ended.

## Resolution

Customers that honored `Retry-After` recovered on their own. We released SDK 4.1, which adds exponential backoff with full jitter and respects `Retry-After`.

## Customer guidance

Use exponential backoff with full jitter on every retry, and never retry sooner than `Retry-After`. Upgrade to SDK 4.1 or later.

## Follow-ups

- Document the recommended retry policy for custom clients.
- Return `RateLimit-Reset` on every publish response so clients can back off before they hit the limit.
