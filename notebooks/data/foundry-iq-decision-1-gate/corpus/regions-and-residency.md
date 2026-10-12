---
id: regions-and-residency
title: "Regions and data residency"
doc_type: guide
api_versions: "v2, v3"
last_updated: "2026-08-12"
---

Relay runs in three regions:

- **us-east** (Virginia)
- **eu-west** (Ireland)
- **ap-south** (Mumbai)

You choose a region when you create a workspace. The region is **fixed for the life of the workspace** and cannot be changed afterward. To move, create a new workspace in the target region and re-create your endpoints and subscriptions.

## What stays in the region

Event payloads, delivery logs, and the dead-letter queue are stored and processed only in the workspace's region. Relay does not copy event data to another region.

Because of this, replay and delivery stay in-region. Relay delivers to your endpoint from egress IPs in the workspace's region. See *IP allowlist* for the ranges.

Publishing from a client in a different region works, but the request travels to the workspace's region, so latency depends on the distance.
