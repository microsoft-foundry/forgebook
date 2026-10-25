---
id: runbook-delivery-failure-spike
title: "Runbook: spike in failed deliveries"
doc_type: runbook
api_versions: "v3"
last_updated: "2026-09-02"
---

Use this runbook when the failure rate for one or more endpoints rises sharply.

1. **Check the status page.** If there is an open incident for your workspace's region, stop here. Do not replay until the incident is closed.
2. **Get the picture.** Run `relayctl deliveries stats --since 1h` and group the failures by status code.
3. **Classify the failures.**
   - **Timeouts:** compare your endpoint's p95 latency to the 10-second limit. Acknowledge first and process asynchronously.
   - **5xx:** your receiver is failing. Check its logs and recent deploys.
   - **429 from your endpoint:** your receiver is throttling Relay. Lower the endpoint's concurrency limit.
   - **Other 4xx:** these are not retried and land in the DLQ immediately. If the cause is signature verification, follow *Runbook: signature verification failures*.
   - **Connection or TLS errors:** check DNS, your certificate chain, and your firewall. A firewall that does not allow Relay's egress range looks like a connection error. See *IP allowlist*.
4. **Escalate.** Open a support case with a sample `Relay-Delivery-Id` if more than 20% of attempts fail across several endpoints in the same region, or if the failures began without any change on your side.
5. **Recover.** After the cause is fixed, replay the affected deliveries from the DLQ. See *Runbook: replay the DLQ safely*.
