---
id: endpoint-requirements
title: "Endpoint requirements"
doc_type: guide
api_versions: "v3"
last_updated: "2026-08-20"
---

Your endpoint must meet these requirements for Relay to deliver events to it.

- **HTTPS only.** Relay requires TLS 1.2 or later and a certificate that chains to a public CA. Plain HTTP endpoints are rejected when you create them.
- **Ports.** Relay delivers to port 443 and port 8443 only.
- **Response time.** Return a 2xx status within **10 seconds** on API v3. Do slow work asynchronously: acknowledge first, process later.
- **No redirects.** Relay does not follow 3xx redirects. A 3xx response counts as a failed attempt.
- **Response body.** Relay ignores the response body, but it logs the first 4 KB for debugging.
- **Public DNS.** The hostname must resolve through public DNS. Private IPs and `localhost` are rejected.

## Testing an endpoint

Run `relayctl test-event <endpoint-id>` to send a signed sample event. The command prints the status code, the latency, and the response headers it received.

If your firewall restricts inbound traffic, allow the egress IP ranges for your workspace's region. See *IP allowlist*.
