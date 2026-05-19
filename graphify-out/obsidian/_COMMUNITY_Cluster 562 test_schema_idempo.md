---
type: community
cohesion: 0.67
members: 3
---

# Cluster 562: test_schema_idempo

**Cohesion:** 0.67 - moderately connected
**Members:** 3 nodes

## Members
- [[Verify 0001_initial_schema.sql uses IF NOT EXISTS on every CREATE TABLE.]] - rationale - tests/virtual_sap/test_schema_idempotent.py
- [[test_all_create_table_are_idempotent()]] - code - tests/virtual_sap/test_schema_idempotent.py
- [[test_schema_idempotent.py]] - code - tests/virtual_sap/test_schema_idempotent.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_562_test_schema_idempo
SORT file.name ASC
```
