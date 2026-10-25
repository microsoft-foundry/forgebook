---
id: pm-2026-03-eu-west-delivery-delay
title: "Postmortem: eu-west delivery delay (March 2026)"
doc_type: postmortem
api_versions: "v3"
last_updated: "2026-03-11"
---

**Date:** 2026-03-04. **Region:** eu-west. **Duration:** 47 minutes (14:12 to 14:59 UTC). **Impact:** deliveries were delayed, not lost. About 3% of eu-west workspaces saw deliveries arrive more than 10 minutes late.

## What happened

A routine deploy restarted the queue brokers in eu-west. When the brokers came back, queue partitions rebalanced one after another instead of in parallel, and the rebalance blocked consumption for the partitions that moved last.

## Detection

An alarm on queue age fired at 14:19 UTC, seven minutes after the first delays.

## Resolution

On-call engineers paused the deploy, forced the rebalance to complete, and the queue drained by 14:59 UTC. No events were dropped and no replay was needed.

## Follow-ups

- Stage broker restarts so only one partition group moves at a time.
- Lower the queue-age alarm threshold from 10 minutes to 3 minutes.
- Add a rebalance dry run to the deploy checklist.
