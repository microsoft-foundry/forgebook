---
id: runbook-egress-ip-change
title: "Runbook: egress IP range change"
doc_type: runbook
api_versions: "v2, v3"
last_updated: "2026-08-12"
---

Relay announces egress IP range changes at least 30 days ahead. Use this runbook to update your firewall without dropping deliveries.

1. **Find the announcement.** It is posted on the status page and emailed to workspace admins. Note the cutover date and the new range.
2. **Add the new range.** Add the new egress range to your firewall allowlist before the cutover date. Keep the old range in place.
3. **Test.** After adding the range, run `relayctl test-event <endpoint-id>` to confirm that your endpoint still receives deliveries.
4. **Wait for the cutover.** Deliveries switch to the new range on the cutover date.
5. **Clean up.** Remove the old range 7 days after the cutover, once the delivery log shows no traffic from it.

Workspaces with dedicated static IPs are not affected by shared range changes.

The most common failure after a change is a connection error or timeout from a firewall that blocks the new range. See *Runbook: spike in failed deliveries*.
