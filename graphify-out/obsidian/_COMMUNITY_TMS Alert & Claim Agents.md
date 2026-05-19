---
type: community
cohesion: 0.07
members: 37
---

# TMS Alert & Claim Agents

**Cohesion:** 0.07 - loosely connected
**Members:** 37 nodes

## Members
- [[Configuration loader for Virtual SAP Simulation engine.]] - rationale - harness/virtual_sap/config.py
- [[FI document verifier — checks fi_document integrity and coverage.]] - rationale - harness/virtual_sap/verifier/doc_verifier.py
- [[Phase E — 자재출고요청 자동화 에이전트.  Trigger sap.mat_document 중 movement_type='261'이고]] - rationale - harness/virtual_sap/agents/material_release_agent.py
- [[Phase F — AQL 불합격 → 재발주 에이전트.  Trigger qi_inspection.disposition='block' 이고 아직]] - rationale - harness/virtual_sap/agents/quality_reject_agent.py
- [[Phase F — 기간마감 경고 에이전트.  Trigger 매월 25일 이후, 당월 period_close 가 아직 'closed'가 아닌 경]] - rationale - harness/virtual_sap/agents/period_close_warning_agent.py
- [[Phase F — 납품 지연 알림 에이전트.  Trigger pod_status='delivered' 이고 actual_delivery  r]] - rationale - harness/virtual_sap/agents/delivery_delay_agent.py
- [[Phase F — 세금계산서 자동 발행 에이전트.  Trigger fi_document.doc_type='SD' (매출 전표) 중 아직 inv]] - rationale - harness/virtual_sap/agents/invoice_agent.py
- [[Phase F — 재고 부족 알림 에이전트.  Trigger 최신 inventory_snapshot 에서 qty_on_hand  reorde]] - rationale - harness/virtual_sap/agents/inventory_alert_agent.py
- [[Phase F — 클레임 접수 에이전트.  Trigger shipment.pod_status='exception' 이고 아직 claim 이벤트]] - rationale - harness/virtual_sap/agents/claim_agent.py
- [[Reset singleton (used in tests).]] - rationale - harness/virtual_sap/config.py
- [[Send material release requests for movement_type=261 documents. Returns count pr]] - rationale - harness/virtual_sap/agents/material_release_agent.py
- [[__init__.py_3]] - code - harness/virtual_sap/__init__.py
- [[_log_agent_event()_3]] - code - harness/virtual_sap/agents/material_release_agent.py
- [[_require()]] - code - harness/virtual_sap/config.py
- [[_slack_notify()]] - code - harness/virtual_sap/agents/claim_agent.py
- [[_slack_notify()_2]] - code - harness/virtual_sap/agents/delivery_delay_agent.py
- [[_slack_notify()_4]] - code - harness/virtual_sap/agents/inventory_alert_agent.py
- [[_slack_notify()_5]] - code - harness/virtual_sap/agents/invoice_agent.py
- [[_slack_notify()_6]] - code - harness/virtual_sap/agents/period_close_warning_agent.py
- [[_slack_notify()_7]] - code - harness/virtual_sap/agents/quality_reject_agent.py
- [[claim_agent.py]] - code - harness/virtual_sap/agents/claim_agent.py
- [[config.py_1]] - code - harness/virtual_sap/config.py
- [[delivery_delay_agent.py]] - code - harness/virtual_sap/agents/delivery_delay_agent.py
- [[doc_verifier.py]] - code - harness/virtual_sap/verifier/doc_verifier.py
- [[inventory_alert_agent.py]] - code - harness/virtual_sap/agents/inventory_alert_agent.py
- [[invoice_agent.py]] - code - harness/virtual_sap/agents/invoice_agent.py
- [[material_release_agent.py]] - code - harness/virtual_sap/agents/material_release_agent.py
- [[period_close_warning_agent.py]] - code - harness/virtual_sap/agents/period_close_warning_agent.py
- [[quality_reject_agent.py]] - code - harness/virtual_sap/agents/quality_reject_agent.py
- [[reset_config()]] - code - harness/virtual_sap/config.py
- [[run()]] - code - harness/virtual_sap/agents/claim_agent.py
- [[run()_3]] - code - harness/virtual_sap/agents/delivery_delay_agent.py
- [[run()_5]] - code - harness/virtual_sap/agents/inventory_alert_agent.py
- [[run()_6]] - code - harness/virtual_sap/agents/invoice_agent.py
- [[run()_7]] - code - harness/virtual_sap/agents/material_release_agent.py
- [[run()_9]] - code - harness/virtual_sap/agents/period_close_warning_agent.py
- [[run()_10]] - code - harness/virtual_sap/agents/quality_reject_agent.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/TMS_Alert__Claim_Agents
SORT file.name ASC
```

## Connections to other communities
- 11 edges to [[_COMMUNITY_Cluster 162 _log_agent_event()]]
- 11 edges to [[_COMMUNITY_Virtual SAP Process Steps]]
- 5 edges to [[_COMMUNITY_Cluster 33 base.py]]
- 4 edges to [[_COMMUNITY_Cluster 41 PartnerType]]
- 2 edges to [[_COMMUNITY_Cluster 141 engine.py]]
- 2 edges to [[_COMMUNITY_Cluster 349 _log_agent_event()]]
- 2 edges to [[_COMMUNITY_Cluster 329 _build_confirmatio]]
- 2 edges to [[_COMMUNITY_Cluster 113 _allocate()]]
- 2 edges to [[_COMMUNITY_Cluster 350 _generate_tracking]]
- 2 edges to [[_COMMUNITY_Cluster 240 cli.py]]
- 2 edges to [[_COMMUNITY_Cluster 330 step_03_inventory.]]
- 1 edge to [[_COMMUNITY_Cluster 142 supabase_client.py]]

## Top bridge nodes
- [[config.py_1]] - degree 28, connects to 11 communities
- [[__init__.py_3]] - degree 27, connects to 11 communities
- [[run()_7]] - degree 4, connects to 1 community
- [[doc_verifier.py]] - degree 4, connects to 1 community
- [[run()]] - degree 3, connects to 1 community