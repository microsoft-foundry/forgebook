# Contoso Grid — SCADA Network Segmentation Standard

Document ID: CGP-NET-007
Classification: Internal — BCSI
Owner: OT Network Engineering

## Network Zones
Contoso Grid operates a three-zone OT architecture aligned to the Purdue model:

- **Corporate Zone (VLAN 10)**: Business IT, email, ERP. No routing into control zones.
- **SCADA DMZ (VLAN 920)**: Jump hosts, patch servers, historian replicas, and the
  Intermediate System for Interactive Remote Access. All cross-zone traffic terminates here.
- **Control Zone (VLAN 30)**: SCADA masters, RTUs, protective relays. No direct route to
  or from the Corporate Zone (VLAN 10); all access is brokered through the SCADA DMZ.

## Firewall Policy
Default-deny applies between all zones. Only explicitly allow-listed protocols and host
pairs are permitted. DNP3 and IEC 61850 traffic is confined to the Control Zone and never
exposed to the Corporate Zone.

## Monitoring
A passive network tap mirrors all SCADA DMZ traffic to the GSOC intrusion detection
sensors. Any new device appearing on VLAN 30 must be registered in the asset inventory
within 24 hours or it is quarantined automatically.
