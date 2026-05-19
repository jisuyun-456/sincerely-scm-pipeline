---
source_file: "scripts/mh_calculator.py"
type: "rationale"
community: "Cluster 22: calc_outbound_qc_m"
location: "L216"
tags:
  - graphify/rationale
  - graphify/EXTRACTED
  - community/Cluster_22_calc_outbound_qc_m
---

# WMS movement은 receiving ledger. 실제입하일 + 입하 qty 보유 → 'receiving'.

## Connections
- [[classify_movement()]] - `rationale_for` [EXTRACTED]

#graphify/rationale #graphify/EXTRACTED #community/Cluster_22_calc_outbound_qc_m