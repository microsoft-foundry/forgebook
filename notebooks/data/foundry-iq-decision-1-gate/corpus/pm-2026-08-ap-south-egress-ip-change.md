---
id: pm-2026-08-ap-south-egress-ip-change
title: "Postmortem: ap-south egress IP change (August 2026)"
doc_type: postmortem
api_versions: "v3"
last_updated: "2026-08-19"
---

**Date:** 2026-08-12. **Region:** ap-south. **Duration:** about 4 hours for the last affected customer. **Impact:** 14 workspaces saw connection errors until they updated their allowlists.

## What happened

The ap-south egress range moved from 192.0.2.64/28 to 192.0.2.0/28 on 2026-08-12. We announced the change on 2026-07-13, 30 days before. Fourteen workspaces that restrict inbound traffic had not added the new range, so their firewalls dropped the deliveries.

## Resolution

Affected customers added the new range and replayed the failed deliveries. Support contacted every workspace that showed failures within the first hour.

## Follow-ups

- Send a reminder email 7 days before every cutover, not only the first announcement.
- Show a console banner on workspaces with an IP allowlist that has not added the new range.
