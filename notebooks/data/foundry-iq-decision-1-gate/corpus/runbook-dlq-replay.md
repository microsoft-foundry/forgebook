---
id: runbook-dlq-replay
title: "Runbook: replay the DLQ safely"
doc_type: runbook
api_versions: "v3"
last_updated: "2026-08-12"
---

Replaying many deliveries at once can overload a receiver that has just recovered. Use these steps to replay safely.

1. **Confirm the receiver is healthy.** Send a test event with `relayctl test-event <endpoint-id>` and check the p95 latency.
2. **Scope the replay.** Filter by endpoint and time window. Check the count first with `relayctl dlq count --endpoint <id> --since <time>`.
3. **Slow it down.** The default replay rate is 50 deliveries per second per endpoint. For a fragile receiver, start lower: `relayctl replay --rate 10 ...`.
4. **Expect duplicates and reordering.** Replays do not preserve order, and a replayed delivery keeps its original event id. Make sure the receiver de-duplicates on `Relay-Event-Id`. Replayed deliveries carry the header `Relay-Replay: true`.
5. **Do not retry a timed-out bulk request blindly.** If a bulk replay call times out, list the replays first to see whether it started, then continue from there. See the July bulk replay postmortem.
6. **Watch the result.** Compare `relayctl dlq count` before and after.

Deliveries that aged out of DLQ retention cannot be replayed. Replay also cannot move a delivery to another region.
