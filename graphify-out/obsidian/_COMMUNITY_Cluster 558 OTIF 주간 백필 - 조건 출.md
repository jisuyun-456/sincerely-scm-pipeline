---
type: community
cohesion: 0.67
members: 3
---

# Cluster 558: OTIF 주간 백필 - 조건: 출

**Cohesion:** 0.67 - moderately connected
**Members:** 3 nodes

## Members
- [[OTIF 주간 백필 - 조건 출하확정일이 대상 주간이고, 발송상태_TMS=출하완료, OTIF 링크 없음 - 동작 Shipment별 OTI]] - rationale - scripts/backfill/backfill_otif.py
- [[backfill_otif.py]] - code - scripts/backfill/backfill_otif.py
- [[run()_21]] - code - scripts/backfill/backfill_otif.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_558_OTIF___-__
SORT file.name ASC
```
