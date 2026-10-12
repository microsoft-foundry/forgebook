---
id: dead-letter-and-replay
title: "Dead-letter queue and replay"
doc_type: guide
api_versions: "v2, v3"
last_updated: "2026-09-09"
---

A delivery moves to the **dead-letter queue (DLQ)** when it exhausts its retries or when your endpoint returns a response that Relay does not retry.

## Retention

The DLQ keeps deliveries for **3 days on Free, 14 days on Pro, and 30 days on Enterprise**. After that they are permanently deleted.

## Replay

- **Single delivery:** run `relayctl replay <delivery-id>` or call `POST /v3/deliveries/{id}/replay`.
- **Bulk replay (v3.2 and later):** call `POST /v3/replays` with a filter on endpoint and time range. One request can replay up to **10,000 deliveries**.
- **API v2:** replay works one event at a time from the console. There is no bulk replay.

Replays run at 50 deliveries per second per endpoint by default. Lower the rate with the `--rate` option.

A replayed delivery keeps the original event id and gets a new delivery id. Relay adds the header `Relay-Replay: true` so your receiver can recognize it.

Replay is **not supported across regions**. You can only replay a delivery into an endpoint in the region where the event was published.

Replays do not preserve the original delivery order.
