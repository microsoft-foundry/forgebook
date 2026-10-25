---
id: release-notes-v3-2
title: "Release notes: API v3.2"
doc_type: release-notes
api_versions: "v3"
last_updated: "2026-04-14"
---

**v3.2 (2026-04-14).**

## New

- **Bulk replay.** `POST /v3/replays` replays up to 10,000 deliveries per request.
- **DLQ retention for Pro** increases from 7 days to 14 days. Free and Enterprise are unchanged.
- **Rate-limit headers.** Publish responses include `RateLimit-Remaining` and `RateLimit-Reset`.
- **relayctl 2.0.** New `relayctl dlq` and `relayctl replay --rate` commands.

## Fixed

- The console showed delivery latency in the wrong unit for deliveries slower than one second.

## Upgrade notes

relayctl 2.0 renames `relayctl retry` to `relayctl replay`. The old name keeps working until v3.6.
