# Contoso Grid — Substation Cyber Incident Response Runbook

Document ID: CGP-IR-011
Classification: Internal — BCSI
Owner: Grid Security Operations Center (GSOC)

## Scope
This runbook applies to suspected or confirmed cyber incidents affecting substation
control systems, including remote terminal units (RTUs), protective relays, and the
local human-machine interface (HMI).

## Severity Tiers
- **SEV-1**: Confirmed unauthorized control action or loss of SCADA visibility to a
  Bulk Electric System (BES) asset. Notify the on-call Operations Director immediately
  and initiate the Reportable Cyber Security Incident process under CIP-008 within
  **1 hour** of determination.
- **SEV-2**: Malware detected on a non-control corporate-adjacent host in the substation.
- **SEV-3**: Failed access attempts exceeding threshold, no confirmed compromise.

## Priority Substations (Black-Start)
Substation **SS-12 (Riverside)** feeds the downtown medical district and is designated
**black-start priority 1**. Any SEV-1 affecting SS-12 triggers automatic escalation to
the Regional Transmission Operator.

## Containment
1. Isolate the affected device at the SCADA DMZ firewall (VLAN 920).
2. Preserve volatile evidence from the HMI before re-imaging.
3. Switch the affected feeder to manual local control only after Operations approval.
