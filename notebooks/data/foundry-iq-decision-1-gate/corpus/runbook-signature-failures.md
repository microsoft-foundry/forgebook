---
id: runbook-signature-failures
title: "Runbook: signature verification failures"
doc_type: runbook
api_versions: "v2, v3"
last_updated: "2026-08-20"
---

Use this runbook when your receiver rejects deliveries with 401 or 403 because the signature does not verify.

Relay does not retry 4xx responses on v3, so rejected deliveries go to the DLQ right away. Fix the cause, then replay them.

## Checklist

1. **Clock skew.** Your server clock must be within 5 minutes of `t`. Check NTP on the receiver.
2. **Raw body.** Verify against the exact bytes you received. If a framework parses and re-serializes the JSON, the signature will not match. Also check for proxies or middleware that change whitespace or compress the body.
3. **Wrong secret.** Confirm the receiver uses the secret of the endpoint that received the delivery, not a different endpoint's secret.
4. **Rotation in progress.** After a rotation the header contains more than one `v1` value. A receiver that compares only the **first** `v1` value, or that still holds only the old secret, will fail. Compare against **every** `v1` value and accept the request if any matches, and deploy the new secret to the receiver.
5. **Single secret on v2.** On API v2 the old secret stops working immediately, so the receiver must hold the new secret before you rotate.

## Verify a failing delivery

Run `relayctl signatures check <delivery-id> --secret <secret>` to see whether the secret verifies the recorded delivery.

When the receiver is fixed, replay the rejected deliveries. See *Runbook: replay the DLQ safely*.
