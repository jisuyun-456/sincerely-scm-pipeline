---
type: community
cohesion: 0.08
members: 28
---

# Cluster 33: base.py

**Cohesion:** 0.08 - loosely connected
**Members:** 28 nodes

## Members
- [[.__str__()_1]] - code - harness/virtual_sap/verifier/base.py
- [[.to_dict()]] - code - harness/virtual_sap/verifier/base.py
- [[DimScore_1]] - code - harness/virtual_sap/verifier/base.py
- [[Flow verifier — checks end-to-end order-to-delivery flow completeness.]] - rationale - harness/virtual_sap/verifier/flow_verifier.py
- [[Inventory verifier — checks mat_document and inventory_snapshot integrity.]] - rationale - harness/virtual_sap/verifier/inventory_verifier.py
- [[Issue_1]] - code - harness/virtual_sap/verifier/base.py
- [[Ledger verifier — checks immutable ledger integrity (reversals, orphans, dates).]] - rationale - harness/virtual_sap/verifier/ledger_verifier.py
- [[Run FI document integrity checks for the given sim_run_id.]] - rationale - harness/virtual_sap/verifier/doc_verifier.py
- [[Run all inventory dimension checks for the given sim_run_id.]] - rationale - harness/virtual_sap/verifier/inventory_verifier.py
- [[Run end-to-end flow completeness checks for the given sim_run_id.]] - rationale - harness/virtual_sap/verifier/flow_verifier.py
- [[Run ledger integrity checks for the given sim_run_id.]] - rationale - harness/virtual_sap/verifier/ledger_verifier.py
- [[VerifierResult]] - code - harness/virtual_sap/verifier/base.py
- [[VerifierResult serialization tests.]] - rationale - tests/virtual_sap/test_verifier_base.py
- [[Virtual SAP verifier package.]] - rationale - harness/virtual_sap/verifier/__init__.py
- [[Virtual SAP verifier — shared dataclasses and enums.]] - rationale - harness/virtual_sap/verifier/base.py
- [[__init__.py_8]] - code - harness/virtual_sap/verifier/__init__.py
- [[base.py]] - code - harness/virtual_sap/verifier/base.py
- [[flow_verifier.py]] - code - harness/virtual_sap/verifier/flow_verifier.py
- [[inventory_verifier.py]] - code - harness/virtual_sap/verifier/inventory_verifier.py
- [[ledger_verifier.py]] - code - harness/virtual_sap/verifier/ledger_verifier.py
- [[test_issue_str_representation()]] - code - tests/virtual_sap/test_verifier_base.py
- [[test_verifier_base.py]] - code - tests/virtual_sap/test_verifier_base.py
- [[test_verifier_result_to_dict_failed()]] - code - tests/virtual_sap/test_verifier_base.py
- [[test_verifier_result_to_dict_passed()]] - code - tests/virtual_sap/test_verifier_base.py
- [[verify()]] - code - harness/virtual_sap/verifier/doc_verifier.py
- [[verify()_1]] - code - harness/virtual_sap/verifier/flow_verifier.py
- [[verify()_2]] - code - harness/virtual_sap/verifier/inventory_verifier.py
- [[verify()_3]] - code - harness/virtual_sap/verifier/ledger_verifier.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_33_basepy
SORT file.name ASC
```

## Connections to other communities
- 5 edges to [[_COMMUNITY_TMS Alert & Claim Agents]]
- 2 edges to [[_COMMUNITY_Cluster 41 PartnerType]]

## Top bridge nodes
- [[base.py]] - degree 11, connects to 2 communities
- [[flow_verifier.py]] - degree 4, connects to 1 community
- [[inventory_verifier.py]] - degree 4, connects to 1 community
- [[ledger_verifier.py]] - degree 4, connects to 1 community
- [[verify()]] - degree 3, connects to 1 community