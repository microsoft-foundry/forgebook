---
id: event-filtering
title: "Event filtering"
doc_type: guide
api_versions: "v3"
last_updated: "2026-08-20"
---

Subscriptions can filter events before delivery so your endpoint only receives what it needs. Filtering is available on **API v3 only**.

A filter is a JMESPath expression evaluated against the event envelope. For example, to receive only paid invoices:

```
type == 'invoice.paid' && data.amount > `0`
```

## Limits

| Plan | Filters per subscription |
|---|---|
| Free | 1 |
| Pro | 5 |
| Enterprise | 20 |

An event is delivered when **all** filters on the subscription match. Events that do not match are counted as `filtered` in the delivery log and are not billed as deliveries.

A filter that fails to evaluate, for example because a field is missing, does not match. Use `exists()` checks if a field is optional.

Filters run before the payload is signed and sent. They cannot modify the event.
