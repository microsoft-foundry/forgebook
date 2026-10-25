---
id: payload-limits
title: "Payload limits"
doc_type: guide
api_versions: "v2, v3"
last_updated: "2026-09-09"
---

The payload limit applies to the `data` field of the event you publish. It is enforced when you publish, not when Relay delivers.

| Plan | Max payload (API v3) |
|---|---|
| Free | 256 KB |
| Pro | 1 MB |
| Enterprise | 5 MB |

On API v2 the limit is 256 KB for every plan.

If an event exceeds the limit, the publish API rejects it with **HTTP 413** and the error code `payload_too_large`. Relay never truncates a payload.

In a batch publish (v3 only) the limit applies to each event separately, not to the batch.

## Large payloads

For anything close to the limit, use the claim-check pattern: store the large object in your own blob storage and publish a small event that carries its URL and a content hash. The receiver fetches the object after it acknowledges the delivery. This keeps deliveries fast and avoids the 10-second response window.
