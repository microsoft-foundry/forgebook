# Contoso Grid — NERC CIP Access Control Policy (CIP-004 / CIP-005)

Document ID: CGP-SEC-004
Classification: Internal — BES Cyber System Information (BCSI)
Owner: Office of the CISO, Contoso Grid Operations

## 1. Personnel Risk Assessment
Per CIP-004-7 R3, every individual with authorized electronic or unescorted physical
access to a BES Cyber System must complete a Personnel Risk Assessment (PRA) before
access is granted, and the PRA must be reviewed at least once every **15 calendar months**.

## 2. Electronic Access Control (CIP-005)
All Interactive Remote Access to the Electronic Security Perimeter (ESP) must traverse an
Intermediate System located in the SCADA DMZ. Direct connections from the corporate
network to any Cyber Asset inside the ESP are prohibited. Multi-factor authentication is
required for all Interactive Remote Access sessions.

## 3. Access Revocation
For a termination action, electronic access to BES Cyber Systems must be revoked within
**24 hours** of the termination. For a reassignment or transfer, access that is no longer
required must be removed by the end of the next calendar day.

## 4. Quarterly Access Review
Account managers must verify that user access privileges align with documented need
every calendar quarter. Discrepancies must be logged in the GRC system and remediated
within 30 days.
