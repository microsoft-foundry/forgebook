---
id: release-notes-v3-4
title: "Release notes: API v3.4"
doc_type: release-notes
api_versions: "v3"
last_updated: "2026-09-09"
---

**v3.4 (2026-09-09).**

## New

- **Mutual TLS is generally available** for Enterprise workspaces in **us-east and eu-west**. ap-south is planned and has no date yet.
- **Configurable rotation grace window** for Enterprise: set any value from **1 to 72 hours**. Free and Pro stay fixed at 24 hours.
- **Higher auto-disable threshold.** An endpoint is now disabled after **100 consecutive failed attempts**, up from 50.
- **Higher endpoint concurrency.** Enterprise workspaces can raise the per-endpoint concurrency limit up to 1,000.

## Changed

- `relayctl endpoints list` now shows `disabled_auto` for endpoints that Relay disabled, instead of `disabled`.

## Upgrade notes

No action is required. Existing endpoints keep their current settings. The new auto-disable threshold applies to failure counts that start after the upgrade.
