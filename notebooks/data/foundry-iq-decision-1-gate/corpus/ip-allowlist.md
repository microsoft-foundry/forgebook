---
id: ip-allowlist
title: "IP allowlist"
doc_type: guide
api_versions: "v2, v3"
last_updated: "2026-08-12"
---

Relay delivers from fixed egress IP ranges. If your firewall restricts inbound traffic, allow the range for your workspace's region.

| Region | Egress range |
|---|---|
| us-east | 203.0.113.0/28 |
| eu-west | 198.51.100.0/28 |
| ap-south | 192.0.2.0/28 |

Allow the range for your workspace's region only. Deliveries never leave the region where the workspace lives.

## Changes

Relay announces egress range changes at least **30 days** in advance on the status page and by email to workspace admins. Add the new range to your allowlist before the cutover date.

## Dedicated IPs

Enterprise workspaces in **us-east and eu-west** can request dedicated static egress IPs. Dedicated IPs are not available in ap-south. Contact your account team to request them.
