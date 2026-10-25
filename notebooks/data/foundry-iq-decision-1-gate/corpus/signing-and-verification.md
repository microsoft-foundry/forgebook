---
id: signing-and-verification
title: "Signing and verification"
doc_type: guide
api_versions: "v2, v3"
last_updated: "2026-08-20"
---

Every delivery carries a `Relay-Signature` header so your endpoint can prove the request came from Relay.

```
Relay-Signature: t=1766620800,v1=5257a869e7ecebeda32affa62cdca3fa51cad7e77a0e56ff536d0ce8e108d8bd
```

- `t` is the Unix timestamp (seconds) when Relay signed the request.
- `v1` is a hex HMAC-SHA256 of the string `{t}.{raw_body}`, keyed with your endpoint's signing secret.

## How to verify

1. Parse `t` and every `v1` value from the header.
2. Recompute the HMAC-SHA256 over `{t}.{raw_body}` using your signing secret.
3. Compare your result to each `v1` value with a constant-time comparison. The request is authentic if any value matches.
4. Reject the request if `t` is more than **5 minutes** away from your server clock. Five minutes is the recommended tolerance.

Always hash the **raw request bytes**. If your framework parses the JSON and you re-serialize it, whitespace and key order can change and the signature will not match.

Signing secrets start with `whsec_` followed by 32 random bytes, base64-encoded. Treat them like passwords and store them in a secret manager.

During a secret rotation the header can carry more than one `v1` value. See *Signing secret rotation*.
