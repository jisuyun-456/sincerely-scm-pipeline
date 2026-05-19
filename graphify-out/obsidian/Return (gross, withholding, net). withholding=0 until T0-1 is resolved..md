---
source_file: "harness/tms_settlement/calc.py"
type: "rationale"
community: "Cluster 75: calc.py"
location: "L61"
tags:
  - graphify/rationale
  - graphify/EXTRACTED
  - community/Cluster_75_calcpy
---

# Return (gross, withholding, net). withholding=0 until T0-1 is resolved.

## Connections
- [[_apply_withholding()]] - `rationale_for` [EXTRACTED]

#graphify/rationale #graphify/EXTRACTED #community/Cluster_75_calcpy