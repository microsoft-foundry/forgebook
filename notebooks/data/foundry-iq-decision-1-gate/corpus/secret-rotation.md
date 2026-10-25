---
id: secret-rotation
title: "Signing secret rotation"
doc_type: guide
api_versions: "v2, v3"
last_updated: "2026-09-09"
---

You can rotate an endpoint's signing secret from the console or with `relayctl secrets rotate <endpoint-id>`.

## API v3: grace window

When you rotate on v3, Relay creates a new secret and keeps the old one active for a **grace window**. During the window every delivery is signed with both secrets, so the `Relay-Signature` header contains two `v1` values, newest secret first. When the window ends, the old secret is revoked and the header carries a single `v1` value again.

- **Free and Pro:** the grace window is fixed at **24 hours**.
- **Enterprise:** the grace window is configurable from v3.4 onward. Before v3.4 it was fixed at 24 hours.

To end the window early, run `relayctl secrets revoke --now <endpoint-id>`. Revoking cannot be undone.

## API v2: no grace window

On v2 the old secret stops working the moment you rotate. Deliveries carry a single `v1` value signed with the new secret. Update your receiver with the new secret **before** you rotate, or it will reject every delivery until you do.

## Plan the rotation

1. Rotate the secret.
2. Deploy the new secret to your receiver while the old secret is still valid.
3. Confirm deliveries verify against the new secret.
4. Let the grace window expire, or revoke the old secret.
