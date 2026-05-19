---
source_file: "harness/virtual_sap/agents/delivery_delay_agent.py"
type: "rationale"
community: "TMS Alert & Claim Agents"
location: "L1"
tags:
  - graphify/rationale
  - graphify/EXTRACTED
  - community/TMS_Alert__Claim_Agents
---

# Phase F — 납품 지연 알림 에이전트.  Trigger: pod_status='delivered' 이고 actual_delivery > r

## Connections
- [[delivery_delay_agent.py]] - `rationale_for` [EXTRACTED]

#graphify/rationale #graphify/EXTRACTED #community/TMS_Alert__Claim_Agents