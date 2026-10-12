---
id: release-notes-v2-9
title: "Release notes: API v2.9 (final v2 release)"
doc_type: release-notes
api_versions: "v2"
last_updated: "2025-11-18"
---

**v2.9 (2025-11-18) is the final v2 release.** v2 now receives security fixes only, and reaches end of support on **2027-03-31**.

## Summary of v2 behavior

- **Retries:** 5 attempts over about 3.6 hours. The waits between attempts are 1 minute, 5 minutes, 30 minutes, and 3 hours. Relay retries every non-2xx response.
- **Delivery timeout:** 30 seconds.
- **Signing secret rotation:** immediate. The old secret stops working when you rotate.
- **Payload limit:** 256 KB on every plan.
- **Replay:** one event at a time from the console.
- **No event filtering and no batch publish.**

## Migrating to v3

v3 shortens the delivery timeout to 10 seconds. Endpoints that take longer than 10 seconds to respond need to acknowledge faster before you move them to v3.
