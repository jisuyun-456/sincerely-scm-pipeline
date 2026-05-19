---
source_file: "harness/virtual_sap/agents/quality_reject_agent.py"
type: "rationale"
community: "TMS Alert & Claim Agents"
location: "L1"
tags:
  - graphify/rationale
  - graphify/EXTRACTED
  - community/TMS_Alert__Claim_Agents
---

# Phase F — AQL 불합격 → 재발주 에이전트.  Trigger: qi_inspection.disposition='block' 이고 아직

## Connections
- [[quality_reject_agent.py]] - `rationale_for` [EXTRACTED]

#graphify/rationale #graphify/EXTRACTED #community/TMS_Alert__Claim_Agents