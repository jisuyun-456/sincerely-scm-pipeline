---
source_file: "harness/tms_settlement/fetch.py"
type: "rationale"
community: "Cluster 214: assert_domain()"
location: "L31"
tags:
  - graphify/rationale
  - graphify/EXTRACTED
  - community/Cluster_214_assert_domain
---

# Raised when a shipment record has a driver ID not in KNOWN_DRIVERS.

## Connections
- [[UnregisteredDriverError]] - `rationale_for` [EXTRACTED]

#graphify/rationale #graphify/EXTRACTED #community/Cluster_214_assert_domain