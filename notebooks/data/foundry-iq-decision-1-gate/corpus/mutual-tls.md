---
id: mutual-tls
title: "Mutual TLS"
doc_type: guide
api_versions: "v3"
last_updated: "2026-09-09"
---

Mutual TLS (mTLS) lets your endpoint verify Relay's client certificate in addition to the signature.

## Availability

mTLS is available on the **Enterprise plan** and on **API v3.4 or later**. It is generally available in the regions listed in the v3.4 release notes.

## Set it up

1. Upload the CA bundle that issued your endpoint's trust chain with `relayctl mtls upload-ca <endpoint-id> ca.pem`.
2. Download Relay's client certificate with `relayctl mtls get-cert <endpoint-id>`.
3. Configure your server to require and verify that client certificate.
4. Send a test event with `relayctl test-event <endpoint-id>` and confirm the TLS handshake succeeds.

## Rotation

Relay rotates its client certificate every 90 days. The new certificate is published 14 days before the switch, and both certificates are accepted during that overlap. Pin the issuing CA, not the leaf certificate.

mTLS adds to signature verification, it does not replace it. Keep verifying `Relay-Signature`.
