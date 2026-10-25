---
id: rate-limits
title: "Publish rate limits"
doc_type: guide
api_versions: "v3"
last_updated: "2026-09-09"
---

Rate limits apply to the publish API. They are counted per workspace.

| Plan | Default publish limit |
|---|---|
| Free | 10 requests/second |
| Pro | 100 requests/second |
| Enterprise | 1,000 requests/second |

Each workspace can burst to twice its limit for up to 10 seconds.

## Batch publish

On API v3 you can publish up to 100 events in one request. A batch counts as one request against the rate limit.

## When you hit the limit

The publish API returns **HTTP 429**. The response includes a `Retry-After` header with the number of seconds to wait. From v3.2 onward, every publish response also carries `RateLimit-Remaining` and `RateLimit-Reset` headers, so you can slow down before you reach the limit.

Always wait at least the `Retry-After` interval before you retry a 429. Retrying immediately keeps you over the limit.

Rate limits apply to publishing. Delivery to your endpoints is governed by the per-endpoint concurrency limit, not by this limit.
