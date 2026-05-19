---
type: community
cohesion: 0.08
members: 40
---

# Virtual SAP Process Steps

**Cohesion:** 0.08 - loosely connected
**Members:** 40 nodes

## Members
- [[Atomically increment and return the next sequence for prefix+period.]] - rationale - harness/virtual_sap/id_gen.py
- [[Return the next document ID for the given prefix.      Example next_id(SO, da]] - rationale - harness/virtual_sap/id_gen.py
- [[Return {material_id net_price} from the SO behind the delivery.]] - rationale - harness/virtual_sap/steps/step_07_fi_posting.py
- [[SAP-style sequential document number generator.  Uses sap.doc_counter table with]] - rationale - harness/virtual_sap/id_gen.py
- [[SimContext]] - code - harness/virtual_sap/steps/step_01_order.py
- [[SimContext_1]] - code - harness/virtual_sap/steps/step_02_inbound.py
- [[SimContext_2]] - code - harness/virtual_sap/steps/step_03_inventory.py
- [[SimContext_3]] - code - harness/virtual_sap/steps/step_04_production.py
- [[SimContext_5]] - code - harness/virtual_sap/steps/step_06_delivery.py
- [[SimContext_6]] - code - harness/virtual_sap/steps/step_07_fi_posting.py
- [[SimContext_7]] - code - harness/virtual_sap/steps/step_08_period_close.py
- [[Step 01 — Create Sales Orders.  Generates ctxorders_count sales orders with]] - rationale - harness/virtual_sap/steps/step_01_order.py
- [[Step 02 — Goods Receipt + AQL Inspection (입하 + 검수).  For each open PO not yet pr]] - rationale - harness/virtual_sap/steps/step_02_inbound.py
- [[Step 06 — TMS Shipment creation + POD simulation.  For each posted outbound_deli]] - rationale - harness/virtual_sap/steps/step_06_delivery.py
- [[Step 07 — FI Journal Entry posting.  For each mat_document in this sim_run_id wi]] - rationale - harness/virtual_sap/steps/step_07_fi_posting.py
- [[Step 08 — Month-end Period Close.  Runs only on the 1st of the month. Closes the]] - rationale - harness/virtual_sap/steps/step_08_period_close.py
- [[StepResult]] - code - harness/virtual_sap/steps/step_01_order.py
- [[StepResult_1]] - code - harness/virtual_sap/steps/step_02_inbound.py
- [[StepResult_5]] - code - harness/virtual_sap/steps/step_06_delivery.py
- [[StepResult_6]] - code - harness/virtual_sap/steps/step_07_fi_posting.py
- [[StepResult_7]] - code - harness/virtual_sap/steps/step_08_period_close.py
- [[TypedDict]] - code
- [[_get_carrier()]] - code - harness/virtual_sap/steps/step_06_delivery.py
- [[_get_net_price_for_601()]] - code - harness/virtual_sap/steps/step_07_fi_posting.py
- [[_make_line()]] - code - harness/virtual_sap/steps/step_07_fi_posting.py
- [[_next_seq()]] - code - harness/virtual_sap/id_gen.py
- [[_period_str()]] - code - harness/virtual_sap/steps/step_08_period_close.py
- [[_prior_period()]] - code - harness/virtual_sap/steps/step_08_period_close.py
- [[id_gen.py]] - code - harness/virtual_sap/id_gen.py
- [[next_id()]] - code - harness/virtual_sap/id_gen.py
- [[run()_13]] - code - harness/virtual_sap/steps/step_01_order.py
- [[run()_14]] - code - harness/virtual_sap/steps/step_02_inbound.py
- [[run()_18]] - code - harness/virtual_sap/steps/step_06_delivery.py
- [[run()_19]] - code - harness/virtual_sap/steps/step_07_fi_posting.py
- [[run()_20]] - code - harness/virtual_sap/steps/step_08_period_close.py
- [[step_01_order.py]] - code - harness/virtual_sap/steps/step_01_order.py
- [[step_02_inbound.py]] - code - harness/virtual_sap/steps/step_02_inbound.py
- [[step_06_delivery.py]] - code - harness/virtual_sap/steps/step_06_delivery.py
- [[step_07_fi_posting.py]] - code - harness/virtual_sap/steps/step_07_fi_posting.py
- [[step_08_period_close.py]] - code - harness/virtual_sap/steps/step_08_period_close.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Virtual_SAP_Process_Steps
SORT file.name ASC
```

## Connections to other communities
- 11 edges to [[_COMMUNITY_TMS Alert & Claim Agents]]
- 9 edges to [[_COMMUNITY_Cluster 41 PartnerType]]
- 5 edges to [[_COMMUNITY_Cluster 162 _log_agent_event()]]
- 3 edges to [[_COMMUNITY_Cluster 330 step_03_inventory.]]

## Top bridge nodes
- [[id_gen.py]] - degree 12, connects to 3 communities
- [[next_id()]] - degree 11, connects to 2 communities
- [[step_06_delivery.py]] - degree 9, connects to 2 communities
- [[run()_18]] - degree 6, connects to 2 communities
- [[step_07_fi_posting.py]] - degree 9, connects to 1 community