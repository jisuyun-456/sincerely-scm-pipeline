---
type: community
cohesion: 0.11
members: 27
---

# Cluster 41: PartnerType

**Cohesion:** 0.11 - loosely connected
**Members:** 27 nodes

## Members
- [[Enum]] - code
- [[Insert a sim_issue record into the sap schema.]] - rationale - harness/virtual_sap/steps/issue_injector.py
- [[IssueCode]] - code - harness/virtual_sap/steps/issue_injector.py
- [[PartnerType]] - code - harness/_core/partners.py
- [[Return True with probability `rate`. Uses rng for reproducibility.]] - rationale - harness/virtual_sap/steps/issue_injector.py
- [[Return material_group for a material_id, or empty string if not found.]] - rationale - harness/virtual_sap/steps/step_04_production.py
- [[Set qi_inspection.disposition='block' for all items in a GR.      Simulates an A]] - rationale - harness/virtual_sap/steps/issue_injector.py
- [[Set shipment.pod_status='exception' to simulate a damagedshort delivery.      T]] - rationale - harness/virtual_sap/steps/issue_injector.py
- [[Severity]] - code - harness/virtual_sap/verifier/base.py
- [[Shared issue injection utility for continuous simulation mode.]] - rationale - harness/virtual_sap/steps/issue_injector.py
- [[SimContext_4]] - code - harness/virtual_sap/steps/step_05_outbound.py
- [[Step 04 — Production Goods Issue (생산출고).  For each open SO item whose material i]] - rationale - harness/virtual_sap/steps/step_04_production.py
- [[Step 05 — Outbound Delivery + Goods Issue (601).  For each open SO not yet deliv]] - rationale - harness/virtual_sap/steps/step_05_outbound.py
- [[StepResult_3]] - code - harness/virtual_sap/steps/step_04_production.py
- [[StepResult_4]] - code - harness/virtual_sap/steps/step_05_outbound.py
- [[_get_material_group()]] - code - harness/virtual_sap/steps/step_04_production.py
- [[inject_aql_failure()]] - code - harness/virtual_sap/steps/issue_injector.py
- [[inject_pod_damage()]] - code - harness/virtual_sap/steps/issue_injector.py
- [[issue_injector.py]] - code - harness/virtual_sap/steps/issue_injector.py
- [[maybe_inject()]] - code - harness/virtual_sap/steps/issue_injector.py
- [[partners.py]] - code - harness/_core/partners.py
- [[record_issue()]] - code - harness/virtual_sap/steps/issue_injector.py
- [[run()_16]] - code - harness/virtual_sap/steps/step_04_production.py
- [[run()_17]] - code - harness/virtual_sap/steps/step_05_outbound.py
- [[step_04_production.py]] - code - harness/virtual_sap/steps/step_04_production.py
- [[step_05_outbound.py]] - code - harness/virtual_sap/steps/step_05_outbound.py
- [[str]] - code

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_41_PartnerType
SORT file.name ASC
```

## Connections to other communities
- 9 edges to [[_COMMUNITY_Virtual SAP Process Steps]]
- 4 edges to [[_COMMUNITY_TMS Alert & Claim Agents]]
- 2 edges to [[_COMMUNITY_Cluster 162 _log_agent_event()]]
- 2 edges to [[_COMMUNITY_Cluster 33 base.py]]

## Top bridge nodes
- [[step_04_production.py]] - degree 9, connects to 2 communities
- [[step_05_outbound.py]] - degree 8, connects to 2 communities
- [[run()_16]] - degree 7, connects to 2 communities
- [[run()_17]] - degree 6, connects to 2 communities
- [[issue_injector.py]] - degree 10, connects to 1 community