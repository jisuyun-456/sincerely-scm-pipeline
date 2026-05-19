---
type: community
cohesion: 0.20
members: 10
---

# Cluster 221: backfill_gr_stockb

**Cohesion:** 0.20 - loosely connected
**Members:** 10 nodes

## Members
- [[WMS_GoodsReceipt + WMS_StockBatch backfill Source txn_batches.json의 501 입하(무PO]] - rationale - _archive/wms/backfill_gr_stockbatch.py
- [[api_get()]] - code - _archive/wms/backfill_gr_stockbatch.py
- [[api_post()]] - code - _archive/wms/backfill_gr_stockbatch.py
- [[backfill_gr_stockbatch.py]] - code - _archive/wms/backfill_gr_stockbatch.py
- [[extract_supplier()]] - code - _archive/wms/backfill_gr_stockbatch.py
- [[map_qc()]] - code - _archive/wms/backfill_gr_stockbatch.py
- [[sort_key()]] - code - _archive/wms/backfill_gr_stockbatch.py
- [[to_datetime()]] - code - _archive/wms/backfill_gr_stockbatch.py
- [[날짜 문자열 → Airtable dateTime 포맷 (UTC 0000)]] - rationale - _archive/wms/backfill_gr_stockbatch.py
- [[이동물품 'PT...-명칭  공급업체명' → 공급업체명]] - rationale - _archive/wms/backfill_gr_stockbatch.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_221_backfill_gr_stockb
SORT file.name ASC
```
